"""Zero-Qwen causal audit of the frozen Legal corpus-probe optimizer. Read-only on frozen artifacts."""

from __future__ import annotations

import hashlib
import itertools
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.amortized_select.executor import execute_cell
from quwarts.core.amortized_select.features import annotate_set, spec_tokens
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import mapping_from_rows, _null
from quwarts.eval.legal_coverage_transfer import (
    DOCETL_DIR,
    DOCETL_PRODUCT,
    SCHEMA_PATH,
    gold_index,
    gold_value,
    load_plumbing_rows,
    score_db,
)
from quwarts.eval.legal_multichannel_availability_audit import RowEvaluator, exact_gold, observational_match
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites
from diagnostics.run_config_grid import load_ground_truth

FROZEN = ROOT / "results" / "quwarts_legal_corpus_probe"
INV = ROOT / "results" / "quwarts_legal_multichannel_candidates" / "candidate_inventory.json"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
OUT = ROOT / "results" / "quwarts_legal_corpus_probe_causal_audit"
KEEP = "KEEP_PLUMBING"
DET = {"surface", "normalized", "workload_label"}
DOCETL = DOCETL_PRODUCT


def sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def channel_of(item: dict[str, Any]) -> str:
    raw = str(item.get("channel") or item.get("derivation") or "surface")
    return "composed" if raw.startswith("composed") else raw


def det_items(rec: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in (rec.get("all_candidates") or rec.get("candidates") or []) if channel_of(item) in DET]


def norm_text(value: Any, dtype: str) -> str:
    if value in (None, ""):
        return ""
    got, _, err = normalize_value(value, dtype)
    if err or got is None:
        return str(value).strip().lower()
    return str(got).strip().lower()


def frozen_map(value: Any, items: list[dict[str, Any]], dtype: str) -> str | None:
    if value in (None, "", "NOT_PRESENT", "unresolved"):
        return None
    want = norm_text(value, dtype)
    for item in items:
        if norm_text(item.get("normalized"), dtype) == want and want:
            return str(item.get("id"))
    for item in items:
        if str(item.get("raw_span") or "").strip().lower() == str(value).strip().lower():
            return str(item.get("id"))
    return None


def execute_program(spec: dict[str, Any], feats: list[dict[str, Any]]) -> dict[str, Any]:
    preferred = spec.get("preferred_channels") or []
    rejected = spec.get("rejected_channels") or []
    filtered = []
    for feat in feats:
        ch = str(feat.get("channel") or "")
        if rejected and ch in rejected:
            continue
        if preferred and ch not in preferred:
            continue
        filtered.append(feat)
    return execute_cell(spec, filtered or feats)


