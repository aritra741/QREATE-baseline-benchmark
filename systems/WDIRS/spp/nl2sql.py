"""Synthesis-time NL2SQL compiler for frozen offline serving."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from spp.budget_ledger import GlobalBudgetLedger
from spp.budgeted_llm import BudgetedLLMClient
from spp.spec import QueryRequirement, SynthesisConfig


_SQL_START = re.compile(r"\b(SELECT|WITH)\b", re.IGNORECASE)


def _extract_sql(response: str) -> str:
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", response, re.I | re.S)
    candidate = fenced.group(1).strip() if fenced else response.strip()
    match = _SQL_START.search(candidate)
    if not match:
        raise ValueError("NL2SQL response contains no SELECT/WITH statement")
    sql = candidate[match.start() :].strip()
    # Strip explanatory text after the first semicolon.
    if ";" in sql:
        sql = sql.split(";", 1)[0].strip()
    return sql


def _verification_payload(response: str) -> dict:
    start, end = response.find("{"), response.rfind("}")
    if start < 0 or end < start:
        raise ValueError("NL2SQL verifier returned no JSON object")
    payload = json.loads(response[start : end + 1])
    if not isinstance(payload, dict) or not isinstance(
        payload.get("consistent"), bool
    ):
        raise ValueError("NL2SQL verifier omitted boolean 'consistent'")
    return payload


def _database_profile(database_path: Path, config: SynthesisConfig) -> list[dict]:
    profile = []
    uri = f"file:{Path(database_path).resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        for relation in config.schema.relations:
            quoted = relation.name.replace('"', '""')
            row_count = connection.execute(
                f'SELECT COUNT(*) FROM "{quoted}"'
            ).fetchone()[0]
            samples = [
                dict(row)
                for row in connection.execute(
                    f'SELECT * FROM "{quoted}" LIMIT 3'
                ).fetchall()
            ]
            non_null_counts = {}
            for column in relation.attributes:
                quoted_column = column.replace('"', '""')
                non_null_counts[column] = connection.execute(
                    f'SELECT COUNT("{quoted_column}") FROM "{quoted}"'
                ).fetchone()[0]
            profile.append(
                {
                    "table": relation.name,
                    "row_count": row_count,
                    "non_null_counts": non_null_counts,
                    "sample_rows": samples,
                }
            )
    return profile


def _query_is_informative(database_path: Path, sql: str) -> bool:
    uri = f"file:{Path(database_path).resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            cursor = connection.execute(sql)
            rows = cursor.fetchmany(20)
            return bool(rows) and any(
                value is not None
                for row in rows
                for value in row
            )
    except sqlite3.Error:
        return False


def make_nl2sql_compiler(llm_client: Any):
    """Return an ``OfflineSynthesisSystem`` compiler callback."""

    def compile_query(
        requirement: QueryRequirement,
        config: SynthesisConfig,
        database_path: Path,
        ledger: GlobalBudgetLedger,
    ) -> str:
        is_sql = bool(
            re.match(r"^\s*(select|with)\b", requirement.text, re.IGNORECASE)
        )
        if is_sql:
            referenced_tables = {
                match.lower()
                for match in re.findall(
                    r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)",
                    requirement.text,
                    re.IGNORECASE,
                )
            }
            candidate_tables = {
                relation.name.lower() for relation in config.schema.relations
            }
            if referenced_tables <= candidate_tables:
                return requirement.text.strip().rstrip(";")
        schema_payload = [
            {
                "table": relation.name,
                "columns": list(relation.attributes),
                "primary_key": relation.primary_key,
                "foreign_keys": [
                    {
                        "column": column,
                        "target_table": target_table,
                        "target_column": target_column,
                    }
                    for column, target_table, target_column in relation.foreign_keys
                ],
            }
            for relation in config.schema.relations
        ]
        data_profile = _database_profile(database_path, config)
        prompt = (
            "Compile the analytical question into one read-only SQLite query. "
            "Use only the provided schema. Return SQL only; never create, modify, "
            "attach, or populate data.\n\nSchema:\n"
            f"{json.dumps(schema_payload, indent=2)}\n\n"
            "Gold-free database profile (use populated columns and avoid empty "
            f"join paths):\n{json.dumps(data_profile, indent=2, default=str)}\n\n"
            + (
                "Original SQL expressing the intended query (rewrite it for "
                "the candidate schema):\n"
                if is_sql
                else "Question:\n"
            )
            + requirement.text
        )
        budgeted = BudgetedLLMClient(
            llm_client,
            ledger,
            default_stage="nl2sql",
            config_id=config.config_id,
            query_id=requirement.query_id,
        )
        response = budgeted.generate(
            prompt,
            max_tokens=1024,
            temperature=0.0,
            operation="compile_query",
        )
        sql = _extract_sql(response)
        verification_prompt = (
            "Check whether the SQLite query exactly answers the stated "
            "analytical intent using the supplied schema. Verify requested "
            "entities, attributes, predicates, grouping, and aggregates. "
            "Return ONLY JSON: {\"consistent\": true|false, \"reason\": "
            "\"...\", \"corrected_sql\": \"...\"}. If inconsistent, provide "
            "a corrected read-only query; otherwise corrected_sql may be null."
            f"\n\nIntent:\n{requirement.text}"
            f"\n\nStructured requirements:\n"
            f"{json.dumps({'entities': requirement.entities, 'attributes': requirement.attributes, 'relationships': requirement.relationships, 'operators': requirement.operators, 'units': requirement.units})}"
            f"\n\nSchema:\n{json.dumps(schema_payload)}"
            f"\n\nGold-free database profile:\n"
            f"{json.dumps(data_profile, default=str)}"
            f"\n\nCandidate SQL:\n{sql}"
        )
        verification = _verification_payload(
            budgeted.generate(
                verification_prompt,
                max_tokens=1024,
                temperature=0.0,
                operation="verify_compiled_query",
            )
        )
        if verification["consistent"]:
            return sql
        corrected = verification.get("corrected_sql")
        if not isinstance(corrected, str) or not corrected.strip():
            raise ValueError(
                f"NL2SQL semantic verification failed: "
                f"{verification.get('reason', 'no reason')}"
            )
        corrected_sql = _extract_sql(corrected)
        # A schema-only verifier can prefer normalized joins whose key columns
        # are unpopulated. Never let such a repair destroy an informative,
        # executable answer from the original compilation.
        if _query_is_informative(
            database_path, sql
        ) and not _query_is_informative(database_path, corrected_sql):
            return sql
        return corrected_sql

    return compile_query
