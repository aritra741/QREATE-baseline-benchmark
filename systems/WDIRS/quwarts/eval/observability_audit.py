"""Step 0–1. AST observability and atomic predicates. Zero tokens."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.synthesize_case80 import queries_for

OUT = ROOT / "results" / "quwarts_med_signatures"


def main() -> int:
    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    report = audit_workload(queries)
    train_report = audit_workload(train)
    predicates = enumerate_predicates(report.occurrences, report.signature_eligible)
    train_predicates = enumerate_predicates(train_report.occurrences, train_report.signature_eligible)
    raw_eligible = sum(
        1
        for item in report.occurrences
        if item.attribute in report.signature_eligible
        and item.usage in {"like_literal", "eq_literal", "is_null", "cmp_literal", "case_condition"}
    )
    per_attr = Counter(item.attribute for item in predicates)
    raw_per_attr: dict[str, int] = defaultdict(int)
    for item in predicates:
        raw_per_attr[item.attribute] += item.raw_occurrences
    payload = {
        "step": 0,
        "n_queries": len(queries),
        "n_train": len(train),
        "n_test": len(test),
        "signature_eligible": report.signature_eligible,
        "full_value_required": report.full_value_required,
        "usages": report.usages,
        "gate_vocab": report.gate_vocab,
        "gate_pass": report.gate_pass,
        "step1": {
            "n_predicates_q": len(predicates),
            "n_predicates_train": len(train_predicates),
            "raw_eligible_occurrences": raw_eligible,
            "dedup_ratio_unique_over_raw": (len(predicates) / raw_eligible) if raw_eligible else None,
            "reuse_1_minus_unique_over_raw": (1 - len(predicates) / raw_eligible) if raw_eligible else None,
            "per_attribute": {
                name: {
                    "unique_predicates": per_attr[name],
                    "raw_occurrences": raw_per_attr[name],
                    "dedup_ratio": per_attr[name] / raw_per_attr[name] if raw_per_attr[name] else None,
                }
                for name in report.signature_eligible
            },
            "predicates": [
                {
                    "pred_id": item.pred_id,
                    "sig_name": item.sig_name,
                    "attribute": item.attribute,
                    "operator": item.operator,
                    "literal": item.literal,
                    "transforms": list(item.transforms),
                    "n_queries": len(item.query_ids),
                    "raw_occurrences": item.raw_occurrences,
                    "bare_condition_sql": item.bare_condition_sql,
                }
                for item in predicates
            ],
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "step0_step1.json"
    path.write_text(json.dumps(payload, indent=2))
    print(json.dumps({
        "wrote": str(path),
        "signature_eligible": report.signature_eligible,
        "full_value_required": report.full_value_required,
        "gate_vocab": report.gate_vocab,
        "gate_pass": report.gate_pass,
        "n_predicates": len(predicates),
        "raw_eligible_occurrences": raw_eligible,
        "dedup_ratio": payload["step1"]["dedup_ratio_unique_over_raw"],
        "reuse": payload["step1"]["reuse_1_minus_unique_over_raw"],
        "per_attribute_unique": dict(per_attr),
    }, indent=2))
    return 0 if report.gate_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
