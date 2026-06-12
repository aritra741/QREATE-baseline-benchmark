from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from optimizer.probing import ProbeData
from pipeline.schema import Schema
from stage1.analysis_1a import analyze_diminishing_returns
from stage1.analysis_1b import analyze_error_surface
from stage1.analysis_1c import analyze_module_ordering
from stage1.analysis_1d import analyze_interactions
from stage1.analysis_1e import analyze_probe_fidelity
from stage1.analysis_1f import analyze_clustering_validity
from stage1.analysis_1g import analyze_routing_gap
from stage1.analysis_1h import analyze_schema_rank_stability
from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage1.characterizer")


@dataclass
class Stage1Report:
    diminishing_returns: dict
    error_surface: dict
    module_ordering: dict
    interactions: dict
    probe_fidelity: dict
    clustering: dict
    routing_gap: dict
    schema_ranking: dict
    recommendations: dict


def characterize(
    probe_data: ProbeData,
    *,
    queries: list[dict],
    schema: Schema,
    thresholds: ThresholdConfig,
    true_errors: dict[str, float] | None = None,
    seed: int = 42,
) -> Stage1Report:
    """Run all Stage 1 analyses and aggregate recommendations."""
    logger.info("Starting Stage 1 characterisation (%d probed configs)", len(probe_data.config_ids))

    scores_for_1a = dict(probe_data.glass_box_composites)
    dim_ret = analyze_diminishing_returns(scores_for_1a, thresholds=thresholds)

    err_surf = analyze_error_surface(probe_data, thresholds=thresholds)

    mod_ord = analyze_module_ordering(probe_data, thresholds=thresholds)

    interact = analyze_interactions(probe_data, thresholds=thresholds)

    proxy_scores = dict(probe_data.glass_box_composites)
    if true_errors is not None:
        fidelity_errors = true_errors
    elif probe_data.btl_scores:
        # Deployment-visible proxy: correlate glass-box with BTL (never probe_data.true_errors)
        fidelity_errors = {cid: -score for cid, score in probe_data.btl_scores.items()}
    else:
        fidelity_errors = {}
    fidelity = analyze_probe_fidelity(proxy_scores, fidelity_errors, thresholds=thresholds)

    clustering = analyze_clustering_validity(queries, thresholds=thresholds, seed=seed)

    routing = analyze_routing_gap(probe_data, thresholds=thresholds)

    schema_rank = analyze_schema_rank_stability(probe_data, schema, thresholds=thresholds)

    recommendations = {
        "probe_viable": fidelity["recommendation"] in ("surrogate_viable", "run_bakeoff"),
        "use_nonlinear": interact["recommendation"] == "nonlinear_surrogate_needed",
        "use_routing": routing["recommendation"] == "co_optimize_routing",
        "use_clustering": clustering["recommendation"] == "structural_clustering_valid",
        "schema_first": schema_rank["recommendation"] == "schema_first_hierarchy",
        "density_greedy_viable": dim_ret["recommendation"] == "density_greedy_plausible",
    }

    logger.info("Stage 1 recommendations: %s", recommendations)
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


def save_stage1_report(report: Stage1Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    logger.info("Saved Stage 1 report to %s", path)


def load_stage1_report(path: Path) -> Stage1Report:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Stage1Report(**data)
