#!/usr/bin/env python3
"""Generate auditable per-query QuWARTS/DocETL Player case studies."""

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
DEFAULT_ARTIFACT_ROOT = ROOT / "case study" / "player_agg20_case_artifacts"
DEFAULT_OUTPUT = ROOT / "case study" / "player_agg20_detailed"
DEFAULT_DIAGNOSES = ROOT / "case study" / "player_agg20_diagnoses.json"


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
        for row in tables["owner"]
        if row.get("nba_team") and row.get("name")
    }
    for row in tables["team"]:
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
        tuple(_norm_key(row.get(key)) for key in keys): row
        for row in rows
    }


def _row_differences(
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
                    "key": {
                        column: gold_row.get(column)
                        for column in keys
                    },
                    "differences": differences,
                }
            )
    return {
        "missing_rows": [gold_by_key[key] for key in missing_keys],
        "extra_rows": [predicted_by_key[key] for key in extra_keys],
        "wrong_values": wrong_values,
    }


def _markdown_value(value: Any, *, limit: int = 180) -> str:
    if value is None:
        text = "NULL"
    elif isinstance(value, float):
        text = f"{value:.8g}"
    else:
        text = str(value)
    text = text.replace("\n", " ").replace("|", "\\|")
    if len(text) > limit:
        text = f"{text[: limit - 24]}… [{len(text)} chars]"
    return text


def _markdown_table(
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    empty: str = "_No rows._",
) -> str:
    if not rows:
        return empty
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(_markdown_value(row.get(column)) for column in columns)
            + " |"
        )
    return "\n".join(lines)


def _wrong_value_table(rows: list[dict[str, Any]]) -> str:
    flattened = []
    for row in rows:
        key_text = ", ".join(
            f"{key}={value}" for key, value in row["key"].items()
        )
        for measure, values in row["differences"].items():
            flattened.append(
                {
                    "group": key_text,
                    "measure": measure,
                    "gold": values["gold"],
                    "predicted": values["predicted"],
                }
            )
    return _markdown_table(
        flattened,
        ["group", "measure", "gold", "predicted"],
        empty="_No wrong values among aligned groups._",
    )


def _diagnosis_section(system: str, diagnosis: dict[str, Any]) -> str:
    label = "QuWARTS" if system == "quwarts" else "DocETL"
    if not diagnosis:
        return f"### Why {label} differs\n_Diagnostic explanation unavailable._"
    evidence = "\n".join(
        f"- {item}" for item in diagnosis.get("evidence", [])
    )
    return "\n".join(
        [
            f"### Why {label} differs",
            f"- **Pipeline stage:** {diagnosis.get('failure_stage', 'mixed')}",
            f"- **Root cause:** {diagnosis.get('root_cause', diagnosis.get('summary', 'Not specified.'))}",
            f"- **Pipeline behavior behind it:** {diagnosis.get('design_choice', 'Not specified.')}",
            f"- **Why validation allowed it:** {diagnosis.get('why_checks_missed', 'Not specified.')}",
            f"- **How it affected the result:** {diagnosis.get('failure_path', 'Not specified.')}",
            "",
            "**What I found in the final and working tables**",
            evidence or "- No artifact evidence recorded.",
        ]
    )


def _score_line(metrics: dict[str, Any]) -> str:
    return (
        f"structure F2 `{float(metrics['structure_fbeta_score']):.4f}`; "
        f"main score at 1% error `{float(metrics['query_score']['0.01']):.4f}`; "
        f"at 5% `{float(metrics['query_score']['0.05']):.4f}`; "
        f"at 20% `{float(metrics['query_score']['0.2']):.4f}`"
    )


