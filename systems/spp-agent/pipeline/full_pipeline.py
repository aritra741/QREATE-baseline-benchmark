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


def _stage2_select_surrogate(
    surrogate_rhos: dict[str, float],
    candidate_order: list[str],
    thresholds,
) -> tuple[str, str]:
    """Apply Stage 1E thresholds to LOO ρ values and pick surrogate.

    Returns (surrogate_name, routing_reason).
    No ground truth accessed — surrogate_rhos came from _loo_rhos_from_probe().
    """
    viable = {k: v for k, v in surrogate_rhos.items()
              if k in candidate_order and v >= thresholds.rho_viable}
    bakeoff = {k: v for k, v in surrogate_rhos.items()
               if k in candidate_order
               and thresholds.rho_bakeoff <= v < thresholds.rho_viable}

    if viable:
        best = max(viable, key=viable.get)
        reason = f"viable_rho={viable[best]:.3f}>={thresholds.rho_viable}"
    elif bakeoff:
        best = max(bakeoff, key=bakeoff.get)
        reason = f"bakeoff_rho={bakeoff[best]:.3f}>={thresholds.rho_bakeoff}"
    else:
        # Fall back to candidate with best ρ among the ordered list
        best = max(
            (k for k in candidate_order if k in surrogate_rhos),
            key=lambda k: surrogate_rhos.get(k, -1.0),
            default="direct_probe_ranking",
        )
        reason = f"fallback_best_rho={surrogate_rhos.get(best, 0.0):.3f}"

    logger.info("Stage2 selected surrogate=%s reason=%s", best, reason)
    return best, reason


# ---------------------------------------------------------------------------
# Stage 2 → Stage 3 handoff
# ---------------------------------------------------------------------------

