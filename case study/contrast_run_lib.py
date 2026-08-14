#!/usr/bin/env python3
"""Shared helpers for contrast-workload QuWARTS and DocETL runners."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = Path(__file__).resolve().parent
WORKLOADS = CASE / "workloads"
DEFAULT_CSV = WORKLOADS / "contrast_workloads.csv"

# Evaluation / GT name -> source_data/ directory name.
SOURCE_DATASET = {
    "Player": "Player",
    "Art": "Art",
    "CSPaper": "CSPaper",
    "Finan": "Finance",
    "Legal": "Legal",
    "Med": "Healthcare",
    "SEC": "SEC",
}

# SQL table name -> subdirectory under source_data/<source_dataset>/.
TABLE_SOURCE_SUBDIRS = {
    "Player": {
        "player": "player",
        "team": "team",
        "owner": "owner",
        "city": "city",
    },
    "Art": {"art": "wikiart"},
    "CSPaper": {"cspaper": "txt"},
    "Finan": {"finance": "finance"},
    "Legal": {"legal": "legal_case"},
    "Med": {
        "disease": "disease_small",
        "drug": "drug_small",
        "institution": "institutes_small",
    },
    "SEC": {
        "company": "company",
        "filing": "filing",
        "filing_metrics": "filing_metrics",
        "concept": "concept",
    },
}

# Attribute-file table keys that differ from SQL table names.
ATTR_TABLE_ALIASES = {
    "Art": {"Art": "art", "art": "art"},
    "CSPaper": {"paper": "cspaper", "cspaper": "cspaper"},
    "Legal": {"legal_case": "legal", "legal": "legal"},
    "Finan": {"finance": "finance"},
}

CONTRAST_DATASETS = ("Art", "CSPaper", "Finan", "Legal", "Med", "SEC")


def source_dataset(eval_dataset: str) -> str:
    key = str(eval_dataset or "").strip()
    return SOURCE_DATASET.get(key, key)


def table_source_subdirs(eval_dataset: str) -> dict[str, str]:
    key = str(eval_dataset or "").strip()
    return dict(TABLE_SOURCE_SUBDIRS.get(key, {}))


def attr_table_alias(eval_dataset: str, raw_name: str) -> str:
    key = str(eval_dataset or "").strip()
    aliases = ATTR_TABLE_ALIASES.get(key, {})
    return aliases.get(raw_name, raw_name.lower())


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def resolve_repo_path(raw: str) -> Path:
    """Resolve a CSV path that may be repo-relative or case-study-relative."""

    text = str(raw or "").strip()
    if not text:
        raise FileNotFoundError("empty path")
    candidate = Path(text).expanduser()
    if candidate.is_absolute() and candidate.exists():
        return candidate.resolve()
    for base in (ROOT, CASE):
        path = (base / candidate).resolve()
        if path.exists():
            return path
    if not text.startswith("case study/"):
        prefixed = (ROOT / "case study" / candidate).resolve()
        if prefixed.exists():
            return prefixed
    return (ROOT / candidate).resolve()


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def select_rows(
    rows: list[dict[str, str]],
    *,
    only: set[str] | None,
    datasets: set[str] | None,
    include_disabled: bool,
    include_player: bool,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for row in rows:
        workload_id = str(row.get("workload_id") or "").strip()
        dataset = str(row.get("dataset") or "").strip()
        if only is not None and workload_id not in only:
            continue
        if datasets is not None and dataset.lower() not in datasets:
            continue
        if not include_player and dataset.lower() == "player":
            continue
        if only is None and not include_disabled and not truthy(row.get("enabled")):
            continue
        selected.append(row)
    if only is not None:
        found = {str(row["workload_id"]).strip() for row in selected}
        missing = sorted(only - found)
        if missing and not include_disabled:
            return select_rows(
                rows,
                only=only,
                datasets=datasets,
                include_disabled=True,
                include_player=include_player,
            )
        if missing:
            raise SystemExit(f"unknown or unavailable workload ids: {missing}")
    if not selected:
        raise SystemExit("no workloads selected")
    return selected


def parse_only(raw: str) -> set[str] | None:
    values = {part.strip() for part in raw.split(",") if part.strip()}
    return values or None


def parse_datasets(raw: str) -> set[str] | None:
    values = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return values or None


def stamp_source_dataset(row: dict[str, str], override: str | None = None) -> dict[str, str]:
    out = dict(row)
    eval_name = str(out.get("dataset") or "").strip()
    out["source_dataset"] = (override or source_dataset(eval_name) or eval_name)
    return out
