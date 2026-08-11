#!/usr/bin/env python3
"""Stage scattered DocETL contrast result dirs into one harvestable root.

DocETL contrast evaluations live under different timestamped run folders.
This copies each workload's evaluation.json, query_tables/, summary.json, and
token/cost sidecars into:

  case study/workloads/runs/docetl_contrast_staged/results/<workload_id>/
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

CASE = Path(__file__).resolve().parent
DEFAULT_SOURCES = {
    "player_join20": CASE
    / "workloads"
    / "runs"
    / "20260808T222754Z"
    / "docetl"
    / "results"
    / "player_join20",
    "player_groupby20": CASE
    / "workloads"
    / "runs"
    / "20260809T002918Z"
    / "docetl"
    / "results"
    / "player_groupby20",
    "player_multiagg20": CASE
    / "workloads"
    / "runs"
    / "20260809T024938Z"
    / "docetl"
    / "results"
    / "player_multiagg20",
    "player_filterjoin20": CASE
    / "workloads"
    / "runs"
    / "20260809T024938Z"
    / "docetl"
    / "results"
    / "player_filterjoin20",
}
COPY_NAMES = (
    "evaluation.json",
    "summary.json",
    "query_results.json",
    "session_token_cost.json",
    "query_manifest.json",
    "query_manifest_nl.json",
)


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def stage(sources: dict[str, Path], dest_root: Path) -> None:
    results = dest_root / "results"
    results.mkdir(parents=True, exist_ok=True)
    for workload_id, source in sources.items():
        if not source.is_dir():
            raise SystemExit(f"missing DocETL result dir: {source}")
        evaluation = source / "evaluation.json"
        tables = source / "query_tables"
        if not evaluation.is_file():
            raise SystemExit(f"missing evaluation.json: {evaluation}")
        if not tables.is_dir():
            raise SystemExit(f"missing query_tables/: {tables}")
        target = results / workload_id
        target.mkdir(parents=True, exist_ok=True)
        for name in COPY_NAMES:
            path = source / name
            if path.is_file():
                shutil.copy2(path, target / name)
        _copy_tree(tables, target / "query_tables")
        print(f"staged {workload_id} <- {source}")
    print(f"\nDocETL stage root: {dest_root}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dest",
        type=Path,
        default=CASE / "workloads" / "runs" / "docetl_contrast_staged",
    )
    args = parser.parse_args()
    stage(DEFAULT_SOURCES, args.dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
