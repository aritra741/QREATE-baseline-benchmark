"""Assemble the full multi-stage algorithm stack for meta-controller reporting."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from agent.meta_actions import ACTION_LABELS, ACTION_TO_STAGE3_ALGORITHM
from diagnostics.structural_score import probe_data_with_selection_scores, structural_scores_from_probe
from pipeline.full_pipeline import _stage3_to_stage4_components
from stage1.characterizer import Stage1Report
from stage2.surrogate_comparison import compare_surrogates, compare_surrogates_per_cluster, select_best_surrogate
from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.composite_policy")

META_SURROGATE_CANDIDATES = [
    "structural_probe_ranking",
    "linear_proxy_glass",
    "rf_proxy_glass",
    "gbdt_proxy_glass",
]


def _surrogate_candidates(stage1_recs: dict[str, Any]) -> list[str]:
    names = list(META_SURROGATE_CANDIDATES)
    if stage1_recs.get("use_nonlinear"):
        if "gp_proxy_glass" not in names:
            names.append("gp_proxy_glass")
    return names


def _metrics_to_dict(metrics) -> dict[str, Any]:
    return {
        "name": metrics.name,
        "spearman_rho": round(float(metrics.spearman_rho), 4),
        "top_k_recall": round(float(metrics.top_k_recall), 4),
        "mean_regret": round(float(metrics.mean_regret), 6),
    }


def build_composite_algorithm_stack(
    *,
    stage1: Stage1Report,
    probe_data,
    query_clusters,
    thresholds: ThresholdConfig,
    solver_runs: list[dict[str, Any]],
    baseline_comparison: list[dict[str, Any]],
    chosen_family: str,
    selection_rationale: str,
    selected_configs: list[str],
    final_routing: dict[str, str],
    audit_log: list[dict[str, Any]],
    seed: int = 42,
) -> dict[str, Any]:
    """
    Paper-facing stack: Stage 1 analyses → Stage 2 surrogates (per cluster)
    → Stage 3 selection algorithms → Stage 4 architecture → deployment.
    """
    selection_scores = structural_scores_from_probe(probe_data)
    probe_view = probe_data_with_selection_scores(probe_data, selection_scores)
    recs = stage1.recommendations
    surrogate_names = _surrogate_candidates(recs)

    global_bakeoff = compare_surrogates(
        probe_view,
        surrogate_names,
        thresholds=thresholds,
        true_errors={cid: -selection_scores[cid] for cid in probe_data.config_ids},
        seed=seed,
    )
    global_surrogate = select_best_surrogate(global_bakeoff, recs)

    per_cluster_bakeoff = compare_surrogates_per_cluster(
        probe_view,
        surrogate_names,
        query_clusters,
        thresholds=thresholds,
        seed=seed,
    )
    cluster_surrogates: dict[int, str] = {}
    stage2_per_cluster: dict[str, Any] = {}
    for cluster_id, result in per_cluster_bakeoff.items():
        chosen = select_best_surrogate(result, recs)
        cluster_surrogates[cluster_id] = chosen
        ctype = query_clusters.cluster_types.get(cluster_id, "mixed")
        stage2_per_cluster[str(cluster_id)] = {
            "cluster_type": ctype,
            "n_queries": len(query_clusters.cluster_to_queries.get(cluster_id, [])),
            "chosen_surrogate": chosen,
            "surrogate_ranking": [
                _metrics_to_dict(m) for m in result.metrics
            ],
        }

    stage1_block = {
        "analyses": {
            "diminishing_returns": stage1.diminishing_returns.get("recommendation"),
            "error_surface": stage1.error_surface.get("recommendation"),
            "module_ordering": stage1.module_ordering.get("recommendation"),
            "interactions": stage1.interactions.get("recommendation"),
            "probe_fidelity": stage1.probe_fidelity.get("recommendation"),
            "clustering": stage1.clustering.get("recommendation"),
            "routing_gap": stage1.routing_gap.get("recommendation"),
            "schema_ranking": stage1.schema_ranking.get("recommendation"),
        },
        "recommendations": recs,
        "probe_fidelity_rho": stage1.probe_fidelity.get("spearman_rho"),
    }

    tried_by_agent = [
        {
            "algorithm_id": r.get("algorithm_family"),
            "algorithm_name": ACTION_LABELS.get(
                r.get("algorithm_family", ""), r.get("algorithm_family")
            ),
            "stage3_engine": ACTION_TO_STAGE3_ALGORITHM.get(r.get("algorithm_family", "")),
            "predicted_score": round(float(r.get("predicted_score", 0.0)), 4),
            "n_configs_selected": len(r.get("selected_configs") or []),
            "selected_by_agent": r.get("algorithm_family") == chosen_family,
        }
        for r in solver_runs
    ]

    all_stage3 = [
        {
            "algorithm_id": b.get("algorithm_family"),
            "algorithm_name": b.get("label")
            or ACTION_LABELS.get(b.get("algorithm_family", ""), ""),
            "stage3_engine": ACTION_TO_STAGE3_ALGORITHM.get(b.get("algorithm_family", "")),
            "predicted_score": round(float(b.get("predicted_score", 0.0)), 4),
            "n_configs_selected": b.get("n_selected_configs"),
            "selected_by_agent": b.get("algorithm_family") == chosen_family,
        }
        for b in baseline_comparison
    ]

    stage4_active = _stage3_to_stage4_components(recs, thresholds)
    all_stage4 = describe_ablation_components_flat(recs)

    cluster_labels = list(query_clusters.labels)
    cluster_to_config = {}
    if final_routing:
        q_to_cluster: dict[str, int] = {}
        for cid, qs in query_clusters.cluster_to_queries.items():
            for q in qs:
                q_to_cluster[str(q.get("query_id", ""))] = int(cid)
        for qid, pipe in final_routing.items():
            cid = q_to_cluster.get(qid)
            if cid is not None:
                cluster_to_config[str(cid)] = pipe

    return {
        "summary": (
            "Composite meta-policy: Stage 1 characterizes the workload, Stage 2 picks "
            "a surrogate per query cluster, Stage 3 compares selection algorithms "
            "(greedy, BO/TPE, hyperband, coordinate descent, ILP, clustered routing), "
            "Stage 4 gates architecture components, then the chosen selector deploys "
            "pipeline configs."
        ),
        "stage1_characterization": stage1_block,
        "stage2_surrogate_selection": {
            "evidence": "structural_probe_scores",
            "global_chosen_surrogate": global_surrogate,
            "global_surrogate_ranking": [
                _metrics_to_dict(m) for m in global_bakeoff.metrics
            ],
            "per_cluster": stage2_per_cluster,
            "cluster_surrogate_map": {
                str(k): v for k, v in cluster_surrogates.items()
            },
        },
        "stage3_config_selection": {
            "agent_chosen_algorithm_id": chosen_family,
            "agent_chosen_algorithm_name": ACTION_LABELS.get(chosen_family, chosen_family),
            "stage3_engine": ACTION_TO_STAGE3_ALGORITHM.get(chosen_family),
            "selection_rationale": selection_rationale,
            "algorithms_tried_by_agent": tried_by_agent,
            "all_selection_algorithms_benchmarked": all_stage3,
        },
        "stage4_architecture": {
            "active_components": stage4_active,
            "component_decisions": all_stage4,
        },
        "deployment": {
            "n_query_clusters": query_clusters.n_clusters,
            "cluster_types": {
                str(k): v for k, v in query_clusters.cluster_types.items()
            },
            "cluster_labels": cluster_labels,
            "selected_pipeline_configs": selected_configs,
            "cluster_to_pipeline_config": cluster_to_config,
            "query_to_pipeline_config": final_routing,
        },
        "decision_action_history": [
            {
                "round": e.get("round"),
                "action": (e.get("decision") or {}).get("action"),
                "rationale_code": (e.get("decision") or {}).get("rationale_code"),
                "confidence": (e.get("decision") or {}).get("confidence"),
                "expected_gain": (e.get("decision") or {}).get("expected_gain"),
                "budget_impact": (e.get("decision") or {}).get("budget_impact"),
            }
            for e in audit_log
        ],
    }


def describe_ablation_components_flat(stage1_recs: dict[str, Any]) -> list[dict[str, Any]]:
    """Stage-4 component retain/skip from Stage-1 flags (no GT ablation run)."""
    from stage4.ablation import describe_ablation_components

    decisions: list[dict[str, Any]] = []
    for component in describe_ablation_components():
        if component == "query_clustering":
            retained = bool(stage1_recs.get("use_clustering"))
            reason = "stage1_clustering_valid" if retained else "stage1_clustering_insufficient"
        elif component == "routing":
            retained = bool(stage1_recs.get("use_routing"))
            reason = "stage1_routing_gap" if retained else "stage1_routing_secondary"
        elif component == "schema_pruning":
            retained = bool(stage1_recs.get("schema_first"))
            reason = "stage1_schema_first" if retained else "stage1_flat_hierarchy"
        elif component == "surrogate":
            retained = bool(stage1_recs.get("probe_viable"))
            reason = "stage1_probe_viable" if retained else "stage1_probe_not_viable"
        else:
            retained = True
            reason = "default_retained"
        decisions.append(
            {
                "component": component,
                "retained": retained,
                "reason": reason,
            }
        )
    return decisions
