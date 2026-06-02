from __future__ import annotations

from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage1.1a")


def analyze_diminishing_returns(
    scores: dict[str, float],
    *,
    thresholds: ThresholdConfig,
) -> dict:
    """Check whether a small number of probes captures most of the score range."""
    if not scores:
        return {
            "saturates_at_k": 0,
            "total_configs": 0,
            "saturated": False,
            "marginal_gains": [],
            "recommendation": "treat_greedy_as_heuristic",
        }

    sorted_vals = sorted(scores.values(), reverse=True)
    score_range = sorted_vals[0] - sorted_vals[-1]
    coverage_target = 1.0 - 1.0 / thresholds.diminishing_returns_k

    marginal_gains: list[float] = []
    prev_coverage = 0.0
    saturates_at_k = len(sorted_vals)
    found = False
    for k in range(1, len(sorted_vals) + 1):
        if score_range == 0.0:
            cum_coverage = 1.0
        else:
            cum_coverage = (sorted_vals[0] - sorted_vals[k - 1]) / score_range
        marginal_gains.append(cum_coverage - prev_coverage)
        prev_coverage = cum_coverage
        if cum_coverage >= coverage_target and not found:
            saturates_at_k = k
            found = True

    saturated = found
    if saturated and saturates_at_k <= len(sorted_vals) // 2:
        recommendation = "density_greedy_plausible"
    else:
        recommendation = "treat_greedy_as_heuristic"

    logger.info(
        "Diminishing returns: saturates_at_k=%d total=%d saturated=%s rec=%s",
        saturates_at_k, len(scores), saturated, recommendation,
    )
    return {
        "saturates_at_k": saturates_at_k,
        "total_configs": len(scores),
        "saturated": saturated,
        "marginal_gains": marginal_gains,
        "recommendation": recommendation,
    }
