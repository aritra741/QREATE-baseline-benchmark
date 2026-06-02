from __future__ import annotations

from collections import defaultdict

from optimizer.probing import ProbeData
from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage1.1g")


def _score_spread(scores: dict[str, float]) -> float:
    if not scores:
        return 0.0
    vals = list(scores.values())
    return float(max(vals) - min(vals))


def _practical_select(glass_box_spread: float, btl_spread: float) -> str:
    """Mirror rule_based_select logic from agent/tools.py."""
    if btl_spread > 0:
        return "llm_judge_btl"
    if glass_box_spread > 0.01:
        return "rf_proxy_glass"
    return "direct_probe_ranking"


def analyze_routing_gap(
    probe_data: ProbeData,
    *,
    thresholds: ThresholdConfig,
    reward_rows: list[dict] | None = None,
) -> dict:
    """Measure gap between oracle routing and practical heuristic routing."""
    if not reward_rows:
        return {
            "oracle_errors": {},
            "practical_errors": {},
            "mean_gap": None,
            "gap_below_threshold": None,
            "recommendation": "cannot_estimate",
        }

    by_budget: dict[str, list[dict]] = defaultdict(list)
    for row in reward_rows:
        by_budget[str(row["budget"])].append(row)

    glass_spread = _score_spread(probe_data.glass_box_composites)
    btl_spread = _score_spread(probe_data.btl_scores)
    practical_choice = _practical_select(glass_spread, btl_spread)

    oracle_errors: dict[str, float] = {}
    practical_errors: dict[str, float] = {}

    for budget_key, group in by_budget.items():
        oracle_errors[budget_key] = min(r["true_spp_error"] for r in group)

        matched = [r for r in group if r.get("surrogate") == practical_choice]
        if matched:
            practical_errors[budget_key] = min(r["true_spp_error"] for r in matched)
        else:
            practical_errors[budget_key] = min(r["true_spp_error"] for r in group)

    common_budgets = set(oracle_errors) & set(practical_errors)
    if not common_budgets:
        return {
            "oracle_errors": oracle_errors,
            "practical_errors": practical_errors,
            "mean_gap": None,
            "gap_below_threshold": None,
            "recommendation": "cannot_estimate",
        }

    mean_gap = sum(
        abs(practical_errors[b] - oracle_errors[b]) for b in common_budgets
    ) / len(common_budgets)

    gap_below = mean_gap < thresholds.routing_gap
    recommendation = "routing_secondary" if gap_below else "co_optimize_routing"

    logger.info(
        "Routing gap: mean_gap=%.4f threshold=%.4f below=%s rec=%s",
        mean_gap, thresholds.routing_gap, gap_below, recommendation,
    )
    return {
        "oracle_errors": oracle_errors,
        "practical_errors": practical_errors,
        "mean_gap": mean_gap,
        "gap_below_threshold": gap_below,
        "recommendation": recommendation,
    }
