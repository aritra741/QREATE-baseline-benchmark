#!/usr/bin/env python3
"""Run QuWARTS sequentially on Player contrast workloads with hard isolation.

Each enabled CSV row is executed in a fresh subprocess with:
  - its own output directory
  - its own scratch / intent-cache / backend SQLite parent
  - no reuse of another workload's materialized database or selected configs

Examples:
  python3 "case study/run_player_contrast_workloads.py" --write-csv
  python3 "case study/run_player_contrast_workloads.py" --dry-run
  python3 "case study/run_player_contrast_workloads.py" --run \\
      --token-budget 2000000 --model qwen2.5:72b
  python3 "case study/run_player_contrast_workloads.py" --run \\
      --only player_join20,player_groupby20 --token-budget 2000000
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

ROOT = Path(__file__).resolve().parents[1]
CASE = Path(__file__).resolve().parent
WORKLOADS = CASE / "workloads"
DEFAULT_CSV = WORKLOADS / "player_contrast_workloads.csv"
WDIRS = ROOT / "systems" / "WDIRS"
RUNNER = WDIRS / "diagnostics" / "run_offline_spp.py"

CSV_FIELDS = [
    "workload_id",
    "kind",
    "focus",
    "n_queries",
    "sql_manifest",
    "nl_manifest",
    "dataset",
    "enabled",
    "notes",
]


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def discover_rows() -> list[dict[str, str]]:
    """Build the workload inventory from on-disk manifests."""

    rows: list[dict[str, str]] = []
    baseline = CASE / "docetl_Player_v7"
    if (baseline / "query_manifest.json").exists():
        sql = json.loads((baseline / "query_manifest.json").read_text())
        rows.append(
            {
                "workload_id": "player_agg20",
                "kind": "baseline",
                "focus": "single-table aggregations",
                "n_queries": str(len(sql)),
                "sql_manifest": _rel(baseline / "query_manifest.json"),
                "nl_manifest": _rel(baseline / "query_manifest_nl.json"),
                "dataset": "Player",
                "enabled": "1",
                "notes": "original case-study workload",
            }
        )

    pure = [
        ("player_join20", "join depth 1-3"),
        ("player_groupby20", "GROUP BY variety"),
        ("player_multiagg20", "multiple aggregates + HAVING"),
        ("player_filterjoin20", "selective filters with light joins"),
    ]
    for workload_id, focus in pure:
        directory = WORKLOADS / workload_id
        sql_path = directory / "query_manifest.json"
        if not sql_path.exists():
            continue
        sql = json.loads(sql_path.read_text())
        rows.append(
            {
                "workload_id": workload_id,
                "kind": "pure",
                "focus": focus,
                "n_queries": str(len(sql)),
                "sql_manifest": _rel(sql_path),
                "nl_manifest": _rel(directory / "query_manifest_nl.json"),
                "dataset": "Player",
                "enabled": "1",
                "notes": "",
            }
        )

    mixtures = WORKLOADS / "mixtures"
    if mixtures.is_dir():
        for directory in sorted(mixtures.iterdir()):
            sql_path = directory / "query_manifest.json"
            if not directory.is_dir() or not sql_path.exists():
                continue
            sql = json.loads(sql_path.read_text())
            meta_path = directory / "meta.json"
            meta = (
                json.loads(meta_path.read_text())
                if meta_path.exists()
                else {}
            )
            rows.append(
                {
                    "workload_id": directory.name,
                    "kind": "mixture",
                    "focus": str(meta.get("title") or directory.name),
                    "n_queries": str(len(sql)),
                    "sql_manifest": _rel(sql_path),
                    "nl_manifest": _rel(directory / "query_manifest_nl.json"),
                    "dataset": "Player",
                    "enabled": "0",
                    "notes": "disabled by default; set enabled=1 to include",
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, str]] | None = None) -> Path:
    rows = rows if rows is not None else discover_rows()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
    return path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def select_rows(
    rows: list[dict[str, str]],
    *,
    only: set[str] | None,
    include_disabled: bool,
) -> list[dict[str, str]]:
    selected = []
    for row in rows:
        workload_id = str(row["workload_id"]).strip()
        if only is not None and workload_id not in only:
            continue
        if only is None and not include_disabled and not _truthy(row.get("enabled")):
            continue
        selected.append(row)
    if only is not None:
        missing = sorted(only - {str(row["workload_id"]) for row in selected})
        if missing:
            raise SystemExit(f"unknown or unavailable workload ids: {missing}")
    if not selected:
        raise SystemExit("no workloads selected")
    return selected


def ensure_manifests(row: dict[str, str]) -> Path:
    sql_manifest = (ROOT / row["sql_manifest"]).resolve()
    if not sql_manifest.exists():
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
    """Create per-workload output and scratch parents; never share them."""

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
        str(row.get("dataset") or args.dataset),
        "--workload",
        str(sql_manifest),
        "--output",
        str(output_dir),
        "--scratch-dir",
        str(scratch_parent),
        "--token-budget",
        str(args.token_budget),
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


def isolated_env(
    scratch_parent: Path,
    *,
    controlled_prefix: bool = False,
) -> dict[str, str]:
    """Clone the process environment with per-workload local caches."""

    env = os.environ.copy()
    cache_root = scratch_parent / "local_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    env["PYTHONPATH"] = str(WDIRS)
    # Keep HF / sentence-transformers / QuWARTS caches from colliding across
    # workloads while still allowing model-weight reuse under the run root.
    env["HF_HOME"] = str(cache_root / "hf")
    env["TRANSFORMERS_CACHE"] = str(cache_root / "transformers")
    env["SENTENCE_TRANSFORMERS_HOME"] = str(cache_root / "sentence_transformers")
    env["XDG_CACHE_HOME"] = str(cache_root / "xdg")
    env["TMPDIR"] = str(cache_root / "tmp")
    env["TMP"] = env["TMPDIR"]
    env["TEMP"] = env["TMPDIR"]
    if controlled_prefix:
        # A single dispatch lane makes the affordable call prefix independent
        # of completion timing. Per-call seeds make each shared call identical.
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
    sql_manifest = ensure_manifests(row)
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    record: dict[str, Any] = {
        "workload_id": workload_id,
        "kind": row.get("kind", ""),
        "dataset": row.get("dataset") or args.dataset,
        "sql_manifest": _rel(sql_manifest),
        "n_queries": row.get("n_queries", ""),
        "started_at_utc": started_at,
        "status": "pending",
    }

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
    record["output_dir"] = _rel(output_dir)
    record["scratch_dir"] = _rel(scratch_parent)
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
    print(f"\n=== {workload_id} ===", flush=True)
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
    record["log_path"] = _rel(log_path)
    record["exit_code"] = completed.returncode
    record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    record["wall_clock_seconds"] = round(time.monotonic() - started, 3)
    record["status"] = "ok" if completed.returncode == 0 else "failed"
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
        "output_dir",
        "scratch_dir",
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
    parser = argparse.ArgumentParser(
        description=(
            "Sequentially run QuWARTS on Player contrast workloads with "
            "hard per-workload isolation."
        )
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Workload inventory CSV (default: {DEFAULT_CSV})",
    )
    parser.add_argument(
        "--write-csv",
        action="store_true",
        help="Refresh the inventory CSV from on-disk manifests and exit.",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Actually run QuWARTS after optional CSV refresh / regeneration.",
    )
    parser.add_argument(
        "--regenerate-workloads",
        action="store_true",
        help="Rebuild pure workloads (and mixtures) before running.",
    )
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated workload ids to run (ignores enabled flag).",
    )
    parser.add_argument(
        "--include-disabled",
        action="store_true",
        help="Also run CSV rows with enabled=0 when --only is not set.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help=(
            "Root directory for this batch. Defaults to "
            "case study/workloads/runs/<utc_timestamp>/."
        ),
    )
    parser.add_argument("--dataset", default="Player")
    parser.add_argument("--token-budget", type=int, default=2_000_000)
    parser.add_argument("--quality-floor", type=float, default=0.0)
    parser.add_argument("--beta", type=float, default=1.0)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional inference seed for reproducible fresh runs.",
    )
    parser.add_argument(
        "--controlled-prefix",
        action="store_true",
        help=(
            "Run a serial, call-key-seeded, append-only extraction protocol "
            "for paired budget comparisons (requires --seed)."
        ),
    )
    parser.add_argument(
        "--replay-root",
        type=Path,
        default=None,
        help=(
            "Prior controlled run root whose per-workload LLM response caches "
            "should be replayed before making new calls."
        ),
    )
    parser.add_argument("--bulk-column-batch-size", type=int, default=10)
    parser.add_argument("--bulk-min-column-coverage", type=float, default=0.0)
    parser.add_argument("--intent-only", action="store_true")
    parser.add_argument("--max-documents-per-entity", type=int, default=None)
    parser.add_argument("--max-document-characters", type=int, default=8000)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete an existing per-workload result/scratch dir before running.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep going after a failed workload instead of stopping.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print isolated commands without invoking QuWARTS.",
    )
    return parser.parse_args()


def maybe_regenerate() -> None:
    build = CASE / "build_player_contrast_workloads.py"
    mix = CASE / "mix_player_workloads.py"
    subprocess.run([sys.executable, str(build)], cwd=str(ROOT), check=True)
    subprocess.run([sys.executable, str(mix)], cwd=str(ROOT), check=True)


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
        write_csv(csv_path)
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

    rows = read_csv(csv_path)
    only = (
        {part.strip() for part in args.only.split(",") if part.strip()}
        if args.only.strip()
        else None
    )
    selected = select_rows(
        rows,
        only=only,
        include_disabled=args.include_disabled,
    )

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
        "csv": _rel(csv_path),
        "dataset_default": args.dataset,
        "intent_source": "sql-contract",
        "pipeline": "contract",
        "isolation": {
            "fresh_subprocess_per_workload": True,
            "separate_output_dir": True,
            "separate_scratch_dir": True,
            "separate_local_model_caches": True,
            "shared_selected_configs": False,
            "shared_materialized_databases": False,
        },
        "selected_workload_ids": [row["workload_id"] for row in selected],
        "token_budget": args.token_budget,
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
    # Keep a copy of the exact inventory used for this batch.
    write_csv(output_root / "workloads_used.csv", selected)

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
        if record["status"] == "failed":
            failures += 1
            if not args.continue_on_error:
                break

    write_index(output_root, records)
    print(f"\nBatch complete under {output_root}")
    print(f"Index: {output_root / 'run_index.csv'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
