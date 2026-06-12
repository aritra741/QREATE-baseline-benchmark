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
from data.instance_builder import build_instance
from data.query_alignment import (
    corpus_alignment_metadata,
    sample_corpus_stratified,
    tables_referenced_by_queries,
)
from data.materialized_db_store import (
    database_path,
    save_materialized_database,
    write_database_index,
)
from data.workload_splits import HOLDOUT_POLICY, load_split_queries
from optimizer.config_space import PopulationConfig, generate_config_space
from pipeline.evaluation import _eval_context
from pipeline.extraction import ExtractionResult, extract_documents
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


def _run_fingerprint(
    *,
    extraction_model: str,
    llm_profile: str | None,
    seed: int,
    num_docs: int,
    n_test_queries: int,
) -> dict[str, Any]:
    """Fields that must match for checkpoint / extraction cache reuse."""
    return {
        "extraction_model": extraction_model,
        "llm_profile": llm_profile,
        "seed": seed,
        "num_docs": num_docs,
        "n_test_queries": n_test_queries,
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
    }


def _extraction_from_payload(payload: dict[str, Any]) -> ExtractionResult:
    return ExtractionResult(
        tuples_by_table=dict(payload.get("tuples_by_table", {})),
        token_cost=float(payload.get("token_cost", 0.0)),
        per_doc_signals=list(payload.get("per_doc_signals", [])),
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


def load_and_validate_test_queries() -> tuple[list[dict], dict[str, int]]:
    """Load held-out test queries; require all five aggregation slices."""
    queries = load_split_queries("test")
    by_slice: dict[str, list[dict]] = defaultdict(list)
    for query in queries:
        slice_name = classify_aggregation_slice(query.get("sql_query", ""))
        if slice_name:
            by_slice[slice_name].append(query)

    counts = {slice_name: len(by_slice.get(slice_name, [])) for slice_name in AGGREGATION_SLICE_ORDER}
    missing = [s for s in AGGREGATION_SLICE_ORDER if counts[s] == 0]
    if missing:
        raise RuntimeError(
            f"Test split missing slices: {missing}. "
            "Regenerate with: python -m data.workload_splits"
        )
    return queries, dict(counts)


def build_test_instance(
    test_queries: list[dict],
    *,
    num_docs: int,
    seed: int,
):
    """Single corpus aligned to the full test workload (all slices)."""
    base = build_instance("Player", include_ground_truth=False)
    schema = base.schema
    required_tables = tables_referenced_by_queries(test_queries, schema)
    corpus = sample_corpus_stratified(base.corpus, required_tables, num_docs, seed)
    return replace(
        base,
        corpus=corpus,
        queries=test_queries,
        metadata={
            **(base.metadata or {}),
            **corpus_alignment_metadata(corpus),
            "workload_split": "test",
            "experiment": EXPERIMENT_NAME,
            "num_docs": len(corpus),
            "num_eval_queries": len(test_queries),
            "required_tables": sorted(required_tables),
            "held_out": True,
        },
    )


def resolve_extraction(
    instance,
    *,
    output_dir: Path,
    extraction_model: str,
    llm_profile: str | None,
    seed: int,
    n_test_queries: int,
    fresh: bool,
) -> tuple[ExtractionResult, str]:
    cache_path = _extraction_cache_path(output_dir)
    expected_meta = _run_fingerprint(
        extraction_model=extraction_model,
        llm_profile=llm_profile,
        seed=seed,
        num_docs=len(instance.corpus),
        n_test_queries=n_test_queries,
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
    extraction = extract_documents(instance.corpus, instance.schema, extraction_model)
    meta = {**expected_meta, "extraction_fingerprint": _extraction_fingerprint(extraction)}
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
            rows.append(
                {
                    "query_id": qid,
                    "aggregation_slice": slice_name,
                    "macro_f1": float(results["macro_f1"]),
                    "mean_relative_error_pct": results.get("mean_relative_error_pct"),
                    "pred_rows": len(results["predicted_result"]),
                    "gold_rows": len(results["gold_result"]),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "query_id": qid,
                    "aggregation_slice": slice_name,
                    "macro_f1": 0.0,
                    "mean_relative_error_pct": 100.0,
                    "pred_rows": -1,
                    "gold_rows": -1,
                    "error": str(exc),
                }
            )
    return rows


def _summarize_per_config(per_query: list[dict]) -> dict[str, Any]:
    by_slice: dict[str, list[float]] = defaultdict(list)
    f1s: list[float] = []
    for row in per_query:
        f1 = float(row.get("macro_f1", 0.0))
        f1s.append(f1)
        by_slice[row.get("aggregation_slice", "unknown")].append(f1)
    return {
        "mean_macro_f1": sum(f1s) / len(f1s) if f1s else 0.0,
        "mean_macro_f1_by_slice": {
            slice_name: sum(vals) / len(vals) if vals else 0.0
            for slice_name, vals in sorted(by_slice.items())
        },
    }


def _databases_dir(output_dir: Path) -> Path:
    return output_dir / "databases"


def run_config_grid(
    *,
    output_dir: Path,
    fresh_extraction: bool = False,
    max_configs: int | None = None,
    materialize_only: bool = False,
    resume: bool = True,
    save_databases: bool = True,
) -> dict[str, Any]:
    cfg = load_config()
    phase0 = cfg.get("phase0", {})
    seed = int(cfg["experiment"]["seed"])
    num_docs = int(phase0.get("num_docs", 20))
    llm_cfg = cfg["llm"]
    extraction_model = llm_cfg["extraction_model"]
    llm_profile = llm_cfg.get("profile")

    test_queries, slice_counts = load_and_validate_test_queries()
    instance = build_test_instance(test_queries, num_docs=num_docs, seed=seed)
    run_fingerprint = _run_fingerprint(
        extraction_model=extraction_model,
        llm_profile=llm_profile,
        seed=seed,
        num_docs=num_docs,
        n_test_queries=len(test_queries),
    )
    extraction, extraction_source = resolve_extraction(
        instance,
        output_dir=output_dir,
        extraction_model=extraction_model,
        llm_profile=llm_profile,
        seed=seed,
        n_test_queries=len(test_queries),
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
        "Config grid: %d configs, %d test queries, slices=%s, save_databases=%s",
        len(all_configs),
        len(test_queries),
        slice_counts,
        save_databases,
    )

    for idx, config in enumerate(all_configs, start=1):
        cid = config.config_id
        db_path = database_path(databases_dir, cid)
        entry = per_config.get(cid)
        has_db_on_disk = save_databases and db_path.is_file()

        if cid in completed and entry is not None and (has_db_on_disk or not save_databases):
            logger.info("[%d/%d] skip cached %s", idx, len(all_configs), cid)
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
        "slices_present": list(AGGREGATION_SLICE_ORDER),
        "extraction_source": extraction_source,
        "extraction_model": extraction_model,
        "extraction_fingerprint": extraction_fp,
        "run_fingerprint": run_fingerprint,
        "llm_profile": llm_profile,
        "num_docs": num_docs,
        "seed": seed,
        "materialize_only": materialize_only,
        "save_databases": save_databases,
        "databases_dir": str(_databases_dir(output_dir).relative_to(output_dir))
        if save_databases
        else None,
    }
    _manifest_path(output_dir).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    grid_summary = _build_grid_summary(per_config, slice_counts)
    results = {
        "manifest": manifest,
        "summary": grid_summary,
        "per_config": per_config,
    }
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
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize all pipeline configs and evaluate on held-out test split."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"Results directory (default: results/{DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore all caches: rerun extraction and rematerialize every config",
    )
    parser.add_argument("--fresh-extraction", action="store_true")
    parser.add_argument("--max-configs", type=int, default=None, help="Limit configs (smoke test)")
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
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = load_config()
    output_dir = args.output_dir or (Path(cfg["paths"]["results_dir"]) / DEFAULT_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Test config grid → {output_dir}")
    print(f"LLM profile: {cfg['llm'].get('profile')} model={cfg['llm']['extraction_model']}")
    print()

    fresh = args.fresh or args.fresh_extraction
    resume = not args.no_resume and not args.fresh

    results = run_config_grid(
        output_dir=output_dir,
        fresh_extraction=fresh,
        max_configs=args.max_configs,
        materialize_only=args.materialize_only,
        resume=resume,
        save_databases=not args.no_save_databases,
    )
    summary = results.get("summary", {})
    manifest = results.get("manifest", {})
    print()
    print("=== Test config grid complete ===")
    print(f"Split: {manifest.get('split')} (held out)")
    print(f"Queries: {manifest.get('n_test_queries')} | slices: {manifest.get('slice_counts')}")
    print(f"Configs: {summary.get('n_configs_completed', 0)}")
    if manifest.get("save_databases"):
        print(f"Databases: {_databases_dir(output_dir)}")
    if summary.get("best_config_id") and summary.get("best_mean_macro_f1") is not None:
        print(
            f"Best config: {summary['best_config_id']} "
            f"(mean macro-F1={summary['best_mean_macro_f1']:.4f})"
        )
    print(f"Results: {_results_path(output_dir)}")


if __name__ == "__main__":
    main()
