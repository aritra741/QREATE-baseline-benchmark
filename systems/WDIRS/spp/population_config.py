"""Phase 1 — Explicit population configuration space for WDIRS.

Mirrors the `Pop(T,s)` axes from the formal problem statement
(description_removed.pdf, Section 4):

    pop = f_miss ∘ f_unit ∘ f_type ∘ f_norm ∘ f_er

Each axis is a categorical strategy (`c_i`) plus strategy-specific
parameters (`h_i`). WDIRS's existing hardcoded behavior becomes one point
in this space (er=embedding_0.75-ish / norm=dictionary-esque / unit=none /
miss=drop-ish); this module makes every axis explicit and enumerable so a
single shared extraction can be "populated" many different ways without
re-running extraction, sieve synthesis, or schema stabilization.

This module has NO dependency on WDIRS's extraction internals -- it only
defines the config space and (de)serialization of config ids. The actual
transformation logic lives in `population.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import List


# ============================================================================
# Axis domains (Cer, Cnorm, Cunit, Cmiss from the problem statement)
# ============================================================================

ER_STRATEGIES: List[str] = [
    "embedding_0.7",
    "embedding_0.8",
    "embedding_0.9",
    "llm",
]

NORM_STRATEGIES: List[str] = [
    "dictionary",
    "llm",
]

UNIT_STRATEGIES: List[str] = [
    "none",
    "unit",
]

MISS_STRATEGIES: List[str] = [
    "drop",
    "mean",
    "median",
    "mode",
    "constant",
    "llm",
]

# Default missing-value fill used by miss_strategy="constant" when no
# schema-derived admissible value is supplied.
DEFAULT_MISSING_CONSTANT = "UNKNOWN"


@dataclass(frozen=True)
class PopulationConfig:
    """One point in WDIRS's Pop(T,s) configuration space."""

    er_strategy: str = "embedding_0.75"  # WDIRS's current default (Phase 0 baseline)
    norm_strategy: str = "dictionary"
    unit_strategy: str = "none"
    miss_strategy: str = "drop"
    missing_constant: str = DEFAULT_MISSING_CONSTANT

    @property
    def config_id(self) -> str:
        return (
            f"er={self.er_strategy}|norm={self.norm_strategy}|"
            f"unit={self.unit_strategy}|miss={self.miss_strategy}"
        )

    @property
    def er_threshold(self) -> float:
        """Bi-encoder blocking threshold implied by an embedding_* strategy.

        Returns WDIRS's current default (0.75) for the "llm" strategy, since
        that strategy bypasses embedding-threshold blocking entirely (see
        population.py).
        """
        if self.er_strategy.startswith("embedding_"):
            try:
                return float(self.er_strategy.split("_", 1)[1])
            except ValueError:
                pass
        return 0.75

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.config_id


def generate_config_space(
    *,
    er_strategies: List[str] | None = None,
    norm_strategies: List[str] | None = None,
    unit_strategies: List[str] | None = None,
    miss_strategies: List[str] | None = None,
) -> List[PopulationConfig]:
    """Enumerate the full (or a restricted) Pop(T,s) config space.

    Deterministically sorted by `config_id` string, matching the invariant
    spp-agent used for its own config space.
    """
    ers = er_strategies or ER_STRATEGIES
    norms = norm_strategies or NORM_STRATEGIES
    units = unit_strategies or UNIT_STRATEGIES
    misses = miss_strategies or MISS_STRATEGIES

    configs = [
        PopulationConfig(er_strategy=er, norm_strategy=norm, unit_strategy=unit, miss_strategy=miss)
        for er, norm, unit, miss in product(ers, norms, units, misses)
    ]
    configs.sort(key=lambda c: c.config_id)
    return configs


def parse_config_id(config_id: str) -> PopulationConfig:
    """Inverse of `PopulationConfig.config_id`. Tolerant of missing axes
    (defaults applied) for forward/backward compatibility with cached data.
    """
    parts = dict(
        part.split("=", 1) for part in config_id.split("|") if "=" in part
    )
    return PopulationConfig(
        er_strategy=parts.get("er", "embedding_0.75"),
        norm_strategy=parts.get("norm", "dictionary"),
        unit_strategy=parts.get("unit", "none"),
        miss_strategy=parts.get("miss", "drop"),
    )


def encode_config_features(config: PopulationConfig) -> List[float]:
    """One-hot feature vector, for surrogate/routing use in later phases.

    Order: [er (4), norm (2), unit (2), miss (6)] = 14 dims.
    """
    vec: List[float] = []
    for er in ER_STRATEGIES:
        vec.append(1.0 if config.er_strategy == er else 0.0)
    for norm in NORM_STRATEGIES:
        vec.append(1.0 if config.norm_strategy == norm else 0.0)
    for unit in UNIT_STRATEGIES:
        vec.append(1.0 if config.unit_strategy == unit else 0.0)
    for miss in MISS_STRATEGIES:
        vec.append(1.0 if config.miss_strategy == miss else 0.0)
    return vec
