from __future__ import annotations

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel

from optimizer.config_space import encode_config_features, parse_config_id
from surrogates.base import BaseSurrogate, cluster_probe_view


class GPProxyGlassSurrogate(BaseSurrogate):
    def __init__(self) -> None:
        kernel = RBF(length_scale=1.0) + WhiteKernel(noise_level=0.1)
        self.model = GaussianProcessRegressor(kernel=kernel, random_state=42)
        self.fitted = False
        self._y_mean: float = 0.0

    def fit(self, probe_data) -> None:
        ids = list(probe_data.config_ids)
        if not ids:
            return
        X = np.vstack([encode_config_features(probe_data.configs[cid]) for cid in ids])
        y = np.array([probe_data.glass_box_composites[cid] for cid in ids])
        self._y_mean = float(np.mean(y))
        if len(ids) < 2:
            self.fitted = False
            return
        self.model.fit(X, y)
        self.fitted = True

    def fit_cluster(self, probe_data, cluster_id: int) -> None:
        self.fit(cluster_probe_view(probe_data, cluster_id))

    def score(self, config_id: str) -> float:
        if not self.fitted:
            return self._y_mean
        cfg = parse_config_id(config_id)
        x = encode_config_features(cfg).reshape(1, -1)
        return float(self.model.predict(x)[0])

    def score_with_uncertainty(self, config_id: str) -> tuple[float, float]:
        if not self.fitted:
            return self._y_mean, 0.0
        cfg = parse_config_id(config_id)
        x = encode_config_features(cfg).reshape(1, -1)
        mean, std = self.model.predict(x, return_std=True)
        return float(mean[0]), float(std[0])