def _load_inputs(artifact_root: Path) -> dict[str, Any]:
    quwarts_root = (
        artifact_root
        / "quwarts"
        / "results"
        / "contract_quwarts_Player_sqlcontract40pct"
    )
    docetl_root = (
        artifact_root
        / "docetl"
        / "results"
        / "docetl_Player_agg20_nl"
    )
    reference_rows = _read_json(docetl_root / "query_manifest.json")
    nl_rows = _read_json(docetl_root / "query_manifest_nl.json")
    references = {row["query_id"]: row["sql"] for row in reference_rows}
    natural_language = {row["query_id"]: row["text"] for row in nl_rows}
    serving_manifest = _read_json(quwarts_root / "serving_bundle" / "manifest.json")
    quwarts_queries = {
        row["query_id"]: row for row in serving_manifest["queries"]
    }
    databases = {
        row["config_id"]: quwarts_root / "serving_bundle" / row["filename"]
        for row in serving_manifest["databases"]
    }
    return {
        "quwarts_root": quwarts_root,
        "docetl_root": docetl_root,
        "references": references,
        "natural_language": natural_language,
        "quwarts_queries": quwarts_queries,
        "databases": databases,
        "quwarts_evaluation": _read_json(
            quwarts_root / "evaluation_fbeta2.json"
        )["per_query"],
        "docetl_evaluation": _read_json(
            docetl_root / "aggregation_evaluation_fbeta2.json"
        )["per_query"],
    }


def _collect_cases(artifact_root: Path) -> dict[str, dict[str, Any]]:
    inputs = _load_inputs(artifact_root)
    ground_truth_db = _build_ground_truth_db(_load_ground_truth())
    database_connections: dict[Path, sqlite3.Connection] = {}
    cases: dict[str, dict[str, Any]] = {}
    try:
        for query_id, reference_sql in inputs["references"].items():
            query = inputs["quwarts_queries"][query_id]
            database_path = inputs["databases"][query["config_id"]]
            if database_path not in database_connections:
                database_connections[database_path] = sqlite3.connect(database_path)
            gold = _execute(ground_truth_db, reference_sql)
            quwarts = _execute(database_connections[database_path], query["sql"])
            docetl = _read_json(
                inputs["docetl_root"] / "query_tables" / f"{query_id}.json"
            )
            schema = inputs["quwarts_evaluation"][query_id]["schema"]
            key_columns = list(schema["key_columns"])
            measure_columns = list(schema["measure_columns"])
            cases[query_id] = {
                "query_id": query_id,
                "natural_language_query": inputs["natural_language"][query_id],
                "reference_sql": reference_sql,
                "quwarts_sql": query["sql"],
                "quwarts_config_id": query["config_id"],
                "schema": schema,
                "gold": gold,
                "quwarts": quwarts,
                "docetl": docetl,
                "quwarts_metrics": inputs["quwarts_evaluation"][query_id],
                "docetl_metrics": inputs["docetl_evaluation"][query_id],
                "quwarts_differences": _row_differences(
                    gold, quwarts, key_columns, measure_columns
                ),
                "docetl_differences": _row_differences(
                    gold, docetl, key_columns, measure_columns
                ),
            }
    finally:
        ground_truth_db.close()
        for connection in database_connections.values():
            connection.close()
    return cases


def _write_case(
    output: Path,
    case: dict[str, Any],
    diagnoses: dict[str, Any],
) -> None:
    query_id = case["query_id"]
    columns = case["schema"]["key_columns"] + case["schema"]["measure_columns"]
    sections = [
        f"# {query_id}: {case['natural_language_query']}",
        "## Query contract",
        f"**Natural language:** {case['natural_language_query']}",
        "",
        "**Reference SQL**",
        "```sql",
        case["reference_sql"],
        "```",
        "",
        "**QuWARTS compiled SQL**",
        "```sql",
        case["quwarts_sql"],
        "```",
        "",
        "The SQL contracts are equivalent unless the two SQL blocks visibly differ. "
        "Therefore, documented failures below are downstream of intent/compilation.",
        "",
        "## Scores",
        f"- **QuWARTS:** {_score_line(case['quwarts_metrics'])}",
        f"- **DocETL:** {_score_line(case['docetl_metrics'])}",
        "",
        "## Ground truth output",
        _markdown_table(case["gold"], columns),
        "",
        "## QuWARTS output",
        _markdown_table(case["quwarts"], columns),
        "",
        "## DocETL output",
        _markdown_table(case["docetl"], columns),
    ]
    for system in ("quwarts", "docetl"):
        label = "QuWARTS" if system == "quwarts" else "DocETL"
        differences = case[f"{system}_differences"]
        sections.extend(
            [
                "",
                f"## {label} discrepancy ledger",
                "### Missing groups",
                _markdown_table(differences["missing_rows"], columns),
                "",
                "### Extra groups",
                _markdown_table(differences["extra_rows"], columns),
                "",
                "### Wrong values on aligned groups",
                _wrong_value_table(differences["wrong_values"]),
                "",
                _diagnosis_section(system, diagnoses.get(query_id, {}).get(system, {})),
            ]
        )
    sections.extend(
        [
            "",
            "## Audit note",
            f"The exact, unabridged rows used in this report are in `data/{query_id}.json`. "
            "Very long malformed values are abbreviated only in the Markdown tables.",
            "",
        ]
    )
    (output / f"{query_id}.md").write_text("\n".join(sections), encoding="utf-8")


