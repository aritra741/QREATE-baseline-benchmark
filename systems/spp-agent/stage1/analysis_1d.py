from __future__ import annotations

import numpy as np

from optimizer.config_space import encode_config_features
from optimizer.probing import ProbeData
from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage1.1d")


def _pairwise_features(x: np.ndarray) -> np.ndarray:
    """Append all pairwise products of columns to *x*."""
    n, d = x.shape
    pairs: list[np.ndarray] = []
    for i in range(d):
        for j in range(i + 1, d):
            pairs.append((x[:, i] * x[:, j]).reshape(-1, 1))
    if not pairs:
        return x
    return np.hstack([x] + pairs)


def _r2(x: np.ndarray, y: np.ndarray) -> float:
    """OLS R² (returns 0.0 when underdetermined)."""
    if x.shape[0] <= x.shape[1]:
        return 0.0
    coef, residuals, _, _ = np.linalg.lstsq(x, y, rcond=None)
    ss_res = float(np.sum((y - x @ coef) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    if ss_tot == 0.0:
        return 1.0
    return max(0.0, 1.0 - ss_res / ss_tot)


def analyze_interactions(
    probe_data: ProbeData,
    *,
    thresholds: ThresholdConfig,
) -> dict:
    """Measure fraction of variance explained by two-way interactions."""
    config_ids = list(probe_data.config_ids)
    if len(config_ids) < 3:
        return {
            "main_effect_r2": 0.0,
            "interaction_r2": 0.0,
            "interaction_ratio": 0.0,
            "sparse": True,
            "recommendation": "linear_surrogate_sufficient",
        }

    x_main = np.array([encode_config_features(probe_data.configs[cid]) for cid in config_ids])
    # Add intercept column
    x_main = np.hstack([np.ones((x_main.shape[0], 1)), x_main])
    y = np.array([probe_data.glass_box_composites[cid] for cid in config_ids])

    main_r2 = _r2(x_main, y)

    x_full = _pairwise_features(x_main)
    interaction_r2 = _r2(x_full, y)

    ratio = interaction_r2 - main_r2
    sparse = ratio < thresholds.interaction_ratio
    recommendation = "linear_surrogate_sufficient" if sparse else "nonlinear_surrogate_needed"

    logger.info(
        "Interactions: main_r2=%.4f interaction_r2=%.4f ratio=%.4f sparse=%s rec=%s",
        main_r2, interaction_r2, ratio, sparse, recommendation,
    )
    return {
        "main_effect_r2": main_r2,
        "interaction_r2": interaction_r2,
        "interaction_ratio": ratio,
        "sparse": sparse,
        "recommendation": recommendation,
    }
