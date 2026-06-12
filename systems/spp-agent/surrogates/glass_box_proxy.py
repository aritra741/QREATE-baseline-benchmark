from __future__ import annotations

import numpy as np

from optimizer.config_space import encode_config_features, parse_config_id
from surrogates.base import BaseSurrogate


def _hamming_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sum(a != b))


class GlassBoxProxySurrogate(BaseSurrogate):
    def __init__(self) -> None:
        self.probed_ids: list[str] = []
        self.features: dict[str, np.ndarray] = {}
        self.glass_scores: dict[str, float] = {}

    def fit(self, probe_data) -> None:
        self.probed_ids = list(probe_data.config_ids)
        self.glass_scores = dict(probe_data.glass_box_composites)
        self.features = {
            cid: encode_config_features(probe_data.configs[cid]) for cid in self.probed_ids
        }

    def score(self, config_id: str) -> float:
        if config_id in self.glass_scores:
            return self.glass_scores[config_id]

        if not self.probed_ids:
            return float("-inf")

        dummy = parse_config_id(config_id)
        target = encode_config_features(dummy)

        best_score = float("-inf")
        best_dist = float("inf")
        for pid in self.probed_ids:
            dist = _hamming_distance(target, self.features[pid])
            if dist < best_dist:
                best_dist = dist
                best_score = self.glass_scores[pid]
        return best_score
