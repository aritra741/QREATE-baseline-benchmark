#!/usr/bin/env python3
"""Refresh the Player agg20 case-study site from the portable analysis pack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "case study" / "player_agg20_case_pack.json"
OUTPUT = ROOT / "player-agg20-case-site" / "src" / "data.json"


def _score(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "structure_f2": metrics.get("structure"),
        "official_accuracy": metrics.get("official_accuracy"),
        "query_score": {"0.2": metrics.get("score_at_20")},
        "pred_rows": metrics.get("predicted_row_count"),
        "gold_rows": metrics.get("gold_row_count"),
    }


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    headline = pack["headline"]
    queries = []
    for query_id in sorted(pack["queries"], key=lambda item: int(item[1:])):
        case = pack["queries"][query_id]
        queries.append(
            {
                "query_id": query_id,
                "nl": case["natural_language"],
                "reference_sql": case["reference_sql"],
                "quwarts_sql": case["quwarts_sql"],
                "route": case["route"],
                "config_id": case["config_id"],
                "schema": case["schema"],
                "gold": case["gold"],
                "quwarts": case["quwarts"],
                "docetl": case["docetl"],
                "scores": {
                    "quwarts": _score(case["quwarts_metrics"]),
                    "docetl": _score(case["docetl_metrics"]),
                },
                "differences": {
                    "quwarts": case["quwarts_differences"],
                    "docetl": case["docetl_differences"],
                },
            }
        )

    quwarts = headline["quwarts"]
    docetl = headline["docetl"]
    quwarts_tokens = headline["quwarts_tokens"]["actual_spent"]
    docetl_tokens = headline["docetl_tokens"]["total_tokens"]
    payload = {
        "title": "QuWARTS case study Aug 14, 2026",
        "subtitle": (
            "A question-by-question comparison of QuWARTS and DocETL on "
            "the Player aggregation workload"
        ),
        "score_note": (
            "The displayed query score is evaluated at the 20% error level. "
            "Official accuracy is reported separately from structural coverage."
        ),
        "paper": {
            "title": (
                "DocETL: Agentic Query Rewriting and Evaluation for "
                "Complex Document Processing"
            ),
            "url": "https://www.vldb.org/pvldb/vol18/p3035-shankar.pdf",
        },
        "error_levels": ["0.2"],
        "primary_error_level": "0.2",
        "tokens": {
            "quwarts": quwarts_tokens,
            "docetl": docetl_tokens,
            "total": quwarts_tokens + docetl_tokens,
        },
        "means": {
            "quwarts": {
                "structure_f2": quwarts["structure"],
                "official_accuracy": quwarts["official_accuracy"],
                "query_score": {"0.2": quwarts["score_at_20"]},
            },
            "docetl": {
                "structure_f2": docetl["structure"],
                "official_accuracy": docetl["official_accuracy"],
                "query_score": {"0.2": docetl["score_at_20"]},
            },
        },
        "queries": queries,
    }
    OUTPUT.write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(queries)} cases to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
