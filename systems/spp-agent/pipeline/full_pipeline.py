from __future__ import annotations

"""Connected SPP pipeline: Stage 1 → 2 → 3 → (4 advisory) → config selection.

No ground-truth query error is accessed anywhere in this module.
All routing decisions are based on deployment-visible probe signals:
  - glass-box composite scores (extraction quality proxy)
  - BTL pairwise judge scores (LLM judge, no query eval)
  - LOO Spearman ρ between surrogate predictions and BTL scores
  - SQL structural features of queries
  - Schema column types
"""

from dataclasses import dataclass, field
from typing import Any

from utils.logging import setup_logger

logger = setup_logger("spp.pipeline")


@dataclass
class PipelineResult:
    # What the pipeline selected
    selected_configs: list[str]
    best_surrogate: str
    best_algorithm: str

    # Stage handoff artifacts (all probe-visible, no ground truth)
    stage1_recommendations: dict[str, Any]
    stage1_probe_fidelity_rho: float    # LOO Spearman ρ of best surrogate
    stage2_surrogate_rhos: dict[str, float]  # {surrogate: loo_rho}
    stage3_algorithm_scores: dict[str, float]  # {algorithm: predicted_score}
    stage4_retained_components: list[str]

    # Adaptive probing info
    n_probe_configs_used: int
    probing_expanded: bool              # True if the pipeline triggered extra probes

    # Token budget accounting
    token_budget_total: float
    token_budget_spent: float
    token_budget_remaining: float
    n_configs_selected: int             # derived from budget, not specified upfront

    # Thresholds that drove decisions (learned offline, applied here)
    thresholds_used: dict[str, Any] = field(default_factory=dict)

    # Routing outputs
    routing_table: Any = None
    cluster_surrogates: dict[int, str] = field(default_factory=dict)
    query_cluster_info: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "risk_neutral"
    audit_log: dict[str, Any] = field(default_factory=dict)


def _score_spread(scores: dict[str, float]) -> float:
    if len(scores) < 2:
        return 0.0
    vals = list(scores.values())
    return float(max(vals) - min(vals))


def _loo_rhos_from_probe(probe_data) -> dict[str, float]:
    """Thin wrapper so full_pipeline doesn't import optimizer directly."""
    from thresholds.optimizer import _compute_loo_rhos
    return _compute_loo_rhos(probe_data)


# ---------------------------------------------------------------------------
# Stage 1 → Stage 2 handoff
# ---------------------------------------------------------------------------

def _stage1_to_stage2_surrogate_list(
    stage1_recs: dict[str, Any],
    all_surrogate_names: list[str],
) -> list[str]:
    """Stage 1 recommendations narrow the Stage 2 candidate list.

    - use_nonlinear=True  → deprioritise linear_proxy_glass (keep last)
    - probe_viable=False  → skip BTL-dependent surrogates (llm_judge_btl)
    """
    ordered = list(all_surrogate_names)

    if not stage1_recs.get("probe_viable", True):
        # Probe fidelity too low for BTL-based surrogate to be trustworthy
        ordered = [s for s in ordered if s != "llm_judge_btl"]
        logger.info("Stage1→Stage2: probe_viable=False, excluded llm_judge_btl")

    if stage1_recs.get("use_nonlinear", False):
        # Move linear model to end so nonlinear gets priority in bakeoff
        linear = [s for s in ordered if "linear" in s and "rf" not in s and "gbdt" not in s]
        nonlinear = [s for s in ordered if s not in linear]
        ordered = nonlinear + linear
        logger.info("Stage1→Stage2: use_nonlinear=True, reordered to prefer nonlinear")

    return ordered


# ---------------------------------------------------------------------------
# Stage 3 → Stage 4 handoff
# ---------------------------------------------------------------------------

def _stage3_to_stage4_components(
    stage1_recs: dict[str, Any],
    thresholds,
) -> list[str]:
    """Stage 1 flags determine which Stage 4 components are active.

    Only components whose Stage 1 analysis recommends retention are included.
    This avoids ablating components that Stage 1 already ruled out.
    """
    from stage4.ablation import describe_ablation_components
    all_components = describe_ablation_components()

    active: list[str] = []
    for component in all_components:
        if component == "query_clustering" and not stage1_recs.get("use_clustering", False):
            logger.info("Stage3→Stage4: skipping query_clustering (Stage1 says not valid)")
            continue
        if component == "routing" and not stage1_recs.get("use_routing", False):
            logger.info("Stage3→Stage4: skipping routing component (Stage1 says gap small)")
            continue
        if component == "schema_pruning" and not stage1_recs.get("schema_first", False):
            logger.info("Stage3→Stage4: skipping schema_pruning (Stage1 says flat hierarchy)")
            continue
        active.append(component)

    logger.info("Stage3→Stage4: active components=%s", active)
    return active


