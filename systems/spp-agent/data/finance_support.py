from __future__ import annotations

import json
import random
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from data.aggregation_slices import (
    filter_aggregation_queries,
    group_queries_by_aggregation_slice,
    queries_for_aggregation_slice,
)
from data.instance_builder import Instance
from data.loader import load_queries, _benchu_root
from diagnostics.tier0 import compute_tier0
from optimizer.config_space import PopulationConfig, encode_config_features, generate_config_space
from pipeline.execution import execute_sql_on_db
from pipeline.schema import Schema
from utils.config import load_config

FINANCE_QUERY_DATASET = "Finan"
FINANCE_TABLE = "Finan"
FINANCE_TRAINING_CATEGORIES = {"Agg", "Filter", "Select", "Mixed"}

_TABLE_ALIAS_RE = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in ("finance", "Finance", "Finan", "finan")) + r")\b",
    re.IGNORECASE,
)


def finance_corpus_dir() -> Path:
    cfg = load_config()
    finance_cfg = cfg.get("finance", {})
    rel = finance_cfg.get("corpus_path", "source_data/Finance")
    path = Path(_benchu_root()) / rel
    if not path.is_dir():
        raise FileNotFoundError(
            f"Finance corpus not found at {path}. Expected text files under source_data/Finance/."
        )
    return path


