from __future__ import annotations

import re

import numpy as np

from optimizer.probing import ProbeData
from pipeline.schema import Schema
from utils.logging import setup_logger

logger = setup_logger("spp.stage4.schema_pruning")

_WORD_RE = re.compile(r"\b\w+\b")


def _columns_referenced_in_sql(sql: str) -> set[str]:
    """Extract candidate column names from a SQL string (lowered tokens)."""
    return {tok.lower() for tok in _WORD_RE.findall(sql)}


def prune_schema_compat(
    schema: Schema,
    queries: list[dict],
) -> Schema:
    """Keep only columns referenced in any query SQL."""
    referenced: set[str] = set()
    for q in queries:
        referenced |= _columns_referenced_in_sql(q.get("sql_query", ""))

    new_tables: dict[str, list[str]] = {}
    new_types: dict[str, dict[str, str]] = {}
    for table, cols in schema.tables.items():
        kept = [c for c in cols if c.lower() in referenced]
        if kept:
            new_tables[table] = kept
            new_types[table] = {
                c: schema.column_types.get(table, {}).get(c, "str") for c in kept
            }

    logger.info(
        "prune_schema_compat: %d/%d tables, %d/%d columns retained",
        len(new_tables),
        len(schema.tables),
        sum(len(v) for v in new_tables.values()),
        sum(len(v) for v in schema.tables.values()),
    )
    return Schema(
        dataset_name=schema.dataset_name,
        tables=new_tables,
        column_types=new_types,
        description=schema.description,
    )


def prune_schema_probe(
    schema: Schema,
    probe_data: ProbeData,
    percentile: float = 0.5,
) -> Schema:
    """Keep columns from tables with above-percentile glass_box_composite."""
    composites = probe_data.glass_box_composites
    if not composites:
        return schema

    table_scores: dict[str, list[float]] = {}
    for cid, score in composites.items():
        # Attribute composite to all tables uniformly
        for table in schema.tables:
            table_scores.setdefault(table, []).append(score)

    # Refine: if tier1 signals carry per-table data, use it
    for cid, signals in probe_data.tier1_signals.items():
        numeric_checks = signals.get("numeric_column_checks", {})
        for table in schema.tables:
            if table in numeric_checks:
                rate = numeric_checks[table].get("success_rate", 0.0)
                table_scores.setdefault(table, []).append(rate)

    mean_scores: dict[str, float] = {
        t: float(np.mean(vals)) for t, vals in table_scores.items()
    }
    threshold = float(np.percentile(list(mean_scores.values()), percentile * 100))

    new_tables: dict[str, list[str]] = {}
    new_types: dict[str, dict[str, str]] = {}
    for table, cols in schema.tables.items():
        if mean_scores.get(table, 0.0) >= threshold:
            new_tables[table] = list(cols)
            new_types[table] = dict(schema.column_types.get(table, {}))

    logger.info(
        "prune_schema_probe: threshold=%.4f, %d/%d tables retained",
        threshold,
        len(new_tables),
        len(schema.tables),
    )
    return Schema(
        dataset_name=schema.dataset_name,
        tables=new_tables,
        column_types=new_types,
        description=schema.description,
    )


def prune_schema_pareto(
    schema: Schema,
    queries: list[dict],
    probe_data: ProbeData,
) -> Schema:
    """Pareto prune: retain columns Pareto-optimal on (query_coverage, probe_score)."""
    referenced_per_query: list[set[str]] = [
        _columns_referenced_in_sql(q.get("sql_query", "")) for q in queries
    ]
    n_queries = max(len(queries), 1)

    # Compute per-table average numeric_type_success_rate across probed configs
    table_probe_score: dict[str, float] = {}
    for table in schema.tables:
        rates: list[float] = []
        for signals in probe_data.tier1_signals.values():
            rate = signals.get("numeric_type_success_rate", 0.0)
            rates.append(rate)
        table_probe_score[table] = float(np.mean(rates)) if rates else 0.0

    # Build (query_coverage, probe_score) for each column
    col_coverage: dict[tuple[str, str], float] = {}
    col_probe: dict[tuple[str, str], float] = {}
    all_cols: list[tuple[str, str]] = []

    for table, cols in schema.tables.items():
        for col in cols:
            key = (table, col)
            all_cols.append(key)
            cov = sum(
                1 for refs in referenced_per_query if col.lower() in refs
            ) / n_queries
            col_coverage[key] = cov
            col_probe[key] = table_probe_score.get(table, 0.0)

    # Find Pareto frontier (no other column dominates on both dimensions)
    pareto: list[tuple[str, str]] = []
    for key in all_cols:
        c1, p1 = col_coverage[key], col_probe[key]
        dominated = False
        for other in all_cols:
            if other == key:
                continue
            c2, p2 = col_coverage[other], col_probe[other]
            if c2 >= c1 and p2 >= p1 and (c2 > c1 or p2 > p1):
                dominated = True
                break
        if not dominated:
            pareto.append(key)

    pareto_set = set(pareto)
    new_tables: dict[str, list[str]] = {}
    new_types: dict[str, dict[str, str]] = {}
    for table, cols in schema.tables.items():
        kept = [c for c in cols if (table, c) in pareto_set]
        if kept:
            new_tables[table] = kept
            new_types[table] = {
                c: schema.column_types.get(table, {}).get(c, "str") for c in kept
            }

    logger.info(
        "prune_schema_pareto: %d/%d Pareto-optimal columns retained",
        sum(len(v) for v in new_tables.values()),
        sum(len(v) for v in schema.tables.values()),
    )
    return Schema(
        dataset_name=schema.dataset_name,
        tables=new_tables,
        column_types=new_types,
        description=schema.description,
    )
