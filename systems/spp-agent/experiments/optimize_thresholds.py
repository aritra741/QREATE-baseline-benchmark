#!/usr/bin/env python3
"""Optimize ThresholdConfig from probe data (no ground-truth access).

The optimizer uses LOO Spearman rho computed from deployment-visible probe
signals (glass-box composites and BTL scores from the LLM judge).  It does
not read true_spp_error or any ground-truth query evaluation results.
"""

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

from thresholds.optimizer import optimize_thresholds
from thresholds.schema import default_thresholds
from data.dataset_registry import (
    normalize_dataset_name,
    phase1_probe_cache_path,
    results_dir_for_dataset,
)
from utils.config import load_config
from utils.logging import setup_logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Optimize ThresholdConfig from probe data (no ground-truth access)."
    )
    parser.add_argument("--dataset", default="Player")
    parser.add_argument("--log-level", default=None)
    parser.add_argument("--n-trials", type=int, default=100)
    parser.add_argument(
        "--cache",
        type=Path,
        default=None,
        help="Path to agent probe cache JSON (phase1_agg_only_probe_context.json).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="If no probe cache found, build a synthetic ProbeData stub for smoke-test.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
    )
    return parser.parse_args()


def _synthetic_probe_data(seed: int):
    """Build a minimal synthetic ProbeData for offline smoke-testing.

    Contains realistic config IDs, glass-box scores, and BTL scores but no
    ground-truth error.  Used only when no real probe cache is available.
    """
    import random
    from optimizer.config_space import generate_config_space
    from optimizer.probing import ProbeData

    rng = random.Random(seed)
    all_configs = generate_config_space()
    rng.shuffle(all_configs)
    probe_configs = all_configs[:8]

    config_ids = [c.config_id for c in probe_configs]
    glass_box = {cid: round(rng.uniform(0.4, 0.95), 4) for cid in config_ids}
    btl_scores = {cid: round(rng.uniform(0.5, 2.0), 4) for cid in config_ids}

    # Minimal pairwise comparisons (spanning tree)
    comparisons = []
    for i in range(1, len(config_ids)):
        winner, loser = (config_ids[i - 1], config_ids[i]) if rng.random() < 0.5 else (config_ids[i], config_ids[i - 1])
        comparisons.append({"winner": winner, "loser": loser, "reasoning": "synthetic"})

    return ProbeData(
        config_ids=config_ids,
        configs={c.config_id: c for c in probe_configs},
        tier1_signals={cid: {"glass_box_composite": glass_box[cid]} for cid in config_ids},
        glass_box_composites=glass_box,
        pairwise_comparisons=comparisons,
        btl_scores=btl_scores,
        databases={},
        total_cost=5000.0,
        btl_report={},
    )


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.optimize_thresholds")
    cfg = load_config()
    dataset = normalize_dataset_name(args.dataset)
    seed = int(cfg["experiment"]["seed"])
    threshold_cfg = cfg.get("threshold_optimization", {})

    results_dir = (
        Path(args.results_dir) if args.results_dir else results_dir_for_dataset(dataset)
    )
    results_dir.mkdir(parents=True, exist_ok=True)

    # Resolve probe cache path
    cache_path = args.cache or phase1_probe_cache_path(results_dir, dataset)

    if cache_path.exists():
        from agent.tools import load_agent_cache
        logger.info("Loading probe data from cache: %s", cache_path)
        toolkit = load_agent_cache(cache_path)
        probe_data = toolkit.probe_data
        logger.info(
            "Probe data: %d configs, %d pairwise comparisons",
            len(probe_data.config_ids),
            len(probe_data.pairwise_comparisons),
        )
    elif args.offline:
        logger.warning(
            "Probe cache not found at %s; using synthetic probe data for smoke-test", cache_path
        )
        probe_data = _synthetic_probe_data(seed)
        logger.info("Synthetic probe data: %d configs", len(probe_data.config_ids))
    else:
        raise FileNotFoundError(
            f"Probe cache not found at {cache_path}. "
            "Run phase1_comparison.py --force-probe first, or use --offline."
        )

    n_trials = args.n_trials or int(threshold_cfg.get("n_trials", 100))
    save_path = results_dir / threshold_cfg.get("optimal_thresholds_file", "optimal_thresholds.json")

    logger.info(
        "Optimizing thresholds from probe signals only (no ground truth): "
        "n_trials=%d save_path=%s",
        n_trials,
        save_path,
    )
    optimized = optimize_thresholds(
        probe_data,
        n_trials=n_trials,
        seed=seed,
        save_path=save_path,
    )

    print()
    print("Optimized ThresholdConfig (learned from probe signals, no ground truth):")
    print(json.dumps(dataclasses.asdict(optimized), indent=2))
    logger.info("Saved optimized thresholds to %s", save_path)


if __name__ == "__main__":
    main()
