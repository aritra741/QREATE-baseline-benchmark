#!/usr/bin/env python3
"""
Config-grid experiment on the held-out test split.

For every pipeline config in population_config_space:
  1. Materialize a database from a single shared LLM extraction on the test corpus.
  2. Evaluate all test queries (5 per aggregation slice, 25 total).

Use only the test split — never train or dev.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from data.aggregation_slices import AGGREGATION_SLICE_ORDER, classify_aggregation_slice
from data.dataset_registry import (
    config_grid_output_dir,
    normalize_dataset_name,
    results_dir_for_dataset,
    workload_slices_for_dataset,
)
from data.instance_builder import build_instance
from data.query_alignment import (
    corpus_alignment_metadata,
    filter_docs_for_tables,
    sample_corpus_stratified,
    tables_referenced_by_queries,
)
from data.materialized_db_store import (
    database_path,
    load_materialized_database,
    save_materialized_database,
    write_database_index,
)
from data.workload_splits import HOLDOUT_POLICY, load_split_queries
from optimizer.config_space import PopulationConfig, generate_config_space
from pipeline.group_by_category_error import (
    build_and_write_config_winner_analysis,
    build_config_leaderboard,
    build_top_category_error_audit,
    build_workload_audit_summary,
    build_workload_category_error_report,
    format_compact_category_error_audit,
    format_config_leaderboard,
    format_config_winner_dimension_histograms,
    format_top_category_error_calculations,
    format_viable_config_search_space,
    refresh_per_config_scores,
    refresh_per_query_row_scores,
    write_category_error_audit_summary,
    write_category_error_report,
    write_top_category_error_audit,
)
from pipeline.evaluation import _eval_context
from pipeline.extraction import ExtractionResult, extract_documents
from pipeline.extraction_context import extract_demand_profile_sql_only
from pipeline.population import PopulationDiagnostics, apply_population
from pipeline.query_benchmark_report import evaluate_query_detailed
from utils.config import load_config
from utils.logging import setup_logger

logger = setup_logger("spp.test_config_grid")

EXPERIMENT_NAME = "config_grid_test"
DEFAULT_OUTPUT_DIR = "config_grid_test"


def _extraction_cache_path(output_dir: Path) -> Path:
    return output_dir / "extraction_cache.json"


def _checkpoint_path(output_dir: Path) -> Path:
    return output_dir / "checkpoint.json"


def _results_path(output_dir: Path) -> Path:
    return output_dir / "grid_results.json"


def _manifest_path(output_dir: Path) -> Path:
    return output_dir / "manifest.json"


def _extraction_fingerprint(extraction: ExtractionResult) -> str:
    payload = json.dumps(extraction.tuples_by_table, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _corpus_fingerprint(corpus: list[dict]) -> str:
    doc_ids = sorted(str(doc.get("doc_id", "")) for doc in corpus)
    return hashlib.sha256("|".join(doc_ids).encode("utf-8")).hexdigest()[:16]


def _demand_fingerprint(demand_profile: dict[str, Any] | None) -> str:
    if not demand_profile:
        return "none"
    payload = json.dumps(demand_profile, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _run_fingerprint(
    *,
    extraction_model: str,
    llm_profile: str | None,
    seed: int,
    num_docs: int,
    n_test_queries: int,
    corpus_fingerprint: str,
    extraction_mode: str,
    demand_fingerprint: str,
) -> dict[str, Any]:
    """Fields that must match for checkpoint / extraction cache reuse."""
    return {
        "extraction_model": extraction_model,
        "llm_profile": llm_profile,
        "seed": seed,
        "num_docs": num_docs,
        "n_test_queries": n_test_queries,
        "corpus_fingerprint": corpus_fingerprint,
        "extraction_mode": extraction_mode,
        "demand_fingerprint": demand_fingerprint,
        "split": "test",
    }


def _fingerprint_matches(cached: dict[str, Any] | None, expected: dict[str, Any]) -> bool:
    if not cached:
        return False
    return all(cached.get(key) == expected.get(key) for key in expected)


def _extraction_to_payload(extraction: ExtractionResult) -> dict[str, Any]:
    return {
        "tuples_by_table": extraction.tuples_by_table,
        "token_cost": extraction.token_cost,
        "per_doc_signals": extraction.per_doc_signals,
        "demand_profile": extraction.demand_profile,
    }


def _extraction_from_payload(payload: dict[str, Any]) -> ExtractionResult:
    return ExtractionResult(
        tuples_by_table=dict(payload.get("tuples_by_table", {})),
        token_cost=float(payload.get("token_cost", 0.0)),
        per_doc_signals=list(payload.get("per_doc_signals", [])),
        demand_profile=payload.get("demand_profile"),
    )


def _save_extraction_cache(path: Path, extraction: ExtractionResult, *, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "meta": meta, "extraction": _extraction_to_payload(extraction)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_extraction_cache(path: Path) -> tuple[ExtractionResult, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _extraction_from_payload(payload["extraction"]), dict(payload.get("meta", {}))


def _diagnostics_to_dict(diag: PopulationDiagnostics) -> dict[str, Any]:
    return asdict(diag)


def _db_row_counts(db: dict) -> dict[str, int]:
    return {table: len(df) for table, df in db.items()}


def load_and_validate_test_queries(*, dataset: str = "Player") -> tuple[list[dict], dict[str, int]]:
    """Load held-out test queries; require all slices that have test assignments."""
    import json

    dataset_key = normalize_dataset_name(dataset)
    queries = load_split_queries("test", dataset=dataset_key)
    by_slice: dict[str, list[dict]] = defaultdict(list)
    for query in queries:
        slice_name = classify_aggregation_slice(query.get("sql_query", ""))
        if slice_name:
            by_slice[slice_name].append(query)

    manifest_path = results_dir_for_dataset(dataset_key) / "workload_split_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        required_slices = [
            slice_name
            for slice_name, counts in manifest.get("counts_per_slice", {}).items()
            if counts.get("test", 0) > 0
        ]
    else:
        required_slices = workload_slices_for_dataset(dataset_key)

    counts = {slice_name: len(by_slice.get(slice_name, [])) for slice_name in required_slices}
    missing = [s for s in required_slices if counts[s] == 0]
    if missing:
        raise RuntimeError(
            f"Test split missing slices: {missing}. "
            f"Regenerate with: python -m data.workload_splits --dataset {dataset_key}"
        )
    if not queries:
        raise RuntimeError(
            f"No test queries for {dataset_key}. "
            f"Regenerate with: python -m data.workload_splits --dataset {dataset_key}"
        )
    return queries, dict(counts)


def build_test_instance(
    test_queries: list[dict],
    *,
    dataset: str = "Player",
    num_docs: int | None,
    seed: int,
):
    """Corpus aligned to all test queries (full aligned set by default)."""
    dataset_key = normalize_dataset_name(dataset)
    base = build_instance(dataset_key, include_ground_truth=False)
    schema = base.schema
    required_tables = tables_referenced_by_queries(test_queries, schema)
    aligned_corpus = filter_docs_for_tables(base.corpus, required_tables, dataset=dataset_key)
    if num_docs is None or num_docs <= 0 or num_docs >= len(aligned_corpus):
        corpus = aligned_corpus
        corpus_mode = "full_aligned"
    else:
        corpus = sample_corpus_stratified(
            base.corpus, required_tables, num_docs, seed, dataset=dataset_key
        )
        corpus_mode = f"sampled_{num_docs}"
    return replace(
        base,
        corpus=corpus,
        queries=test_queries,
        metadata={
            **(base.metadata or {}),
            **corpus_alignment_metadata(corpus),
            "workload_split": "test",
            "dataset": dataset_key,
            "experiment": EXPERIMENT_NAME,
            "corpus_mode": corpus_mode,
            "num_docs": len(corpus),
            "aligned_corpus_size": len(aligned_corpus),
            "num_eval_queries": len(test_queries),
            "required_tables": sorted(required_tables),
            "held_out": True,
        },
    )


def _warn_infeasible_test_queries(test_queries: list[dict], corpus: list[dict]) -> None:
    from data.corpus_feasibility import missing_corpus_literals

    infeasible: list[tuple[str, list[str]]] = []
    for query in test_queries:
        missing = missing_corpus_literals(query.get("sql_query", ""), corpus)
        if missing:
            infeasible.append((str(query.get("query_id", "")), missing))
    if not infeasible:
        return
    logger.warning(
        "%d/%d test queries have WHERE literals missing from corpus; "
        "use full aligned corpus or increase --num-docs. Examples: %s",
        len(infeasible),
        len(test_queries),
        infeasible[:3],
    )


def resolve_extraction(
    instance,
    *,
    output_dir: Path,
    extraction_model: str,
    llm_profile: str | None,
    seed: int,
    n_test_queries: int,
    test_queries: list[dict],
    fresh: bool,
) -> tuple[ExtractionResult, str]:
    cache_path = _extraction_cache_path(output_dir)
    cfg = load_config()
    extraction_mode = (
        "workload_aware"
        if cfg.get("extraction", {}).get("workload_aware", True)
        else "legacy_schema"
    )
    demand_fp = _demand_fingerprint(
        extract_demand_profile_sql_only(test_queries)
        if extraction_mode == "workload_aware"
        else None
    )
    expected_meta = _run_fingerprint(
        extraction_model=extraction_model,
        llm_profile=llm_profile,
        seed=seed,
        num_docs=len(instance.corpus),
        n_test_queries=n_test_queries,
        corpus_fingerprint=_corpus_fingerprint(instance.corpus),
        extraction_mode=extraction_mode,
        demand_fingerprint=demand_fp,
    )
    if cache_path.is_file() and not fresh:
        extraction, cached_meta = _load_extraction_cache(cache_path)
        if _fingerprint_matches(cached_meta, expected_meta):
            return extraction, f"cache ({cached_meta.get('extraction_model', '?')})"
        logger.warning(
            "Extraction cache stale (cached profile=%s model=%s; "
            "current profile=%s model=%s); rerunning extraction",
            cached_meta.get("llm_profile"),
            cached_meta.get("extraction_model"),
            expected_meta.get("llm_profile"),
            expected_meta.get("extraction_model"),
        )

    logger.info("Running LLM extraction on %d docs", len(instance.corpus))
    extraction = extract_documents(
        instance.corpus,
        instance.schema,
        extraction_model,
        queries=instance.queries,
    )
    meta = {
        **expected_meta,
        "extraction_fingerprint": _extraction_fingerprint(extraction),
        "demand_profile": extraction.demand_profile,
    }
    _save_extraction_cache(cache_path, extraction, meta=meta)
    return extraction, "fresh_extraction"


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"completed_configs": [], "per_config": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("completed_configs", [])
    payload.setdefault("per_config", {})
    return payload


def _reset_checkpoint(
    *,
    run_fingerprint: dict[str, Any],
    extraction_fingerprint: str,
) -> dict[str, Any]:
    return {
        "completed_configs": [],
        "per_config": {},
        "run_fingerprint": run_fingerprint,
        "extraction_fingerprint": extraction_fingerprint,
    }


def _validate_checkpoint(
    checkpoint: dict[str, Any],
    *,
    run_fingerprint: dict[str, Any],
    extraction_fingerprint: str,
) -> dict[str, Any]:
    if not checkpoint.get("completed_configs") and not checkpoint.get("per_config"):
        return _reset_checkpoint(
            run_fingerprint=run_fingerprint,
            extraction_fingerprint=extraction_fingerprint,
        )
    if not _fingerprint_matches(checkpoint.get("run_fingerprint"), run_fingerprint):
        logger.warning(
            "Checkpoint stale (profile/model/seed/docs changed); discarding %d cached configs",
            len(checkpoint.get("completed_configs", [])),
        )
        return _reset_checkpoint(
            run_fingerprint=run_fingerprint,
            extraction_fingerprint=extraction_fingerprint,
        )
    if checkpoint.get("extraction_fingerprint") != extraction_fingerprint:
        logger.warning(
            "Checkpoint extraction mismatch; discarding %d cached configs",
            len(checkpoint.get("completed_configs", [])),
        )
        return _reset_checkpoint(
            run_fingerprint=run_fingerprint,
            extraction_fingerprint=extraction_fingerprint,
        )
    checkpoint["run_fingerprint"] = run_fingerprint
    checkpoint["extraction_fingerprint"] = extraction_fingerprint
    return checkpoint


def _save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def materialize_database(
    extraction: ExtractionResult,
    config: PopulationConfig,
    schema,
    *,
    extraction_model: str,
) -> tuple[dict, PopulationDiagnostics]:
    return apply_population(
        extraction,
        config,
        schema,
        extraction_model=extraction_model,
    )


def _category_error_report_path(output_dir: Path) -> Path:
    return output_dir / "category_error_report.json"


def _category_error_audit_summary_path(output_dir: Path) -> Path:
    return output_dir / "category_error_audit_summary.json"


def _category_error_top_calculations_path(output_dir: Path) -> Path:
    return output_dir / "category_error_top_calculations.json"


def _config_leaderboard_path(output_dir: Path) -> Path:
    return output_dir / "config_leaderboard.json"


def _config_winner_dimension_histograms_path(output_dir: Path) -> Path:
    return output_dir / "config_winner_dimension_histograms.json"


def _viable_config_search_space_path(output_dir: Path) -> Path:
    return output_dir / "viable_config_search_space.json"


def _write_config_leaderboard(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_category_error_audit(
    *,
    per_config: dict[str, Any],
    output_dir: Path,
    config_id: str | None = None,
    worst_query_limit: int = 5,
    detail_config_limit: int = 10,
    include_all_config_scalars: bool = False,
    top_error_limit: int = 10,
) -> dict[str, Any]:
    """Build summarized per-config audit JSON; full detail printed to stdout only."""
    evaluated = {
        cid: entry
        for cid, entry in per_config.items()
        if entry.get("per_query")
    }
    if not evaluated:
        raise ValueError("No evaluated configs available for category-error audit")

    refresh_per_config_scores(per_config)

    config_ids = [config_id] if config_id is not None else None
    if config_id is not None and config_id not in evaluated:
        raise ValueError(
            f"Config {config_id!r} has no per_query results "
            f"(available: {sorted(evaluated)})"
        )

    payload = build_workload_audit_summary(
        per_config,
        config_ids=config_ids,
        worst_query_limit=worst_query_limit,
        detail_config_limit=detail_config_limit,
        include_all_config_scalars=include_all_config_scalars,
    )
    summary_path = _category_error_audit_summary_path(output_dir)
    write_category_error_audit_summary(payload, summary_path)
    print(format_compact_category_error_audit(payload, per_config=per_config))
    print(f"Category error audit summary: {summary_path}")

    top_calc = build_top_category_error_audit(
        per_config,
        config_ids=config_ids,
        limit=top_error_limit,
    )
    top_calc_path = _category_error_top_calculations_path(output_dir)
    write_top_category_error_audit(top_calc, top_calc_path)
    print(format_top_category_error_calculations(top_calc.get("top_errors") or []))
    print(f"Top category error calculations: {top_calc_path}")

    return {
        "path": str(summary_path),
        "top_calculations_path": str(top_calc_path),
        "n_configs": payload.get("n_configs"),
        "workload_summary": payload.get("workload_summary"),
        "detail_config_limit": payload.get("detail_config_limit"),
    }


def evaluate_queries_on_db(
    instance,
    db: dict,
    queries: list[dict],
    *,
    settings,
    parser,
    attributes,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for query in queries:
        qid = str(query.get("query_id", ""))
        slice_name = classify_aggregation_slice(query.get("sql_query", "")) or "unknown"
        try:
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
            category_error = results.get("category_error")
            row = {
                "query_id": qid,
                "aggregation_slice": slice_name,
                "macro_f1": float(results["macro_f1"]),
                "mean_relative_error_pct": results.get("mean_relative_error_pct"),
                "query_error": results.get("query_error"),
                "query_accuracy": results.get("query_accuracy"),
                "pred_rows": len(results["predicted_result"]),
                "gold_rows": len(results["gold_result"]),
            }
            if category_error:
                row["category_error"] = category_error
                row["primary_failure_mode"] = category_error.get("primary_failure_mode")
            rows.append(row)
        except Exception as exc:
            rows.append(
                {
                    "query_id": qid,
                    "aggregation_slice": slice_name,
                    "macro_f1": 0.0,
                    "mean_relative_error_pct": 100.0,
                    "query_error": 1.0,
                    "query_accuracy": 0.0,
                    "pred_rows": -1,
                    "gold_rows": -1,
                    "primary_failure_mode": "evaluation_exception",
                    "error": str(exc),
                }
            )
    return rows


def _summarize_per_config(per_query: list[dict]) -> dict[str, Any]:
    by_slice: dict[str, list[float]] = defaultdict(list)
    f1s: list[float] = []
    query_errors: list[float] = []
    query_accuracies: list[float] = []
    failure_modes: dict[str, int] = defaultdict(int)
    for row in per_query:
        f1 = float(row.get("macro_f1", 0.0))
        f1s.append(f1)
        by_slice[row.get("aggregation_slice", "unknown")].append(f1)
        row = refresh_per_query_row_scores(row)
        if row.get("query_error") is not None:
            query_errors.append(float(row["query_error"]))
        if row.get("query_accuracy") is not None:
            query_accuracies.append(float(row["query_accuracy"]))
        mode = row.get("primary_failure_mode")
        if mode:
            failure_modes[str(mode)] += 1
    summary = {
        "mean_macro_f1": sum(f1s) / len(f1s) if f1s else 0.0,
        "mean_macro_f1_by_slice": {
            slice_name: sum(vals) / len(vals) if vals else 0.0
            for slice_name, vals in sorted(by_slice.items())
        },
    }
    if query_errors:
        summary["mean_query_error"] = sum(query_errors) / len(query_errors)
        summary["mean_query_accuracy"] = sum(query_accuracies) / len(query_accuracies)
        summary["failure_mode_counts"] = dict(sorted(failure_modes.items()))
    return summary


def _databases_dir(output_dir: Path) -> Path:
    return output_dir / "databases"


def run_config_grid(
    *,
    dataset: str = "Player",
    output_dir: Path,
    fresh_extraction: bool = False,
    max_configs: int | None = None,
    materialize_only: bool = False,
    resume: bool = True,
    save_databases: bool = True,
    num_docs: int | None = None,
    audit_metric: bool = False,
    audit_config_id: str | None = None,
    audit_worst_queries: int = 5,
    audit_detail_configs: int = 10,
    audit_all_config_scalars: bool = False,
    audit_top_errors: int = 10,
) -> dict[str, Any]:
    cfg = load_config()
    dataset_key = normalize_dataset_name(dataset)
    grid_cfg = cfg.get("config_grid", {})
    seed = int(cfg["experiment"]["seed"])
    if num_docs is None:
        num_docs = grid_cfg.get("num_docs")
    llm_cfg = cfg["llm"]
    extraction_model = llm_cfg["extraction_model"]
    llm_profile = llm_cfg.get("profile")

    test_queries, slice_counts = load_and_validate_test_queries(dataset=dataset_key)
    instance = build_test_instance(test_queries, dataset=dataset_key, num_docs=num_docs, seed=seed)
    corpus_fp = _corpus_fingerprint(instance.corpus)
    _warn_infeasible_test_queries(test_queries, instance.corpus)
    extraction_mode = (
        "workload_aware"
        if cfg.get("extraction", {}).get("workload_aware", True)
        else "legacy_schema"
    )
    demand_fp = _demand_fingerprint(
        extract_demand_profile_sql_only(test_queries)
        if extraction_mode == "workload_aware"
        else None
    )
    run_fingerprint = _run_fingerprint(
        extraction_model=extraction_model,
        llm_profile=llm_profile,
        seed=seed,
        num_docs=len(instance.corpus),
        n_test_queries=len(test_queries),
        corpus_fingerprint=corpus_fp,
        extraction_mode=extraction_mode,
        demand_fingerprint=demand_fp,
    )
    extraction, extraction_source = resolve_extraction(
        instance,
        output_dir=output_dir,
        extraction_model=extraction_model,
        llm_profile=llm_profile,
        seed=seed,
        n_test_queries=len(test_queries),
        test_queries=test_queries,
        fresh=fresh_extraction,
    )
    extraction_fp = _extraction_fingerprint(extraction)

    all_configs = generate_config_space()
    if max_configs is not None:
        all_configs = all_configs[:max_configs]

    checkpoint_path = _checkpoint_path(output_dir)
    if resume:
        checkpoint = _validate_checkpoint(
            _load_checkpoint(checkpoint_path),
            run_fingerprint=run_fingerprint,
            extraction_fingerprint=extraction_fp,
        )
    else:
        checkpoint = _reset_checkpoint(
            run_fingerprint=run_fingerprint,
            extraction_fingerprint=extraction_fp,
        )
    completed = set(checkpoint.get("completed_configs", []))
    per_config: dict[str, Any] = dict(checkpoint.get("per_config", {}))

    settings, parser, attributes, _ = _eval_context(instance)
    databases_dir = _databases_dir(output_dir)

    logger.info(
        "Config grid: %d configs, %d test queries, corpus=%d docs (%s), slices=%s, save_databases=%s",
        len(all_configs),
        len(test_queries),
        len(instance.corpus),
        instance.metadata.get("corpus_mode", "?"),
        slice_counts,
        save_databases,
    )

    for idx, config in enumerate(all_configs, start=1):
        cid = config.config_id
        db_path = database_path(databases_dir, cid)
        entry = per_config.get(cid)
        has_db_on_disk = save_databases and db_path.is_file()

        if cid in completed and entry is not None and (has_db_on_disk or not save_databases):
            needs_eval = not materialize_only and not entry.get("per_query")
            if not needs_eval:
                logger.info("[%d/%d] skip cached %s", idx, len(all_configs), cid)
                continue
            logger.info(
                "[%d/%d] re-evaluating cached %s (missing per_query results)",
                idx,
                len(all_configs),
                cid,
            )
            if has_db_on_disk:
                _, db = load_materialized_database(db_path)
                config_t0 = time.perf_counter()
                materialize_sec = 0.0
            else:
                config_t0 = time.perf_counter()
                db, diagnostics = materialize_database(
                    extraction,
                    config,
                    instance.schema,
                    extraction_model=extraction_model,
                )
                materialize_sec = time.perf_counter() - config_t0
                entry["population_diagnostics"] = _diagnostics_to_dict(diagnostics)
                entry["materialize_seconds"] = round(materialize_sec, 3)

            eval_t0 = time.perf_counter()
            per_query = evaluate_queries_on_db(
                instance,
                db,
                test_queries,
                settings=settings,
                parser=parser,
                attributes=attributes,
            )
            evaluate_sec = time.perf_counter() - eval_t0
            entry["evaluate_seconds"] = round(evaluate_sec, 3)
            entry["per_query"] = per_query
            entry.update(_summarize_per_config(per_query))
            entry["total_seconds"] = round(time.perf_counter() - config_t0, 3)
            per_config[cid] = entry
            checkpoint["per_config"] = per_config
            _save_checkpoint(checkpoint_path, checkpoint)
            logger.info(
                "[%d/%d] %s eval=%.1fs mean_f1=%.3f",
                idx,
                len(all_configs),
                cid,
                evaluate_sec,
                entry.get("mean_macro_f1", 0),
            )
            continue

        if cid in completed and entry is not None and save_databases and not has_db_on_disk:
            logger.warning(
                "[%d/%d] checkpoint hit for %s but database file missing; rematerializing",
                idx,
                len(all_configs),
                cid,
            )

        config_t0 = time.perf_counter()
        db, diagnostics = materialize_database(
            extraction,
            config,
            instance.schema,
            extraction_model=extraction_model,
        )
        materialize_sec = time.perf_counter() - config_t0

        saved_db_path: str | None = None
        if save_databases:
            save_materialized_database(db_path, config_id=cid, db=db)
            saved_db_path = str(db_path.relative_to(output_dir))

        entry = {
            "config_id": cid,
            "row_counts": _db_row_counts(db),
            "population_diagnostics": _diagnostics_to_dict(diagnostics),
            "materialize_seconds": round(materialize_sec, 3),
        }
        if saved_db_path is not None:
            entry["database_path"] = saved_db_path

        evaluate_sec: float | None = None
        if not materialize_only:
            eval_t0 = time.perf_counter()
            per_query = evaluate_queries_on_db(
                instance,
                db,
                test_queries,
                settings=settings,
                parser=parser,
                attributes=attributes,
            )
            evaluate_sec = time.perf_counter() - eval_t0
            entry["evaluate_seconds"] = round(evaluate_sec, 3)
            entry["per_query"] = per_query
            entry.update(_summarize_per_config(per_query))

        total_sec = time.perf_counter() - config_t0
        entry["total_seconds"] = round(total_sec, 3)

        per_config[cid] = entry
        completed.add(cid)
        checkpoint["completed_configs"] = sorted(completed)
        checkpoint["per_config"] = per_config
        _save_checkpoint(checkpoint_path, checkpoint)
        timing_parts = [f"total={total_sec:.1f}s", f"materialize={materialize_sec:.1f}s"]
        if evaluate_sec is not None:
            timing_parts.append(f"eval={evaluate_sec:.1f}s")
        logger.info(
            "[%d/%d] %s %s rows=%s%s%s",
            idx,
            len(all_configs),
            cid,
            " ".join(timing_parts),
            entry["row_counts"],
            f" db={saved_db_path}" if saved_db_path else "",
            f" mean_f1={entry.get('mean_macro_f1', 0):.3f}" if not materialize_only else "",
        )

    if save_databases:
        db_index: dict[str, str] = {}
        for cid, entry in per_config.items():
            rel = entry.get("database_path")
            if rel:
                db_index[cid] = Path(rel).name
            else:
                path = database_path(databases_dir, cid)
                if path.is_file():
                    db_index[cid] = path.name
        if db_index:
            write_database_index(databases_dir, entries=db_index)

    manifest = {
        "experiment": EXPERIMENT_NAME,
        "split": "test",
        "held_out_policy": HOLDOUT_POLICY,
        "n_configs": len(all_configs),
        "n_test_queries": len(test_queries),
        "slice_counts": slice_counts,
        "dataset": dataset_key,
        "slices_present": list(slice_counts.keys()),
        "extraction_source": extraction_source,
        "extraction_model": extraction_model,
        "extraction_fingerprint": extraction_fp,
        "run_fingerprint": run_fingerprint,
        "corpus_fingerprint": corpus_fp,
        "extraction_mode": extraction_mode,
        "demand_fingerprint": demand_fp,
        "demand_profile": extraction.demand_profile,
        "corpus_mode": instance.metadata.get("corpus_mode"),
        "aligned_corpus_size": instance.metadata.get("aligned_corpus_size"),
        "llm_profile": llm_profile,
        "num_docs": len(instance.corpus),
        "seed": seed,
        "materialize_only": materialize_only,
        "save_databases": save_databases,
        "databases_dir": str(_databases_dir(output_dir).relative_to(output_dir))
        if save_databases
        else None,
    }
    _manifest_path(output_dir).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if not materialize_only and per_config:
        refresh_per_config_scores(per_config)
        checkpoint["per_config"] = per_config
        _save_checkpoint(checkpoint_path, checkpoint)

    grid_summary = _build_grid_summary(per_config, slice_counts)
    category_error_report = None
    config_leaderboard = None
    config_winner_analysis = None
    test_query_ids = [str(q.get("query_id", "")) for q in test_queries]
    if not materialize_only and per_config:
        category_error_report = build_workload_category_error_report(
            per_config,
            query_ids=test_query_ids,
        )
        write_category_error_report(category_error_report, _category_error_report_path(output_dir))
        config_leaderboard = build_config_leaderboard(
            per_config,
            query_ids=test_query_ids,
        )
        _write_config_leaderboard(config_leaderboard, _config_leaderboard_path(output_dir))
        config_winner_analysis = build_and_write_config_winner_analysis(
            config_leaderboard,
            output_dir,
        )
        grid_summary["config_leaderboard"] = {
            "n_queries": config_leaderboard.get("n_queries"),
            "top_win_count": config_leaderboard.get("top_win_count"),
            "top_configs": (config_leaderboard.get("configs_at_top_win_count") or [])[:5],
            "leaderboard_path": str(_config_leaderboard_path(output_dir).name),
        }
        viable = config_winner_analysis.get("viable_search_space") or {}
        grid_summary["viable_config_search_space"] = {
            "n_ever_winning": viable.get("n_ever_winning"),
            "n_never_winning": viable.get("n_never_winning"),
            "ever_winning_fraction_of_evaluated": viable.get("ever_winning_fraction_of_evaluated"),
            "ever_winning_fraction_of_full_space": viable.get("ever_winning_fraction_of_full_space"),
            "report_path": str(_viable_config_search_space_path(output_dir).name),
            "histogram_path": str(_config_winner_dimension_histograms_path(output_dir).name),
        }

    results = {
        "manifest": manifest,
        "summary": grid_summary,
        "per_config": per_config,
        "category_error_report": category_error_report,
        "config_leaderboard": config_leaderboard,
        "config_winner_analysis": config_winner_analysis,
    }

    if audit_metric:
        if materialize_only:
            logger.warning("--audit-metric ignored with --materialize-only")
        else:
            results["category_error_audit"] = run_category_error_audit(
                per_config=per_config,
                output_dir=output_dir,
                config_id=audit_config_id,
                worst_query_limit=audit_worst_queries,
                detail_config_limit=audit_detail_configs,
                include_all_config_scalars=audit_all_config_scalars,
                top_error_limit=audit_top_errors,
            )

    _results_path(output_dir).write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def _build_grid_summary(per_config: dict[str, Any], slice_counts: dict[str, int]) -> dict[str, Any]:
    if not per_config:
        return {}
    ranked = sorted(
        per_config.items(),
        key=lambda kv: float(kv[1].get("mean_macro_f1") or 0.0),
        reverse=True,
    )
    best_cid, best_entry = ranked[0]
    mean_by_slice_across_configs: dict[str, list[float]] = defaultdict(list)
    for entry in per_config.values():
        if "mean_macro_f1_by_slice" not in entry:
            continue
        for slice_name, val in entry["mean_macro_f1_by_slice"].items():
            mean_by_slice_across_configs[slice_name].append(float(val))

    result: dict[str, Any] = {
        "n_configs_completed": len(per_config),
        "expected_slice_counts": slice_counts,
    }
    if best_entry.get("mean_macro_f1") is not None:
        result.update(
            {
                "best_config_id": best_cid,
                "best_mean_macro_f1": best_entry.get("mean_macro_f1"),
                "worst_mean_macro_f1": float(ranked[-1][1].get("mean_macro_f1") or 0.0),
                "mean_macro_f1_by_slice_averaged_over_configs": {
                    slice_name: sum(vals) / len(vals) if vals else 0.0
                    for slice_name, vals in sorted(mean_by_slice_across_configs.items())
                },
            }
        )

    error_ranked = sorted(
        (
            (cid, entry)
            for cid, entry in per_config.items()
            if entry.get("mean_query_error") is not None
        ),
        key=lambda kv: float(kv[1]["mean_query_error"]),
    )
    if error_ranked:
        best_err_cid, best_err_entry = error_ranked[0]
        worst_err_cid, worst_err_entry = error_ranked[-1]
        result.update(
            {
                "best_config_by_query_error": best_err_cid,
                "best_mean_query_error": best_err_entry.get("mean_query_error"),
                "best_mean_query_accuracy": best_err_entry.get("mean_query_accuracy"),
                "worst_config_by_query_error": worst_err_cid,
                "worst_mean_query_error": worst_err_entry.get("mean_query_error"),
                "worst_mean_query_accuracy": worst_err_entry.get("mean_query_accuracy"),
            }
        )
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize all pipeline configs and evaluate on held-out test split."
    )
    parser.add_argument("--dataset", default="Player", help="Bench-U dataset (Player, Med, ...)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Results directory (default: results/<dataset>/config_grid_test...)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore all caches: rerun extraction and rematerialize every config",
    )
    parser.add_argument("--fresh-extraction", action="store_true")
    parser.add_argument("--max-configs", type=int, default=None, help="Limit configs (smoke test)")
    parser.add_argument(
        "--num-docs",
        type=int,
        default=None,
        help="Cap extraction corpus size (default: all docs aligned to test queries)",
    )
    parser.add_argument(
        "--materialize-only",
        action="store_true",
        help="Only build databases; skip per-query evaluation",
    )
    parser.add_argument(
        "--no-save-databases",
        action="store_true",
        help="Do not persist materialized tables to disk (metrics only)",
    )
    parser.add_argument("--no-resume", action="store_true", help="Ignore checkpoint and start fresh")
    parser.add_argument(
        "--audit-metric",
        action="store_true",
        help="Print compact category-error audit per config (full detail for worst queries only)",
    )
    parser.add_argument(
        "--audit-config-id",
        default=None,
        help="Limit audit to one config (default: all evaluated configs)",
    )
    parser.add_argument(
        "--audit-worst-queries",
        type=int,
        default=5,
        help="Worst queries per config in the detail section (default: 5)",
    )
    parser.add_argument(
        "--audit-detail-configs",
        type=int,
        default=10,
        help="How many highest-error configs get per-query detail in the summary JSON (default: 10)",
    )
    parser.add_argument(
        "--audit-all-config-scalars",
        action="store_true",
        help="Include full per-config scalar blocks in JSON (large; default is ranking only)",
    )
    parser.add_argument(
        "--audit-top-errors",
        type=int,
        default=10,
        help="Print exact numerator/denominator path for the N largest category errors (default: 10)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = load_config()
    dataset = normalize_dataset_name(args.dataset)
    dataset_results = results_dir_for_dataset(dataset)
    default_grid_name = config_grid_output_dir(dataset_results, dataset)
    output_dir = args.output_dir or (dataset_results / default_grid_name)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Test config grid ({dataset}) → {output_dir}")
    print(f"LLM profile: {cfg['llm'].get('profile')} model={cfg['llm']['extraction_model']}")
    print()

    fresh = args.fresh or args.fresh_extraction
    resume = not args.no_resume and not args.fresh

    results = run_config_grid(
        dataset=dataset,
        output_dir=output_dir,
        fresh_extraction=fresh,
        max_configs=args.max_configs,
        materialize_only=args.materialize_only,
        resume=resume,
        save_databases=not args.no_save_databases,
        num_docs=args.num_docs,
        audit_metric=args.audit_metric,
        audit_config_id=args.audit_config_id,
        audit_worst_queries=args.audit_worst_queries,
        audit_detail_configs=args.audit_detail_configs,
        audit_all_config_scalars=args.audit_all_config_scalars,
        audit_top_errors=args.audit_top_errors,
    )
    summary = results.get("summary", {})
    manifest = results.get("manifest", {})
    print()
    print("=== Test config grid complete ===")
    print(f"Split: {manifest.get('split')} (held out)")
    print(f"Queries: {manifest.get('n_test_queries')} | slices: {manifest.get('slice_counts')}")
    print(f"Configs: {summary.get('n_configs_completed', 0)}")
    if summary.get("best_config_by_query_error") and summary.get("best_mean_query_error") is not None:
        print(
            f"Best by category error: {summary['best_config_by_query_error']} "
            f"(mean query error={summary['best_mean_query_error']:.4f}, "
            f"accuracy={summary.get('best_mean_query_accuracy', 0):.4f})"
        )
    if manifest.get("save_databases"):
        print(f"Databases: {_databases_dir(output_dir)}")
    if results.get("category_error_report"):
        print(f"Category error report: {_category_error_report_path(output_dir)}")
    if results.get("config_leaderboard"):
        print(format_config_leaderboard(results["config_leaderboard"]))
        print(f"Config leaderboard: {_config_leaderboard_path(output_dir)}")
    if results.get("config_winner_analysis"):
        dim_payload = results["config_winner_analysis"].get("dimension_histograms") or {}
        viable_payload = results["config_winner_analysis"].get("viable_search_space") or {}
        print()
        print(format_config_winner_dimension_histograms(dim_payload))
        print()
        print(format_viable_config_search_space(viable_payload))
        print(f"Winner dimension histograms: {_config_winner_dimension_histograms_path(output_dir)}")
        print(f"Viable search space: {_viable_config_search_space_path(output_dir)}")
        if dim_payload.get("charts_dir"):
            print(f"Winner dimension charts: {dim_payload['charts_dir']}")
    if results.get("category_error_audit"):
        print(f"Category error audit summary: {_category_error_audit_summary_path(output_dir)}")
    if summary.get("best_config_id") and summary.get("best_mean_macro_f1") is not None:
        print(
            f"Best config: {summary['best_config_id']} "
            f"(mean macro-F1={summary['best_mean_macro_f1']:.4f})"
        )
    print(f"Results: {_results_path(output_dir)}")


if __name__ == "__main__":
    main()
