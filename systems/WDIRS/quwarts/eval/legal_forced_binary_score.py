"""Post-freeze scoring for the Legal forced-binary A/B aggregation arm."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
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
    load_plumbing_rows,
    score_db,
)
from quwarts.eval.legal_multichannel_availability_audit import RowEvaluator, exact_gold, observational_match
from quwarts.experiments.synthesize_case80 import gold_name
from diagnostics.run_config_grid import load_ground_truth

OUT = ROOT / "results" / "quwarts_legal_forced_binary"
KEEP = "KEEP_PLUMBING"
FROZEN_A = 3_468_542
FROZEN_B = 7_491_088
AB_WIN = ROOT / "results" / "quwarts_legal_evidence_card_aggregation_audit" / "reachability" / "restricted" / "A_+_B" / "best"


def main() -> int:
    freeze = json.loads((OUT / "generation_frozen.json").read_text())
    if not freeze:
        raise SystemExit("run invalid: missing freeze")
    pre = json.loads((OUT / "pre_gold.json").read_text())
    if not freeze.get("gate_passed"):
        print(json.dumps({"decision": "forced binary prompt failed synthetic gate", "pre_gold": pre}, indent=2), flush=True)
        return 0
    if freeze.get("gold_loaded"):
        raise SystemExit("run invalid: already-scored freeze")
    parsed = json.loads((OUT / "parsed_decisions.json").read_text())
    cells_src = json.loads((ROOT / "results" / "quwarts_legal_evidence_card_select" / "cards.json").read_text())
    inventory = json.loads((ROOT / "results" / "quwarts_legal_multichannel_candidates" / "candidate_inventory.json").read_text())
    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    plumbing_rows = load_plumbing_rows()
    gold = load_ground_truth(gold_name("Legal"))
    gold_by = gold_index(gold)
    plumbing_by = {str(row.get("__entity_id")): row for row in plumbing_rows}
    evaluator = RowEvaluator(list(plumbing_rows[0]), statements)
    queries_by_attr = {name: list(records[name].queries) for name in records}
    by_id = {}
    for rec in inventory:
        for item in rec.get("all_candidates") or rec.get("candidates") or []:
            by_id[(rec["document_id"], rec["attribute"], str(item.get("id")))] = item
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    spent = pre["causal_spent"]
    arms = [
        ("plumbing", "plumbing", 0),
        ("A", "A", FROZEN_A),
        ("B", "B", FROZEN_B),
        ("forward", "forward only", spent),
        ("reverse", "reverse only", spent),
        ("official", "official forced binary", spent),
    ]
    plumbing_db = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
    scores = {"plumbing": score_db(plumbing_db, statements, predicates, query_ids, gold)}
    scores["plumbing"]["tokens"] = 0
    table = []
    for name, label, tokens in arms:
        if name == "plumbing":
            s = scores["plumbing"]
            meta = {"accepted": 0}
        else:
            s = score_db(OUT / "databases" / f"{name}.db", statements, predicates, query_ids, gold)
            scores[name] = s
            meta = json.loads((OUT / "arm_meta" / f"{name}.json").read_text())
        table.append({"arm": label, "tokens": tokens, "accepted": 0 if name == "plumbing" else meta.get("accepted"), "f2": s["mean_structure_f2"], "f1": s["mean_cell_f1_at_0.20"], "product": s["mean_per_query_product"]})
    table.append({"arm": "DocETL", "tokens": DOCETL_TOKENS, "accepted": "", "f2": DOCETL_F2, "f1": DOCETL_F1, "product": DOCETL_PRODUCT})

    official = parsed["official"]
    exact = obs = n = 0
    cons_a_n = cons_a_hit = cons_b_n = cons_b_hit = 0
    trans = Counter()
    completed = set(parsed.get("completed") or [])
    for card in cells_src:
        n += 1
        gold_v = gold_value(gold_by, card["document_id"], card["attribute"])
        cid = official.get(card["cell_id"])
        item = by_id.get((card["document_id"], card["attribute"], cid)) if cid and cid != KEEP else None
        pred = None if item is None else item.get("normalized")
        hit = bool(pred is not None and exact_gold(specs, card["attribute"], pred, gold_v))
        exact += int(hit)
        prow = plumbing_by[card["entity_id"]]
        if pred is not None and observational_match(evaluator, queries_by_attr.get(card["attribute"]) or [], prow, card["attribute"], pred, gold_v):
            obs += 1
        a = parsed["A"].get(card["cell_id"])
        b = parsed["B"].get(card["cell_id"])
        if a != b and card["cell_id"] in completed:
            fwd = parsed["forward"].get(card["cell_id"])
            rev = parsed["reverse"].get(card["cell_id"])
            if fwd == rev == "A":
                cons_a_n += 1
                cons_a_hit += int(hit)
            elif fwd == rev == "B":
                cons_b_n += 1
                cons_b_hit += int(hit)
            if cid == b and b != a:
                trans["A_to_B"] += 1
            if cid == a and a != b:
                trans["B_to_A"] += 1
            if a != KEEP and cid == KEEP:
                trans["candidate_to_plumbing"] += 1
            if a == KEEP and cid != KEEP:
                trans["plumbing_to_candidate"] += 1

    diag = {}
    if AB_WIN.joinpath("assignment_manifest.json").is_file():
        diag_manifest = json.loads((AB_WIN / "assignment_manifest.json").read_text())
        off_pairs = {}
        for card in cells_src:
            cid = official.get(card["cell_id"])
            if cid and cid != KEEP:
                off_pairs[(card["document_id"], card["attribute"])] = cid
        diag_pairs = {(doc, attr): cid for doc, attrs in diag_manifest.items() for attr, cid in attrs.items()}
        diag = {
            "distance": len(set(off_pairs) ^ set(diag_pairs)) + sum(1 for k in set(off_pairs) & set(diag_pairs) if off_pairs[k] != diag_pairs[k]),
            "recovered_ids": sum(1 for k, cid in diag_pairs.items() if off_pairs.get(k) == cid),
            "diag_writes": len(diag_pairs),
            "official_writes": len(off_pairs),
        }

    prefixes = {}
    for name in ("prefix_25", "prefix_50", "prefix_75", "prefix_100"):
        s = score_db(OUT / "databases" / f"{name}.db", statements, predicates, query_ids, gold)
        prefixes[name] = s["mean_per_query_product"]

    off_prod = scores["official"]["mean_per_query_product"]
    a_prod = scores["A"]["mean_per_query_product"]
    if off_prod > DOCETL_PRODUCT:
        decision = "forced binary A/B aggregation beats Legal DocETL within theta25"
    elif off_prod + 1e-12 < a_prod:
        decision = "forced binary harms A"
    elif off_prod > a_prod + 1e-12:
        decision = "forced binary improves A but remains below DocETL"
    else:
        decision = "forced binary harms A" if off_prod <= a_prod else "forced binary improves A but remains below DocETL"

    report = {
        "decision": decision,
        "pre_gold": pre,
        "table": table,
        "exact_accuracy": exact / max(n, 1),
        "observational_accuracy": obs / max(n, 1),
        "consistent_A_accuracy": cons_a_hit / max(cons_a_n, 1),
        "consistent_B_accuracy": cons_b_hit / max(cons_b_n, 1),
        "transitions": dict(trans),
        "diagnostic_AB_0_1301": diag,
        "prefix_products": prefixes,
        "official_product": off_prod,
    }
    (OUT / "post_freeze.json").write_text(json.dumps(report, indent=2, default=str))
    lines = [
        "# Legal forced binary A/B aggregation",
        "",
        "Frozen Pass A/B artifacts were not modified. Gold and reachability assignments were loaded only after `generation_frozen.json`.",
        "",
        "## Pre-gold",
        "",
        f"Synthetic gate: {pre['synthetic_correct']}/24 correct, {pre['synthetic_order_consistent']}/12 order-consistent, {pre['synthetic_parsed_fixtures']}/12 parsed.",
        "",
        f"A=B candidate {pre['A_eq_B_candidate']}. A=B plumbing {pre['A_eq_B_plumbing']}. A candidate/B candidate {pre['A_cand_B_cand']}. A candidate/B plumbing {pre['A_cand_B_plumbing']}. A plumbing/B candidate {pre['A_plumbing_B_cand']}.",
        f"Completed pairs {pre['completed_pairs']}. Consistent A {pre['consistent_A']}. Consistent B {pre['consistent_B']}. Order disagreements {pre['order_disagreements']}. Malformed {pre['malformed_responses']}. Unscheduled A fallbacks {pre['unscheduled_A_fallback']}.",
        f"Tokens by direction: {json.dumps(pre['tokens_by_direction'])}. Tokens by attribute: {json.dumps(pre['tokens_by_attribute'])}. Causal spend {pre['causal_spent']}.",
        "",
        "## Scores",
        "",
        "| Arm | Causal tokens | Accepted | F2 | F1@0.20 | Product |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in table:
        acc = row["accepted"] if row["accepted"] != "" else ""
        lines.append(f"| {row['arm']} | {row['tokens']} | {acc} | {row['f2']:.4f} | {row['f1']:.4f} | {row['product']:.4f} |")
    a_pq = {row["query_id"]: row["product"] for row in scores["A"]["per_query"]}
    lines += ["", "## Official per-query versus A", "", "| Query | A | Official | Delta vs A |", "| --- | ---: | ---: | ---: |"]
    for row in scores["official"]["per_query"]:
        base = a_pq.get(row["query_id"], 0.0)
        lines.append(f"| `{row['query_id']}` | {base:.4f} | {row['product']:.4f} | {row['product']-base:+.4f} |")
    lines += [
        "",
        f"Exact accuracy: {report['exact_accuracy']:.4f}. Observational: {report['observational_accuracy']:.4f}.",
        f"Consistent-A accuracy: {report['consistent_A_accuracy']:.4f}. Consistent-B accuracy: {report['consistent_B_accuracy']:.4f}.",
        f"Transitions: {json.dumps(dict(trans))}. Diagnostic 0.1301 comparison: {json.dumps(diag)}.",
        f"Prefix products: {json.dumps(prefixes)}.",
        "",
        decision,
        "",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines))
    print(json.dumps({"decision": decision, "official": off_prod, "A": a_prod, "docetl": DOCETL_PRODUCT, "diag": diag}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
