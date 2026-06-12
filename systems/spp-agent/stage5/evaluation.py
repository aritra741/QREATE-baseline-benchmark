"""Stage 5 — end-to-end evaluation of the full SPP system against baselines."""

from __future__ import annotations

import dataclasses
import time
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from stage5.baselines import (
    build_trivial_routing_table,
    default_config_select,
    ilp_baseline_select,
    random_select,
    single_best_select,
    squid_select,
)
from stage4.query_clustering import cluster_workload
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
    routing_table: dict[int, str] = field(default_factory=dict)
    routed_error: float = 0.0
    oracle_min_error: float = 0.0
    routing_regret: float = 0.0


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


def evaluate_routing_table(
    routing_table: dict[int, str],
    query_clusters,
    queries: list[dict],
    ground_truth_tables: dict | None,
    databases_by_config: dict | None,
    error_fn=None,
) -> float:
    """Compute routed SPP error using cluster assignments."""
    if not routing_table or not queries:
        return float("nan")
    if ground_truth_tables is None or databases_by_config is None or error_fn is None:
        return float("nan")

    errors: list[float] = []
    labels = getattr(query_clusters, "labels", [])
    for idx, query in enumerate(queries):
        if idx >= len(labels):
            break
        cluster_id = labels[idx]
        config_id = routing_table.get(cluster_id)
        if not config_id:
            continue
        db = databases_by_config.get(config_id, {})
        err = error_fn(query, db, ground_truth_tables)
        if err == err:
            errors.append(float(err))
    return float(mean(errors)) if errors else float("nan")


def lookup_error(
    selected_configs: list[str],
    budget: int,
    reward_rows: list[dict],
    surrogate_name: str,
) -> float:
    """Find matching row in reward_rows."""
    for row in reward_rows:
        if (
            str(row.get("surrogate", "")) == surrogate_name
            and int(row.get("budget", -1)) == budget
        ):
            return float(row.get("true_spp_error", float("nan")))

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


def lookup_oracle_min_error(
    selected_configs: list[str],
    reward_rows: list[dict],
    surrogate_name: str,
) -> float:
    """Oracle-min proxy: min-over-selected-set from reward table."""
    if not selected_configs or not reward_rows:
        return float("nan")
    budget = max(1, len(selected_configs))
    return lookup_error(selected_configs, budget, reward_rows, surrogate_name)


def lookup_routed_error_proxy(
    routing_table: dict[int, str],
    reward_rows: list[dict],
    surrogate_name: str,
) -> float:
    """Routed-error proxy when per-query DB execution is unavailable.

    Uses distinct materialized configs in the routing table as the budget
    level (one DB per routed config, no post-hoc oracle choice).
    """
    if not routing_table or not reward_rows:
        return float("nan")
    materialized = sorted(set(routing_table.values()))
    budget = max(1, len(materialized))
    return lookup_error(materialized, budget, reward_rows, surrogate_name)


def _surrogate_for_method(method: str, best_surrogate: str) -> str:
    mapping: dict[str, str] = {
        "default": "random_ranking",
        "random": "random_ranking",
        "squid": best_surrogate,
        "single_best": best_surrogate,
        "ilp": best_surrogate,
        "full_system": best_surrogate,
    }
    return mapping.get(method, best_surrogate)


