"""Phase 2: enumerate candidate configs and estimate materialization costs."""

from __future__ import annotations

from itertools import product
from typing import Any

from optimizer.config_space import PopulationConfig
from utils.token_budget import CostModel


def generate_budgeted_config_space() -> list[PopulationConfig]:
    """Config axes specified for the budgeted agent (coerce: strict | llm only)."""
    configs: list[PopulationConfig] = []
    for er, norm, unit, miss, coerce in product(
        ["embedding_0.7", "embedding_0.8", "embedding_0.9", "llm"],
        ["dictionary", "llm"],
        ["none", "unit"],
        ["drop", "mean", "median", "mode", "constant", "llm"],
        ["strict", "llm"],
    ):
        cid = f"er={er}|norm={norm}|unit={unit}|miss={miss}|coerce={coerce}"
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
    return configs


def _settings_dict(config: PopulationConfig) -> dict[str, str]:
    return {
        "er": config.er_strategy,
        "norm": config.norm_strategy,
        "unit": config.unit_strategy,
        "miss": config.miss_strategy,
        "coerce": config.type_coercion,
    }


def build_config_catalog(
    n_docs: int,
    avg_doc_tokens: float,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """
    Returns (unprobed_configs, catalog_id_to_pipe_id).

    estimated_cost = extraction + marginal materialization (CostModel).
    """
    cost_model = CostModel(avg_doc_tokens=avg_doc_tokens)
    extraction_cost = cost_model.extraction_cost(n_docs)
    catalog: list[dict[str, Any]] = []
    id_map: dict[str, str] = {}

    for idx, config in enumerate(generate_budgeted_config_space(), start=1):
        catalog_id = f"c{idx}"
        pipe_id = config.config_id
        marginal = cost_model.config_marginal_cost(pipe_id, n_docs)
        estimated = int(extraction_cost + marginal)
        catalog.append(
            {
                "config_id": catalog_id,
                "settings": _settings_dict(config),
                "estimated_cost": estimated,
                "pipe_config_id": pipe_id,
            }
        )
        id_map[catalog_id] = pipe_id

    return catalog, id_map