def _stage2_to_stage3_algorithm(
    stage1_recs: dict[str, Any],
    stage2_use_acquisition: bool,
) -> str:
    """Stage 1 surface-shape + Stage 2 acquisition flag choose the algorithm.

    - error_surface smooth + no acquisition  → greedy or coord_descent
    - error_surface rugged (local minima > 1) → bayesian_opt
    - Stage 2 selected GP/TPE               → bayesian_opt
    - otherwise                              → greedy
    """
    surface = stage1_recs.get("error_surface", {})
    rugged = not surface.get("smooth", True)

    if stage2_use_acquisition or rugged:
        algo = "bayesian_opt"
        logger.info("Stage2→Stage3: algorithm=bayesian_opt "
                    "(acquisition=%s rugged=%s)", stage2_use_acquisition, rugged)
    elif stage1_recs.get("density_greedy_viable", True):
        algo = "greedy"
        logger.info("Stage2→Stage3: algorithm=greedy (density_greedy_viable)")
    else:
        algo = "coord_descent"
        logger.info("Stage2→Stage3: algorithm=coord_descent")

    return algo


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
) -> PipelineResult:
    """Run the connected Stage 1 → 2 → 3 → 4 pipeline.

    All decisions are made from deployment-visible signals only.
    Ground-truth query error is NEVER accessed here.

    The number of configs selected is DERIVED from the token budget — it is
    not a parameter.  More configs always lowers SPP error (the formula takes
    the minimum over all selected configs), so we select as many as the
    remaining budget allows after paying for the probe run.

    Parameters
    ----------
    probe_data:
        ProbeData from a probe run (glass-box, BTL, tier1 signals).
    queries:
        The SQL workload queries (structure only, not answers).
    schema:
        Schema object (column names and types).
    thresholds:
        ThresholdConfig (learned offline from deployment-visible signals).
    token_budget:
        Total token allowance for the pipeline.  Probe cost is deducted first;
        whatever remains determines how many configs can be selected.
    candidate_ids:
        All config IDs to rank. Defaults to generate_config_space() ids.
    allow_adaptive_probing:
        If True and Stage 1E probe fidelity is very low, probe additional
        configs before proceeding (requires `instance` to be provided).
    instance:
        Instance object needed for adaptive probing (optional).
    """
    from optimizer.config_space import generate_config_space
    from optimizer.materialize import all_config_ids
    from stage1.characterizer import characterize
    from stage2.surrogate_comparison import compare_surrogates
    from stage3.comparison import compare_algorithms
    from surrogates.registry import ALL_SURROGATES, build_surrogate
    from utils.token_budget import CostModel, TokenBudget, budget_aware_select

    if candidate_ids is None:
        candidate_ids = all_config_ids()

    probing_expanded = False

    # -----------------------------------------------------------------------
    # Budget accounting: deduct probe cost, leaving remainder for selection
    # -----------------------------------------------------------------------
    tb = TokenBudget(total=int(token_budget))
    n_docs = len(getattr(instance, "corpus", [])) or 20  # fallback estimate
    n_probe_pairs = len(probe_data.pairwise_comparisons)
    cost_model = CostModel.from_tier0(
        {"avg_doc_tokens": probe_data.total_cost / max(1, len(probe_data.config_ids) * n_docs)}
        if probe_data.total_cost > 0 else {}
    )
    # Deduct what the probe run already spent (recorded in probe_data.total_cost)
    tb.spend(probe_data.total_cost, label="probe_run")
    logger.info(
        "Token budget: total=%.0f probe_spent=%.0f remaining=%.0f",
        tb.total, probe_data.total_cost, tb.remaining,
    )

    # -----------------------------------------------------------------------
    # Stage 1: Characterize the search space from probe signals
    # -----------------------------------------------------------------------
    logger.info("=== Stage 1: Search space characterization ===")
    stage1_report = characterize(
        probe_data,
        queries=queries,
        schema=schema,
        thresholds=thresholds,
        true_errors=None,    # no ground truth
        reward_rows=None,    # no reward table
        seed=seed,
    )
    recs = stage1_report.recommendations
    logger.info("Stage 1 recommendations: %s", recs)

    # -----------------------------------------------------------------------
    # Adaptive probing: if probe fidelity is too low, probe more configs
    # -----------------------------------------------------------------------
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
        probe_data = _expand_probes(probe_data, instance, schema, queries, n_additional=4, seed=seed)
        probing_expanded = True
        # Re-run Stage 1 on expanded probe data
        stage1_report = characterize(
            probe_data,
            queries=queries,
            schema=schema,
            thresholds=thresholds,
            true_errors=None,
            reward_rows=None,
            seed=seed,
        )
        recs = stage1_report.recommendations
        fidelity_rho = stage1_report.probe_fidelity.get("spearman_rho", 0.0) or 0.0
        logger.info("After expansion: Stage 1 recommendations=%s fidelity_rho=%.3f", recs, fidelity_rho)

    # -----------------------------------------------------------------------
    # Stage 2: Surrogate bakeoff (LOO Spearman ρ on probe signals)
    # Stage 1 recommendations narrow the candidate surrogate list.
    # -----------------------------------------------------------------------
    logger.info("=== Stage 2: Surrogate selection ===")
    all_surrogates = [k for k in ALL_SURROGATES if k != "random_ranking"]
    candidate_surrogates = _stage1_to_stage2_surrogate_list(recs, all_surrogates)

    # LOO ρ computed from probe data (no ground truth)
    surrogate_rhos = _loo_rhos_from_probe(probe_data)

    best_surrogate, surrogate_reason = _stage2_select_surrogate(
        surrogate_rhos, candidate_surrogates, thresholds
    )

    # Stage 2 also checks linear_tolerance (from ThresholdConfig)
    best_rho = surrogate_rhos.get(best_surrogate, 0.0)
    linear_rho = max(
        (surrogate_rhos.get(s, 0.0) for s in candidate_surrogates if "linear" in s),
        default=0.0,
    )
    if (
        best_surrogate not in ("linear_proxy_glass",)
        and linear_rho >= best_rho * (1.0 - thresholds.linear_tolerance)
        and not recs.get("use_nonlinear", False)
    ):
        logger.info(
            "Stage2: linear_proxy_glass within tolerance (%.3f vs %.3f); preferring linear for interpretability",
            linear_rho, best_rho,
        )
        best_surrogate = "linear_proxy_glass"

    use_acquisition = best_surrogate in ("gp_proxy_glass", "tpe_proxy")

    # -----------------------------------------------------------------------
    # Stage 2 → Stage 3 handoff: choose selection algorithm
    # -----------------------------------------------------------------------
    logger.info("=== Stage 3: Selection algorithm ===")
    best_algorithm = _stage2_to_stage3_algorithm(recs, use_acquisition)

    # Build and fit the selected surrogate
    surrogate = build_surrogate(best_surrogate, seed=seed)
    surrogate.fit(probe_data)

    # -----------------------------------------------------------------------
    # Budget-aware selection: select as many configs as the budget allows.
    # The count is derived, not specified.  All dictionary-norm configs are
    # free; llm-norm configs deduct from remaining budget.
    # -----------------------------------------------------------------------
    selected_configs = budget_aware_select(
        surrogate,
        candidate_ids,
        tb,
        cost_model,
        n_docs,
    )
    logger.info(
        "Budget-aware selection: n_selected=%d from %d candidates "
        "(token_remaining=%.0f)",
        len(selected_configs), len(candidate_ids), tb.remaining,
    )

    # Run algorithm comparison on the budget-selected subset for reporting
    # (greedy is used as reference; the selection above already used the surrogate)
    algo_results = compare_algorithms(
        surrogate,
        selected_configs,  # only score the actually-selected configs
        probe_data,
        budget=len(selected_configs),
        algorithms=[best_algorithm, "greedy"],
        seed=seed,
    )
    algo_scores = {r.algorithm: r.total_predicted_score for r in algo_results}

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
        n_configs_selected=len(selected_configs),
        thresholds_used={
            "rho_viable": thresholds.rho_viable,
            "rho_bakeoff": thresholds.rho_bakeoff,
            "linear_tolerance": thresholds.linear_tolerance,
            "interaction_ratio": thresholds.interaction_ratio,
        },
    )


# ---------------------------------------------------------------------------
# Adaptive probing helper
# ---------------------------------------------------------------------------

def _expand_probes(probe_data, instance, schema, queries, *, n_additional: int, seed: int):
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
        true_errors={},  # never populated; ground truth lives only in evaluation
    )
