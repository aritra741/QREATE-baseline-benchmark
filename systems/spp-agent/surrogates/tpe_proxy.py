from __future__ import annotations

import numpy as np

from optimizer.config_space import PopulationConfig, encode_config_features
from surrogates.base import BaseSurrogate


def _hamming_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sum(a != b))


def _normalize_to_01(values: np.ndarray) -> np.ndarray:
    vmin = values.min()
    vmax = values.max()
    if vmax - vmin < 1e-12:
        return np.full_like(values, 0.5)
    return (values - vmin) / (vmax - vmin)


class TPEProxySurrogate(BaseSurrogate):
    def __init__(self) -> None:
        self.probed_ids: list[str] = []
        self.features: dict[str, np.ndarray] = {}
        self._fitted_glass: dict[str, float] = {}
        self._fitted_btl: dict[str, float] = {}
        self._combined: dict[str, float] = {}

    def fit(self, probe_data) -> None:
        self.probed_ids = list(probe_data.config_ids)
        self._fitted_glass = dict(probe_data.glass_box_composites)
        self._fitted_btl = dict(probe_data.btl_scores)
        self.features = {
            cid: encode_config_features(probe_data.configs[cid])
            for cid in self.probed_ids
        }

        if not self.probed_ids:
            return

        glass_arr = np.array([self._fitted_glass[cid] for cid in self.probed_ids])
        glass_norm = _normalize_to_01(glass_arr)

        btl_ids = [cid for cid in self.probed_ids if cid in self._fitted_btl]
        if btl_ids:
            btl_arr = np.array([self._fitted_btl[cid] for cid in self.probed_ids])
            btl_norm = _normalize_to_01(btl_arr)
            combined = 0.5 * glass_norm + 0.5 * btl_norm
        else:
            combined = glass_norm

        for i, cid in enumerate(self.probed_ids):
            self._combined[cid] = float(combined[i])

    def score(self, config_id: str) -> float:
        if config_id in self._combined:
            return self._combined[config_id]

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

        best_score = float("-inf")
        best_dist = float("inf")
        for pid in self.probed_ids:
            dist = _hamming_distance(target, self.features[pid])
            if dist < best_dist:
                best_dist = dist
                best_score = self._combined.get(pid, float("-inf"))
        return best_score
