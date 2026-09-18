"""Workload-referenced attributes must exist as typed physical columns."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlglot import exp

from quwarts.core.logical import expression_aliases
from quwarts.core.signature import resolve_attribute, select_aliases, table_aliases
from quwarts.core.workload import _default_entity, parse_sql

_NUMERIC = (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between)
_NUMERIC_AGGS = (exp.Sum, exp.Avg)


@dataclass(frozen=True)
class ReferencedColumn:
    table: str
    column: str
    sql_type: str


class MissingColumnError(sqlite3.OperationalError):
    """A rewritten query still references a column that is not physical."""


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _statements(statements: dict[str, str] | Iterable[str]) -> list[str]:
    if isinstance(statements, dict):
        return [sql for sql in statements.values() if sql]
    return [sql for sql in statements if sql]


def referenced_columns(statements: dict[str, str] | Iterable[str]) -> list[ReferencedColumn]:
    """Columns mentioned in workload SQL, excluding SELECT aliases."""

    types: dict[tuple[str, str], set[str]] = {}
    for sql in _statements(statements):
        try:
            tree = parse_sql(sql)
        except Exception:
            continue
        aliases = table_aliases(tree)
        default = _default_entity(tree)
        skip = select_aliases(tree) | {alias.lower() for alias in expression_aliases(tree, default)}
        for column in tree.find_all(exp.Column):
            resolved = resolve_attribute(column, aliases, default)
            if resolved is None:
                continue
            _qualified, table, name = resolved
            if name in skip or name == "rowid":
                continue
            kinds = types.setdefault((table, name), set())
            parent = column.parent
            while parent is not None:
                if isinstance(parent, _NUMERIC + _NUMERIC_AGGS):
                    kinds.add("numeric")
                    break
                parent = parent.parent
    out = []
    for (table, name), kinds in sorted(types.items()):
        out.append(ReferencedColumn(table, name, "REAL" if "numeric" in kinds else "TEXT"))
    return out


def _tables(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        row[0].lower(): row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({_quote(table)})")}


def applicable_tables(conn: sqlite3.Connection, table: str) -> list[str]:
    names = _tables(conn)
    if table.lower() in names:
        return [names[table.lower()]]
    if "fact" in names:
        return [names["fact"]]
    return []


def ensure_referenced_columns(
    conn: sqlite3.Connection,
    statements: dict[str, str] | Iterable[str],
) -> list[tuple[str, str, str]]:
    """Add a typed NULL column for every referenced attribute that is absent."""

    added: list[tuple[str, str, str]] = []
    for item in referenced_columns(statements):
        for table in applicable_tables(conn, item.table):
            have = _columns(conn, table)
            if item.column in have:
                continue
            conn.execute(
                f"ALTER TABLE {_quote(table)} ADD COLUMN {_quote(item.column)} {item.sql_type}"
            )
            added.append((table, item.column, item.sql_type))
    return added


def missing_column_error(exc: BaseException) -> bool:
    return "no such column" in str(exc).lower()


def assert_queries_execute(
    conn: sqlite3.Connection,
    statements: dict[str, str],
) -> None:
    """Every statement must run without a missing-column error."""

    failures: list[tuple[str, str]] = []
    for query_id, sql in statements.items():
        if not sql:
            continue
        try:
            conn.execute(sql)
        except sqlite3.Error as exc:
            if missing_column_error(exc):
                failures.append((query_id, str(exc)))
    if failures:
        detail = "; ".join(f"{qid}: {msg}" for qid, msg in failures)
        raise MissingColumnError(detail)


def ensure_and_assert(
    sqlite_path: str | Path,
    statements: dict[str, str],
    rewritten: dict[str, str] | None = None,
) -> list[tuple[str, str, str]]:
    conn = sqlite3.connect(str(sqlite_path))
    try:
        added = ensure_referenced_columns(conn, statements)
        conn.commit()
        assert_queries_execute(conn, rewritten or statements)
        return added
    finally:
        conn.close()
