from __future__ import annotations

from abc import ABC, abstractmethod


class BaseSurrogate(ABC):
    def fit(self, probe_data) -> None:
        ...

    @abstractmethod
    def score(self, config_id: str) -> float:
        ...

    def rank(self, candidates: list[str]) -> list[str]:
        return sorted(candidates, key=self.score, reverse=True)
