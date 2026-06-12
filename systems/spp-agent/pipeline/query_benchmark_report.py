"""Full per-query benchmark report for five-slice evaluation."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sqlglot
from sqlglot import exp

from data.aggregation_slices import classify_aggregation_slice
from pipeline.evaluation import (
    _alignment_keys_for_match,
    _normalize_join_keys_case_insensitive,
    _run_gold_sql,
)
from pipeline.execution import execute_sql_on_db
from pipeline.humanize_report import humanize_agent_run, humanize_per_query_agent
from pipeline.relative_error import (
    _aggregate_column_names,
    cell_relative_error_pct,
    query_relative_error_pct,
)


def _df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    cleaned = df.replace({np.nan: None})
    return json.loads(cleaned.to_json(orient="records"))


def _summarize_values(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "max": 0.0, "min": 0.0, "std": 0.0}
    if len(values) == 1:
        return {
            "mean": float(values[0]),
            "max": float(values[0]),
            "min": float(values[0]),
            "std": 0.0,
        }
    return {
        "mean": float(statistics.mean(values)),
        "max": float(max(values)),
        "min": float(min(values)),
        "std": float(statistics.stdev(values)),
    }


def _count_where_conditions(sql: str) -> int:
    try:
        parsed = sqlglot.parse_one(sql, error_level="ignore")
    except Exception:
        return 0
    where = parsed.args.get("where")
    if where is None:
        return 0
    predicate_types = (
        exp.EQ,
        exp.NEQ,
        exp.GT,
        exp.GTE,
        exp.LT,
        exp.LTE,
        exp.Like,
        exp.ILike,
        exp.In,
        exp.Between,
        exp.Is,
    )
    return sum(len(list(where.find_all(node_type))) for node_type in predicate_types)


def _count_joins(sql: str) -> int:
    try:
        parsed = sqlglot.parse_one(sql, error_level="ignore")
    except Exception:
        return 0
    return len(list(parsed.find_all(exp.Join)))


def _extract_query_metadata(
    sql: str,
    parsed,
    *,
    slice_name: str | None = None,
) -> dict[str, Any]:
    agg_items = [
        {
            "output_name": item.output_name,
            "function": (item.agg_func or "UNKNOWN").upper(),
            "source": item.source_name,
        }
        for item in parsed.select_items
        if item.is_agg
    ]
    agg_functions = sorted({item["function"] for item in agg_items})
    return {
        "slice_type": slice_name or classify_aggregation_slice(sql),
        "n_joins": _count_joins(sql),
        "n_group_by_columns": len(parsed.group_by),
        "group_by_columns": list(parsed.group_by),
        "n_aggregate_functions": len(agg_items),
        "aggregate_functions": agg_functions,
        "aggregates": agg_items,
        "n_where_conditions": _count_where_conditions(sql),
        "gold_result_row_count": None,
    }


def _with_row_keys(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    from evaluation.utils import format_primary_key

    out = df.copy()
    for key in keys:
        if key in out.columns:
            out[key] = out[key].fillna("").astype(str)
    out["__key"] = out.apply(lambda row: format_primary_key(row, keys), axis=1)
    return out


def _alignment_details(
    gold_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    gold_aligned: pd.DataFrame,
    pred_aligned: pd.DataFrame,
    keys: list[str],
    manifest,
) -> dict[str, Any]:
    from evaluation.utils import format_primary_key

    agg_cols = _aggregate_column_names(manifest)
    aligned_pairs: list[dict[str, Any]] = []

    for pair_index in range(len(gold_aligned)):
        gold_row = gold_aligned.iloc[pair_index]
        pred_row = pred_aligned.iloc[pair_index]
        key_tuple = format_primary_key(gold_row, keys)
        column_errors: dict[str, float | None] = {}
        for col in agg_cols:
            if col not in gold_row.index or col not in pred_row.index:
                continue
            column_errors[col] = cell_relative_error_pct(pred_row[col], gold_row[col])

        aligned_pairs.append(
            {
                "pair_index": pair_index,
                "alignment_key": list(key_tuple),
                "gold_row": _df_to_records(gold_row.to_frame().T)[0],
                "pred_row": _df_to_records(pred_row.to_frame().T)[0],
                "column_relative_error_pct": column_errors,
            }
        )

    paired_keys = {tuple(pair["alignment_key"]) for pair in aligned_pairs}
    gold_keyed = _with_row_keys(gold_df, keys)
    pred_keyed = _with_row_keys(pred_df, keys)

    unmatched_gold = gold_keyed[~gold_keyed["__key"].isin(paired_keys)]
    unmatched_pred = pred_keyed[~pred_keyed["__key"].isin(paired_keys)]
    if "__key" in unmatched_gold.columns:
        unmatched_gold = unmatched_gold.drop(columns="__key")
    if "__key" in unmatched_pred.columns:
        unmatched_pred = unmatched_pred.drop(columns="__key")

    return {
        "aligned_pairs": aligned_pairs,
        "unmatched_gold_rows": _df_to_records(unmatched_gold),
        "unmatched_pred_rows": _df_to_records(unmatched_pred),
        "n_aligned_pairs": len(aligned_pairs),
        "n_unmatched_gold_rows": len(unmatched_gold),
        "n_unmatched_pred_rows": len(unmatched_pred),
    }


def evaluate_query_detailed(
    instance,
    db: dict,
    query: dict,
    parser,
    attributes: dict,
    settings,
    *,
    slice_name: str,
) -> dict[str, Any]:
    from evaluation.metrics import MetricCalculator
    from evaluation.query_manifest import QueryManifest
    from evaluation.row_matcher import RowMatcher

    sql = query["sql_query"]
    qid = str(query.get("query_id", sql[:40]))
    parsed = parser.parse(sql)
    manifest = QueryManifest(sql, parsed, attributes)

    pred_df = execute_sql_on_db(db, sql)
    gold_df = _run_gold_sql(instance, sql)

    metadata = _extract_query_metadata(sql, parsed, slice_name=slice_name)
    metadata["gold_result_row_count"] = len(gold_df)

    join_keys = _alignment_keys_for_match(manifest, pred_df, gold_df)
    pred_norm, gold_norm = _normalize_join_keys_case_insensitive(pred_df, gold_df, join_keys)

    matcher = RowMatcher(settings=settings)
    match_result = matcher.match(
        gold_df=gold_norm,
        pred_df=pred_norm,
        primary_keys=join_keys,
        secondary_key=None,
        attr_descriptions=attributes,
        query_type=manifest.parsed.query_type,
    )

    metrics = MetricCalculator(manifest, settings).compute(match_result)
    mean_relative_error_pct = query_relative_error_pct(match_result, manifest)
    alignment = _alignment_details(
        gold_norm,
        pred_norm,
        match_result.gold_aligned,
        match_result.pred_aligned,
        join_keys,
        manifest,
    )

    return {
        "query_id": qid,
        "metadata": {
            "query_id": qid,
            "sql": sql,
            **metadata,
        },
        "results": {
            "gold_result": _df_to_records(gold_df),
            "predicted_result": _df_to_records(pred_df),
            **alignment,
            "mean_relative_error_pct": mean_relative_error_pct,
            "macro_f1": float(metrics["macro_f1"]),
            "macro_precision": float(metrics["macro_precision"]),
            "macro_recall": float(metrics["macro_recall"]),
            "column_metrics": metrics.get("columns", {}),
            "alignment_keys": join_keys,
            "match_warnings": list(match_result.warnings),
        },
    }


def summarize_slice_queries(
    per_query: list[dict],
    *,
    feasible_only: bool = True,
) -> dict[str, Any]:
    rows = per_query
    if feasible_only:
        rows = [q for q in per_query if not q.get("corpus_infeasible")]

    rel_errors: list[float] = []
    f1s: list[float] = []
    precisions: list[float] = []
    recalls: list[float] = []
    rel_by_query: list[dict[str, Any]] = []

    for row in rows:
        qid = row.get("query_id") or row.get("metadata", {}).get("query_id")
        results = row.get("results", row)
        rel = results.get("mean_relative_error_pct", results.get("relative_error_pct"))
        if rel is not None:
            rel_f = float(rel)
            rel_errors.append(rel_f)
            rel_by_query.append({"query_id": qid, "mean_relative_error_pct": round(rel_f, 4)})
        f1s.append(float(results.get("macro_f1", row.get("macro_f1", 0.0))))
        precisions.append(float(results.get("macro_precision", row.get("macro_precision", 0.0))))
        recalls.append(float(results.get("macro_recall", row.get("macro_recall", 0.0))))

    return {
        "n_queries": len(rows),
        "per_query_mean_relative_error_pct": rel_by_query,
        "relative_error_pct_array": [entry["mean_relative_error_pct"] for entry in rel_by_query],
        "relative_error": _summarize_values(rel_errors),
        "macro_f1": _summarize_values(f1s),
        "macro_precision": _summarize_values(precisions),
        "macro_recall": _summarize_values(recalls),
    }


def write_query_benchmark_report(payload: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return output_path


def format_query_for_report(row: dict[str, Any]) -> dict[str, Any]:
    """Structured per-query entry: metadata, results, agent — no duplicate flat fields."""
    qid = row.get("query_id") or row.get("metadata", {}).get("query_id")
    out: dict[str, Any] = {
        "query_id": qid,
        "corpus_infeasible": bool(row.get("corpus_infeasible")),
    }
    if row.get("missing_corpus_literals"):
        out["missing_corpus_literals"] = row["missing_corpus_literals"]
    if row.get("error"):
        out["error"] = row["error"]
    if "metadata" in row:
        out["metadata"] = row["metadata"]
    if "results" in row:
        out["results"] = row["results"]
    if row.get("agent"):
        out["agent"] = row["agent"]
    return out


def _extract_algorithm_selection(agent_pipeline: dict[str, Any] | None) -> dict[str, Any] | None:
    if not agent_pipeline:
        return None
    if agent_pipeline.get("algorithm_selection"):
        return agent_pipeline["algorithm_selection"]
    family = agent_pipeline.get("chosen_solver_family") or agent_pipeline.get(
        "chosen_algorithm_family"
    )
    if family:
        from pipeline.humanize_report import build_algorithm_selection_block

        return build_algorithm_selection_block(
            {
                "chosen_algorithm_family": family,
                "selection_rationale": agent_pipeline.get("selection_rationale", ""),
                "rounds": agent_pipeline.get("rounds_run"),
                "budget_summary": agent_pipeline.get("token_budget"),
                "solver_comparison": agent_pipeline.get("solver_comparison"),
                "baseline_comparison": agent_pipeline.get("baseline_comparison"),
                "selected_configs": [
                    c.get("config") or c.get("pipe_id")
                    for c in agent_pipeline.get("deployed_configs", [])
                    if isinstance(c, dict)
                ],
                "audit_log": agent_pipeline.get("action_audit"),
            }
        )
    return {
        "headline": "Chosen algorithm: budgeted per-query routing (no solver-family selection)",
        "chosen_algorithm": {
            "id": "budgeted_per_query_routing",
            "name": "Budgeted per-query routing by probed macro-F1",
            "stage3_engine": None,
            "selection_rationale": "Heuristic probe loop; route each query to best probed config",
            "rounds_to_decide": agent_pipeline.get("rounds_run"),
            "predicted_score": None,
        },
    }


def _build_report_summary(slice_results: list[dict[str, Any]]) -> dict[str, Any]:
    per_slice: list[dict[str, Any]] = []
    algorithm_selection_table: list[dict[str, Any]] = []
    all_f1: list[float] = []
    all_rel: list[float] = []
    n_queries = 0
    n_infeasible = 0

    for row in slice_results:
        if row.get("error"):
            continue
        summary = row.get("slice_summary") or {}
        n_q = int(row.get("n_queries", 0))
        n_ex = int(row.get("n_corpus_infeasible", 0))
        n_queries += n_q
        n_infeasible += n_ex
        agent_pipeline = row.get("agent_pipeline") or {}
        algo = _extract_algorithm_selection(agent_pipeline)
        chosen = (algo or {}).get("chosen_algorithm") or {}
        per_slice.append(
            {
                "slice": row["slice"],
                "n_queries": n_q,
                "n_corpus_infeasible": n_ex,
                "mean_macro_f1": summary.get("macro_f1", {}).get("mean"),
                "mean_relative_error_pct": summary.get("relative_error", {}).get("mean"),
                "mean_relative_accuracy": (
                    round(1.0 - float(summary.get("relative_error", {}).get("mean", 0)) / 100.0, 4)
                    if summary.get("relative_error", {}).get("mean") is not None
                    else None
                ),
                "chosen_algorithm_id": chosen.get("id"),
                "chosen_algorithm_name": chosen.get("name"),
                "selection_rationale": chosen.get("selection_rationale"),
                "agent_source": row.get("agent_source"),
            }
        )
        if algo:
            algorithm_selection_table.append(
                {
                    "slice": row["slice"],
                    "chosen_algorithm_id": chosen.get("id"),
                    "chosen_algorithm_name": chosen.get("name"),
                    "selection_rationale": chosen.get("selection_rationale"),
                    "predicted_score": chosen.get("predicted_score"),
                    "tokens_spent": (algo.get("token_budget") or {}).get("tokens_spent"),
                }
            )
        for entry in summary.get("per_query_mean_relative_error_pct") or []:
            all_rel.append(float(entry["mean_relative_error_pct"]))
        f1_block = summary.get("macro_f1") or {}
        if f1_block.get("mean") is not None:
            all_f1.append(float(f1_block["mean"]))

    return {
        "n_slices": len(per_slice),
        "n_queries_total": n_queries,
        "n_queries_feasible": n_queries - n_infeasible,
        "n_corpus_infeasible": n_infeasible,
        "mean_macro_f1_across_slices": _summarize_values(all_f1)["mean"],
        "mean_relative_error_pct_across_queries": _summarize_values(all_rel)["mean"],
        "algorithm_selection_table": algorithm_selection_table,
        "per_slice": per_slice,
    }


def build_query_benchmark_report(
    slice_results: list[dict[str, Any]],
    *,
    evaluation_mode: str = "agent_pipeline",
    technical_by_slice: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the final human-readable workload report."""
    slices: dict[str, Any] = {}
    for row in slice_results:
        if row.get("error"):
            continue
        agent_pipeline = row.get("agent_pipeline")
        if isinstance(agent_pipeline, dict):
            agent_pipeline = {
                k: v for k, v in agent_pipeline.items() if k != "_technical_details"
            }
        algorithm_selection = _extract_algorithm_selection(agent_pipeline)
        slice_entry: dict[str, Any] = {
            "slice": row["slice"],
            "evaluation_mode": row.get("evaluation_mode", evaluation_mode),
            "algorithm_selection": algorithm_selection,
            "n_queries": row.get("n_queries", 0),
            "n_corpus_infeasible": row.get("n_corpus_infeasible", 0),
            "extraction_source": row.get("extraction_source"),
            "agent_source": row.get("agent_source"),
            "slice_summary": row.get("slice_summary", {}),
            "agent_pipeline": agent_pipeline,
            "queries": [
                format_query_for_report(q) for q in row.get("per_query", [])
            ],
        }
        if row.get("workload_mode"):
            slice_entry["workload_mode"] = row["workload_mode"]
        if row.get("queries_by_aggregation_slice_type"):
            slice_entry["queries_by_aggregation_slice_type"] = row[
                "queries_by_aggregation_slice_type"
            ]
        slices[row["slice"]] = slice_entry

    descriptions = {
        "meta_controller": (
            "Workload report under meta-controller evaluation: the agent selects a "
            "solver family under budget; each query is evaluated on the database "
            "assigned by that solver. Reports include solver choice rationale and "
            "baseline comparison."
        ),
        "budgeted_routing": (
            "Workload report under budgeted routing: the agent probes pipeline "
            "configs and routes each query to the best-scoring probed config."
        ),
        "agent_pipeline": (
            "Workload report: each query is evaluated on the database built with "
            "the pipeline config the agent chose."
        ),
    }
    summary = _build_report_summary(slice_results)
    composite_stacks = {
        row["slice"]: (row.get("agent_pipeline") or {}).get("algorithm_selection", {}).get(
            "algorithm_stack"
        )
        for row in slice_results
        if not row.get("error")
    }
    composite_stacks = {k: v for k, v in composite_stacks.items() if v}
    workload_mode = next(
        (row.get("workload_mode") for row in slice_results if row.get("workload_mode")),
        None,
    )
    report: dict[str, Any] = {
        "report_version": 6,
        "description": descriptions.get(
            evaluation_mode,
            descriptions["agent_pipeline"],
        ),
        "evaluation_mode": evaluation_mode,
        "algorithm_selection_by_slice": {
            row["slice"]: {
                "chosen_algorithm_id": row.get("chosen_algorithm_id"),
                "chosen_algorithm_name": row.get("chosen_algorithm_name"),
                "selection_rationale": row.get("selection_rationale"),
            }
            for row in summary.get("algorithm_selection_table", [])
        },
        "composite_algorithm_stack_by_slice": composite_stacks,
        "summary": summary,
        "slices": slices,
        "_technical_details_path": (
            "query_benchmark_report_technical.json"
            if technical_by_slice
            else None
        ),
    }
    if workload_mode:
        report["workload_mode"] = workload_mode
    return report


