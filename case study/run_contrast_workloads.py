#!/usr/bin/env python3
"""Run QuWARTS sequentially on Art/CSPaper/Finan/Legal/Med/SEC contrast workloads.

Same isolation model as ``run_player_contrast_workloads.py``: each enabled CSV
row gets a fresh subprocess, output directory, and scratch/cache tree.

Finan and Med source documents live under ``source_data/Finance`` and
``source_data/Healthcare``. The runner maps those automatically; evaluation
still uses the CSV dataset name (Finan, Med).

Examples:
  python3 "case study/run_contrast_workloads.py" --dry-run
  python3 "case study/run_contrast_workloads.py" --run --datasets art,legal \\
      --token-budget 2000000 --model qwen2.5:7b-instruct
  python3 "case study/run_contrast_workloads.py" --run --only art_agg20,med_join20
  python3 "case study/run_contrast_workloads.py" --run --datasets med \\
      --budget-from-docetl --budget-fraction 0.25 --model qwen2.5:7b-instruct
"""

from __future__ import annotations

import argparse
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
    CASE as CASE_DIR,
    DEFAULT_CSV,
    ROOT,
    WORKLOADS,
    docetl_total_tokens,
    load_csv,
    parse_datasets,
    parse_only,
    quwarts_budget_from_docetl,
    rel,
    resolve_docetl_root,
    resolve_repo_path,
    select_rows,
    stamp_source_dataset,
)

WDIRS = ROOT / "systems" / "WDIRS"
RUNNER = WDIRS / "diagnostics" / "run_offline_spp.py"
EVALUATOR = WDIRS / "diagnostics" / "evaluate_native_spp_bundle.py"


def ensure_manifest(row: dict[str, str]) -> Path:
    sql_manifest = resolve_repo_path(row["sql_manifest"])
    if not sql_manifest.is_file():
        raise FileNotFoundError(
            f"missing SQL manifest for {row['workload_id']}: {sql_manifest}"
        )
    return sql_manifest


def prepare_isolated_dirs(
    output_root: Path,
    workload_id: str,
    *,
    force: bool,
) -> tuple[Path, Path]:
    safe_id = workload_id.replace("/", "_")
    output_dir = (output_root / "results" / safe_id).resolve()
    scratch_parent = (output_root / "scratch" / safe_id).resolve()

    if output_dir.exists():
        if any(output_dir.iterdir()):
            if not force:
                raise FileExistsError(
                    f"non-empty isolated output already exists: {output_dir}"
                )
            shutil.rmtree(output_dir)
        else:
            output_dir.rmdir()
    if scratch_parent.exists() and force:
        shutil.rmtree(scratch_parent)

    output_dir.mkdir(parents=True, exist_ok=False)
    scratch_parent.mkdir(parents=True, exist_ok=True)
    return output_dir, scratch_parent