# ---------------------------------------------------------------------------
# Main pipeline runner
# ---------------------------------------------------------------------------

def run_spp_pipeline(
    probe_data=None,
    *,
    queries: list[dict],
    schema,
    thresholds=None,
    token_budget: int = 50_000,
    candidate_ids: list[str] | None = None,
    seed: int = 42,
    allow_adaptive_probing: bool = False,
    instance=None,
    agent_risk_level: str = "risk_neutral",
    query_clusters=None,
    use_heuristic_agent: bool = False,
    pipeline_mode: str = "meta_controller",
    shared_extraction=None,
) -> PipelineResult:
    """Run SPP pipeline.

    ``pipeline_mode``:
      - ``meta_controller`` (default): solver-family meta-selection under budget
      - ``budgeted_routing``: legacy per-query heuristic router
      - ``legacy``: Stage 1–4 surrogate + routing assignment path
    """
    if instance is None:
        raise ValueError("run_spp_pipeline requires instance=.")

    if pipeline_mode == "legacy":
        if probe_data is None or thresholds is None:
            raise ValueError("legacy pipeline_mode requires probe_data and thresholds.")
        return _run_spp_pipeline_legacy(
            probe_data,
            queries=queries,
            schema=schema,
            thresholds=thresholds,
            token_budget=token_budget,
            candidate_ids=candidate_ids,
            seed=seed,
            allow_adaptive_probing=allow_adaptive_probing,
            instance=instance,
            agent_risk_level=agent_risk_level,
            query_clusters=query_clusters,
        )

    if pipeline_mode == "budgeted_routing":
        del probe_data, thresholds, candidate_ids, allow_adaptive_probing
        del agent_risk_level, query_clusters, seed, shared_extraction

        from pipeline.budgeted_pipeline import run_budgeted_spp_pipeline

        logger.info("=== Budgeted routing pipeline ===")
        br = run_budgeted_spp_pipeline(
            instance,
            token_budget=token_budget,
            use_heuristic_agent=use_heuristic_agent,
            shared_extraction=shared_extraction,
        )
        pipe_routing = {
            qid: br.catalog_id_to_pipe.get(cid, cid)
            for qid, cid in br.routing_table.query_to_config.items()
        }
        return PipelineResult(
            selected_configs=br.selected_configs,
            best_surrogate=br.best_surrogate,
            best_algorithm=br.best_algorithm,
            stage1_recommendations={
                "demand_profile": br.demand_profile,
                "supply_profile": br.supply_profile,
            },
            stage1_probe_fidelity_rho=0.0,
            stage2_surrogate_rhos={},
            stage3_algorithm_scores={},
            stage4_retained_components=[],
            n_probe_configs_used=len(br.probed_configs),
            probing_expanded=False,
            token_budget_total=float(br.token_budget_total),
            token_budget_spent=float(br.token_budget_spent),
            token_budget_remaining=float(br.token_budget_remaining),
            n_configs_selected=br.n_configs_selected,
            routing_table=br.routing_table,
            query_cluster_info={"per_query_routing": pipe_routing},
            audit_log={"rounds": br.rounds, "events": br.audit_log, "pipeline_mode": pipeline_mode},
        )

    del probe_data, thresholds, candidate_ids, allow_adaptive_probing
    del agent_risk_level, query_clusters

    from pipeline.meta_pipeline import run_meta_spp_pipeline

    logger.info("=== Meta-controller pipeline (solver-family selection) ===")
    mr = run_meta_spp_pipeline(
        instance,
        token_budget=token_budget,
        shared_extraction=shared_extraction,
        seed=seed,
        use_heuristic=use_heuristic_agent,
    )

    algo_scores = {
        entry.get("algorithm_family", ""): float(entry.get("predicted_score", 0.0))
        for entry in mr.solver_comparison
    }
    pipe_routing = dict(mr.final_routing)

    return PipelineResult(
        selected_configs=mr.selected_configs,
        best_surrogate="structural_probe_ranking",
        best_algorithm=mr.chosen_algorithm_family,
        stage1_recommendations=mr.stage_summaries.get("stage1", {}).get("recommendations", {}),
        stage1_probe_fidelity_rho=float(
            mr.stage_summaries.get("stage1", {})
            .get("probe_fidelity", {})
            .get("spearman_rho", 0.0)
        ),
        stage2_surrogate_rhos={"structural_probe_ranking": 1.0},
        stage3_algorithm_scores=algo_scores,
        stage4_retained_components=["meta_controller"],
        n_probe_configs_used=len(mr.probed_configs),
        probing_expanded=any(
            e.get("decision", {}).get("action") == "probe_more" for e in mr.audit_log
        ),
        token_budget_total=float(mr.budget_summary.get("total", 0)),
        token_budget_spent=float(mr.budget_summary.get("spent", 0)),
        token_budget_remaining=float(mr.budget_summary.get("remaining", 0)),
        n_configs_selected=len(mr.selected_configs),
        routing_table=mr.routing_table,
        query_cluster_info={
            "per_query_routing": pipe_routing,
            "selection_rationale": mr.selection_rationale,
            "solver_comparison": mr.solver_comparison,
        },
        audit_log={
            "rounds": mr.rounds,
            "events": mr.audit_log,
            "pipeline_mode": pipeline_mode,
            "chosen_algorithm_family": mr.chosen_algorithm_family,
        },
    )


