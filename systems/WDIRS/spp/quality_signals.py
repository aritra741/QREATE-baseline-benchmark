"""Deterministic gold-free relational and query-consistency diagnostics."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from spp.spec import SchemaDesign


@dataclass(frozen=True)
class RelationalDiagnostics:
    schema_validity: float
    type_validity: float
    key_validity: float
    join_validity: float
    details: Mapping[str, float]


@dataclass(frozen=True)
class MetamorphicCheck:
    original_sql: str
    equivalent_sql: str


def _table_columns(connection: sqlite3.Connection, table: str) -> Dict[str, str]:
    rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {str(row[1]): str(row[2]).upper() for row in rows}


def profile_relational_database(
    database_path: Path, schema: SchemaDesign
) -> RelationalDiagnostics:
    """Validate schema, PK/FK consistency and SQLite type conformance."""
    uri = f"file:{Path(database_path).resolve()}?mode=ro"
    details: Dict[str, float] = {}
    with sqlite3.connect(uri, uri=True) as connection:
        expected_columns = 0
        present_columns = 0
        key_scores: List[float] = []
        foreign_key_scores: List[float] = []
        type_scores: List[float] = []
        for relation in schema.relations:
            columns = _table_columns(connection, relation.name)
            expected_columns += len(relation.attributes)
            present_columns += len(set(relation.attributes) & set(columns))
            if not columns:
                key_scores.append(0.0)
                type_scores.append(0.0)
                continue
            quoted_table = relation.name.replace('"', '""')
            row_count = connection.execute(
                f'SELECT COUNT(*) FROM "{quoted_table}"'
            ).fetchone()[0]
            if relation.primary_key and relation.primary_key in columns:
                quoted_key = relation.primary_key.replace('"', '""')
                non_null, distinct = connection.execute(
                    f'SELECT COUNT("{quoted_key}"), '
                    f'COUNT(DISTINCT "{quoted_key}") FROM "{quoted_table}"'
                ).fetchone()
                key_scores.append(
                    1.0 if row_count == 0 else min(non_null, distinct) / row_count
                )
            else:
                key_scores.append(0.0 if relation.primary_key else 1.0)

            valid_types = sum(
                1
                for column in relation.attributes
                if column in columns and columns[column] not in {"", "BLOB"}
            )
            type_scores.append(
                valid_types / max(len(relation.attributes), 1)
            )
            for column, target_table, target_column in relation.foreign_keys:
                if column not in columns:
                    foreign_key_scores.append(0.0)
                    continue
                target_columns = _table_columns(connection, target_table)
                if target_column not in target_columns:
                    foreign_key_scores.append(0.0)
                    continue
                qc = column.replace('"', '""')
                qt = target_table.replace('"', '""')
                qtc = target_column.replace('"', '""')
                source_non_null = connection.execute(
                    f'SELECT COUNT("{qc}") FROM "{quoted_table}"'
                ).fetchone()[0]
                matches = connection.execute(
                    f'SELECT COUNT(*) FROM "{quoted_table}" s '
                    f'JOIN "{qt}" t ON s."{qc}" = t."{qtc}" '
                    f'WHERE s."{qc}" IS NOT NULL'
                ).fetchone()[0]
                foreign_key_scores.append(
                    1.0
                    if source_non_null == 0
                    else min(matches / source_non_null, 1.0)
                )

    schema_validity = present_columns / max(expected_columns, 1)
    key_validity = sum(key_scores) / max(len(key_scores), 1)
    join_validity = (
        sum(foreign_key_scores) / len(foreign_key_scores)
        if foreign_key_scores
        else 1.0
    )
    type_validity = sum(type_scores) / max(len(type_scores), 1)
    details.update(
        {
            "expected_columns": float(expected_columns),
            "present_columns": float(present_columns),
            "relations": float(len(schema.relations)),
            "foreign_keys": float(
                sum(len(relation.foreign_keys) for relation in schema.relations)
            ),
        }
    )
    return RelationalDiagnostics(
        schema_validity=min(schema_validity, 1.0),
        type_validity=min(type_validity, 1.0),
        key_validity=min(key_validity, 1.0),
        join_validity=min(join_validity, 1.0),
        details=details,
    )


def _canonical_rows(rows: Iterable[sqlite3.Row], columns: Sequence[str]) -> str:
    payload = [
        {columns[index]: row[index] for index in range(len(columns))}
        for row in rows
    ]
    payload.sort(key=lambda row: json.dumps(row, sort_keys=True, default=str))
    return json.dumps(payload, sort_keys=True, default=str)


def metamorphic_consistency(
    database_path: Path, checks: Sequence[MetamorphicCheck]
) -> float:
    """Fraction of declared equivalent SQL rewrites with identical results."""
    if not checks:
        return 1.0
    uri = f"file:{Path(database_path).resolve()}?mode=ro"
    passed = 0
    with sqlite3.connect(uri, uri=True) as connection:
        for check in checks:
            try:
                left = connection.execute(check.original_sql)
                left_columns = [description[0] for description in left.description or []]
                left_result = _canonical_rows(left.fetchall(), left_columns)
                right = connection.execute(check.equivalent_sql)
                right_columns = [
                    description[0] for description in right.description or []
                ]
                right_result = _canonical_rows(right.fetchall(), right_columns)
                passed += left_columns == right_columns and left_result == right_result
            except sqlite3.Error:
                continue
    return passed / len(checks)


def candidate_agreement(
    outputs_by_config: Mapping[str, Iterable[dict]]
) -> Dict[str, float]:
    """Agreement with the modal output, exposed only as uncertainty evidence."""
    signatures: Dict[str, str] = {}
    for config_id, rows in outputs_by_config.items():
        payload = [
            {str(key): row[key] for key in sorted(row)}
            for row in rows
        ]
        payload.sort(key=lambda row: json.dumps(row, sort_keys=True, default=str))
        signatures[config_id] = json.dumps(payload, sort_keys=True, default=str)
    counts: Dict[str, int] = {}
    for signature in signatures.values():
        counts[signature] = counts.get(signature, 0) + 1
    denominator = max(len(signatures), 1)
    return {
        config_id: counts[signature] / denominator
        for config_id, signature in signatures.items()
    }
