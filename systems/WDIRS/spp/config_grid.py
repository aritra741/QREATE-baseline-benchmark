"""Phase 2 — Brute-force config grid diagnostic, run against WDIRS-quality
extraction instead of spp-agent's own extractor.

This mirrors spp-agent's `diagnostics/config_grid_test` +
`viable_config_search_space` report (see
systems/spp-agent/results/Art/config_grid_test_Art/viable_config_search_space.json)
but sources its records from `WDIRSRunner.materialize_population_config`
(Phase 1) so extraction quality is WDIRS's, not spp-agent's.

Usage (requires a WDIRSRunner that has already run `.preprocess(...)` once
for the dataset -- extraction is shared/expensive; population is replayed
cheaply per config):

    from wdirs_runner import WDIRSRunner
    from spp.config_grid import run_config_grid, build_viable_config_search_space

    runner = WDIRSRunner("Player")
    runner.preprocess(workload_queries=[...])
    grid = run_config_grid(runner, queries, ground_truth_tables)
    viable = build_viable_config_search_space(grid)
"""

from __future__ import annotations

import re
import sqlite3
import logging
import sys
from pathlib import Path
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Mapping, Optional

from spp.population_config import PopulationConfig, generate_config_space
from token_counter import TokenBudgetExceeded

FUZZY_THRESHOLD = 0.85
logger = logging.getLogger(__name__)


class SQLExecutionError(RuntimeError):
    """Raised when a diagnostic SQL query cannot be evaluated."""


def _sqlite_affinity(values: List[Any], declared_type: Optional[str] = None) -> str:
    if declared_type in {"MONEY", "QUANTITY", "QUANTITY_COUNT", "REAL", "NUMERIC", "INTEGER"}:
        return "NUMERIC"
    non_null = [v for v in values if v not in (None, "")]
    if non_null:
        for value in non_null:
            try:
                float(str(value).strip().replace(",", ""))
            except (TypeError, ValueError):
                return "TEXT"
        return "NUMERIC"
    return "TEXT"


# ============================================================================
# Query execution against config-populated in-memory tables
# ============================================================================

def _build_in_memory_db(
    tables: Dict[str, List[Dict[str, Any]]],
    table_schemas: Optional[Dict[str, Dict[str, str]]] = None,
) -> sqlite3.Connection:
    """Build a throwaway in-memory SQLite DB from populated/ground-truth rows.

    Affinity is schema/value-aware. Declared numeric columns and columns whose
    non-null values are all numeric-looking use NUMERIC; genuine text uses
    TEXT. Declaring everything TEXT breaks numeric predicates, while declaring
    everything NUMERIC corrupts numeric-looking identifiers (for example,
    leading-zero codes).
    """
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    for table_name, rows in tables.items():
        declared = (table_schemas or {}).get(table_name, {})
        columns = sorted({*declared.keys(), *(k for row in rows for k in row.keys())})
        if not columns:
            continue
        col_defs = ", ".join(
            f'"{c}" {_sqlite_affinity([row.get(c) for row in rows], declared.get(c))}'
            for c in columns
        )
        cursor.execute(f'CREATE TABLE "{table_name}" ({col_defs})')
        placeholders = ", ".join("?" for _ in columns)
        for row in rows:
            values = [row.get(c) for c in columns]
            cursor.execute(f'INSERT INTO "{table_name}" VALUES ({placeholders})', values)
    conn.commit()
    return conn


def _execute_sql(conn: sqlite3.Connection, query: str) -> List[Dict[str, Any]]:
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as exc:
        raise SQLExecutionError(f"SQL execution failed for {query!r}: {exc}") from exc


# ============================================================================
# Row-aligned, cell-level scoring (simplified UDA-Bench-style F1)
# ============================================================================

def _norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _fuzzy_equal(a: Any, b: Any) -> bool:
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return True
    if not na or not nb:
        return False
    return SequenceMatcher(None, na, nb).ratio() >= FUZZY_THRESHOLD


def query_error(gt_rows: List[Dict[str, Any]], pred_rows: List[Dict[str, Any]]) -> float:
    """Legacy lightweight row-F1 diagnostic. Lower is better.

    This is intentionally not labeled as the official UDA-Bench metric. HPC
    grid runs pass ``official_query_error`` into ``run_config_grid`` instead.
    """
    if not gt_rows and not pred_rows:
        return 0.0
    if not gt_rows or not pred_rows:
        return 1.0

    columns = list(gt_rows[0].keys())
    unmatched_pred = list(range(len(pred_rows)))
    tp = 0
    for gt_row in gt_rows:
        match_idx = None
        for i in unmatched_pred:
            if all(_fuzzy_equal(gt_row.get(c), pred_rows[i].get(c)) for c in columns):
                match_idx = i
                break
        if match_idx is not None:
            tp += 1
            unmatched_pred.remove(match_idx)

    fp = len(pred_rows) - tp
    fn = len(gt_rows) - tp
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return 1.0 - f1


