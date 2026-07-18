"""Phase 4 — Lean, budget-aware routing layer: cluster -> WDIRS PopulationConfig.

Per the migration plan, this deliberately skips spp-agent's full
surrogate/BTL-judge/ILP stack. It ranks candidate configs purely by
glass-box signals (`spp.population.PopulationDiagnostics`, computed with NO
ground-truth access) and reuses the budget/greedy materialization-reuse
idea from spp-agent's `stage3/routing_assignment.py`, reimplemented against
WDIRS's own (population-replay) cost accounting instead of spp-agent's
token-cost model.

If Phase 2's grid shows glass-box signals alone can't discriminate configs
well, `assign_configs_to_clusters` accepts an optional `judge_fn` hook so
BTL/LLM-judge style pairwise comparison can be added later without
reworking the routing loop -- but by default it is unused.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from spp.population import PopulationDiagnostics
from spp.population_config import PopulationConfig
from spp.query_clustering import QueryClusters

logger = logging.getLogger(__name__)


@dataclass
class TokenBudget:
    """Tracks a simple spend-down budget for materializing configs."""

    total: float
    spent: float = 0.0

    @property
    def remaining(self) -> float:
        return self.total - self.spent

    def spend(self, amount: float, *, label: str = "") -> None:
        self.spent += amount
        logger.info("Spent %.2f on %s (remaining=%.2f)", amount, label, self.remaining)


def estimate_config_marginal_cost(config: PopulationConfig, n_rows: int) -> float:
    """Marginal materialization cost of one PopulationConfig, in WDIRS's own
    units (rough proxy: 1 unit per row per LLM-backed axis touched).

    Extraction is shared/free at this point (Phase 1); only the LLM-backed
    population axes (er="llm", norm="llm", miss="llm") cost anything --
    embedding/dictionary/rule-based axes are ~free CPU-only replays.
    """
    llm_axes = sum(
        1
        for value in (config.er_strategy, config.norm_strategy, config.miss_strategy)
        if value == "llm"
    )
    return float(llm_axes * n_rows)


@dataclass
class RoutingTable:
    cluster_to_config: Dict[int, str]
    selected_configs: List[str]
    cluster_types: Dict[int, str]
    assignment_scores: Dict[int, float]
    n_materializations: int
    token_cost_estimate: float


def _glass_box_score_for_cluster(
    config_id: str,
    cluster_type: str,
    diagnostics_by_config: Dict[str, Dict[str, PopulationDiagnostics]],
    *,
    default_table: Optional[str] = None,
) -> float:
    """Average glass-box composite across all tables materialized for this
    config, optionally weighted toward the cluster's most relevant table.
    """
    per_table = diagnostics_by_config.get(config_id, {})
    if not per_table:
        return 0.0
    if default_table and default_table in per_table:
        return per_table[default_table].glass_box_composite()
    return sum(d.glass_box_composite() for d in per_table.values()) / len(per_table)


def assign_configs_to_clusters(
    query_clusters: QueryClusters,
    candidate_configs: List[PopulationConfig],
    diagnostics_by_config: Dict[str, Dict[str, PopulationDiagnostics]],
    *,
    token_budget: Optional[TokenBudget] = None,
    n_rows_by_table: Optional[Dict[str, int]] = None,
    cluster_primary_table: Optional[Dict[int, str]] = None,
    judge_fn: Optional[Callable[[int, str, str], float]] = None,
) -> RoutingTable:
    """Assign each query cluster to a WDIRS PopulationConfig, honoring a
    materialization budget and reusing already-materialized configs across
    clusters when possible (greedy, largest clusters first -- same
    heuristic as spp-agent's routing_assignment.py).

    `diagnostics_by_config[config_id][table_name]` supplies glass-box
    signals for that config on that table (no ground truth).
    `judge_fn(cluster_id, config_id_a, config_id_b) -> preference score`
    is an optional escape hatch for later BTL/LLM-judge style refinement;
    unused by default per the plan's "skip unless proven necessary" guidance.
    """
    n_rows_by_table = n_rows_by_table or {}
    cluster_primary_table = cluster_primary_table or {}
    token_budget = token_budget or TokenBudget(total=float("inf"))

    sizes = {cid: len(qs) for cid, qs in query_clusters.cluster_to_queries.items()}
    sorted_clusters = sorted(
        range(query_clusters.n_clusters), key=lambda cid: sizes.get(cid, 0), reverse=True
    )

    materialized: set = set()
    routing: Dict[int, str] = {}
    scores: Dict[int, float] = {}
    token_cost = 0.0

    config_by_id = {c.config_id: c for c in candidate_configs}

    for cluster_id in sorted_clusters:
        cluster_type = query_clusters.cluster_types.get(cluster_id, "mixed")
        primary_table = cluster_primary_table.get(cluster_id)
        n_rows = n_rows_by_table.get(primary_table, 0) if primary_table else 0

        ranked = sorted(
            candidate_configs,
            key=lambda c: _glass_box_score_for_cluster(
                c.config_id, cluster_type, diagnostics_by_config, default_table=primary_table
            ),
            reverse=True,
        )

        assigned = False
        for config in ranked:
            cid = config.config_id
            score = _glass_box_score_for_cluster(
                cid, cluster_type, diagnostics_by_config, default_table=primary_table
            )
            if judge_fn is not None and materialized:
                # Optional escape hatch: compare against best-so-far materialized config.
                current_best = max(
                    materialized,
                    key=lambda m: _glass_box_score_for_cluster(
                        m, cluster_type, diagnostics_by_config, default_table=primary_table
                    ),
                )
                preference = judge_fn(cluster_id, cid, current_best)
                if preference <= 0:
                    continue

            if cid in materialized:
                routing[cluster_id] = cid
                scores[cluster_id] = score
                assigned = True
                break

            marginal = estimate_config_marginal_cost(config, n_rows)
            if token_budget.remaining >= marginal:
                if marginal > 0:
                    token_budget.spend(marginal, label=f"materialize:{cid}")
                    token_cost += marginal
                materialized.add(cid)
                routing[cluster_id] = cid
                scores[cluster_id] = score
                assigned = True
                break

        if not assigned:
            if materialized:
                fallback = max(
                    materialized,
                    key=lambda m: _glass_box_score_for_cluster(
                        m, cluster_type, diagnostics_by_config, default_table=primary_table
                    ),
                )
                routing[cluster_id] = fallback
                scores[cluster_id] = _glass_box_score_for_cluster(
                    fallback, cluster_type, diagnostics_by_config, default_table=primary_table
                )
            elif ranked:
                fallback = ranked[0]
                routing[cluster_id] = fallback.config_id
                scores[cluster_id] = _glass_box_score_for_cluster(
                    fallback.config_id, cluster_type, diagnostics_by_config, default_table=primary_table
                )
                materialized.add(fallback.config_id)

    selected_configs = sorted(set(routing.values()))
    logger.info(
        "Routing assignment: clusters=%d materializations=%d token_cost=%.2f",
        len(routing),
        len(selected_configs),
        token_cost,
    )

    return RoutingTable(
        cluster_to_config=routing,
        selected_configs=selected_configs,
        cluster_types=dict(query_clusters.cluster_types),
        assignment_scores=scores,
        n_materializations=len(selected_configs),
        token_cost_estimate=token_cost,
    )


def deterministic_routing_fallback(
    query_clusters: QueryClusters,
    diagnostics_by_config: Dict[str, Dict[str, PopulationDiagnostics]],
) -> RoutingTable:
    """Assign the single globally-best glass-box config to every cluster.
    Used when no budget information or per-cluster signal is available.
    """
    global_scores = {
        cid: sum(d.glass_box_composite() for d in tables.values()) / max(len(tables), 1)
        for cid, tables in diagnostics_by_config.items()
    }
    best = max(global_scores, key=global_scores.get) if global_scores else ""
    routing = {cid: best for cid in range(query_clusters.n_clusters)}
    return RoutingTable(
        cluster_to_config=routing,
        selected_configs=[best] if best else [],
        cluster_types=dict(query_clusters.cluster_types),
        assignment_scores={cid: global_scores.get(best, 0.0) for cid in routing},
        n_materializations=1 if best else 0,
        token_cost_estimate=0.0,
    )
