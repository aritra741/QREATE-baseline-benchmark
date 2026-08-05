"""Run DocETL on a paired SQL + NL Player query manifest.

Extraction map prompts use the natural-language questions. Relational
closure still executes the reference SQL on DocETL-extracted tables, and
the column set to extract is derived from that SQL
(``columns_per_table_from_sql``). Accuracy uses the same
``official_query_error`` function as the WDIRS / QuWARTS evaluations:

    score = 1 - mean(query_error)

Results are checkpointed after each query and can be resumed.

Example:
    python systems/DocETL/run_player_nl_manifest_docetl.py \\
      --sql-manifest "case study/docetl_Player_v7/query_manifest.json" \\
      --nl-manifest "case study/docetl_Player_v7/query_manifest_nl.json" \\
      --out results/docetl_Player_agg20_nl
"""

from __future__ import annotations

import argparse
import json
import logging
import math
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
    nl: str
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


def _load_paired_manifests(
    sql_path: Path,
    nl_path: Path,
) -> List[Tuple[str, str, str]]:
    sql_rows = json.loads(sql_path.read_text())
    nl_rows = json.loads(nl_path.read_text())
    if not isinstance(sql_rows, list) or not isinstance(nl_rows, list):
        raise ValueError("Both manifests must be JSON arrays")

    nl_by_id: Dict[str, str] = {}
    for row in nl_rows:
        if not isinstance(row, Mapping):
            raise ValueError("NL manifest rows must be JSON objects")
        query_id = str(row.get("query_id", "")).strip()
        text = str(row.get("text") or row.get("nl") or "").strip()
        if not query_id or not text:
            raise ValueError(f"Invalid NL manifest row: {row!r}")
        if query_id in nl_by_id:
            raise ValueError(f"Duplicate NL query ID: {query_id}")
        nl_by_id[query_id] = text

    paired: List[Tuple[str, str, str]] = []
    seen: set[str] = set()
    for row in sql_rows:
        if not isinstance(row, Mapping):
            raise ValueError("SQL manifest rows must be JSON objects")
        query_id = str(row.get("query_id", "")).strip()
        sql = str(row.get("sql") or row.get("sql_query") or "").strip()
        if not query_id or not sql:
            raise ValueError(f"Invalid SQL manifest row: {row!r}")
        if query_id in seen:
            raise ValueError(f"Duplicate SQL query ID: {query_id}")
        if query_id not in nl_by_id:
            raise ValueError(f"No NL text for query {query_id!r}")
        seen.add(query_id)
        paired.append((query_id, sql, nl_by_id[query_id]))

    missing_sql = sorted(set(nl_by_id) - seen)
    if missing_sql:
        raise ValueError(f"NL-only query IDs without SQL: {missing_sql}")
    if not paired:
        raise ValueError("Manifest pair is empty")
    return paired


