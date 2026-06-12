from __future__ import annotations

from scipy.stats import kendalltau

from surrogates.registry import build_surrogate
from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage1.1g")

_ROUTING_SURROGATES = [
    "direct_probe_ranking",
    "glass_box_proxy",
    "llm_judge_btl",
    "rf_proxy_glass",
]


def analyze_routing_gap(
    probe_data,
    *,
    thresholds: ThresholdConfig,
    reward_rows: list[dict] | None = None,
) -> dict:
    """Measure surrogate disagreement as a deployment-visible routing signal."""
    _ = reward_rows  # accepted for signature compat; never read

    config_ids = list(probe_data.config_ids)
    if len(config_ids) < 2:
        return {
            "surrogate_rankings": {},
            "pairwise_kendall_tau": {},
            "mean_disagreement": None,
            "disagreement_above_threshold": None,
            "recommendation": "cannot_estimate",
        }

    surrogate_rankings: dict[str, list[str]] = {}
    for name in _ROUTING_SURROGATES:
        if name == "llm_judge_btl" and not probe_data.btl_scores:
            continue
        try:
            surrogate = build_surrogate(name, seed=42)
            surrogate.fit(probe_data)
            surrogate_rankings[name] = surrogate.rank(config_ids)
        except Exception as exc:
            logger.warning("Routing gap: surrogate %s failed: %s", name, exc)

    names = list(surrogate_rankings.keys())
    pairwise_tau: dict[str, float] = {}
    taus: list[float] = []

    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            rank_a = {cid: idx for idx, cid in enumerate(surrogate_rankings[a])}
            rank_b = {cid: idx for idx, cid in enumerate(surrogate_rankings[b])}
            x = [rank_a[cid] for cid in config_ids]
            y = [rank_b[cid] for cid in config_ids]
            tau, _ = kendalltau(x, y)
            if tau == tau:
                pairwise_tau[f"{a}_vs_{b}"] = float(tau)
                taus.append(abs(float(tau)))

    if not taus:
        mean_disagreement = None
        above = None
        recommendation = "cannot_estimate"
    else:
        mean_disagreement = 1.0 - float(sum(taus) / len(taus))
        above = mean_disagreement > thresholds.surrogate_disagreement_threshold
        recommendation = "co_optimize_routing" if above else "routing_secondary"

    logger.info(
        "Routing disagreement: mean=%.4f threshold=%.4f above=%s rec=%s",
        mean_disagreement or 0.0,
        thresholds.surrogate_disagreement_threshold,
        above,
        recommendation,
    )

    return {
        "surrogate_rankings": surrogate_rankings,
        "pairwise_kendall_tau": pairwise_tau,
        "mean_disagreement": mean_disagreement,
        "disagreement_above_threshold": above,
        "recommendation": recommendation,
    }
