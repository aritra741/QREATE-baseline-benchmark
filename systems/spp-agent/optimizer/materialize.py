from __future__ import annotations

from optimizer.config_space import PopulationConfig, generate_config_space
from optimizer.probing import ProbeData
from pipeline.extraction import ExtractionResult
from pipeline.population import apply_population
from pipeline.schema import Schema


def materialize_database(
    probe_data: ProbeData,
    config_id: str,
    schema: Schema,
) -> dict:
    if config_id in probe_data.databases:
        return probe_data.databases[config_id]

    if probe_data.extraction is None:
        raise RuntimeError(f"No database for config {config_id} and no cached extraction.")

    parts = dict(p.split("=", 1) for p in config_id.split("|") if "=" in p)
    config = PopulationConfig(
        config_id=config_id,
        er_strategy=parts.get("er", "embedding_0.7"),
        norm_strategy=parts.get("norm", "dictionary"),
        unit_strategy=parts.get("unit", "none"),
        miss_strategy=parts.get("miss", "drop"),
    )
    db, _ = apply_population(probe_data.extraction, config, schema)
    probe_data.databases[config_id] = db
    return db


def all_config_ids() -> list[str]:
    return [c.config_id for c in generate_config_space()]
