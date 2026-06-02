from __future__ import annotations

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor

from optimizer.config_space import PopulationConfig, encode_config_features
from surrogates.base import BaseSurrogate


class LinearErrorSurrogate(BaseSurrogate):
    """Ablation only — uses true probe errors; not exposed to agent."""

    def __init__(self) -> None:
        self.model = LinearRegression()
        self.fitted = False

    def fit(self, probe_data, true_errors: dict[str, float] | None = None) -> None:
        if true_errors is None:
            true_errors = getattr(probe_data, "true_errors", {})
        ids = list(probe_data.config_ids)
        if not ids or not true_errors:
            return
        X = np.vstack([encode_config_features(probe_data.configs[cid]) for cid in ids])
        y = np.array([true_errors[cid] for cid in ids])
        self.model.fit(X, y)
        self.fitted = True

    def score(self, config_id: str) -> float:
        if not self.fitted:
            return float("-inf")
        parts = dict(p.split("=", 1) for p in config_id.split("|") if "=" in p)
        cfg = PopulationConfig(
            config_id=config_id,
            er_strategy=parts.get("er", "embedding_0.7"),
            norm_strategy=parts.get("norm", "dictionary"),
            unit_strategy=parts.get("unit", "none"),
            miss_strategy=parts.get("miss", "drop"),
        )
        x = encode_config_features(cfg).reshape(1, -1)
        # lower error is better -> negate
        return float(-self.model.predict(x)[0])


class RFErrorSurrogate(BaseSurrogate):
    """Ablation only — uses true probe errors; not exposed to agent."""

    def __init__(self) -> None:
        self.model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.fitted = False

    def fit(self, probe_data, true_errors: dict[str, float] | None = None) -> None:
        if true_errors is None:
            true_errors = getattr(probe_data, "true_errors", {})
        ids = list(probe_data.config_ids)
        if not ids or not true_errors:
            return
        X = np.vstack([encode_config_features(probe_data.configs[cid]) for cid in ids])
        y = np.array([true_errors[cid] for cid in ids])
        self.model.fit(X, y)
        self.fitted = True

    def score(self, config_id: str) -> float:
        if not self.fitted:
            return float("-inf")
        parts = dict(p.split("=", 1) for p in config_id.split("|") if "=" in p)
        cfg = PopulationConfig(
            config_id=config_id,
            er_strategy=parts.get("er", "embedding_0.7"),
            norm_strategy=parts.get("norm", "dictionary"),
            unit_strategy=parts.get("unit", "none"),
            miss_strategy=parts.get("miss", "drop"),
        )
        x = encode_config_features(cfg).reshape(1, -1)
        return float(-self.model.predict(x)[0])
