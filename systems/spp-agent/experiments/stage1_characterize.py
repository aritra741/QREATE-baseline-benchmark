#!/usr/bin/env python3
"""Stage 1 — run instance characterization and save report."""

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
from stage1.characterizer import Stage1Report, characterize, save_stage1_report
from thresholds.schema import default_thresholds, load_thresholds
from utils.config import load_config
from utils.logging import setup_logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 1 instance characterization.")
    parser.add_argument("--log-level", default=None)
    parser.add_argument("--dataset", default="Player")
    parser.add_argument("--slice", default="agg_only")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="If no cache, build a minimal stub Stage1Report.",
    )
    parser.add_argument("--results-dir", type=Path, default=None)
    return parser.parse_args()


def _build_stub_stage1_report(dataset: str, slice_name: str) -> Stage1Report:
    """Minimal placeholder when running offline without cached probe data."""
    return Stage1Report(
        dataset=dataset,
        slice_name=slice_name,
        analyses={
            "interaction_ratio": {"value": 0.0, "note": "offline_stub"},
            "diminishing_returns": {"k": 4, "note": "offline_stub"},
            "surrogate_viability": {"rho": 0.0, "note": "offline_stub"},
            "bakeoff_warranted": {"rho": 0.0, "note": "offline_stub"},
            "cluster_purity": {"purity": 0.0, "note": "offline_stub"},
            "routing_gap": {"gap": 0.0, "note": "offline_stub"},
            "schema_rank": {"rho": 0.0, "note": "offline_stub"},
        },
        recommendations=[],
    )


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.stage1_characterize")
    cfg = load_config()
    seed = int(cfg["experiment"]["seed"])

    results_dir = Path(args.results_dir) if args.results_dir else Path(cfg["paths"]["results_dir"])
    results_dir.mkdir(parents=True, exist_ok=True)

    # Load thresholds (optimized if available, else defaults)
    thresholds_path = results_dir / "optimal_thresholds.json"
    if thresholds_path.exists():
        tc = load_thresholds(thresholds_path)
        logger.info("Loaded optimized thresholds from %s", thresholds_path)
    else:
        tc = default_thresholds()
        logger.info("Using default thresholds (no optimal_thresholds.json found)")

    # Load reward rows for true_errors
    phase0_path = results_dir / "phase0_reward_table_Player.json"
    reward_rows: list[dict] = []
    true_errors: dict[str, float] = {}
    if phase0_path.exists():
        report = json.loads(phase0_path.read_text(encoding="utf-8"))
        reward_rows = report.get("rows", [])
        for row in reward_rows:
            key = str(row.get("surrogate", ""))
            true_errors[key] = float(row.get("true_spp_error", float("nan")))
        logger.info("Loaded %d reward rows for true_errors", len(reward_rows))

    # Load probe data from agent cache
    cache_name = cfg.get("phase1", {}).get("probe_context_cache", "phase1_agg_only_probe_context.json")
    cache_path = results_dir / cache_name
    probe_data = None
    toolkit = None
    if cache_path.exists():
        try:
            toolkit = load_agent_cache(cache_path)
            probe_data = toolkit.probe_data if toolkit else None
            logger.info("Loaded probe data from %s", cache_path)
        except Exception:
            logger.warning("Failed to load agent cache from %s", cache_path)

    if probe_data is None and args.offline:
        logger.warning("No probe data available; building stub Stage1Report")
        report_obj = _build_stub_stage1_report(args.dataset, args.slice)
    elif probe_data is None:
        raise RuntimeError(
            f"No probe data at {cache_path}. Run phase1_comparison.py first, or use --offline."
        )
    else:
        from data.instance_builder import build_instance
        from pipeline.schema import load_fixed_schema

        instance = build_instance(args.dataset, include_ground_truth=False)
        schema = load_fixed_schema(args.dataset)
        queries = instance.queries
        report_obj = characterize(
            probe_data,
            queries=queries,
            schema=schema,
            thresholds=tc,
            true_errors=true_errors if not args.offline else None,
            seed=seed,
        )

    out_path = results_dir / "stage1_report.json"
    save_stage1_report(report_obj, out_path)
    logger.info("Saved Stage 1 report to %s", out_path)

    print()
    print("Stage 1 Characterization Report:")
    print(json.dumps(dataclasses.asdict(report_obj), indent=2))

    if hasattr(report_obj, "recommendations") and report_obj.recommendations:
        print()
        print("Recommendations:")
        for rec in report_obj.recommendations:
            print(f"  - {rec}")


if __name__ == "__main__":
    main()