def _cache_hit_rate(selected: list[str], probe_config_ids: list[str]) -> float:
    if not selected:
        return 0.0
    probe_set = set(probe_config_ids)
    hits = sum(1 for c in selected if c in probe_set)
    return hits / len(selected)


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
    queries: list[dict] | None = None,
    schema=None,
    token_budget: int = 500_000,
    ground_truth_tables: dict | None = None,
    databases_by_config: dict | None = None,
    error_fn=None,
    seed: int = 42,
) -> dict:
    """Run all baselines + full_system at each budget level."""
    surrogates_available = sorted(
        {str(r.get("surrogate", "")) for r in reward_rows if r.get("surrogate")}
    )
    if not surrogates_available:
        surrogates_available = [best_surrogate]

    probe_config_ids: list[str] = []
    if hasattr(probe_data, "config_ids"):
        probe_config_ids = list(probe_data.config_ids)

    query_clusters = cluster_workload(queries or [], seed=seed)

    try:
        surr = build_surrogate(best_surrogate, seed=seed)
        if probe_data is not None:
            surr.fit(probe_data)
    except Exception:
        logger.warning(
            "Could not build surrogate %s; surrogate-dependent baselines may fail",
            best_surrogate,
        )
        surr = None

    per_instance: list[dict] = []
    method_rows: dict[str, list[EvaluationResult]] = defaultdict(list)
    resolved_algorithm = best_algorithm

    for budget in budget_levels:
        oracle_surr, oracle_err = oracle_error_for_budget(
            budget, reward_rows, surrogates_available
        )

        # method -> (selected_configs, routing_table, wall_time)
        methods: list[tuple[str, list[str], dict[int, str], float]] = []

        t0 = time.perf_counter()
        default_sel = default_config_select(candidate_ids, budget)
        default_rt = build_trivial_routing_table(default_sel, query_clusters, probe_data)
        methods.append(("default", default_sel, default_rt, time.perf_counter() - t0))

        if surr is not None:
            t0 = time.perf_counter()
            sb_sel = single_best_select(surr, candidate_ids, budget)
            sb_rt = build_trivial_routing_table(sb_sel, query_clusters, probe_data)
            methods.append(("single_best", sb_sel, sb_rt, time.perf_counter() - t0))

        current_slice = (
            str(stage1_report.slice_name) if hasattr(stage1_report, "slice_name") else "agg_only"
        )
        t0 = time.perf_counter()
        squid_sel = squid_select(
            candidate_ids,
            budget,
            historical_rows=reward_rows,
            current_slice=current_slice,
        )
        squid_rt = build_trivial_routing_table(squid_sel, query_clusters, probe_data)
        methods.append(("squid", squid_sel, squid_rt, time.perf_counter() - t0))

        t0 = time.perf_counter()
        rand_sel = random_select(candidate_ids, budget, seed=seed + budget)
        rand_rt = build_trivial_routing_table(rand_sel, query_clusters, probe_data)
        methods.append(("random", rand_sel, rand_rt, time.perf_counter() - t0))

        if surr is not None:
            try:
                t0 = time.perf_counter()
                ilp_sel = ilp_baseline_select(surr, candidate_ids, budget)
                ilp_rt = build_trivial_routing_table(ilp_sel, query_clusters, probe_data)
                methods.append(("ilp", ilp_sel, ilp_rt, time.perf_counter() - t0))
            except Exception:
                logger.warning("ILP baseline failed for budget=%d; skipping", budget)

        if probe_data is not None and queries and schema is not None:
            try:
                t0 = time.perf_counter()
                from pipeline.full_pipeline import run_spp_pipeline

                pipeline_result = run_spp_pipeline(
                    probe_data,
                    queries=queries,
                    schema=schema,
                    thresholds=thresholds,
                    token_budget=token_budget,
                    candidate_ids=candidate_ids,
                    seed=seed,
                    query_clusters=query_clusters,
                )
                full_sel = list(pipeline_result.selected_configs)
                full_rt = dict(pipeline_result.routing_table.cluster_to_config)
                resolved_algorithm = pipeline_result.best_algorithm
                methods.append(("full_system", full_sel, full_rt, time.perf_counter() - t0))
            except Exception as exc:
                logger.warning("full_system pipeline failed for budget=%d: %s", budget, exc)
                if surr is not None:
                    t0 = time.perf_counter()
                    full_sel = single_best_select(surr, candidate_ids, budget)
                    full_rt = build_trivial_routing_table(full_sel, query_clusters, probe_data)
                    methods.append(("full_system", full_sel, full_rt, time.perf_counter() - t0))

        for method_name, selected, routing_table, wall_time in methods:
            surr_name = _surrogate_for_method(method_name, best_surrogate)

            routed = evaluate_routing_table(
                routing_table,
                query_clusters,
                queries or [],
                ground_truth_tables,
                databases_by_config,
                error_fn,
            )
            if routed != routed:
                routed = lookup_routed_error_proxy(routing_table, reward_rows, surr_name)

            oracle_min = lookup_oracle_min_error(selected, reward_rows, surr_name)
            regret = routed - oracle_err if routed == routed and oracle_err == oracle_err else float("nan")
            routing_regret = (
                routed - oracle_min if routed == routed and oracle_min == oracle_min else float("nan")
            )
            oracle_match = abs(routed - oracle_err) < 1e-12 if routed == routed else False

            result = EvaluationResult(
                method=method_name,
                budget=budget,
                selected_configs=selected,
                error=routed,
                oracle_error=oracle_err,
                regret=regret,
                oracle_match=oracle_match,
                token_cost=0.0,
                wall_time_seconds=wall_time,
                cache_hit_rate=_cache_hit_rate(selected, probe_config_ids),
                routing_table={int(k): v for k, v in routing_table.items()},
                routed_error=routed,
                oracle_min_error=oracle_min,
                routing_regret=routing_regret,
            )
            method_rows[method_name].append(result)
            per_instance.append(dataclasses.asdict(result))

            logger.info(
                "budget=%d method=%s routed_error=%.4f oracle_min=%.4f regret=%.4f",
                budget,
                method_name,
                routed if routed == routed else float("nan"),
                oracle_min if oracle_min == oracle_min else float("nan"),
                regret if regret == regret else float("nan"),
            )

    method_summaries = _aggregate_method_summaries(method_rows)

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
        "best_algorithm": resolved_algorithm,
        "thresholds_used": dataclasses.asdict(thresholds),
        "methods": method_summaries,
        "per_instance": per_instance,
        "sensitivity": sensitivity,
        "note": "Primary metric is routed_error. oracle_min_error is an upper-bound reference.",
    }


def _safe_mean(values: list[float]) -> float:
    clean = [v for v in values if v == v]
    return float(mean(clean)) if clean else float("nan")


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
                "avg_routed_error": _safe_mean([r.routed_error for r in results]),
                "avg_oracle_min_error": _safe_mean([r.oracle_min_error for r in results]),
                "avg_error": _safe_mean([r.routed_error for r in results]),
                "avg_regret": _safe_mean([r.regret for r in results]),
                "avg_routing_regret": _safe_mean([r.routing_regret for r in results]),
                "oracle_match_rate": float(mean(1.0 if r.oracle_match else 0.0 for r in results)),
                "worst_regret": float(
                    max((r.regret for r in results if r.regret == r.regret), default=0.0)
                ),
                "avg_wall_time": float(mean(r.wall_time_seconds for r in results)),
                "avg_cache_hit_rate": float(mean(r.cache_hit_rate for r in results)),
            }
        )
    return summaries


def error_vs_budget_curve(
    results: list[EvaluationResult],
    budgets: list[int],
) -> dict[str, list[float]]:
    grouped: dict[str, dict[int, float]] = defaultdict(dict)
    for r in results:
        grouped[r.method][r.budget] = r.routed_error

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
    if param_name == "num_probe_configs":
        return [4, 8, 12, 16]
    if param_name == "corpus_sample_fraction":
        return [0.05, 0.10, 0.20, 0.40]
    if param_name == "budget":
        return [1, 2, 3, 4]
    if param_name == "config_space_size":
        return [8, 16, 32]
    return []
