from __future__ import annotations

import numpy as np
from scipy.stats import spearmanr

from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage1.1e")


def analyze_probe_fidelity(
    proxy_scores: dict[str, float],
    true_errors: dict[str, float],
    *,
    thresholds: ThresholdConfig,
    top_k: int = 3,
) -> dict:
    """Assess how well deployment-visible proxy scores predict true errors."""
    common = sorted(set(proxy_scores) & set(true_errors))
    if len(common) < 2:
        return {
            "spearman_rho": 0.0,
            "top_k_recall": 0.0,
            "best_proxy_regret": 0.0,
            "recommendation": "improve_sampling_or_skip_probes",
        }

    x = np.array([proxy_scores[cid] for cid in common])
    y = np.array([-true_errors[cid] for cid in common])  # higher proxy ↔ lower error
    rho = float(spearmanr(x, y).correlation)

    k = min(top_k, len(common))
    true_top_k = set(sorted(common, key=lambda c: true_errors[c])[:k])
    proxy_top_k = set(sorted(common, key=lambda c: proxy_scores[c], reverse=True)[:k])
    top_k_recall = len(true_top_k & proxy_top_k) / k

    best_proxy_cid = max(common, key=lambda c: proxy_scores[c])
    oracle_cid = min(common, key=lambda c: true_errors[c])
    best_proxy_regret = true_errors[best_proxy_cid] - true_errors[oracle_cid]

    if rho >= thresholds.rho_viable:
        recommendation = "surrogate_viable"
    elif rho >= thresholds.rho_bakeoff:
        recommendation = "run_bakeoff"
    else:
        recommendation = "improve_sampling_or_skip_probes"

    logger.info(
        "Probe fidelity: rho=%.4f top_%d_recall=%.2f regret=%.4f rec=%s",
        rho, top_k, top_k_recall, best_proxy_regret, recommendation,
    )
    return {
        "spearman_rho": rho,
        "top_k_recall": top_k_recall,
        "best_proxy_regret": best_proxy_regret,
        "recommendation": recommendation,
    }
