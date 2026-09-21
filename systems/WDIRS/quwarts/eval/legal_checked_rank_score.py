"""Post-freeze gold scoring for the Legal checked-extraction ranker."""

from __future__ import annotations

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

from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.provenance import document_stem
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.legal_coverage_transfer import (
    DOCETL_DIR,
    DOCETL_F1,
    DOCETL_F2,
    DOCETL_PRODUCT,
    DOCETL_TOKENS,
    SCHEMA_PATH,
    gold_index,
    gold_value,
    score_db,
)
from quwarts.eval.legal_multichannel_availability_audit import RowEvaluator, exact_gold, observational_match
from quwarts.experiments.synthesize_case80 import gold_name
from diagnostics.run_config_grid import load_ground_truth

OUT = ROOT / "results" / "quwarts_legal_checked_rank"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
INV = ROOT / "results" / "quwarts_legal_multichannel_candidates" / "candidate_inventory.json"
KEEP = "KEEP_PLUMBING"
UNCERTAIN = "UNCERTAIN"
DET = {"surface", "normalized", "workload_label"}


def channel_of(item: dict[str, Any]) -> str:
    raw = str(item.get("channel") or item.get("derivation") or "surface")
    return "composed" if raw.startswith("composed") else raw


def det_items(rec: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in (rec.get("all_candidates") or rec.get("candidates") or []) if channel_of(item) in DET]


def band(score: float) -> str:
    if score >= 0.85:
        return "0.85+"
    if score >= 0.75:
        return "0.75-0.85"
    if score >= 0.65:
        return "0.65-0.75"
    if score >= 0.55:
        return "0.55-0.65"
    return "<0.55"