def _write_index(
    output: Path,
    cases: dict[str, dict[str, Any]],
    diagnoses: dict[str, Any],
) -> None:
    rows = []
    for query_id in sorted(cases, key=lambda item: int(item[1:])):
        case = cases[query_id]
        rows.append(
            {
                "query": f"[{query_id}]({query_id}.md)",
                "QuWARTS main score at 20%": (
                    f"{case['quwarts_metrics']['query_score']['0.2']:.4f}"
                ),
                "DocETL main score at 20%": (
                    f"{case['docetl_metrics']['query_score']['0.2']:.4f}"
                ),
                "QuWARTS stage": diagnoses.get(query_id, {})
                .get("quwarts", {})
                .get("failure_stage", "unclassified"),
                "DocETL stage": diagnoses.get(query_id, {})
                .get("docetl", {})
                .get("failure_stage", "unclassified"),
            }
        )
    text = "\n".join(
        [
            "# Player aggregation case studies: QuWARTS vs DocETL",
            "This index links the 20 query-level reports. Each report contains the exact "
            "query contract, scores, gold output, both system outputs, row/cell discrepancy "
            "ledgers, and artifact-backed causal diagnoses.",
            "",
            _markdown_table(
                rows,
                [
                    "query",
                    "QuWARTS main score at 20%",
                    "DocETL main score at 20%",
                    "QuWARTS stage",
                    "DocETL stage",
                ],
            ),
            "",
            "## Cross-query findings",
            "- **Shared hard failure:** q0, q4, and q8 return no rows in both systems because "
            "fine-grained positions are never mapped to the contract literals Frontcourt and "
            "Backcourt.",
            "- **QuWARTS:** its largest recurring failures are sparse player attributes, "
            "unresolved college/nationality/team aliases, team documents expanding into "
            "historical or non-team records, and inconsistent numeric/unit extraction.",
            "- **DocETL:** its largest recurring failures are treating -1 as data inside "
            "aggregates and predicates, extracting join keys independently without resolution, "
            "and retaining malformed structured payloads as scalar values.",
            "- **Evaluator-specific effects:** q5/q6 expose mixed-type SQLite behavior for "
            "empty numeric strings, while q14 gold keys are rewritten through the separate "
            "owner table before scoring. The q14 reports distinguish this hidden canonicalization "
            "from extraction mistakes.",
            "",
            "## Interpretation boundary",
            "The reports treat the supplied run artifacts as immutable observations. "
            "Each root cause is tied to the pipeline code and to an error that is visible "
            "in an intermediate extraction or materialized table.",
            "",
        ]
    )
    (output / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--diagnoses", type=Path, default=DEFAULT_DIAGNOSES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    diagnoses = _read_json(args.diagnoses) if args.diagnoses.exists() else {}
    cases = _collect_cases(args.artifact_root)
    args.output.mkdir(parents=True, exist_ok=True)
    data_dir = args.output / "data"
    data_dir.mkdir(exist_ok=True)
    for query_id, case in cases.items():
        (data_dir / f"{query_id}.json").write_text(
            json.dumps(case, indent=2, ensure_ascii=False, allow_nan=False),
            encoding="utf-8",
        )
        _write_case(args.output, case, diagnoses)
    _write_index(args.output, cases, diagnoses)
    print(f"Wrote {len(cases)} case studies to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
