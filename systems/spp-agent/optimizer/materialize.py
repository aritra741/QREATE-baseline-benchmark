from __future__ import annotations

from optimizer.config_space import generate_config_space, parse_config_id
from optimizer.probing import ProbeData
from pipeline.extraction import ExtractionResult
from pipeline.population import apply_population
from pipeline.schema import Schema


def materialize_database(
    probe_data: ProbeData,
    config_id: str,
    schema: Schema,
) -> dict:
    if probe_data.extraction is None:
        if config_id in probe_data.databases:
            return probe_data.databases[config_id]
        raise RuntimeError(f"No database for config {config_id} and no cached extraction.")

    config = parse_config_id(config_id)
    db, _ = apply_population(probe_data.extraction, config, schema)
    probe_data.databases[config_id] = db
    return db


def all_config_ids() -> list[str]:
    return [c.config_id for c in generate_config_space()]
