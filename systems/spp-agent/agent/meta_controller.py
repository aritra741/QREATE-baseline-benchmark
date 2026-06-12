"""Meta-controller: selects a solver family under budget, not per-query routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.meta_actions import (
    ACTION_TO_STAGE3_ALGORITHM,
    META_ACTIONS,
    MetaActionRecord,
)
from agent.meta_state import build_meta_controller_state, stage1_report_to_dict
from diagnostics.structural_score import (
    probe_data_with_selection_scores,
    structural_scores_from_probe,
)
from stage1.characterizer import Stage1Report
from stage1.meta_characterize import characterize_meta
from stage3.comparison import compare_algorithms
from stage3.routing_assignment import assign_configs_to_clusters
from stage4.query_clustering import cluster_workload
from surrogates.structural_probe_ranking import StructuralProbeRankingSurrogate
from thresholds.schema import ThresholdConfig, load_thresholds
from utils.logging import setup_logger
from utils.token_budget import CostModel, TokenBudget

logger = setup_logger("spp.meta_controller")

MAX_META_ROUNDS = 8
PROBE_MORE_BATCH = 4


@dataclass
class MetaControllerRunResult:
    """Paper-facing meta-selection result + eval-compat routing artifacts."""

    agent_mode: str = "meta_controller"
    chosen_algorithm_family: str = ""
    selection_rationale: str = ""
    solver_comparison: list[dict[str, Any]] = field(default_factory=list)
    baseline_comparison: list[dict[str, Any]] = field(default_factory=list)
    stage_summaries: dict[str, Any] = field(default_factory=dict)
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0

    selected_configs: list[str] = field(default_factory=list)
    final_routing: dict[str, str] = field(default_factory=dict)
    databases: dict[str, Any] = field(default_factory=dict)
    probed_configs: list[dict[str, Any]] = field(default_factory=list)
    budget_summary: dict[str, Any] = field(default_factory=dict)

    demand_profile: dict[str, Any] = field(default_factory=dict)
    supply_profile: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    catalog_id_to_pipe: dict[str, str] = field(default_factory=dict)
    routing_table: Any = None
    probe_data: Any = None
    algorithm_stack: dict[str, Any] = field(default_factory=dict)
    stage1_report: Any = None
    query_clusters: Any = None


def _estimate_probe_cost(n_configs: int, n_docs: int, cost_model: CostModel) -> int:
    return int(n_configs * cost_model.config_marginal_cost("er=embedding_0.7|norm=dictionary|unit=none|miss=drop|coerce=strict", n_docs))


def _solver_budget_remaining(token_budget: TokenBudget, n_docs: int, cost_model: CostModel) -> int:
    """Configs affordable from remaining tokens (selection only, not probe cost)."""
    marginal = cost_model.config_marginal_cost(
        "er=embedding_0.7|norm=dictionary|unit=none|miss=drop|coerce=strict", n_docs
    )
    if marginal <= 0:
        return 8
    return max(1, int(token_budget.remaining // marginal))


def heuristic_meta_decision(state: dict[str, Any]) -> MetaActionRecord:
    """Evidence-driven solver-family selection (deterministic)."""
    recs = state.get("stage1_summary", {}).get("recommendations", {})
    probe = state.get("probe_outcomes", {})
    n_probed = int(probe.get("n_probed", 0))
    budget_remaining = int(state.get("budget", {}).get("remaining", 0))
    prior = state.get("prior_chosen_algorithm_family")
    comparisons = state.get("solver_comparison_summary", [])
    tried = {c.get("algorithm_family") for c in comparisons}

    if n_probed < 6 and budget_remaining > 500:
        return MetaActionRecord(
            action="probe_more",
            rationale_code="insufficient_probe_coverage|n_probed<6",
            confidence=0.82,
            expected_gain=0.12,
            budget_impact=_estimate_probe_cost(PROBE_MORE_BATCH, 20, CostModel()),
            observation={},
        )

    candidates: list[tuple[str, str, float, float]] = []

    if recs.get("density_greedy_viable") and "use_greedy" not in tried:
        candidates.append(("use_greedy", "stage1_density_greedy_viable", 0.78, 0.08))
    if recs.get("use_nonlinear") and "use_bo_tpe" not in tried:
        candidates.append(("use_bo_tpe", "stage1_nonlinear_surface", 0.74, 0.10))
    err_rec = state.get("stage1_summary", {}).get("error_surface", "")
    if err_rec == "include_bo_sa_evolutionary" and "use_bo_tpe" not in tried:
        candidates.append(("use_bo_tpe", "rugged_error_surface", 0.76, 0.11))
    if err_rec == "local_coord_methods_viable" and "use_coordinate_descent" not in tried:
        candidates.append(("use_coordinate_descent", "smooth_local_surface", 0.72, 0.07))
    if recs.get("use_routing") and "use_clustered_routing" not in tried:
        candidates.append(("use_clustered_routing", "stage1_routing_gap", 0.80, 0.09))
    if recs.get("use_clustering") and "use_clustered_routing" not in tried:
        candidates.append(("use_clustered_routing", "stage1_clustering_valid", 0.77, 0.09))
    if float(probe.get("score_spread", 0)) < 0.05 and "use_hyperband" not in tried:
        candidates.append(("use_hyperband", "low_score_spread_multifidelity", 0.70, 0.06))
    if recs.get("use_nonlinear") and "use_ilp" not in tried:
        candidates.append(("use_ilp", "interaction_heavy_workload", 0.68, 0.05))

    if not candidates:
        if prior:
            return MetaActionRecord(
                action="finalize",
                rationale_code=f"finalize|prior={prior}",
                confidence=0.88,
                expected_gain=0.0,
                budget_impact=0,
                observation={},
            )
        return MetaActionRecord(
            action="use_greedy",
            rationale_code="default_greedy_fallback",
            confidence=0.65,
            expected_gain=0.05,
            budget_impact=0,
            observation={},
        )

    candidates.sort(key=lambda x: (-x[2], -x[3]))
    action, code, conf, gain = candidates[0]

    if prior and comparisons:
        best = comparisons[0]
        runner = comparisons[1] if len(comparisons) > 1 else None
        if (
            runner
            and best.get("algorithm_family") == prior
            and (best["predicted_score"] - runner["predicted_score"]) < 0.02
        ):
            return MetaActionRecord(
                action="finalize",
                rationale_code=f"near_tie_finalize|winner={prior}",
                confidence=0.86,
                expected_gain=0.0,
                budget_impact=0,
                observation={},
            )

    return MetaActionRecord(
        action=action,
        rationale_code=code,
        confidence=conf,
        expected_gain=gain,
        budget_impact=0,
        observation={},
    )


def _run_solver_action(
    action: str,
    *,
    probe_data,
    queries: list[dict],
    schema,
    candidate_ids: list[str],
    solver_budget: int,
    token_budget: TokenBudget,
    cost_model: CostModel,
    n_docs: int,
    seed: int,
    query_clusters,
) -> dict[str, Any]:
    surrogate = StructuralProbeRankingSurrogate()
    surrogate.fit(probe_data)

    if action == "use_clustered_routing":
        scores = structural_scores_from_probe(probe_data)
        probe_view = probe_data_with_selection_scores(probe_data, scores)
        cluster_surrogates = {
            cid: "structural_probe_ranking"
            for cid in range(query_clusters.n_clusters)
        }
        routing = assign_configs_to_clusters(
            query_clusters,
            probe_view,
            cluster_surrogates,
            candidate_ids,
            token_budget,
            cost_model,
            n_docs,
            seed=seed,
        )
        total_score = sum(routing.assignment_scores.values())
        return {
            "algorithm_family": action,
            "selected_configs": list(routing.selected_configs),
            "predicted_score": float(total_score),
            "wall_time_seconds": 0.0,
            "routing_table": routing,
        }

    algo = ACTION_TO_STAGE3_ALGORITHM[action]
    if algo is None:
        raise ValueError(f"Action {action} is not a solver action")

    results = compare_algorithms(
        surrogate,
        candidate_ids,
        probe_data,
        budget=solver_budget,
        algorithms=[algo],
        seed=seed,
    )
    if not results:
        return {
            "algorithm_family": action,
            "selected_configs": [],
            "predicted_score": 0.0,
            "wall_time_seconds": 0.0,
            "routing_table": None,
        }
    best = results[0]
    return {
        "algorithm_family": action,
        "selected_configs": list(best.selected_configs),
        "predicted_score": float(best.total_predicted_score),
        "wall_time_seconds": float(best.wall_time_seconds),
        "routing_table": None,
    }


def _build_query_routing(
    queries: list[dict],
    selected_configs: list[str],
    routing_table,
    query_clusters,
    selection_scores: dict[str, float],
) -> dict[str, str]:
    if routing_table is not None and getattr(routing_table, "cluster_to_config", None):
        q_to_cluster: dict[str, int] = {}
        for cid, cluster_queries in query_clusters.cluster_to_queries.items():
            for q in cluster_queries:
                q_to_cluster[str(q.get("query_id", ""))] = int(cid)
        routing: dict[str, str] = {}
        for q in queries:
            qid = str(q.get("query_id", ""))
            cluster_id = q_to_cluster.get(qid)
            if cluster_id is not None and cluster_id in routing_table.cluster_to_config:
                routing[qid] = routing_table.cluster_to_config[cluster_id]
            elif selected_configs:
                routing[qid] = selected_configs[0]
        return routing

    if not selected_configs:
        return {}
    if len(selected_configs) == 1:
        return {str(q.get("query_id", "")): selected_configs[0] for q in queries}
    best = max(selected_configs, key=lambda c: selection_scores.get(c, 0.0))
    return {str(q.get("query_id", "")): best for q in queries}


def run_meta_controller_loop(
    instance,
    *,
    probe_data,
    demand_profile: dict[str, Any],
    supply_profile: dict[str, Any],
    token_budget_total: int | None = None,
    thresholds: ThresholdConfig | None = None,
    seed: int = 42,
    max_rounds: int = MAX_META_ROUNDS,
    use_heuristic: bool = True,
) -> MetaControllerRunResult:
    """Iteratively choose a solver family; routing is a downstream artifact."""
    from utils.config import load_config

    cfg = load_config()
    thresholds = thresholds or load_thresholds()
    budget_total = int(token_budget_total or cfg.get("token_budget", 80_000))
    queries = list(instance.queries)
    schema = instance.schema
    n_docs = len(instance.corpus) or 1
    cost_model = CostModel.from_tier0(cfg.get("tier0", {}))

    token_budget = TokenBudget(total=budget_total)
    token_budget.spend(int(probe_data.total_cost), label="bootstrap_probes")

    selection_scores = structural_scores_from_probe(probe_data)
    query_clusters = cluster_workload(queries, seed=seed)
    stage1 = characterize_meta(
        probe_data,
        selection_scores=selection_scores,
        queries=queries,
        schema=schema,
        thresholds=thresholds,
        seed=seed,
    )

    candidate_ids = list(probe_data.config_ids)

    solver_runs: list[dict[str, Any]] = []
    audit_log: list[dict[str, Any]] = []
    chosen_family: str | None = None
    chosen_run: dict[str, Any] | None = None
    selection_rationale = ""

    for round_num in range(1, max_rounds + 1):
        state = build_meta_controller_state(
            queries=queries,
            demand_profile=demand_profile,
            supply_profile=supply_profile,
            probe_data=probe_data,
            selection_scores=selection_scores,
            stage1=stage1,
            budget_total=budget_total,
            budget_spent=int(token_budget.spent),
            solver_runs=solver_runs,
            chosen_algorithm_family=chosen_family,
            round_num=round_num,
        )

        if use_heuristic:
            decision = heuristic_meta_decision(state)
        else:
            decision = heuristic_meta_decision(state)

        action = decision.action
        if action not in META_ACTIONS:
            raise ValueError(f"Invalid meta action: {action}")

        observation: dict[str, Any] = {}

        if action == "probe_more":
            from optimizer.probing import expand_structural_probes

            probe_data, added_cost = expand_structural_probes(
                probe_data,
                instance,
                schema,
                queries,
                n_additional=PROBE_MORE_BATCH,
                seed=seed + round_num,
                shared_extraction=getattr(probe_data, "extraction", None),
            )
            token_budget.spend(added_cost, label="probe_more")
            selection_scores = structural_scores_from_probe(probe_data)
            candidate_ids = list(probe_data.config_ids)
            stage1 = characterize_meta(
                probe_data,
                selection_scores=selection_scores,
                queries=queries,
                schema=schema,
                thresholds=thresholds,
                seed=seed,
            )
            observation = {"n_probed": len(probe_data.config_ids), "added_cost": added_cost}

        elif action == "finalize":
            if chosen_family and chosen_run:
                selection_rationale = decision.rationale_code
                break
            if solver_runs:
                chosen_run = max(solver_runs, key=lambda r: r["predicted_score"])
                chosen_family = chosen_run["algorithm_family"]
                selection_rationale = decision.rationale_code
                break
            action = "use_greedy"
            decision = MetaActionRecord(
                action=action,
                rationale_code="finalize_fallback_greedy",
                confidence=0.6,
                expected_gain=0.05,
                budget_impact=0,
                observation={},
            )

        if action in {
            "use_greedy",
            "use_bo_tpe",
            "use_hyperband",
            "use_coordinate_descent",
            "use_ilp",
            "use_clustered_routing",
        }:
            solver_budget = _solver_budget_remaining(token_budget, n_docs, cost_model)
            run_result = _run_solver_action(
                action,
                probe_data=probe_data,
                queries=queries,
                schema=schema,
                candidate_ids=candidate_ids,
                solver_budget=solver_budget,
                token_budget=token_budget,
                cost_model=cost_model,
                n_docs=n_docs,
                seed=seed,
                query_clusters=query_clusters,
            )
            solver_runs.append(run_result)
            chosen_family = action
            chosen_run = run_result
            observation = {
                "selected_configs": run_result["selected_configs"],
                "predicted_score": run_result["predicted_score"],
            }
            if len(solver_runs) >= 2:
                ranked = sorted(solver_runs, key=lambda r: -r["predicted_score"])
                if ranked[0]["predicted_score"] - ranked[1]["predicted_score"] >= 0.03:
                    chosen_family = ranked[0]["algorithm_family"]
                    chosen_run = ranked[0]
                    selection_rationale = f"clear_solver_winner|{chosen_family}"
                    audit_log.append(
                        {
                            "round": round_num,
                            "state": state,
                            "decision": decision.to_dict(),
                            "observation": observation,
                        }
                    )
                    break

        audit_log.append(
            {
                "round": round_num,
                "state": state,
                "decision": decision.to_dict(),
                "observation": observation,
            }
        )

    if not chosen_run:
        chosen_run = _run_solver_action(
            "use_greedy",
            probe_data=probe_data,
            queries=queries,
            schema=schema,
            candidate_ids=candidate_ids,
            solver_budget=_solver_budget_remaining(token_budget, n_docs, cost_model),
            token_budget=token_budget,
            cost_model=cost_model,
            n_docs=n_docs,
            seed=seed,
            query_clusters=query_clusters,
        )
        chosen_family = "use_greedy"
        solver_runs.append(chosen_run)
        selection_rationale = selection_rationale or "default_greedy"

    selected_configs = list(chosen_run.get("selected_configs", []))
    routing_table = chosen_run.get("routing_table")
    final_routing = _build_query_routing(
        queries,
        selected_configs,
        routing_table,
        query_clusters,
        selection_scores,
    )

    databases: dict[str, Any] = {}
    for cid in set(selected_configs) | set(probe_data.config_ids):
        if cid in probe_data.databases:
            databases[cid] = probe_data.databases[cid]

    probed_payload = [
        {
            "config_id": cid,
            "pipe_config_id": cid,
            "settings": dict(
                part.split("=", 1)
                for part in cid.split("|")
                if "=" in part
            ),
            "structural_score": selection_scores.get(cid, 0.0),
            "mean_f1": None,
        }
        for cid in probe_data.config_ids
    ]

    diagnostics = {
        "glass_box_composites": dict(probe_data.glass_box_composites),
        "btl_scores": dict(probe_data.btl_scores),
        "structural_scores": selection_scores,
    }

    ranked_comparison = sorted(
        [
            {
                "algorithm_family": r["algorithm_family"],
                "predicted_score": r["predicted_score"],
                "selected_configs": r["selected_configs"],
                "wall_time_seconds": r.get("wall_time_seconds", 0.0),
            }
            for r in solver_runs
        ],
        key=lambda x: -x["predicted_score"],
    )

    return MetaControllerRunResult(
        chosen_algorithm_family=chosen_family or "use_greedy",
        selection_rationale=selection_rationale or "meta_controller_complete",
        solver_comparison=ranked_comparison,
        stage1_report=stage1,
        query_clusters=query_clusters,
        stage_summaries={
            "stage1": stage1_report_to_dict(stage1),
            "workload": build_meta_controller_state(
                queries=queries,
                demand_profile=demand_profile,
                supply_profile=supply_profile,
                probe_data=probe_data,
                selection_scores=selection_scores,
                stage1=stage1,
                budget_total=budget_total,
                budget_spent=int(token_budget.spent),
                solver_runs=solver_runs,
                chosen_algorithm_family=chosen_family,
                round_num=len(audit_log),
            ),
        },
        audit_log=audit_log,
        rounds=len(audit_log),
        selected_configs=selected_configs,
        final_routing=final_routing,
        databases=databases,
        probed_configs=probed_payload,
        budget_summary={
            "total": budget_total,
            "spent": int(token_budget.spent),
            "remaining": int(token_budget.remaining),
        },
        demand_profile=demand_profile,
        supply_profile=supply_profile,
        diagnostics=diagnostics,
        catalog_id_to_pipe={cid: cid for cid in probe_data.config_ids},
        routing_table=routing_table,
        probe_data=probe_data,
        algorithm_stack={},
    )
