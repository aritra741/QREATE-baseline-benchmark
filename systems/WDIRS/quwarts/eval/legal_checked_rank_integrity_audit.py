"""Zero-Qwen integrity audit. Reads the frozen checked-rank arm and writes only a new audit directory."""

from __future__ import annotations

import json
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing
from quwarts.core.provenance import document_stem
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import mapping_from_rows
from quwarts.eval.legal_coverage_transfer import DOCETL_DIR, SCHEMA_PATH, gold_index, gold_value, score_db
from quwarts.eval.legal_multichannel_availability_audit import RowEvaluator, exact_gold, observational_match
from quwarts.experiments.synthesize_case80 import gold_name
from diagnostics.run_config_grid import load_ground_truth

FROZEN = ROOT / "results" / "quwarts_legal_checked_rank"
OUT = ROOT / "results" / "quwarts_legal_checked_rank_integrity_audit"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
INV = ROOT / "results" / "quwarts_legal_multichannel_candidates" / "candidate_inventory.json"
SOURCE = ROOT / "source_data" / "Legal" / "legal_case"
KEEP = "KEEP_PLUMBING"
UNCERTAIN = "UNCERTAIN"
DET = {"surface", "normalized", "workload_label"}
THETA = 12_610_011


def channel_of(item: dict[str, Any]) -> str:
    raw = str(item.get("channel") or item.get("derivation") or "surface")
    return "composed" if raw.startswith("composed") else raw


def det_items(rec: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in (rec.get("all_candidates") or rec.get("candidates") or []) if channel_of(item) in DET]