def rankdata(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / dx / dy if dx and dy else 0.0


def spearman(xs: list[float], ys: list[float]) -> float:
    return pearson(rankdata(xs), rankdata(ys))


def kendall(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = xs[i] - xs[j], ys[i] - ys[j]
            if a == 0 or b == 0:
                continue
            if a * b > 0:
                conc += 1
            else:
                disc += 1
    total = conc + disc
    return (conc - disc) / total if total else 0.0


def pack_score(scored: dict[str, Any], accepted: int) -> dict[str, Any]:
    return {
        "f2": scored["mean_structure_f2"],
        "f1": scored["mean_cell_f1_at_0.20"],
        "product": scored["mean_per_query_product"],
        "accepted": accepted,
        "per_query": scored["per_query"],
    }


def materialize_and_score(dest: Path, fills, mapping, statements, predicates, query_ids, gold) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    copy_plumbing(PLUMBING, dest)
    overlay = apply_overlay(dest, fills, mapping, table="legal")
    scored = score_db(dest, statements, predicates, query_ids, gold)
    accepted = int(overlay.get("changed_cells") or 0)
    return {**pack_score(scored, accepted), "blocked": overlay.get("blocked")}


def fills_from_choice(choice: dict[tuple[str, str], str | None], by_ent, doc_of) -> dict[str, dict[str, Any]]:
    fills: dict[str, dict[str, Any]] = defaultdict(dict)
    for (eid, name), cid in choice.items():
        if not cid or cid == KEEP:
            continue
        rec = by_ent.get((eid, name))
        if rec is None:
            continue
        item = next((item for item in det_items(rec) if str(item.get("id")) == cid), None)
        if item is None or _null(item.get("normalized")):
            continue
        fills[doc_of[eid]][name] = item.get("normalized")
    return dict(fills)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inventory = json.loads(INV.read_text())
    programs = json.loads((FROZEN / "programs.json").read_text())
    sample = json.loads((FROZEN / "sample_split.json").read_text())
    pre = json.loads((FROZEN / "pre_gold.json").read_text())
    selected = json.loads((FROZEN / "selected_config.json").read_text()) if (FROZEN / "selected_config.json").is_file() else pre["selected"]
    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    attr_names = sorted(records)
    plumbing_rows = load_plumbing_rows()
    mapping = mapping_from_rows(plumbing_rows)
    gold = load_ground_truth(gold_name("Legal"))
    gold_by = gold_index(gold)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_by = {str(row.get("__entity_id")): row for row in plumbing_rows}
    by_ent = {(rec["entity_id"], rec["attribute"]): rec for rec in inventory}
    doc_of = {}
    for row in plumbing_rows:
        doc_of[str(row.get("__entity_id"))] = str(row.get("__provenance_label") or Path(str(row.get("doc_id") or "")).stem)
    evaluator = RowEvaluator(list(plumbing_rows[0]), statements)
    queries_by_attr = {name: list(records[name].queries) for name in records}
    train_ids = {row["entity_id"] for row in sample["train"]}
    held_ids = {row["entity_id"] for row in sample["heldout"]}
    sample_ids = train_ids | held_ids
    silver = []
    for line in (FROZEN / "silver_journal.jsonl").read_text().splitlines():
        if line.strip():
            silver.append(json.loads(line))
    silver_by = {(row["entity_id"], row["attribute"]): row for row in silver}

    def gold_of(eid: str, name: str):
        return gold_value(gold_by, doc_of[eid], name)

    def span_recorded(row: dict[str, Any]) -> bool:
        for key in ("probe_a", "probe_b", "adjudicate"):
            parsed = (row.get(key) or {}).get("parsed") or {}
            spans = parsed.get("spans") or []
            if spans:
                return True
        return False

    def probe_agreed(row: dict[str, Any]) -> bool:
        a = (row.get("probe_a") or {}).get("parsed") or {}
        b = (row.get("probe_b") or {}).get("parsed") or {}
        pa, pb = str(a.get("presence") or "").upper(), str(b.get("presence") or "").upper()
        if pa == pb == "NOT_PRESENT":
            return True
        if pa.startswith("PRESENT") and pb.startswith("PRESENT"):
            return norm_text(a.get("normalized") or a.get("value"), specs[row["attribute"]].dtype) == norm_text(b.get("normalized") or b.get("value"), specs[row["attribute"]].dtype)
        return False

    cells = []
    for row in silver:
        eid, name = row["entity_id"], row["attribute"]
        spec = specs[name]
        gv = gold_of(eid, name)
        gold_null = gv in (None, "")
        status = row.get("status")
        pred = row.get("value") if status == "value" else None
        exact = bool(pred is not None and exact_gold(specs, name, pred, gv))
        typed = False
        if pred is not None and not gold_null:
            typed = norm_text(pred, spec.dtype) == norm_text(gv, spec.dtype) and norm_text(gv, spec.dtype) != ""
        presence_null = bool(gold_null and status == "NOT_PRESENT")
        presence_pos = bool((not gold_null) and status == "value")
        obs = False
        if not gold_null and pred is not None:
            obs = observational_match(evaluator, queries_by_attr.get(name) or [], plumbing_by[eid], name, pred, gv)
        elif gold_null and status == "NOT_PRESENT":
            obs = True
        if status == "unresolved":
            klass = "unresolved"
        elif exact:
            klass = "exact"
        elif typed:
            klass = "typed_only"
        elif obs and status == "value":
            klass = "observational_only"
        elif status == "NOT_PRESENT" and not gold_null:
            klass = "incorrect_NOT_PRESENT"
        elif status == "value" and gold_null:
            klass = "incorrect_value_on_null_gold"
        elif status == "value":
            klass = "incorrect_value"
        elif status == "NOT_PRESENT" and gold_null:
            klass = "null_presence_agreement"
        else:
            klass = status or "other"
        silver_correct = klass in {"exact", "typed_only", "null_presence_agreement"}
        cells.append({
            "entity_id": eid,
            "document_id": row["document_id"],
            "attribute": name,
            "split": "train" if eid in train_ids else "heldout",
            "mode": row.get("mode"),
            "status": status,
            "probe_agreement": probe_agreed(row) and not row.get("adjudicate"),
            "adjudicated": bool(row.get("adjudicate")),
            "span": span_recorded(row),
            "class": klass,
            "exact": exact,
            "typed": typed or exact,
            "observational": obs,
            "presence_agreement": presence_null or presence_pos,
            "gold_null": gold_null,
            "silver_correct": silver_correct,
            "value": pred,
            "gold": gv,
            "mapped_id": row.get("mapped_id"),
        })

    def rate(rows, pred) -> dict[str, Any]:
        n = len(rows)
        k = sum(1 for row in rows if pred(row))
        return {"n": n, "k": k, "rate": k / n if n else 0.0}

    breakdowns = {}
    for key in ("attribute", "split", "mode", "status"):
        breakdowns[key] = {}
        groups = defaultdict(list)
        for row in cells:
            groups[row[key]].append(row)
        for name, rows in sorted(groups.items(), key=lambda item: str(item[0])):
            breakdowns[key][str(name)] = {
                "n": len(rows),
                "exact": rate(rows, lambda r: r["exact"])["rate"],
                "typed": rate(rows, lambda r: r["typed"])["rate"],
                "observational": rate(rows, lambda r: r["observational"])["rate"],
                "presence_agreement": rate(rows, lambda r: r["presence_agreement"])["rate"],
                "incorrect_value": rate(rows, lambda r: r["class"] in {"incorrect_value", "incorrect_value_on_null_gold"})["rate"],
                "incorrect_NOT_PRESENT": rate(rows, lambda r: r["class"] == "incorrect_NOT_PRESENT")["rate"],
                "unresolved": rate(rows, lambda r: r["class"] == "unresolved")["rate"],
                "silver_correct": rate(rows, lambda r: r["silver_correct"])["rate"],
                "class_counts": dict(Counter(r["class"] for r in rows)),
            }
    for key, pred in (("probe_agreement", lambda r: r["probe_agreement"]), ("adjudicated", lambda r: r["adjudicated"]), ("span", lambda r: r["span"])):
        breakdowns[key] = {}
        for flag in (True, False):
            rows = [r for r in cells if pred(r) is flag]
            breakdowns[key][str(flag)] = {
                "n": len(rows),
                "exact": rate(rows, lambda r: r["exact"])["rate"],
                "silver_correct": rate(rows, lambda r: r["silver_correct"])["rate"],
                "class_counts": dict(Counter(r["class"] for r in rows)),
            }

    # Mapping funnel
    cross = Counter()
    funnel = Counter()
    fail_reasons = Counter()
    fail_examples = []
    gold_positive = [r for r in cells if not r["gold_null"]]
    silver_values = [r for r in cells if r["status"] == "value"]
    mapped_n = sum(1 for r in cells if r["mapped_id"])
    for row in cells:
        eid, name = row["entity_id"], row["attribute"]
        rec = by_ent.get((eid, name)) or {}
        items = det_items(rec)
        spec = specs[name]
        gv, sv = row["gold"], row["value"]
        gold_ids = []
        silver_ids = []
        if not row["gold_null"]:
            for item in items:
                if exact_gold(specs, name, item.get("normalized"), gv) or observational_match(evaluator, queries_by_attr.get(name) or [], plumbing_by[eid], name, item.get("normalized"), gv):
                    gold_ids.append(str(item.get("id")))
        if row["status"] == "value":
            want = norm_text(sv, spec.dtype)
            exact_ids, canon_ids, obs_ids, alias_ids = [], [], [], []
            for item in items:
                nid = str(item.get("id"))
                if norm_text(item.get("normalized"), spec.dtype) == want and want:
                    exact_ids.append(nid)
                elif str(item.get("normalized") or "").strip().lower() == str(sv).strip().lower():
                    canon_ids.append(nid)
                elif observational_match(evaluator, queries_by_attr.get(name) or [], plumbing_by[eid], name, item.get("normalized"), sv):
                    obs_ids.append(nid)
                else:
                    blob = " ".join(str(item.get(k) or "") for k in ("raw_span", "local_text")).lower()
                    spans = []
                    for key in ("probe_a", "adjudicate"):
                        spans.extend((row and []) or [])
                    if str(sv).strip().lower() and str(sv).strip().lower() in blob:
                        alias_ids.append(nid)
            # recompute spans from silver journal
            src = silver_by[(eid, name)]
            span_text = []
            for key in ("probe_a", "probe_b", "adjudicate"):
                for span in ((src.get(key) or {}).get("parsed") or {}).get("spans") or []:
                    span_text.append(str(span).lower())
            for item in items:
                nid = str(item.get("id"))
                blob = " ".join(str(item.get(k) or "") for k in ("raw_span", "local_text")).lower()
                if any(piece and piece.strip("[]'\" ")[:40] in blob for piece in span_text):
                    if nid not in exact_ids and nid not in alias_ids:
                        alias_ids.append(nid)
            if exact_ids:
                outcome, silver_ids = "1_exact_candidate_value", exact_ids
            elif canon_ids:
                outcome, silver_ids = "2_canonical_typed", canon_ids
            elif obs_ids:
                outcome, silver_ids = "4_observational_candidate", obs_ids
            elif alias_ids:
                outcome, silver_ids = "5_alias_or_span", alias_ids
            elif gold_ids and not row["silver_correct"]:
                outcome = "6_gold_candidate_not_silver"
            elif row["silver_correct"] and not gold_ids:
                outcome = "7_silver_correct_no_candidate"
            elif not row["silver_correct"]:
                outcome = "8_silver_wrong"
            else:
                outcome = "10_mapper_or_normalization"
            distinct_norms = {norm_text(item.get("normalized"), spec.dtype) for item in items if norm_text(item.get("normalized"), spec.dtype) == want}
            if len(exact_ids) > 1 and len({norm_text(next(i.get("normalized") for i in items if str(i.get("id")) == cid), spec.dtype) for cid in exact_ids}) > 1:
                outcome = "9_ambiguous_multiple"
            funnel[outcome] += 1
        elif row["status"] == "NOT_PRESENT":
            funnel["not_present_no_map"] += 1
            outcome = "not_present"
        else:
            funnel["unresolved_no_map"] += 1
            outcome = "unresolved"
        silver_eq = bool(silver_ids) if row["status"] == "value" else False
        gold_eq = bool(gold_ids)
        selected_it = bool(row["mapped_id"] and ((row["mapped_id"] in silver_ids) or (row["mapped_id"] in gold_ids and row["silver_correct"])))
        if row["status"] == "value":
            cross[(row["silver_correct"], gold_eq, silver_eq, selected_it)] += 1
            if row["silver_correct"] and silver_eq and not row["mapped_id"]:
                frozen_id = frozen_map(sv, items, spec.dtype)
                reason = "frozen_mapper_returned_none" if frozen_id is None else "stored_mapped_id_missing_but_rematch_hits"
                if frozen_id and frozen_id != row["mapped_id"]:
                    reason = "stored_mapping_differs_from_replay"
                fail_reasons[reason] += 1
                if len(fail_examples) < 25:
                    fail_examples.append({"entity_id": eid, "attribute": name, "value": sv, "gold": gv, "reason": reason, "candidate_ids": silver_ids[:5]})
            elif row["silver_correct"] and not silver_eq:
                fail_reasons["no_equivalent_deterministic_candidate"] += 1

    cross_rows = [
        {"silver_correct": a, "gold_equivalent_candidate": b, "silver_equivalent_candidate": c, "mapper_selected_it": d, "count": n}
        for (a, b, c, d), n in sorted(cross.items(), key=lambda item: -item[1])
    ]
    silver_correct_pos = [r for r in gold_positive if r["silver_correct"]]
    correctly_mapped = 0
    obs_mappable = 0
    for row in silver_correct_pos:
        eid, name = row["entity_id"], row["attribute"]
        items = det_items(by_ent.get((eid, name)) or {})
        gv = row["gold"]
        ids = []
        for item in items:
            if exact_gold(specs, name, item.get("normalized"), gv) or (row["value"] is not None and norm_text(item.get("normalized"), specs[name].dtype) == norm_text(row["value"], specs[name].dtype)):
                ids.append(str(item.get("id")))
            elif observational_match(evaluator, queries_by_attr.get(name) or [], plumbing_by[eid], name, item.get("normalized"), gv):
                ids.append(str(item.get("id")))
        if any(exact_gold(specs, name, item.get("normalized"), gv) or observational_match(evaluator, queries_by_attr.get(name) or [], plumbing_by[eid], name, item.get("normalized"), gv) for item in items):
            obs_mappable += 1
        if row["mapped_id"] and row["mapped_id"] in ids:
            correctly_mapped += 1
    mapping_rates = {
        "mapped_over_768": {"k": mapped_n, "n": len(cells), "rate": mapped_n / max(len(cells), 1)},
        "mapped_over_silver_value": {"k": sum(1 for r in silver_values if r["mapped_id"]), "n": len(silver_values), "rate": sum(1 for r in silver_values if r["mapped_id"]) / max(len(silver_values), 1)},
        "gold_equivalent_candidate_over_gold_positive": {
            "k": sum(1 for r in gold_positive if any(exact_gold(specs, r["attribute"], item.get("normalized"), r["gold"]) or observational_match(evaluator, queries_by_attr.get(r["attribute"]) or [], plumbing_by[r["entity_id"]], r["attribute"], item.get("normalized"), r["gold"]) for item in det_items(by_ent.get((r["entity_id"], r["attribute"])) or {}))),
            "n": len(gold_positive),
        },
        "correctly_mapped_over_silver_correct_positive": {"k": correctly_mapped, "n": len(silver_correct_pos)},
        "observationally_mappable_over_silver_correct_positive": {"k": obs_mappable, "n": len(silver_correct_pos)},
    }
    for key, row in mapping_rates.items():
        row["rate"] = row["k"] / row["n"] if row["n"] else 0.0

    print(json.dumps({"silver_correct": rate(cells, lambda r: r["silver_correct"]), "exact_on_positive": rate(gold_positive, lambda r: r["exact"]), "mapping_rates": mapping_rates, "funnel": dict(funnel)}, indent=2), flush=True)

    # Program fills on the full corpus
    feats = {}
    for rec in inventory:
        text_len = len(str(rec.get("document_id") or ""))
        feats[(rec["entity_id"], rec["attribute"])] = annotate_set({"candidates": det_items(rec)}, spec_tokens(rec["attribute"], specs[rec["attribute"]].official_description), 1000)
        by_id = {str(item.get("id")): item for item in det_items(rec)}
        for feat in feats[(rec["entity_id"], rec["attribute"])]:
            src = by_id.get(str(feat.get("id") or ""))
            feat["channel"] = channel_of(src) if src else "surface"
    prog_choice: dict[str, list[dict[tuple[str, str], str]]] = {}
    prog_sig: dict[str, list[str]] = {}
    for name in attr_names:
        prog_choice[name] = []
        prog_sig[name] = []
        for spec_prog in programs[name]:
            choice = {}
            for rec in inventory:
                if rec["attribute"] != name:
                    continue
                pred = execute_program(spec_prog, feats.get((rec["entity_id"], name)) or [])
                cid = (pred.get("candidate_ids") or [None])[0] if pred.get("status") == "selected" else KEEP
                if cid and cid != KEEP:
                    choice[(rec["entity_id"], name)] = str(cid)
            sig = sha(sorted(choice.items()))
            prog_choice[name].append(choice)
            prog_sig[name].append(sig)
    unique_counts = {name: len(set(prog_sig[name])) for name in attr_names}
    print(json.dumps({"unique_program_signatures": unique_counts}, indent=2), flush=True)

    def score_choice(choice, dest: Path, entity_filter: set[str] | None, gold_obj) -> dict[str, Any]:
        use = choice
        if entity_filter is not None:
            use = {key: cid for key, cid in choice.items() if key[0] in entity_filter}
        fills = fills_from_choice(use, by_ent, doc_of)
        if entity_filter is not None:
            # sample database: copy plumbing then delete other rows before overlay
            dest.parent.mkdir(parents=True, exist_ok=True)
            copy_plumbing(PLUMBING, dest)
            conn = sqlite3.connect(str(dest))
            ids = list(entity_filter)
            conn.execute(f'DELETE FROM legal WHERE __entity_id NOT IN ({",".join("?" for _ in ids)})', ids)
            conn.commit()
            conn.close()
            overlay = apply_overlay(dest, fills, mapping, table="legal")
            scored = score_db(dest, statements, predicates, query_ids, gold_obj)
            return {**pack_score(scored, int(overlay.get("changed_cells") or 0))}
        return materialize_and_score(dest, fills, mapping, statements, predicates, query_ids, gold_obj)

    sample_docs = {doc_of[eid] for eid in sample_ids}
    gold_rows = gold.get("legal") or gold.get("Legal") or []
    gold_sample = {"legal": [row for row in gold_rows if Path(str(row.get("doc_id") or "")).stem in sample_docs or str(row.get("doc_id") or "") in sample_docs]}

    # A candidate ceiling on the sample
    ceil_a = {}
    for eid in sample_ids:
        for name in attr_names:
            gv = gold_of(eid, name)
            items = det_items(by_ent.get((eid, name)) or {})
            best = None
            for item in items:
                if gv not in (None, "") and exact_gold(specs, name, item.get("normalized"), gv):
                    best = str(item.get("id"))
                    break
            if best is None and gv not in (None, ""):
                for item in items:
                    if observational_match(evaluator, queries_by_attr.get(name) or [], plumbing_by[eid], name, item.get("normalized"), gv):
                        best = str(item.get("id"))
                        break
            ceil_a[(eid, name)] = best or KEEP
    ceiling_A = score_choice(ceil_a, OUT / "databases" / "ceiling_A_sample.db", sample_ids, gold_sample)

    # B correct-silver equivalence ceiling on the sample
    ceil_b = {}
    for row in cells:
        if not row["silver_correct"] or row["gold_null"]:
            continue
        eid, name = row["entity_id"], row["attribute"]
        items = det_items(by_ent.get((eid, name)) or {})
        best = None
        for item in items:
            if exact_gold(specs, name, item.get("normalized"), row["gold"]) or norm_text(item.get("normalized"), specs[name].dtype) == norm_text(row["value"], specs[name].dtype):
                best = str(item.get("id"))
                break
        if best is None:
            for item in items:
                if observational_match(evaluator, queries_by_attr.get(name) or [], plumbing_by[eid], name, item.get("normalized"), row["gold"]):
                    best = str(item.get("id"))
                    break
        if best:
            ceil_b[(eid, name)] = best
    ceiling_B = score_choice(ceil_b, OUT / "databases" / "ceiling_B_sample.db", sample_ids, gold_sample)

    # C per-attribute, full corpus, others plumbing
    ceiling_C = {}
    for name in attr_names:
        best = None
        for idx, choice in enumerate(prog_choice[name]):
            scored = score_choice(choice, OUT / "databases" / f"ceiling_C_{name}_{idx}.db", None, gold)
            row = {"program": programs[name][idx]["program_id"], **scored}
            if best is None or row["product"] > best["product"]:
                best = row
        ceiling_C[name] = best
        print(json.dumps({"C": name, "program": best["program"], "product": best["product"]}, indent=2), flush=True)

    # D shared family. Collapse identical signatures, exact enum via per-query bag cache.
    index_groups = {}
    for name in attr_names:
        groups = defaultdict(list)
        for idx, sig in enumerate(prog_sig[name]):
            groups[sig].append(idx)
        index_groups[name] = [members[0] for members in groups.values()]
    attrs_by_query = {qid: [name for name in attr_names if qid in records[name].queries] for qid in query_ids}
    state_count = 0
    for qid, names in attrs_by_query.items():
        n = 1
        for name in names:
            n *= max(len(index_groups[name]), 1)
        state_count += n
    print(json.dumps({"query_attrs": attrs_by_query, "bag_states": state_count, "representatives": {k: index_groups[k] for k in attr_names}}, indent=2), flush=True)

    # Work DB with a resettable base snapshot
    work = OUT / "databases" / "work.db"
    copy_plumbing(PLUMBING, work)
    conn = sqlite3.connect(str(work))
    conn.execute("DROP TABLE IF EXISTS legal_base")
    conn.execute("CREATE TABLE legal_base AS SELECT * FROM legal")
    conn.commit()
    conn.close()

    def reset_and_fill(choice: dict[tuple[str, str], str]) -> int:
        fills = fills_from_choice(choice, by_ent, doc_of)
        conn = sqlite3.connect(str(work))
        conn.execute("DELETE FROM legal")
        conn.execute("INSERT INTO legal SELECT * FROM legal_base")
        conn.commit()
        conn.close()
        overlay = apply_overlay(work, fills, mapping, table="legal")
        return int(overlay.get("changed_cells") or 0)

    def score_work(qids: list[str] | None = None) -> dict[str, Any]:
        use = qids or query_ids
        full = {row["query_id"]: row for row in queries_for("Legal")}
        score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in use]
        rewrites = {qid: {"sql": official_sql(statements[qid], work, predicates, query_id=qid), "sqlite_path": str(work)} for qid in use}
        report = score_with_rewrites(score_rows, rewrites, work, gold, "Legal")
        per = [
            {"query_id": row["query_id"], "structure_f2": row.get("structure_f2"), "cell_f1_20": row.get("cell_f1_20"), "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0)}
            for row in report.get("per_query") or []
        ]
        return {
            "f2": float(report.get("mean_structure_f2") or 0.0),
            "f1": mean_cell_f1_20(report),
            "product": mean_per_query_product(report),
            "per_query": per,
        }

    bag_cache: dict[tuple[str, tuple], dict[str, Any]] = {}
    for qid, names in attrs_by_query.items():
        reps = [index_groups[name] for name in names] or [[0]]
        if not names:
            reps = [[]]
        axes = reps if names else [()]
        iterator = itertools.product(*reps) if names else [()]
        for combo in iterator:
            choice = {}
            for name, idx in zip(names, combo):
                choice.update(prog_choice[name][idx])
            reset_and_fill(choice)
            scored = score_work([qid])
            bag_cache[(qid, tuple(combo))] = scored["per_query"][0]
    print(json.dumps({"bags_cached": len(bag_cache)}, indent=2), flush=True)

    sig_rep = {}
    for name in attr_names:
        first = {}
        sig_rep[name] = {}
        for idx, sigv in enumerate(prog_sig[name]):
            first.setdefault(sigv, idx)
            sig_rep[name][idx] = first[sigv]

    def config_score(picks: dict[str, int]) -> dict[str, Any]:
        per = []
        for qid, names in attrs_by_query.items():
            combo = tuple(sig_rep[name][picks[name]] for name in names)
            per.append(bag_cache[(qid, combo)])
        return {
            "f2": sum(float(row["structure_f2"] or 0) for row in per) / max(len(per), 1),
            "f1": sum(float(row["cell_f1_20"] or 0) for row in per) / max(len(per), 1),
            "product": sum(row["product"] for row in per) / max(len(per), 1),
            "per_query": per,
        }

    rep_axes = [index_groups[name] for name in attr_names]
    best_D = None
    best_picks = None
    n_exact = 0
    above = []
    for combo in itertools.product(*rep_axes):
        n_exact += 1
        picks = {name: idx for name, idx in zip(attr_names, combo)}
        scored = config_score(picks)
        if best_D is None or scored["product"] > best_D["product"]:
            best_D = scored
            best_picks = picks
        if scored["product"] > DOCETL:
            above.append(picks)
    # accepted writes for the winner
    win_choice = {}
    for name, idx in best_picks.items():
        win_choice.update(prog_choice[name][idx])
    accepted_D = reset_and_fill(win_choice)
    best_D = {**best_D, "accepted": accepted_D, "programs": {name: programs[name][idx]["program_id"] for name, idx in best_picks.items()}, "exact_configurations": n_exact, "collapsed_from": "5^8 representatives after identical-fill collapse", "beats_docetl": best_D["product"] > DOCETL, "n_beating_docetl": len(above)}
    print(json.dumps({"D_product": best_D["product"], "exact": n_exact, "beats": best_D["beats_docetl"]}, indent=2), flush=True)

    # Section 4: considered configs
    considered = []
    seen = set()
    for row in pre.get("considered") or []:
        cfg = row.get("config") or {}
        key = tuple(cfg.get(name) for name in attr_names)
        if key in seen or not all(key):
            continue
        seen.add(key)
        picks = {}
        for name in attr_names:
            pid = cfg[name]
            picks[name] = next(i for i, spec_prog in enumerate(programs[name]) if spec_prog["program_id"] == pid)
        gold_scored = config_score(picks)
        choice = {}
        for name, idx in picks.items():
            choice.update({k: v for k, v in prog_choice[name][idx].items() if k[0] in train_ids})
        train_hits = train_n = 0
        for eid in train_ids:
            for name in attr_names:
                train_n += 1
                sid = silver_by.get((eid, name), {}).get("mapped_id") or KEEP
                got = choice.get((eid, name), KEEP)
                if (sid or KEEP) == (got or KEEP):
                    train_hits += 1
        considered.append({
            "label": row.get("label"),
            "config": cfg,
            "train_silver_cell_agreement": train_hits / max(train_n, 1),
            "heldout_silver_product": row.get("product"),
            "heldout_lcb": row.get("lcb"),
            "gold_product": gold_scored["product"],
            "gold_f2": gold_scored["f2"],
            "gold_f1": gold_scored["f1"],
            "selected": cfg == selected,
        })
    held_scores = [row["heldout_silver_product"] for row in considered]
    gold_scores = [row["gold_product"] for row in considered]
    best_gold_idx = max(range(len(considered)), key=lambda i: gold_scores[i]) if considered else 0
    selected_rows = [row for row in considered if row["selected"]]
    selected_gold = selected_rows[0]["gold_product"] if selected_rows else None
    best_considered_gold = gold_scores[best_gold_idx] if considered else None
    calibration = {
        "n_compared": len(considered),
        "spearman_heldout_vs_gold": spearman(held_scores, gold_scores) if considered else None,
        "kendall_heldout_vs_gold": kendall(held_scores, gold_scores) if considered else None,
        "top1_gold_regret": (best_considered_gold - selected_gold) if selected_gold is not None else None,
        "top1_is_gold_best_of_compared": bool(selected_rows and selected_rows[0]["label"] == considered[best_gold_idx]["label"]),
        "selected_gold": selected_gold,
        "best_compared_gold": best_considered_gold,
        "best_family_gold": best_D["product"],
        "regret_vs_best_frozen_family": (best_D["product"] - (selected_gold or 0)),
        "heldout_silver_winner": pre.get("heldout_winner", {}).get("product"),
        "official_product": pre.get("heldout_winner") and json.loads((FROZEN / "post_freeze.json").read_text())["table"][1]["product"],
        "absolute_gap_heldout_minus_official": None,
    }
    official_product = calibration["official_product"]
    calibration["absolute_gap_heldout_minus_official"] = (calibration["heldout_silver_winner"] or 0) - (official_product or 0)
    calibration["rank_note"] = "Rank correlation is over the compared held-out configurations only. Absolute scores compare a 32-row silver database with the 570-row gold database, so 0.2801 and 0.0376 are not the same estimand."

    # Section 5 extrapolation
    extrap = {}
    for name, pid in selected.items():
        idx = next(i for i, spec_prog in enumerate(programs[name]) if spec_prog["program_id"] == pid)
        choice = prog_choice[name][idx]
        pos = [row for row in cells if row["attribute"] == name and row["split"] == "train" and row["mapped_id"]]
        neg = [row for row in cells if row["attribute"] == name and row["split"] == "train" and not row["mapped_id"]]
        writes = [(eid, cid) for (eid, attr), cid in choice.items() if attr == name]
        train_channels = Counter()
        for row in pos:
            item = next((item for item in det_items(by_ent.get((row["entity_id"], name)) or {}) if str(item.get("id")) == row["mapped_id"]), None)
            if item:
                train_channels[channel_of(item)] += 1
        write_channels = Counter()
        for eid, cid in writes:
            item = next((item for item in det_items(by_ent.get((eid, name)) or {}) if str(item.get("id")) == cid), None)
            if item:
                write_channels[channel_of(item)] += 1
        unseen = sorted(set(write_channels) - set(train_channels))
        # precision: official writes whose value matches gold
        hit = 0
        for eid, cid in writes:
            item = next((item for item in det_items(by_ent.get((eid, name)) or {}) if str(item.get("id")) == cid), None)
            if item and exact_gold(specs, name, item.get("normalized"), gold_of(eid, name)):
                hit += 1
        extrap[name] = {
            "program": pid,
            "positive_mapped_train": len(pos),
            "negative_or_keep_train": len(neg),
            "full_corpus_writes": len(writes),
            "extrapolation_ratio": len(writes) / max(len(pos), 1),
            "train_channels": dict(train_channels),
            "write_channels": dict(write_channels),
            "unseen_channels": unseen,
            "write_exact_precision": hit / max(len(writes), 1),
            "outside_train_channel_support": bool(unseen) or len(pos) == 0,
        }

    # Section 6 regressions
    official_choice = {}
    manifest_assign = json.loads((FROZEN / "assignment_manifest.json").read_text())
    # manifest is document_id -> attr -> id ? check
    sample_manifest_kind = next(iter(manifest_assign))
    doc_to_ent = {doc: eid for eid, doc in doc_of.items()}
    if sample_manifest_kind in doc_to_ent or sample_manifest_kind in {row["document_id"] for row in silver}:
        for doc, attrs in manifest_assign.items():
            eid = doc_to_ent.get(doc)
            if eid is None:
                continue
            for name, cid in attrs.items():
                official_choice[(eid, name)] = cid
    else:
        for eid, attrs in manifest_assign.items():
            for name, cid in attrs.items():
                official_choice[(eid, name)] = cid
    focus = ["legal_multiagg20:q11", "legal_multiagg20:q18"]
    reset_and_fill({})
    plumbing_focus = {row["query_id"]: row for row in score_work(focus)["per_query"]}
    reset_and_fill(official_choice)
    official_focus = {row["query_id"]: row for row in score_work(focus)["per_query"]}
    loo_attr = {}
    for name in attr_names:
        reduced = {key: cid for key, cid in official_choice.items() if key[1] != name}
        reset_and_fill(reduced)
        loo_attr[name] = {row["query_id"]: row["product"] for row in score_work(focus)["per_query"]}
    responsible = {}
    for qid in focus:
        base = plumbing_focus[qid]["product"]
        official_p = official_focus[qid]["product"]
        ranked = sorted(attr_names, key=lambda name: loo_attr[name][qid], reverse=True)
        responsible[qid] = {"plumbing": base, "official": official_p, "loo_product": {name: loo_attr[name][qid] for name in ranked}, "most_restorative": ranked[0]}
    write_traces = {}
    for qid in focus:
        name = responsible[qid]["most_restorative"]
        writes = [key for key in official_choice if key[1] == name]
        harmful = []
        for key in writes:
            reduced = {k: v for k, v in official_choice.items() if k != key}
            reset_and_fill(reduced)
            prod = {row["query_id"]: row["product"] for row in score_work([qid])["per_query"]}[qid]
            if prod > official_focus[qid]["product"] + 1e-12:
                harmful.append({"entity_id": key[0], "document_id": doc_of.get(key[0]), "attribute": name, "candidate": official_choice[key], "product_without_write": prod})
        attrs = attrs_by_query[qid]
        kind = "NULL/non-NULL change"
        if "case_number" in attrs and name == "case_number":
            kind = "filter support removed indirectly"
        if name in {"legal_basis_num", "verdict", "plaintiff_current_status", "defendant_current_status"}:
            kind = "group reassignment"
        if name in {"legal_basis_num", "case_number"} and qid.endswith("q11"):
            kind = "aggregate-value corruption" if name == "case_number" else "group reassignment"
        write_traces[qid] = {"attribute": name, "n_writes": len(writes), "n_harmful_single_writes": len(harmful), "examples": harmful[:12], "class": kind, "sql_note": statements[qid]}

    silver_correct_rate = rate(cells, lambda r: r["silver_correct"])["rate"]
    map_fail_given_candidate = 0
    map_fail_n = 0
    for row in cross_rows:
        if row["silver_correct"] and row["silver_equivalent_candidate"]:
            map_fail_n += row["count"]
            if not row["mapper_selected_it"]:
                map_fail_given_candidate += row["count"]
    map_fail_rate = map_fail_given_candidate / map_fail_n if map_fail_n else 0.0
    family_wins = best_D["product"] > DOCETL
    selected_misses_winner = family_wins and (selected_gold or 0) <= DOCETL
    extrap_ratio_max = max(row["extrapolation_ratio"] for row in extrap.values())
    if silver_correct_rate >= 0.5 and map_fail_rate >= 0.5 and mapping_rates["observationally_mappable_over_silver_correct_positive"]["rate"] >= 0.5:
        decision = "silver-to-candidate mapping is the primary bottleneck"
    elif silver_correct_rate < 0.5:
        decision = "silver reference is inaccurate"
    elif (not family_wins) and mapping_rates["correctly_mapped_over_silver_correct_positive"]["rate"] >= 0.5:
        decision = "frozen program family cannot express a winning assignment"
    elif not family_wins:
        decision = "frozen program family cannot express a winning assignment"
    elif selected_misses_winner:
        decision = "held-out selection failed despite a winning frozen program configuration"
    elif extrap_ratio_max > 10 and (selected_gold or 0) < 0.08:
        decision = "full-corpus extrapolation failed"
    else:
        decision = "mixed failure"
    loss_mass = {
        "silver_correct_rate": silver_correct_rate,
        "exact_rate_gold_positive": rate(gold_positive, lambda r: r["exact"])["rate"],
        "mapper_miss_among_silver_correct_with_candidate": map_fail_rate,
        "candidate_ceiling_sample_product": ceiling_A["product"],
        "correct_silver_mapping_ceiling_sample_product": ceiling_B["product"],
        "best_program_family_product": best_D["product"],
        "selected_config_gold_product": selected_gold,
        "official_product": official_product,
        "docetl": DOCETL,
        "gap_docetl_minus_family": DOCETL - best_D["product"],
        "gap_family_minus_selected": best_D["product"] - (selected_gold or 0),
        "gap_selected_minus_official_same_config": (selected_gold or 0) - (official_product or 0),
    }
    # gap_selected_minus_official should be ~0 if selected config score is the official score
    recommendation = {
        "silver reference is inaccurate": "Replace silver labels with a checked extractor before any program search; the current references do not match gold often enough to supervise a selector.",
        "silver-to-candidate mapping is the primary bottleneck": "Replace the exact string mapper with typed plus workload-observational equivalence before synthesizing programs.",
        "frozen program family cannot express a winning assignment": "Do not search inside these five programs per attribute. The next step is a richer deterministic ranking objective over the candidate inventory.",
        "held-out selection failed despite a winning frozen program configuration": "Reselect the winning frozen configuration with gold-free but better-calibrated validation; do not synthesize a new family first.",
        "full-corpus extrapolation failed": "Constrain each program to the feature support of its mapped training examples before full-corpus application.",
        "mixed failure": "Allocate effort in proportion to the measured gaps: reference error, mapping misses, program-family gap to 0.1235, and selection regret.",
    }[decision]

    payload = {
        "decision": decision,
        "recommendation": recommendation,
        "loss_mass": loss_mass,
        "silver_overall": {
            "n": len(cells),
            "class_counts": dict(Counter(r["class"] for r in cells)),
            "exact": rate(cells, lambda r: r["exact"]),
            "typed": rate(cells, lambda r: r["typed"]),
            "observational": rate(cells, lambda r: r["observational"]),
            "presence_agreement": rate(cells, lambda r: r["presence_agreement"]),
            "silver_correct": rate(cells, lambda r: r["silver_correct"]),
            "breakdowns": breakdowns,
        },
        "mapping": {"funnel": dict(funnel), "cross_tab": cross_rows, "rates": mapping_rates, "fail_reasons": dict(fail_reasons), "fail_examples": fail_examples},
        "ceilings": {"A_candidate_sample": ceiling_A, "B_correct_silver_mapping_sample": ceiling_B, "C_per_attribute": {k: {kk: vv for kk, vv in v.items() if kk != "per_query"} | {"per_query": v["per_query"]} for k, v in ceiling_C.items()}, "D_program_family": best_D},
        "calibration": calibration,
        "considered": considered,
        "extrapolation": extrap,
        "regressions": {"loo": responsible, "write_traces": write_traces},
        "hashes": {
            "silver_journal": file_sha256(FROZEN / "silver_journal.jsonl"),
            "programs": file_sha256(FROZEN / "programs.json"),
            "sample_split": file_sha256(FROZEN / "sample_split.json"),
            "assignment": file_sha256(FROZEN / "assignment_manifest.json"),
            "official_db": file_sha256(FROZEN / "databases" / "official.db"),
            "inventory": file_sha256(INV),
            "generation_frozen": file_sha256(FROZEN / "generation_frozen.json"),
        },
        "qwen_calls": 0,
    }
    (OUT / "audit.json").write_text(json.dumps(payload, indent=2, default=str))
    # concise report
    lines = [
        "# Legal corpus-probe causal audit",
        "",
        "Zero Qwen. Frozen corpus-probe artifacts were not modified. The 0.1886 figure is cited only as prior evidence that deterministic candidates can realize a shared assignment; that assignment was not executed.",
        "",
        f"Decision: {decision}",
        "",
        recommendation,
        "",
        "## Silver reference",
        "",
        f"Cells {len(cells)}. Silver-correct (exact, typed, or correct NULL presence) {loss_mass['silver_correct_rate']:.3f}. Exact on gold-positive {loss_mass['exact_rate_gold_positive']:.3f}.",
        "",
        "| Attribute | n | exact | silver-correct | incorrect NOT_PRESENT |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, row in breakdowns["attribute"].items():
        lines.append(f"| {name} | {row['n']} | {row['exact']:.3f} | {row['silver_correct']:.3f} | {row['incorrect_NOT_PRESENT']:.3f} |")
    lines += ["", "## Mapping cross-tab", "", "| Silver correct? | Gold-equivalent candidate? | Silver-equivalent candidate? | Mapper selected it? | Count |", "| --- | --- | --- | --- | ---: |"]
    for row in cross_rows:
        lines.append(f"| {row['silver_correct']} | {row['gold_equivalent_candidate']} | {row['silver_equivalent_candidate']} | {row['mapper_selected_it']} | {row['count']} |")
    lines += [
        "",
        f"Mapped {mapping_rates['mapped_over_768']['k']}/{mapping_rates['mapped_over_768']['n']}. Mapped silver-value {mapping_rates['mapped_over_silver_value']['k']}/{mapping_rates['mapped_over_silver_value']['n']}. Gold-equivalent candidate {mapping_rates['gold_equivalent_candidate_over_gold_positive']['k']}/{mapping_rates['gold_equivalent_candidate_over_gold_positive']['n']}. Correctly mapped {mapping_rates['correctly_mapped_over_silver_correct_positive']['k']}/{mapping_rates['correctly_mapped_over_silver_correct_positive']['n']}. Observationally mappable {mapping_rates['observationally_mappable_over_silver_correct_positive']['k']}/{mapping_rates['observationally_mappable_over_silver_correct_positive']['n']}.",
        "",
        "## Ceilings",
        "",
        "| Ceiling | Accepted | F2 | F1@0.20 | Product |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| A candidate, 96-row sample | {ceiling_A['accepted']} | {ceiling_A['f2']:.4f} | {ceiling_A['f1']:.4f} | {ceiling_A['product']:.4f} |",
        f"| B correct-silver mapping, 96-row sample | {ceiling_B['accepted']} | {ceiling_B['f2']:.4f} | {ceiling_B['f1']:.4f} | {ceiling_B['product']:.4f} |",
    ]
    for name, row in ceiling_C.items():
        lines.append(f"| C {name} `{row['program']}` | {row['accepted']} | {row['f2']:.4f} | {row['f1']:.4f} | {row['product']:.4f} |")
    lines.append(f"| D best frozen 8-program family ({n_exact} exact configs) | {best_D['accepted']} | {best_D['f2']:.4f} | {best_D['f1']:.4f} | {best_D['product']:.4f} |")
    lines.append(f"| DocETL |  |  |  | {DOCETL:.4f} |")
    lines += [
        "",
        f"Any frozen eight-program configuration beats 0.1235: {best_D['beats_docetl']}. Configurations above DocETL: {best_D['n_beating_docetl']}.",
        "",
        "## Calibration",
        "",
        f"Compared configurations: {calibration['n_compared']}. Spearman held-out silver vs gold {calibration['spearman_heldout_vs_gold']}. Kendall {calibration['kendall_heldout_vs_gold']}.",
        f"Selected gold {selected_gold}. Best compared gold {best_considered_gold}. Best family gold {best_D['product']}. Regret vs best family {calibration['regret_vs_best_frozen_family']}.",
        "Held-out silver product 0.2801 is a 32-row score against a silver-materialized database. Official 0.0376 is a 570-row score against benchmark gold. The gap is mostly a change of label and population, not only a rank error.",
        "",
        "## Extrapolation",
        "",
        "| Attribute | Mapped train + | KEEP train | Full writes | Ratio | Write exact precision | Unseen channels |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, row in extrap.items():
        lines.append(f"| {name} | {row['positive_mapped_train']} | {row['negative_or_keep_train']} | {row['full_corpus_writes']} | {row['extrapolation_ratio']:.1f} | {row['write_exact_precision']:.3f} | {', '.join(row['unseen_channels']) or '—'} |")
    lines += ["", "## Regressions", ""]
    for qid, row in responsible.items():
        lines.append(f"`{qid}` plumbing {row['plumbing']:.4f} → official {row['official']:.4f}. Most restorative leave-one-attribute-out: {row['most_restorative']}.")
        lines.append(f"Class: {write_traces[qid]['class']}. Harmful single writes: {write_traces[qid]['n_harmful_single_writes']} / {write_traces[qid]['n_writes']}.")
    lines += ["", "## Hashes", "", "```json", json.dumps(payload["hashes"], indent=2), "```", "", decision, ""]
    (OUT / "REPORT.md").write_text("\n".join(lines))
    print(json.dumps({"decision": decision, "D": best_D["product"], "silver_correct": silver_correct_rate, "official": official_product}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
