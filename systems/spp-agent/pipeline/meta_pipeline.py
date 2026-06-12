"""Meta-selection pipeline: bootstrap probes + solver-family controller."""

from __future__ import annotations

import random
from typing import Any

from agent.meta_controller import MetaControllerRunResult, run_meta_controller_loop
from agent.phases.demand_profile import extract_demand_profile
from agent.phases.supply_profile import build_supply_profile
from optimizer.config_space import generate_config_space
from optimizer.probing import run_probes
from thresholds.schema import load_thresholds
from utils.config import load_config
from utils.logging import setup_logger

logger = setup_logger("spp.meta_pipeline")

INITIAL_PROBE_COUNT = 8


def _select_initial_probe_configs(seed: int, n: int = INITIAL_PROBE_COUNT):
    all_configs = generate_config_space()
    rng = random.Random(seed)
    rng.shuffle(all_configs)
    pool = sorted(
        all_configs[: n * 6],
        key=lambda c: (c.miss_strategy == "drop", c.norm_strategy == "llm"),
    )
    return pool[:n]


def bootstrap_probes(
    instance,
    *,
    shared_extraction=None,
    seed: int = 42,
    n_configs: int = INITIAL_PROBE_COUNT,
):
    """Setup-only bootstrap: materialize a small probe set (no BTL judge)."""
    schema = instance.schema
    probe_configs = _select_initial_probe_configs(seed, n=n_configs)
    logger.info(
        "Bootstrap probes: %d configs, skip_judge=True",
        len(probe_configs),
    )
    probe_data = run_probes(
        instance,
        schema,
        probe_configs,
        judge_pair_budget=0,
        seed=seed,
        corpus_docs=list(instance.corpus),
        eval_queries=list(instance.queries),
        shared_extraction=shared_extraction,
        skip_judge=True,
    )
    return probe_data


def run_meta_spp_pipeline(
    instance,
    *,
    token_budget: int | None = None,
    shared_extraction=None,
    seed: int = 42,
    use_heuristic: bool = True,
    max_rounds: int = 8,
) -> MetaControllerRunResult:
    """
    Paper path: agent selects a solver family under budget.

    Bootstrap (demand/supply profiling + initial probes) is setup only.
    """
    cfg = load_config()
    budget = int(token_budget or cfg.get("token_budget", 80_000))
    seed = int(seed if seed is not None else cfg["experiment"]["seed"])

    demand_profile = extract_demand_profile(
        instance.queries,
        instance.schema,
        use_heuristic=True,
    )
    supply_profile = build_supply_profile(
        instance.corpus,
        demand_profile,
        instance.schema,
    )

    probe_data = bootstrap_probes(
        instance,
        shared_extraction=shared_extraction,
        seed=seed,
    )

    thresholds = load_thresholds()
    result = run_meta_controller_loop(
        instance,
        probe_data=probe_data,
        demand_profile=demand_profile,
        supply_profile=supply_profile,
        token_budget_total=budget,
        thresholds=thresholds,
        seed=seed,
        max_rounds=max_rounds,
        use_heuristic=use_heuristic,
    )
    result.baseline_comparison = _baseline_solver_comparison(
        probe_data,
        budget=max(2, len(result.selected_configs) or 2),
        seed=seed,
    )
    from pipeline.composite_policy import build_composite_algorithm_stack

    result.algorithm_stack = build_composite_algorithm_stack(
        stage1=result.stage1_report,
        probe_data=result.probe_data,
        query_clusters=result.query_clusters,
        thresholds=thresholds,
        solver_runs=result.solver_comparison,
        baseline_comparison=result.baseline_comparison,
        chosen_family=result.chosen_algorithm_family,
        selection_rationale=result.selection_rationale,
        selected_configs=result.selected_configs,
        final_routing=result.final_routing,
        audit_log=result.audit_log,
        seed=seed,
    )
    logger.info(
        "Meta pipeline complete: chosen_family=%s configs=%s rounds=%d",
        result.chosen_algorithm_family,
        result.selected_configs,
        result.rounds,
    )
    return result


def _baseline_solver_comparison(probe_data, *, budget: int, seed: int) -> list[dict[str, Any]]:
    """Offline comparison of all solver families on structural evidence (for reporting)."""
    from agent.meta_actions import ACTION_LABELS, STAGE3_ALGORITHM_TO_ACTION
    from stage3.comparison import ALL_ALGORITHMS, compare_algorithms
    from surrogates.structural_probe_ranking import StructuralProbeRankingSurrogate

    surrogate = StructuralProbeRankingSurrogate()
    surrogate.fit(probe_data)
    results = compare_algorithms(
        surrogate,
        list(probe_data.config_ids),
        probe_data,
        budget=budget,
        algorithms=list(ALL_ALGORITHMS),
        seed=seed,
    )
    out: list[dict[str, Any]] = []
    for row in results:
        family = STAGE3_ALGORITHM_TO_ACTION.get(row.algorithm, row.algorithm)
        out.append(
            {
                "algorithm_family": family,
                "label": ACTION_LABELS.get(family, row.algorithm),
                "predicted_score": float(row.total_predicted_score),
                "n_selected_configs": len(row.selected_configs),
                "selected_configs": list(row.selected_configs),
                "wall_time_seconds": float(row.wall_time_seconds),
            }
        )
    return out