def _run_spp_pipeline_legacy(
    probe_data,
    *,
    queries: list[dict],
    schema,
    thresholds,
    token_budget: int = 50_000,
    candidate_ids: list[str] | None = None,
    seed: int = 42,
    allow_adaptive_probing: bool = False,
    instance=None,
    agent_risk_level: str = "risk_neutral",
    query_clusters=None,
) -> PipelineResult:
    """Legacy Stage 1–4 pipeline (retained for reference, not used by default)."""
    from optimizer.config_space import generate_config_space
    from optimizer.materialize import all_config_ids
    from stage1.characterizer import characterize
    from stage2.surrogate_comparison import compare_surrogates_per_cluster
    from stage3.routing_assignment import assign_configs_to_clusters
    from stage4.query_clustering import cluster_workload
    from surrogates.registry import ALL_SURROGATES
    from thresholds.optimizer import _compute_loo_rhos_per_cluster
    from utils.audit import AuditLog
    from utils.config import load_config
    from utils.token_budget import CostModel, TokenBudget

    cfg = load_config()
    stage3_cfg = cfg.get("stage3", {})
    risk_lambda = float(stage3_cfg.get("risk_lambda", 0.5))

    if candidate_ids is None:
        candidate_ids = all_config_ids()

    if query_clusters is None:
        query_clusters = cluster_workload(queries, seed=seed)
    logger.info(
        "Query clusters: n=%d types=%s sizes=%s",
        query_clusters.n_clusters,
        query_clusters.cluster_types,
        {k: len(v) for k, v in query_clusters.cluster_to_queries.items()},
    )

    probing_expanded = False

    tb = TokenBudget(total=int(token_budget))
    n_docs = len(getattr(instance, "corpus", [])) or 20
    cost_model = CostModel.from_tier0(
        {"avg_doc_tokens": probe_data.total_cost / max(1, len(probe_data.config_ids) * n_docs)}
        if probe_data.total_cost > 0 else {}
    )
    tb.spend(probe_data.total_cost, label="probe_run")
    logger.info(
        "Token budget: total=%.0f probe_spent=%.0f remaining=%.0f",
        tb.total, probe_data.total_cost, tb.remaining,
    )

    logger.info("=== Stage 1: Search space characterization ===")
    stage1_report = characterize(
        probe_data,
        queries=queries,
        schema=schema,
        thresholds=thresholds,
        true_errors=None,
        seed=seed,
    )
    recs = stage1_report.recommendations
    logger.info("Stage 1 recommendations: %s", recs)

    fidelity_rho = stage1_report.probe_fidelity.get("spearman_rho", 0.0) or 0.0
    if (
        allow_adaptive_probing
        and instance is not None
        and fidelity_rho < thresholds.rho_bakeoff
        and len(probe_data.config_ids) < 12
    ):
        logger.info(
            "Stage1 fidelity rho=%.3f < rho_bakeoff=%.3f; probing 4 more configs",
            fidelity_rho, thresholds.rho_bakeoff,
        )
        probe_data = _expand_probes(
            probe_data, instance, schema, queries,
            n_additional=4, seed=seed, query_clusters=query_clusters,
        )
        probing_expanded = True
        # Re-run Stage 1 on expanded probe data
        stage1_report = characterize(
            probe_data,
            queries=queries,
            schema=schema,
            thresholds=thresholds,
            true_errors=None,
            seed=seed,
        )
        recs = stage1_report.recommendations
        fidelity_rho = stage1_report.probe_fidelity.get("spearman_rho", 0.0) or 0.0
        logger.info("After expansion: Stage 1 recommendations=%s fidelity_rho=%.3f", recs, fidelity_rho)

    # -----------------------------------------------------------------------
    # Stage 2: Per-cluster surrogate bakeoff
    # -----------------------------------------------------------------------
    logger.info("=== Stage 2: Per-cluster surrogate selection ===")
    all_surrogates = [k for k in ALL_SURROGATES if k != "random_ranking"]
    candidate_surrogates = _stage1_to_stage2_surrogate_list(recs, all_surrogates)

    cluster_bakeoff_results = compare_surrogates_per_cluster(
        probe_data,
        candidate_surrogates,
        query_clusters,
        thresholds=thresholds,
        seed=seed,
    )
    cluster_surrogates = {
        cid: res.best_surrogate for cid, res in cluster_bakeoff_results.items()
    }
    per_cluster_loo = _compute_loo_rhos_per_cluster(probe_data, query_clusters)
    surrogate_rhos = _loo_rhos_from_probe(probe_data)
    best_surrogate = max(
        cluster_surrogates.values(),
        key=lambda name: surrogate_rhos.get(name, 0.0),
        default=cluster_surrogates.get(0, "direct_probe_ranking"),
    )

    # -----------------------------------------------------------------------
    # Stage 3: Routing assignment
    # -----------------------------------------------------------------------
    logger.info("=== Stage 3: Routing assignment ===")
    best_algorithm = "routing_assignment"

    routing_table = assign_configs_to_clusters(
        query_clusters,
        probe_data,
        cluster_surrogates,
        candidate_ids,
        tb,
        cost_model,
        n_docs,
        risk_level=agent_risk_level,
        risk_lambda=risk_lambda,
        seed=seed,
    )
    selected_configs = routing_table.selected_configs
    algo_scores = {
        f"cluster_{cid}": routing_table.assignment_scores.get(cid, 0.0)
        for cid in routing_table.cluster_to_config
    }

    # -----------------------------------------------------------------------
    # Stage 3 → Stage 4 handoff: determine active components
    # -----------------------------------------------------------------------
    logger.info("=== Stage 4: Architecture decisions ===")
    active_components = _stage3_to_stage4_components(recs, thresholds)
    logger.info("Stage 4 active components: %s", active_components)

    logger.info(
        "Pipeline complete: surrogate=%s algorithm=%s selected=%s probing_expanded=%s",
        best_surrogate, best_algorithm, selected_configs, probing_expanded,
    )

    query_cluster_info = {
        "n_clusters": query_clusters.n_clusters,
        "cluster_types": query_clusters.cluster_types,
        "cluster_sizes": {k: len(v) for k, v in query_clusters.cluster_to_queries.items()},
        "labels": query_clusters.labels,
    }

    audit = AuditLog.new(int(token_budget))
    audit.probe_config_ids = list(probe_data.config_ids)
    audit.probe_total_token_cost = float(probe_data.total_cost)
    audit.probe_n_judge_pairs = len(probe_data.pairwise_comparisons)
    audit.n_clusters = query_clusters.n_clusters
    audit.cluster_types = {int(k): v for k, v in query_clusters.cluster_types.items()}
    audit.cluster_sizes = {int(k): len(v) for k, v in query_clusters.cluster_to_queries.items()}
    audit.cluster_labels = list(query_clusters.labels)
    audit.cluster_btl_scores = {
        int(k): dict(v) for k, v in getattr(probe_data, "cluster_btl_scores", {}).items()
    }
    audit.cluster_btl_uncertainty = {
        int(k): dict(v) for k, v in getattr(probe_data, "cluster_btl_uncertainty", {}).items()
    }
    audit.cluster_surrogate_loo_rhos = {
        int(k): dict(v) for k, v in per_cluster_loo.items()
    }
    audit.cluster_selected_surrogates = {int(k): v for k, v in cluster_surrogates.items()}
    audit.routing_table = dict(routing_table.cluster_to_config)
    audit.selected_configs = list(selected_configs)
    audit.risk_level = agent_risk_level
    audit.n_materializations = routing_table.n_materializations
    audit.token_budget_spent = tb.spent
    audit.token_budget_remaining = tb.remaining

    return PipelineResult(
        selected_configs=selected_configs,
        best_surrogate=best_surrogate,
        best_algorithm=best_algorithm,
        stage1_recommendations=recs,
        stage1_probe_fidelity_rho=float(fidelity_rho),
        stage2_surrogate_rhos=surrogate_rhos,
        stage3_algorithm_scores=algo_scores,
        stage4_retained_components=active_components,
        n_probe_configs_used=len(probe_data.config_ids),
        probing_expanded=probing_expanded,
        token_budget_total=tb.total,
        token_budget_spent=tb.spent,
        token_budget_remaining=tb.remaining,
        n_configs_selected=routing_table.n_materializations,
        thresholds_used={
            "rho_viable": thresholds.rho_viable,
            "rho_bakeoff": thresholds.rho_bakeoff,
            "linear_tolerance": thresholds.linear_tolerance,
            "interaction_ratio": thresholds.interaction_ratio,
            "surrogate_disagreement_threshold": thresholds.surrogate_disagreement_threshold,
        },
        routing_table=routing_table,
        cluster_surrogates=cluster_surrogates,
        query_cluster_info=query_cluster_info,
        risk_level=agent_risk_level,
        audit_log=audit.to_dict(),
    )


