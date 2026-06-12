"""Phase 3: iterative budgeted agent loop."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from agent.budgeted_agent import call_budgeted_agent
from agent.phases.config_catalog import build_config_catalog
from agent.phases.demand_profile import extract_demand_profile
from agent.phases.supply_profile import (
    build_supply_profile,
    build_supply_profile_by_query,
    build_weighted_config_recommendation,
)
from llm.client import estimate_tokens
from optimizer.config_space import parse_config_id
from pipeline.extraction import ExtractionResult, extract_documents
from pipeline.population import apply_population
from stage5.per_query_eval import evaluate_per_query_f1, mean_f1
from utils.logging import setup_logger
from utils.token_budget import CostModel, TokenBudget

logger = setup_logger("spp.budgeted_loop")


@dataclass
class BudgetedRunResult:
    demand_profile: dict[str, Any]
    supply_profile: dict[str, Any]
    probed_configs: list[dict[str, Any]]
    final_routing: dict[str, str]
    budget_summary: dict[str, Any]
    rounds: int
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    extraction: ExtractionResult | None = None
    databases: dict[str, dict] = field(default_factory=dict)
    catalog_id_to_pipe: dict[str, str] = field(default_factory=dict)


def _probe_cost(
    entry: dict[str, Any],
    *,
    extraction_done: bool,
    cost_model: CostModel,
    n_docs: int,
    catalog_id_to_pipe: dict[str, str],
) -> int:
    pipe_id = entry.get("pipe_config_id") or catalog_id_to_pipe[entry["config_id"]]
    marginal = int(cost_model.config_marginal_cost(pipe_id, n_docs))
    if extraction_done:
        return marginal
    return int(cost_model.extraction_cost(n_docs)) + marginal


def _affordable_count(
    unprobed: list[dict],
    remaining: int,
    *,
    extraction_done: bool,
    cost_model: CostModel,
    n_docs: int,
    catalog_id_to_pipe: dict[str, str],
) -> int:
    return sum(
        1
        for c in unprobed
        if _probe_cost(
            c,
            extraction_done=extraction_done,
            cost_model=cost_model,
            n_docs=n_docs,
            catalog_id_to_pipe=catalog_id_to_pipe,
        )
        <= remaining
    )


def _update_best_routing(
    probed: list[dict[str, Any]],
    query_ids: list[str],
) -> dict[str, str]:
    routing: dict[str, str] = {}
    for qid in query_ids:
        best_cid = None
        best_f1 = -1.0
        for pc in probed:
            f1 = pc.get("per_query_f1", {}).get(qid, 0.0)
            if f1 > best_f1:
                best_f1 = f1
                best_cid = pc["config_id"]
        if best_cid:
            routing[qid] = best_cid
    return routing


def _build_state(
    *,
    round_num: int,
    budget: TokenBudget,
    demand_profile: dict,
    supply_profile_by_query: dict[str, dict],
    probed_configs: list[dict],
    unprobed_configs: list[dict],
    current_routing: dict[str, str],
    previous_reflection: str,
    extraction_done: bool,
    cost_model: CostModel,
    n_docs: int,
    catalog_id_to_pipe: dict[str, str],
) -> dict[str, Any]:
    remaining = budget.remaining
    affordable = _affordable_count(
        unprobed_configs,
        remaining,
        extraction_done=extraction_done,
        cost_model=cost_model,
        n_docs=n_docs,
        catalog_id_to_pipe=catalog_id_to_pipe,
    )
    return {
        "task": "select_extraction_pipeline_configs_for_aggregation_workload",
        "round": round_num,
        "budget": {
            "total": budget.total,
            "spent": budget.spent,
            "remaining": remaining,
            "affordable_probes_remaining": affordable,
        },
        "demand_profile": demand_profile,
        "supply_profile_by_query": supply_profile_by_query,
        "weighted_config_recommendation": build_weighted_config_recommendation(
            demand_profile, supply_profile_by_query
        ),
        "probed_configs": [
            {
                "config_id": p["config_id"],
                "settings": p["settings"],
                "per_query_f1": p.get("per_query_f1", {}),
                "mean_f1": p.get("mean_f1", 0.0),
                "cost": p.get("cost", 0),
            }
            for p in probed_configs
        ],
        "unprobed_configs": [
            {
                "config_id": c["config_id"],
                "settings": c["settings"],
                "estimated_cost": c["estimated_cost"],
            }
            for c in unprobed_configs
        ],
        "current_best_routing": current_routing,
        "previous_reflection": previous_reflection,
    }


def run_budgeted_agent_loop(
    instance,
    *,
    token_budget_total: int | None = None,
    max_rounds: int = 20,
    use_heuristic_agent: bool = False,
    use_heuristic_demand: bool = False,
    shared_extraction: ExtractionResult | None = None,
) -> BudgetedRunResult:
    from utils.config import load_config

    cfg = load_config()
    total = int(token_budget_total or cfg.get("token_budget", 50_000))
    budget = TokenBudget(total=total)

    queries = instance.queries
    query_ids = [str(q.get("query_id", i)) for i, q in enumerate(queries, start=1)]
    corpus = instance.corpus
    schema = instance.schema

    avg_tokens = (
        sum(estimate_tokens(d["text"]) for d in corpus) / len(corpus) if corpus else 512.0
    )
    cost_model = CostModel(avg_doc_tokens=avg_tokens)
    n_docs = len(corpus)

    # Phase 0 & 1
    demand_profile = extract_demand_profile(
        queries, schema, use_heuristic=use_heuristic_demand
    )
    supply_profile = build_supply_profile(corpus, demand_profile, schema)
    supply_profile_by_query = build_supply_profile_by_query(
        supply_profile, demand_profile, query_ids
    )

    # Phase 2
    catalog, catalog_id_to_pipe = build_config_catalog(n_docs, avg_tokens)
    unprobed = copy.deepcopy(catalog)
    probed: list[dict[str, Any]] = []
    extraction: ExtractionResult | None = shared_extraction
    databases: dict[str, dict] = {}
    audit: list[dict[str, Any]] = []

    current_routing: dict[str, str] = {}
    previous_reflection = ""
    round_num = 1

    llm_model = cfg["llm"]["extraction_model"]

    while round_num <= max_rounds:
        affordable = [
            c
            for c in unprobed
            if _probe_cost(
                c,
                extraction_done=extraction is not None,
                cost_model=cost_model,
                n_docs=n_docs,
                catalog_id_to_pipe=catalog_id_to_pipe,
            )
            <= budget.remaining
        ]
        if not affordable:
            logger.info("Forced finalize: no affordable unprobed configs.")
            break

        state = _build_state(
            round_num=round_num,
            budget=budget,
            demand_profile=demand_profile,
            supply_profile_by_query=supply_profile_by_query,
            probed_configs=probed,
            unprobed_configs=unprobed,
            current_routing=current_routing,
            previous_reflection=previous_reflection,
            extraction_done=extraction is not None,
            cost_model=cost_model,
            n_docs=n_docs,
            catalog_id_to_pipe=catalog_id_to_pipe,
        )
        if use_heuristic_agent:
            from agent.budgeted_agent import heuristic_budgeted_decision

            decision = heuristic_budgeted_decision(state)
        else:
            decision = call_budgeted_agent(state)
        audit.append({"round": round_num, "state": state, "decision": decision})
        previous_reflection = decision["reflection"]
        action = decision["action"]

        if action == "finalize_routing":
            overrides = decision.get("routing_overrides") or {}
            probed_ids = {p["config_id"] for p in probed}
            for qid, cid in overrides.items():
                if cid in probed_ids:
                    current_routing[qid] = cid
            break

        if action == "adjust_routing":
            overrides = decision.get("routing_overrides") or {}
            probed_ids = {p["config_id"] for p in probed}
            for qid, cid in overrides.items():
                if cid in probed_ids:
                    current_routing[qid] = cid
            round_num += 1
            continue

        if action == "probe_config":
            target = decision.get("target_config_id")
            entry = next((c for c in unprobed if c["config_id"] == target), None)
            if entry is None:
                logger.warning("Invalid probe target %s; finalize.", target)
                break
            cost = _probe_cost(
                entry,
                extraction_done=extraction is not None,
                cost_model=cost_model,
                n_docs=n_docs,
                catalog_id_to_pipe=catalog_id_to_pipe,
            )
            if cost > budget.remaining:
                logger.info("Probe cost %d exceeds remaining %d; finalize.", cost, budget.remaining)
                break

            if extraction is None:
                extraction = extract_documents(corpus, schema, llm_model, queries=queries)
                budget.spend(int(cost_model.extraction_cost(n_docs)), label="extraction")

            pipe_id = catalog_id_to_pipe[target]
            config = parse_config_id(pipe_id)
            db, _ = apply_population(extraction, config, schema)
            marginal = cost_model.config_marginal_cost(pipe_id, n_docs)
            if marginal > 0:
                budget.spend(marginal, label=f"materialize:{target}")

            per_query_f1 = evaluate_per_query_f1(instance, db)
            m_f1 = mean_f1(per_query_f1)
            databases[target] = db

            probed.append(
                {
                    "config_id": target,
                    "settings": entry["settings"],
                    "pipe_config_id": pipe_id,
                    "per_query_f1": per_query_f1,
                    "mean_f1": round(m_f1, 4),
                    "cost": cost,
                }
            )
            unprobed = [c for c in unprobed if c["config_id"] != target]
            current_routing = _update_best_routing(probed, query_ids)
            round_num += 1
            continue

    if not current_routing and probed:
        current_routing = _update_best_routing(probed, query_ids)

    return BudgetedRunResult(
        demand_profile=demand_profile,
        supply_profile=supply_profile,
        probed_configs=probed,
        final_routing=current_routing,
        budget_summary=budget.summary(),
        rounds=round_num,
        audit_log=audit,
        extraction=extraction,
        databases=databases,
        catalog_id_to_pipe=catalog_id_to_pipe,
    )
