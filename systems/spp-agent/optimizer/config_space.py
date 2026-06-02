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


def _make_config_id(er: str, norm: str, unit: str, miss: str) -> str:
    return f"er={er}|norm={norm}|unit={unit}|miss={miss}"


def generate_config_space() -> list[PopulationConfig]:
    cfg = load_config()
    space = cfg["population_config_space"]
    configs: list[PopulationConfig] = []
    for er, norm, unit, miss in product(
        space["er_strategy"],
        space["norm_strategy"],
        space["unit_strategy"],
        space["miss_strategy"],
    ):
        configs.append(
            PopulationConfig(
                config_id=_make_config_id(er, norm, unit, miss),
                er_strategy=er,
                norm_strategy=norm,
                unit_strategy=unit,
                miss_strategy=miss,
            )
        )
    return configs


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
    return np.array(features, dtype=float)
