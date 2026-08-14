#!/usr/bin/env python3
"""Run classic SQL-context DocETL on Art/CSPaper/Finan/Legal/Med/SEC workloads.

Mirrors ``run_player_contrast_docetl.py``: write a grid shim from the SQL
manifest, run the DocETL grid executor, then score with
``evaluate_docetl_result_dir.py`` using the CSV evaluation dataset name.

Examples:
  python3 "case study/run_contrast_docetl.py" --dry-run --only art_agg20
  python3 "case study/run_contrast_docetl.py" --run --datasets art \\
      --model qwen2.5:7b-instruct --threads 4 --force
  python3 "case study/run_contrast_docetl.py" --run --datasets med --retry-failed
  python3 "case study/run_contrast_docetl.py" --run --only med_join20 \\
      --continue-on-error
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CASE = Path(__file__).resolve().parent
if str(CASE) not in sys.path:
    sys.path.insert(0, str(CASE))

from contrast_run_lib import (  # noqa: E402
    DEFAULT_CSV,
    ROOT,
    WORKLOADS,
    load_csv,
    parse_datasets,
    parse_only,
    rel,
    resolve_repo_path,
    select_rows,
    stamp_source_dataset,
)

DOCETL = ROOT / "systems" / "DocETL"
RUNNER = DOCETL / "run_player_grid_test_docetl.py"
EVALUATOR = DOCETL / "evaluate_docetl_result_dir.py"


def load_sql_pairs(manifest_path: Path) -> list[dict[str, str]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = payload.get("queries", []) if isinstance(payload, dict) else payload
    pairs: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{manifest_path}: row {index} is not an object")
        query_id = str(row.get("query_id", f"q{index}")).strip()
        sql = str(row.get("sql") or row.get("sql_query") or "").strip()
        if not query_id or not sql:
            raise ValueError(f"{manifest_path}: invalid row {index}")
        pairs.append({"query_id": query_id, "sql": sql})
    if not pairs:
        raise ValueError(f"{manifest_path}: empty SQL workload")
    return pairs


def write_grid_shim(sql_manifest: Path, shim_path: Path, workload_id: str) -> Path:
    pairs = load_sql_pairs(sql_manifest)
    shim = {"per_config": {workload_id: {"per_query": pairs}}}
    shim_path.parent.mkdir(parents=True, exist_ok=True)
    shim_path.write_text(json.dumps(shim, indent=2), encoding="utf-8")
    return shim_path


def prepare_output_dir(
    output_root: Path,
    workload_id: str,
    *,
    force: bool,
    resume: bool,
) -> Path:
    output_dir = output_root / "results" / workload_id
    if resume:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    if output_dir.exists():
        if not force and any(output_dir.iterdir()):
            raise FileExistsError(
                f"{output_dir} already exists; pass --force to replace "
                "or --retry-failed to rerun only failed queries"
            )
        if force:
            shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def latest_docetl_root(workload_ids: set[str]) -> Path | None:
    runs_dir = WORKLOADS / "runs"
    if not runs_dir.is_dir():
        return None
    stamps = sorted(
        (path for path in runs_dir.iterdir() if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )
    for stamp in stamps:
        docetl = stamp / "docetl"
        if any((docetl / "results" / workload_id).is_dir() for workload_id in workload_ids):
            return docetl.resolve()
    return None


def failed_query_ids(output_dir: Path) -> list[str] | None:
    checkpoint = output_dir / "query_results.json"
    if not checkpoint.is_file():
        return None
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return None
    return [
        str(row["query_id"])
        for row in payload
        if isinstance(row, dict) and not row.get("success")
    ]


def run_one(
    row: dict[str, str],
    *,
    output_root: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    workload_id = row["workload_id"].strip()
    sql_manifest = resolve_repo_path(row["sql_manifest"])
    if not sql_manifest.is_file():
        raise FileNotFoundError(sql_manifest)
    eval_dataset = str(row.get("dataset") or "").strip()

    started = time.monotonic()
    record: dict[str, Any] = {
        "workload_id": workload_id,
        "kind": row.get("kind", ""),
        "dataset": eval_dataset,
        "source_dataset": row.get("source_dataset", ""),
        "sql_manifest": rel(sql_manifest),
        "n_queries": row.get("n_queries", ""),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "query_context": "benchmark SQL (classic UDA-Bench DocETL path)",
    }

    output_dir = output_root / "results" / workload_id
    shim_path = output_dir / "docetl_grid_shim.json"
    eval_output = output_dir / "evaluation.json"
    retry_failed = bool(args.retry_failed)
    run_command = [
        sys.executable,
        str(RUNNER),
        "--grid-results",
        str(shim_path),
        "--out",
        str(output_dir),
        "--dataset",
        eval_dataset,
        "--model",
        args.model,
        "--ollama-base-url",
        args.ollama_base_url,
        "--threads",
        str(args.threads),
        "--timeout",
        str(args.timeout),
        "--retries",
        str(args.retries),
    ]
    if args.force:
        run_command.append("--fresh")
    eval_command = [
        sys.executable,
        str(EVALUATOR),
        "--result-dir",
        str(output_dir),
        "--reference-workload",
        str(sql_manifest),
        "--dataset",
        eval_dataset,
        "--output",
        str(eval_output),
    ]

    record["output_dir"] = rel(output_dir)
    record["shim_path"] = rel(shim_path)
    record["run_command"] = run_command
    record["eval_command"] = eval_command

    print(
        f"\n=== {workload_id} (DocETL SQL, {eval_dataset} → {row.get('source_dataset')}) ===",
        flush=True,
    )
    print(" ".join(run_command), flush=True)
    if not args.skip_eval:
        print(" ".join(eval_command), flush=True)

    if retry_failed:
        pending = failed_query_ids(output_dir)
        record["retry_failed_query_ids"] = pending
        if pending is None:
            record.update(
                {
                    "status": "skipped_no_checkpoint",
                    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                    "wall_clock_seconds": round(time.monotonic() - started, 3),
                }
            )
            print(f"{workload_id}: no query_results.json; skip", flush=True)
            return record
        if not pending:
            record.update(
                {
                    "status": "skipped_all_ok",
                    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                    "wall_clock_seconds": round(time.monotonic() - started, 3),
                }
            )
            print(f"{workload_id}: all queries already succeeded; skip", flush=True)
            return record
        print(
            f"{workload_id}: retrying {len(pending)} failed queries: "
            + ", ".join(pending),
            flush=True,
        )

    if args.dry_run:
        record.update(
            {
                "status": "dry_run",
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "wall_clock_seconds": round(time.monotonic() - started, 3),
            }
        )
        return record

    try:
        prepare_output_dir(
            output_root,
            workload_id,
            force=args.force,
            resume=retry_failed,
        )
    except FileExistsError as exc:
        record.update(
            {
                "status": "skipped_exists",
                "error": str(exc),
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "wall_clock_seconds": round(time.monotonic() - started, 3),
            }
        )
        return record

    write_grid_shim(sql_manifest, shim_path, workload_id)
    log_path = output_root / "logs" / f"{workload_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record["log_path"] = rel(log_path)

    env = os.environ.copy()
    summary_path = output_dir / "summary.json"
    log_mode = "a" if retry_failed and log_path.exists() else "w"
    with log_path.open(log_mode, encoding="utf-8") as log_handle:
        log_handle.write("RUN COMMAND:\n" + " ".join(run_command) + "\n\n")
        log_handle.flush()
        completed = subprocess.run(
            run_command,
            cwd=str(ROOT),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
        record["run_exit_code"] = completed.returncode
        has_results = summary_path.is_file() and (output_dir / "query_tables").is_dir()
        if has_results and not args.skip_eval:
            log_handle.write("\n\nEVAL COMMAND:\n" + " ".join(eval_command) + "\n\n")
            log_handle.flush()
            print(" ".join(eval_command), flush=True)
            evaluated = subprocess.run(
                eval_command,
                cwd=str(ROOT),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
            record["eval_exit_code"] = evaluated.returncode
            if evaluated.returncode == 0 and eval_output.is_file():
                try:
                    report = json.loads(eval_output.read_text(encoding="utf-8"))
                    record["evaluation"] = {
                        "mean_official_accuracy": report.get(
                            "mean_official_accuracy"
                        ),
                        "mean_structure_score": report.get("mean_structure_score"),
                        "mean_query_score": report.get("mean_query_score"),
                        "output": rel(eval_output),
                    }
                except json.JSONDecodeError:
                    pass
            status_ok = evaluated.returncode == 0
        else:
            status_ok = completed.returncode == 0 and has_results

    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            record["docetl_summary"] = {
                "score": summary.get("score"),
                "mean_query_error": summary.get("mean_query_error"),
                "queries_succeeded": summary.get("queries_succeeded"),
                "queries_failed": summary.get("queries_failed"),
                "total_tokens": summary.get("total_tokens"),
            }
        except json.JSONDecodeError:
            pass

    record["exit_code"] = 0 if status_ok else 1
    if status_ok and completed.returncode != 0:
        record["status"] = "ok_with_query_failures"
    else:
        record["status"] = "ok" if status_ok else "failed"
    record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    record["wall_clock_seconds"] = round(time.monotonic() - started, 3)

    if not status_ok:
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            log_text = ""
        tail = "\n".join(log_text.splitlines()[-80:])
        record["error_tail"] = tail
        print(
            f"\n----- {workload_id} failed; last log lines -----\n"
            f"{tail}\n"
            f"----- full log: {log_path} -----\n",
            flush=True,
        )
    else:
        if completed.returncode != 0:
            print(
                f"{workload_id}: DocETL exit={completed.returncode} "
                f"(some queries failed); scoring completed tables anyway.",
                flush=True,
            )
        if record.get("evaluation"):
            print(json.dumps(record["evaluation"], indent=2), flush=True)
        elif record.get("docetl_summary"):
            print(json.dumps(record["docetl_summary"], indent=2), flush=True)
    return record


def write_index(output_root: Path, records: list[dict[str, Any]]) -> None:
    index_json = output_root / "run_index.json"
    index_csv = output_root / "run_index.csv"
    index_json.write_text(
        json.dumps(records, indent=2, default=str),
        encoding="utf-8",
    )
    fields = [
        "workload_id",
        "kind",
        "status",
        "exit_code",
        "n_queries",
        "dataset",
        "source_dataset",
        "output_dir",
        "log_path",
        "wall_clock_seconds",
        "error",
    ]
    with index_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", type=str, default="")
    parser.add_argument(
        "--datasets",
        default="",
        help="Comma-separated eval dataset names, e.g. art,legal,med.",
    )
    parser.add_argument("--include-player", action="store_true")
    parser.add_argument("--include-disabled", action="store_true")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help=(
            "Reuse an existing result dir and rerun only queries whose "
            "checkpoint success=false. Skips packs that already finished. "
            "Uses --output-root, or the latest workloads/runs/*/docetl."
        ),
    )
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--model", default="qwen2.5:7b-instruct")
    parser.add_argument("--ollama-base-url", default="http://localhost:11434")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--retries", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.run and not args.dry_run:
        raise SystemExit("Pass --run and/or --dry-run")
    if args.force and args.retry_failed:
        raise SystemExit("Use either --force or --retry-failed, not both")
    if not RUNNER.is_file() or not EVALUATOR.is_file():
        raise SystemExit(f"DocETL scripts missing under {DOCETL}")

    csv_path = args.csv.expanduser()
    if not csv_path.is_absolute():
        csv_path = (ROOT / csv_path).resolve()
    if not csv_path.is_file():
        raise SystemExit(f"Missing inventory CSV: {csv_path}")

    rows = [
        stamp_source_dataset(row)
        for row in select_rows(
            load_csv(csv_path),
            only=parse_only(args.only),
            datasets=parse_datasets(args.datasets),
            include_disabled=args.include_disabled,
            include_player=args.include_player,
        )
    ]

    if args.output_root is not None:
        output_root = args.output_root.expanduser()
        if not output_root.is_absolute():
            output_root = (ROOT / output_root).resolve()
    elif args.retry_failed:
        found = latest_docetl_root({row["workload_id"] for row in rows})
        if found is None:
            raise SystemExit(
                "No prior DocETL run found under case study/workloads/runs. "
                "Pass --output-root pointing at the previous .../docetl directory."
            )
        output_root = found
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_root = (WORKLOADS / "runs" / stamp / "docetl").resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    print(f"Output root: {output_root}", flush=True)
    print(
        "Workloads: " + ", ".join(row["workload_id"] for row in rows),
        flush=True,
    )

    records: list[dict[str, Any]] = []
    failed = False
    for row in rows:
        record = run_one(row, output_root=output_root, args=args)
        records.append(record)
        write_index(output_root, records)
        if record.get("status") == "failed":
            failed = True
            if not args.continue_on_error:
                break

    write_index(output_root, records)
    print(f"\nIndex: {output_root / 'run_index.json'}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
