"""Materialize explicit schema designs from shared populated evidence tables."""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from spp.spec import RelationSpec, SchemaDesign


JoinPair = Tuple[str, str, str, str]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sqlite_value(value: object) -> object:
    """Return a deterministic value supported by Python's SQLite bindings."""
    if value is None or isinstance(value, (str, int, bytes)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    return str(value)


def _affinity(values: Iterable[object]) -> str:
    observed = [
        normalized
        for value in values
        if (normalized := _sqlite_value(value)) not in (None, "")
    ]
    if observed and all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in observed
    ):
        return "NUMERIC"
    return "TEXT"


def _project_rows(
    relation: RelationSpec, records: Sequence[Mapping[str, object]]
) -> List[dict]:
    return [
        {column: record.get(column) for column in relation.attributes}
        for record in records
    ]


def _joined_rows(
    base_tables: Mapping[str, Sequence[Mapping[str, object]]],
    join_pairs: Sequence[JoinPair],
) -> List[Dict[Tuple[str, str], object]]:
    if not base_tables:
        return []
    ordered_tables = sorted(base_tables)
    root = ordered_tables[0]
    rows: List[Dict[Tuple[str, str], object]] = [
        {(root, column): value for column, value in record.items()}
        for record in base_tables[root]
    ]
    included = {root}
    remaining = set(ordered_tables) - included
    while remaining:
        progress = False
        for left_table, left_column, right_table, right_column in join_pairs:
            if left_table in included and right_table in remaining:
                source_table, source_column = left_table, left_column
                target_table, target_column = right_table, right_column
            elif right_table in included and left_table in remaining:
                source_table, source_column = right_table, right_column
                target_table, target_column = left_table, left_column
            else:
                continue
            index: Dict[object, List[Mapping[str, object]]] = {}
            for record in base_tables[target_table]:
                index.setdefault(record.get(target_column), []).append(record)
            expanded: List[Dict[Tuple[str, str], object]] = []
            for row in rows:
                matches = index.get(row.get((source_table, source_column)), [])
                if not matches:
                    expanded.append(dict(row))
                for match in matches:
                    joined = dict(row)
                    joined.update(
                        {
                            (target_table, column): value
                            for column, value in match.items()
                        }
                    )
                    expanded.append(joined)
            rows = expanded
            included.add(target_table)
            remaining.remove(target_table)
            progress = True
            break
        if progress:
            continue
        # Disconnected workload branches are combined without inventing a join.
        target_table = min(remaining)
        records = base_tables[target_table]
        rows = [
            {
                **row,
                **{
                    (target_table, column): value
                    for column, value in record.items()
                },
            }
            for row in rows
            for record in records
        ]
        included.add(target_table)
        remaining.remove(target_table)
    return rows


def reshape_tables(
    base_tables: Mapping[str, Sequence[Mapping[str, object]]],
    schema: SchemaDesign,
    *,
    join_pairs: Sequence[JoinPair] = (),
) -> Dict[str, List[dict]]:
    """Apply a denormalized/star/snowflake schema without re-extraction."""
    if schema.pattern == "denormalized":
        joined = _joined_rows(base_tables, join_pairs)
        relation = schema.relations[0]
        rows: List[dict] = []
        for joined_row in joined:
            output = {}
            for attribute in relation.attributes:
                candidates = [
                    value
                    for (_table, column), value in joined_row.items()
                    if column == attribute and value not in (None, "")
                ]
                output[attribute] = candidates[0] if candidates else None
            rows.append(output)
        return {relation.name: rows}

    result: Dict[str, List[dict]] = {}
    for relation in schema.relations:
        records = base_tables.get(relation.name, ())
        result[relation.name] = _project_rows(relation, records)
    return result


def write_sqlite_database(
    path: Path,
    tables: Mapping[str, Sequence[Mapping[str, object]]],
    schema: SchemaDesign,
) -> Path:
    """Write one candidate to a fresh SQLite database."""
    path = Path(path).expanduser().resolve()
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        for relation in schema.relations:
            rows = list(tables.get(relation.name, ()))
            definitions = []
            for column in relation.attributes:
                declared_type = relation.semantic_type(column)
                affinity = (
                    "NUMERIC"
                    if declared_type in {"integer", "real", "boolean"}
                    else _affinity(row.get(column) for row in rows)
                )
                definitions.append(f"{_quote(column)} {affinity}")
            if relation.primary_key and relation.primary_key in relation.attributes:
                # Do not declare a SQLite PK: pilot extraction can contain
                # duplicates, and validity diagnostics must observe them.
                pass
            connection.execute(
                f"CREATE TABLE {_quote(relation.name)} "
                f"({', '.join(definitions)})"
            )
            if rows and relation.attributes:
                columns = ", ".join(_quote(c) for c in relation.attributes)
                placeholders = ", ".join("?" for _ in relation.attributes)
                connection.executemany(
                    f"INSERT INTO {_quote(relation.name)} ({columns}) "
                    f"VALUES ({placeholders})",
                    [
                        tuple(
                            _sqlite_value(row.get(column))
                            for column in relation.attributes
                        )
                        for row in rows
                    ],
                )
    return path
