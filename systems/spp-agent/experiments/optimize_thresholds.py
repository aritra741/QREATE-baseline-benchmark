#!/usr/bin/env python3
"""Optimize ThresholdConfig using Phase 0 reward table."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from thresholds.optimizer import optimize_thresholds
from thresholds.schema import default_thresholds
from utils.config import load_config
from utils.logging import setup_logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize thresholds from Phase 0 reward table.")
    parser.add_argument("--log-level", default=None)
    parser.add_argument("--n-trials", type=int, default=100)
    parser.add_argument(
        "--phase0",
        type=Path,
        default=None,
        help="Path to Phase 0 reward table JSON.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="If no reward table found, generate synthetic rows for smoke-test mode.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help="Override results output directory.",
    )
    return parser.parse_args()


def _generate_synthetic_rows(seed: int) -> list[dict]:
    """Build synthetic reward rows for offline smoke-test."""
    rng = random.Random(seed)
    surrogates = [
        "random_ranking",
        "direct_probe_ranking",
        "glass_box_proxy",
        "llm_judge_btl",
        "linear_proxy_glass",
        "rf_proxy_glass",
    ]
    rows: list[dict] = []
    for budget in (1, 2):
        for surrogate in surrogates:
            rows.append(
                {
                    "dataset": "Player",
                    "slice": "agg_only",
                    "budget": budget,
                    "surrogate": surrogate,
                    "true_spp_error": round(rng.uniform(0.05, 0.60), 4),
                    "num_probe_configs": 8,
                    "selected_configs": [f"synthetic_config_{i}" for i in range(budget)],
                }
            )
    return rows


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.optimize_thresholds")
    cfg = load_config()
    seed = int(cfg["experiment"]["seed"])
    threshold_cfg = cfg.get("threshold_optimization", {})

    results_dir = Path(args.results_dir) if args.results_dir else Path(cfg["paths"]["results_dir"])
    results_dir.mkdir(parents=True, exist_ok=True)

    phase0_path = args.phase0 or results_dir / "phase0_reward_table_Player.json"

    if phase0_path.exists():
        report = json.loads(phase0_path.read_text(encoding="utf-8"))
        reward_rows = report.get("rows", [])
        logger.info("Loaded %d reward rows from %s", len(reward_rows), phase0_path)
    elif args.offline:
        logger.warning("Phase 0 reward table not found; generating synthetic rows for smoke-test")
        reward_rows = _generate_synthetic_rows(seed)
    else:
        raise FileNotFoundError(
            f"Phase 0 reward table not found at {phase0_path}. "
            "Run phase0_reward_table.py first, or use --offline for synthetic rows."
        )

    n_trials = args.n_trials or int(threshold_cfg.get("n_trials", 100))
    save_path = results_dir / threshold_cfg.get("optimal_thresholds_file", "optimal_thresholds.json")

    logger.info("Optimizing thresholds: n_trials=%d save_path=%s", n_trials, save_path)
    optimized = optimize_thresholds(
        reward_rows,
        n_trials=n_trials,
        seed=seed,
        save_path=save_path,
    )

    import dataclasses

    print()
    print("Optimized ThresholdConfig:")
    print(json.dumps(dataclasses.asdict(optimized), indent=2))
    logger.info("Saved optimized thresholds to %s", save_path)


if __name__ == "__main__":
    main()
