"""Persist budgeted agent runs per slice so benchmark reruns need no LLM calls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from agent.budgeted_loop import BudgetedRunResult
from pipeline.extraction import ExtractionResult


def agent_run_cache_path(results_dir: Path, slice_name: str) -> Path:
    return results_dir / "agent_run_cache" / f"{slice_name}.json"


def _extraction_fingerprint(extraction: ExtractionResult | None) -> str | None:
    if extraction is None:
        return None
    payload = json.dumps(extraction.tuples_by_table, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _table_to_payload(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "columns": list(df.columns),
        "rows": json.loads(df.replace({np.nan: None}).to_json(orient="records")),
    }


def _table_from_payload(payload: Any) -> pd.DataFrame:
    # Legacy caches stored bare row lists without column metadata.
    if isinstance(payload, list):
        return pd.DataFrame(payload) if payload else pd.DataFrame()
    columns = list(payload.get("columns", []))
    rows = payload.get("rows", [])
    if rows:
        return pd.DataFrame(rows, columns=columns or None)
    return pd.DataFrame(columns=columns)


def _databases_to_payload(databases: dict[str, dict[str, pd.DataFrame]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for catalog_id, tables in databases.items():
        out[catalog_id] = {
            table: _table_to_payload(df) for table, df in tables.items()
        }
    return out


def _databases_from_payload(payload: dict[str, Any]) -> dict[str, dict[str, pd.DataFrame]]:
    out: dict[str, dict[str, pd.DataFrame]] = {}
    for catalog_id, tables in payload.items():
        out[catalog_id] = {
            table: _table_from_payload(table_payload)
            for table, table_payload in tables.items()
        }
    return out


def _repair_empty_table_columns(
    databases: dict[str, dict[str, pd.DataFrame]],
    schema: Any | None,
) -> dict[str, dict[str, pd.DataFrame]]:
    """Empty tables must keep schema columns so DuckDB can register them."""
    if schema is None:
        return databases
    schema_tables = getattr(schema, "tables", {}) or {}
    repaired: dict[str, dict[str, pd.DataFrame]] = {}
    for catalog_id, tables in databases.items():
        fixed: dict[str, pd.DataFrame] = {}
        for table, df in tables.items():
            if df.empty and len(df.columns) == 0 and table in schema_tables:
                fixed[table] = pd.DataFrame(columns=list(schema_tables[table]))
            else:
                fixed[table] = df
        repaired[catalog_id] = fixed
    return repaired


def save_agent_run_cache(
    path: Path,
    *,
    slice_name: str,
    seed: int,
    token_budget_total: int,
    extraction: ExtractionResult | None,
    run: BudgetedRunResult,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "slice": slice_name,
        "seed": seed,
        "token_budget_total": token_budget_total,
        "extraction_fingerprint": _extraction_fingerprint(extraction),
        "demand_profile": run.demand_profile,
        "supply_profile": run.supply_profile,
        "probed_configs": run.probed_configs,
        "final_routing": run.final_routing,
        "budget_summary": run.budget_summary,
        "rounds": run.rounds,
        "catalog_id_to_pipe": run.catalog_id_to_pipe,
        "databases": _databases_to_payload(run.databases),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_agent_run_cache(
    path: Path,
    *,
    slice_name: str,
    seed: int,
    token_budget_total: int,
    extraction: ExtractionResult | None,
    schema: Any | None = None,
) -> BudgetedRunResult | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if int(payload.get("version", 0)) < 2:
        return None
    if payload.get("slice") != slice_name:
        return None
    if int(payload.get("seed", -1)) != seed:
        return None
    if int(payload.get("token_budget_total", -1)) != token_budget_total:
        return None

    expected_fp = _extraction_fingerprint(extraction)
    cached_fp = payload.get("extraction_fingerprint")
    if expected_fp and cached_fp and expected_fp != cached_fp:
        return None

    databases = _repair_empty_table_columns(
        _databases_from_payload(payload.get("databases", {})),
        schema,
    )

    return BudgetedRunResult(
        demand_profile=dict(payload.get("demand_profile", {})),
        supply_profile=dict(payload.get("supply_profile", {})),
        probed_configs=list(payload.get("probed_configs", [])),
        final_routing=dict(payload.get("final_routing", {})),
        budget_summary=dict(payload.get("budget_summary", {})),
        rounds=int(payload.get("rounds", 0)),
        extraction=extraction,
        databases=databases,
        catalog_id_to_pipe=dict(payload.get("catalog_id_to_pipe", {})),
    )
