"""Compact evidence-driven state for the meta-controller agent."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from agent.meta_actions import ACTION_LABELS
from stage1.characterizer import Stage1Report


def _compact_workload_summary(queries: list[dict], demand_profile: dict[str, Any]) -> dict[str, Any]:
    n_join = sum(1 for q in queries if "join" in q.get("sql_query", "").lower())
    n_group = sum(
        1 for q in queries if "group by" in q.get("sql_query", "").lower()
    )
    return {
        "n_queries": len(queries),
        "n_join_queries": n_join,
        "n_group_by_queries": n_group,
        "has_join": bool(demand_profile.get("has_join")),
        "has_temporal": bool(demand_profile.get("has_temporal")),
        "n_demand_columns": len(demand_profile.get("columns", [])),
    }


def _compact_corpus_summary(supply_profile: dict[str, Any]) -> dict[str, Any]:
    cols = supply_profile.get("columns", [])
    if not cols:
        return {"n_profiled_columns": 0}
    diversity = [
        float((c.get("expression_diversity") or {}).get("diversity_ratio", 0.0))
        for c in cols
    ]
    ambiguous = [
        float((c.get("derivability") or {}).get("ambiguous_rate", 0.0)) for c in cols
    ]
    return {
        "n_profiled_columns": len(cols),
        "mean_diversity_ratio": round(sum(diversity) / len(diversity), 4) if diversity else 0.0,
        "max_diversity_ratio": round(max(diversity), 4) if diversity else 0.0,
        "mean_ambiguous_rate": round(sum(ambiguous) / len(ambiguous), 4) if ambiguous else 0.0,
        "feasibility_flags": sum(
            1 for c in cols if (c.get("recommendations") or {}).get("feasibility_flag")
        ),
    }


def _compact_probe_outcomes(
    probe_data,
    selection_scores: dict[str, float],
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    ranked = sorted(selection_scores.items(), key=lambda x: -x[1])
    return {
        "n_probed": len(probe_data.config_ids),
        "top_configs": [
            {"config_id": cid, "structural_score": round(score, 4)}
            for cid, score in ranked[:top_k]
        ],
        "score_spread": round(ranked[0][1] - ranked[-1][1], 4) if len(ranked) >= 2 else 0.0,
        "probe_token_cost": int(probe_data.total_cost),
    }


def _compact_stage1_summary(stage1: Stage1Report) -> dict[str, Any]:
    recs = stage1.recommendations
    return {
        "recommendations": recs,
        "diminishing_returns": stage1.diminishing_returns.get("recommendation"),
        "error_surface": stage1.error_surface.get("recommendation"),
        "interactions": stage1.interactions.get("recommendation"),
        "probe_fidelity_rho": stage1.probe_fidelity.get("spearman_rho"),
        "clustering": stage1.clustering.get("recommendation"),
        "routing": stage1.routing_gap.get("recommendation"),
    }


def _compact_solver_comparison(solver_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for run in solver_runs:
        out.append(
            {
                "algorithm_family": run.get("algorithm_family"),
                "label": ACTION_LABELS.get(run.get("algorithm_family", ""), ""),
                "predicted_score": round(float(run.get("predicted_score", 0.0)), 4),
                "n_selected_configs": len(run.get("selected_configs", [])),
                "wall_time_seconds": round(float(run.get("wall_time_seconds", 0.0)), 3),
            }
        )
    return sorted(out, key=lambda x: -x["predicted_score"])


def build_meta_controller_state(
    *,
    queries: list[dict],
    demand_profile: dict[str, Any],
    supply_profile: dict[str, Any],
    probe_data,
    selection_scores: dict[str, float],
    stage1: Stage1Report,
    budget_total: int,
    budget_spent: int,
    solver_runs: list[dict[str, Any]],
    chosen_algorithm_family: str | None,
    round_num: int,
) -> dict[str, Any]:
    return {
        "round": round_num,
        "workload_summary": _compact_workload_summary(queries, demand_profile),
        "corpus_profile_summary": _compact_corpus_summary(supply_profile),
        "probe_outcomes": _compact_probe_outcomes(probe_data, selection_scores),
        "stage1_summary": _compact_stage1_summary(stage1),
        "solver_comparison_summary": _compact_solver_comparison(solver_runs),
        "budget": {
            "total": budget_total,
            "spent": budget_spent,
            "remaining": max(0, budget_total - budget_spent),
        },
        "prior_chosen_algorithm_family": chosen_algorithm_family,
        "available_actions": sorted(
            [
                "probe_more",
                "use_greedy",
                "use_bo_tpe",
                "use_hyperband",
                "use_coordinate_descent",
                "use_ilp",
                "use_clustered_routing",
                "finalize",
            ]
        ),
    }


def stage1_report_to_dict(stage1: Stage1Report) -> dict[str, Any]:
    return asdict(stage1)