# ---------------------------------------------------------------------------
# Adaptive probing helper
# ---------------------------------------------------------------------------

def _expand_probes(probe_data, instance, schema, queries, *, n_additional: int, seed: int, query_clusters=None):
    """Probe n_additional extra configs and merge results into probe_data.

    Uses cheap LLM extraction + BTL judge (same cost model as initial probing).
    No ground-truth evaluation is performed.
    """
    import random
    from optimizer.config_space import generate_config_space
    from optimizer.probing import run_probes
    from judge.pair_selection import select_diverse_pairs

    existing_ids = set(probe_data.config_ids)
    all_configs = generate_config_space()
    remaining = [c for c in all_configs if c.config_id not in existing_ids]

    if not remaining:
        logger.info("No additional configs to probe (all %d already probed)", len(existing_ids))
        return probe_data

    rng = random.Random(seed + 1000)
    rng.shuffle(remaining)
    extra_configs = remaining[:n_additional]

    logger.info("Adaptive probing: adding %d configs %s",
                len(extra_configs), [c.config_id for c in extra_configs])

    extra_probe = run_probes(
        instance,
        schema,
        extra_configs,
        judge_pair_budget=max(2, n_additional),
        seed=seed + 1000,
        corpus_docs=instance.corpus if instance else None,
        eval_queries=queries,
        query_clusters=query_clusters,
    )

    # Merge: combine config_ids, tier1, glass_box, btl, pairwise
    import dataclasses
    from judge.btl import fit_btl
    from judge.btl_report import build_btl_report, log_btl_report

    merged_ids = list(probe_data.config_ids) + list(extra_probe.config_ids)
    merged_configs = {**probe_data.configs, **extra_probe.configs}
    merged_tier1 = {**probe_data.tier1_signals, **extra_probe.tier1_signals}
    merged_glass = {**probe_data.glass_box_composites, **extra_probe.glass_box_composites}
    merged_comparisons = list(probe_data.pairwise_comparisons) + list(extra_probe.pairwise_comparisons)
    merged_dbs = {**probe_data.databases, **extra_probe.databases}

    merged_btl = fit_btl(merged_comparisons, all_config_ids=merged_ids)
    merged_report = build_btl_report(merged_comparisons, merged_ids, merged_btl)
    log_btl_report(merged_report, logger)

    merged_cluster_gb = {**probe_data.cluster_glass_box_composites, **extra_probe.cluster_glass_box_composites}
    merged_cluster_btl = {**probe_data.cluster_btl_scores, **extra_probe.cluster_btl_scores}
    merged_cluster_unc = {**probe_data.cluster_btl_uncertainty, **extra_probe.cluster_btl_uncertainty}

    return dataclasses.replace(
        probe_data,
        config_ids=merged_ids,
        configs=merged_configs,
        tier1_signals=merged_tier1,
        glass_box_composites=merged_glass,
        pairwise_comparisons=merged_comparisons,
        btl_scores=merged_btl,
        databases=merged_dbs,
        total_cost=probe_data.total_cost + extra_probe.total_cost,
        btl_report=merged_report,
        cluster_glass_box_composites=merged_cluster_gb,
        cluster_btl_scores=merged_cluster_btl,
        cluster_btl_uncertainty=merged_cluster_unc,
    )
