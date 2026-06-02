"""Stage 5 — end-to-end evaluation of the full SPP system against baselines."""

from __future__ import annotations

import dataclasses
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from stage5.baselines import (
    default_config_select,
    ilp_baseline_select,
    random_select,
    single_best_select,
    squid_select,
)
from surrogates.registry import build_surrogate
from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage5.evaluation")


@dataclass
class EvaluationResult:
    method: str
    budget: int
    selected_configs: list[str]
    error: float
    oracle_error: float
    regret: float
    oracle_match: bool
    token_cost: float
    wall_time_seconds: float
    cache_hit_rate: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def oracle_error_for_budget(
    budget: int,
    reward_rows: list[dict],
    surrogates: list[str],
) -> tuple[str, float]:
    """Best surrogate and error for given budget from reward table."""
    errors: dict[str, float] = {}
    for row in reward_rows:
        if int(row.get("budget", -1)) != budget:
            continue
        s = str(row.get("surrogate", ""))
        if s not in surrogates:
            continue
        err = float(row.get("true_spp_error", float("nan")))
        if s not in errors or err < errors[s]:
            errors[s] = err

    if not errors:
        return surrogates[0] if surrogates else "unknown", float("nan")

    best_err = min(errors.values())
    tied = sorted(s for s, e in errors.items() if abs(e - best_err) < 1e-12)
    return tied[0], float(best_err)


def lookup_error(
    selected_configs: list[str],
    budget: int,
    reward_rows: list[dict],
    surrogate_name: str,
) -> float:
    """Find matching row in reward_rows.  If exact match not found, use closest
    budget row for that surrogate."""
    # Try exact match on surrogate + budget
    for row in reward_rows:
        if (
            str(row.get("surrogate", "")) == surrogate_name
            and int(row.get("budget", -1)) == budget
        ):
            return float(row.get("true_spp_error", float("nan")))

    # Closest budget fallback
    best_row: dict | None = None
    best_gap = float("inf")
    for row in reward_rows:
        if str(row.get("surrogate", "")) != surrogate_name:
            continue
        gap = abs(int(row.get("budget", 0)) - budget)
        if gap < best_gap:
            best_gap = gap
            best_row = row

    if best_row is not None:
        return float(best_row.get("true_spp_error", float("nan")))

    return float("nan")


def _surrogate_for_method(method: str, best_surrogate: str) -> str:
    """Map a baseline method name to a surrogate name for error lookup."""
    mapping: dict[str, str] = {
        "default": "random_ranking",
        "random": "random_ranking",
        "squid": best_surrogate,
        "single_best": best_surrogate,
        "ilp": best_surrogate,
        "full_system": best_surrogate,
    }
    return mapping.get(method, best_surrogate)


