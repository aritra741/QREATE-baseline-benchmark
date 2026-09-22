"""Post-freeze scoring for the Legal A/B pairwise aggregation arm."""

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

OUT = ROOT / "results" / "quwarts_legal_pairwise_ab"
KEEP = "KEEP_PLUMBING"
THETA_25 = 12_610_011
FROZEN_A = 3_468_542
FROZEN_B = 7_491_088
AB_WIN = ROOT / "results" / "quwarts_legal_evidence_card_aggregation_audit" / "reachability" / "restricted" / "A_+_B" / "best"


def main() -> int:
    freeze = json.loads((OUT / "generation_frozen.json").read_text())
    if not freeze or freeze.get("gold_loaded"):
        raise SystemExit("run invalid: missing or already-scored freeze")
    pre = json.loads((OUT / "pre_gold.json").read_text())
    parsed = json.loads((OUT / "parsed_decisions.json").read_text())
    cards = json.loads((OUT / "pair_cards.json").read_text()) if (OUT / "pair_cards.json").is_file() else {}
    cells_src = json.loads((ROOT / "results" / "quwarts_legal_evidence_card_select" / "cards.json").read_text())
    cells = {c["cell_id"]: c for c in cells_src}
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

    from quwarts.core.signature import audit_workload, enumerate_predicates
    from quwarts.core.signature_realize import live_predicates

    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    arms = [
        ("plumbing", "plumbing", 0),
        ("A", "A", FROZEN_A),
        ("B", "B", FROZEN_B),
        ("judge1_A_fallback", "Judge 1 + A fallback", pre["causal_spent"]),
        ("judge2_A_fallback", "Judge 2 + A fallback", pre["causal_spent"]),
        ("agreement_replacements", "agreement replacements", pre["causal_spent"]),
        ("agreement_additions", "agreement additions", pre["causal_spent"]),
        ("official", "official pairwise", pre["causal_spent"]),
    ]
    plumbing_db = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
    scores = {"plumbing": score_db(plumbing_db, statements, predicates, query_ids, gold)}
    scores["plumbing"]["tokens"] = 0
    table = []
    for name, label, tokens in arms:
        if name == "plumbing":
            s = scores["plumbing"]
            meta = {"accepted": 0, "changed_cells": 0}
        else:
            s = score_db(OUT / "databases" / f"{name}.db", statements, predicates, query_ids, gold)
            scores[name] = s
            meta = json.loads((OUT / "arm_meta" / f"{name}.json").read_text())
        s["tokens"] = tokens
        table.append(
            {
                "arm": label,
                "tokens": tokens,
                "accepted": 0 if name == "plumbing" else meta.get("accepted"),
                "sql_visible": 0 if name == "plumbing" else meta.get("changed_cells"),
                "f2": s["mean_structure_f2"],
                "f1": s["mean_cell_f1_at_0.20"],
                "product": s["mean_per_query_product"],
            }
        )
    table.append({"arm": "DocETL", "tokens": DOCETL_TOKENS, "accepted": "", "sql_visible": "", "f2": DOCETL_F2, "f1": DOCETL_F1, "product": DOCETL_PRODUCT})

    official = parsed["official"]
    exact = obs = n = 0
    pair_n = pair_hit = 0
    by_kind = defaultdict(lambda: {"n": 0, "exact": 0})
    agree_n = agree_hit = disagree_n = disagree_hit = 0
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
        if a != b:
            pair_n += 1
            pair_hit += int(hit)
            if a != KEEP and b != KEEP:
                kind = "A_cand_B_cand"
            elif a != KEEP:
                kind = "A_cand_B_KEEP"
            else:
                kind = "A_KEEP_B_cand"
            by_kind[kind]["n"] += 1
            by_kind[kind]["exact"] += int(hit)
            if card["cell_id"] in completed:
                j1 = parsed["J1"].get(card["cell_id"])
                j2 = parsed["J2"].get(card["cell_id"])
                if j1 and j2 and j1 == j2:
                    agree_n += 1
                    agree_hit += int(hit)
                else:
                    disagree_n += 1
                    disagree_hit += int(hit)
            if cid == b and a != b:
                trans["A_to_B"] += 1
            if cid == a and a != b:
                trans["B_to_A"] += 1
            if a != KEEP and cid == KEEP:
                trans["candidate_to_KEEP"] += 1
            if a == KEEP and cid != KEEP:
                trans["KEEP_to_candidate"] += 1

    diag = {}
    if AB_WIN.joinpath("assignment_manifest.json").is_file():
        diag_manifest = json.loads((AB_WIN / "assignment_manifest.json").read_text())
        off_pairs = {}
        for card in cells_src:
            cid = official.get(card["cell_id"])
            if cid and cid != KEEP:
                off_pairs[(card["document_id"], card["attribute"])] = cid
        diag_pairs = {(doc, attr): cid for doc, attrs in diag_manifest.items() for attr, cid in attrs.items()}
        distance = len(set(off_pairs) ^ set(diag_pairs)) + sum(1 for k in set(off_pairs) & set(diag_pairs) if off_pairs[k] != diag_pairs[k])
        recovered = sum(1 for k, cid in diag_pairs.items() if off_pairs.get(k) == cid)
        diag = {"distance": distance, "recovered_ids": recovered, "diag_writes": len(diag_pairs), "official_writes": len(off_pairs)}

    prefixes = {}
    for name in ("prefix_25", "prefix_50", "prefix_75", "prefix_100"):
        s = score_db(OUT / "databases" / f"{name}.db", statements, predicates, query_ids, gold)
        prefixes[name] = s["mean_per_query_product"]

    off_prod = scores["official"]["mean_per_query_product"]
    a_prod = scores["A"]["mean_per_query_product"]
    if off_prod > DOCETL_PRODUCT:
        decision = "pairwise A/B aggregation beats Legal DocETL within theta25"
    elif off_prod + 1e-12 < a_prod:
        decision = "A fallback is better than pairwise aggregation"
    elif off_prod > a_prod + 1e-12:
        decision = "pairwise judging improves A but remains below DocETL"
    else:
        decision = "A+B judgments contain a win but Qwen cannot identify it"

    report = {
        "decision": decision,
        "pre_gold": pre,
        "table": table,
        "exact_accuracy": exact / max(n, 1),
        "observational_accuracy": obs / max(n, 1),
        "pairwise_accuracy_overall": pair_hit / max(pair_n, 1),
        "by_disagreement": dict(by_kind),
        "agree_accuracy": agree_hit / max(agree_n, 1),
        "disagree_accuracy": disagree_hit / max(disagree_n, 1),
        "transitions": dict(trans),
        "diagnostic_AB_0_1301": diag,
        "prefix_products": prefixes,
        "official_product": off_prod,
    }
    (OUT / "post_freeze.json").write_text(json.dumps(report, indent=2, default=str))
    lines = [
        "# Legal A/B pairwise aggregation",
        "",
        "Frozen Pass A/B artifacts were not modified. Gold and reachability assignments were loaded only after `generation_frozen.json`.",
        "",
        "## Pre-gold",
        "",
        json.dumps(pre, indent=2),
        "",
        "## Scores",
        "",
        "| Arm | Causal tokens | Accepted | SQL-visible | F2 | F1@0.20 | Product |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in table:
        acc = row["accepted"] if row["accepted"] != "" else ""
        vis = row["sql_visible"] if row["sql_visible"] != "" else ""
        lines.append(f"| {row['arm']} | {row['tokens']} | {acc} | {vis} | {row['f2']:.4f} | {row['f1']:.4f} | {row['product']:.4f} |")
    plumbing_pq = {row["query_id"]: row["product"] for row in scores["plumbing"]["per_query"]}
    a_pq = {row["query_id"]: row["product"] for row in scores["A"]["per_query"]}
    lines += ["", "## Official per-query versus A", "", "| Query | A | Official | Delta vs A |", "| --- | ---: | ---: | ---: |"]
    for row in scores["official"]["per_query"]:
        base = a_pq.get(row["query_id"], 0.0)
        lines.append(f"| `{row['query_id']}` | {base:.4f} | {row['product']:.4f} | {row['product']-base:+.4f} |")
    lines += [
        "",
        f"Pairwise accuracy overall: {report['pairwise_accuracy_overall']:.4f}. By type: {json.dumps({k: (v['exact']/max(v['n'],1)) for k,v in by_kind.items()})}.",
        f"Exact accuracy: {report['exact_accuracy']:.4f}. Observational: {report['observational_accuracy']:.4f}.",
        f"Judge-agree accuracy: {report['agree_accuracy']:.4f}. Judge-disagree accuracy: {report['disagree_accuracy']:.4f}.",
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
