#!/usr/bin/env python3
"""Stage 2 — compare surrogates and select the best one."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from agent.tools import load_agent_cache
from stage2.surrogate_comparison import SurrogateComparisonResult, compare_surrogates, select_best_surrogate
from surrogates.registry import ALL_SURROGATES
from thresholds.schema import default_thresholds, load_thresholds
from utils.config import load_config
from utils.logging import setup_logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 2 surrogate comparison.")
    parser.add_argument("--log-level", default=None)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use placeholder data if probe cache is missing.",
    )
    parser.add_argument("--results-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.stage2_surrogates")
    cfg = load_config()

    results_dir = Path(args.results_dir) if args.results_dir else Path(cfg["paths"]["results_dir"])
    results_dir.mkdir(parents=True, exist_ok=True)

    # Load thresholds
    thresholds_path = results_dir / "optimal_thresholds.json"
    if thresholds_path.exists():
        tc = load_thresholds(thresholds_path)
        logger.info("Loaded optimized thresholds from %s", thresholds_path)
    else:
        tc = default_thresholds()
        logger.info("Using default thresholds")

    # Load true errors from Phase 0
    phase0_path = results_dir / "phase0_reward_table_Player.json"
    true_errors: dict[str, float] = {}
    if phase0_path.exists():
        report = json.loads(phase0_path.read_text(encoding="utf-8"))
        for row in report.get("rows", []):
            key = str(row.get("surrogate", ""))
            true_errors[key] = float(row.get("true_spp_error", float("nan")))

    # Load probe data
    cache_name = cfg.get("phase1", {}).get("probe_context_cache", "phase1_agg_only_probe_context.json")
    cache_path = results_dir / cache_name
    probe_data = None
    if cache_path.exists():
        try:
            toolkit = load_agent_cache(cache_path)
            probe_data = toolkit.probe_data if toolkit else None
            logger.info("Loaded probe data from %s", cache_path)
        except Exception:
            logger.warning("Failed to load agent cache from %s", cache_path)

    if probe_data is None and not args.offline:
        raise RuntimeError(
            f"No probe data at {cache_path}. Run phase1_comparison.py first, or use --offline."
        )

    surrogate_names = list(ALL_SURROGATES.keys())
    logger.info("Comparing %d surrogates: %s", len(surrogate_names), surrogate_names)

    result = compare_surrogates(
        probe_data,
        surrogate_names,
        thresholds=tc,
        true_errors=true_errors,
    )

    out_path = results_dir / "stage2_report.json"
    out_path.write_text(
        json.dumps(dataclasses.asdict(result), indent=2),
        encoding="utf-8",
    )
    logger.info("Saved Stage 2 report to %s", out_path)

    best = select_best_surrogate(result)
    print()
    print("Stage 2 Surrogate Comparison:")
    print(f"  Best surrogate: {best}")
    print()
    print("Ranking:")
    result_dict = dataclasses.asdict(result)
    rankings = result_dict.get("rankings", result_dict.get("surrogate_rankings", []))
    if isinstance(rankings, list):
        for i, entry in enumerate(rankings, 1):
            name = entry.get("surrogate", entry.get("name", "?"))
            score = entry.get("score", entry.get("correlation", "?"))
            print(f"  {i}. {name}: {score}")
    elif isinstance(rankings, dict):
        for name, score in sorted(rankings.items(), key=lambda x: x[1], reverse=True):
            print(f"  {name}: {score}")


if __name__ == "__main__":
    main()
