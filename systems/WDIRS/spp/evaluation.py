"""Phase 5 — Ground-truth-firewalled evaluation harness.

Scores a WDIRS-backed `RoutingTable` (Phase 4) against UDA-Bench ground
truth, reusing the row-aligned cell-level `Error` definition from Phase 2's
`config_grid.query_error` (which already matches UDA-Bench's evaluation
protocol, per the migration plan).

GROUND-TRUTH FIREWALL: every function in this module takes
`ground_truth_tables` explicitly and is only ever meant to be called
*offline*, after routing decisions (Phase 4) have already been made using
glass-box signals alone. Nothing in `spp/routing.py` or `spp/population.py`
imports this module or receives ground truth -- config/routing selection
must never see it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Dict, List, Optional

from spp.config_grid import _build_in_memory_db, _execute_sql, query_error
from spp.population_config import PopulationConfig, parse_config_id
from spp.query_clustering import QueryClusters
from spp.routing import RoutingTable

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    routed_error: float
    oracle_min_error: float
    regret: float
    per_query_errors: Dict[str, float] = field(default_factory=dict)
    n_queries_scored: int = 0
    selected_configs: List[str] = field(default_factory=list)


def _tables_for_sql(sql: str, all_tables: List[str]) -> List[str]:
    import re

    found = re.findall(r"(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE)
    found = [t for t in found if t in all_tables]
    return found or all_tables


def _populate_and_run(
    runner: Any,
    config: PopulationConfig,
    sql: str,
    tables_needed: List[str],
    cache: Dict[str, Dict[str, List[dict]]],
) -> List[dict]:
    key = config.config_id
    populated = cache.setdefault(key, {})
    for table_name in tables_needed:
        if table_name not in populated:
            records, _diag = runner.materialize_population_config(table_name, config)
            populated[table_name] = records

    conn = _build_in_memory_db({t: populated[t] for t in tables_needed})
    rows = _execute_sql(conn, sql)
    conn.close()
    return rows


def routed_error(
    routing_table: RoutingTable,
    query_clusters: QueryClusters,
    queries: List[Dict[str, Any]],
    runner: Any,
    ground_truth_tables: Dict[str, List[dict]],
    *,
    materialization_cache: Optional[Dict[str, Dict[str, List[dict]]]] = None,
) -> "tuple[float, Dict[str, float]]":
    """Average query error obtained by executing each query against the
    PopulationConfig its cluster was routed to. This IS ground-truth-firewalled
    at the routing-decision level: `routing_table` was built in Phase 4
    without ever seeing `ground_truth_tables`; ground truth is used here
    only to *score* that already-fixed decision.
    """
    if not queries:
        return float("nan"), {}

    cache = materialization_cache if materialization_cache is not None else {}
    all_tables = list(ground_truth_tables.keys())
    labels = query_clusters.labels
    per_query_errors: Dict[str, float] = {}

    for idx, query in enumerate(queries):
        if idx >= len(labels):
            break
        cluster_id = labels[idx]
        config_id = routing_table.cluster_to_config.get(cluster_id)
        if not config_id:
            continue

        qid = query.get("query_id", query.get("sql", "")[:40])
        sql = query["sql"]
        tables_needed = _tables_for_sql(sql, all_tables)

        config = parse_config_id(config_id)
        pred_rows = _populate_and_run(runner, config, sql, tables_needed, cache)

        gt_conn = _build_in_memory_db({t: ground_truth_tables[t] for t in tables_needed})
        gt_rows = _execute_sql(gt_conn, sql)
        gt_conn.close()

        per_query_errors[qid] = query_error(gt_rows, pred_rows)

    if not per_query_errors:
        return float("nan"), {}
    return float(mean(per_query_errors.values())), per_query_errors


def oracle_min_error(
    candidate_configs: List[PopulationConfig],
    queries: List[Dict[str, Any]],
    runner: Any,
    ground_truth_tables: Dict[str, List[dict]],
    *,
    materialization_cache: Optional[Dict[str, Dict[str, List[dict]]]] = None,
) -> "tuple[str, float]":
    """True (ground-truth-using, offline-only) oracle: the single BEST
    PopulationConfig across the whole workload, i.e. an upper bound on what
    any *unrouted* (single-config) baseline could achieve. This is strictly
    for offline reporting -- never fed back into Phase 4's routing logic.
    """
    if not queries or not candidate_configs:
        return "", float("nan")

    cache = materialization_cache if materialization_cache is not None else {}
    all_tables = list(ground_truth_tables.keys())

    best_config_id = ""
    best_error = float("inf")
    for config in candidate_configs:
        errs = []
        for query in queries:
            sql = query["sql"]
            tables_needed = _tables_for_sql(sql, all_tables)
            pred_rows = _populate_and_run(runner, config, sql, tables_needed, cache)
            gt_conn = _build_in_memory_db({t: ground_truth_tables[t] for t in tables_needed})
            gt_rows = _execute_sql(gt_conn, sql)
            gt_conn.close()
            errs.append(query_error(gt_rows, pred_rows))
        mean_err = mean(errs) if errs else float("nan")
        if mean_err == mean_err and mean_err < best_error:
            best_error = mean_err
            best_config_id = config.config_id

    return best_config_id, best_error if best_error != float("inf") else float("nan")


def per_query_oracle_error(
    candidate_configs: List[PopulationConfig],
    queries: List[Dict[str, Any]],
    runner: Any,
    ground_truth_tables: Dict[str, List[dict]],
    *,
    materialization_cache: Optional[Dict[str, Dict[str, List[dict]]]] = None,
) -> float:
    """Strongest oracle bound: best config PER QUERY (perfect, unbounded
    routing). Reported alongside oracle_min_error (best SINGLE config) so
    Phase 4's routing regret can be read against both bounds.
    """
    if not queries or not candidate_configs:
        return float("nan")

    cache = materialization_cache if materialization_cache is not None else {}
    all_tables = list(ground_truth_tables.keys())

    per_query_best: List[float] = []
    for query in queries:
        sql = query["sql"]
        tables_needed = _tables_for_sql(sql, all_tables)
        gt_conn = _build_in_memory_db({t: ground_truth_tables[t] for t in tables_needed})
        gt_rows = _execute_sql(gt_conn, sql)
        gt_conn.close()

        best_err = float("inf")
        for config in candidate_configs:
            pred_rows = _populate_and_run(runner, config, sql, tables_needed, cache)
            err = query_error(gt_rows, pred_rows)
            best_err = min(best_err, err)
        per_query_best.append(best_err)

    return float(mean(per_query_best)) if per_query_best else float("nan")


def evaluate_routing(
    routing_table: RoutingTable,
    query_clusters: QueryClusters,
    queries: List[Dict[str, Any]],
    runner: Any,
    ground_truth_tables: Dict[str, List[dict]],
    candidate_configs: List[PopulationConfig],
) -> EvaluationResult:
    """Full Phase 5 evaluation: routed_error, oracle_min_error (best single
    config, ground-truth-using, offline-only), and regret.
    """
    cache: Dict[str, Dict[str, List[dict]]] = {}

    r_err, per_query = routed_error(
        routing_table, query_clusters, queries, runner, ground_truth_tables,
        materialization_cache=cache,
    )
    _best_config_id, o_err = oracle_min_error(
        candidate_configs, queries, runner, ground_truth_tables,
        materialization_cache=cache,
    )

    regret = r_err - o_err if r_err == r_err and o_err == o_err else float("nan")

    logger.info(
        "evaluate_routing: routed_error=%.4f oracle_min_error=%.4f regret=%.4f",
        r_err if r_err == r_err else float("nan"),
        o_err if o_err == o_err else float("nan"),
        regret if regret == regret else float("nan"),
    )

    return EvaluationResult(
        routed_error=r_err,
        oracle_min_error=o_err,
        regret=regret,
        per_query_errors=per_query,
        n_queries_scored=len(per_query),
        selected_configs=routing_table.selected_configs,
    )