def _summary(rows: Sequence[QueryResult]) -> Dict[str, Any]:
    prompt_tokens = sum(row.prompt_tokens for row in rows)
    completion_tokens = sum(row.completion_tokens for row in rows)
    errors = [row.query_error for row in rows]
    mean_error = sum(errors) / len(errors) if errors else None
    return {
        "queries_expected": None,
        "queries_completed": len(rows),
        "queries_succeeded": sum(row.success for row in rows),
        "queries_failed": sum(not row.success for row in rows),
        "mean_query_error": mean_error,
        "score": (1.0 - mean_error) if mean_error is not None else None,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "llm_calls": sum(row.llm_calls for row in rows),
        "latency_seconds": sum(row.latency_s for row in rows),
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql-manifest", required=True, type=Path)
    parser.add_argument("--nl-manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", default="qwen2.5:7b-instruct")
    parser.add_argument("--ollama-base-url", default="http://localhost:11434")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore an existing checkpoint and rerun every query",
    )
    args = parser.parse_args()

    sql_path = args.sql_manifest.expanduser().resolve()
    nl_path = args.nl_manifest.expanduser().resolve()
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    docetl_runner.setup_logging(out_dir / "docetl_nl_manifest.log")
    ensure_precise_tokenizer_ready()
    _configure_docetl(args)

    manifest = _load_paired_manifests(sql_path, nl_path)
    _write_json_atomic(
        out_dir / "query_manifest.json",
        [{"query_id": qid, "sql": sql} for qid, sql, _ in manifest],
    )
    _write_json_atomic(
        out_dir / "query_manifest_nl.json",
        [{"query_id": qid, "text": nl} for qid, _, nl in manifest],
    )

    checkpoint_path = out_dir / "query_results.json"
    completed = {} if args.fresh else _load_checkpoint(checkpoint_path)
    expected = {qid: (sql, nl) for qid, sql, nl in manifest}
    stale = [
        qid
        for qid, row in completed.items()
        if qid not in expected
        or row.sql != expected[qid][0]
        or row.nl != expected[qid][1]
    ]
    if stale:
        raise ValueError(
            "Checkpoint does not match this manifest pair for query IDs "
            f"{stale}. Use a different --out directory or pass --fresh."
        )

    if completed:
        logger.info(
            "Resuming with %d/%d queries checkpointed",
            len(completed),
            len(manifest),
        )
    else:
        logger.info("Starting NL-manifest DocETL run with %d queries", len(manifest))
    logger.info("SQL manifest: %s", sql_path)
    logger.info("NL manifest: %s", nl_path)
    logger.info(
        "Model=%s API=%s threads=%d",
        docetl_runner.DOCETL_MODEL,
        docetl_runner.OLLAMA_BASE_URL,
        docetl_runner.DOCETL_THREADS,
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
        for index, (query_id, sql, nl) in enumerate(manifest, start=1):
            if query_id in completed and completed[query_id].success:
                ordered_results.append(completed[query_id])
                logger.info(
                    "[%d/%d] %s checkpointed; skipping",
                    index,
                    len(manifest),
                    query_id,
                )
                continue
            if query_id in completed:
                logger.info(
                    "[%d/%d] %s previously failed; retrying",
                    index,
                    len(manifest),
                    query_id,
                )

            logger.info("[%d/%d] Executing %s", index, len(manifest), query_id)
            logger.info("[NL] %s", nl)
            tokens_before = (
                GLOBAL_COUNTER.input_tokens,
                GLOBAL_COUNTER.output_tokens,
            )
            calls_before = GLOBAL_COUNTER.call_count
            started = time.time()
            try:
                gold_rows = _execute_sql(gt_conn, sql)
                pred_rows, _, _ = docetl_runner.execute_query_via_docetl_nl(
                    query_id, sql, nl, pipeline_dir
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
                    nl=nl,
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
                    nl=nl,
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
                completed[qid] for qid, _, _ in manifest if qid in completed
            ]
            _save_checkpoint(checkpoint_path, checkpoint_rows)
            current_summary = _summary(checkpoint_rows)
            current_summary.update(
                {
                    "queries_expected": len(manifest),
                    "dataset": "Player",
                    "sql_manifest": str(sql_path),
                    "nl_manifest": str(nl_path),
                    "model": docetl_runner.DOCETL_MODEL,
                    "ollama_base_url": docetl_runner.OLLAMA_BASE_URL,
                    "threads": args.threads,
                    "nl_context": True,
                    "accuracy_metric": (
                        "Same official_query_error as WDIRS / QuWARTS; "
                        "score = 1 - mean query error"
                    ),
                }
            )
            _write_json_atomic(out_dir / "summary.json", current_summary)
    finally:
        gt_conn.close()

    final_summary = _summary(ordered_results)
    final_summary.update(
        {
            "queries_expected": len(manifest),
            "dataset": "Player",
            "sql_manifest": str(sql_path),
            "nl_manifest": str(nl_path),
            "model": docetl_runner.DOCETL_MODEL,
            "ollama_base_url": docetl_runner.OLLAMA_BASE_URL,
            "threads": args.threads,
            "nl_context": True,
            "accuracy_metric": (
                "Same official_query_error as WDIRS / QuWARTS; "
                "score = 1 - mean query error"
            ),
        }
    )
    _write_json_atomic(out_dir / "summary.json", final_summary)
    GLOBAL_COUNTER.save_json(out_dir / "session_token_cost.json")

    logger.info("=" * 80)
    logger.info(
        "Completed %d/%d: score=%.4f mean_error=%.4f tokens=%d",
        final_summary["queries_completed"],
        final_summary["queries_expected"],
        final_summary["score"],
        final_summary["mean_query_error"],
        final_summary["total_tokens"],
    )
    logger.info("Summary: %s", out_dir / "summary.json")
    logger.info("=" * 80)
    return 0 if final_summary["queries_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
