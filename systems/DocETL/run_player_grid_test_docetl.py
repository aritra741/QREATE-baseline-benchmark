"""Run DocETL on the exact Player queries recorded by a WDIRS grid run.

The WDIRS ``config_grid_results.json`` is used as the query manifest. This
guarantees that DocETL is evaluated on the same sampled SQL statements rather
than merely recreating the sampling procedure. Accuracy uses the same
``official_query_error`` function as the WDIRS grid:

    score = 1 - mean(query_error)

Token usage is read from provider-reported LiteLLM usage at DocETL's lowest LLM
call layer. Results are checkpointed after each query and can be resumed.

Example:
    python systems/DocETL/run_player_grid_test_docetl.py \
      --grid-results results/spp_config_grid_Player_v7/config_grid_results.json \
      --out results/docetl_Player_v7
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
WDIRS_DIR = PROJECT_ROOT / "systems" / "WDIRS"

sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(WDIRS_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

import test_player_query_awareness_trend_docetl as docetl_runner  # noqa: E402
from diagnostics.run_config_grid import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    load_attributes,
    load_ground_truth,
)
from spp.config_grid import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    _build_in_memory_db,
    _execute_sql,
    official_query_error,
)
from token_counter import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    GLOBAL_COUNTER,
    ensure_precise_tokenizer_ready,
)

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    query_id: str
    sql: str
    success: bool
    query_error: float
    score: float
    gold_rows: int
    pred_rows: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    llm_calls: int
    latency_s: float
    error: str | None = None


def _load_query_manifest(path: Path) -> List[Tuple[str, str]]:
    """Read and validate the exact scored query list from grid output."""
    payload = json.loads(path.read_text())
    per_config = payload.get("per_config")
    if not isinstance(per_config, Mapping) or not per_config:
        raise ValueError(f"No per_config results found in {path}")

    first_id, first = next(iter(per_config.items()))
    rows = first.get("per_query", [])
    manifest = [(str(row["query_id"]), str(row["sql"])) for row in rows]
    if not manifest:
        raise ValueError(f"No per-query SQL found under config {first_id}")
    if len({qid for qid, _ in manifest}) != len(manifest):
        raise ValueError("Grid query manifest contains duplicate query IDs")

    expected = manifest
    for config_id, entry in per_config.items():
        observed = [
            (str(row["query_id"]), str(row["sql"]))
            for row in entry.get("per_query", [])
        ]
        if observed != expected:
            raise ValueError(
                f"Query manifest differs between configs {first_id!r} and "
                f"{config_id!r}; refusing an ambiguous comparison"
            )
    return manifest


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.replace(path)


def _load_checkpoint(path: Path) -> Dict[str, QueryResult]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {row["query_id"]: QueryResult(**row) for row in raw}


def _save_checkpoint(path: Path, rows: Sequence[QueryResult]) -> None:
    _write_json_atomic(path, [asdict(row) for row in rows])


def _summary(
    rows: Sequence[QueryResult],
    *,
    input_cost_per_million: float,
    output_cost_per_million: float,
    expected_queries: int,
) -> Dict[str, Any]:
    prompt_tokens = sum(row.prompt_tokens for row in rows)
    completion_tokens = sum(row.completion_tokens for row in rows)
    total_tokens = prompt_tokens + completion_tokens
    total_cost = (
        prompt_tokens * input_cost_per_million
        + completion_tokens * output_cost_per_million
    ) / 1_000_000

    # A failed query is retained with error=1 and score=0. This prevents
    # failures from artificially improving the reported mean.
    errors = [row.query_error for row in rows]
    mean_error = sum(errors) / len(errors) if errors else None
    score = 1.0 - mean_error if mean_error is not None else None
    return {
        "queries_expected": expected_queries,
        "queries_completed": len(rows),
        "queries_succeeded": sum(row.success for row in rows),
        "queries_failed": sum(not row.success for row in rows),
        "mean_query_error": mean_error,
        "score": score,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "llm_calls": sum(row.llm_calls for row in rows),
        "latency_seconds": sum(row.latency_s for row in rows),
        "input_cost_per_million_tokens": input_cost_per_million,
        "output_cost_per_million_tokens": output_cost_per_million,
        "estimated_dollar_cost": total_cost,
        "cost_note": (
            "Ollama is locally hosted, so monetary API cost is $0 by default. "
            "Pass nonzero per-million-token rates to estimate an equivalent "
            "hosted-model cost; compute/electricity cost is not included."
        ),
    }


def _configure_docetl(args: argparse.Namespace) -> None:
    model = args.model
    if not model.startswith("ollama/"):
        model = f"ollama/{model}"
    docetl_runner.DOCETL_MODEL = model
    docetl_runner.OLLAMA_BASE_URL = args.ollama_base_url
    docetl_runner.DOCETL_THREADS = args.threads
    docetl_runner.DOCETL_MAP_TIMEOUT = args.timeout
    docetl_runner.DOCETL_MAX_RETRIES_PER_TIMEOUT = args.retries


def _add_run_metadata(
    summary: Dict[str, Any],
    *,
    grid_path: Path,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    summary.update(
        {
            "dataset": "Player",
            "grid_results": str(grid_path),
            "model": docetl_runner.DOCETL_MODEL,
            "ollama_base_url": docetl_runner.OLLAMA_BASE_URL,
            "threads": args.threads,
            "accuracy_metric": (
                "Same official_query_error as WDIRS config grid; "
                "score = 1 - mean query error"
            ),
            "query_context": (
                "Benchmark SQL itself (the exact sampled queries have no "
                "natural-language descriptions)"
            ),
        }
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid-results", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", default="qwen2.5:7b-instruct")
    parser.add_argument("--ollama-base-url", default="http://localhost:11434")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument(
        "--input-cost-per-million",
        type=float,
        default=0.0,
        help="Optional hosted-price estimate; local Ollama defaults to $0",
    )
    parser.add_argument(
        "--output-cost-per-million",
        type=float,
        default=0.0,
        help="Optional hosted-price estimate; local Ollama defaults to $0",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore an existing checkpoint and rerun every query",
    )
    args = parser.parse_args()

    grid_path = args.grid_results.expanduser().resolve()
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    docetl_runner.setup_logging(out_dir / "docetl_grid_test.log")
    ensure_precise_tokenizer_ready()
    _configure_docetl(args)

    manifest = _load_query_manifest(grid_path)
    _write_json_atomic(
        out_dir / "query_manifest.json",
        [{"query_id": qid, "sql": sql} for qid, sql in manifest],
    )
    checkpoint_path = out_dir / "query_results.json"
    completed = {} if args.fresh else _load_checkpoint(checkpoint_path)
    manifest_sql = dict(manifest)
    stale = [
        qid
        for qid, row in completed.items()
        if qid not in manifest_sql or row.sql != manifest_sql[qid]
    ]
    if stale:
        raise ValueError(
            "Checkpoint does not match this grid manifest for query IDs "
            f"{stale}. Use a different --out directory or pass --fresh."
        )

    if completed:
        logger.info("Resuming with %d/%d queries checkpointed", len(completed), len(manifest))
    else:
        logger.info("Starting exact-grid DocETL run with %d queries", len(manifest))
    logger.info("Grid manifest: %s", grid_path)
    logger.info(
        "Model=%s API=%s threads=%d",
        docetl_runner.DOCETL_MODEL,
        docetl_runner.OLLAMA_BASE_URL,
        docetl_runner.DOCETL_THREADS,
    )
    logger.info(
        "Query context uses the benchmark SQL itself because the sampled grid "
        "queries do not have natural-language descriptions."
    )

    ground_truth = load_ground_truth("Player")
    attributes = load_attributes("Player")
    gt_conn = _build_in_memory_db(ground_truth)

    token_tracker = docetl_runner.TokenTracker()
    docetl_runner.patch_docetl_for_token_tracking(token_tracker)
    pipeline_dir = out_dir / "docetl_pipelines"
    table_dir = out_dir / "query_tables"
    table_dir.mkdir(parents=True, exist_ok=True)

    ordered_results: List[QueryResult] = []
    try:
        for index, (query_id, sql) in enumerate(manifest, start=1):
            if query_id in completed and completed[query_id].success:
                ordered_results.append(completed[query_id])
                logger.info("[%d/%d] %s checkpointed; skipping", index, len(manifest), query_id)
                continue
            if query_id in completed:
                logger.info(
                    "[%d/%d] %s previously failed; retrying",
                    index,
                    len(manifest),
                    query_id,
                )

            logger.info("[%d/%d] Executing %s", index, len(manifest), query_id)
            # GLOBAL_COUNTER.record() is lock-protected; use it for deltas
            # because DocETL executes document maps concurrently.
            tokens_before = (
                GLOBAL_COUNTER.input_tokens,
                GLOBAL_COUNTER.output_tokens,
            )
            calls_before = GLOBAL_COUNTER.call_count
            started = time.time()
            try:
                gold_rows = _execute_sql(gt_conn, sql)
                # SQL is the only query-intent representation available for
                # this exact seeded sample, and is also what WDIRS receives.
                pred_rows, _, _ = docetl_runner.execute_query_via_docetl_nl(
                    query_id, sql, sql, pipeline_dir
                )
                error = float(
                    official_query_error(sql, gold_rows, pred_rows, attributes)
                )
                if not math.isfinite(error):
                    raise ValueError(f"Non-finite official query error: {error}")
                prompt = GLOBAL_COUNTER.input_tokens - tokens_before[0]
                completion = GLOBAL_COUNTER.output_tokens - tokens_before[1]
                item = QueryResult(
                    query_id=query_id,
                    sql=sql,
                    success=True,
                    query_error=error,
                    score=1.0 - error,
                    gold_rows=len(gold_rows),
                    pred_rows=len(pred_rows),
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    total_tokens=prompt + completion,
                    llm_calls=GLOBAL_COUNTER.call_count - calls_before,
                    latency_s=time.time() - started,
                )
                _write_json_atomic(table_dir / f"{query_id}.json", pred_rows)
                logger.info(
                    "%s score=%.4f error=%.4f rows=%d/%d tokens=%d",
                    query_id,
                    item.score,
                    item.query_error,
                    item.pred_rows,
                    item.gold_rows,
                    item.total_tokens,
                )
            except Exception as exc:
                prompt = GLOBAL_COUNTER.input_tokens - tokens_before[0]
                completion = GLOBAL_COUNTER.output_tokens - tokens_before[1]
                item = QueryResult(
                    query_id=query_id,
                    sql=sql,
                    success=False,
                    query_error=1.0,
                    score=0.0,
                    gold_rows=0,
                    pred_rows=0,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    total_tokens=prompt + completion,
                    llm_calls=GLOBAL_COUNTER.call_count - calls_before,
                    latency_s=time.time() - started,
                    error=str(exc),
                )
                logger.exception("%s failed; counted as score=0", query_id)

            completed[query_id] = item
            ordered_results.append(item)
            checkpoint_rows = [
                completed[qid] for qid, _ in manifest if qid in completed
            ]
            _save_checkpoint(checkpoint_path, checkpoint_rows)
            current_summary = _add_run_metadata(
                _summary(
                    checkpoint_rows,
                    input_cost_per_million=args.input_cost_per_million,
                    output_cost_per_million=args.output_cost_per_million,
                    expected_queries=len(manifest),
                ),
                grid_path=grid_path,
                args=args,
            )
            _write_json_atomic(out_dir / "summary.json", current_summary)
    finally:
        gt_conn.close()

    final_summary = _add_run_metadata(
        _summary(
            ordered_results,
            input_cost_per_million=args.input_cost_per_million,
            output_cost_per_million=args.output_cost_per_million,
            expected_queries=len(manifest),
        ),
        grid_path=grid_path,
        args=args,
    )
    _write_json_atomic(out_dir / "summary.json", final_summary)
    # On a resumed run GLOBAL_COUNTER only contains calls made by this process;
    # summary.json and query_results.json contain the cumulative checkpointed
    # totals. Name this file explicitly to avoid mistaking it for full-run cost.
    GLOBAL_COUNTER.save_json(out_dir / "session_token_cost.json")

    logger.info("=" * 80)
    logger.info(
        "Completed %d/%d: score=%.4f mean_error=%.4f tokens=%d cost=$%.6f",
        final_summary["queries_completed"],
        final_summary["queries_expected"],
        final_summary["score"],
        final_summary["mean_query_error"],
        final_summary["total_tokens"],
        final_summary["estimated_dollar_cost"],
    )
    logger.info("Summary: %s", out_dir / "summary.json")
    logger.info("=" * 80)
    return 0 if final_summary["queries_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
