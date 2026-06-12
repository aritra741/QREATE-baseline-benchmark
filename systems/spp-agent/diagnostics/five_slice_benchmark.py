#!/usr/bin/env python3
"""Evaluate all five Player aggregation slices with corpus-locked probe extraction."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from data.aggregation_slices import (
    AGGREGATION_SLICE_ORDER,
    UNIFIED_WORKLOAD_NAME,
    classify_aggregation_slice,
)
from data.instance_builder import build_instance
from data.corpus_feasibility import is_corpus_infeasible, missing_corpus_literals
from data.query_alignment import (
    prepare_aggregation_slice_instance,
    prepare_unified_aggregation_instance,
)
from data.agent_run_cache import (
    agent_run_cache_path,
    load_agent_run_cache,
    save_agent_run_cache,
)
from data.meta_run_cache import (
    load_meta_run_cache,
    meta_run_cache_path,
    save_meta_run_cache,
)
from data.slice_extraction_cache import (
    resolve_slice_extraction,
    slice_extraction_cache_path,
)
from pipeline.evaluation import _eval_context
from pipeline.query_benchmark_report import (
    attach_agent_output_to_queries,
    build_query_benchmark_report,
    evaluate_query_detailed,
    serialize_agent_run,
    summarize_slice_queries,
    write_query_benchmark_report,
)
from pipeline.relative_error import (
    build_slice_relative_error_report,
    print_slice_relative_error_report,
    write_relative_error_report,
)
from utils.config import load_config

CONFIG_ID = "er=embedding_0.7|norm=dictionary|unit=none|miss=constant|coerce=llm"
PROFILED_TOKEN_BUDGET = 80_000


from data.workload_selection import stable_slice_seed as _stable_slice_seed


def _evaluate_query(instance, db, query, parser, attributes, settings, *, slice_name: str) -> dict:
    detailed = evaluate_query_detailed(
        instance,
        db,
        query,
        parser,
        attributes,
        settings,
        slice_name=slice_name,
    )
    results = detailed["results"]
    return {
        **detailed,
        "macro_f1": float(results["macro_f1"]),
        "macro_precision": float(results["macro_precision"]),
        "macro_recall": float(results["macro_recall"]),
        "relative_error_pct": results["mean_relative_error_pct"],
        "pred_rows": len(results["predicted_result"]),
        "gold_rows": len(results["gold_result"]),
        "aligned_rows": int(results["n_aligned_pairs"]),
        "sql": detailed["metadata"]["sql"],
    }


def _write_combined_relative_error_report(
    slice_reports: list[dict],
    report_path: Path,
    *,
    histogram_suffix: str = "",
) -> None:
    import json

    from pipeline.relative_error import (
        histogram_bucket_counts,
        save_relative_error_histogram,
        summarize_relative_errors,
    )

    all_values: list[float] = []
    all_entries: list[dict] = []
    for report in slice_reports:
        for entry in report.get("per_query", []):
            rel = entry.get("relative_error_pct")
            if rel is None:
                continue
            all_values.append(float(rel))
            all_entries.append({**entry, "slice": report["slice"]})

    if not all_values:
        return

    stats = summarize_relative_errors(all_values)
    histogram = histogram_bucket_counts(all_values)
    combined_path = report_path.parent / f"relative_error_histogram_all{histogram_suffix}.png"
    save_relative_error_histogram(
        f"all queries ({len(all_values)})",
        all_values,
        combined_path,
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["all_queries"] = {
        "n_queries": len(all_values),
        "relative_error_pct_per_query": [round(v, 4) for v in all_values],
        "per_query": all_entries,
        "statistics": {k: round(v, 4) for k, v in stats.items()},
        "histogram": histogram,
        "histogram_path": str(combined_path.resolve()),
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    formatted = ", ".join(f"{v:.1f}%" for v in all_values)
    print(f"\n### All queries — relative error (n={len(all_values)})")
    print(f"Per-query: [{formatted}]")
    print(
        f"Statistics: mean={stats['mean']:.2f}% max={stats['max']:.2f}% "
        f"min={stats['min']:.2f}% std={stats['std']:.2f}%"
    )
    hist_line = ", ".join(f"{bucket}: {count}" for bucket, count in histogram.items())
    print(f"Histogram: {hist_line}")


def _failure_mode(row: dict) -> str:
    if row.get("error"):
        err = row["error"].lower()
        if "missing key columns" in err:
            return "gold/pred schema mismatch (missing join-key column)"
        return f"evaluation error: {row['error'][:80]}"
    sql = row["sql"].lower()
    f1 = row["macro_f1"]
    if row["pred_rows"] == 0 and row["gold_rows"] > 0:
        if "join" in sql:
            return "JOIN/filter returns empty result"
        if re.search(r"\bwhere\b", sql):
            return "WHERE filter returns empty result"
        return "aggregation returns empty result"
    if row["pred_rows"] > 0 and row["gold_rows"] == 0:
        return "spurious non-empty result (gold empty)"
    if row["pred_rows"] != row["gold_rows"]:
        if "join" in sql:
            return "JOIN produces wrong row count"
        return "result row count mismatch vs gold"
    if "nationality" in sql and f1 < 0.85:
        return "nationality group value mismatch"
    if "position" in sql and f1 < 0.85:
        return "position group value mismatch"
    if re.search(r"\b(birth_date|draft_year|year|date)\b", sql):
        return "temporal/date aggregation mismatch"
    if row["aligned_rows"] < min(row["pred_rows"], row["gold_rows"]):
        return "join-key alignment failure (unmatched groups)"
    return "aggregate value mismatch on matched keys"


def _run_agent_for_instance(
    instance,
    *,
    slice_name: str,
    slice_seed: int,
    shared_extraction,
    results_dir: Path,
    fresh_agent: bool = False,
    use_heuristic_agent: bool = True,
    agent_mode: str = "meta_controller",
) -> tuple[Any, str]:
    if agent_mode == "budgeted_routing":
        from agent.budgeted_loop import run_budgeted_agent_loop

        cache_path = agent_run_cache_path(results_dir, slice_name)
        if not fresh_agent:
            cached = load_agent_run_cache(
                cache_path,
                slice_name=slice_name,
                seed=slice_seed,
                token_budget_total=PROFILED_TOKEN_BUDGET,
                extraction=shared_extraction,
                schema=instance.schema,
            )
            if cached is not None:
                return cached, "agent_run_cache"

        run = run_budgeted_agent_loop(
            instance,
            token_budget_total=PROFILED_TOKEN_BUDGET,
            max_rounds=8,
            use_heuristic_agent=use_heuristic_agent,
            use_heuristic_demand=True,
            shared_extraction=shared_extraction,
        )
        save_agent_run_cache(
            cache_path,
            slice_name=slice_name,
            seed=slice_seed,
            token_budget_total=PROFILED_TOKEN_BUDGET,
            extraction=shared_extraction,
            run=run,
        )
        return run, "fresh_agent_run"

    from pipeline.meta_pipeline import run_meta_spp_pipeline

    cache_path = meta_run_cache_path(results_dir, slice_name)
    if not fresh_agent:
        cached = load_meta_run_cache(
            cache_path,
            slice_name=slice_name,
            seed=slice_seed,
            token_budget_total=PROFILED_TOKEN_BUDGET,
            extraction=shared_extraction,
            schema=instance.schema,
        )
        if cached is not None:
            return cached, "meta_run_cache"

    run = run_meta_spp_pipeline(
        instance,
        token_budget=PROFILED_TOKEN_BUDGET,
        shared_extraction=shared_extraction,
        seed=slice_seed,
        use_heuristic=use_heuristic_agent,
    )
    save_meta_run_cache(
        cache_path,
        slice_name=slice_name,
        seed=slice_seed,
        token_budget_total=PROFILED_TOKEN_BUDGET,
        extraction=shared_extraction,
        run=run,
    )
    return run, "fresh_meta_run"


def _prepare_slice_instance(
    slice_name: str,
    *,
    cfg: dict,
    included_slices: list[str] | None = None,
    workload_split: str | None = None,
) -> tuple[Any, list, int]:
    phase0 = cfg.get("phase0", {})
    seed = int(cfg["experiment"]["seed"])
    num_docs = int(phase0.get("num_docs", 20))
    table_filter = set(phase0.get("table_filter", ["player"]))
    queries_per_slice = int(phase0.get("queries_per_slice", 20))

    base = build_instance("Player", include_ground_truth=False)
    slice_seed = _stable_slice_seed(seed, slice_name)
    if slice_name == UNIFIED_WORKLOAD_NAME:
        slice_queries_pool, _ = prepare_unified_aggregation_instance(
            base,
            num_docs=num_docs,
            num_eval_queries=9999,
            seed=slice_seed,
            query_table_filter=table_filter,
            slice_names=included_slices,
            queries_per_slice=queries_per_slice,
        )
    else:
        slice_queries_pool, _ = prepare_aggregation_slice_instance(
            base,
            slice_name=slice_name,
            num_docs=num_docs,
            num_eval_queries=9999,
            seed=slice_seed,
            query_table_filter=table_filter,
            queries_per_slice=queries_per_slice,
            workload_split=workload_split,
        )
    queries = list(slice_queries_pool.queries)
    return slice_queries_pool, queries, slice_seed


def _evaluate_slice_agent(
    slice_name: str,
    *,
    cache_path: Path,
    cfg: dict,
    fresh_extraction: bool = False,
    fresh_agent: bool = False,
    agent_mode: str = "meta_controller",
    use_heuristic_agent: bool = True,
    included_slices: list[str] | None = None,
    workload_split: str | None = None,
) -> dict:
    """Run the agent pipeline and evaluate each query on its routed database."""
    phase0 = cfg.get("phase0", {})
    llm_cfg = cfg["llm"]
    results_dir = Path(cfg["paths"]["results_dir"])

    slice_queries_pool, queries, slice_seed = _prepare_slice_instance(
        slice_name,
        cfg=cfg,
        included_slices=included_slices,
        workload_split=workload_split,
    )
    instance, extraction, _, extraction_source = resolve_slice_extraction(
        slice_name=slice_name,
        slice_pool=slice_queries_pool,
        queries=queries,
        seed=slice_seed,
        config_id=CONFIG_ID,
        cache_path=slice_extraction_cache_path(results_dir, slice_name),
        legacy_agg_only_cache=cache_path,
        fresh_extraction=fresh_extraction,
        extraction_model=llm_cfg["extraction_model"],
    )
    print(f"  Extraction source: {extraction_source}", flush=True)
    if workload_split:
        print(f"  Workload split: {workload_split}", flush=True)
    if slice_name == UNIFIED_WORKLOAD_NAME:
        print(f"  Queries in unified workload: {len(queries)}", flush=True)

    agent_run, agent_source = _run_agent_for_instance(
        instance,
        slice_name=slice_name,
        slice_seed=slice_seed,
        shared_extraction=extraction,
        results_dir=results_dir,
        fresh_agent=fresh_extraction or fresh_agent,
        agent_mode=agent_mode,
        use_heuristic_agent=use_heuristic_agent,
    )
    print(f"  Agent mode: {agent_mode}", flush=True)
    print(f"  Agent pipeline source: {agent_source}", flush=True)
    databases = agent_run.databases
    routing = agent_run.final_routing
    if not databases:
        raise RuntimeError("Agent pipeline produced no probed databases")

    settings, parser, attributes, _ = _eval_context(instance)
    corpus = list(instance.corpus)
    per_query: list[dict] = []
    for q in queries:
        qid = str(q.get("query_id", q.get("sql_query", "")[:40]))
        if routing.get(qid):
            cid = routing[qid]
        elif agent_mode == "meta_controller":
            cid = max(
                agent_run.probed_configs,
                key=lambda p: float(p.get("structural_score") or 0.0),
            )["config_id"]
        else:
            cid = max(
                agent_run.probed_configs,
                key=lambda p: float(p.get("mean_f1") or 0.0),
            )["config_id"]
        db = databases.get(cid) or next(iter(databases.values()))
        try:
            row = _evaluate_query(
                instance, db, q, parser, attributes, settings, slice_name=slice_name
            )
        except Exception as exc:
            row = {
                "query_id": qid,
                "macro_f1": 0.0,
                "macro_precision": 0.0,
                "macro_recall": 0.0,
                "relative_error_pct": 100.0,
                "pred_rows": -1,
                "gold_rows": -1,
                "aligned_rows": 0,
                "sql": q.get("sql_query", ""),
                "error": str(exc),
            }
        sql = row.get("sql", q.get("sql_query", ""))
        pred_rows = int(row.get("pred_rows", -1))
        gold_rows = int(row.get("gold_rows", -1))
        infeasible = is_corpus_infeasible(
            sql=sql,
            corpus=corpus,
            pred_rows=max(pred_rows, 0),
            gold_rows=max(gold_rows, 0),
        )
        row["corpus_infeasible"] = infeasible
        if infeasible:
            row["missing_corpus_literals"] = missing_corpus_literals(sql, corpus)
        if slice_name == UNIFIED_WORKLOAD_NAME:
            row["aggregation_slice_type"] = classify_aggregation_slice(sql)
        per_query.append(row)

    query_ids = [str(q.get("query_id", q.get("sql_query", "")[:40])) for q in queries]
    attach_agent_output_to_queries(per_query, agent_run)
    agent_output = serialize_agent_run(agent_run, query_ids=query_ids)

    feasible_f1s = [r["macro_f1"] for r in per_query if not r.get("corpus_infeasible")]
    all_f1s = [r["macro_f1"] for r in per_query]
    n_excluded = sum(1 for r in per_query if r.get("corpus_infeasible"))
    slice_summary = summarize_slice_queries(per_query)
    eval_mode = agent_mode if agent_mode != "agent_pipeline" else "agent_pipeline"
    result: dict[str, Any] = {
        "slice": slice_name,
        "evaluation_mode": eval_mode,
        "agent_mode": agent_mode,
        "n_queries": len(queries),
        "n_corpus_infeasible": n_excluded,
        "mean_f1": sum(all_f1s) / len(all_f1s) if all_f1s else 0.0,
        "mean_f1_feasible": sum(feasible_f1s) / len(feasible_f1s) if feasible_f1s else 0.0,
        "min_f1": min(feasible_f1s) if feasible_f1s else 0.0,
        "below_05": sum(1 for f in feasible_f1s if f < 0.5),
        "per_query": per_query,
        "slice_summary": slice_summary,
        "extraction_source": extraction_source,
        "agent_source": agent_source,
        "agent_pipeline": agent_output,
    }
    if slice_name == UNIFIED_WORKLOAD_NAME:
        subtype_counts: dict[str, int] = {}
        for row in per_query:
            st = row.get("aggregation_slice_type") or "unknown"
            subtype_counts[st] = subtype_counts.get(st, 0) + 1
        result["workload_mode"] = "unified"
        result["queries_by_aggregation_slice_type"] = subtype_counts
    return result


def _evaluate_slice_fixed_baseline(
    slice_name: str,
    *,
    cache_path: Path,
    cfg: dict,
    fresh_extraction: bool = False,
    included_slices: list[str] | None = None,
    workload_split: str | None = None,
) -> dict:
    """Optional comparison mode: one fixed pipeline config for every query."""
    llm_cfg = cfg["llm"]
    results_dir = Path(cfg["paths"]["results_dir"])

    slice_queries_pool, queries, slice_seed = _prepare_slice_instance(
        slice_name,
        cfg=cfg,
        included_slices=included_slices,
        workload_split=workload_split,
    )
    instance, _, db, extraction_source = resolve_slice_extraction(
        slice_name=slice_name,
        slice_pool=slice_queries_pool,
        queries=queries,
        seed=slice_seed,
        config_id=CONFIG_ID,
        cache_path=slice_extraction_cache_path(results_dir, slice_name),
        legacy_agg_only_cache=cache_path,
        fresh_extraction=fresh_extraction,
        extraction_model=llm_cfg["extraction_model"],
    )
    print(f"  Extraction source: {extraction_source}", flush=True)
    if workload_split:
        print(f"  Workload split: {workload_split}", flush=True)
    if slice_name == UNIFIED_WORKLOAD_NAME:
        print(f"  Queries in unified workload: {len(queries)}", flush=True)
    print(f"  Fixed baseline config: {CONFIG_ID}", flush=True)

    settings, parser, attributes, _ = _eval_context(instance)
    corpus = list(instance.corpus)
    per_query: list[dict] = []
    for q in queries:
        try:
            row = _evaluate_query(
                instance, db, q, parser, attributes, settings, slice_name=slice_name
            )
        except Exception as exc:
            row = {
                "query_id": q.get("query_id", q.get("sql_query", "")[:40]),
                "macro_f1": 0.0,
                "macro_precision": 0.0,
                "macro_recall": 0.0,
                "relative_error_pct": 100.0,
                "pred_rows": -1,
                "gold_rows": -1,
                "aligned_rows": 0,
                "sql": q.get("sql_query", ""),
                "error": str(exc),
            }
        sql = row.get("sql", q.get("sql_query", ""))
        pred_rows = int(row.get("pred_rows", -1))
        gold_rows = int(row.get("gold_rows", -1))
        infeasible = is_corpus_infeasible(
            sql=sql,
            corpus=corpus,
            pred_rows=max(pred_rows, 0),
            gold_rows=max(gold_rows, 0),
        )
        row["corpus_infeasible"] = infeasible
        if infeasible:
            row["missing_corpus_literals"] = missing_corpus_literals(sql, corpus)
        per_query.append(row)

    feasible_f1s = [r["macro_f1"] for r in per_query if not r.get("corpus_infeasible")]
    all_f1s = [r["macro_f1"] for r in per_query]
    n_excluded = sum(1 for r in per_query if r.get("corpus_infeasible"))
    slice_summary = summarize_slice_queries(per_query)
    return {
        "slice": slice_name,
        "evaluation_mode": "fixed_baseline",
        "fixed_baseline_config": CONFIG_ID,
        "n_queries": len(queries),
        "n_corpus_infeasible": n_excluded,
        "mean_f1": sum(all_f1s) / len(all_f1s) if all_f1s else 0.0,
        "mean_f1_feasible": sum(feasible_f1s) / len(feasible_f1s) if feasible_f1s else 0.0,
        "min_f1": min(feasible_f1s) if feasible_f1s else 0.0,
        "below_05": sum(1 for f in feasible_f1s if f < 0.5),
        "per_query": per_query,
        "slice_summary": slice_summary,
        "extraction_source": extraction_source,
    }


def _evaluate_slice(
    slice_name: str,
    *,
    cache_path: Path,
    cfg: dict,
    fixed_baseline: bool = False,
    fresh_extraction: bool = False,
    fresh_agent: bool = False,
    agent_mode: str = "meta_controller",
    use_heuristic_agent: bool = True,
    included_slices: list[str] | None = None,
    workload_split: str | None = None,
) -> dict:
    if fixed_baseline:
        return _evaluate_slice_fixed_baseline(
            slice_name,
            cache_path=cache_path,
            cfg=cfg,
            fresh_extraction=fresh_extraction,
            included_slices=included_slices,
            workload_split=workload_split,
        )
    return _evaluate_slice_agent(
        slice_name,
        cache_path=cache_path,
        cfg=cfg,
        fresh_extraction=fresh_extraction,
        fresh_agent=fresh_agent,
        agent_mode=agent_mode,
        use_heuristic_agent=use_heuristic_agent,
        included_slices=included_slices,
        workload_split=workload_split,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--slices", nargs="*", default=None)
    parser.add_argument(
        "--fixed-baseline",
        action="store_true",
        help=(
            "Compare against one fixed pipeline config for all queries "
            "(not the real agent output)"
        ),
    )
    parser.add_argument(
        "--fresh-extraction",
        action="store_true",
        help="Re-run LLM extraction and invalidate dependent agent-run cache",
    )
    parser.add_argument(
        "--fresh-agent",
        action="store_true",
        help="Re-run the agent even if a cached run exists",
    )
    parser.add_argument(
        "--agent-mode",
        choices=["meta_controller", "budgeted_routing"],
        default="meta_controller",
        help=(
            "meta_controller: solver-family meta-selection (paper default); "
            "budgeted_routing: per-query heuristic router"
        ),
    )
    parser.add_argument(
        "--llm-meta-agent",
        action="store_true",
        help="Use LLM meta-agent when implemented; default is heuristic meta-controller",
    )
    parser.add_argument(
        "--split",
        choices=["train", "dev", "test"],
        default=None,
        help="Evaluate only queries from the held-out workload split manifest",
    )
    parser.add_argument(
        "--unified-workload",
        action="store_true",
        help=(
            "Evaluate all aggregation queries in one workload (single extraction, "
            "single agent run, shared routing)"
        ),
    )
    args = parser.parse_args()

    cfg = load_config()
    cache_path = Path(cfg["paths"]["results_dir"]) / cfg.get("phase1", {}).get(
        "probe_context_cache", "phase1_agg_only_probe_context.json"
    )

    if args.unified_workload:
        included = args.slices or list(AGGREGATION_SLICE_ORDER)
        slice_names = [UNIFIED_WORKLOAD_NAME]
        print(
            f"Unified workload mode: {len(included)} slice types merged into one run",
            flush=True,
        )
    else:
        slice_names = args.slices or list(AGGREGATION_SLICE_ORDER)
        included = None
    results_dir = Path(cfg["paths"]["results_dir"])
    results = []
    relative_error_reports: list[dict] = []
    rel_suffix = "_fixed_baseline" if args.fixed_baseline else ""
    for slice_name in slice_names:
        print(f"Evaluating slice {slice_name}...", flush=True)
        try:
            slice_result = _evaluate_slice(
                slice_name,
                cache_path=cache_path,
                cfg=cfg,
                fixed_baseline=args.fixed_baseline,
                fresh_extraction=args.fresh_extraction,
                fresh_agent=args.fresh_agent,
                agent_mode=args.agent_mode,
                use_heuristic_agent=not args.llm_meta_agent,
                included_slices=included,
                workload_split=args.split,
            )
            results.append(slice_result)
            if slice_result.get("per_query"):
                rel_report = build_slice_relative_error_report(
                    slice_name,
                    slice_result["per_query"],
                    results_dir=results_dir,
                    histogram_suffix=rel_suffix,
                )
                relative_error_reports.append(rel_report)
                print_slice_relative_error_report(rel_report)
        except Exception as exc:
            print(f"  FAILED: {exc}", flush=True)
            results.append(
                {
                    "slice": slice_name,
                    "n_queries": 0,
                    "n_corpus_infeasible": 0,
                    "mean_f1": 0.0,
                    "mean_f1_feasible": 0.0,
                    "min_f1": 0.0,
                    "below_05": 0,
                    "per_query": [],
                    "error": str(exc),
                }
            )

    if relative_error_reports:
        report_path = results_dir / f"relative_error_report{rel_suffix}.json"
        write_relative_error_report(relative_error_reports, report_path)
        _write_combined_relative_error_report(
            relative_error_reports,
            report_path,
            histogram_suffix=rel_suffix,
        )
        print(f"\nRelative error report saved to {report_path}")
        print(
            f"Combined histogram (all queries): "
            f"{results_dir / f'relative_error_histogram_all{rel_suffix}.png'}"
        )

    if results:
        if args.fixed_baseline:
            eval_mode = "fixed_baseline"
        else:
            eval_mode = args.agent_mode
        technical_by_slice = {
            r["slice"]: r["agent_pipeline"]["_technical_details"]
            for r in results
            if not r.get("error")
            and isinstance(r.get("agent_pipeline"), dict)
            and r["agent_pipeline"].get("_technical_details")
        }
        benchmark_report = build_query_benchmark_report(
            results,
            evaluation_mode=eval_mode,
            technical_by_slice=technical_by_slice or None,
        )
        report_name = (
            "query_benchmark_report_fixed_baseline.json"
            if args.fixed_baseline
            else "query_benchmark_report.json"
        )
        full_report_path = write_query_benchmark_report(
            benchmark_report,
            results_dir / report_name,
        )
        if technical_by_slice:
            tech_path = write_query_benchmark_report(
                {"slices": technical_by_slice},
                results_dir / "query_benchmark_report_technical.json",
            )
            print(f"Technical agent details saved to {tech_path}")
        print(f"Full per-query benchmark report saved to {full_report_path}")

    print()
    print("| Slice | Feasible queries | Mean macro-F1 | Min macro-F1 | # below 0.5 |")
    print("|-------|------------------|---------------|--------------|-------------|")
    for r in results:
        excluded = r.get("n_corpus_infeasible", 0)
        feasible = r["n_queries"] - excluded
        mean_f = r.get("mean_f1_feasible", r.get("mean_f1", 0.0))
        print(
            f"| {r['slice']} | {feasible} | {mean_f:.4f} | "
            f"{r['min_f1']:.4f} | {r['below_05']} |"
        )

    for r in results:
        if r.get("error"):
            print(f"\n### {r['slice']} — ERROR: {r['error']}")
            continue
        if r["mean_f1"] >= 0.85:
            continue
        worst = sorted(r["per_query"], key=lambda x: x["macro_f1"])[:3]
        print(f"\n### {r['slice']} — worst queries (mean F1 {r['mean_f1']:.4f})")
        for row in worst:
            mode = _failure_mode(row)
            print(f"- {row['query_id']}: F1={row['macro_f1']:.4f} — {mode}")


if __name__ == "__main__":
    main()
