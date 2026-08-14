#!/usr/bin/env python3
"""Pack Player agg20 QuWARTS/DocETL artifacts into one analysis JSON.

Run on HPC from the repo root, then copy the printed output file here.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUWARTS = ROOT / "case study" / "workloads" / "runs" / "20260814T054503Z"
DEFAULT_DOCETL = (
    ROOT / "case study" / "workloads" / "runs" / "20260814T011708Z" / "docetl"
)
DEFAULT_OLD_QUWARTS = Path("/scratch/general/vast/u1592362/quwarts_player_agg20_25pct")
SAMPLE_ROWS = 12


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_ready(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return value


def _norm_key(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def _sqlite_affinity(values: list[Any]) -> str:
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
    for path in sorted((ROOT / "Data" / "Player").glob("*.csv")):
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


def _build_ground_truth_db(tables: dict[str, list[dict[str, Any]]]) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    for table, rows in tables.items():
        columns = sorted({key for row in rows for key in row})
        definitions = ", ".join(
            f'"{column}" {_sqlite_affinity([row.get(column) for row in rows])}'
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


def _row_differences(
    gold: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
    keys: list[str],
    measures: list[str],
) -> dict[str, Any]:
    gold_by_key = {
        tuple(_norm_key(row.get(key)) for key in keys): row for row in gold
    }
    predicted_by_key = {
        tuple(_norm_key(row.get(key)) for key in keys): row for row in predicted
    }
    missing_keys = sorted(set(gold_by_key) - set(predicted_by_key))
    extra_keys = sorted(set(predicted_by_key) - set(gold_by_key))
    wrong_values = []
    for key in sorted(set(gold_by_key) & set(predicted_by_key)):
        gold_row = gold_by_key[key]
        predicted_row = predicted_by_key[key]
        differences = {}
        for measure in measures:
            if gold_row.get(measure) != predicted_row.get(measure):
                differences[measure] = {
                    "gold": gold_row.get(measure),
                    "predicted": predicted_row.get(measure),
                }
        if differences:
            wrong_values.append(
                {
                    "key": {column: gold_row.get(column) for column in keys},
                    "differences": differences,
                }
            )
    return {
        "missing_count": len(missing_keys),
        "extra_count": len(extra_keys),
        "wrong_count": len(wrong_values),
        "missing_rows": [gold_by_key[key] for key in missing_keys],
        "extra_rows": [predicted_by_key[key] for key in extra_keys],
        "wrong_values": wrong_values,
    }


def _short_config(config_id: str) -> str:
    if "er=evidence" in config_id and "norm=contract_mapping" in config_id:
        return "mapped"
    if "er=raw" in config_id:
        return "raw"
    return config_id


def _score_block(evaluation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not evaluation:
        return None
    query_score = evaluation.get("mean_query_score") or {}
    return {
        "structure": evaluation.get("mean_structure_score"),
        "score_at_20": query_score.get("0.2"),
        "score_at_05": query_score.get("0.05"),
        "score_at_01": query_score.get("0.01"),
        "official_accuracy": evaluation.get("mean_official_accuracy"),
    }


def _token_summary(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = _read_json(path)
    charges = data.get("charges") or []
    by_stage: dict[str, int] = {}
    for charge in charges:
        stage = str(charge.get("stage") or "unknown")
        by_stage[stage] = by_stage.get(stage, 0) + int(
            charge.get("actual_tokens")
            or (
                int(charge.get("input_tokens") or 0)
                + int(charge.get("output_tokens") or 0)
            )
        )
    return {
        "actual_spent": data.get("actual_spent"),
        "total_budget": data.get("total_tokens") or data.get("total_budget"),
        "by_stage": by_stage or data.get("by_stage"),
    }


def _table_profile(connection: sqlite3.Connection) -> dict[str, Any]:
    tables = {}
    names = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    for name in names:
        columns = [
            row[1]
            for row in connection.execute(f'PRAGMA table_info("{name}")')
        ]
        rows = _execute(connection, f'SELECT * FROM "{name}"')
        coverage = {}
        distinct = {}
        samples = {}
        for column in columns:
            values = [row.get(column) for row in rows]
            filled = [value for value in values if value not in (None, "")]
            coverage[column] = {
                "filled": len(filled),
                "total": len(values),
                "rate": (len(filled) / len(values)) if values else 0.0,
            }
            unique = []
            seen = set()
            for value in filled:
                key = _norm_key(value)
                if key in seen:
                    continue
                seen.add(key)
                unique.append(value)
                if len(unique) >= 20:
                    break
            distinct[column] = {
                "count": len({_norm_key(value) for value in filled}),
                "examples": unique,
            }
            samples[column] = filled[:8]
        tables[name] = {
            "row_count": len(rows),
            "columns": columns,
            "coverage": coverage,
            "distinct": distinct,
            "sample_rows": rows[:SAMPLE_ROWS],
        }
    return tables


def _find_first(*candidates: Path) -> Path | None:
    for path in candidates:
        if path.is_file():
            return path
    return None


def _find_dir(*candidates: Path) -> Path | None:
    for path in candidates:
        if path.is_dir():
            return path
    return None


def _extract_bulk_metadata(synthesis: dict[str, Any] | None) -> dict[str, Any]:
    if not synthesis:
        return {}
    found: dict[str, Any] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "relation_balanced_scheduler" in node and "scheduler" not in found:
                found["scheduler"] = node["relation_balanced_scheduler"]
            if "column_coverage" in node and "column_coverage" not in found:
                found["column_coverage"] = node["column_coverage"]
            if (
                "column_coverage_targets" in node
                and "column_coverage_targets" not in found
            ):
                found["column_coverage_targets"] = node["column_coverage_targets"]
            if "document_routing" in node and "document_routing" not in found:
                found["document_routing"] = node["document_routing"]
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(synthesis)
    return found


def _query_score(evaluation: dict[str, Any] | None, query_id: str) -> dict[str, Any]:
    if not evaluation:
        return {}
    row = (evaluation.get("per_query") or {}).get(query_id) or {}
    rank = row.get("rank") or {}
    return {
        "predicted_row_count": row.get("predicted_row_count"),
        "gold_row_count": row.get("gold_row_count"),
        "structure": (rank.get("structure_score") or row.get("structure_score")),
        "score_at_20": ((rank.get("query_score") or {}).get("0.2")),
        "official_accuracy": row.get("official_accuracy"),
        "schema": row.get("schema"),
    }


def pack(
    quwarts_run: Path,
    docetl_run: Path,
    old_quwarts_run: Path | None,
) -> dict[str, Any]:
    quwarts_result = _find_dir(
        quwarts_run / "results" / "player_agg20",
        quwarts_run,
    )
    if quwarts_result is None:
        raise FileNotFoundError(f"QuWARTS result dir not found under {quwarts_run}")
    bundle = quwarts_result / "serving_bundle"
    serving = _read_json(bundle / "manifest.json")
    quwarts_eval = _read_json(quwarts_result / "evaluation.json")
    run_manifest_path = _find_first(
        quwarts_result / "run_manifest.json",
        quwarts_run / "run_manifest.json",
    )
    synthesis_path = _find_first(
        quwarts_result / "synthesis_manifest.json",
        quwarts_run / "synthesis_manifest.json",
    )
    ledger_path = _find_first(
        bundle / "token_ledger.json",
        quwarts_result / "token_ledger.json",
    )
    run_manifest = _read_json(run_manifest_path) if run_manifest_path else {}
    synthesis = _read_json(synthesis_path) if synthesis_path else None

    docetl_result = _find_dir(
        docetl_run / "results" / "player_agg20",
        docetl_run,
    )
    docetl_eval = None
    docetl_summary = None
    docetl_tables_dir = None
    if docetl_result is not None:
        eval_path = _find_first(
            docetl_result / "evaluation.json",
            docetl_result / "aggregation_evaluation_fbeta2.json",
        )
        if eval_path:
            docetl_eval = _read_json(eval_path)
        summary_path = _find_first(docetl_result / "summary.json")
        if summary_path:
            docetl_summary = _read_json(summary_path)
        docetl_tables_dir = _find_dir(docetl_result / "query_tables")

    old_eval = None
    if old_quwarts_run is not None:
        old_eval_path = _find_first(
            old_quwarts_run / "results" / "player_agg20" / "evaluation.json",
            old_quwarts_run / "evaluation.json",
        )
        if old_eval_path:
            old_eval = _read_json(old_eval_path)

    manifest_path = ROOT / "case study" / "docetl_Player_v7" / "query_manifest.json"
    nl_path = ROOT / "case study" / "docetl_Player_v7" / "query_manifest_nl.json"
    references = {
        row["query_id"]: row["sql"] for row in _read_json(manifest_path)
    }
    natural_language = {
        row["query_id"]: row.get("text") or row.get("sql")
        for row in _read_json(nl_path)
    } if nl_path.is_file() else references

    serving_queries = {row["query_id"]: row for row in serving.get("queries", [])}
    databases = {
        row["config_id"]: bundle / row["filename"]
        for row in serving.get("databases", [])
    }
    gold_db = _build_ground_truth_db(_load_ground_truth())
    db_profiles = {}
    connections: dict[str, sqlite3.Connection] = {}
    try:
        for config_id, path in databases.items():
            connection = sqlite3.connect(path)
            connections[config_id] = connection
            db_profiles[_short_config(config_id)] = {
                "config_id": config_id,
                "filename": str(path.relative_to(bundle)),
                "tables": _table_profile(connection),
            }

        queries = {}
        for query_id in sorted(references, key=lambda item: int(item[1:])):
            serving_query = serving_queries.get(query_id, {})
            config_id = serving_query.get("config_id") or (
                (serving.get("portfolio") or {}).get("query_to_config") or {}
            ).get(query_id)
            gold = _execute(gold_db, references[query_id])
            quwarts_rows: list[dict[str, Any]] = []
            quwarts_error = None
            if config_id in connections and serving_query.get("sql"):
                try:
                    quwarts_rows = _execute(
                        connections[config_id], serving_query["sql"]
                    )
                except Exception as exc:  # noqa: BLE001
                    quwarts_error = str(exc)
            docetl_rows = []
            if docetl_tables_dir is not None:
                table_path = docetl_tables_dir / f"{query_id}.json"
                if table_path.is_file():
                    docetl_rows = _read_json(table_path)
            quwarts_metrics = _query_score(quwarts_eval, query_id)
            docetl_metrics = _query_score(docetl_eval, query_id)
            schema = quwarts_metrics.get("schema") or docetl_metrics.get("schema") or {}
            keys = list(schema.get("key_columns") or [])
            measures = list(schema.get("measure_columns") or [])
            queries[query_id] = {
                "natural_language": natural_language.get(query_id),
                "reference_sql": references[query_id],
                "quwarts_sql": serving_query.get("sql"),
                "route": _short_config(config_id or ""),
                "config_id": config_id,
                "schema": schema,
                "gold": gold,
                "quwarts": quwarts_rows,
                "quwarts_error": quwarts_error,
                "docetl": docetl_rows,
                "quwarts_metrics": quwarts_metrics,
                "docetl_metrics": docetl_metrics,
                "old_quwarts_metrics": _query_score(old_eval, query_id),
                "quwarts_differences": _row_differences(
                    gold, quwarts_rows, keys, measures
                ),
                "docetl_differences": _row_differences(
                    gold, docetl_rows, keys, measures
                ),
            }
    finally:
        gold_db.close()
        for connection in connections.values():
            connection.close()

    tokens = _token_summary(ledger_path) if ledger_path else None
    if tokens is None and run_manifest.get("tokens"):
        tokens = {
            "actual_spent": (run_manifest["tokens"] or {}).get("actual_spent"),
            "total_budget": (run_manifest["tokens"] or {}).get("total_budget"),
            "by_stage": (run_manifest["tokens"] or {}).get("by_stage"),
        }

    return {
        "paths": {
            "quwarts_run": str(quwarts_run),
            "quwarts_result": str(quwarts_result),
            "docetl_run": str(docetl_run),
            "old_quwarts_run": str(old_quwarts_run) if old_quwarts_run else None,
        },
        "headline": {
            "quwarts": _score_block(quwarts_eval),
            "docetl": _score_block(docetl_eval),
            "old_quwarts": _score_block(old_eval),
            "quwarts_tokens": tokens,
            "docetl_tokens": {
                "total_tokens": (docetl_summary or {}).get("total_tokens"),
                "prompt_tokens": (docetl_summary or {}).get("prompt_tokens"),
                "completion_tokens": (docetl_summary or {}).get("completion_tokens"),
            },
        },
        "portfolio": {
            "selected_config_ids": (serving.get("portfolio") or {}).get(
                "selected_config_ids"
            ),
            "query_to_route": {
                query_id: _short_config(config_id)
                for query_id, config_id in (
                    (serving.get("portfolio") or {}).get("query_to_config") or {}
                ).items()
            },
        },
        "bulk": _extract_bulk_metadata(synthesis),
        "databases": db_profiles,
        "queries": queries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quwarts-run", type=Path, default=DEFAULT_QUWARTS)
    parser.add_argument("--docetl-run", type=Path, default=DEFAULT_DOCETL)
    parser.add_argument("--old-quwarts-run", type=Path, default=DEFAULT_OLD_QUWARTS)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "case study" / "player_agg20_case_pack.json",
    )
    args = parser.parse_args()
    old_run = args.old_quwarts_run if args.old_quwarts_run.exists() else None
    payload = pack(args.quwarts_run, args.docetl_run, old_run)
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(output.resolve())
    print("bytes", output.stat().st_size)
    headline = payload["headline"]
    print("QuWARTS structure", (headline["quwarts"] or {}).get("structure"))
    print("QuWARTS score@20", (headline["quwarts"] or {}).get("score_at_20"))
    print("DocETL structure", (headline["docetl"] or {}).get("structure"))
    print("DocETL score@20", (headline["docetl"] or {}).get("score_at_20"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
