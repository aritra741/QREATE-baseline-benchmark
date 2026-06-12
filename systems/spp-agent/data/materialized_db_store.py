"""Serialize materialized pipeline databases to JSON for experiment caches."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def safe_config_slug(config_id: str) -> str:
    """Filesystem-safe slug that remains reversible enough for debugging."""
    return config_id.replace("|", "__").replace("=", "_")


def database_path(databases_dir: Path, config_id: str) -> Path:
    return databases_dir / f"{safe_config_slug(config_id)}.json"


def _table_to_payload(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "columns": list(df.columns),
        "rows": json.loads(df.replace({np.nan: None}).to_json(orient="records")),
    }


def _table_from_payload(payload: Any) -> pd.DataFrame:
    if isinstance(payload, list):
        return pd.DataFrame(payload) if payload else pd.DataFrame()
    columns = list(payload.get("columns", []))
    rows = payload.get("rows", [])
    if rows:
        return pd.DataFrame(rows, columns=columns or None)
    return pd.DataFrame(columns=columns)


def save_materialized_database(
    path: Path,
    *,
    config_id: str,
    db: dict[str, pd.DataFrame],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "config_id": config_id,
        "tables": {table: _table_to_payload(df) for table, df in db.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_materialized_database(path: Path) -> tuple[str, dict[str, pd.DataFrame]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    config_id = str(payload.get("config_id", ""))
    tables = {
        table: _table_from_payload(table_payload)
        for table, table_payload in (payload.get("tables") or {}).items()
    }
    return config_id, tables


def write_database_index(
    databases_dir: Path,
    *,
    entries: dict[str, str],
) -> Path:
    """Map config_id -> relative database filename."""
    databases_dir.mkdir(parents=True, exist_ok=True)
    index_path = databases_dir / "index.json"
    payload = {
        "version": 1,
        "n_databases": len(entries),
        "databases": {
            config_id: {"path": rel_path, "slug": safe_config_slug(config_id)}
            for config_id, rel_path in sorted(entries.items())
        },
    }
    index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return index_path