def per_query_agent_fields(qid: str, agent_run: Any) -> dict[str, Any]:
    """Per-query agent routing in plain language."""
    return humanize_per_query_agent(qid, agent_run)


def _slim_audit_log(audit_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slim: list[dict[str, Any]] = []
    for entry in audit_log:
        state = entry.get("state", {})
        slim.append(
            {
                "round": entry.get("round"),
                "decision": entry.get("decision"),
                "budget": state.get("budget"),
                "current_best_routing": state.get("current_best_routing"),
                "weighted_config_recommendation": state.get(
                    "weighted_config_recommendation"
                ),
                "n_probed_configs": len(state.get("probed_configs", [])),
                "n_unprobed_configs": len(state.get("unprobed_configs", [])),
            }
        )
    return slim


def serialize_meta_run(agent_run: Any) -> dict[str, Any]:
    """Serialize meta-controller run for benchmark reporting."""
    from pipeline.humanize_report import humanize_meta_run

    raw = {
        "agent_mode": "meta_controller",
        "algorithm_stack": getattr(agent_run, "algorithm_stack", {}),
        "chosen_algorithm_family": agent_run.chosen_algorithm_family,
        "selection_rationale": agent_run.selection_rationale,
        "solver_comparison": agent_run.solver_comparison,
        "baseline_comparison": getattr(agent_run, "baseline_comparison", []),
        "stage_summaries": agent_run.stage_summaries,
        "audit_log": agent_run.audit_log,
        "rounds": agent_run.rounds,
        "selected_configs": agent_run.selected_configs,
        "final_routing": dict(agent_run.final_routing),
        "probed_configs": agent_run.probed_configs,
        "budget_summary": agent_run.budget_summary,
        "diagnostics": agent_run.diagnostics,
        "catalog_id_to_pipe": dict(agent_run.catalog_id_to_pipe),
    }
    human = humanize_meta_run(raw)
    return {**human, "_technical_details": raw}


def serialize_agent_run(
    agent_run: Any,
    *,
    query_ids: list[str],
    supply_profile_by_query: dict[str, Any] | None = None,
    use_heuristic_agent: bool = True,
) -> dict[str, Any]:
    if getattr(agent_run, "agent_mode", "") == "meta_controller":
        return serialize_meta_run(agent_run)
    from agent.phases.supply_profile import (
        build_supply_profile_by_query,
        build_weighted_config_recommendation,
    )

    if supply_profile_by_query is None:
        supply_profile_by_query = build_supply_profile_by_query(
            agent_run.supply_profile,
            agent_run.demand_profile,
            query_ids,
        )
    raw = {
        "agent_mode": "heuristic" if use_heuristic_agent else "llm",
        "rounds": agent_run.rounds,
        "budget_summary": agent_run.budget_summary,
        "final_routing": dict(agent_run.final_routing),
        "weighted_config_recommendation": build_weighted_config_recommendation(
            agent_run.demand_profile,
            supply_profile_by_query,
        ),
        "demand_profile": agent_run.demand_profile,
        "supply_profile": agent_run.supply_profile,
        "supply_profile_by_query": supply_profile_by_query,
        "probed_configs": [
            {
                "config_id": p["config_id"],
                "pipe_config_id": p.get("pipe_config_id"),
                "settings": p.get("settings"),
                "mean_f1": p.get("mean_f1"),
                "per_query_f1": p.get("per_query_f1", {}),
                "cost": p.get("cost"),
            }
            for p in agent_run.probed_configs
        ],
        "audit_log": _slim_audit_log(agent_run.audit_log),
        "catalog_id_to_pipe": dict(agent_run.catalog_id_to_pipe),
    }
    human = humanize_agent_run(raw, include_per_query_f1=False)
    return {
        **human,
        "_technical_details": raw,
    }


def attach_agent_output_to_queries(
    per_query: list[dict],
    agent_run: Any,
) -> None:
    for row in per_query:
        qid = str(row.get("query_id") or row.get("metadata", {}).get("query_id", ""))
        row["agent"] = per_query_agent_fields(qid, agent_run)