def official_query_error(
    sql: str,
    gt_rows: List[Dict[str, Any]],
    pred_rows: List[Dict[str, Any]],
    attributes: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> float:
    """Compute 1 - official UDA-Bench column macro-F1 without evaluator LLMs."""
    # Macro-F1 is undefined on two empty frames, but query-answer correctness
    # is not: predicting no rows for a genuinely empty gold result is exact.
    if not gt_rows:
        return 0.0 if not pred_rows else 1.0

    import pandas as pd

    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from evaluation.config import EvalSettings
    from evaluation.metrics import MetricCalculator
    from evaluation.query_manifest import QueryManifest
    from evaluation.row_matcher import RowMatcher
    from evaluation.sql_parser import SqlParser
    from evaluation.utils import (
        add_missing_columns,
        clean_string_columns,
        normalize_types,
        standardize_column_name,
    )

    parser = SqlParser()
    settings = EvalSettings(llm_provider="none")
    manifest = QueryManifest(sql, parser.parse(sql), attributes)

    def _frame(rows: List[Dict[str, Any]]) -> "pd.DataFrame":
        frame = pd.DataFrame(rows)
        frame = frame.rename(
            columns={column: standardize_column_name(column) for column in frame.columns}
        )
        frame = add_missing_columns(frame, manifest.parsed.output_columns)
        frame = add_missing_columns(frame, manifest.stop_columns)
        frame = clean_string_columns(frame)
        return normalize_types(frame, attributes)

    gold_df = _frame(gt_rows)
    pred_df = _frame(pred_rows)
    keys = []
    for key in manifest.primary_keys:
        candidates = [key, key.split(".", 1)[-1]]
        chosen = next(
            (
                candidate
                for candidate in candidates
                if candidate in gold_df.columns and candidate in pred_df.columns
            ),
            None,
        )
        if chosen and chosen not in keys:
            keys.append(chosen)

    if not keys:
        # Aggregate-only queries generally yield one row. For non-aggregate
        # queries, use projected columns as deterministic alignment keys.
        keys = [
            column
            for column in manifest.parsed.output_columns
            if column in gold_df.columns and column in pred_df.columns
        ]

    for key in keys:
        for frame in (gold_df, pred_df):
            if key in frame.columns:
                frame[key] = frame[key].map(
                    lambda value: value.lower().strip()
                    if isinstance(value, str)
                    else value
                )

    if not keys:
        # Both frames have no evaluable output columns.
        return 0.0 if gold_df.empty and pred_df.empty else 1.0

    match_result = RowMatcher(settings=settings).match(
        gold_df=gold_df,
        pred_df=pred_df,
        primary_keys=keys,
        attr_descriptions=attributes,
        query_type=manifest.parsed.query_type,
    )
    metrics = MetricCalculator(manifest, settings).compute(match_result)
    return 1.0 - float(metrics["macro_f1"])


# ============================================================================
# Grid execution
# ============================================================================

@dataclass
class ConfigGridResult:
    per_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    n_queries: int = 0
    config_space_size: int = 0
    stopped_early: bool = False
    stop_reason: Optional[str] = None


def run_config_grid(
    runner: "Any",
    queries: List[Dict[str, Any]],
    ground_truth_tables: Dict[str, List[Dict[str, Any]]],
    *,
    config_space: Optional[List[PopulationConfig]] = None,
    required_tables_by_query: Optional[Dict[str, List[str]]] = None,
    query_error_fn: Optional[
        Callable[[str, List[Dict[str, Any]], List[Dict[str, Any]]], float]
    ] = None,
) -> ConfigGridResult:
    """Run every config in `config_space` against WDIRS's shared extraction
    (via `runner.materialize_population_config`) and score each query.

    `queries` entries: {"query_id": str, "sql": str}.
    `required_tables_by_query`: optional override; defaults to every table
    referenced via a naive FROM/JOIN scan of the SQL text.
    """
    config_space = config_space or generate_config_space()
    result = ConfigGridResult(n_queries=len(queries), config_space_size=len(config_space))

    all_tables = list(ground_truth_tables.keys())

    def _tables_for(sql: str) -> List[str]:
        found = re.findall(r"(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE)
        found = [t for t in found if t in all_tables]
        return found or all_tables

    query_specs: List[Dict[str, Any]] = []
    for query in queries:
        qid = query.get("query_id", query.get("sql", "")[:40])
        sql = query["sql"]
        needed_tables = (
            required_tables_by_query.get(qid) if required_tables_by_query else None
        ) or _tables_for(sql)
        gt_error = None
        gt_rows: List[Dict[str, Any]] = []
        try:
            gt_conn = _build_in_memory_db(
                {t: ground_truth_tables[t] for t in needed_tables if t in ground_truth_tables}
            )
            gt_rows = _execute_sql(gt_conn, sql)
            gt_conn.close()
        except SQLExecutionError as exc:
            gt_error = str(exc)
            logger.error("Ground-truth query is invalid; excluding %s: %s", qid, exc)
        query_specs.append(
            {
                "query_id": qid,
                "sql": sql,
                "tables": needed_tables,
                "gt_rows": gt_rows,
                "gt_error": gt_error,
            }
        )
    required_table_names = sorted(
        {table for spec in query_specs for table in spec["tables"]}
    )

    for config in config_space:
        per_query_rows: List[Dict[str, Any]] = []
        try:
            if hasattr(runner, "materialize_population_tables"):
                populated_tables = runner.materialize_population_tables(
                    required_table_names, config
                )
            else:
                populated_tables = {
                    table_name: runner.materialize_population_config(
                        table_name, config
                    )[0]
                    for table_name in required_table_names
                }
        except TokenBudgetExceeded as exc:
            result.stopped_early = True
            result.stop_reason = str(exc)
            break

        for spec in query_specs:
            qid = spec["query_id"]
            sql = spec["sql"]
            needed_tables = spec["tables"]

            table_schemas = {
                t: runner.lattice_planner.get_table_schema(t) for t in needed_tables
            }
            pred_rows: List[Dict[str, Any]] = []
            pred_error = None
            try:
                conn = _build_in_memory_db(
                    {t: populated_tables[t] for t in needed_tables},
                    table_schemas=table_schemas,
                )
                pred_rows = _execute_sql(conn, sql)
                conn.close()
            except SQLExecutionError as exc:
                pred_error = str(exc)
                logger.error("Populated query failed for %s / %s: %s", qid, config.config_id, exc)

            gt_rows = spec["gt_rows"]
            sql_error = spec["gt_error"] or pred_error
            err = (
                None
                if sql_error
                else (
                    query_error_fn(sql, gt_rows, pred_rows)
                    if query_error_fn
                    else query_error(gt_rows, pred_rows)
                )
            )
            per_query_rows.append(
                {
                    "query_id": qid,
                    "sql": sql,
                    "tables_used": needed_tables,
                    "query_error": err,
                    "gold_rows": len(gt_rows),
                    "pred_rows": len(pred_rows),
                    "sql_error": sql_error,
                    "populated_table_sizes": {t: len(populated_tables.get(t, [])) for t in needed_tables},
                }
            )

        errs = [r["query_error"] for r in per_query_rows if r["query_error"] is not None]
        result.per_config[config.config_id] = {
            "mean_query_error": sum(errs) / len(errs) if errs else None,
            "per_query": per_query_rows,
        }

    return result


# ============================================================================
# Viable-config-search-space report (matches spp-agent's report shape)
# ============================================================================

def summarize_query_sensitivity(
    grid: ConfigGridResult, *, tie_epsilon: float = 1e-9
) -> Dict[str, Any]:
    """Classify each query as config-sensitive (its error varies across the
    evaluated config space) or config-insensitive (identical error for
    every config -- usually a sign of an extraction-quality floor/ceiling
    that no PopulationConfig axis can move, e.g. a WHERE-value the base
    extraction never got right, or a JOIN whose keys never align, rather
    than a real "config doesn't matter" finding).

    This is diagnostic-only: it's what makes a flat `ever_optimal` fraction
    (e.g. 100%) interpretable instead of mysterious.
    """
    per_config = grid.per_config
    config_ids = list(per_config.keys())
    if not config_ids:
        return {"n_queries": 0, "n_config_sensitive": 0, "n_config_insensitive": 0, "queries": []}

    by_query: Dict[str, List[Dict[str, Any]]] = {}
    for cid in config_ids:
        for row in per_config[cid].get("per_query", []):
            by_query.setdefault(row["query_id"], []).append({**row, "config_id": cid})

    sensitive: List[Dict[str, Any]] = []
    insensitive: List[Dict[str, Any]] = []
    for qid, rows in by_query.items():
        errors = [r["query_error"] for r in rows if r["query_error"] is not None]
        if not errors:
            continue
        spread = max(errors) - min(errors)
        sample = rows[0]
        summary = {
            "query_id": qid,
            "sql": sample.get("sql"),
            "tables_used": sample.get("tables_used"),
            "gold_rows": sample.get("gold_rows"),
            "error_spread": spread,
            "min_error": min(errors),
            "max_error": max(errors),
            "pred_rows_range": [
                min(r["pred_rows"] for r in rows),
                max(r["pred_rows"] for r in rows),
            ],
        }
        if spread <= tie_epsilon:
            insensitive.append(summary)
        else:
            sensitive.append(summary)

    return {
        "n_queries": len(by_query),
        "n_config_sensitive": len(sensitive),
        "n_config_insensitive": len(insensitive),
        "config_sensitive_queries": sorted(sensitive, key=lambda s: -s["error_spread"]),
        "config_insensitive_queries": insensitive,
        "note": (
            "Config-insensitive queries had identical valid error across every "
            "evaluated config. They may be stably correct, extraction-limited, "
            "or genuinely unaffected by these axes. They provide no evidence "
            "for retaining or pruning an individual config."
        ),
    }


def build_viable_config_search_space(grid: ConfigGridResult, *, tie_epsilon: float = 1e-9) -> Dict[str, Any]:
    """For each query, find the tied-best (lowest query_error) config(s).
    A config is "ever_optimal" if it is tied-best for at least one query.
    """
    per_config = grid.per_config
    config_ids = list(per_config.keys())

    query_ids: List[str] = []
    for entry in per_config.values():
        for row in entry.get("per_query", []):
            qid = row["query_id"]
            if qid not in query_ids:
                query_ids.append(qid)

    ever_optimal_all_queries: set = set()
    ever_optimal: set = set()
    strictly_optimal: set = set()
    discriminative_query_ids: List[str] = []
    n_discriminative_queries = 0
    for qid in query_ids:
        errors_by_config: Dict[str, float] = {}
        for cid in config_ids:
            row = next(
                (r for r in per_config[cid].get("per_query", []) if r["query_id"] == qid), None
            )
            if row is None or row["query_error"] is None:
                continue
            errors_by_config[cid] = row["query_error"]
        if not errors_by_config:
            continue
        best_err = min(errors_by_config.values())
        best_ids = {
            cid
            for cid, error in errors_by_config.items()
            if abs(error - best_err) <= tie_epsilon
        }
        ever_optimal_all_queries.update(best_ids)
        if max(errors_by_config.values()) - min(errors_by_config.values()) > tie_epsilon:
            n_discriminative_queries += 1
            discriminative_query_ids.append(qid)
            ever_optimal.update(best_ids)
            if len(best_ids) == 1:
                strictly_optimal.update(best_ids)

    never_optimal = [cid for cid in config_ids if cid not in ever_optimal]
    profile_groups: Dict[tuple, List[str]] = {}
    for cid in config_ids:
        rows_by_qid = {
            row["query_id"]: row.get("query_error")
            for row in per_config[cid].get("per_query", [])
        }
        profile = tuple(
            None
            if rows_by_qid.get(qid) is None
            else round(float(rows_by_qid[qid]), 12)
            for qid in discriminative_query_ids
        )
        profile_groups.setdefault(profile, []).append(cid)
    equivalent_groups = [
        sorted(group)
        for group in profile_groups.values()
        if len(group) > 1
    ]
    optimal_profile_groups = [
        sorted(group)
        for group in profile_groups.values()
        if any(cid in ever_optimal for cid in group)
    ]
    representative_optimal_ids = sorted(
        group[0] for group in optimal_profile_groups
    )

    return {
        "report_type": "viable_config_search_space",
        "full_config_space_size": grid.config_space_size,
        "n_evaluated_configs": len(config_ids),
        "n_queries": len(query_ids),
        "n_discriminative_queries": n_discriminative_queries,
        "n_ever_optimal": len(ever_optimal),
        "n_strictly_optimal": len(strictly_optimal),
        "strictly_optimal_config_ids": sorted(strictly_optimal),
        "n_never_optimal": len(never_optimal),
        "ever_optimal_fraction_of_evaluated": (
            len(ever_optimal) / len(config_ids) if config_ids else 0.0
        ),
        "ever_optimal_config_ids": sorted(ever_optimal),
        "n_ever_optimal_including_flat_queries": len(ever_optimal_all_queries),
        "ever_optimal_config_ids_including_flat_queries": sorted(
            ever_optimal_all_queries
        ),
        "never_optimal_config_ids": sorted(never_optimal),
        "n_behaviorally_distinct_error_profiles": len(profile_groups),
        "n_ever_optimal_error_profiles": len(optimal_profile_groups),
        "representative_ever_optimal_config_ids": representative_optimal_ids,
        "equivalent_config_groups": equivalent_groups,
        "pruning_note": (
            "Primary ever/never-optimal counts use only config-sensitive queries. "
            "Flat queries are excluded because one flat query makes every config "
            "tied-best and otherwise forces a meaningless 100% result. "
            "never_optimal_config_ids never appear in a tied-best set for any "
            "sensitive scored query on THIS WDIRS-extraction run; compare against "
            "spp-agent's own viable_config_search_space.json to see whether "
            "extraction quality changes which configs are prunable. Configs in "
            "an equivalent_config_group have identical error vectors on every "
            "sensitive query and can be represented by one member for this run."
        ),
    }
