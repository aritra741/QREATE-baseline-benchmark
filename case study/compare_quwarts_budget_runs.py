#!/usr/bin/env python3
"""Compare QuWARTS contrast evaluations across token-budget settings.

Default: 25% DocETL-budget runs vs a new 50% DocETL-budget root.

Example:
  python3 "case study/compare_quwarts_budget_runs.py" \\
    --baseline-root "case study/workloads/runs/quwarts_controlled_25pct_20260811" \\
    --new-root "case study/workloads/runs/quwarts_controlled_50pct_20260811" \\
    --output "case study/workloads/runs/quwarts_controlled_50pct_20260811/budget_compare.json"
"""

from __future__ import annotations

import argparse
import csv
import json
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
DEFAULT_BASELINE = {
    "player_join20": CASE
    / "workloads"
    / "runs"
    / "quwarts_forced_taxonomy_25pct_20260810"
    / "results"
    / "player_join20"
    / "evaluation.json",
    "player_groupby20": CASE
    / "workloads"
    / "runs"
    / "quwarts_forced_taxonomy_25pct_20260809"
    / "results"
    / "player_groupby20"
    / "evaluation.json",
    "player_multiagg20": CASE
    / "workloads"
    / "runs"
    / "quwarts_forced_taxonomy_25pct_20260810"
    / "results"
    / "player_multiagg20"
    / "evaluation.json",
    "player_filterjoin20": CASE
    / "workloads"
    / "runs"
    / "quwarts_forced_taxonomy_25pct_20260810"
    / "results"
    / "player_filterjoin20"
    / "evaluation.json",
}
DOCETL_TOKENS = {
    "player_join20": 28_462_525,
    "player_groupby20": 20_540_522,
    "player_multiagg20": 22_680_169,
    "player_filterjoin20": 24_456_613,
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _metrics(report: dict[str, Any]) -> dict[str, Any]:
    qs = report.get("mean_query_score") or {}
    return {
        "mean_official_accuracy": report.get("mean_official_accuracy"),
        "mean_structure_score": report.get("mean_structure_score"),
        "mean_query_score_0.2": qs.get("0.2") if isinstance(qs, dict) else None,
        "mean_cell_f1_0.2": (report.get("mean_cell_f1") or {}).get("0.2"),
        "construction_tokens": report.get("construction_tokens"),
        "total_token_budget": report.get("total_token_budget"),
        "unused_tokens": report.get("unused_tokens"),
    }


def _delta(new: Any, old: Any) -> Any:
    if new is None or old is None:
        return None
    return float(new) - float(old)


def _find_evaluation(root: Path, workload_id: str) -> Path:
    path = root / "results" / workload_id / "evaluation.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--new-root", type=Path, required=True)
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated workload ids to compare (default: all four).",
    )
    parser.add_argument(
        "--baseline-root",
        type=Path,
        default=None,
        help=(
            "Root containing results/<workload>/evaluation.json for the "
            "baseline budget. Defaults to the hardcoded prior 25%% paths."
        ),
    )
    parser.add_argument(
        "--baseline-label",
        default="25pct",
        help="Label for the previous budget setting.",
    )
    parser.add_argument(
        "--new-label",
        default="50pct",
        help="Label for the new budget setting.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSON report path (default: <new-root>/budget_compare.json).",
    )
    args = parser.parse_args()
    new_root = args.new_root
    if not new_root.is_absolute():
        new_root = (ROOT / new_root).resolve()
    baseline_root = args.baseline_root
    if baseline_root is not None and not baseline_root.is_absolute():
        baseline_root = (ROOT / baseline_root).resolve()
    output = args.output or (new_root / "budget_compare.json")
    if not output.is_absolute():
        output = (ROOT / output).resolve()
    selected_workloads = (
        tuple(
            workload_id.strip()
            for workload_id in args.only.split(",")
            if workload_id.strip()
        )
        if args.only
        else WORKLOADS
    )
    unknown = sorted(set(selected_workloads) - set(WORKLOADS))
    if unknown:
        raise ValueError(f"unknown workload ids: {', '.join(unknown)}")

    rows: list[dict[str, Any]] = []
    for workload_id in selected_workloads:
        if baseline_root is not None:
            baseline_path = _find_evaluation(baseline_root, workload_id)
        else:
            baseline_path = DEFAULT_BASELINE[workload_id]
        new_path = _find_evaluation(new_root, workload_id)
        baseline = _metrics(_read(baseline_path))
        current = _metrics(_read(new_path))
        docetl = DOCETL_TOKENS[workload_id]
        row = {
            "workload_id": workload_id,
            "docetl_tokens": docetl,
            f"{args.baseline_label}_budget": int(docetl * 0.25),
            f"{args.new_label}_budget": docetl // 2,
            args.baseline_label: baseline,
            args.new_label: current,
            "delta": {
                "mean_official_accuracy": _delta(
                    current["mean_official_accuracy"],
                    baseline["mean_official_accuracy"],
                ),
                "mean_structure_score": _delta(
                    current["mean_structure_score"],
                    baseline["mean_structure_score"],
                ),
                "mean_query_score_0.2": _delta(
                    current["mean_query_score_0.2"],
                    baseline["mean_query_score_0.2"],
                ),
                "mean_cell_f1_0.2": _delta(
                    current["mean_cell_f1_0.2"],
                    baseline["mean_cell_f1_0.2"],
                ),
                "construction_tokens": _delta(
                    current["construction_tokens"],
                    baseline["construction_tokens"],
                ),
            },
            "paths": {
                args.baseline_label: str(baseline_path),
                args.new_label: str(new_path),
            },
        }
        rows.append(row)

    report = {
        "title": f"QuWARTS budget comparison: {args.baseline_label} vs {args.new_label}",
        "baseline_label": args.baseline_label,
        "new_label": args.new_label,
        "baseline_root": None if baseline_root is None else str(baseline_root),
        "new_root": str(new_root),
        "workloads": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "workload_id",
                "docetl_tokens",
                f"{args.baseline_label}_acc",
                f"{args.new_label}_acc",
                "delta_acc",
                f"{args.baseline_label}_structure",
                f"{args.new_label}_structure",
                "delta_structure",
                f"{args.baseline_label}_qs@0.2",
                f"{args.new_label}_qs@0.2",
                "delta_qs@0.2",
                f"{args.baseline_label}_tokens",
                f"{args.new_label}_tokens",
            ],
        )
        writer.writeheader()
        for row in rows:
            baseline = row[args.baseline_label]
            current = row[args.new_label]
            delta = row["delta"]
            writer.writerow(
                {
                    "workload_id": row["workload_id"],
                    "docetl_tokens": row["docetl_tokens"],
                    f"{args.baseline_label}_acc": baseline["mean_official_accuracy"],
                    f"{args.new_label}_acc": current["mean_official_accuracy"],
                    "delta_acc": delta["mean_official_accuracy"],
                    f"{args.baseline_label}_structure": baseline[
                        "mean_structure_score"
                    ],
                    f"{args.new_label}_structure": current["mean_structure_score"],
                    "delta_structure": delta["mean_structure_score"],
                    f"{args.baseline_label}_qs@0.2": baseline["mean_query_score_0.2"],
                    f"{args.new_label}_qs@0.2": current["mean_query_score_0.2"],
                    "delta_qs@0.2": delta["mean_query_score_0.2"],
                    f"{args.baseline_label}_tokens": baseline["construction_tokens"],
                    f"{args.new_label}_tokens": current["construction_tokens"],
                }
            )

    print(f"{'workload':22} {'acc25':>8} {'acc50':>8} {'d_acc':>8} {'qs25':>8} {'qs50':>8} {'d_qs':>8}")
    print("-" * 80)
    for row in rows:
        b = row[args.baseline_label]
        n = row[args.new_label]
        d = row["delta"]
        print(
            f"{row['workload_id']:22} "
            f"{b['mean_official_accuracy']:>8.3f} "
            f"{n['mean_official_accuracy']:>8.3f} "
            f"{d['mean_official_accuracy']:>+8.3f} "
            f"{b['mean_query_score_0.2']:>8.3f} "
            f"{n['mean_query_score_0.2']:>8.3f} "
            f"{d['mean_query_score_0.2']:>+8.3f}"
        )
    print(f"\nWrote {output}")
    print(f"Wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
