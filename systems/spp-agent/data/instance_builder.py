from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from data.loader import load_corpus, load_ground_truth, load_queries
from optimizer.config_space import PopulationConfig, generate_config_space
from pipeline.schema import Schema, load_fixed_schema


@dataclass
class Instance:
    dataset_name: str
    corpus: list[dict]
    queries: list[dict]
    schema: Schema
    ground_truth_tables: dict[str, pd.DataFrame] | None = None
    config_space: list[PopulationConfig] | None = None
    metadata: dict[str, Any] | None = None


def build_instance(
    dataset_name: str,
    *,
    include_ground_truth: bool = False,
) -> Instance:
    corpus = load_corpus(dataset_name)
    queries = load_queries(dataset_name)
    schema = load_fixed_schema(dataset_name)
    gt = load_ground_truth(dataset_name) if include_ground_truth else None
    configs = generate_config_space()

    return Instance(
        dataset_name=dataset_name,
        corpus=corpus,
        queries=queries,
        schema=schema,
        ground_truth_tables=gt,
        config_space=configs,
        metadata={"num_docs": len(corpus), "num_queries": len(queries)},
    )
