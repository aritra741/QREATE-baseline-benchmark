#!/usr/bin/env python3
"""Stage 3 — compare config-selection algorithms with a fitted surrogate."""

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
from optimizer.materialize import all_config_ids
from stage3.comparison import AlgorithmResult, compare_algorithms
from surrogates.registry import build_surrogate
from thresholds.schema import default_thresholds, load_thresholds
from utils.config import load_config
from utils.logging import setup_logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 3 algorithm comparison.")
    parser.add_argument("--log-level", default=None)
    parser.add_argument(
        "--surrogate",
        default=None,
        help="Surrogate name (default: best from stage2 report, or glass_box_proxy).",
    )
    parser.add_argument("--budget", type=int, default=2)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use placeholder data if probe cache is missing.",
    )
    parser.add_argument("--results-dir", type=Path, default=None)
    return parser.parse_args()


def _determine_surrogate_name(args, results_dir: Path, logger) -> str:
    """Pick surrogate from CLI, stage2 report, or fallback."""
    if args.surrogate:
        return args.surrogate

    stage2_path = results_dir / "stage2_report.json"
    if stage2_path.exists():
        try:
            report = json.loads(stage2_path.read_text(encoding="utf-8"))
            best = report.get("best_surrogate")
            if best:
                logger.info("Using best surrogate from stage2 report: %s", best)
                return str(best)
        except Exception:
            logger.warning("Failed to read stage2 report; using fallback")

    return "glass_box_proxy"


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.stage3_algorithms")
    cfg = load_config()
    seed = int(cfg["experiment"]["seed"])

    results_dir = Path(args.results_dir) if args.results_dir else Path(cfg["paths"]["results_dir"])
    results_dir.mkdir(parents=True, exist_ok=True)

    # Load thresholds
    thresholds_path = results_dir / "optimal_thresholds.json"
    if thresholds_path.exists():
        tc = load_thresholds(thresholds_path)
    else:
        tc = default_thresholds()

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

    surrogate_name = _determine_surrogate_name(args, results_dir, logger)
    logger.info("Building surrogate: %s", surrogate_name)

    surr = build_surrogate(surrogate_name, seed=seed)
    if probe_data is not None:
        surr.fit(probe_data)

    candidate_ids = all_config_ids()
    logger.info(
        "Comparing algorithms: surrogate=%s budget=%d candidates=%d",
        surrogate_name,
        args.budget,
        len(candidate_ids),
    )

    results = compare_algorithms(surr, candidate_ids, probe_data, budget=args.budget)

    # Serialize results
    if isinstance(results, list):
        serialized = [dataclasses.asdict(r) if dataclasses.is_dataclass(r) else r for r in results]
    elif dataclasses.is_dataclass(results):
        serialized = dataclasses.asdict(results)
    else:
        serialized = results

    report = {
        "surrogate": surrogate_name,
        "budget": args.budget,
        "num_candidates": len(candidate_ids),
        "results": serialized,
    }

    out_path = results_dir / "stage3_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Saved Stage 3 report to %s", out_path)

    print()
    print("Stage 3 Algorithm Comparison:")
    print(f"  Surrogate: {surrogate_name}")
    print(f"  Budget: {args.budget}")
    print()
    entries = serialized if isinstance(serialized, list) else [serialized]
    for entry in entries:
        if isinstance(entry, dict):
            alg = entry.get("algorithm", "?")
            score = entry.get("predicted_score", entry.get("score", "?"))
            wt = entry.get("wall_time", entry.get("wall_time_seconds", "?"))
            print(f"  {alg}: predicted_score={score}  wall_time={wt}")


if __name__ == "__main__":
    main()
