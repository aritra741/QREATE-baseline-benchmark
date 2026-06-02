from __future__ import annotations

import numpy as np

from optimizer.config_space import PopulationConfig, encode_config_features
from surrogates.base import BaseSurrogate


class LLMJudgeBTLSurrogate(BaseSurrogate):
    def __init__(self) -> None:
        self.btl_scores: dict[str, float] = {}
        self.features: dict[str, np.ndarray] = {}
        self.probed_ids: list[str] = []

    def fit(self, probe_data) -> None:
        self.btl_scores = dict(probe_data.btl_scores)
        self.probed_ids = list(probe_data.config_ids)
        self.features = {
            cid: encode_config_features(probe_data.configs[cid]) for cid in self.probed_ids
        }

    def score(self, config_id: str) -> float:
        if config_id in self.btl_scores:
            return self.btl_scores[config_id]
        if not self.probed_ids:
            return float("-inf")

        parts = dict(p.split("=", 1) for p in config_id.split("|") if "=" in p)
        dummy = PopulationConfig(
            config_id=config_id,
            er_strategy=parts.get("er", "embedding_0.7"),
            norm_strategy=parts.get("norm", "dictionary"),
            unit_strategy=parts.get("unit", "none"),
            miss_strategy=parts.get("miss", "drop"),
        )
        target = encode_config_features(dummy)

        best = float("-inf")
        best_dist = float("inf")
        for pid in self.probed_ids:
            dist = float(np.sum(target != self.features[pid]))
            if dist < best_dist:
                best_dist = dist
                best = self.btl_scores.get(pid, float("-inf"))
        return best
