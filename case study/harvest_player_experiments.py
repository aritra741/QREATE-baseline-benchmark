#!/usr/bin/env python3
"""Refresh the case-study experiments page from known results plus HPC overlays.

Looks for optional artifacts:
  - latest case study/workloads/runs/cross_eval_*/cross_eval_index.csv
and merges them into player-agg20-case-site/src/experiments-data.json
without dropping the curated timeline.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE = Path(__file__).resolve().parent
SITE = ROOT / "player-agg20-case-site" / "src" / "experiments-data.json"
RUNS = CASE / "workloads" / "runs"
WORKLOADS = (
    "player_join20",
    "player_groupby20",
    "player_multiagg20",
    "player_filterjoin20",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_cross_index() -> Path | None:
    hits = sorted(RUNS.glob("cross_eval_*/cross_eval_index.csv"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def _load_cross_pairs(path: Path) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            train = row.get("train_workload") or ""
            test = row.get("test_workload") or ""
            if train not in WORKLOADS or test not in WORKLOADS or train == test:
                continue
            acc = row.get("mean_official_accuracy")
            structure = row.get("mean_structure_score")
            query_score = row.get("mean_query_score_0.2")
            compiled = row.get("compiled_ok_count")
            pairs.append(
                {
                    "train": train,
                    "test": test,
                    "accuracy": None if acc in (None, "") else float(acc),
                    "structure": None if structure in (None, "") else float(structure),
                    "query_score": None if query_score in (None, "") else float(query_score),
                    "compiled_ok_count": None if compiled in (None, "") else int(float(compiled)),
                    "source": str(path),
                }
            )
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=SITE)
    parser.add_argument("--cross-index", type=Path, default=None)
    args = parser.parse_args()
    output = args.output
    if not output.is_absolute():
        output = (ROOT / output).resolve()
    payload = _read_json(output if output.is_file() else SITE)
    payload.pop("uncontrolled_50pct", None)
    payload.pop("controlled_filterjoin", None)
    payload.pop("filterjoin_per_query", None)
    cross_index = args.cross_index or _latest_cross_index()
    if cross_index is not None and not cross_index.is_absolute():
        cross_index = (ROOT / cross_index).resolve()
    if cross_index is not None and cross_index.is_file():
        pairs = _load_cross_pairs(cross_index)
        payload.setdefault("cross_eval", {})["pairs"] = pairs
        payload["cross_eval"]["status"] = (
            f"Harvested {len(pairs)} transfer pairs from {cross_index}."
        )
        payload["cross_eval"]["source"] = str(cross_index)
    payload["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    if cross_index is not None and cross_index.is_file():
        print(f"Cross-eval overlay: {cross_index}")
    else:
        print("No cross_eval_index.csv found; diagonal-only matrix kept.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