def tokens(text: str) -> set[str]:
    return {part for part in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(part) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def norm_text(value: Any, dtype: str) -> str:
    if value in (None, ""):
        return ""
    got, _, err = normalize_value(value, dtype)
    if err or got is None:
        return str(value).strip().lower()
    return str(got).strip().lower()


def feature_row(item, spec, rec_items, plumbing_null, roles, amp, desc_tokens, doc_len=1) -> list[float]:
    if item is None:
        return [
            0, 0, 0, 1, 0, 0, 0, 0, 0,
            1 if spec.dtype == "numeric" else 0, 0, 0, 0, 0,
            0, float(len(rec_items)), 1 if plumbing_null else 0,
            float(roles.get("WHERE") or 0), float(roles.get("GROUP BY") or 0),
            float(roles.get("HAVING") or 0), float(roles.get("aggregate input") or 0), 1 if amp else 0, 1,
        ]
    ch = channel_of(item)
    blob = " ".join(str(item.get(key) or "") for key in ("local_text", "raw_span", "heading", "column_header", "table_title"))
    blob_tokens = tokens(blob)
    value = str(item.get("normalized") or "")
    start = float(item.get("start") or 0) / max(doc_len, 1)
    return [
        1 if ch == "surface" else 0, 1 if ch == "normalized" else 0, 1 if ch == "workload_label" else 0, 0,
        1 if (item.get("evidence_spans") or item.get("raw_span")) else 0,
        jaccard(desc_tokens, blob_tokens),
        jaccard(desc_tokens, tokens(item.get("heading") or item.get("table_title") or "")),
        jaccard(tokens(spec.name), blob_tokens),
        1 if item.get("period") else 0,
        1 if spec.dtype == "numeric" else 0,
        float(len(value)),
        float(item.get("occurrence") or item.get("count") or 1),
        start,
        jaccard(desc_tokens, tokens(item.get("local_text") or "")),
        1 if ch == "workload_label" else 0,
        float(len(rec_items)),
        1 if plumbing_null else 0,
        float(roles.get("WHERE") or 0),
        float(roles.get("GROUP BY") or 0),
        float(roles.get("HAVING") or 0),
        float(roles.get("aggregate input") or 0),
        1 if amp else 0,
        0,
    ]


def equivalent_ids(chosen, items, spec, evaluator, queries, row) -> set[str]:
    by_id = {str(item.get("id")): item for item in items}
    out = {cid for cid in chosen if cid in by_id}
    anchors = [by_id[cid] for cid in out]
    for item in items:
        cid = str(item.get("id"))
        if cid in out:
            continue
        if any(norm_text(item.get("normalized"), spec.dtype) == norm_text(anchor.get("normalized"), spec.dtype) and norm_text(anchor.get("normalized"), spec.dtype) for anchor in anchors):
            out.add(cid)
            continue
        if anchors and queries and all(
            evaluator.run(qid, {**row, spec.name: item.get("normalized")}) == evaluator.run(qid, {**row, spec.name: anchor.get("normalized")})
            for qid in queries
            for anchor in anchors[:1]
        ):
            out.add(cid)
    return out


def terminal_of(label: dict[str, Any] | None) -> str:
    if not label:
        return "MISSING_PIPELINE_OUTPUT"
    decision = label.get("decision")
    if decision == KEEP:
        return "KEEP_PLUMBING"
    if decision == UNCERTAIN:
        return "UNCERTAIN"
    if decision:
        return "CANDIDATE"
    return "MISSING_PIPELINE_OUTPUT"


def ratio(n: int, d: int) -> dict[str, Any]:
    return {"numerator": n, "denominator": d, "rate": (n / d) if d else None}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sample = json.loads((FROZEN / "sample_split.json").read_text())
    pre = json.loads((FROZEN / "pre_gold.json").read_text())
    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    attr_names = sorted(records)
    inventory = json.loads(INV.read_text())
    by_ent = {(rec["entity_id"], rec["attribute"]): rec for rec in inventory}
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute('PRAGMA table_info("legal")')]
    plumbing_rows = [dict(zip(cols, rec)) for rec in conn.execute('SELECT * FROM "legal"')]
    conn.close()
    plumbing_by = {str(row.get("__entity_id")): row for row in plumbing_rows}
    doc_of = {eid: str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or ""))) for eid, row in plumbing_by.items()}
    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in SOURCE.glob("*.txt")}
    doc_len = {}
    for eid, row in plumbing_by.items():
        doc_len[eid] = max(len(texts.get(doc_of[eid]) or " "), 1)
    train_ids = [row["entity_id"] for row in sample["train"]]
    held_ids = [row["entity_id"] for row in sample["heldout"]]
    train_set, held_set = set(train_ids), set(held_ids)
    split_of = {eid: "train" for eid in train_set}
    split_of.update({eid: "validation" for eid in held_set})
    raw_counts = Counter()
    journal_rows = []
    for line in (FROZEN / "cell_journal.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        journal_rows.append(row)
        raw_counts[(row["entity_id"], row["attribute"])] += 1
    cells = {}
    for row in journal_rows:
        cells[(row["entity_id"], row["attribute"])] = row
    scans = {}
    scan_dupes = Counter()
    for line in (FROZEN / "scan_journal.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        scan_dupes[row["entity_id"]] += 1
        scans[row["entity_id"]] = row
    trace = json.loads((FROZEN / "assignment_trace.json").read_text())
    pred_by = {(row["entity_id"], row["attribute"]): row for row in trace}
    gold = load_ground_truth(gold_name("Legal"))
    gold_by = gold_index(gold)
    evaluator = RowEvaluator(list(plumbing_rows[0]), statements)
    desc_tokens = {name: tokens(specs[name].official_description + " " + name) for name in attr_names}
    amp = set(json.loads((FROZEN / "design.json").read_text())["amplification_attributes"])
    mapping = mapping_from_rows(plumbing_rows)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    canonical = []
    for eid in train_ids + held_ids:
        scan = scans.get(eid) or {}
        for name in attr_names:
            label = cells.get((eid, name))
            items = det_items(by_ent.get((eid, name)) or {})
            state = terminal_of(label)
            pred = pred_by.get((eid, name))
            plumbing_null = plumbing_by[eid].get(name) in (None, "")
            supported = []
            if label and state == "CANDIDATE":
                supported = list(dict.fromkeys([*(label.get("supported_candidate_ids") or []), label.get("decision")]))
            canonical.append({
                "entity_id": eid,
                "document_id": doc_of.get(eid),
                "attribute": name,
                "split": split_of[eid],
                "scan_completed": bool(scan) and not scan.get("incomplete"),
                "scan_mode": scan.get("mode"),
                "candidate_set_size": len(items),
                "matcher": (label or {}).get("match", {}).get("decision") if isinstance((label or {}).get("match"), dict) else None,
                "verifier": (label or {}).get("verify", {}).get("decision") if isinstance((label or {}).get("verify"), dict) else None,
                "adjudicator": ((label or {}).get("adjudicate") or {}).get("parsed", {}).get("decision") if isinstance((label or {}).get("adjudicate"), dict) else None,
                "terminal": state,
                "positive_candidate_ids": supported,
                "keep_eligibility": state == "KEEP_PLUMBING",
                "uncertain": state == "UNCERTAIN",
                "incumbent": (label or {}).get("reason") == "incumbent_non_null",
                "in_ranker_training": False,
                "in_ranker_validation": False,
                "ranker_prediction": None if not plumbing_null else (pred or {}).get("candidate_id", KEEP),
                "ranker_confidence": None if not pred else pred.get("score"),
                "ranker_margin": None if not pred else pred.get("margin"),
                "full_corpus_eligible": plumbing_null,
                "reason": (label or {}).get("reason"),
            })
    by_canon = {(row["entity_id"], row["attribute"]): row for row in canonical}

    def item_value(eid, name, cid):
        if cid in {KEEP, UNCERTAIN, None, ""}:
            return None
        item = next((item for item in det_items(by_ent.get((eid, name)) or {}) if str(item.get("id")) == cid), None)
        return None if item is None else item.get("normalized")

    def agrees(eid, name, pred, gold_v):
        exact = exact_gold(specs, name, pred, gold_v)
        obs = exact or observational_match(evaluator, records[name].queries or query_ids[:1], plumbing_by[eid], name, pred, gold_v)
        return exact, obs

    # Training matrix, matching the frozen group_rows rules.
    matrix = []
    dropped_candidate_groups = []
    positive_missing = []
    equivalent_marked_negative = []
    for eid in train_ids + held_ids:
        for name in attr_names:
            label = cells.get((eid, name))
            rowc = by_canon[(eid, name)]
            if not label or label.get("reason") == "incumbent_non_null" or label.get("decision") == UNCERTAIN:
                continue
            items = det_items(by_ent.get((eid, name)) or {})
            raw_supported = set(label.get("supported_candidate_ids") or [])
            if label.get("decision") not in {KEEP, UNCERTAIN} and label.get("decision"):
                raw_supported.add(label["decision"])
            supported = equivalent_ids(list(raw_supported), items, specs[name], evaluator, records[name].queries, plumbing_by[eid])
            unknown = [cid for cid in raw_supported if cid not in {str(item.get("id")) for item in items}]
            if unknown:
                positive_missing.append({"entity_id": eid, "attribute": name, "ids": unknown})
            options = [(None, 1 if label.get("decision") == KEEP else 0)]
            for item in items:
                flag = 1 if str(item.get("id")) in supported else 0
                options.append((item, flag))
                if str(item.get("id")) in supported and flag == 0:
                    equivalent_marked_negative.append((eid, name, str(item.get("id"))))
            if sum(flag for _item, flag in options) == 0 and label.get("decision") != KEEP:
                dropped_candidate_groups.append({"entity_id": eid, "attribute": name, "decision": label.get("decision")})
                continue
            if split_of[eid] == "train":
                rowc["in_ranker_training"] = True
            else:
                rowc["in_ranker_validation"] = True
            rowc["positive_candidate_ids"] = sorted(supported)
            for item, flag in options:
                matrix.append({
                    "entity_id": eid,
                    "attribute": name,
                    "split": split_of[eid],
                    "candidate_id": KEEP if item is None else str(item.get("id")),
                    "y": flag,
                    "x": feature_row(item, specs[name], items, True, records[name].roles, name in amp, desc_tokens[name], doc_len.get(eid, 1)),
                    "channel": "keep" if item is None else channel_of(item),
                })

    def subset(rows, split=None, attr=None, y=None):
        out = rows
        if split:
            out = [row for row in out if row["split"] == split]
        if attr:
            out = [row for row in out if row["attribute"] == attr]
        if y is not None:
            out = [row for row in out if row["y"] == y]
        return out

    train_rows = subset(matrix, "train")
    groups = {(row["entity_id"], row["attribute"]) for row in matrix}
    cross = [row["entity_id"] for row in matrix if row["entity_id"] in train_set and row["entity_id"] in held_set]
    feature_std = np.std(np.array([row["x"] for row in train_rows], dtype=float), axis=0) if train_rows else np.zeros(23)
    collisions = []
    by_group = defaultdict(list)
    for row in matrix:
        by_group[(row["entity_id"], row["attribute"])].append(row)
    for key, rows in by_group.items():
        seen = {}
        for row in rows:
            sig = tuple(np.round(row["x"], 8))
            prev = seen.get(sig)
            if prev is not None and prev["y"] != row["y"]:
                collisions.append({"cell": key, "a": prev["candidate_id"], "b": row["candidate_id"]})
            seen.setdefault(sig, row)

    def fit_predict(rows, extra=None):
        xs = [list(row["x"]) + ([] if extra is None else [extra(row)]) for row in rows]
        ys = [row["y"] for row in rows]
        model = GradientBoostingClassifier(n_estimators=50, max_depth=2, learning_rate=0.1, random_state=120)
        if len(set(ys)) < 2:
            return {i: 0.0 for i in range(len(rows))}, model
        model.fit(np.array(xs, dtype=float), np.array(ys, dtype=int))
        classes = list(model.classes_)
        proba = model.predict_proba(np.array(xs, dtype=float))
        pos = proba[:, classes.index(1)] if 1 in classes else np.zeros(len(rows))
        return {i: float(pos[i]) for i in range(len(rows))}, model

    def cell_metrics(rows, scores):
        grouped = defaultdict(list)
        for i, row in enumerate(rows):
            grouped[(row["entity_id"], row["attribute"])].append((i, row))
        top1 = keep_hit = keep_n = pos_hit = pos_n = 0
        per_attr = defaultdict(lambda: [0, 0])
        n_cells = 0
        for key, group in grouped.items():
            n_cells += 1
            order = sorted(group, key=lambda pair: (-scores[pair[0]], pair[1]["candidate_id"]))
            best = order[0][1]
            positives = [row for _i, row in group if row["y"] == 1]
            top_ok = best["y"] == 1
            top1 += int(top_ok)
            per_attr[key[1]][0] += int(top_ok)
            per_attr[key[1]][1] += 1
            if positives and all(row["candidate_id"] == KEEP for row in positives):
                keep_n += 1
                keep_hit += int(best["candidate_id"] == KEEP)
            for _i, row in group:
                if row["y"] == 1:
                    pos_n += 1
                    pos_hit += int(scores[_i] >= max(scores[j] for j, _r in group) - 1e-12 and row["candidate_id"] == best["candidate_id"] or scores[_i] > 0 and False)
            # set recall: fraction of positive rows whose score is strictly above every negative, or tied-best if all positives are best
            neg_scores = [scores[i] for i, row in group if row["y"] == 0]
            ceil = max(neg_scores) if neg_scores else -1
            for i, row in group:
                if row["y"] == 1 and scores[i] > ceil:
                    pass
        set_hit = set_n = 0
        for key, group in grouped.items():
            neg_scores = [scores[i] for i, row in group if row["y"] == 0]
            ceil = max(neg_scores) if neg_scores else -1.0
            for i, row in group:
                if row["y"] == 1:
                    set_n += 1
                    set_hit += int(scores[i] > ceil)
        return {
            "cells": n_cells,
            "top1": ratio(top1, n_cells),
            "set_recall": ratio(set_hit, set_n),
            "keep_accuracy": ratio(keep_hit, keep_n),
            "per_attribute": {name: ratio(hit, n) for name, (hit, n) in sorted(per_attr.items())},
        }

    train_scores, _model = fit_predict(train_rows)
    memo = cell_metrics(train_rows, train_scores)
    cell_ids = {}
    for i, row in enumerate(train_rows):
        cell_ids.setdefault((row["entity_id"], row["attribute"]), len(cell_ids))
    cell_scores, _m = fit_predict(train_rows, extra=lambda row: float(cell_ids[(row["entity_id"], row["attribute"])]))
    memo_cell = cell_metrics(train_rows, cell_scores)
    row_ids = {i: float(i) for i in range(len(train_rows))}
    row_scores, _m = fit_predict(train_rows, extra=lambda row, _ids=row_ids: row_ids[train_rows.index(row)] if False else 0.0)
    # stable row index feature
    index_of = {id(row): i for i, row in enumerate(train_rows)}
    row_scores, _m = fit_predict(train_rows, extra=lambda row: float(index_of[id(row)]))
    memo_row = cell_metrics(train_rows, row_scores)

    # Hand fixture: separable one-hot slot.
    fixture_rows = []
    for cell, positive in (("A", {KEEP, "c1"}), ("B", {"c4", "c5"})):
        for cid in (KEEP, "c1", "c2", "c3") if cell == "A" else (KEEP, "c4", "c5", "c6"):
            vec = [0.0] * 4
            slot = {KEEP: 0, "c1": 1, "c2": 2, "c3": 3, "c4": 1, "c5": 1, "c6": 2}[cid]
            # c4 and c5 share the equivalence feature so both can be positive together; c5 gets a second bit too
            if cid == "c5":
                vec = [0, 1, 0, 1]
            else:
                vec[slot] = 1
            fixture_rows.append({"entity_id": cell, "attribute": "attr", "candidate_id": cid, "y": int(cid in positive), "x": vec, "split": "train", "channel": "keep" if cid == KEEP else "surface"})
    fx_scores, fx_model = fit_predict(fixture_rows)
    fx_metrics = cell_metrics(fixture_rows, fx_scores)
    fx_choice = {}
    for cell in ("A", "B"):
        group = [(i, row) for i, row in enumerate(fixture_rows) if row["entity_id"] == cell]
        order = sorted(group, key=lambda pair: (-fx_scores[pair[0]], pair[1]["candidate_id"]))
        best, second = order[0], order[1]
        gap = fx_scores[best[0]] - fx_scores[second[0]]
        chosen = best[1]["candidate_id"] if fx_scores[best[0]] >= 0.55 and gap >= 0.02 else KEEP
        fx_choice[cell] = chosen
    fixture_pass = fx_choice["A"] == "c1" and fx_choice["B"] in {"c4", "c5"} and fx_metrics["top1"]["numerator"] == fx_metrics["top1"]["denominator"]

    # Baselines on ranker-validation cells (non-incumbent, non-UNCERTAIN, held out, not dropped).
    val_cells = [row for row in canonical if row["in_ranker_validation"]]
    def supported_set(row):
        return set(row["positive_candidate_ids"])

    def score_policy(choice_fn):
        top = keep_ok = n = writes = prec_n = 0
        for row in val_cells:
            pred = choice_fn(row)
            positives = supported_set(row)
            keep_label = row["terminal"] == "KEEP_PLUMBING"
            n += 1
            if keep_label and pred == KEEP:
                top += 1
                keep_ok += 1
            elif pred in positives:
                top += 1
            if pred != KEEP:
                writes += 1
                prec_n += int(pred in positives)
        return {"top1": ratio(top, n), "writes": writes, "precision": ratio(prec_n, writes)}

    rng = random.Random(120)

    def priority(row):
        items = det_items(by_ent.get((row["entity_id"], row["attribute"])) or {})
        order = {"surface": 0, "normalized": 1, "workload_label": 2}
        items = sorted(items, key=lambda item: (order.get(channel_of(item), 9), str(item.get("id"))))
        return str(items[0].get("id")) if items else KEEP

    def random_choice(row):
        items = det_items(by_ent.get((row["entity_id"], row["attribute"])) or {})
        options = [KEEP] + [str(item.get("id")) for item in items]
        return rng.choice(options)

    def checked_choice(row):
        if row["terminal"] == "KEEP_PLUMBING":
            return KEEP
        return row["positive_candidate_ids"][0] if row["positive_candidate_ids"] else KEEP

    # Train-only model with the frozen threshold, scored on validation cells.
    val_matrix = [row for row in matrix if row["split"] == "validation"]
    # scores for val rows from a model fit on train
    xs_train = np.array([row["x"] for row in train_rows], dtype=float)
    ys_train = np.array([row["y"] for row in train_rows], dtype=int)
    selector = GradientBoostingClassifier(n_estimators=50, max_depth=2, learning_rate=0.1, random_state=120)
    selector.fit(xs_train, ys_train)

    def predict_cell(model, eid, name):
        items = det_items(by_ent.get((eid, name)) or {})
        rows = [feature_row(None, specs[name], items, True, records[name].roles, name in amp, desc_tokens[name], doc_len.get(eid, 1))]
        ids = [KEEP]
        for item in items:
            rows.append(feature_row(item, specs[name], items, True, records[name].roles, name in amp, desc_tokens[name], doc_len.get(eid, 1)))
            ids.append(str(item.get("id")))
        proba = model.predict_proba(np.array(rows, dtype=float))
        classes = list(model.classes_)
        scores = proba[:, classes.index(1)] if 1 in classes else np.zeros(len(rows))
        order = sorted(range(len(ids)), key=lambda i: (-float(scores[i]), ids[i]))
        best, second = order[0], order[1] if len(order) > 1 else order[0]
        gap = float(scores[best] - scores[second])
        need = 0.75 if name in amp else 0.55
        if name in amp and ids[best] != KEEP:
            item = next((item for item in items if str(item.get("id")) == ids[best]), None)
            if item is None or channel_of(item) == "workload_label" or not (item.get("evidence_spans") or item.get("raw_span")):
                return KEEP, float(scores[best])
        if float(scores[best]) >= need and gap >= 0.02:
            return ids[best], float(scores[best])
        return KEEP, float(scores[best])

    learned_choice = { (row["entity_id"], row["attribute"]): predict_cell(selector, row["entity_id"], row["attribute"])[0] for row in val_cells }
    baselines = {
        "always_KEEP": score_policy(lambda row: KEEP),
        "always_abstain": score_policy(lambda row: KEEP),
        "highest_priority_channel": score_policy(priority),
        "checked_label": score_policy(checked_choice),
        "random_seed_120": score_policy(random_choice),
        "selected_ranker_train_only": score_policy(lambda row: learned_choice[(row["entity_id"], row["attribute"])]),
        "final_trace_ranker": score_policy(lambda row: row["ranker_prediction"] or KEEP),
    }

    # Gold metrics on declared universes.
    def gold_block(rows):
        exact_n = obs_n = cand_n = cand_obs = decided_n = decided_obs = gold_pos = covered = false_abs = 0
        for row in rows:
            eid, name = row["entity_id"], row["attribute"]
            gold_v = gold_value(gold_by, row["document_id"], name)
            present = gold_v not in (None, "")
            if present:
                gold_pos += 1
                cands = det_items(by_ent.get((eid, name)) or {})
                if any(agrees(eid, name, item.get("normalized"), gold_v)[1] for item in cands):
                    covered += 1
                if row["terminal"] == "KEEP_PLUMBING":
                    false_abs += 1
            exact = obs = False
            if row["terminal"] == "KEEP_PLUMBING" and not present:
                exact = obs = True
            elif row["terminal"] == "UNCERTAIN":
                exact = obs = False
            elif row["terminal"] == "CANDIDATE":
                for cid in row["positive_candidate_ids"]:
                    ex, ob = agrees(eid, name, item_value(eid, name, cid), gold_v)
                    exact = exact or ex
                    obs = obs or ob
            exact_n += int(exact)
            obs_n += int(obs)
            if row["terminal"] != "UNCERTAIN":
                decided_n += 1
                decided_obs += int(obs)
            if row["terminal"] == "CANDIDATE":
                cand_n += 1
                cand_obs += int(obs)
        n = len(rows)
        cand_rows = [row for row in rows if row["candidate_set_size"] > 0]
        return {
            "n": n,
            "exact": ratio(exact_n, n),
            "observational_including_uncertain": ratio(obs_n, n),
            "committed_candidate": ratio(cand_obs, cand_n),
            "decided": ratio(decided_obs, decided_n),
            "candidate_rate": ratio(sum(row["terminal"] == "CANDIDATE" for row in rows), n),
            "keep_rate": ratio(sum(row["terminal"] == "KEEP_PLUMBING" for row in rows), n),
            "uncertain_rate": ratio(sum(row["terminal"] == "UNCERTAIN" for row in rows), n),
            "candidate_coverage": ratio(covered, gold_pos),
            "false_absence": ratio(false_abs, gold_pos),
            "gold_positive": gold_pos,
            "with_candidates": len(cand_rows),
        }

    universes = {
        "all_960": canonical,
        "complete_scans": [row for row in canonical if row["scan_completed"]],
        "with_candidate_sets": [row for row in canonical if row["candidate_set_size"] > 0],
        "committed_candidates": [row for row in canonical if row["terminal"] == "CANDIDATE"],
        "decided": [row for row in canonical if row["terminal"] in {"CANDIDATE", "KEEP_PLUMBING"}],
        "non_uncertain": [row for row in canonical if row["terminal"] != "UNCERTAIN"],
        "ranker_training": [row for row in canonical if row["in_ranker_training"]],
        "ranker_validation": val_cells,
        "gold_positive_non_incumbent": [],
    }
    # gold-positive among canonical, filled after gold lookup
    universes["gold_positive"] = []
    for row in canonical:
        gold_v = gold_value(gold_by, row["document_id"], row["attribute"])
        row["gold_present"] = gold_v not in (None, "")
        if row["gold_present"]:
            universes["gold_positive"].append(row)
    published_universe = [row for row in canonical if not row["incumbent"]]
    universe_metrics = {name: gold_block(rows) for name, rows in {**universes, "published_non_incumbent": published_universe}.items()}

    def agreement(rows):
        hit = 0
        for row in rows:
            pred = row["ranker_prediction"] or KEEP
            if row["terminal"] == "KEEP_PLUMBING" and pred == KEEP:
                hit += 1
            elif pred in set(row["positive_candidate_ids"]):
                hit += 1
        return ratio(hit, len(rows))

    agreements = {
        "training_cells": agreement([row for row in canonical if row["in_ranker_training"]]),
        "validation_cells": agreement(val_cells),
        "published_non_incumbent_trace": agreement(published_universe),
    }

    # Direct writes.
    def fills_from(rows):
        fills = defaultdict(dict)
        for row in rows:
            if row["terminal"] != "CANDIDATE":
                continue
            value = item_value(row["entity_id"], row["attribute"], row["positive_candidate_ids"][0])
            if value in (None, "", -1, "-1"):
                continue
            fills[row["document_id"]][row["attribute"]] = value
        return fills

    agreed_rows = []
    for row in canonical:
        if row["terminal"] != "CANDIDATE":
            continue
        label = cells[(row["entity_id"], row["attribute"])]
        if label.get("adjudicate"):
            continue
        verifier = (label.get("verify") or {}).get("decision")
        if verifier == label.get("decision") or verifier in (label.get("supported_candidate_ids") or []):
            agreed_rows.append(row)
    sample_ranker_writes = [row for row in canonical if row["full_corpus_eligible"] and row["ranker_prediction"] not in {KEEP, None}]
    full_writes = [row for row in trace if row.get("candidate_id") not in {KEEP, None}]

    def materialize(name, fills):
        dest = OUT / "databases" / f"{name}.db"
        copy_plumbing(PLUMBING, dest)
        overlay = apply_overlay(dest, fills, mapping, table="legal")
        scored = score_db(dest, statements, predicates, query_ids, gold)
        return {"writes": overlay.get("changed_cells"), "product": scored["mean_per_query_product"], "f2": scored["mean_structure_f2"], "f1": scored["mean_cell_f1_at_0.20"], "per_query": scored["per_query"]}

    db_committed = materialize("committed_92", fills_from([row for row in canonical if row["terminal"] == "CANDIDATE"]))
    db_agreed = materialize("verifier_agreed", fills_from(agreed_rows))
    sample_fills = defaultdict(dict)
    for row in sample_ranker_writes:
        value = item_value(row["entity_id"], row["attribute"], row["ranker_prediction"])
        if value not in (None, "", -1, "-1"):
            sample_fills[row["document_id"]][row["attribute"]] = value
    db_sample = materialize("ranker_sample", sample_fills)
    db_full = score_db(FROZEN / "databases" / "official.db", statements, predicates, query_ids, gold)
    db_plumbing = score_db(PLUMBING, statements, predicates, query_ids, gold)

    # Extrapolation.
    pos_by_attr = defaultdict(list)
    for row in matrix:
        if row["y"] == 1 and row["candidate_id"] != KEEP:
            pos_by_attr[row["attribute"]].append(np.array(row["x"], dtype=float))
    pos_attrs = {name for name, rows in pos_by_attr.items() if rows}
    extrap = []
    for write in full_writes:
        name = write["attribute"]
        vec = np.array(write.get("features") or [], dtype=float)
        bank = pos_by_attr.get(name) or []
        if len(vec) and bank:
            dist = min(float(np.linalg.norm(vec - other)) for other in bank)
        else:
            dist = None
        channel = "keep"
        if len(vec) >= 4:
            if vec[0] == 1:
                channel = "surface"
            elif vec[1] == 1:
                channel = "normalized"
            elif vec[2] == 1:
                channel = "workload_label"
        train_channels = {row["channel"] for row in matrix if row["attribute"] == name and row["y"] == 1 and row["split"] == "train"}
        extrap.append({
            "entity_id": write["entity_id"],
            "attribute": name,
            "candidate_id": write["candidate_id"],
            "score": write.get("score"),
            "distance": dist,
            "positive_training_examples": len(bank),
            "unseen_channel": channel not in train_channels and channel != "keep",
            "in_sample": write["entity_id"] in train_set or write["entity_id"] in held_set,
        })
    zero_pos_writes = [row for row in extrap if row["positive_training_examples"] == 0]
    forced_fills = defaultdict(dict)
    for write in full_writes:
        if write["attribute"] in {row["attribute"] for row in zero_pos_writes}:
            continue
        value = item_value(write["entity_id"], write["attribute"], write["candidate_id"])
        if value not in (None, "", -1, "-1"):
            doc = doc_of.get(write["entity_id"]) or write.get("document_id")
            forced_fills[doc][write["attribute"]] = value
    db_forced = materialize("zero_positive_forced_keep", forced_fills)

    # Budget.
    spent = int(pre["causal_spent"])
    remaining = THETA - spent
    per_entity = spent / 120
    additional = int(remaining // per_entity)
    scan_tokens = pre["tokens_by_purpose"]["scan"] + pre["tokens_by_purpose"]["scan_chunk"] + pre["tokens_by_purpose"]["scan_reduce"]
    verify_tokens = pre["tokens_by_purpose"]["verify_match"] + pre["tokens_by_purpose"]["verify_check"] + pre["tokens_by_purpose"]["verify_absence"]
    caps = json.loads((FROZEN / "design.json").read_text())["allocation"]

    label_by_attr = defaultdict(Counter)
    for row in canonical:
        label_by_attr[row["attribute"]][row["terminal"]] += 1
        label_by_attr[row["attribute"]][row["split"]] += 1
    train_pos_cells = Counter(row["attribute"] for row in matrix if row["split"] == "train" and row["y"] == 1 and row["candidate_id"] != KEEP)
    train_keep_cells = Counter()
    for key, rows in by_group.items():
        if rows[0]["split"] == "train" and any(row["candidate_id"] == KEEP and row["y"] == 1 for row in rows):
            train_keep_cells[key[1]] += 1

    # Confidence of writes equals selected candidate: features of a write should not be the KEEP vector.
    write_feature_mismatch = 0
    for write in full_writes:
        vec = write.get("features") or []
        if len(vec) >= 4 and vec[3] == 1 and vec[-1] == 1:
            write_feature_mismatch += 1

    summary = {
        "canonical_n": len(canonical),
        "journal_rows": len(journal_rows),
        "duplicate_cells": sum(1 for n in raw_counts.values() if n > 1),
        "missing_cells": sum(row["terminal"] == "MISSING_PIPELINE_OUTPUT" for row in canonical),
        "terminal": dict(Counter(row["terminal"] for row in canonical)),
        "incumbent_keep": sum(row["incumbent"] for row in canonical),
        "extracted_keep": sum(row["terminal"] == "KEEP_PLUMBING" and not row["incumbent"] for row in canonical),
        "scan_entities": len([eid for eid in train_set | held_set if scans.get(eid)]),
        "extra_scan_entities": sorted(set(scans) - (train_set | held_set)),
        "incomplete_scans": sum(1 for eid in train_set | held_set if scans.get(eid, {}).get("incomplete")),
        "matrix_rows": len(matrix),
        "matrix_train": len(train_rows),
        "matrix_val": len(val_matrix),
        "positive_labels": sum(row["y"] for row in matrix),
        "negative_labels": sum(row["y"] == 0 for row in matrix),
        "train_groups": len({(row["entity_id"], row["attribute"]) for row in train_rows}),
        "val_groups": len({(row["entity_id"], row["attribute"]) for row in val_matrix}),
        "dropped_candidate_groups": dropped_candidate_groups,
        "positive_ids_missing_from_list": positive_missing,
        "equivalent_marked_negative": equivalent_marked_negative,
        "cross_split_entities": cross,
        "feature_std_min": float(feature_std.min()) if len(feature_std) else None,
        "constant_features": int(np.sum(feature_std < 1e-12)),
        "feature_collisions": collisions,
        "memorization": memo,
        "memorization_cell_id": memo_cell,
        "memorization_row_id": memo_row,
        "fixture_pass": fixture_pass,
        "fixture_choice": fx_choice,
        "fixture_metrics": fx_metrics,
        "baselines": baselines,
        "agreements": agreements,
        "universes": universe_metrics,
        "databases": {
            "plumbing": {"product": db_plumbing["mean_per_query_product"], "f2": db_plumbing["mean_structure_f2"], "f1": db_plumbing["mean_cell_f1_at_0.20"], "per_query": db_plumbing["per_query"]},
            "committed": db_committed,
            "verifier_agreed": {**db_agreed, "cells": len(agreed_rows)},
            "ranker_sample": db_sample,
            "ranker_full": {"writes": pre["writes"], "product": db_full["mean_per_query_product"], "f2": db_full["mean_structure_f2"], "f1": db_full["mean_cell_f1_at_0.20"], "per_query": db_full["per_query"]},
            "zero_positive_forced_keep": db_forced,
        },
        "extrapolation": {
            "writes": len(extrap),
            "zero_positive_attributes": sorted({row["attribute"] for row in zero_pos_writes}),
            "zero_positive_writes": len(zero_pos_writes),
            "unseen_channel_writes": sum(row["unseen_channel"] for row in extrap),
            "median_distance": float(np.median([row["distance"] for row in extrap if row["distance"] is not None])) if any(row["distance"] is not None for row in extrap) else None,
        },
        "budget": {
            "spent": spent,
            "remaining": remaining,
            "per_entity": per_entity,
            "additional_packages_affordable": additional,
            "entities_left": 570 - 120,
            "scan_tokens": scan_tokens,
            "scan_cap": caps["scan"],
            "verify_tokens": verify_tokens,
            "verify_cap": caps["verify"],
            "adjudicate_tokens": pre["tokens_by_purpose"]["adjudicate"],
            "adjudicate_cap": caps["adjudicate"],
        },
        "train_positive_cells_by_attr": dict(train_pos_cells),
        "label_by_attr": {name: dict(counts) for name, counts in label_by_attr.items()},
        "write_keep_feature_mismatch": write_feature_mismatch,
        "class_weight": "uniform; GradientBoostingClassifier was fit without class weights",
        "group_loss": "pointwise binary labels; GroupKFold was diagnostic only and did not define the fitted model",
    }
    (OUT / "audit.json").write_text(json.dumps(summary, indent=2, default=str))
    (OUT / "canonical_cells.jsonl").write_text("".join(json.dumps(row) + "\n" for row in canonical))
    (OUT / "extrapolation.json").write_text(json.dumps(extrap, indent=2))
    print(json.dumps({
        "canonical": summary["canonical_n"],
        "terminal": summary["terminal"],
        "incumbent_keep": summary["incumbent_keep"],
        "extracted_keep": summary["extracted_keep"],
        "matrix": [summary["matrix_rows"], summary["positive_labels"], summary["negative_labels"]],
        "memo_top1": memo["top1"],
        "memo_cell": memo_cell["top1"],
        "memo_row": memo_row["top1"],
        "collisions": len(collisions),
        "fixture": fixture_pass,
        "baselines": {k: v["top1"] for k, v in baselines.items()},
        "db": {k: summary["databases"][k]["product"] for k in summary["databases"]},
        "zero_pos": summary["extrapolation"],
        "budget_extra": additional,
    }, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
