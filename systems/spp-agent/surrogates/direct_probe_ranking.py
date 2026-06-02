from __future__ import annotations

from surrogates.base import BaseSurrogate


class DirectProbeRankingSurrogate(BaseSurrogate):
    def __init__(self) -> None:
        self.scores: dict[str, float] = {}

    def fit(self, probe_data) -> None:
        self.scores = dict(probe_data.glass_box_composites)

    def score(self, config_id: str) -> float:
        return self.scores.get(config_id, float("-inf"))
