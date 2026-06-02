from __future__ import annotations

import numpy as np

from optimizer.config_space import encode_config_features
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

        from optimizer.config_space import PopulationConfig

        # config_id string encodes modules; rebuild PopulationConfig from probe configs template
        # Use nearest probed by Hamming distance in one-hot features
        target = None
        for cid in self.probed_ids:
            if cid == config_id:
                return self.glass_scores[cid]

        # Parse config_id if unprobed
        parts = dict(p.split("=", 1) for p in config_id.split("|") if "=" in p)
        dummy = PopulationConfig(
            config_id=config_id,
            er_strategy=parts.get("er", "embedding_0.7"),
            norm_strategy=parts.get("norm", "dictionary"),
            unit_strategy=parts.get("unit", "none"),
            miss_strategy=parts.get("miss", "drop"),
        )
        target = encode_config_features(dummy)

        best_score = float("-inf")
        best_dist = float("inf")
        for pid in self.probed_ids:
            dist = _hamming_distance(target, self.features[pid])
            if dist < best_dist:
                best_dist = dist
                best_score = self.glass_scores[pid]
        return best_score