def build_command(
    row: dict[str, str],
    *,
    sql_manifest: Path,
    output_dir: Path,
    scratch_parent: Path,
    args: argparse.Namespace,
) -> list[str]:
    command = [
        sys.executable,
        str(RUNNER),
        "--pipeline",
        "contract",
        "--intent-source",
        "sql-contract",
        "--dataset",
        str(row.get("source_dataset") or row.get("dataset")),
        "--workload",
        str(sql_manifest),
        "--output",
        str(output_dir),
        "--scratch-dir",
        str(scratch_parent),
        "--token-budget",
        str(row.get("token_budget") or args.token_budget),
        "--quality-floor",
        str(args.quality_floor),
        "--beta",
        str(args.beta),
        "--bulk-column-batch-size",
        str(args.bulk_column_batch_size),
        "--bulk-min-column-coverage",
        str(args.bulk_min_column_coverage),
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.base_url:
        command.extend(["--base-url", args.base_url])
    if args.seed is not None:
        command.extend(["--seed", str(args.seed)])
    if args.controlled_prefix:
        command.append("--controlled-prefix")
    if args.replay_root is not None:
        replay_root = args.replay_root.expanduser()
        if not replay_root.is_absolute():
            replay_root = (ROOT / replay_root).resolve()
        command.extend(
            [
                "--llm-replay-path",
                str(
                    replay_root
                    / "results"
                    / row["workload_id"]
                    / "llm_response_cache.jsonl"
                ),
            ]
        )
    if args.intent_only:
        command.append("--intent-only")
    if args.max_documents_per_entity is not None:
        command.extend(
            [
                "--max-documents-per-entity",
                str(args.max_documents_per_entity),
                "--max-document-characters",
                str(args.max_document_characters),
            ]
        )
    return command


def evaluate_command(
    row: dict[str, str],
    *,
    sql_manifest: Path,
    output_dir: Path,
) -> list[str]:
    return [
        sys.executable,
        str(EVALUATOR),
        "--bundle",
        str(output_dir / "serving_bundle"),
        "--reference-workload",
        str(sql_manifest),
        "--dataset",
        str(row.get("dataset") or ""),
        "--output",
        str(output_dir / "evaluation.json"),
    ]


def isolated_env(
    scratch_parent: Path,
    *,
    controlled_prefix: bool = False,
) -> dict[str, str]:
    env = os.environ.copy()
    cache_root = scratch_parent / "local_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    env["PYTHONPATH"] = str(WDIRS)
    hf_home = env.get("HF_HOME") or str(cache_root / "hf")
    env["HF_HOME"] = hf_home
    env["HUGGINGFACE_HUB_CACHE"] = str(Path(hf_home) / "hub")
    env.pop("TRANSFORMERS_CACHE", None)
    env.pop("SENTENCE_TRANSFORMERS_HOME", None)
    env["XDG_CACHE_HOME"] = str(cache_root / "xdg")
    env["TMPDIR"] = str(cache_root / "tmp")
    env["TMP"] = env["TMPDIR"]
    env["TEMP"] = env["TMPDIR"]
    if controlled_prefix:
        env["MAX_PARALLEL_REQUESTS"] = "1"
        env["SPP_CONTRACT_MAX_WORKERS"] = "1"
        env["SPP_INTENT_MAX_WORKERS"] = "1"
        env["SPP_APPEND_ONLY_EVIDENCE"] = "1"
        env["SPP_CONTROLLED_PREFIX"] = "1"
    (cache_root / "tmp").mkdir(parents=True, exist_ok=True)
    return env


def run_one(
    row: dict[str, str],
    *,
    output_root: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    workload_id = row["workload_id"]
    sql_manifest = ensure_manifest(row)
    started = time.monotonic()
    record: dict[str, Any] = {
        "workload_id": workload_id,
        "kind": row.get("kind", ""),
        "dataset": row.get("dataset", ""),
        "source_dataset": row.get("source_dataset", ""),
        "sql_manifest": rel(sql_manifest),
        "n_queries": row.get("n_queries", ""),
        "token_budget": int(row.get("token_budget") or args.token_budget),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }
    if row.get("docetl_tokens"):
        record["docetl_tokens"] = int(row["docetl_tokens"])
        record["budget_fraction"] = float(row.get("budget_fraction") or 0)

    try:
        output_dir, scratch_parent = prepare_isolated_dirs(
            output_root,
            workload_id,
            force=args.force,
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

    command = build_command(
        row,
        sql_manifest=sql_manifest,
        output_dir=output_dir,
        scratch_parent=scratch_parent,
        args=args,
    )
    record["output_dir"] = rel(output_dir)
    record["scratch_dir"] = rel(scratch_parent)
    record["command"] = command

    if args.dry_run:
        record.update(
            {
                "status": "dry_run",
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "wall_clock_seconds": round(time.monotonic() - started, 3),
            }
        )
        return record

    log_path = output_root / "logs" / f"{workload_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = isolated_env(
        scratch_parent,
        controlled_prefix=args.controlled_prefix,
    )
    print(f"\n=== {workload_id} ({row.get('dataset')} → {row.get('source_dataset')}) ===", flush=True)
    print(" ".join(command), flush=True)
    with log_path.open("w", encoding="utf-8") as log_handle:
        log_handle.write("COMMAND:\n" + " ".join(command) + "\n\n")
        log_handle.flush()
        completed = subprocess.run(
            command,
            cwd=str(WDIRS),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    record["log_path"] = rel(log_path)
    record["exit_code"] = completed.returncode
    record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    record["wall_clock_seconds"] = round(time.monotonic() - started, 3)
    record["status"] = "ok" if completed.returncode == 0 else "failed"
    if (
        completed.returncode == 0
        and not args.dry_run
        and not args.skip_eval
        and (output_dir / "serving_bundle" / "SEALED").is_file()
    ):
        eval_cmd = evaluate_command(
            row,
            sql_manifest=sql_manifest,
            output_dir=output_dir,
        )
        record["eval_command"] = eval_cmd
        print(" ".join(eval_cmd), flush=True)
        with log_path.open("a", encoding="utf-8") as log_handle:
            log_handle.write("\n\nEVAL COMMAND:\n" + " ".join(eval_cmd) + "\n\n")
            log_handle.flush()
            evaluated = subprocess.run(
                eval_cmd,
                cwd=str(WDIRS),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
        record["eval_exit_code"] = evaluated.returncode
        eval_output = output_dir / "evaluation.json"
        if evaluated.returncode == 0 and eval_output.is_file():
            try:
                report = json.loads(eval_output.read_text(encoding="utf-8"))
                record["evaluation"] = {
                    "mean_official_accuracy": report.get("mean_official_accuracy"),
                    "mean_structure_score": report.get("mean_structure_score"),
                    "mean_query_score": report.get("mean_query_score"),
                    "construction_tokens": report.get("construction_tokens"),
                    "total_token_budget": report.get("total_token_budget"),
                    "output": rel(eval_output),
                }
                print(json.dumps(record["evaluation"], indent=2), flush=True)
            except json.JSONDecodeError:
                record["status"] = "eval_failed"
                record["exit_code"] = 1
        else:
            record["status"] = "eval_failed"
            record["exit_code"] = evaluated.returncode or 1
    if completed.returncode != 0:
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

    manifest = output_dir / "run_manifest.json"
    if manifest.exists():
        try:
            summary = json.loads(manifest.read_text(encoding="utf-8"))
            record["selected_config_ids"] = summary.get("selected_config_ids")
            record["candidate_count"] = summary.get("candidate_count")
            record["tokens"] = summary.get("tokens")
            record["serving_manifest"] = summary.get("serving_manifest")
        except json.JSONDecodeError:
            pass
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
        "token_budget",
        "docetl_tokens",
        "output_dir",
        "scratch_dir",
        "log_path",
        "wall_clock_seconds",
        "error",
    ]
    import csv

    with index_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Workload inventory CSV (default: {DEFAULT_CSV})",
    )
    parser.add_argument(
        "--write-csv",
        action="store_true",
        help="Refresh contrast_workloads.csv from on-disk manifests and exit.",
    )
    parser.add_argument("--run", action="store_true")
    parser.add_argument(
        "--regenerate-workloads",
        action="store_true",
        help="Rebuild pure contrast packs and mixtures before running.",
    )
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated workload ids (ignores enabled flag).",
    )
    parser.add_argument(
        "--datasets",
        default="",
        help="Comma-separated eval dataset names, e.g. art,legal,med.",
    )
    parser.add_argument(
        "--include-player",
        action="store_true",
        help="Also include Player rows from the unified inventory CSV.",
    )
    parser.add_argument("--include-disabled", action="store_true")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Batch root. Default: case study/workloads/runs/<utc_timestamp>/",
    )
    parser.add_argument(
        "--source-dataset",
        default="",
        help="Override source_data directory for every selected row.",
    )
    parser.add_argument("--token-budget", type=int, default=2_000_000)
    parser.add_argument(
        "--budget-from-docetl",
        action="store_true",
        help=(
            "Set each workload's QuWARTS token budget to a fraction of that "
            "pack's DocETL total_tokens."
        ),
    )
    parser.add_argument(
        "--docetl-root",
        type=Path,
        default=None,
        help=(
            "DocETL batch root (.../docetl or .../<stamp>). "
            "Default with --budget-from-docetl: latest run covering the "
            "selected workloads."
        ),
    )
    parser.add_argument(
        "--budget-fraction",
        type=float,
        default=None,
        help=(
            "Fraction of each pack's DocETL tokens to give QuWARTS. "
            "Default: 0.25 with --budget-from-docetl."
        ),
    )
    parser.add_argument("--quality-floor", type=float, default=0.0)
    parser.add_argument("--beta", type=float, default=1.0)
    parser.add_argument("--model", default="qwen2.5:7b-instruct")
    parser.add_argument("--base-url")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--controlled-prefix", action="store_true")
    parser.add_argument("--replay-root", type=Path, default=None)
    parser.add_argument("--bulk-column-batch-size", type=int, default=10)
    parser.add_argument("--bulk-min-column-coverage", type=float, default=0.0)
    parser.add_argument("--intent-only", action="store_true")
    parser.add_argument("--max-documents-per-entity", type=int, default=None)
    parser.add_argument("--max-document-characters", type=int, default=8000)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def maybe_regenerate() -> None:
    build = CASE_DIR / "build_contrast_workloads.py"
    mix = CASE_DIR / "mix_contrast_workloads.py"
    subprocess.run([sys.executable, str(build)], cwd=str(ROOT), check=True)
    subprocess.run([sys.executable, str(mix)], cwd=str(ROOT), check=True)


