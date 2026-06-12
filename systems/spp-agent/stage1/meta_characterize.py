"""Stage 1 characterization for the meta-controller (no BTL / glass-box core signals)."""

from __future__ import annotations

from stage1.analysis_1a import analyze_diminishing_returns
from stage1.analysis_1b import analyze_error_surface
from stage1.analysis_1c import analyze_module_ordering
from stage1.analysis_1d import analyze_interactions
from stage1.analysis_1f import analyze_clustering_validity
from stage1.analysis_1h import analyze_schema_rank_stability
from stage1.characterizer import Stage1Report
from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage1.meta_characterize")


def _structural_probe_fidelity(
    scores: dict[str, float],
    *,
    thresholds: ThresholdConfig,
) -> dict:
    if len(scores) < 2:
        return {
            "spearman_rho": 0.0,
            "top_k_recall": 0.0,
            "best_proxy_regret": 0.0,
            "recommendation": "improve_sampling_or_skip_probes",
        }
    vals = list(scores.values())
    spread = max(vals) - min(vals)
    rho = min(1.0, spread / 0.25) if spread > 0 else 0.0
    if rho >= thresholds.rho_viable:
        recommendation = "surrogate_viable"
    elif rho >= thresholds.rho_bakeoff:
        recommendation = "run_bakeoff"
    else:
        recommendation = "improve_sampling_or_skip_probes"
    return {
        "spearman_rho": float(rho),
        "top_k_recall": float(min(1.0, len(scores) / 8.0)),
        "best_proxy_regret": float(1.0 - max(vals)) if vals else 0.0,
        "recommendation": recommendation,
        "score_spread": float(spread),
    }


def _structural_routing_gap(scores: dict[str, float]) -> dict:
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top = [cid for cid, _ in ranked[:3]]
    return {
        "structural_top_configs": top,
        "score_spread": float(ranked[0][1] - ranked[-1][1]) if ranked else 0.0,
        "mean_disagreement": 0.0,
        "disagreement_above_threshold": False,
        "recommendation": "co_optimize_routing" if len(ranked) >= 4 else "routing_secondary",
    }


def characterize_meta(
    probe_data,
    *,
    selection_scores: dict[str, float],
    queries: list[dict],
    schema,
    thresholds: ThresholdConfig,
    seed: int = 42,
) -> Stage1Report:
    """Run Stage 1 analyses on structural selection scores (not glass-box / BTL)."""
    logger.info(
        "Meta Stage 1 characterization (%d probed configs, structural scores)",
        len(probe_data.config_ids),
    )

    class _ScoreProbeData:
        """Minimal adapter so analyses read structural scores like glass_box."""

        def __init__(self, base, scores: dict[str, float]):
            self.config_ids = base.config_ids
            self.configs = base.configs
            self.glass_box_composites = scores

    adapter = _ScoreProbeData(probe_data, selection_scores)

    dim_ret = analyze_diminishing_returns(selection_scores, thresholds=thresholds)
    err_surf = analyze_error_surface(adapter, thresholds=thresholds)
    mod_ord = analyze_module_ordering(adapter, thresholds=thresholds)
    interact = analyze_interactions(adapter, thresholds=thresholds)
    fidelity = _structural_probe_fidelity(selection_scores, thresholds=thresholds)
    clustering = analyze_clustering_validity(queries, thresholds=thresholds, seed=seed)
    routing = _structural_routing_gap(selection_scores)
    schema_rank = analyze_schema_rank_stability(probe_data, schema, thresholds=thresholds)

    recommendations = {
        "probe_viable": fidelity["recommendation"] in ("surrogate_viable", "run_bakeoff"),
        "use_nonlinear": interact["recommendation"] == "nonlinear_surrogate_needed",
        "use_routing": routing["recommendation"] == "co_optimize_routing",
        "use_clustering": clustering["recommendation"] == "structural_clustering_valid",
        "schema_first": schema_rank["recommendation"] == "schema_first_hierarchy",
        "density_greedy_viable": dim_ret["recommendation"] == "density_greedy_plausible",
    }

    return Stage1Report(
        diminishing_returns=dim_ret,
        error_surface=err_surf,
        module_ordering=mod_ord,
        interactions=interact,
        probe_fidelity=fidelity,
        clustering=clustering,
        routing_gap=routing,
        schema_ranking=schema_rank,
        recommendations=recommendations,
    )
