#!/usr/bin/env python3
"""Post-hoc analysis utilities. Ground truth allowed here."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))

from experiments.ranking_metrics import proxy_vs_true_correlation, scores_from_config_table
from utils.config import load_config


def load_precheck_report(path: Path | None = None) -> dict:
    cfg = load_config()
    report_path = path or Path(cfg["paths"]["results_dir"]) / "precheck_Player.json"
    return json.loads(report_path.read_text(encoding="utf-8"))


def recompute_ranking_metrics(report: dict) -> dict:
    table = report["config_table"]
    true_errors = {row["config_id"]: float(row["true_error"]) for row in table}

    glass_scores = {row["config_id"]: float(row["glass_box_score"]) for row in table}
    btl_scores = {row["config_id"]: float(row["btl_score"]) for row in table}

    return {
        "glass_box_vs_true": proxy_vs_true_correlation(glass_scores, true_errors),
        "btl_vs_true": proxy_vs_true_correlation(btl_scores, true_errors),
    }


def update_precheck_report(report_path: Path | None = None) -> dict:
    cfg = load_config()
    path = report_path or Path(cfg["paths"]["results_dir"]) / "precheck_Player.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    metrics = recompute_ranking_metrics(report)
    report["glass_box_vs_true"] = metrics["glass_box_vs_true"]
    report["btl_vs_true"] = metrics["btl_vs_true"]
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute precheck ranking metrics from saved report.")
    parser.add_argument("--report", type=Path, default=None, help="Path to precheck_Player.json")
    args = parser.parse_args()

    report = update_precheck_report(args.report)
    print(json.dumps(
        {
            "glass_box_vs_true": report["glass_box_vs_true"],
            "btl_vs_true": report["btl_vs_true"],
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
