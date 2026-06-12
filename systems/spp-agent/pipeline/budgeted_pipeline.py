"""Budgeted SPP pipeline (replaces BTL / glass-box / cluster routing)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.budgeted_loop import BudgetedRunResult, run_budgeted_agent_loop
from utils.logging import setup_logger

logger = setup_logger("spp.budgeted_pipeline")


@dataclass
class QueryRoutingTable:
    query_to_config: dict[str, str] = field(default_factory=dict)

    @property
    def cluster_to_config(self) -> dict[str, str]:
        """Legacy compat for cluster-based routing callers."""
        return {}


@dataclass
class BudgetedPipelineResult:
    selected_configs: list[str]
    routing_table: QueryRoutingTable
    demand_profile: dict[str, Any]
    supply_profile: dict[str, Any]
    probed_configs: list[dict[str, Any]]
    budget_summary: dict[str, Any]
    rounds: int
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    databases: dict[str, dict] = field(default_factory=dict)
    catalog_id_to_pipe: dict[str, str] = field(default_factory=dict)

    # Compatibility fields for legacy callers
    best_surrogate: str = "budgeted_agent"
    best_algorithm: str = "per_query_routing"
    token_budget_total: int = 0
    token_budget_spent: int = 0
    token_budget_remaining: int = 0
    n_configs_selected: int = 0


def run_budgeted_spp_pipeline(
    instance,
    *,
    token_budget: int | None = None,
    max_rounds: int = 20,
    use_heuristic_agent: bool = False,
    use_heuristic_demand: bool = False,
    shared_extraction=None,
) -> BudgetedPipelineResult:
    """
    Run Phases 0–3: demand profile → supply profile → config catalog → agent loop.
    No BTL, glass-box, or cluster routing.
    """
    logger.info(
        "Starting budgeted SPP pipeline docs=%d queries=%d budget=%s",
        len(instance.corpus),
        len(instance.queries),
        token_budget,
    )
    run: BudgetedRunResult = run_budgeted_agent_loop(
        instance,
        token_budget_total=token_budget,
        max_rounds=max_rounds,
        use_heuristic_agent=use_heuristic_agent,
        use_heuristic_demand=use_heuristic_demand,
        shared_extraction=shared_extraction,
    )
    selected = [p.get("pipe_config_id", p["config_id"]) for p in run.probed_configs]
    budget = run.budget_summary
    return BudgetedPipelineResult(
        selected_configs=selected,
        routing_table=QueryRoutingTable(query_to_config=dict(run.final_routing)),
        demand_profile=run.demand_profile,
        supply_profile=run.supply_profile,
        probed_configs=run.probed_configs,
        budget_summary=budget,
        rounds=run.rounds,
        audit_log=run.audit_log,
        databases=run.databases,
        catalog_id_to_pipe=run.catalog_id_to_pipe,
        token_budget_total=int(budget.get("total", 0)),
        token_budget_spent=int(budget.get("spent", 0)),
        token_budget_remaining=int(budget.get("remaining", 0)),
        n_configs_selected=len(selected),
    )