def main() -> int:
    freeze = json.loads((OUT / "generation_frozen.json").read_text())
    if not freeze or freeze.get("gold_loaded") or not freeze.get("rebuild_match") or not freeze.get("forbidden_inaccessible"):
        raise SystemExit("run invalid")
    pre = json.loads((OUT / "pre_gold.json").read_text())
    sample = json.loads((OUT / "sample_split.json").read_text())
    gold = load_ground_truth(gold_name("Legal"))
    gold_by = gold_index(gold)
    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    inventory = json.loads(INV.read_text())
    by_ent = {(rec["entity_id"], rec["attribute"]): rec for rec in inventory}
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute('PRAGMA table_info("legal")')]
    plumbing_rows = [dict(zip(cols, rec)) for rec in conn.execute('SELECT * FROM "legal"')]
    conn.close()
    plumbing_by = {str(row.get("__entity_id")): row for row in plumbing_rows}
    doc_of = {eid: str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or ""))) for eid, row in plumbing_by.items()}
    evaluator = RowEvaluator(list(plumbing_rows[0]), statements)
    train_ids = {row["entity_id"] for row in sample["train"]}
    held_ids = {row["entity_id"] for row in sample["heldout"]}
    cells = {}
    for line in (OUT / "cell_journal.jsonl").read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            cells[(row["entity_id"], row["attribute"])] = row
    trace = json.loads((OUT / "assignment_trace.json").read_text())
    pred_by = {(row["entity_id"], row["attribute"]): row for row in trace}

    def item_value(eid: str, name: str, cid: str):
        if cid in {KEEP, UNCERTAIN, None, ""}:
            return None
        item = next((item for item in det_items(by_ent.get((eid, name)) or {}) if str(item.get("id")) == cid), None)
        return None if item is None else item.get("normalized")

    def agrees(eid: str, name: str, pred, gold_v) -> tuple[bool, bool]:
        row = plumbing_by[eid]
        exact = exact_gold(specs, name, pred, gold_v)
        obs = exact or observational_match(evaluator, records[name].queries or query_ids[:1], row, name, pred, gold_v)
        return exact, obs

    checked_n = exact_n = obs_n = false_abs = gold_pos = covered = 0
    by_attr = defaultdict(lambda: Counter())
    split_acc = {"train": Counter(), "heldout": Counter()}
    for (eid, name), label in cells.items():
        if label.get("reason") == "incumbent_non_null":
            continue
        doc = doc_of.get(eid) or label.get("document_id")
        gold_v = gold_value(gold_by, doc, name)
        gold_present = gold_v not in (None, "")
        supported = list(label.get("supported_candidate_ids") or [])
        if label.get("decision") not in {KEEP, UNCERTAIN}:
            supported.append(label["decision"])
        values = [item_value(eid, name, cid) for cid in supported]
        exact = obs = False
        if label.get("decision") == KEEP and not gold_present:
            exact = obs = True
        elif label.get("decision") == UNCERTAIN:
            exact = obs = False
        else:
            for value in values:
                ex, ob = agrees(eid, name, value, gold_v)
                exact = exact or ex
                obs = obs or ob
        checked_n += 1
        exact_n += int(exact)
        obs_n += int(obs)
        if gold_present:
            gold_pos += 1
            cands = det_items(by_ent.get((eid, name)) or {})
            if any(agrees(eid, name, item.get("normalized"), gold_v)[1] for item in cands):
                covered += 1
            if label.get("decision") == KEEP:
                false_abs += 1
        split = "train" if eid in train_ids else "heldout"
        pred = pred_by.get((eid, name), {}).get("candidate_id", KEEP)
        pred_v = item_value(eid, name, pred)
        p_exact, p_obs = agrees(eid, name, pred_v, gold_v) if pred != KEEP or not gold_present else (not gold_present, not gold_present)
        if pred == KEEP and not gold_present:
            p_exact = p_obs = True
        split_acc[split]["n"] += 1
        split_acc[split]["exact"] += int(p_exact)
        split_acc[split]["obs"] += int(p_obs)
        ref_ok = label.get("decision") == KEEP and pred == KEEP or pred in set(supported)
        split_acc[split]["vs_checked"] += int(bool(ref_ok))
        by_attr[name]["n"] += 1
        by_attr[name]["checked_obs"] += int(obs)
        by_attr[name]["ranker_obs"] += int(p_obs)
        by_attr[name]["writes"] += int(pred not in {KEEP, None})

    bands = defaultdict(lambda: Counter())
    for row in trace:
        if row.get("candidate_id") in {KEEP, None}:
            continue
        key = band(float(row.get("score") or 0))
        eid, name = row["entity_id"], row["attribute"]
        gold_v = gold_value(gold_by, doc_of.get(eid, row.get("document_id")), name)
        pred_v = item_value(eid, name, row["candidate_id"])
        _ex, ob = agrees(eid, name, pred_v, gold_v)
        bands[key]["writes"] += 1
        bands[key]["obs"] += int(ob)

    plumbing = score_db(PLUMBING, statements, predicates, query_ids, gold)
    official = score_db(OUT / "databases" / "official.db", statements, predicates, query_ids, gold)
    product = official["mean_per_query_product"]
    checked_obs_rate = obs_n / max(checked_n, 1)
    coverage_rate = covered / max(gold_pos, 1)
    false_abs_rate = false_abs / max(gold_pos, 1)
    val_vs_checked = split_acc["heldout"]["vs_checked"] / max(split_acc["heldout"]["n"], 1)
    if product > DOCETL_PRODUCT:
        decision = "candidate-aligned checked extraction beats DocETL"
    elif checked_obs_rate >= 0.55 and (val_vs_checked < 0.55 or product <= DOCETL_PRODUCT):
        decision = "checked references are accurate but deterministic ranking fails"
    elif coverage_rate < 0.40:
        decision = "deterministic candidates lack source-supported coverage"
    elif checked_obs_rate < 0.55:
        decision = "checked extraction remains too inaccurate for supervision"
    else:
        decision = "run invalid"
    sample_writes = sum(1 for row in trace if row.get("candidate_id") not in {KEEP, None} and row["entity_id"] in (train_ids | held_ids))
    full_writes = pre.get("writes")
    table = [
        {"arm": "plumbing", "tokens": 0, "accepted": 0, "f2": plumbing["mean_structure_f2"], "f1": plumbing["mean_cell_f1_at_0.20"], "product": plumbing["mean_per_query_product"]},
        {"arm": "checked ranker", "tokens": pre.get("causal_spent"), "accepted": pre.get("accepted"), "f2": official["mean_structure_f2"], "f1": official["mean_cell_f1_at_0.20"], "product": product},
        {"arm": "DocETL", "tokens": DOCETL_TOKENS, "accepted": "", "f2": DOCETL_F2, "f1": DOCETL_F1, "product": DOCETL_PRODUCT},
    ]
    report = {
        "decision": decision,
        "checked_obs_rate": checked_obs_rate,
        "checked_exact_rate": exact_n / max(checked_n, 1),
        "false_absence_rate": false_abs_rate,
        "candidate_coverage": coverage_rate,
        "split": {k: dict(v) for k, v in split_acc.items()},
        "bands": {k: dict(v) for k, v in bands.items()},
        "by_attr": {k: dict(v) for k, v in by_attr.items()},
        "extrapolation": {"sample_writes": sample_writes, "full_writes": full_writes, "ratio": (full_writes or 0) / max(sample_writes, 1)},
        "table": table,
        "per_query": official["per_query"],
        "plumbing_per_query": plumbing["per_query"],
        "hashes": freeze,
        "pre_gold": pre,
    }
    (OUT / "post_freeze.json").write_text(json.dumps(report, indent=2, default=str))
    freeze["gold_loaded"] = True
    (OUT / "generation_frozen.json").write_text(json.dumps(freeze, indent=2))
    lines = [
        "# Legal candidate-aligned checked extraction",
        "",
        "Gold was loaded only after `generation_frozen.json`. The selector did not read benchmark gold, DocETL answers, reachability assignments, or prior gold-labeled audits.",
        "",
        "## Checked labels",
        "",
        f"Cells {checked_n}. Exact {exact_n / max(checked_n, 1):.4f}. Observational {checked_obs_rate:.4f}. False absence {false_abs_rate:.4f} on {gold_pos} gold-positive cells. Candidate coverage {coverage_rate:.4f}. Incomplete scans {pre.get('coverage_incomplete')}.",
        "",
        f"Label counts: {json.dumps(pre.get('checked'))}.",
        "",
        "## Ranker",
        "",
        f"Train gold-observational {split_acc['train']['obs'] / max(split_acc['train']['n'], 1):.4f}. Validation gold-observational {split_acc['heldout']['obs'] / max(split_acc['heldout']['n'], 1):.4f}. Validation agreement with checked labels {val_vs_checked:.4f}.",
        "",
        "| Attribute | Checked obs | Ranker obs | Writes |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, counts in sorted(by_attr.items()):
        lines.append(f"| `{name}` | {counts['checked_obs'] / max(counts['n'], 1):.4f} | {counts['ranker_obs'] / max(counts['n'], 1):.4f} | {counts['writes']} |")
    lines += ["", "| Confidence band | Writes | Observational precision |", "| --- | ---: | ---: |"]
    for key in ["0.85+", "0.75-0.85", "0.65-0.75", "0.55-0.65", "<0.55"]:
        counts = bands.get(key) or Counter()
        lines.append(f"| {key} | {counts['writes']} | {counts['obs'] / max(counts['writes'], 1):.4f} |")
    lines += [
        "",
        f"Full-corpus writes {full_writes}. Sample writes {sample_writes}. Extrapolation ratio {(full_writes or 0) / max(sample_writes, 1):.4f}.",
        f"Count-inflation fixture: {json.dumps(pre.get('fixture'), default=str)}.",
        "",
        "## Scores",
        "",
        "| Arm | Causal tokens | Accepted | F2 | F1@0.20 | Product |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in table:
        lines.append(f"| {row['arm']} | {row['tokens']} | {row['accepted']} | {row['f2']:.4f} | {row['f1']:.4f} | {row['product']:.4f} |")
    plumb = {row["query_id"]: row["product"] for row in plumbing["per_query"]}
    lines += ["", "## Per-query versus plumbing", "", "| Query | Plumbing | Official | Delta |", "| --- | ---: | ---: | ---: |"]
    for row in official["per_query"]:
        base = plumb.get(row["query_id"], 0.0)
        lines.append(f"| `{row['query_id']}` | {base:.4f} | {row['product']:.4f} | {row['product'] - base:+.4f} |")
    lines += ["", "## Hashes", "", "```json", json.dumps(freeze, indent=2), "```", "", decision, ""]
    (OUT / "REPORT.md").write_text("\n".join(lines))
    print(json.dumps({"decision": decision, "product": product, "docetl": DOCETL_PRODUCT, "checked_obs": checked_obs_rate, "coverage": coverage_rate, "false_absence": false_abs_rate}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
