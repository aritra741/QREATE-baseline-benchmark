from __future__ import annotations

import copy
from abc import ABC, abstractmethod


def cluster_probe_view(probe_data, cluster_id: int):
    """Build a probe_data view with cluster-specific glass-box and BTL scores."""
    if not getattr(probe_data, "cluster_glass_box_composites", None):
        return probe_data

    pd_view = copy.copy(probe_data)
    pd_view.glass_box_composites = {
        cid: probe_data.cluster_glass_box_composites.get(cid, {}).get(
            cluster_id,
            probe_data.glass_box_composites.get(cid, 0.0),
        )
        for cid in probe_data.config_ids
    }
    cluster_btl = probe_data.cluster_btl_scores.get(cluster_id)
    if cluster_btl:
        pd_view.btl_scores = dict(cluster_btl)
    return pd_view


class BaseSurrogate(ABC):
    def fit(self, probe_data) -> None:
        ...

    @abstractmethod
    def score(self, config_id: str) -> float:
        ...

    def rank(self, candidates: list[str]) -> list[str]:
        return sorted(candidates, key=self.score, reverse=True)

    def score_with_uncertainty(self, config_id: str) -> tuple[float, float]:
        """Return (predicted_score, uncertainty_estimate)."""
        return self.score(config_id), 0.0

    def fit_cluster(self, probe_data, cluster_id: int) -> None:
        """Fit surrogate using cluster-conditioned signals for a specific cluster."""
        if getattr(probe_data, "cluster_glass_box_composites", None):
            self.fit(cluster_probe_view(probe_data, cluster_id))
        else:
            self.fit(probe_data)
