from __future__ import annotations

import numpy as np
from sklearn.linear_model import LinearRegression

from optimizer.config_space import encode_config_features
from surrogates.base import BaseSurrogate


class LinearProxyGlassSurrogate(BaseSurrogate):
    def __init__(self) -> None:
        self.model = LinearRegression()
        self.config_ids: list[str] = []
        self.fitted = False

    def fit(self, probe_data) -> None:
        self.config_ids = list(probe_data.config_ids)
        if not self.config_ids:
            return
        X = np.vstack([encode_config_features(probe_data.configs[cid]) for cid in self.config_ids])
        y = np.array([probe_data.glass_box_composites[cid] for cid in self.config_ids])
        self.model.fit(X, y)
        self.fitted = True

    def score(self, config_id: str) -> float:
        if not self.fitted:
            return float("-inf")
        parts = dict(p.split("=", 1) for p in config_id.split("|") if "=" in p)
        from optimizer.config_space import PopulationConfig

        cfg = PopulationConfig(
            config_id=config_id,
            er_strategy=parts.get("er", "embedding_0.7"),
            norm_strategy=parts.get("norm", "dictionary"),
            unit_strategy=parts.get("unit", "none"),
            miss_strategy=parts.get("miss", "drop"),
        )
        x = encode_config_features(cfg).reshape(1, -1)
        return float(self.model.predict(x)[0])
