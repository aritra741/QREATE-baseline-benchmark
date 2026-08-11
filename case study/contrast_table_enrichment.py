#!/usr/bin/env python3
"""Attach gold/predicted tables and row diffs to contrast site queries."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
CASE = Path(__file__).resolve().parent
DEFAULT_BUNDLE = ROOT / "player-agg20-case-site" / "src" / "contrast-data.json"
PLAYER_CSV_DIR = ROOT / "Data" / "Player"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_ready(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return value


def _sqlite_affinity(values: Iterable[Any]) -> str:
    nonempty = [value for value in values if value not in (None, "")]
    if not nonempty:
        return "TEXT"
    for value in nonempty:
        try:
            float(str(value).strip().replace(",", ""))
        except (TypeError, ValueError):
            return "TEXT"
    return "NUMERIC"


def _load_ground_truth() -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(PLAYER_CSV_DIR.glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            tables[path.stem.lower()] = [
                {
                    str(key).strip(): (
                        value.strip() if isinstance(value, str) else value
                    )
                    for key, value in row.items()
                }
                for row in csv.DictReader(handle, skipinitialspace=True)
            ]
    owner_by_team = {
        row.get("nba_team"): row.get("name")
        for row in tables.get("owner", [])
        if row.get("nba_team") and row.get("name")
    }
    for row in tables.get("team", []):
        canonical_owner = owner_by_team.get(row.get("team_name"))
        if canonical_owner:
            row["ownership"] = canonical_owner
    return tables


def _build_ground_truth_db(
    tables: dict[str, list[dict[str, Any]]],
) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    for table, rows in tables.items():
        columns = sorted({key for row in rows for key in row})
        definitions = ", ".join(
            f'"{column}" {_sqlite_affinity(row.get(column) for row in rows)}'
            for column in columns
        )
        connection.execute(f'CREATE TABLE "{table}" ({definitions})')
        placeholders = ", ".join("?" for _ in columns)
        connection.executemany(
            f'INSERT INTO "{table}" VALUES ({placeholders})',
            [[row.get(column) for column in columns] for row in rows],
        )
    connection.commit()
    return connection


def _execute(connection: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    cursor = connection.execute(sql)
    columns = [item[0] for item in cursor.description]
    return [
        {column: _json_ready(value) for column, value in zip(columns, row)}
        for row in cursor.fetchall()
    ]


def _norm_key(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def _by_key(rows: list[dict[str, Any]], keys: list[str]) -> dict[tuple[str, ...], dict]:
    return {
        tuple(_norm_key(row.get(key)) for key in keys): row for row in rows
    }


def row_differences(
    gold: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
    keys: list[str],
    measures: list[str],
) -> dict[str, Any]:
    gold_by_key = _by_key(gold, keys)
    predicted_by_key = _by_key(predicted, keys)
    missing_keys = sorted(set(gold_by_key) - set(predicted_by_key))
    extra_keys = sorted(set(predicted_by_key) - set(gold_by_key))
    wrong_values: list[dict[str, Any]] = []
    for key in sorted(set(gold_by_key) & set(predicted_by_key)):
        gold_row = gold_by_key[key]
        predicted_row = predicted_by_key[key]
        differences = {}
        for measure in measures:
            gold_value = gold_row.get(measure)
            predicted_value = predicted_row.get(measure)
            if gold_value != predicted_value:
                differences[measure] = {
                    "gold": gold_value,
                    "predicted": predicted_value,
                }
        if differences:
            wrong_values.append(
                {
                    "key": {column: gold_row.get(column) for column in keys},
                    "differences": differences,
                }
            )
    return {
        "missing_rows": [gold_by_key[key] for key in missing_keys],
        "extra_rows": [predicted_by_key[key] for key in extra_keys],
        "wrong_values": wrong_values,
    }


def _load_docetl_table(result_dir: Path | None, query_id: str) -> list[dict[str, Any]] | None:
    if result_dir is None:
        return None
    candidates = [
        result_dir / "query_tables" / f"{query_id}.json",
        result_dir.parent / "query_tables" / f"{query_id}.json",
    ]
    for path in candidates:
        if path.is_file():
            payload = _read_json(path)
            if isinstance(payload, list):
                return payload
    results_path = result_dir / "query_results.json"
    if results_path.is_file():
        payload = _read_json(results_path)
        if isinstance(payload, dict) and isinstance(payload.get(query_id), list):
            return payload[query_id]
        if isinstance(payload, list):
            for row in payload:
                if isinstance(row, dict) and row.get("query_id") == query_id:
                    table = row.get("rows") or row.get("table") or row.get("result")
                    if isinstance(table, list):
                        return table
    return None


def _load_quwarts_table(result_dir: Path | None, query_id: str) -> list[dict[str, Any]] | None:
    if result_dir is None:
        return None
    bundle = result_dir / "serving_bundle"
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = _read_json(manifest_path)
    query = next(
        (
            row
            for row in manifest.get("queries", [])
            if row.get("query_id") == query_id
        ),
        None,
    )
    if not query or not query.get("sql") or query.get("compilation_error"):
        return []
    databases = {
        row["config_id"]: bundle / row["filename"]
        for row in manifest.get("databases", [])
        if row.get("config_id") and row.get("filename")
    }
    database_path = databases.get(query.get("config_id"))
    if database_path is None or not database_path.is_file():
        return None
    connection = sqlite3.connect(database_path)
    try:
        return _execute(connection, query["sql"])
    finally:
        connection.close()


def enrich_query_tables(
    query: dict[str, Any],
    *,
    gold_db: sqlite3.Connection,
    quwarts_result_dir: Path | None,
    docetl_result_dir: Path | None,
) -> dict[str, Any]:
    schema = (
        ((query.get("metrics") or {}).get("quwarts") or {}).get("schema")
        or ((query.get("metrics") or {}).get("docetl") or {}).get("schema")
        or {}
    )
    keys = list(schema.get("key_columns") or [])
    measures = list(schema.get("measure_columns") or [])
    gold = _execute(gold_db, query["sql"]) if query.get("sql") else []
    quwarts = _load_quwarts_table(quwarts_result_dir, query["query_id"])
    docetl = _load_docetl_table(docetl_result_dir, query["query_id"])
    differences = {
        "quwarts": (
            row_differences(gold, quwarts, keys, measures)
            if quwarts is not None
            else None
        ),
        "docetl": (
            row_differences(gold, docetl, keys, measures)
            if docetl is not None
            else None
        ),
    }
    query = {
        **query,
        "schema": schema,
        "gold": gold,
        "tables": {"quwarts": quwarts, "docetl": docetl},
        "differences": differences,
        "tables_complete": quwarts is not None and docetl is not None,
    }
    # Surface missing columns in evidence even when empty, for the UI.
    for system in ("quwarts", "docetl"):
        evidence = (query.get("evidence") or {}).get(system)
        if not isinstance(evidence, dict):
            continue
        structure = evidence.get("structure")
        if isinstance(structure, dict) and "missing_key_columns" not in structure:
            structure["missing_key_columns"] = []
    return query


def enrich_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    gold_db = _build_ground_truth_db(_load_ground_truth())
    try:
        workloads = {}
        for workload_id, row in (bundle.get("workloads") or {}).items():
            quwarts_dir = Path(row.get("quwarts", {}).get("result_dir") or "")
            docetl_dir = Path(row.get("docetl", {}).get("result_dir") or "")
            queries = [
                enrich_query_tables(
                    query,
                    gold_db=gold_db,
                    quwarts_result_dir=quwarts_dir if quwarts_dir.is_dir() else None,
                    docetl_result_dir=docetl_dir if docetl_dir.is_dir() else None,
                )
                for query in row.get("queries") or []
            ]
            workloads[workload_id] = {
                **row,
                "queries": queries,
                "tables_complete": all(query.get("tables_complete") for query in queries),
            }
        return {
            **bundle,
            "tables_attached": True,
            "tables_complete": all(
                row.get("tables_complete") for row in workloads.values()
            ),
            "workloads": workloads,
        }
    finally:
        gold_db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    bundle = _read_json(args.bundle)
    enriched = enrich_bundle(bundle)
    output = args.output or args.bundle
    output.write_text(
        json.dumps(enriched, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    complete = enriched.get("tables_complete")
    print(
        f"Wrote {output} (gold attached; predicted tables "
        f"{'complete' if complete else 'incomplete — stage serving_bundle/query_tables next to evaluation.json'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