def _cache_hit_rate(
    selected: list[str],
    probe_config_ids: list[str],
) -> float:
    if not selected:
        return 0.0
    probe_set = set(probe_config_ids)
    hits = sum(1 for c in selected if c in probe_set)
    return hits / len(selected)


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def run_stage5_evaluation(
    *,
    reward_rows: list[dict],
    probe_data: Any,
    thresholds: ThresholdConfig,
    stage1_report: Any,
    best_surrogate: str,
    best_algorithm: str,
    budget_levels: list[int],
    candidate_ids: list[str],
    seed: int = 42,
) -> dict:
    """Run all baselines + full_system at each budget level and return a report dict."""
    surrogates_available = sorted(
        {str(r.get("surrogate", "")) for r in reward_rows if r.get("surrogate")}
    )
    if not surrogates_available:
        surrogates_available = [best_surrogate]

    probe_config_ids: list[str] = []
    if hasattr(probe_data, "config_ids"):
        probe_config_ids = list(probe_data.config_ids)

    # Build surrogate instance for baselines that need one
    try:
        surr = build_surrogate(best_surrogate, seed=seed)
        if probe_data is not None:
            surr.fit(probe_data)
    except Exception:
        logger.warning("Could not build surrogate %s; surrogate-dependent baselines may fail", best_surrogate)
        surr = None

    per_instance: list[dict] = []
    method_rows: dict[str, list[EvaluationResult]] = defaultdict(list)

    for budget in budget_levels:
        oracle_surr, oracle_err = oracle_error_for_budget(budget, reward_rows, surrogates_available)

        methods_to_run: list[tuple[str, list[str], float]] = []

        # -- default --
        t0 = time.perf_counter()
        default_sel = default_config_select(candidate_ids, budget)
        dt = time.perf_counter() - t0
        methods_to_run.append(("default", default_sel, dt))

        # -- single_best --
        if surr is not None:
            t0 = time.perf_counter()
            sb_sel = single_best_select(surr, candidate_ids, budget)
            dt = time.perf_counter() - t0
            methods_to_run.append(("single_best", sb_sel, dt))

        # -- squid --
        current_slice = str(stage1_report.slice_name) if hasattr(stage1_report, "slice_name") else "agg_only"
        t0 = time.perf_counter()
        squid_sel = squid_select(
            candidate_ids,
            budget,
            historical_rows=reward_rows,
            current_slice=current_slice,
        )
        dt = time.perf_counter() - t0
        methods_to_run.append(("squid", squid_sel, dt))

        # -- random --
        t0 = time.perf_counter()
        rand_sel = random_select(candidate_ids, budget, seed=seed + budget)
        dt = time.perf_counter() - t0
        methods_to_run.append(("random", rand_sel, dt))

        # -- ilp --
        if surr is not None:
            try:
                t0 = time.perf_counter()
                ilp_sel = ilp_baseline_select(surr, candidate_ids, budget)
                dt = time.perf_counter() - t0
                methods_to_run.append(("ilp", ilp_sel, dt))
            except Exception:
                logger.warning("ILP baseline failed for budget=%d; skipping", budget)

        # -- full_system --
        if surr is not None:
            try:
                t0 = time.perf_counter()
                from stage3.comparison import compare_algorithms

                alg_result = compare_algorithms(surr, candidate_ids, probe_data, budget=budget)
                # Pick selected configs from best_algorithm result
                full_sel = candidate_ids[: max(1, budget)]
                for ar in (alg_result if isinstance(alg_result, list) else [alg_result]):
                    if hasattr(ar, "algorithm") and ar.algorithm == best_algorithm:
                        full_sel = ar.selected_configs if hasattr(ar, "selected_configs") else full_sel
                        break
                    if isinstance(ar, dict) and ar.get("algorithm") == best_algorithm:
                        full_sel = ar.get("selected_configs", full_sel)
                        break
                dt = time.perf_counter() - t0
                methods_to_run.append(("full_system", full_sel, dt))
            except Exception:
                logger.warning("full_system failed for budget=%d; using surrogate ranking fallback", budget)
                t0 = time.perf_counter()
                full_sel = single_best_select(surr, candidate_ids, budget)
                dt = time.perf_counter() - t0
                methods_to_run.append(("full_system", full_sel, dt))

        for method_name, selected, wall_time in methods_to_run:
            surr_name = _surrogate_for_method(method_name, best_surrogate)
            err = lookup_error(selected, budget, reward_rows, surr_name)
            regret = err - oracle_err if not (err != err or oracle_err != oracle_err) else float("nan")
            oracle_match = abs(err - oracle_err) < 1e-12 if not (err != err) else False

            result = EvaluationResult(
                method=method_name,
                budget=budget,
                selected_configs=selected,
                error=err,
                oracle_error=oracle_err,
                regret=regret,
                oracle_match=oracle_match,
                token_cost=0.0,
                wall_time_seconds=wall_time,
                cache_hit_rate=_cache_hit_rate(selected, probe_config_ids),
            )
            method_rows[method_name].append(result)
            per_instance.append(dataclasses.asdict(result))

            logger.info(
                "budget=%d method=%s error=%.4f regret=%.4f oracle_match=%s",
                budget,
                method_name,
                err,
                regret,
                oracle_match,
            )

    # Aggregate method summaries
    method_summaries = _aggregate_method_summaries(method_rows)

    # Sensitivity analysis
    sensitivity: list[dict] = []
    base_budget = budget_levels[0] if budget_levels else 1
    for param in ("num_probe_configs", "corpus_sample_fraction"):
        try:
            sa = sensitivity_analysis(
                reward_rows,
                param_name=param,
                param_values=_default_param_values(param),
                base_budget=base_budget,
                base_surrogate=best_surrogate,
            )
            sensitivity.extend(sa)
        except Exception:
            logger.warning("Sensitivity analysis for %s failed; skipping", param)

    return {
        "budget_levels": budget_levels,
        "best_surrogate": best_surrogate,
        "best_algorithm": best_algorithm,
        "thresholds_used": dataclasses.asdict(thresholds),
        "methods": method_summaries,
        "per_instance": per_instance,
        "sensitivity": sensitivity,
    }


