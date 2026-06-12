from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np

from utils.config import load_config


@dataclass(frozen=True)
class PopulationConfig:
    config_id: str
    er_strategy: str
    norm_strategy: str
    unit_strategy: str
    miss_strategy: str
    type_coercion: str = "strict"


def _make_config_id(er: str, norm: str, unit: str, miss: str, coerce: str) -> str:
    return f"er={er}|norm={norm}|unit={unit}|miss={miss}|coerce={coerce}"


def parse_config_id(config_id: str) -> PopulationConfig:
    """Parse a pipe-delimited config id; defaults coerce=strict for legacy caches."""
    parts = dict(p.split("=", 1) for p in config_id.split("|") if "=" in p)
    er = parts.get("er", "embedding_0.7")
    norm = parts.get("norm", "dictionary")
    unit = parts.get("unit", "none")
    miss = parts.get("miss", "drop")
    coerce = parts.get("coerce", "strict")
    return PopulationConfig(
        config_id=config_id,
        er_strategy=er,
        norm_strategy=norm,
        unit_strategy=unit,
        miss_strategy=miss,
        type_coercion=coerce,
    )


def generate_config_space() -> list[PopulationConfig]:
    cfg = load_config()
    space = cfg["population_config_space"]
    configs: list[PopulationConfig] = []
    for er, norm, unit, miss, coerce in product(
        space["er_strategy"],
        space["norm_strategy"],
        space["unit_strategy"],
        space["miss_strategy"],
        space.get("type_coercion", ["strict"]),
    ):
        cid = _make_config_id(er, norm, unit, miss, coerce)
        configs.append(
            PopulationConfig(
                config_id=cid,
                er_strategy=er,
                norm_strategy=norm,
                unit_strategy=unit,
                miss_strategy=miss,
                type_coercion=coerce,
            )
        )
    return sorted(configs, key=lambda c: c.config_id)


def encode_config_features(config: PopulationConfig) -> np.ndarray:
    cfg = load_config()
    space = cfg["population_config_space"]

    def one_hot(value: str, choices: list[str]) -> list[float]:
        return [1.0 if value == c else 0.0 for c in choices]

    features: list[float] = []
    features.extend(one_hot(config.er_strategy, space["er_strategy"]))
    features.extend(one_hot(config.norm_strategy, space["norm_strategy"]))
    features.extend(one_hot(config.unit_strategy, space["unit_strategy"]))
    features.extend(one_hot(config.miss_strategy, space["miss_strategy"]))
    features.extend(one_hot(config.type_coercion, space.get("type_coercion", ["strict"])))
    return np.array(features, dtype=float)
