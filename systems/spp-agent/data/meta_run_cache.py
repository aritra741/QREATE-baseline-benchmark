"""Cache meta-controller runs per slice."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from agent.meta_controller import MetaControllerRunResult
from pipeline.extraction import ExtractionResult


def meta_run_cache_path(results_dir: Path, slice_name: str) -> Path:
    return results_dir / "meta_run_cache" / f"{slice_name}.json"


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
    if isinstance(payload, list):
        return pd.DataFrame(payload) if payload else pd.DataFrame()
    columns = list(payload.get("columns", []))
    rows = payload.get("rows", [])
    if rows:
        return pd.DataFrame(rows, columns=columns or None)
    return pd.DataFrame(columns=columns)


def _databases_to_payload(databases: dict[str, dict[str, pd.DataFrame]]) -> dict[str, Any]:
    return {
        cid: {table: _table_to_payload(df) for table, df in tables.items()}
        for cid, tables in databases.items()
    }


def _databases_from_payload(payload: dict[str, Any]) -> dict[str, dict[str, pd.DataFrame]]:
    return {
        cid: {table: _table_from_payload(tp) for table, tp in tables.items()}
        for cid, tables in payload.items()
    }


def save_meta_run_cache(
    path: Path,
    *,
    slice_name: str,
    seed: int,
    token_budget_total: int,
    extraction: ExtractionResult | None,
    run: MetaControllerRunResult,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "slice_name": slice_name,
        "seed": seed,
        "token_budget_total": token_budget_total,
        "extraction_fingerprint": _extraction_fingerprint(extraction),
        "agent_mode": run.agent_mode,
        "chosen_algorithm_family": run.chosen_algorithm_family,
        "selection_rationale": run.selection_rationale,
        "solver_comparison": run.solver_comparison,
        "baseline_comparison": run.baseline_comparison,
        "algorithm_stack": run.algorithm_stack,
        "stage_summaries": run.stage_summaries,
        "audit_log": run.audit_log,
        "rounds": run.rounds,
        "selected_configs": run.selected_configs,
        "final_routing": run.final_routing,
        "databases": _databases_to_payload(run.databases),
        "probed_configs": run.probed_configs,
        "budget_summary": run.budget_summary,
        "demand_profile": run.demand_profile,
        "supply_profile": run.supply_profile,
        "diagnostics": run.diagnostics,
        "catalog_id_to_pipe": run.catalog_id_to_pipe,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_meta_run_cache(
    path: Path,
    *,
    slice_name: str,
    seed: int,
    token_budget_total: int,
    extraction: ExtractionResult | None,
    schema: Any | None = None,
) -> MetaControllerRunResult | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("slice_name") != slice_name:
        return None
    if int(payload.get("seed", -1)) != seed:
        return None
    if int(payload.get("token_budget_total", -1)) != token_budget_total:
        return None
    fp = _extraction_fingerprint(extraction)
    if fp and payload.get("extraction_fingerprint") and payload["extraction_fingerprint"] != fp:
        return None

    databases = _databases_from_payload(payload.get("databases", {}))
    if schema is not None:
        from data.agent_run_cache import _repair_empty_table_columns

        databases = _repair_empty_table_columns(databases, schema)

    return MetaControllerRunResult(
        agent_mode=str(payload.get("agent_mode", "meta_controller")),
        chosen_algorithm_family=str(payload.get("chosen_algorithm_family", "")),
        selection_rationale=str(payload.get("selection_rationale", "")),
        solver_comparison=list(payload.get("solver_comparison", [])),
        baseline_comparison=list(payload.get("baseline_comparison", [])),
        algorithm_stack=dict(payload.get("algorithm_stack", {})),
        stage_summaries=dict(payload.get("stage_summaries", {})),
        audit_log=list(payload.get("audit_log", [])),
        rounds=int(payload.get("rounds", 0)),
        selected_configs=list(payload.get("selected_configs", [])),
        final_routing=dict(payload.get("final_routing", {})),
        databases=databases,
        probed_configs=list(payload.get("probed_configs", [])),
        budget_summary=dict(payload.get("budget_summary", {})),
        demand_profile=dict(payload.get("demand_profile", {})),
        supply_profile=dict(payload.get("supply_profile", {})),
        diagnostics=dict(payload.get("diagnostics", {})),
        catalog_id_to_pipe=dict(payload.get("catalog_id_to_pipe", {})),
    )