def refresh_inventory(csv_path: Path) -> Path:
    sys.path.insert(0, str(CASE_DIR))
    from mix_contrast_workloads import write_inventory

    written = write_inventory()
    if csv_path.resolve() != written.resolve():
        shutil.copy2(written, csv_path)
    return csv_path


def main() -> int:
    args = parse_args()
    if args.controlled_prefix and args.seed is None:
        raise SystemExit("--controlled-prefix requires --seed")
    if args.regenerate_workloads:
        maybe_regenerate()

    csv_path = args.csv.expanduser()
    if not csv_path.is_absolute():
        csv_path = (ROOT / csv_path).resolve()

    if args.write_csv or not csv_path.exists():
        refresh_inventory(csv_path)
        print(f"wrote {csv_path}")
        if args.write_csv and not (
            args.run or args.dry_run or args.only or args.output_root is not None
        ):
            return 0

    if not (
        args.run or args.dry_run or args.only or args.output_root is not None
    ):
        raise SystemExit(
            "Nothing to do. Pass --run (or --dry-run / --only / --output-root), "
            "or use --write-csv to refresh the inventory."
        )

    selected = [
        stamp_source_dataset(row, args.source_dataset or None)
        for row in select_rows(
            load_csv(csv_path),
            only=parse_only(args.only),
            datasets=parse_datasets(args.datasets),
            include_disabled=args.include_disabled,
            include_player=args.include_player,
        )
    ]

    use_docetl_budget = (
        args.budget_from_docetl
        or args.docetl_root is not None
        or args.budget_fraction is not None
    )
    budget_plan: dict[str, Any] | None = None
    if use_docetl_budget:
        fraction = (
            0.25 if args.budget_fraction is None else float(args.budget_fraction)
        )
        if not 0 < fraction <= 1:
            raise SystemExit("--budget-fraction must be in (0, 1]")
        docetl_root = resolve_docetl_root(
            args.docetl_root,
            {row["workload_id"] for row in selected},
        )
        missing: list[str] = []
        planned: dict[str, dict[str, Any]] = {}
        for row in selected:
            tokens = docetl_total_tokens(docetl_root, row["workload_id"])
            if tokens is None:
                missing.append(row["workload_id"])
                continue
            budget = quwarts_budget_from_docetl(tokens, fraction)
            row["docetl_tokens"] = str(tokens)
            row["token_budget"] = str(budget)
            row["budget_fraction"] = str(fraction)
            planned[row["workload_id"]] = {
                "docetl_tokens": tokens,
                "token_budget": budget,
                "budget_fraction": fraction,
            }
            print(
                f"{row['workload_id']}: DocETL {tokens} tokens → "
                f"QuWARTS budget {budget} ({fraction:.0%})",
                flush=True,
            )
        if missing:
            raise SystemExit(
                "No DocETL total_tokens for: "
                + ", ".join(missing)
                + f" under {docetl_root}"
            )
        budget_plan = {
            "docetl_root": rel(docetl_root),
            "budget_fraction": fraction,
            "workloads": planned,
        }
    else:
        for row in selected:
            row["token_budget"] = str(args.token_budget)

    if args.output_root is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_root = WORKLOADS / "runs" / stamp
    else:
        output_root = args.output_root.expanduser()
        if not output_root.is_absolute():
            output_root = (ROOT / output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    batch_manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "csv": rel(csv_path),
        "intent_source": "sql-contract",
        "pipeline": "contract",
        "selected_workload_ids": [row["workload_id"] for row in selected],
        "datasets": sorted({row["dataset"] for row in selected}),
        "source_datasets": sorted({row["source_dataset"] for row in selected}),
        "token_budget": args.token_budget,
        "budget_from_docetl": use_docetl_budget,
        "budget_plan": budget_plan,
        "model": args.model,
        "base_url": args.base_url,
        "seed": args.seed,
        "controlled_prefix": args.controlled_prefix,
        "replay_root": (
            str(args.replay_root) if args.replay_root is not None else None
        ),
        "intent_only": args.intent_only,
        "dry_run": args.dry_run,
    }
    (output_root / "batch_manifest.json").write_text(
        json.dumps(batch_manifest, indent=2, default=str),
        encoding="utf-8",
    )
    if budget_plan is not None:
        (output_root / "budget_plan.json").write_text(
            json.dumps(budget_plan, indent=2, default=str),
            encoding="utf-8",
        )
    import csv

    with (output_root / "workloads_used.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(selected[0].keys()))
        writer.writeheader()
        writer.writerows(selected)

    records: list[dict[str, Any]] = []
    failures = 0
    for row in selected:
        record = run_one(row, output_root=output_root, args=args)
        records.append(record)
        write_index(output_root, records)
        print(
            f"[{record['status']}] {record['workload_id']}"
            + (
                f" exit={record.get('exit_code')}"
                if record.get("exit_code") is not None
                else ""
            ),
            flush=True,
        )
        if record["status"] in {"failed", "eval_failed"}:
            failures += 1
            if not args.continue_on_error:
                break

    write_index(output_root, records)
    print(f"\nBatch complete under {output_root}")
    print(f"Index: {output_root / 'run_index.csv'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
