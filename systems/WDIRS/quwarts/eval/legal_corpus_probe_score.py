"""Post-freeze scoring for the Legal corpus-probe optimizer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.legal_coverage_transfer import (
    DOCETL_DIR,
    DOCETL_F1,
    DOCETL_F2,
    DOCETL_PRODUCT,
    DOCETL_TOKENS,
    score_db,
)
from quwarts.experiments.synthesize_case80 import gold_name
from diagnostics.run_config_grid import load_ground_truth

OUT = ROOT / "results" / "quwarts_legal_corpus_probe"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"


def main() -> int:
    freeze = json.loads((OUT / "generation_frozen.json").read_text())
    if not freeze or freeze.get("gold_loaded"):
        raise SystemExit("run invalid: information-boundary or freeze failure")
    pre = json.loads((OUT / "pre_gold.json").read_text())
    gold = load_ground_truth(gold_name("Legal"))
    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing = score_db(PLUMBING, statements, predicates, query_ids, gold)
    official = score_db(OUT / "databases" / "official.db", statements, predicates, query_ids, gold)
    diag_scores = []
    for path in sorted((OUT / "databases").glob("diag_config_*.db")):
        if path.name.endswith("_rebuild.db"):
            continue
        diag_scores.append({"name": path.stem, **score_db(path, statements, predicates, query_ids, gold)})
    silver_order = [row["label"] for row in pre.get("considered") or []]
    gold_order = ["official"] + [row["name"] for row in sorted(diag_scores, key=lambda r: -r["mean_per_query_product"])]
    calibrated = True
    if diag_scores:
        best_diag = max(diag_scores, key=lambda r: r["mean_per_query_product"])
        if best_diag["mean_per_query_product"] > official["mean_per_query_product"] + 1e-12:
            calibrated = False
    off = official["mean_per_query_product"]
    if off > DOCETL_PRODUCT:
        decision = "corpus-probed optimizer beats DocETL"
    elif not calibrated:
        decision = "corpus-derived validation is not calibrated to benchmark accuracy"
    else:
        decision = "corpus probes rank plans correctly but available programs remain insufficient"
    table = [
        {"arm": "plumbing", "tokens": 0, "accepted": 0, "f2": plumbing["mean_structure_f2"], "f1": plumbing["mean_cell_f1_at_0.20"], "product": plumbing["mean_per_query_product"]},
        {"arm": "official corpus-probe", "tokens": pre["causal_spent"], "accepted": pre.get("accepted"), "f2": official["mean_structure_f2"], "f1": official["mean_cell_f1_at_0.20"], "product": off},
        {"arm": "DocETL", "tokens": DOCETL_TOKENS, "accepted": "", "f2": DOCETL_F2, "f1": DOCETL_F1, "product": DOCETL_PRODUCT},
    ]
    report = {
        "decision": decision,
        "pre_gold": {k: pre[k] for k in pre if k != "sample"},
        "table": table,
        "per_query": official["per_query"],
        "plumbing_per_query": plumbing["per_query"],
        "diag": diag_scores,
        "silver_order": silver_order[:8],
        "gold_order": gold_order,
        "calibrated": calibrated,
        "hashes": freeze,
    }
    (OUT / "post_freeze.json").write_text(json.dumps(report, indent=2, default=str))
    lines = [
        "# Legal corpus-grounded sample-probe optimizer",
        "",
        "Benchmark gold was loaded only after `generation_frozen.json`. Blocked reachability and prior judge artifacts were not read by the selector.",
        "",
        "## Selected programs",
        "",
        json.dumps(pre.get("selected"), indent=2),
        "",
        f"Sample: train {pre['sample']['train'] if isinstance(pre.get('sample'), dict) and 'train' in pre.get('sample', {}) else pre.get('sample', {}).get('train') if isinstance(pre.get('sample'), dict) else ''} / held-out from pre-gold file.",
        f"Silver: {json.dumps(pre.get('silver'))}",
        f"Held-out winner product {pre.get('heldout_winner')}. Tokens {json.dumps(pre.get('tokens_by_purpose'))}. Causal spend {pre.get('causal_spent')}.",
        "",
        "## Scores",
        "",
        "| Arm | Causal tokens | Accepted | F2 | F1@0.20 | Product |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in table:
        acc = row["accepted"] if row["accepted"] != "" else ""
        lines.append(f"| {row['arm']} | {row['tokens']} | {acc} | {row['f2']:.4f} | {row['f1']:.4f} | {row['product']:.4f} |")
    plumb = {row["query_id"]: row["product"] for row in plumbing["per_query"]}
    lines += ["", "## Per-query", "", "| Query | Plumbing | Official | Delta |", "| --- | ---: | ---: | ---: |"]
    for row in official["per_query"]:
        base = plumb.get(row["query_id"], 0.0)
        lines.append(f"| `{row['query_id']}` | {base:.4f} | {row['product']:.4f} | {row['product']-base:+.4f} |")
    lines += ["", f"Pre-gold ranking vs post-freeze: calibrated={calibrated}.", "", json.dumps(freeze, indent=2), "", decision, ""]
    # fix sample line - read pre properly
    (OUT / "REPORT.md").write_text("\n".join(lines))
    # rewrite report sample section more cleanly
    sample = json.loads((OUT / "pre_gold.json").read_text())
    report_text = (OUT / "REPORT.md").read_text()
    (OUT / "REPORT.md").write_text(report_text)
    print(json.dumps({"decision": decision, "official": off, "docetl": DOCETL_PRODUCT, "calibrated": calibrated, "spent": pre["causal_spent"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
