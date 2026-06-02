from __future__ import annotations

import random

from surrogates.base import BaseSurrogate


class RandomRankingSurrogate(BaseSurrogate):
    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)
        self.order: list[str] = []

    def fit(self, probe_data) -> None:
        ids = list(probe_data.config_ids)
        self.rng.shuffle(ids)
        self.order = ids

    def score(self, config_id: str) -> float:
        if config_id in self.order:
            return float(len(self.order) - self.order.index(config_id))
        return self.rng.random()
