#!/usr/bin/env python3
"""Harvest QuWARTS/DocETL contrast evaluations into one site-ready bundle.

Examples:
  python3 "case study/harvest_player_contrast_results.py" \\
    --quwarts-root "case study/workloads/runs/quwarts_forced_taxonomy_25pct_20260810" \\
    --groupby-root "case study/workloads/runs/quwarts_forced_taxonomy_25pct_20260809" \\
    --docetl-root "case study/workloads/runs/docetl_contrast" \\
    --output "case study/workloads/contrast_site_bundle.json"
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE = Path(__file__).resolve().parent
WORKLOADS = (
    "player_join20",
    "player_groupby20",
    "player_multiagg20",
    "player_filterjoin20",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _score_block(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        "mean_official_accuracy": evaluation.get("mean_official_accuracy"),
        "mean_structure_score": evaluation.get("mean_structure_score"),
        "mean_structure_f1_score": evaluation.get("mean_structure_f1_score"),
        "mean_cell_f1": evaluation.get("mean_cell_f1"),
        "mean_query_score": evaluation.get("mean_query_score"),
        "aggregation_query_count": evaluation.get("aggregation_query_count"),
    }


def _actual_tokens(result_dir: Path) -> int | None:
    for name in (
        "budget_ledger.json",
        "token_ledger.json",
        "run_manifest.json",
        "synthesis_manifest.json",
    ):
        path = result_dir / name
        if not path.is_file():
            continue
        payload = _read_json(path)
        for key in (
            "actual_spent",
            "actual_tokens",
            "total_tokens",
            "tokens_spent",
        ):
            if key in payload and payload[key] is not None:
                return int(payload[key])
        tokens = payload.get("tokens")
        if isinstance(tokens, dict):
            for key in ("actual_spent", "actual_tokens", "total"):
                if tokens.get(key) is not None:
                    return int(tokens[key])
        if isinstance(tokens, (int, float)):
            return int(tokens)
    return None


def _find_evaluation(root: Path, workload_id: str) -> Path | None:
    candidates = [
        root / "results" / workload_id / "evaluation.json",
        root / workload_id / "evaluation.json",
        root / workload_id / "results" / "evaluation.json",
        root / f"{workload_id}" / "evaluation.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    matches = sorted(root.rglob(f"*/{workload_id}/evaluation.json"))
    return matches[0] if matches else None


def _system_entry(root: Path | None, workload_id: str) -> dict[str, Any]:
    if root is None:
        return {"status": "missing_root"}
    evaluation_path = _find_evaluation(root, workload_id)
    if evaluation_path is None:
        return {
            "status": "missing_evaluation",
            "searched_under": str(root),
        }
    evaluation = _read_json(evaluation_path)
    result_dir = evaluation_path.parent
    return {
        "status": "ok",
        "evaluation_json": str(evaluation_path),
        "result_dir": str(result_dir),
        "scores": _score_block(evaluation),
        "tokens_actual": _actual_tokens(result_dir),
        "per_query": evaluation.get("per_query"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--quwarts-root",
        type=Path,
        default=CASE
        / "workloads"
        / "runs"
        / "quwarts_forced_taxonomy_25pct_20260810",
    )
    parser.add_argument(
        "--groupby-root",
        type=Path,
        default=CASE
        / "workloads"
        / "runs"
        / "quwarts_forced_taxonomy_25pct_20260809",
        help="Optional override when groupby lives in a different run root.",
    )
    parser.add_argument(
        "--docetl-root",
        type=Path,
        default=None,
        help="Root containing DocETL contrast evaluations.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=CASE / "workloads" / "contrast_results_summary.json",
        help="Fallback scores when an evaluation file is absent.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=CASE / "workloads" / "contrast_site_bundle.json",
    )
    args = parser.parse_args()

    summary = (
        _read_json(args.summary) if args.summary.is_file() else {"workloads": {}}
    )
    workloads: dict[str, Any] = {}
    for workload_id in WORKLOADS:
        quwarts_root = (
            args.groupby_root
            if workload_id == "player_groupby20" and args.groupby_root is not None
            else args.quwarts_root
        )
        quwarts = _system_entry(quwarts_root, workload_id)
        docetl = _system_entry(args.docetl_root, workload_id)
        fallback = summary.get("workloads", {}).get(workload_id, {})
        if quwarts.get("status") != "ok" and "quwarts" in fallback:
            quwarts = {
                "status": "summary_fallback",
                "scores": {
                    "mean_official_accuracy": fallback["quwarts"].get(
                        "mean_official_accuracy"
                    ),
                    "mean_structure_score": fallback["quwarts"].get(
                        "mean_structure_score"
                    ),
                    "mean_structure_f1_score": fallback["quwarts"].get(
                        "mean_structure_f1_score"
                    ),
                    "mean_cell_f1": fallback["quwarts"].get("mean_cell_f1"),
                    "mean_query_score": fallback["quwarts"].get(
                        "mean_query_score"
                    ),
                },
                "tokens_actual": fallback["quwarts"].get("token_budget"),
                "evaluation_json": fallback["quwarts"].get("evaluation_json"),
            }
        if docetl.get("status") != "ok" and "docetl" in fallback:
            docetl = {
                "status": "summary_fallback",
                "scores": {
                    "mean_official_accuracy": fallback["docetl"].get(
                        "mean_official_accuracy"
                    ),
                    "mean_structure_score": fallback["docetl"].get(
                        "mean_structure_score"
                    ),
                    "mean_query_score": fallback["docetl"].get(
                        "mean_query_score"
                    ),
                },
                "tokens_actual": fallback["docetl"].get("tokens"),
            }
        workloads[workload_id] = {
            "focus": fallback.get("focus"),
            "quwarts": quwarts,
            "docetl": docetl,
            "prior_quwarts": fallback.get("prior_quwarts"),
        }

    bundle = {
        "title": "Player contrast workloads",
        "subtitle": "QuWARTS vs DocETL across join, groupby, multiagg, and filterjoin",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_error_level": "0.2",
        "error_levels": ["0.01", "0.05", "0.2"],
        "score_note": summary.get(
            "score_note",
            "Main ranking score is query_score = structure × cell_f1.",
        ),
        "workloads": workloads,
        "headline": summary.get("headline"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"wrote {args.output}")
    print(
        f"{'workload':20} {'Q_acc':>7} {'D_acc':>7} {'Q_qs@.2':>8} "
        f"{'D_qs@.2':>8} {'Q_tok':>10} {'D_tok':>10}"
    )
    print("-" * 78)
    for workload_id, row in workloads.items():
        q = row["quwarts"].get("scores") or {}
        d = row["docetl"].get("scores") or {}
        q_qs = (q.get("mean_query_score") or {}).get("0.2")
        d_qs = (d.get("mean_query_score") or {}).get("0.2")
        print(
            f"{workload_id:20} "
            f"{(q.get('mean_official_accuracy') or 0):7.3f} "
            f"{(d.get('mean_official_accuracy') or 0):7.3f} "
            f"{(q_qs or 0):8.3f} "
            f"{(d_qs or 0):8.3f} "
            f"{int(row['quwarts'].get('tokens_actual') or 0):10,d} "
            f"{int(row['docetl'].get('tokens_actual') or 0):10,d}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
