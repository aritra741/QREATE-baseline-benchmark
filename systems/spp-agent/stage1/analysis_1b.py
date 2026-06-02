from __future__ import annotations

import numpy as np

from optimizer.config_space import encode_config_features
from optimizer.probing import ProbeData
from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage1.1b")


def analyze_error_surface(
    probe_data: ProbeData,
    *,
    thresholds: ThresholdConfig,
) -> dict:
    """Count local minima on the one-hot Hamming-1 neighbour graph."""
    config_ids = list(probe_data.config_ids)
    if not config_ids:
        return {
            "local_minima_count": 0,
            "total_configs": 0,
            "smooth": True,
            "recommendation": "local_coord_methods_viable",
        }

    features = {cid: encode_config_features(probe_data.configs[cid]) for cid in config_ids}
    scores = probe_data.glass_box_composites

    local_minima = 0
    for cid in config_ids:
        vec = features[cid]
        neighbours = [
            other for other in config_ids
            if other != cid
            and int(np.sum(np.abs(features[other] - vec))) == 2  # one-hot flip = 2 changed entries
        ]
        if not neighbours:
            continue
        if all(scores[cid] < scores[n] for n in neighbours):
            local_minima += 1

    smooth = local_minima <= 1
    recommendation = "local_coord_methods_viable" if smooth else "include_bo_sa_evo"

    logger.info(
        "Error surface: local_minima=%d total=%d smooth=%s rec=%s",
        local_minima, len(config_ids), smooth, recommendation,
    )
    return {
        "local_minima_count": local_minima,
        "total_configs": len(config_ids),
        "smooth": smooth,
        "recommendation": recommendation,
    }
