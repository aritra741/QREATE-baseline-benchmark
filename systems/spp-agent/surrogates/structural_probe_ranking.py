from __future__ import annotations

from diagnostics.structural_score import structural_scores_from_probe
from surrogates.base import BaseSurrogate


class StructuralProbeRankingSurrogate(BaseSurrogate):
    """Rank configs by deployment-visible structural probe scores."""

    def __init__(self) -> None:
        self.scores: dict[str, float] = {}

    def fit(self, probe_data) -> None:
        self.scores = structural_scores_from_probe(probe_data)

    def score(self, config_id: str) -> float:
        return self.scores.get(config_id, float("-inf"))
