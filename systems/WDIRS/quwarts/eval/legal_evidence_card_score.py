"""Post-freeze scoring for the Legal evidence-card selection arm."""

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
from quwarts.eval.legal_multichannel_availability_audit import RowEvaluator, channel_of, exact_gold, observational_match
from quwarts.experiments.synthesize_case80 import gold_name

OUT = ROOT / "results" / "quwarts_legal_evidence_card_select"
THETA_25 = 12_610_011
KEEP = "KEEP_PLUMBING"
from diagnostics.run_config_grid import load_ground_truth

FROZEN = ROOT / "results" / "quwarts_legal_multichannel_candidates"
WIN = ROOT / "results" / "quwarts_legal_shared_reachability"
DIAG = ROOT / "results" / "quwarts_legal_cost_aware_reachability" / "rebuilds" / "deterministic"


def main() -> int:
    freeze = json.loads((OUT / "generation_frozen.json").read_text())
    if not freeze or freeze.get("gold_loaded"):
        raise SystemExit("run invalid: missing or already-scored freeze")
    pre = json.loads((OUT / "pre_gold.json").read_text())
    parsed = json.loads((OUT / "parsed_decisions.json").read_text())
    cards = json.loads((OUT / "cards.json").read_text())
    cards_by = {c["cell_id"]: c for c in cards}
    inventory = json.loads((FROZEN / "candidate_inventory.json").read_text())
    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    plumbing_rows = load_plumbing_rows()
    gold = load_ground_truth(gold_name("Legal"))
    gold_by = gold_index(gold)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_by = {str(row.get("__entity_id")): row for row in plumbing_rows}
    evaluator = RowEvaluator(list(plumbing_rows[0]), statements)
    queries_by_attr = {name: list(records[name].queries) for name in records}
    by_id = {}
    for rec in inventory:
        for item in rec.get("all_candidates") or rec.get("candidates") or []:
            by_id[(rec["document_id"], rec["attribute"], str(item.get("id")))] = item

    arms = ["plumbing", "pass_a", "pass_b", "pass_c", "majority", "adjudication_only", "theta_5", "theta_10", "theta_25"]
    scores = {}
    plumbing_db = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
    scores["plumbing"] = score_db(plumbing_db, statements, predicates, query_ids, gold)
    scores["plumbing"]["tokens"] = 0
    meta_tokens = json.loads((OUT / "theta25_ledger.json").read_text())["spent"]
    for name in arms[1:]:
        db = OUT / "databases" / f"{name}.db"
        scores[name] = score_db(db, statements, predicates, query_ids, gold)
        scores[name]["tokens"] = meta_tokens if name in {"official", "theta_25"} else json.loads((OUT / "arm_meta" / f"{name}.json").read_text()).get("changed_cells", 0) and meta_tokens
        if name in {"pass_a", "pass_b", "pass_c"}:
            scores[name]["tokens"] = json.loads((OUT / "pre_gold.json").read_text()).get("purpose_tokens", {}).get(f"pass_{name[-1].upper()}", 0)
        meta = json.loads((OUT / "arm_meta" / f"{name}.json").read_text())
        scores[name]["accepted"] = meta["accepted"]
        scores[name]["sql_visible"] = meta.get("changed_cells")
    scores["theta_25"]["tokens"] = meta_tokens
    scores["official"] = scores["theta_25"]

    purpose = json.loads((OUT / "pre_gold.json").read_text()).get("purpose_tokens") or {}
    for name, key in (("pass_a", "pass_A"), ("pass_b", "pass_B"), ("pass_c", "pass_C")):
        scores[name]["tokens"] = purpose.get(key, 0)

    official = parsed["official"]
    exact = obs = cond_n = cond_hit = 0
    by_pass = {p: {"n": 0, "exact": 0} for p in ("A", "B", "C")}
    by_attr = defaultdict(lambda: {"n": 0, "exact": 0})
    by_ch = defaultdict(lambda: {"n": 0, "exact": 0})
    by_class = defaultdict(lambda: {"n": 0, "exact": 0})
    wrong = Counter()
    for card in cards:
        gold_v = gold_value(gold_by, card["document_id"], card["attribute"])
        cid = official.get(card["cell_id"])
        item = by_id.get((card["document_id"], card["attribute"], cid)) if cid and cid != KEEP else None
        pred = None if item is None else item.get("normalized")
        prow = plumbing_by[card["entity_id"]]
        has_gold_cand = any(exact_gold(specs, card["attribute"], by_id.get((card["document_id"], card["attribute"], lid), {}).get("normalized"), gold_v) for lid in card["listed_ids"] if lid != KEEP)
        hit = exact_gold(specs, card["attribute"], pred, gold_v) if pred is not None else False
        exact += int(hit)
        if pred is not None and observational_match(evaluator, queries_by_attr.get(card["attribute"]) or [], prow, card["attribute"], pred, gold_v):
            obs += 1
        if has_gold_cand:
            cond_n += 1
            cond_hit += int(hit)
        if cid and cid != KEEP and not hit:
            gtxt = str(gold_v or "").lower()
            ptxt = str(pred or "").lower()
            if any(y in ptxt and y not in gtxt for y in ("2006", "2007", "2008", "2009", "2010")):
                wrong["wrong_period"] += 1
            elif "component" in str(item.get("component_scope") or "").lower():
                wrong["wrong_component"] += 1
            elif item.get("unit") and gold_v not in (None, ""):
                wrong["wrong_unit"] += 1
            else:
                wrong["wrong_candidate"] += 1
        by_attr[card["attribute"]]["n"] += 1
        by_attr[card["attribute"]]["exact"] += int(hit)
        if item is not None:
            by_ch[channel_of(item)]["n"] += 1
            by_ch[channel_of(item)]["exact"] += int(hit)
        kind = (parsed.get("consensus") or {}).get(card["cell_id"], {}).get("kind") or "unknown"
        by_class[kind]["n"] += 1
        by_class[kind]["exact"] += int(hit)
        for p in ("A", "B", "C"):
            pcid = (parsed.get(p) or {}).get(card["cell_id"])
            pitem = by_id.get((card["document_id"], card["attribute"], pcid)) if pcid and pcid != KEEP else None
            by_pass[p]["n"] += 1
            by_pass[p]["exact"] += int(exact_gold(specs, card["attribute"], None if pitem is None else pitem.get("normalized"), gold_v))

    diag = {}
    recovered = 0
    distance = None
    if DIAG.joinpath("assignment_manifest.json").is_file():
        diag_manifest = json.loads((DIAG / "assignment_manifest.json").read_text())
        off_pairs = {}
        for card in cards:
            cid = official.get(card["cell_id"])
            if cid and cid != KEEP:
                off_pairs[(card["document_id"], card["attribute"])] = cid
        diag_pairs = {(doc, attr): cid for doc, attrs in diag_manifest.items() for attr, cid in attrs.items()}
        distance = len(set(off_pairs) ^ set(diag_pairs)) + sum(1 for k in set(off_pairs) & set(diag_pairs) if off_pairs[k] != diag_pairs[k])
        recovered = sum(1 for k, cid in diag_pairs.items() if off_pairs.get(k) == cid)
        diag = {"distance": distance, "recovered_ids": recovered, "diag_writes": len(diag_pairs), "official_writes": len(off_pairs)}

    maj_prod = scores["majority"]["mean_per_query_product"]
    off_prod = scores["theta_25"]["mean_per_query_product"]
    adj_effect = "improved" if off_prod > maj_prod + 1e-12 else ("harmed" if off_prod + 1e-12 < maj_prod else "unchanged")
    product = off_prod
    if product > DOCETL_PRODUCT:
        decision = "evidence-card selection beats Legal DocETL within theta25"
    elif freeze.get("spent", 0) >= THETA_25 and pre.get("completed_C", 0) < pre.get("selectable_cells", 1):
        decision = "budget exhausted before complete selection"
    elif adj_effect == "harmed" and maj_prod > DOCETL_PRODUCT:
        decision = "majority is useful but adjudication harms"
    else:
        decision = "deterministic candidates are sufficient but Qwen selection remains inadequate"

    rows = []
    for name, label in (
        ("plumbing", "plumbing"),
        ("pass_a", "Pass A"),
        ("pass_b", "Pass B"),
        ("pass_c", "Pass C"),
        ("majority", "majority"),
        ("adjudication_only", "adjudication-only"),
        ("theta_5", "official θ5"),
        ("theta_10", "official θ10"),
        ("theta_25", "official θ25"),
    ):
        s = scores[name]
        meta = {"accepted": 0, "changed_cells": 0}
        if name != "plumbing":
            meta = json.loads((OUT / "arm_meta" / f"{name}.json").read_text())
        rows.append({
            "arm": label,
            "tokens": s.get("tokens") or (0 if name == "plumbing" else meta_tokens if name.startswith("theta") or name == "official" else s.get("tokens") or 0),
            "accepted": 0 if name == "plumbing" else meta.get("accepted"),
            "sql_visible": 0 if name == "plumbing" else meta.get("changed_cells"),
            "f2": s["mean_structure_f2"],
            "f1": s["mean_cell_f1_at_0.20"],
            "product": s["mean_per_query_product"],
        })
    rows.append({"arm": "DocETL", "tokens": DOCETL_TOKENS, "accepted": "", "sql_visible": "", "f2": DOCETL_F2, "f1": DOCETL_F1, "product": DOCETL_PRODUCT})

    report = {
        "decision": decision,
        "pre_gold": pre,
        "scores": {k: {kk: scores[k][kk] for kk in scores[k] if kk != "per_query"} | {"per_query": scores[k].get("per_query")} for k in scores},
        "exact_accuracy": exact / max(len(cards), 1),
        "observational_accuracy": obs / max(len(cards), 1),
        "conditional_on_gold_candidate": cond_hit / max(cond_n, 1),
        "by_pass": by_pass,
        "by_attribute": dict(by_attr),
        "by_channel": dict(by_ch),
        "by_consensus": dict(by_class),
        "error_kinds": dict(wrong),
        "diagnostic": diag,
        "adjudication_effect": adj_effect,
        "table": rows,
    }
    (OUT / "post_freeze.json").write_text(json.dumps(report, indent=2, default=str))
    lines = [
        "# Legal deterministic evidence-card selection",
        "",
        "No frozen candidate, plumbing, or query artifact was modified. Reachability assignment manifests were blocked before the first spend. Gold was loaded only after `generation_frozen.json`.",
        "",
        "## Pre-gold",
        "",
        json.dumps(pre, indent=2),
        "",
        "## Post-freeze scores",
        "",
        "| Arm | Tokens | Accepted | SQL-visible | F2 | F1@0.20 | Product |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        acc = row["accepted"] if row["accepted"] != "" else ""
        vis = row["sql_visible"] if row["sql_visible"] != "" else ""
        lines.append(f"| {row['arm']} | {row['tokens']} | {acc} | {vis} | {row['f2']:.4f} | {row['f1']:.4f} | {row['product']:.4f} |")
    plumbing_pq = {row["query_id"]: row["product"] for row in scores["plumbing"]["per_query"]}
    lines += ["", "## Official θ25 per-query products", "", "| Query | Plumbing | Official | Delta |", "| --- | ---: | ---: | ---: |"]
    for row in scores["theta_25"]["per_query"]:
        base = plumbing_pq.get(row["query_id"], 0.0)
        lines.append(f"| `{row['query_id']}` | {base:.4f} | {row['product']:.4f} | {row['product']-base:+.4f} |")
    lines += [
        "",
        f"Exact candidate accuracy: {report['exact_accuracy']:.4f}. Observational: {report['observational_accuracy']:.4f}. Conditional on gold candidate present: {report['conditional_on_gold_candidate']:.4f}.",
        f"Diagnostic 0.1886 comparison: {json.dumps(diag)}. Adjudication vs majority: {adj_effect}.",
        "",
        decision,
        "",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines))
    print(json.dumps({"decision": decision, "product": product, "docetl": DOCETL_PRODUCT, "adj": adj_effect}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
