#!/usr/bin/env python3
"""Refresh the case-study experiments page from known results plus HPC overlays.

Looks for optional artifacts, in order:
  - --cross-index
  - latest case study/workloads/runs/cross_eval_*/cross_eval_index.csv
  - player-agg20-case-site/src/cross_eval_index.csv
  - pair evaluation.json files under any cross_eval_* run
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
SITE_JSON = ROOT / "player-agg20-case-site" / "src" / "experiments-data.json"
SITE_INDEX = ROOT / "player-agg20-case-site" / "src" / "cross_eval_index.csv"
RUNS = CASE / "workloads" / "runs"
WORKLOADS = (
    "player_join20",
    "player_groupby20",
    "player_multiagg20",
    "player_filterjoin20",
)
INDEX_FIELDS = (
    "train_workload",
    "test_workload",
    "mean_official_accuracy",
    "mean_structure_score",
    "mean_query_score_0.2",
    "compiled_ok_count",
    "query_count",
    "construction_tokens",
    "evaluation_json",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_index(path: Path, pairs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(INDEX_FIELDS))
        writer.writeheader()
        for pair in pairs:
            writer.writerow(
                {
                    "train_workload": pair.get("train"),
                    "test_workload": pair.get("test"),
                    "mean_official_accuracy": pair.get("accuracy"),
                    "mean_structure_score": pair.get("structure"),
                    "mean_query_score_0.2": pair.get("query_score"),
                    "compiled_ok_count": pair.get("compiled_ok_count"),
                    "query_count": pair.get("query_count"),
                    "construction_tokens": pair.get("construction_tokens"),
                    "evaluation_json": pair.get("evaluation_json") or pair.get("source"),
                }
            )


def _pair_key(train: str, test: str) -> str:
    return f"{train}:{test}"


def _is_transfer_pair(train: str, test: str) -> bool:
    return train in WORKLOADS and test in WORKLOADS and train != test


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def _pair_from_csv_row(row: dict[str, str], source: Path) -> dict[str, Any] | None:
    train = (row.get("train_workload") or "").strip()
    test = (row.get("test_workload") or "").strip()
    if not _is_transfer_pair(train, test):
        return None
    return {
        "train": train,
        "test": test,
        "accuracy": _float_or_none(row.get("mean_official_accuracy")),
        "structure": _float_or_none(row.get("mean_structure_score")),
        "query_score": _float_or_none(row.get("mean_query_score_0.2")),
        "compiled_ok_count": _int_or_none(row.get("compiled_ok_count")),
        "query_count": _int_or_none(row.get("query_count")),
        "construction_tokens": _int_or_none(row.get("construction_tokens")),
        "evaluation_json": (row.get("evaluation_json") or "").strip(),
        "source": str(source),
    }


def _pair_from_eval(path: Path) -> dict[str, Any] | None:
    payload = _read_json(path)
    train = str(payload.get("train_workload") or "")
    test = str(payload.get("test_workload") or "")
    if not train or not test:
        parts = path.parent.parts
        train = next((part[6:] for part in parts if part.startswith("train=")), train)
        test = next((part[5:] for part in parts if part.startswith("test=")), test)
    if not _is_transfer_pair(train, test):
        return None
    query_score = payload.get("mean_query_score") or {}
    if isinstance(query_score, dict):
        query_score = query_score.get("0.2")
    return {
        "train": train,
        "test": test,
        "accuracy": _float_or_none(payload.get("mean_official_accuracy")),
        "structure": _float_or_none(payload.get("mean_structure_score")),
        "query_score": _float_or_none(query_score),
        "compiled_ok_count": _int_or_none(payload.get("compiled_ok_count")),
        "query_count": _int_or_none(payload.get("query_count")),
        "construction_tokens": _int_or_none(payload.get("construction_tokens")),
        "evaluation_json": str(path),
        "source": str(path),
    }


def _load_cross_pairs(path: Path) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            pair = _pair_from_csv_row(row, path)
            if pair is not None:
                pairs.append(pair)
    return pairs


def _discover_index_csvs() -> list[Path]:
    hits = sorted(RUNS.glob("cross_eval_*/cross_eval_index.csv"), key=lambda p: p.stat().st_mtime)
    if SITE_INDEX.is_file():
        hits.append(SITE_INDEX)
    return hits


def _discover_eval_jsons() -> list[Path]:
    return sorted(
        RUNS.glob("cross_eval_*/train=*/test=*/evaluation.json"),
        key=lambda p: p.stat().st_mtime,
    )


def collect_pairs(explicit: Path | None) -> tuple[list[dict[str, Any]], list[str]]:
    merged: dict[str, dict[str, Any]] = {}
    sources: list[str] = []

    def absorb(pairs: list[dict[str, Any]], source: Path) -> None:
        if not pairs:
            return
        sources.append(str(source))
        for pair in pairs:
            merged[_pair_key(pair["train"], pair["test"])] = pair

    if explicit is not None and explicit.is_file():
        absorb(_load_cross_pairs(explicit), explicit)
    for csv_path in _discover_index_csvs():
        absorb(_load_cross_pairs(csv_path), csv_path)
    for eval_path in _discover_eval_jsons():
        pair = _pair_from_eval(eval_path)
        if pair is not None:
            absorb([pair], eval_path)

    ordered = [
        merged[_pair_key(train, test)]
        for train in WORKLOADS
        for test in WORKLOADS
        if train != test and _pair_key(train, test) in merged
    ]
    return ordered, sources


def harvest(output: Path, explicit_index: Path | None) -> int:
    payload = _read_json(output if output.is_file() else SITE_JSON)
    payload.pop("uncontrolled_50pct", None)
    payload.pop("controlled_filterjoin", None)
    payload.pop("filterjoin_per_query", None)
    pairs, sources = collect_pairs(explicit_index)
    payload.setdefault("cross_eval", {})
    payload["cross_eval"]["pairs"] = pairs
    payload["cross_eval"]["pair_count"] = 12
    if pairs:
        payload["cross_eval"]["status"] = (
            f"Harvested {len(pairs)} of 12 transfer pairs."
        )
        payload["cross_eval"]["source"] = sources[-1] if sources else ""
        _write_index(SITE_INDEX, pairs)
    else:
        payload["cross_eval"]["status"] = (
            "No cross_eval_index.csv or pair evaluation.json found. "
            'Run python3 "case study/run_and_harvest_player_cross_eval.py" --run on HPC.'
        )
        payload["cross_eval"].pop("source", None)
    if len(pairs) >= 12:
        payload["remaining"] = []
    else:
        missing = 12 - len(pairs)
        payload["remaining"] = [
            f"Finish and harvest the remaining {missing} cross-workload transfer pairs "
            'with python3 "case study/run_and_harvest_player_cross_eval.py".'
        ]
    payload["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    if pairs:
        print(f"Harvested {len(pairs)} transfer pairs")
        print(f"Tracked index: {SITE_INDEX}")
        for source in sources:
            print(f"  source: {source}")
    else:
        print("No cross-eval artifacts found; off-diagonal cells stay pending.")
    return 0 if len(pairs) >= 12 else (0 if pairs else 2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=SITE_JSON)
    parser.add_argument("--cross-index", type=Path, default=None)
    args = parser.parse_args()
    output = args.output
    if not output.is_absolute():
        output = (ROOT / output).resolve()
    explicit = args.cross_index
    if explicit is not None and not explicit.is_absolute():
        explicit = (ROOT / explicit).resolve()
    return harvest(output, explicit)


if __name__ == "__main__":
    raise SystemExit(main())
