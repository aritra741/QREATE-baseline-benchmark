"""Zero-Qwen replay that repairs checked-ranker labels. Does not modify frozen artifacts or call a model."""

from __future__ import annotations

import builtins
import hashlib
import json
import pickle
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

BLOCKED = (
    "/quwarts_legal_shared_reachability",
    "/quwarts_legal_cost_aware_reachability",
    "/quwarts_legal_evidence_card_aggregation_audit",
    "/quwarts_legal_checked_rank_integrity_audit",
    "/ground_truth",
)
_REAL_OPEN = builtins.open


def _blocked(path: Any) -> bool:
    text = str(path).replace("\\", "/")
    if any(token in text for token in BLOCKED):
        return True
    if text.endswith("/quwarts_legal_checked_rank/REPORT.md") or text.endswith("/quwarts_legal_checked_rank/post_freeze.json"):
        return True
    if "docetl_legal" in text and not text.endswith("query_manifest.json"):
        return True
    return False


def _guarded_open(file, *args, **kwargs):
    if _blocked(file):
        raise RuntimeError(f"forbidden artifact access blocked: {file}")
    return _REAL_OPEN(file, *args, **kwargs)


builtins.open = _guarded_open

from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, official_bag
from quwarts.core.materialize import file_sha256
from quwarts.core.provenance import document_stem
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import mapping_from_rows, _hash, _null

FROZEN = ROOT / "results" / "quwarts_legal_checked_rank"
INV = ROOT / "results" / "quwarts_legal_multichannel_candidates" / "candidate_inventory.json"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_legal_case80"
SOURCE = ROOT / "source_data" / "Legal" / "legal_case"
SCHEMA = ROOT / "Query" / "Legal" / "Legal_attributes.json"
OUT = ROOT / "results" / "quwarts_legal_checked_rank_label_repair"
TABLE = "legal"
KEEP = "KEEP_PLUMBING"
UNCERTAIN = "UNCERTAIN"
WRITE = "WRITE"
DO_NOT_WRITE = "DO_NOT_WRITE"
DET = {"surface", "normalized", "workload_label"}
CHANNEL_RANK = {"surface": 0, "normalized": 1, "workload_label": 2}
CAUSAL = 3_626_478
PARAMS = {"n_estimators": 50, "max_depth": 2, "learning_rate": 0.1, "random_state": 120}
MARGIN = 0.02
SCORE_FLOOR = 0.50
GATE_NU = 0.10
POLICIES = (
    "ranker_only",
    "write_gate_then_ranker",
    "write_gate_then_highest_priority_channel",
    "write_gate_then_source_supported_channel",
    "committed_pattern_only",
    "nearest_positive_pattern_then_ranker",
)


def sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def tokens(text: str) -> set[str]:
    return {part for part in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(part) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def channel_of(item: dict[str, Any]) -> str:
    raw = str(item.get("channel") or item.get("derivation") or "surface")
    return "composed" if raw.startswith("composed") else raw


def det_items(rec: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not rec:
        return []
    return [item for item in (rec.get("all_candidates") or rec.get("candidates") or []) if channel_of(item) in DET]


def canonical_value(value: Any, spec) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if spec.dtype == "numeric":
        got, _, err = normalize_value(text, "numeric")
        if not err and isinstance(got, (int, float)):
            number = float(got)
            return str(int(number)) if number.is_integer() else f"{number:.10g}"
        if "year" in spec.name.lower():
            year = re.search(r"\b(?:19|20)\d{2}\b", text)
            if year:
                return year.group(0)
        return ""
    folded = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return re.sub(r"\s+", " ", folded)


def same_value(left: Any, right: Any, spec) -> bool:
    a, b = canonical_value(left, spec), canonical_value(right, spec)
    return bool(a) and a == b


def feature_row(item, spec, rec_items, roles, desc_tokens, doc_len) -> list[float]:
    ch = channel_of(item)
    blob = " ".join(str(item.get(key) or "") for key in ("local_text", "raw_span", "heading", "column_header", "table_title"))
    blob_tokens = tokens(blob)
    start = float(item.get("start") or 0) / max(doc_len, 1)
    return [
        1 if ch == "surface" else 0,
        1 if ch == "normalized" else 0,
        1 if ch == "workload_label" else 0,
        0,
        1 if (item.get("evidence_spans") or item.get("raw_span")) else 0,
        jaccard(desc_tokens, blob_tokens),
        jaccard(desc_tokens, tokens(item.get("heading") or item.get("table_title") or "")),
        jaccard(tokens(spec.name), blob_tokens),
        1 if item.get("period") else 0,
        1 if spec.dtype == "numeric" else 0,
        float(len(str(item.get("normalized") or ""))),
        float(item.get("occurrence") or item.get("count") or 1),
        start,
        jaccard(desc_tokens, tokens(item.get("local_text") or "")),
        1 if ch == "workload_label" else 0,
        float(len(rec_items)),
        1,
        float(roles.get("WHERE") or 0),
        float(roles.get("GROUP BY") or 0),
        float(roles.get("HAVING") or 0),
        float(roles.get("aggregate input") or 0),
        1,
        0,
    ]


def has_span(item: dict[str, Any]) -> bool:
    return bool(item.get("evidence_spans") or item.get("raw_span"))


def verifier_hit(label: dict[str, Any] | None, cid: str) -> int:
    verify = (label or {}).get("verify") if isinstance((label or {}).get("verify"), dict) else {}
    if str(verify.get("decision") or "") == cid:
        return 1
    supported = verify.get("supported_candidate_ids") or []
    if isinstance(supported, str):
        supported = [part.strip() for part in supported.replace(";", ",").split(",") if part.strip()]
    return int(cid in {str(item) for item in supported})


def pick_member(members: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(members, key=lambda item: (0 if item["has_span"] else 1, 0 if item["verifier"] else 1, CHANNEL_RANK.get(item["channel"], 9), item["id"]))[0]


def choose_class(scored: list[dict[str, Any]], margin: float, score_floor: float) -> dict[str, Any] | None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in scored:
        if item["value_class"]:
            grouped[item["value_class"]].append(item)
    if not grouped:
        return None
    ranked = sorted(grouped.items(), key=lambda pair: (-max(row["score"] for row in pair[1]), pair[0]))
    best_key, best_rows = ranked[0]
    best_score = max(row["score"] for row in best_rows)
    gap = float("inf") if len(ranked) == 1 else best_score - max(row["score"] for row in ranked[1][1])
    if best_score < score_floor or gap < margin:
        return None
    chosen = pick_member(best_rows)
    return {"candidate_id": chosen["id"], "value_class": best_key, "score": best_score, "margin": gap if gap < 1e8 else None, "has_span": chosen["has_span"], "channel": chosen["channel"], "verifier": chosen["verifier"]}


def pattern_of(item: dict[str, Any]) -> tuple:
    return (channel_of(item), int(has_span(item)), int(bool(item.get("period"))), int(channel_of(item) == "workload_label"))


def priority_choice(scored: list[dict[str, Any]], source_only: bool) -> dict[str, Any] | None:
    rows = [row for row in scored if row["value_class"] and (row["has_span"] if source_only else True)]
    if not rows:
        return None
    chosen = pick_member(rows)
    return {"candidate_id": chosen["id"], "value_class": chosen["value_class"], "score": chosen["score"], "margin": None, "has_span": chosen["has_span"], "channel": chosen["channel"], "verifier": chosen["verifier"]}


def run_tests(spec_numeric, spec_string) -> None:
    assert canonical_value("2008", spec_numeric) == canonical_value("2008.0", spec_numeric) == "2008"
    assert canonical_value("Approved", spec_string) == canonical_value(" approved. ", spec_string)
    assert not same_value("1", "99", spec_numeric)
    assert not same_value("2", "9", spec_numeric)
    aliases = [
        {"id": "a", "score": 0.91, "value_class": "2008", "has_span": True, "channel": "surface", "verifier": 1},
        {"id": "b", "score": 0.90, "value_class": "2008", "has_span": False, "channel": "normalized", "verifier": 0},
        {"id": "c", "score": 0.20, "value_class": "1999", "has_span": True, "channel": "surface", "verifier": 0},
    ]
    chosen = choose_class(aliases, MARGIN, SCORE_FLOOR)
    assert chosen and chosen["value_class"] == "2008" and chosen["candidate_id"] == "a"
    close = [
        {"id": "a", "score": 0.60, "value_class": "2008", "has_span": True, "channel": "surface", "verifier": 0},
        {"id": "c", "score": 0.59, "value_class": "1999", "has_span": True, "channel": "surface", "verifier": 0},
    ]
    assert choose_class(close, MARGIN, SCORE_FLOOR) is None
    assert choose_class(aliases, MARGIN, SCORE_FLOOR)["candidate_id"] != KEEP
    assert WRITE != "C1" and DO_NOT_WRITE in {WRITE, DO_NOT_WRITE}


def gate_features(items: list[dict[str, Any]], spec, roles: dict[str, int]) -> list[float]:
    spans = [1.0 if has_span(item) else 0.0 for item in items]
    channels = [channel_of(item) for item in items]
    overlaps = []
    desc = tokens(spec.official_description + " " + spec.name)
    for item in items:
        blob = tokens(" ".join(str(item.get(key) or "") for key in ("local_text", "raw_span", "heading", "column_header")))
        overlaps.append(jaccard(desc, blob))
    classes = {canonical_value(item.get("normalized"), spec) for item in items}
    classes.discard("")
    return [
        float(len(items)),
        float(np.mean(spans) if spans else 0.0),
        float(channels.count("surface")),
        float(channels.count("normalized")),
        float(channels.count("workload_label")),
        float(max(overlaps) if overlaps else 0.0),
        float(np.mean(overlaps) if overlaps else 0.0),
        float(len(classes)),
        1.0 if spec.dtype == "numeric" else 0.0,
        float(roles.get("WHERE") or 0),
        float(roles.get("GROUP BY") or 0),
        float(roles.get("HAVING") or 0),
        float(roles.get("aggregate input") or 0),
    ]


def fit_gate(kind: str, xs: np.ndarray):
    scaler = StandardScaler()
    scaled = scaler.fit_transform(xs)
    if kind == "one_class_svm":
        model = OneClassSVM(kernel="rbf", nu=GATE_NU, gamma="scale")
    else:
        model = IsolationForest(n_estimators=50, contamination=GATE_NU, random_state=120)
    model.fit(scaled)
    return {"kind": kind, "scaler": scaler, "model": model}


def gate_score(bundle, row: list[float]) -> float:
    scaled = bundle["scaler"].transform(np.array([row], dtype=float))
    if bundle["kind"] == "one_class_svm":
        return float(bundle["model"].decision_function(scaled)[0])
    return float(bundle["model"].decision_function(scaled)[0])


def gate_writes(bundle, row: list[float]) -> bool:
    scaled = bundle["scaler"].transform(np.array([row], dtype=float))
    return int(bundle["model"].predict(scaled)[0]) == 1


def fit_ranker(rows: list[dict[str, Any]]):
    xs = np.array([row["x"] for row in rows], dtype=float)
    ys = np.array([row["y"] for row in rows], dtype=int)
    model = GradientBoostingClassifier(**PARAMS)
    if len(set(ys.tolist())) < 2:
        raise SystemExit("run invalid: repaired ranker labels are single-class")
    model.fit(xs, ys)
    return model


def positive_scores(model, xs: list[list[float]]) -> np.ndarray:
    proba = model.predict_proba(np.array(xs, dtype=float))
    classes = list(model.classes_)
    if 1 not in classes:
        return np.zeros(len(xs))
    return proba[:, classes.index(1)]


def main() -> int:
    source = Path(__file__).read_text()
    if "load_" + "ground_truth" in source:
        raise SystemExit("run invalid")
    OUT.mkdir(parents=True, exist_ok=True)
    sample = json.loads((FROZEN / "sample_split.json").read_text())
    train_ids = [row["entity_id"] for row in sample["train"]]
    held_ids = [row["entity_id"] for row in sample["heldout"]]
    if len(train_ids) != 80 or len(held_ids) != 40 or set(train_ids) & set(held_ids):
        raise SystemExit("run invalid: sample split is not the frozen 80/40")
    split_of = {eid: "train" for eid in train_ids}
    split_of.update({eid: "validation" for eid in held_ids})
    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    statements = {row["query_id"]: row["sql"] for row in manifest}
    query_ids = [row["query_id"] for row in manifest]
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA), records)
    attr_names = sorted(records)
    if len(attr_names) != 8:
        raise SystemExit("run invalid: attribute universe is not 8")
    inventory = json.loads(INV.read_text())
    by_ent = {(rec["entity_id"], rec["attribute"]): rec for rec in inventory}
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute('PRAGMA table_info("legal")')]
    plumbing_rows = [dict(zip(cols, rec)) for rec in conn.execute('SELECT * FROM "legal"')]
    conn.close()
    plumbing_by = {str(row.get("__entity_id")): row for row in plumbing_rows}
    doc_of = {eid: str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or ""))) for eid, row in plumbing_by.items()}
    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in SOURCE.glob("*.txt")}
    doc_len = {eid: max(len(texts.get(doc_of[eid], "")), 1) for eid in plumbing_by}
    desc_tokens = {name: tokens(specs[name].official_description + " " + name) for name in attr_names}
    cells = {}
    for line in (FROZEN / "cell_journal.jsonl").read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            cells[(row["entity_id"], row["attribute"])] = row
    numeric = next(specs[name] for name in attr_names if specs[name].dtype == "numeric")
    string = next(specs[name] for name in attr_names if specs[name].dtype != "numeric")
    run_tests(numeric, string)

    canonical = []
    for eid in train_ids + held_ids:
        for name in attr_names:
            label = cells.get((eid, name))
            if not label:
                raise SystemExit("run invalid: missing canonical cell")
            if label.get("reason") == "incumbent_non_null":
                state = "incumbent_non_null"
            elif label.get("decision") == KEEP:
                state = "extracted_keep"
            elif label.get("decision") == UNCERTAIN:
                state = "uncertain"
            elif label.get("decision"):
                state = "committed_candidate"
            else:
                raise SystemExit("run invalid: cell has no terminal state")
            items = det_items(by_ent.get((eid, name)))
            anchor = ""
            positives = []
            if state == "committed_candidate":
                anchor_item = next((item for item in items if str(item.get("id")) == str(label.get("decision"))), None)
                anchor = canonical_value(None if anchor_item is None else anchor_item.get("normalized"), specs[name])
                if not anchor and label.get("decision"):
                    raw_supported = [label.get("decision"), *(label.get("supported_candidate_ids") or [])]
                    for cid in raw_supported:
                        item = next((item for item in items if str(item.get("id")) == str(cid)), None)
                        if item is not None:
                            anchor = canonical_value(item.get("normalized"), specs[name])
                            if anchor:
                                break
                positives = [str(item.get("id")) for item in items if anchor and canonical_value(item.get("normalized"), specs[name]) == anchor]
            classes = {canonical_value(item.get("normalized"), specs[name]) for item in items}
            classes.discard("")
            canonical.append({
                "entity_id": eid,
                "document_id": doc_of.get(eid) or label.get("document_id"),
                "attribute": name,
                "split": split_of[eid],
                "state": state,
                "decision": label.get("decision"),
                "positives": positives,
                "value_class": anchor,
                "n_candidates": len(items),
                "n_value_classes": len(classes),
                "all_same_value": len(classes) <= 1,
            })
    if len(canonical) != 960:
        raise SystemExit("run invalid: canonical universe is not 960")
    by_canon = {(row["entity_id"], row["attribute"]): row for row in canonical}
    multi = [row for row in canonical if row["state"] == "committed_candidate" and len(row["positives"]) > 1]
    all_positive = [row for row in canonical if row["state"] == "committed_candidate" and row["n_candidates"] and len(row["positives"]) == row["n_candidates"]]
    if any(not row["all_same_value"] for row in all_positive):
        raise SystemExit("run invalid: an all-positive group contains different canonical values")

    def old_positive_count(entity_ids: set[str]) -> dict[str, int]:
        class Evaluator:
            def __init__(self):
                self.conn = sqlite3.connect(":memory:")
                quoted = ", ".join(f'"{c}" TEXT' for c in cols)
                self.conn.execute(f'CREATE TABLE "{TABLE}" ({quoted})')
                self.insert = f'INSERT INTO "{TABLE}" ({", ".join(chr(34)+c+chr(34) for c in cols)}) VALUES ({", ".join("?" for _ in cols)})'

            def run(self, query_id, row):
                payload = tuple(None if row.get(c) in (None, "") else str(row.get(c)) for c in cols)
                self.conn.execute(f'DELETE FROM "{TABLE}"')
                self.conn.execute(self.insert, payload)
                try:
                    return tuple(self.conn.execute(statements[query_id]).fetchall())
                except sqlite3.Error:
                    return (("__error__",),)

        evaluator = Evaluator()
        groups = positives = negatives = all_pos = 0
        for row in canonical:
            if row["entity_id"] not in entity_ids or row["state"] != "committed_candidate":
                continue
            groups += 1
            items = det_items(by_ent.get((row["entity_id"], row["attribute"])))
            anchor = next((item for item in items if str(item.get("id")) == str(row["decision"])), None)
            if anchor is None:
                continue
            spec = specs[row["attribute"]]
            queries = records[row["attribute"]].queries
            base = plumbing_by[row["entity_id"]]
            marked = {str(anchor.get("id"))}
            for item in items:
                cid = str(item.get("id"))
                if cid in marked:
                    continue
                if canonical_value(item.get("normalized"), spec) == canonical_value(anchor.get("normalized"), spec) and canonical_value(anchor.get("normalized"), spec):
                    marked.add(cid)
                    continue
                if queries and all(evaluator.run(qid, {**base, spec.name: item.get("normalized")}) == evaluator.run(qid, {**base, spec.name: anchor.get("normalized")}) for qid in queries):
                    marked.add(cid)
            positives += len(marked)
            negatives += max(len(items) - len(marked), 0)
            all_pos += int(len(items) and len(marked) == len(items))
        return {"groups": groups, "positive_rows": positives, "negative_rows": negatives, "all_positive_groups": all_pos}

    old_train = old_positive_count(set(train_ids))
    old_val = old_positive_count(set(held_ids))

    def matrix_for(entity_ids: set[str]) -> list[dict[str, Any]]:
        rows = []
        for cell in canonical:
            if cell["entity_id"] not in entity_ids or cell["state"] != "committed_candidate":
                continue
            items = det_items(by_ent.get((cell["entity_id"], cell["attribute"])))
            positive = set(cell["positives"])
            for item in items:
                cid = str(item.get("id"))
                rows.append({
                    "entity_id": cell["entity_id"],
                    "attribute": cell["attribute"],
                    "candidate_id": cid,
                    "y": int(cid in positive),
                    "x": feature_row(item, specs[cell["attribute"]], items, records[cell["attribute"]].roles, desc_tokens[cell["attribute"]], doc_len.get(cell["entity_id"], 1)),
                    "value_class": canonical_value(item.get("normalized"), specs[cell["attribute"]]),
                    "channel": channel_of(item),
                    "has_span": has_span(item),
                    "pattern": pattern_of(item),
                })
        return rows

    train_rows = matrix_for(set(train_ids))
    val_rows = matrix_for(set(held_ids))
    label_stats = {
        "train_groups": sum(row["split"] == "train" and row["state"] == "committed_candidate" for row in canonical),
        "validation_groups": sum(row["split"] == "validation" and row["state"] == "committed_candidate" for row in canonical),
        "positive_rows": sum(row["y"] for row in train_rows + val_rows),
        "negative_rows": sum(row["y"] == 0 for row in train_rows + val_rows),
        "train_positive_rows": sum(row["y"] for row in train_rows),
        "train_negative_rows": sum(row["y"] == 0 for row in train_rows),
        "validation_positive_rows": sum(row["y"] for row in val_rows),
        "validation_negative_rows": sum(row["y"] == 0 for row in val_rows),
        "multi_value_identical_groups": len(multi),
        "all_positive_groups": len(all_positive),
        "extracted_keep": sum(row["state"] == "extracted_keep" for row in canonical),
        "uncertain": sum(row["state"] == "uncertain" for row in canonical),
        "incumbent_non_null": sum(row["state"] == "incumbent_non_null" for row in canonical),
        "train_do_not_write": sum(row["split"] == "train" and row["state"] == "extracted_keep" for row in canonical),
        "old_query_equivalence": {"train": old_train, "validation": old_val},
    }
    if label_stats["train_do_not_write"] != 0:
        pass
    policy_lattice = {
        "margin": MARGIN,
        "score_floor": SCORE_FLOOR,
        "ranker": PARAMS,
        "gate_nu": GATE_NU,
        "zero_committed_attribute_writes": "forbidden_by_every_policy",
        "policies": {
            "ranker_only": "On a null cell whose attribute has a committed training example, score candidates, collapse value-identical IDs, and write iff the best value class clears the score floor and the margin against the best different value class.",
            "write_gate_then_ranker": "Write only if the novelty gate accepts the cell, then apply ranker_only.",
            "write_gate_then_highest_priority_channel": "Write only if the gate accepts. Among candidates, pick source support, then verifier hit, then surface over normalized over workload_label, then stable ID.",
            "write_gate_then_source_supported_channel": "Write only if the gate accepts and at least one candidate has a source span. Restrict the previous rule to spanned candidates.",
            "committed_pattern_only": "A candidate is eligible when its channel, span bit, period bit, and workload-literal bit occurred on a positive training row for that attribute. Write only when eligible candidates share one canonical value.",
            "nearest_positive_pattern_then_ranker": "Keep candidates within the training-only median nearest-positive distance for that attribute, then apply the ranker margin rule to that subset.",
        },
    }
    (OUT / "corrected_labels.json").write_text(json.dumps(canonical))
    (OUT / "policy_lattice.json").write_text(json.dumps(policy_lattice, indent=2))

    ranker = fit_ranker(train_rows)
    committed_train = [row for row in canonical if row["split"] == "train" and row["state"] == "committed_candidate"]
    gate_x = np.array([
        gate_features(det_items(by_ent.get((row["entity_id"], row["attribute"]))), specs[row["attribute"]], records[row["attribute"]].roles)
        for row in committed_train
    ], dtype=float)
    gates = {"one_class_svm": fit_gate("one_class_svm", gate_x), "isolation_forest": fit_gate("isolation_forest", gate_x)}

    def cell_gate_row(cell):
        return gate_features(det_items(by_ent.get((cell["entity_id"], cell["attribute"]))), specs[cell["attribute"]], records[cell["attribute"]].roles)

    val_cells = [row for row in canonical if row["split"] == "validation" and row["state"] != "incumbent_non_null"]
    gate_choice = []
    for kind, bundle in gates.items():
        committed_hit = keep_hit = uncertain_write = n_committed = n_keep = n_uncertain = 0
        for cell in val_cells:
            accept = gate_writes(bundle, cell_gate_row(cell))
            if cell["state"] == "committed_candidate":
                n_committed += 1
                committed_hit += int(accept)
            elif cell["state"] == "extracted_keep":
                n_keep += 1
                keep_hit += int(not accept)
            elif cell["state"] == "uncertain":
                n_uncertain += 1
                uncertain_write += int(accept)
        gate_choice.append({
            "kind": kind,
            "committed_recall": committed_hit / max(n_committed, 1),
            "keep_preservation": keep_hit / max(n_keep, 1),
            "uncertain_write_rate": uncertain_write / max(n_uncertain, 1),
            "objective": (keep_hit / max(n_keep, 1), -uncertain_write / max(n_uncertain, 1), committed_hit / max(n_committed, 1)),
        })
    gate_choice.sort(key=lambda row: row["objective"], reverse=True)
    selected_gate_kind = gate_choice[0]["kind"]
    gate = gates[selected_gate_kind]
    train_patterns = {(row["attribute"],) + row["pattern"] for row in train_rows if row["y"] == 1}
    train_attr_counts = Counter(row["attribute"] for row in committed_train)
    pos_by_attr = defaultdict(list)
    for row in train_rows:
        if row["y"] == 1:
            pos_by_attr[row["attribute"]].append(np.array(row["x"], dtype=float))
    neighbor = []
    for vecs in pos_by_attr.values():
        if len(vecs) < 2:
            continue
        for i, vec in enumerate(vecs):
            neighbor.append(min(float(np.linalg.norm(vec - other)) for j, other in enumerate(vecs) if j != i))
    distance_threshold = float(np.median(neighbor)) if neighbor else 1.0
    policy_lattice["distance_threshold"] = distance_threshold
    policy_lattice["selected_gate"] = selected_gate_kind
    (OUT / "policy_lattice.json").write_text(json.dumps(policy_lattice, indent=2))

    def scored_candidates(cell, model) -> list[dict[str, Any]]:
        items = det_items(by_ent.get((cell["entity_id"], cell["attribute"])))
        if not items:
            return []
        xs = [feature_row(item, specs[cell["attribute"]], items, records[cell["attribute"]].roles, desc_tokens[cell["attribute"]], doc_len.get(cell["entity_id"], 1)) for item in items]
        scores = positive_scores(model, xs)
        label = cells.get((cell["entity_id"], cell["attribute"]))
        out = []
        for item, score, vec in zip(items, scores, xs):
            cid = str(item.get("id"))
            out.append({
                "id": cid,
                "score": float(score),
                "value_class": canonical_value(item.get("normalized"), specs[cell["attribute"]]),
                "has_span": has_span(item),
                "channel": channel_of(item),
                "verifier": verifier_hit(label, cid),
                "x": vec,
                "pattern": pattern_of(item),
                "normalized": item.get("normalized"),
            })
        return out

    def apply_policy(name: str, cell, model, gate_bundle) -> dict[str, Any] | None:
        if train_attr_counts.get(cell["attribute"], 0) <= 0:
            return None
        scored = scored_candidates(cell, model)
        allowed = gate_writes(gate_bundle, cell_gate_row(cell))
        if name == "ranker_only":
            return choose_class(scored, MARGIN, SCORE_FLOOR)
        if name == "write_gate_then_ranker":
            return choose_class(scored, MARGIN, SCORE_FLOOR) if allowed else None
        if name == "write_gate_then_highest_priority_channel":
            return priority_choice(scored, False) if allowed else None
        if name == "write_gate_then_source_supported_channel":
            return priority_choice(scored, True) if allowed else None
        if name == "committed_pattern_only":
            eligible = [row for row in scored if (cell["attribute"],) + row["pattern"] in train_patterns and row["value_class"]]
            classes = {row["value_class"] for row in eligible}
            if len(classes) != 1:
                return None
            chosen = pick_member(eligible)
            return {"candidate_id": chosen["id"], "value_class": chosen["value_class"], "score": chosen["score"], "margin": None, "has_span": chosen["has_span"], "channel": chosen["channel"], "verifier": chosen["verifier"]}
        if name == "nearest_positive_pattern_then_ranker":
            bank = pos_by_attr.get(cell["attribute"]) or []
            if not bank:
                return None
            eligible = []
            for row in scored:
                dist = min(float(np.linalg.norm(np.array(row["x"]) - other)) for other in bank)
                if dist <= distance_threshold:
                    eligible.append(row)
            return choose_class(eligible, MARGIN, SCORE_FLOOR)
        raise SystemExit("run invalid: unknown policy")

    def evaluate(name: str) -> dict[str, Any]:
        committed = correct = committed_writes = committed_correct = uncertain_writes = keep_preserved = writes = 0
        n_committed = n_uncertain = n_keep = 0
        for cell in val_cells:
            pred = apply_policy(name, cell, ranker, gate)
            wrote = pred is not None
            writes += int(wrote)
            if cell["state"] == "committed_candidate":
                n_committed += 1
                if wrote and pred["candidate_id"] in set(cell["positives"]):
                    correct += 1
                if wrote:
                    committed_writes += 1
                    committed_correct += int(pred["candidate_id"] in set(cell["positives"]))
            elif cell["state"] == "uncertain":
                n_uncertain += 1
                uncertain_writes += int(wrote)
            elif cell["state"] == "extracted_keep":
                n_keep += 1
                keep_preserved += int(not wrote)
        return {
            "policy": name,
            "candidate_accuracy": correct / max(n_committed, 1),
            "candidate_accuracy_n": [correct, n_committed],
            "committed_precision": committed_correct / committed_writes if committed_writes else 0.0,
            "committed_precision_n": [committed_correct, committed_writes],
            "uncertain_incorrect_rate": uncertain_writes / max(n_uncertain, 1),
            "uncertain_incorrect_n": [uncertain_writes, n_uncertain],
            "keep_preservation": keep_preserved / max(n_keep, 1),
            "keep_preservation_n": [keep_preserved, n_keep],
            "writes": writes,
            "objective": (
                correct / max(n_committed, 1),
                committed_correct / committed_writes if committed_writes else 0.0,
                -(uncertain_writes / max(n_uncertain, 1)),
                keep_preserved / max(n_keep, 1),
                -writes,
            ),
        }

    considered = [evaluate(name) for name in POLICIES]
    considered.sort(key=lambda row: row["objective"], reverse=True)
    selected = considered[0]

    def cell_top1(rows, model) -> dict[str, Any]:
        grouped = defaultdict(list)
        for row in rows:
            grouped[(row["entity_id"], row["attribute"])].append(row)
        hit = set_hit = set_n = 0
        xs = [row["x"] for row in rows]
        scores = {i: float(score) for i, score in enumerate(positive_scores(model, xs))}
        index = {id(row): i for i, row in enumerate(rows)}
        for group in grouped.values():
            order = sorted(group, key=lambda row: (-scores[index[id(row)]], row["candidate_id"]))
            hit += int(order[0]["y"] == 1)
            neg = [scores[index[id(row)]] for row in group if row["y"] == 0]
            ceil = max(neg) if neg else -1.0
            for row in group:
                if row["y"] == 1:
                    set_n += 1
                    set_hit += int(scores[index[id(row)]] > ceil)
        write_correct = 0
        write_n = len(committed_train)
        for cell in committed_train:
            pred = gate_writes(gate, cell_gate_row(cell))
            write_correct += int(pred)
        return {
            "writeability_recall_on_committed_train": [write_correct, write_n],
            "top1_value_class": [hit, len(grouped)],
            "positive_set_recall": [set_hit, set_n],
        }

    overfit = cell_top1(train_rows, ranker)
    baselines = {
        "always_abstain": {"candidate_accuracy": 0.0, "writes": 0, "candidate_accuracy_n": [0, selected["candidate_accuracy_n"][1]]},
    }
    # Channel baselines on the same committed-validation denominator, ignoring the gate.
    for label, source_only in (("highest_priority_channel", False), ("source_supported_channel", True)):
        hit = n = 0
        for cell in val_cells:
            if cell["state"] != "committed_candidate":
                continue
            n += 1
            pred = priority_choice(scored_candidates(cell, ranker), source_only)
            hit += int(pred is not None and pred["candidate_id"] in set(cell["positives"]))
        baselines[label] = {"candidate_accuracy": hit / max(n, 1), "candidate_accuracy_n": [hit, n]}
    baselines["repaired_ranker"] = {"policy": selected["policy"], "candidate_accuracy": selected["candidate_accuracy"], "candidate_accuracy_n": selected["candidate_accuracy_n"]}
    (OUT / "validation.json").write_text(json.dumps({"gates": gate_choice, "policies": considered, "selected": selected, "overfit": overfit, "baselines": baselines, "distance_threshold": distance_threshold}, indent=2))

    all_rows = matrix_for(set(train_ids) | set(held_ids))
    final_ranker = fit_ranker(all_rows)
    all_committed = [row for row in canonical if row["state"] == "committed_candidate"]
    final_gate = fit_gate(selected_gate_kind, np.array([cell_gate_row(row) for row in all_committed], dtype=float))
    final_patterns = {(row["attribute"],) + row["pattern"] for row in all_rows if row["y"] == 1}
    final_counts = Counter(row["attribute"] for row in all_committed)
    final_pos = defaultdict(list)
    for row in all_rows:
        if row["y"] == 1:
            final_pos[row["attribute"]].append(np.array(row["x"], dtype=float))
    # Application uses the refit sample as the committed-example set. Policies still forbid attributes with zero committed sample examples.
    saved_counts, saved_patterns, saved_pos = train_attr_counts, train_patterns, pos_by_attr
    train_attr_counts, train_patterns, pos_by_attr = final_counts, final_patterns, final_pos
    trace = []
    fills = defaultdict(dict)
    for eid, prow in plumbing_by.items():
        for name in attr_names:
            if prow.get(name) not in (None, ""):
                continue
            cell = {"entity_id": eid, "attribute": name, "document_id": doc_of[eid], "state": "full_corpus", "positives": []}
            pred = apply_policy(selected["policy"], cell, final_ranker, final_gate)
            gate_value = gate_score(final_gate, cell_gate_row(cell))
            if pred is None:
                continue
            item = next((item for item in det_items(by_ent.get((eid, name))) if str(item.get("id")) == pred["candidate_id"]), None)
            if item is None or _null(item.get("normalized")):
                continue
            bank = final_pos.get(name) or []
            nearest = None
            if bank:
                vec = np.array(feature_row(item, specs[name], det_items(by_ent.get((eid, name))), records[name].roles, desc_tokens[name], doc_len.get(eid, 1)), dtype=float)
                nearest = min(float(np.linalg.norm(vec - other)) for other in bank)
            fills[doc_of[eid]][name] = item.get("normalized")
            trace.append({
                "entity_id": eid,
                "document_id": doc_of[eid],
                "attribute": name,
                "candidate_id": pred["candidate_id"],
                "gate_score": gate_value,
                "value_class": pred["value_class"],
                "rank_score": pred["score"],
                "margin": pred["margin"],
                "nearest_positive_distance": nearest,
                "attribute_had_committed_examples": final_counts[name] > 0,
                "has_span": pred["has_span"],
                "channel": pred["channel"],
                "verifier": pred["verifier"],
            })
    train_attr_counts, train_patterns, pos_by_attr = saved_counts, saved_patterns, saved_pos
    forbidden = [row for row in trace if not row["attribute_had_committed_examples"]]
    if forbidden:
        raise SystemExit("run invalid: wrote an attribute with zero committed examples")
    (OUT / "assignment_trace.json").write_text(json.dumps(trace, indent=2))
    manifest_assign = defaultdict(dict)
    for row in trace:
        manifest_assign[row["document_id"]][row["attribute"]] = row["candidate_id"]
    (OUT / "assignment_manifest.json").write_text(json.dumps(manifest_assign, indent=2))
    with _REAL_OPEN(OUT / "models.pkl", "wb") as handle:
        pickle.dump({"ranker": final_ranker, "gate": final_gate, "policy": selected["policy"]}, handle)

    mapping = mapping_from_rows(plumbing_rows)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    def materialize(dest: Path, use_fills) -> dict[str, Any]:
        copy_plumbing(PLUMBING, dest)
        overlay = apply_overlay(dest, use_fills, mapping, table=TABLE)
        bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
        return {"overlay": overlay, "bags": bags, "bag_sha256": _hash(bags)}

    official = materialize(OUT / "databases" / "official.db", fills)
    rebuild = materialize(OUT / "databases" / "official_rebuild.db", fills)
    if official["bag_sha256"] != rebuild["bag_sha256"]:
        raise SystemExit("run invalid: rebuild mismatch")
    empty_dest = OUT / "databases" / "empty_overlay.db"
    copy_plumbing(PLUMBING, empty_dest)
    empty = apply_overlay(empty_dest, {}, mapping, table=TABLE)
    if int(empty.get("changed_cells") or 0) != 0:
        raise SystemExit("run invalid: empty overlay changed cells")
    (OUT / "bags").mkdir(parents=True, exist_ok=True)
    (OUT / "bags" / "official.json").write_text(json.dumps(official["bags"], indent=2, default=str))
    by_attr = Counter(row["attribute"] for row in trace)
    by_channel = Counter(row["channel"] for row in trace)
    pre_gold = {
        "labels": label_stats,
        "selected_policy": selected,
        "gates": gate_choice,
        "overfit": overfit,
        "baselines": baselines,
        "writes": len(trace),
        "accepted": official["overlay"].get("changed_cells"),
        "writes_by_attribute": dict(by_attr),
        "writes_by_channel": dict(by_channel),
        "causal_spent": CAUSAL,
        "new_model_spend": 0,
        "empty_overlay_writes": empty.get("changed_cells"),
        "rebuild_match": True,
        "distance_threshold": distance_threshold,
        "selected_gate": selected_gate_kind,
    }
    (OUT / "pre_gold.json").write_text(json.dumps(pre_gold, indent=2, default=str))
    ledger = {"theta_charge": CAUSAL, "new_model_spend": 0, "total": CAUSAL, "purpose": "frozen_checked_extraction_replay"}
    (OUT / "theta25_ledger.json").write_text(json.dumps(ledger, indent=2))
    frozen = {
        "labels": sha(canonical),
        "policy_lattice": sha(policy_lattice),
        "validation": file_sha256(OUT / "validation.json"),
        "selected_policy": sha(selected),
        "models": file_sha256(OUT / "models.pkl"),
        "assignment": file_sha256(OUT / "assignment_manifest.json"),
        "official_db": file_sha256(OUT / "databases" / "official.db"),
        "official_bags": official["bag_sha256"],
        "configuration": sha(policy_lattice),
        "ledger": sha(ledger),
        "causal_spent": CAUSAL,
        "new_model_spend": 0,
        "rebuild_match": True,
        "gold_loaded": False,
        "writes": len(trace),
    }
    (OUT / "generation_frozen.json").write_text(json.dumps(frozen, indent=2))
    print(json.dumps({"frozen": True, "policy": selected["policy"], "writes": len(trace), "labels": label_stats, "objective": selected["objective"]}, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