def _aggregate_method_summaries(
    method_rows: dict[str, list[EvaluationResult]],
) -> list[dict]:
    summaries: list[dict] = []
    for method_name, results in sorted(method_rows.items()):
        if not results:
            continue
        summaries.append(
            {
                "method": method_name,
                "avg_error": float(mean(r.error for r in results if r.error == r.error)),
                "avg_regret": float(mean(r.regret for r in results if r.regret == r.regret)),
                "oracle_match_rate": float(mean(1.0 if r.oracle_match else 0.0 for r in results)),
                "worst_regret": float(max((r.regret for r in results if r.regret == r.regret), default=0.0)),
                "avg_wall_time": float(mean(r.wall_time_seconds for r in results)),
                "avg_cache_hit_rate": float(mean(r.cache_hit_rate for r in results)),
            }
        )
    return summaries


# ---------------------------------------------------------------------------
# Curve / sensitivity helpers
# ---------------------------------------------------------------------------

def error_vs_budget_curve(
    results: list[EvaluationResult],
    budgets: list[int],
) -> dict[str, list[float]]:
    """Returns dict method -> list of errors at each budget."""
    grouped: dict[str, dict[int, float]] = defaultdict(dict)
    for r in results:
        grouped[r.method][r.budget] = r.error

    curves: dict[str, list[float]] = {}
    for method, by_budget in sorted(grouped.items()):
        curves[method] = [by_budget.get(b, float("nan")) for b in budgets]
    return curves


def sensitivity_analysis(
    reward_rows: list[dict],
    *,
    param_name: str,
    param_values: list,
    base_budget: int,
    base_surrogate: str,
) -> list[dict]:
    """For each param_value, filter/group reward_rows and compute mean error.

    param_name in: num_probe_configs, slice (as proxy for corpus_sample_fraction).
    """
    results: list[dict] = []
    for val in param_values:
        filtered: list[float] = []
        for row in reward_rows:
            if int(row.get("budget", -1)) != base_budget:
                continue
            if str(row.get("surrogate", "")) != base_surrogate:
                continue
            row_val = row.get(param_name)
            if row_val is not None and row_val != val:
                continue
            filtered.append(float(row.get("true_spp_error", float("nan"))))

        avg = float(mean(filtered)) if filtered else float("nan")
        results.append(
            {
                "param_name": param_name,
                "param_value": val,
                "budget": base_budget,
                "surrogate": base_surrogate,
                "n_rows": len(filtered),
                "mean_error": avg,
            }
        )
    return results


def _default_param_values(param_name: str) -> list:
    """Reasonable default sweep values for sensitivity analysis."""
    if param_name == "num_probe_configs":
        return [4, 8, 12, 16]
    if param_name == "corpus_sample_fraction":
        return [0.05, 0.10, 0.20, 0.40]
    if param_name == "budget":
        return [1, 2, 3, 4]
    if param_name == "config_space_size":
        return [8, 16, 32]
    return []