def load_finance_corpus() -> list[dict]:
    """Load Finance documents from source_data/Finance/finance/."""
    corpus_root = finance_corpus_dir()
    docs: list[dict] = []
    txt_files = sorted(corpus_root.rglob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(f"No Finance .txt files found under {corpus_root}")

    missing_ids: list[int] = []
    seen_ids: set[int] = set()
    for path in txt_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(corpus_root)
        stem = path.stem
        if stem.isdigit():
            seen_ids.add(int(stem))
        docs.append(
            {
                "doc_id": str(rel.with_suffix("")),
                "text": text,
                "metadata": {
                    "file_name": path.name,
                    "table_hint": FINANCE_TABLE.lower(),
                    "entity_type": "finance",
                    "source_path": str(path),
                },
            }
        )

    gt = load_finance_ground_truth()
    gt_ids = set(gt[FINANCE_TABLE]["id"].astype(int).tolist()) if "id" in gt[FINANCE_TABLE].columns else set()
    if gt_ids:
        missing_ids = sorted(gt_ids - seen_ids)
        if missing_ids:
            import logging

            logging.getLogger("spp.finance").warning(
                "Finance corpus missing %d GT doc(s): %s (continuing with %d docs)",
                len(missing_ids),
                missing_ids[:10],
                len(docs),
            )

    return docs


def load_finance_ground_truth() -> dict[str, pd.DataFrame]:
    root = _benchu_root()
    for candidate in (root / "Data" / "Finan" / "Finan.csv", root / "Query" / "Finan" / "Finan.csv"):
        if candidate.is_file():
            df = pd.read_csv(candidate)
            if "ID" in df.columns and "id" not in df.columns:
                df = df.rename(columns={"ID": "id"})
            return {FINANCE_TABLE: df}
    raise FileNotFoundError("Finance ground-truth CSV not found under Data/Finan or Query/Finan.")


def load_finance_training_queries() -> list[dict]:
    """Training split only (Agg/Filter/Select/Mixed), matching Legal pilot scope."""
    all_queries = load_queries(FINANCE_QUERY_DATASET)
    kept = [q for q in all_queries if (q.get("category") or "") in FINANCE_TRAINING_CATEGORIES]
    if not kept:
        raise RuntimeError(
            f"No Finan training queries found in categories {sorted(FINANCE_TRAINING_CATEGORIES)}."
        )
    return kept


def build_finance_schema() -> Schema:
    tables = load_finance_ground_truth()
    table_columns: dict[str, list[str]] = {}
    column_types: dict[str, dict[str, str]] = {}
    descriptions: list[str] = []

    benchu_root = _benchu_root()
    attr_path = benchu_root / "Query" / FINANCE_QUERY_DATASET / "Finan_attributes.json"
    attr_map: dict[str, dict[str, dict]] = {}
    if attr_path.is_file():
        with attr_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        for entity_name, cols in data.items():
            attr_map.setdefault(entity_name, {}).update(cols)

    entity_attrs = attr_map.get("finance", {})

    for table_name, df in tables.items():
        cols = [c for c in df.columns if c.lower() not in {"unnamed: 0"}]
        table_columns[table_name] = cols
        column_types[table_name] = {}
        for col in cols:
            series = df[col]
            if pd.api.types.is_integer_dtype(series):
                dtype = "int"
            elif pd.api.types.is_float_dtype(series):
                dtype = "float"
            elif pd.api.types.is_bool_dtype(series):
                dtype = "bool"
            else:
                dtype = "str"
            column_types[table_name][col] = dtype
            desc = entity_attrs.get(col, {}).get("description", "")
            if desc:
                descriptions.append(f"{table_name}.{col}: {desc}")

    description = (
        "Finance single-table denormalized schema (finance entity). "
        "No joins; all configuration variation is in population/preprocessing modules. "
        + " ".join(descriptions[:40])
    )
    return Schema(
        dataset_name=FINANCE_QUERY_DATASET,
        tables=table_columns,
        column_types=column_types,
        description=description,
    )


def normalize_finance_sql(sql: str) -> str:
    return _TABLE_ALIAS_RE.sub(FINANCE_TABLE, sql)


def normalize_finance_queries(queries: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for query in queries:
        item = dict(query)
        item["sql_query"] = normalize_finance_sql(query.get("sql_query", ""))
        normalized.append(item)
    return normalized


def build_finance_instance(*, include_ground_truth: bool = False) -> Instance:
    corpus = load_finance_corpus()
    queries = normalize_finance_queries(load_finance_training_queries())
    schema = build_finance_schema()
    gt = load_finance_ground_truth() if include_ground_truth else None
    configs = generate_config_space()

    agg_buckets = group_queries_by_aggregation_slice(filter_aggregation_queries(queries))
    return Instance(
        dataset_name=FINANCE_QUERY_DATASET,
        corpus=corpus,
        queries=queries,
        schema=schema,
        ground_truth_tables=gt,
        config_space=configs,
        metadata={
            "num_docs": len(corpus),
            "num_queries": len(queries),
            "schema_mode": "denormalized_single_table",
            "table_name": FINANCE_TABLE,
            "aggregation_slice_counts": {k: len(v) for k, v in agg_buckets.items()},
            "corpus_missing_gt_ids": [],
        },
    )


def sample_finance_corpus(corpus: list[dict], num_docs: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    pool = list(corpus)
    rng.shuffle(pool)
    return pool[: min(num_docs, len(pool))]


def prepare_finance_agg_only_instance(
    instance: Instance,
    *,
    num_docs: int,
    num_eval_queries: int,
    seed: int,
) -> tuple[Instance, set[str]]:
    slice_queries = queries_for_aggregation_slice(instance.queries, "agg_only")
    if not slice_queries:
        raise RuntimeError("No agg_only queries available for Finance.")

    eval_queries = slice_queries[:num_eval_queries]
    sampled_corpus = sample_finance_corpus(instance.corpus, num_docs, seed)
    required_tables = {FINANCE_TABLE}

    trimmed = replace(
        instance,
        corpus=sampled_corpus,
        queries=eval_queries,
        metadata={
            **(instance.metadata or {}),
            "aggregation_slice": "agg_only",
            "num_docs": len(sampled_corpus),
            "num_eval_queries": len(eval_queries),
            "num_queries_in_slice": len(slice_queries),
            "required_tables": sorted(required_tables),
            "corpus_entity_types": ["finance"],
        },
    )
    return trimmed, required_tables


def register_finance_db(db: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Ensure DuckDB can resolve SQL table aliases used in Bench-U Finance queries."""
    extended = dict(db)
    if FINANCE_TABLE in db:
        df = db[FINANCE_TABLE]
        extended.setdefault("finance", df)
        extended.setdefault("Finance", df)
        extended.setdefault("Finan", df)
    return extended


def execute_finance_sql(db: dict[str, pd.DataFrame], sql: str) -> pd.DataFrame:
    return execute_sql_on_db(register_finance_db(db), normalize_finance_sql(sql))


def config_feature_vector(config: PopulationConfig) -> list[float]:
    return encode_config_features(config).tolist()


def build_tier0_summary(instance: Instance, *, budget: float = 0.0) -> dict[str, Any]:
    return compute_tier0(
        corpus=instance.corpus,
        queries=instance.queries,
        schema=instance.schema,
        config_space_size=len(generate_config_space()),
        budget=budget,
    )


def analyze_unit_relevance(probe_config_ids: list[str], per_config_errors: dict[str, float]) -> dict[str, Any]:
    none_errors: list[float] = []
    unit_errors: list[float] = []
    for cid in probe_config_ids:
        err = per_config_errors.get(cid)
        if err is None:
            continue
        if "|unit=none|" in cid or cid.endswith("|unit=none"):
            none_errors.append(err)
        elif "|unit=unit|" in cid:
            unit_errors.append(err)

    none_avg = sum(none_errors) / len(none_errors) if none_errors else None
    unit_avg = sum(unit_errors) / len(unit_errors) if unit_errors else None
    return {
        "unit_none_avg_error": none_avg,
        "unit_unit_avg_error": unit_avg,
        "unit_effect": None
        if none_avg is None or unit_avg is None
        else abs(none_avg - unit_avg),
        "note": "Finance revenue/assets are numeric strings; unit standardization may have limited effect.",
    }
