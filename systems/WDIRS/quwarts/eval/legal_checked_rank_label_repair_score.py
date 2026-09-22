"""Post-freeze gold scoring for the label-repaired checked ranker."""

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

OUT = ROOT / "results" / "quwarts_legal_checked_rank_label_repair"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
PREVIOUS = 0.03495590543909872


def main() -> int:
    freeze = json.loads((OUT / "generation_frozen.json").read_text())
    if freeze.get("gold_loaded") or not freeze.get("rebuild_match") or int(freeze.get("new_model_spend") or 0) != 0:
        raise SystemExit("run invalid")
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
    product = official["mean_per_query_product"]
    train_top1 = pre["overfit"]["top1_value_class"][0] / max(pre["overfit"]["top1_value_class"][1], 1)
    val_acc = pre["selected_policy"]["candidate_accuracy"]
    channel_acc = pre["baselines"]["highest_priority_channel"]["candidate_accuracy"]
    if product > DOCETL_PRODUCT:
        decision = "label-semantic repair beats DocETL"
    elif pre["labels"]["train_groups"] < 30 or pre["labels"]["train_positive_rows"] < 30:
        decision = "checked supervision is too sparse after label repair"
    elif product > PREVIOUS:
        decision = "label-semantic repair improves ranking but remains below DocETL"
    elif val_acc + 1e-12 < channel_acc or val_acc + 0.15 <= train_top1:
        decision = "repaired selector does not generalize"
    else:
        decision = "checked supervision is too sparse after label repair"
    table = [
        {"arm": "plumbing", "tokens": 0, "writes": 0, "f2": plumbing["mean_structure_f2"], "f1": plumbing["mean_cell_f1_at_0.20"], "product": plumbing["mean_per_query_product"]},
        {"arm": "previous checked ranker", "tokens": 3626478, "writes": 136, "f2": 0.20543217286914767, "f1": 0.049038461538461545, "product": PREVIOUS},
        {"arm": "label repair", "tokens": pre["causal_spent"], "writes": pre["writes"], "f2": official["mean_structure_f2"], "f1": official["mean_cell_f1_at_0.20"], "product": product},
        {"arm": "DocETL", "tokens": DOCETL_TOKENS, "writes": "", "f2": DOCETL_F2, "f1": DOCETL_F1, "product": DOCETL_PRODUCT},
    ]
    report = {"decision": decision, "table": table, "per_query": official["per_query"], "plumbing_per_query": plumbing["per_query"], "pre_gold": pre, "hashes": freeze}
    (OUT / "post_freeze.json").write_text(json.dumps(report, indent=2, default=str))
    labels = pre["labels"]
    old = labels["old_query_equivalence"]
    lines = [
        "# Legal checked-ranker label repair",
        "",
        "Gold was loaded only after `generation_frozen.json`. No new model calls were made. Frozen checked-extraction artifacts were not modified.",
        "",
        "## Labels",
        "",
        f"Training groups {labels['train_groups']}. Validation groups {labels['validation_groups']}. Repaired positive rows {labels['positive_rows']} and negative rows {labels['negative_rows']}. Value-identical multi-positive groups {labels['multi_value_identical_groups']}. All-positive groups {labels['all_positive_groups']}.",
        "",
        f"Query-result equivalence on the training cells had marked {old['train']['positive_rows']} rows positive and {old['train']['all_positive_groups']} groups all-positive. After value-identity repair those training figures are {labels['train_positive_rows']} positives and {labels['all_positive_groups']} all-positive groups.",
        "",
        f"Extracted KEEP labels: {labels['extracted_keep']}, both in validation. Training DO_NOT_WRITE count: {labels['train_do_not_write']}. A weighted two-class gate is undefined on that split. The one-class SVM preserved both validation KEEP cells and was selected over isolation forest.",
        "",
        "## Validation",
        "",
        f"Selected policy `{pre['selected_policy']['policy']}`. Candidate accuracy {pre['selected_policy']['candidate_accuracy_n'][0]}/{pre['selected_policy']['candidate_accuracy_n'][1]}. Committed precision {pre['selected_policy']['committed_precision_n'][0]}/{pre['selected_policy']['committed_precision_n'][1]}. UNCERTAIN writes {pre['selected_policy']['uncertain_incorrect_n'][0]}/{pre['selected_policy']['uncertain_incorrect_n'][1]}. KEEP preservation {pre['selected_policy']['keep_preservation_n'][0]}/{pre['selected_policy']['keep_preservation_n'][1]}.",
        "",
        f"Train-on-train writeability recall {pre['overfit']['writeability_recall_on_committed_train'][0]}/{pre['overfit']['writeability_recall_on_committed_train'][1]}. Top-1 value class {pre['overfit']['top1_value_class'][0]}/{pre['overfit']['top1_value_class'][1]}. Positive-set recall {pre['overfit']['positive_set_recall'][0]}/{pre['overfit']['positive_set_recall'][1]}.",
        "",
        f"Same-denominator baselines: always abstain {pre['baselines']['always_abstain']['candidate_accuracy_n'][0]}/{pre['baselines']['always_abstain']['candidate_accuracy_n'][1]}, highest-priority channel {pre['baselines']['highest_priority_channel']['candidate_accuracy_n'][0]}/{pre['baselines']['highest_priority_channel']['candidate_accuracy_n'][1]}, source-supported channel {pre['baselines']['source_supported_channel']['candidate_accuracy_n'][0]}/{pre['baselines']['source_supported_channel']['candidate_accuracy_n'][1]}, repaired ranker {pre['baselines']['repaired_ranker']['candidate_accuracy_n'][0]}/{pre['baselines']['repaired_ranker']['candidate_accuracy_n'][1]}.",
        "",
        f"Full-corpus writes {pre['writes']}. By attribute: {json.dumps(pre['writes_by_attribute'])}. By channel: {json.dumps(pre['writes_by_channel'])}.",
        "",
        "## Scores",
        "",
        "| Arm | Causal tokens | Writes | F2 | F1@0.20 | Product |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in table:
        lines.append(f"| {row['arm']} | {row['tokens']} | {row['writes']} | {row['f2']:.4f} | {row['f1']:.4f} | {row['product']:.4f} |")
    plumb = {row["query_id"]: row["product"] for row in plumbing["per_query"]}
    lines += ["", "## Per-query versus plumbing", "", "| Query | Plumbing | Repair | Delta |", "| --- | ---: | ---: | ---: |"]
    for row in official["per_query"]:
        base = plumb.get(row["query_id"], 0.0)
        lines.append(f"| `{row['query_id']}` | {base:.4f} | {row['product']:.4f} | {row['product'] - base:+.4f} |")
    freeze["gold_loaded"] = True
    (OUT / "generation_frozen.json").write_text(json.dumps(freeze, indent=2))
    lines += ["", "## Hashes", "", "```json", json.dumps(freeze, indent=2), "```", "", decision, ""]
    (OUT / "REPORT.md").write_text("\n".join(lines))
    print(json.dumps({"decision": decision, "product": product, "docetl": DOCETL_PRODUCT, "previous": PREVIOUS, "f2": official["mean_structure_f2"], "f1": official["mean_cell_f1_at_0.20"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
