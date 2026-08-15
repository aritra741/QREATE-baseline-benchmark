#!/usr/bin/env python3
"""Shared helpers for contrast-workload QuWARTS and DocETL runners."""

from __future__ import annotations

import csv
import json
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


def resolve_docetl_root(raw: Path | None, workload_ids: set[str]) -> Path:
    if raw is not None:
        path = raw.expanduser()
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        if (path / "results").is_dir():
            return path.resolve()
        nested = path / "docetl"
        if (nested / "results").is_dir():
            return nested.resolve()
        raise SystemExit(f"no DocETL results under {path}")
    found = latest_docetl_root(workload_ids)
    if found is None:
        raise SystemExit(
            "No DocETL run found under case study/workloads/runs. "
            "Pass --docetl-root pointing at the previous .../docetl directory."
        )
    return found


def _positive_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        tokens = int(value)
    except (TypeError, ValueError):
        return None
    return tokens if tokens > 0 else None


def docetl_total_tokens(docetl_root: Path, workload_id: str) -> int | None:
    result_dir = docetl_root / "results" / workload_id
    for name in ("summary.json", "session_token_cost.json"):
        path = result_dir / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            tokens = _positive_int(payload.get("total_tokens"))
            if tokens is not None:
                return tokens
    index_path = docetl_root / "run_index.json"
    if index_path.is_file():
        try:
            records = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            records = []
        if isinstance(records, list):
            for record in records:
                if not isinstance(record, dict):
                    continue
                if str(record.get("workload_id") or "") != workload_id:
                    continue
                summary = record.get("docetl_summary")
                tokens = None
                if isinstance(summary, dict):
                    tokens = _positive_int(summary.get("total_tokens"))
                if tokens is None:
                    tokens = _positive_int(record.get("total_tokens"))
                if tokens is not None:
                    return tokens
    query_results = result_dir / "query_results.json"
    if query_results.is_file():
        try:
            payload = json.loads(query_results.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = None
        rows = payload
        if isinstance(payload, dict):
            rows = (
                payload.get("queries")
                or payload.get("results")
                or payload.get("per_query")
            )
        if isinstance(rows, list):
            total = 0
            found = False
            for row in rows:
                if not isinstance(row, dict):
                    continue
                tokens = _positive_int(row.get("total_tokens"))
                if tokens is not None:
                    total += tokens
                    found = True
            if found and total > 0:
                return total
    return None


def quwarts_budget_from_docetl(tokens: int, fraction: float) -> int:
    if tokens <= 0:
        raise ValueError(f"DocETL tokens must be positive, got {tokens}")
    if fraction <= 0:
        raise ValueError(f"budget fraction must be positive, got {fraction}")
    return max(1, int(tokens * fraction))
