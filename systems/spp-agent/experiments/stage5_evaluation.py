#!/usr/bin/env python3
"""Stage 5 — end-to-end evaluation of the full SPP system against baselines."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path
from statistics import mean

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from agent.tools import load_agent_cache
from optimizer.materialize import all_config_ids
from stage1.characterizer import Stage1Report, load_stage1_report
from stage5.evaluation import run_stage5_evaluation
from thresholds.schema import default_thresholds, load_thresholds
from utils.config import load_config
from utils.logging import setup_logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 5 end-to-end evaluation.")
    parser.add_argument("--log-level", default=None)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use stub data for any missing upstream artifacts.",
    )
    parser.add_argument(
        "--budget-levels",
        nargs="+",
        type=int,
        default=None,
        help="Budget levels to evaluate (default: from config).",
    )
    parser.add_argument("--results-dir", type=Path, default=None)
    return parser.parse_args()


def _determine_best_surrogate(results_dir: Path, logger) -> str:
    stage2_path = results_dir / "stage2_report.json"
    if stage2_path.exists():
        try:
            report = json.loads(stage2_path.read_text(encoding="utf-8"))
            best = report.get("best_surrogate")
            if best:
                logger.info("Best surrogate from stage2: %s", best)
                return str(best)
        except Exception:
            logger.warning("Failed to read stage2 report")
    return "glass_box_proxy"


def _determine_best_algorithm(results_dir: Path, logger) -> str:
    stage3_path = results_dir / "stage3_report.json"
    if stage3_path.exists():
        try:
            report = json.loads(stage3_path.read_text(encoding="utf-8"))
            results = report.get("results", [])
            if isinstance(results, list) and results:
                # Pick algorithm with best (lowest) predicted_score or first entry
                best_entry = min(
                    results,
                    key=lambda r: float(r.get("predicted_score", r.get("score", float("inf")))),
                )
                alg = best_entry.get("algorithm")
                if alg:
                    logger.info("Best algorithm from stage3: %s", alg)
                    return str(alg)
        except Exception:
            logger.warning("Failed to read stage3 report")
    return "greedy"


def _build_stub_stage1_report() -> Stage1Report:
    _empty: dict = {"recommendation": "insufficient_data"}
    return Stage1Report(
        diminishing_returns=_empty,
        error_surface=_empty,
        module_ordering=_empty,
        interactions=_empty,
        probe_fidelity=_empty,
        clustering=_empty,
        routing_gap=_empty,
        schema_ranking=_empty,
        recommendations={
            "probe_viable": True,
            "use_nonlinear": False,
            "use_routing": False,
            "use_clustering": False,
            "schema_first": False,
            "density_greedy_viable": True,
        },
    )


def _print_summary(report: dict) -> None:
    print()
    print("STAGE 5: End-to-End Evaluation")
    print(f"  Best surrogate: {report.get('best_surrogate', '?')}")
    print(f"  Best algorithm: {report.get('best_algorithm', '?')}")
    print(f"  Budget levels: {report.get('budget_levels', [])}")
    print()

    methods = report.get("methods", [])
    if methods:
        # Header
        print(f"  {'Method':<16} {'Avg Error':>10} {'Avg Regret':>12} {'Oracle Match':>13} {'Worst Regret':>13}")
        print(f"  {'-' * 16} {'-' * 10} {'-' * 12} {'-' * 13} {'-' * 13}")
        for m in methods:
            name = m.get("method", "?")
            avg_err = m.get("avg_error", float("nan"))
            avg_reg = m.get("avg_regret", float("nan"))
            om_rate = m.get("oracle_match_rate", float("nan"))
            worst = m.get("worst_regret", float("nan"))
            print(f"  {name:<16} {avg_err:>10.4f} {avg_reg:>12.4f} {om_rate:>13.4f} {worst:>13.4f}")

    print()
    # Conclusion
    method_map = {m["method"]: m for m in methods}
    full = method_map.get("full_system", {})
    best_baseline_error = min(
        (m.get("avg_error", float("inf")) for m in methods if m.get("method") != "full_system"),
        default=float("inf"),
    )
    full_error = full.get("avg_error", float("inf"))
    if full_error <= best_baseline_error + 1e-9:
        print("  Conclusion: full_system matches or beats all baselines.")
    else:
        print("  Conclusion: full_system does not beat the best baseline on this slice.")
    print("  Scope: Player agg_only only; do not generalize beyond this pilot slice.")


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.stage5_evaluation")
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

    # Budget levels
    budget_levels = args.budget_levels or [
        int(b) for b in cfg.get("phase0", {}).get("budget_levels", [1, 2])
    ]

    # Load reward rows
    phase0_path = results_dir / "phase0_reward_table_Player.json"
    reward_rows: list[dict] = []
    if phase0_path.exists():
        report = json.loads(phase0_path.read_text(encoding="utf-8"))
        reward_rows = report.get("rows", [])
        logger.info("Loaded %d reward rows", len(reward_rows))
    elif not args.offline:
        raise FileNotFoundError(
            f"Phase 0 reward table not found at {phase0_path}. "
            "Run phase0_reward_table.py first, or use --offline."
        )

    # Load probe data
    cache_name = cfg.get("phase1", {}).get("probe_context_cache", "phase1_agg_only_probe_context.json")
    cache_path = results_dir / cache_name
    probe_data = None
    if cache_path.exists():
        try:
            toolkit = load_agent_cache(cache_path)
            probe_data = toolkit.probe_data if toolkit else None
        except Exception:
            logger.warning("Failed to load agent cache from %s", cache_path)

    # Load stage1 report
    stage1_path = results_dir / "stage1_report.json"
    if stage1_path.exists():
        try:
            stage1_report = load_stage1_report(stage1_path)
        except Exception:
            logger.warning("Failed to load stage1 report; using stub")
            stage1_report = _build_stub_stage1_report()
    else:
        stage1_report = _build_stub_stage1_report()

    best_surrogate = _determine_best_surrogate(results_dir, logger)
    best_algorithm = _determine_best_algorithm(results_dir, logger)
    candidate_ids = all_config_ids()

    logger.info(
        "Running Stage 5 evaluation: best_surrogate=%s best_algorithm=%s budgets=%s candidates=%d",
        best_surrogate,
        best_algorithm,
        budget_levels,
        len(candidate_ids),
    )

    report = run_stage5_evaluation(
        reward_rows=reward_rows,
        probe_data=probe_data,
        thresholds=tc,
        stage1_report=stage1_report,
        best_surrogate=best_surrogate,
        best_algorithm=best_algorithm,
        budget_levels=budget_levels,
        candidate_ids=candidate_ids,
        seed=seed,
    )

    out_path = results_dir / "stage5_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Saved Stage 5 report to %s", out_path)

    _print_summary(report)


if __name__ == "__main__":
    main()
