from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.stats import spearmanr

from surrogates.registry import build_surrogate
from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage2.surrogate_comparison")


@dataclass
class SurrogateMetrics:
    name: str
    spearman_rho: float
    top_k_recall: float    # fraction of true top-3 that appear in proxy top-3
    mean_regret: float     # mean(proxy_best_error - oracle_error) across LOO folds
    cv_folds: int


@dataclass
class SurrogateComparisonResult:
    metrics: list[SurrogateMetrics]   # sorted by spearman_rho descending
    best_surrogate: str
    use_linear: bool       # True if linear within thresholds.linear_tolerance of best spearman
    use_acquisition_search: bool  # True if gp_proxy_glass or tpe_proxy is best
    ranking: list[str]     # surrogate names by spearman descending


def _make_reduced_probe_data(probe_data, held_out_id: str):
    """Build a copy of probe_data with one config removed."""
    reduced_ids = [cid for cid in probe_data.config_ids if cid != held_out_id]
    reduced_configs = {cid: probe_data.configs[cid] for cid in reduced_ids}
    reduced_tier1 = {cid: probe_data.tier1_signals[cid] for cid in reduced_ids}
    reduced_glass = {cid: probe_data.glass_box_composites[cid] for cid in reduced_ids}
    reduced_btl = {cid: probe_data.btl_scores[cid] for cid in reduced_ids if cid in probe_data.btl_scores}

    return replace(
        probe_data,
        config_ids=reduced_ids,
        configs=reduced_configs,
        tier1_signals=reduced_tier1,
        glass_box_composites=reduced_glass,
        btl_scores=reduced_btl,
    )


def _compute_metrics(
    surrogate_name: str,
    probe_data,
    true_errors: dict[str, float],
    seed: int,
) -> SurrogateMetrics:
    """Run LOO cross-validation for a single surrogate and compute metrics."""
    config_ids = list(probe_data.config_ids)
    n = len(config_ids)

    predicted: dict[str, float] = {}
    regrets: list[float] = []

    oracle_best_id = min(true_errors, key=true_errors.get)
    oracle_error = true_errors[oracle_best_id]

    for held_out_id in config_ids:
        reduced = _make_reduced_probe_data(probe_data, held_out_id)
        surrogate = build_surrogate(surrogate_name, seed=seed)
        surrogate.fit(reduced)
        pred_score = surrogate.score(held_out_id)
        predicted[held_out_id] = pred_score

        # Compute regret: score all non-held-out configs and pick proxy best
        remaining_ids = [cid for cid in config_ids if cid != held_out_id]
        if remaining_ids:
            scores = {cid: surrogate.score(cid) for cid in remaining_ids}
            proxy_best_id = max(scores, key=scores.get)
            proxy_best_error = true_errors.get(proxy_best_id, 0.0)
            regrets.append(proxy_best_error - oracle_error)

    # Spearman between predicted scores and true errors (negate true_errors for correlation)
    pred_arr = np.array([predicted[cid] for cid in config_ids])
    true_arr = np.array([-true_errors[cid] for cid in config_ids])

    if len(config_ids) < 3 or np.std(pred_arr) < 1e-12:
        rho = 0.0
    else:
        rho, _ = spearmanr(pred_arr, true_arr)
        if np.isnan(rho):
            rho = 0.0

    # Top-3 recall
    k = min(3, n)
    true_top_k = set(sorted(config_ids, key=lambda c: true_errors[c])[:k])
    pred_top_k = set(sorted(config_ids, key=lambda c: predicted.get(c, float("-inf")), reverse=True)[:k])
    top_k_recall = len(true_top_k & pred_top_k) / k if k > 0 else 0.0

    mean_regret = float(np.mean(regrets)) if regrets else 0.0

    return SurrogateMetrics(
        name=surrogate_name,
        spearman_rho=rho,
        top_k_recall=top_k_recall,
        mean_regret=mean_regret,
        cv_folds=n,
    )


def compare_surrogates(
    probe_data,
    surrogates: list[str],
    *,
    thresholds: ThresholdConfig,
    true_errors: dict[str, float] | None = None,
    seed: int = 42,
) -> SurrogateComparisonResult:
    """Compare surrogates via LOO cross-validation on probed configs."""
    config_ids = list(probe_data.config_ids)

    # If true_errors unavailable or too few probed configs, use glass_box as proxy
    if true_errors is None or len(config_ids) < 4:
        logger.info(
            "Using glass_box_composites as true_error proxy (configs=%d, true_errors=%s)",
            len(config_ids),
            "absent" if true_errors is None else f"n={len(true_errors)}",
        )
        true_errors = {
            cid: -probe_data.glass_box_composites[cid] for cid in config_ids
        }

    metrics_list: list[SurrogateMetrics] = []
    for name in surrogates:
        logger.info("Evaluating surrogate %s", name)
        m = _compute_metrics(name, probe_data, true_errors, seed)
        logger.info(
            "Surrogate %s rho=%.4f top3_recall=%.4f regret=%.6f folds=%d",
            m.name, m.spearman_rho, m.top_k_recall, m.mean_regret, m.cv_folds,
        )
        metrics_list.append(m)

    metrics_list.sort(key=lambda m: m.spearman_rho, reverse=True)
    ranking = [m.name for m in metrics_list]
    best_name = ranking[0] if ranking else ""
    best_rho = metrics_list[0].spearman_rho if metrics_list else 0.0

    # Check if linear surrogate is within tolerance of best
    linear_rho = 0.0
    for m in metrics_list:
        if m.name == "linear_proxy_glass":
            linear_rho = m.spearman_rho
            break
    use_linear = linear_rho >= best_rho * (1.0 - thresholds.linear_tolerance)

    use_acquisition_search = best_name in ("gp_proxy_glass", "tpe_proxy")

    result = SurrogateComparisonResult(
        metrics=metrics_list,
        best_surrogate=best_name,
        use_linear=use_linear,
        use_acquisition_search=use_acquisition_search,
        ranking=ranking,
    )
    logger.info(
        "Comparison complete best=%s use_linear=%s use_acquisition=%s ranking=%s",
        result.best_surrogate, result.use_linear, result.use_acquisition_search,
        result.ranking,
    )
    return result


def select_best_surrogate(
    result: SurrogateComparisonResult,
    stage1_recommendations: dict | None = None,
) -> str:
    """Select final surrogate considering stage1 recommendations."""
    if stage1_recommendations is None:
        return result.best_surrogate

    use_nonlinear = stage1_recommendations.get("use_nonlinear", False)
    nonlinear_names = {"rf_proxy_glass", "gbdt_proxy_glass", "gp_proxy_glass", "tpe_proxy"}

    # If stage1 says use nonlinear but linear is currently best, override
    if use_nonlinear and result.best_surrogate == "linear_proxy_glass":
        for name in result.ranking:
            if name in nonlinear_names:
                logger.info(
                    "Stage1 recommends nonlinear; overriding linear with %s", name,
                )
                return name

    # Prefer acquisition-search surrogates when they are best
    if result.use_acquisition_search:
        for name in result.ranking:
            if name in ("gp_proxy_glass", "tpe_proxy"):
                return name

    return result.best_surrogate
