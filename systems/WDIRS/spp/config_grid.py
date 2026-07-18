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
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from spp.population_config import PopulationConfig, generate_config_space

FUZZY_THRESHOLD = 0.85


# ============================================================================
# Query execution against config-populated in-memory tables
# ============================================================================

def _build_in_memory_db(tables: Dict[str, List[Dict[str, Any]]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    for table_name, rows in tables.items():
        if not rows:
            continue
        columns = sorted({k for row in rows for k in row.keys()})
        col_defs = ", ".join(f'"{c}" TEXT' for c in columns)
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
    except Exception:
        return []


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
    """1 - F1 over row alignment with fuzzy cell matching. Lower is better."""
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


# ============================================================================
# Grid execution
# ============================================================================

@dataclass
class ConfigGridResult:
    per_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    n_queries: int = 0
    config_space_size: int = 0


def run_config_grid(
    runner: "Any",
    queries: List[Dict[str, Any]],
    ground_truth_tables: Dict[str, List[Dict[str, Any]]],
    *,
    config_space: Optional[List[PopulationConfig]] = None,
    required_tables_by_query: Optional[Dict[str, List[str]]] = None,
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

    for config in config_space:
        per_query_rows: List[Dict[str, Any]] = []
        populated_tables: Dict[str, List[Dict[str, Any]]] = {}

        for query in queries:
            qid = query.get("query_id", query.get("sql", "")[:40])
            sql = query["sql"]
            needed_tables = (
                required_tables_by_query.get(qid) if required_tables_by_query else None
            ) or _tables_for(sql)

            for table_name in needed_tables:
                if table_name not in populated_tables:
                    records, _diag = runner.materialize_population_config(table_name, config)
                    populated_tables[table_name] = records

            conn = _build_in_memory_db({t: populated_tables[t] for t in needed_tables})
            pred_rows = _execute_sql(conn, sql)
            conn.close()

            gt_conn = _build_in_memory_db(
                {t: ground_truth_tables[t] for t in needed_tables if t in ground_truth_tables}
            )
            gt_rows = _execute_sql(gt_conn, sql)
            gt_conn.close()

            err = query_error(gt_rows, pred_rows)
            per_query_rows.append(
                {
                    "query_id": qid,
                    "query_error": err,
                    "gold_rows": len(gt_rows),
                    "pred_rows": len(pred_rows),
                }
            )

        errs = [r["query_error"] for r in per_query_rows]
        result.per_config[config.config_id] = {
            "mean_query_error": sum(errs) / len(errs) if errs else None,
            "per_query": per_query_rows,
        }

    return result


# ============================================================================
# Viable-config-search-space report (matches spp-agent's report shape)
# ============================================================================

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

    ever_optimal: set = set()
    for qid in query_ids:
        best_err = None
        for cid in config_ids:
            row = next(
                (r for r in per_config[cid].get("per_query", []) if r["query_id"] == qid), None
            )
            if row is None or row["query_error"] is None:
                continue
            if best_err is None or row["query_error"] < best_err - tie_epsilon:
                best_err = row["query_error"]
        if best_err is None:
            continue
        for cid in config_ids:
            row = next(
                (r for r in per_config[cid].get("per_query", []) if r["query_id"] == qid), None
            )
            if row is not None and row["query_error"] is not None and abs(row["query_error"] - best_err) <= tie_epsilon:
                ever_optimal.add(cid)

    never_optimal = [cid for cid in config_ids if cid not in ever_optimal]

    return {
        "report_type": "viable_config_search_space",
        "full_config_space_size": grid.config_space_size,
        "n_evaluated_configs": len(config_ids),
        "n_queries": len(query_ids),
        "n_ever_optimal": len(ever_optimal),
        "n_never_optimal": len(never_optimal),
        "ever_optimal_fraction_of_evaluated": (
            len(ever_optimal) / len(config_ids) if config_ids else 0.0
        ),
        "ever_optimal_config_ids": sorted(ever_optimal),
        "never_optimal_config_ids": sorted(never_optimal),
        "pruning_note": (
            "never_optimal_config_ids never appear in the tied-best set for any "
            "scored query on THIS WDIRS-extraction run; compare against "
            "spp-agent's own viable_config_search_space.json to see whether "
            "extraction quality changes which configs are prunable."
        ),
    }
