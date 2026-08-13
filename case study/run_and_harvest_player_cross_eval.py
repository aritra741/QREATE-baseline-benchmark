#!/usr/bin/env python3
"""HPC one-shot: preflight sealed train DBs, run 12 transfer pairs, harvest the site.

The website stays pending until scores are written into the tracked file
``player-agg20-case-site/src/experiments-data.json``. Run artifacts under
``case study/workloads/runs/`` are gitignored, so this script also copies a
tracked ``cross_eval_index.csv`` next to that JSON.

On HPC, from the repo root after ``git pull`` and WDIRS venv activation:

  python3 "case study/run_and_harvest_player_cross_eval.py" --check
  python3 "case study/run_and_harvest_player_cross_eval.py" --run

If the 12 pairs already finished and you only need the site files:

  python3 "case study/run_and_harvest_player_cross_eval.py" --harvest-only

Then commit and push the tracked files this script prints, and ``git pull``
on the laptop.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = Path(__file__).resolve().parent
WDIRS = ROOT / "systems" / "WDIRS"
RUNNER = CASE / "run_player_contrast_cross_eval.py"
HARVEST = CASE / "harvest_player_experiments.py"
DEFAULT_OUTPUT = CASE / "workloads" / "runs" / "cross_eval_taxonomy25"
DEFAULT_QUWARTS = CASE / "workloads" / "runs" / "quwarts_forced_taxonomy_25pct_20260810"
DEFAULT_GROUPBY = CASE / "workloads" / "runs" / "quwarts_forced_taxonomy_25pct_20260809"
WORKLOADS = (
    "player_join20",
    "player_groupby20",
    "player_multiagg20",
    "player_filterjoin20",
)
TRACKED = (
    ROOT / "player-agg20-case-site" / "src" / "experiments-data.json",
    ROOT / "player-agg20-case-site" / "src" / "cross_eval_index.csv",
)


def _venv_python() -> Path | None:
    for name in ("python3", "python"):
        candidate = WDIRS / "venv" / "bin" / name
        if candidate.is_file():
            return candidate
    return None


def _ensure_venv() -> None:
    wanted = _venv_python()
    if wanted is None:
        return
    if Path(sys.executable).resolve() == wanted.resolve():
        return
    os.execv(str(wanted), [str(wanted), *sys.argv])


def _python() -> str:
    venv = _venv_python()
    return str(venv) if venv is not None else sys.executable


def _train_root(workload_id: str, *, quwarts_root: Path, groupby_root: Path) -> Path:
    return groupby_root if workload_id == "player_groupby20" else quwarts_root


def _result_dir(root: Path, workload_id: str) -> Path:
    return root / "results" / workload_id


def preflight(*, quwarts_root: Path, groupby_root: Path) -> list[str]:
    errors: list[str] = []
    for workload_id in WORKLOADS:
        root = _train_root(
            workload_id, quwarts_root=quwarts_root, groupby_root=groupby_root
        )
        result = _result_dir(root, workload_id)
        bundle = result / "serving_bundle"
        sealed = bundle / "SEALED"
        synthesis = result / "synthesis_manifest.json"
        print(f"  {workload_id}")
        print(f"    bundle={bundle}")
        if not sealed.is_file():
            errors.append(f"missing sealed bundle: {sealed}")
            print("    SEALED=MISSING")
        else:
            print("    SEALED=ok")
        if not synthesis.is_file():
            errors.append(f"missing synthesis manifest: {synthesis}")
            print("    synthesis_manifest.json=MISSING")
        else:
            print("    synthesis_manifest.json=ok")
    return errors


def _run(cmd: list[str]) -> int:
    print("+", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    _ensure_venv()
    parser = argparse.ArgumentParser(
        description="Preflight, run, and harvest Player cross-workload transfer."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="Verify sealed train databases exist; do not evaluate.",
    )
    mode.add_argument(
        "--run",
        action="store_true",
        help="Run all 12 train→test pairs, then harvest tracked site files.",
    )
    mode.add_argument(
        "--harvest-only",
        action="store_true",
        help="Harvest an existing cross_eval_* run into the website JSON.",
    )
    parser.add_argument("--quwarts-root", type=Path, default=DEFAULT_QUWARTS)
    parser.add_argument("--groupby-root", type=Path, default=DEFAULT_GROUPBY)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    quwarts_root = args.quwarts_root
    groupby_root = args.groupby_root
    output_root = args.output_root
    if not quwarts_root.is_absolute():
        quwarts_root = (ROOT / quwarts_root).resolve()
    if not groupby_root.is_absolute():
        groupby_root = (ROOT / groupby_root).resolve()
    if not output_root.is_absolute():
        output_root = (ROOT / output_root).resolve()

    print(f"repo={ROOT}")
    print(f"python={_python()}")
    if not args.harvest_only:
        print("train databases:")
        errors = preflight(quwarts_root=quwarts_root, groupby_root=groupby_root)
        if errors:
            print("\nPreflight failed:")
            for item in errors:
                print(f"  - {item}")
            return 1

    if args.check:
        print("\nPreflight ok. Next:\n"
              '  python3 "case study/run_and_harvest_player_cross_eval.py" --run')
        return 0

    if args.run:
        code = _run(
            [
                _python(),
                str(RUNNER),
                "--run",
                "--quwarts-root",
                str(quwarts_root),
                "--groupby-root",
                str(groupby_root),
                "--output-root",
                str(output_root),
            ]
        )
        if code != 0:
            print(
                "Cross-eval exited non-zero. Harvesting whatever pairs finished."
            )

    harvest_cmd = [_python(), str(HARVEST)]
    index = output_root / "cross_eval_index.csv"
    if index.is_file():
        harvest_cmd.extend(["--cross-index", str(index)])
    harvest_code = _run(harvest_cmd)

    print("\nTracked files to commit and pull on the laptop:")
    for path in TRACKED:
        status = "ok" if path.is_file() else "MISSING"
        print(f"  [{status}] {path.relative_to(ROOT)}")
    print(
        "\nOn HPC:\n"
        "  git add player-agg20-case-site/src/experiments-data.json "
        "player-agg20-case-site/src/cross_eval_index.csv\n"
        '  git commit -m "Harvest Player cross-workload transfer scores"\n'
        "  git push\n"
        "On the laptop:\n"
        "  git pull"
    )
    return harvest_code


if __name__ == "__main__":
    raise SystemExit(main())
