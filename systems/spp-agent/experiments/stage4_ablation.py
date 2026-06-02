#!/usr/bin/env python3
"""Stage 4 — ablation study: measure contribution of each system component."""

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
from stage4.ablation import AblationResult, describe_ablation_components, run_ablation
from thresholds.schema import default_thresholds, load_thresholds
from utils.config import load_config
from utils.logging import setup_logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 4 ablation study.")
    parser.add_argument("--log-level", default=None)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use heuristic component errors if real data is missing.",
    )
    parser.add_argument("--results-dir", type=Path, default=None)
    return parser.parse_args()


def _determine_best_surrogate(results_dir: Path, logger) -> str:
    """Read stage2 report for best surrogate, or fall back."""
    stage2_path = results_dir / "stage2_report.json"
    if stage2_path.exists():
        try:
            report = json.loads(stage2_path.read_text(encoding="utf-8"))
            best = report.get("best_surrogate")
            if best:
                return str(best)
        except Exception:
            logger.warning("Failed to read stage2 report")
    return "glass_box_proxy"


def _lookup_error_for_surrogate(
    reward_rows: list[dict],
    surrogate_name: str,
    budget: int,
) -> float:
    """Find the true_spp_error for a given surrogate at a budget."""
    for row in reward_rows:
        if (
            str(row.get("surrogate", "")) == surrogate_name
            and int(row.get("budget", -1)) == budget
        ):
            return float(row.get("true_spp_error", float("nan")))
    return float("nan")


def main() -> None:
    args = _parse_args()
    if args.log_level:
        os.environ["SPP_LOG_LEVEL"] = args.log_level.upper()

    logger = setup_logger("spp.stage4_ablation")
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

    # Load reward rows from Phase 0
    phase0_path = results_dir / "phase0_reward_table_Player.json"
    reward_rows: list[dict] = []
    if phase0_path.exists():
        report = json.loads(phase0_path.read_text(encoding="utf-8"))
        reward_rows = report.get("rows", [])
        logger.info("Loaded %d reward rows", len(reward_rows))

    best_surrogate = _determine_best_surrogate(results_dir, logger)
    full_system_error = _lookup_error_for_surrogate(reward_rows, best_surrogate, budget=1)
    random_error = _lookup_error_for_surrogate(reward_rows, "random_ranking", budget=1)
    direct_probe_error = _lookup_error_for_surrogate(reward_rows, "direct_probe_ranking", budget=1)

    logger.info(
        "full_system_error=%.4f random_error=%.4f direct_probe_error=%.4f",
        full_system_error,
        random_error,
        direct_probe_error,
    )

    # Build component_errors heuristic
    components = describe_ablation_components()
    component_errors: dict[str, float] = {}
    for component in components:
        if component == "surrogate":
            # Ablating surrogate → fall back to random ranking error
            component_errors[component] = random_error
        elif component == "recalibration":
            # Ablating recalibration → use direct probe ranking error
            component_errors[component] = direct_probe_error
        else:
            # Default: use random ranking error as offline placeholder
            component_errors[component] = random_error

    logger.info("Component errors: %s", component_errors)

    result = run_ablation(
        full_system_error=full_system_error,
        component_errors=component_errors,
        thresholds=tc,
    )

    # Serialize
    if dataclasses.is_dataclass(result):
        serialized = dataclasses.asdict(result)
    elif isinstance(result, dict):
        serialized = result
    else:
        serialized = {"result": str(result)}

    out_path = results_dir / "stage4_report.json"
    out_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    logger.info("Saved Stage 4 report to %s", out_path)

    print()
    print("Stage 4 Ablation Study:")
    print(f"  Full system error ({best_surrogate}): {full_system_error:.4f}")
    print()
    ablation_entries = serialized.get("components", serialized.get("entries", []))
    if isinstance(ablation_entries, list):
        for entry in ablation_entries:
            if isinstance(entry, dict):
                comp = entry.get("component", "?")
                delta = entry.get("delta", entry.get("relative_gain", "?"))
                retained = entry.get("retained", "?")
                print(f"  {comp}: delta={delta}  retained={retained}")
    elif isinstance(ablation_entries, dict):
        for comp, info in ablation_entries.items():
            if isinstance(info, dict):
                delta = info.get("delta", "?")
                retained = info.get("retained", "?")
                print(f"  {comp}: delta={delta}  retained={retained}")


if __name__ == "__main__":
    main()
