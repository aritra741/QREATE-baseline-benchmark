"""Query-level support sets. A' universe only. No gold."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from sqlglot import exp

from quwarts.core.pipeline import official_sql
from quwarts.core.signature import AtomicPredicate, table_aliases
from quwarts.core.workload import _default_entity, parse_sql

_AGGS = (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)


@dataclass
class QueryShape:
    query_id: str
    sql: str
    tables: tuple[str, ...]
    aliases: dict[str, str]
    primary: str
    primary_alias: str
    group_aliases: tuple[str, ...]
    group_sql: tuple[str, ...]
    aggregates: tuple[tuple[str, str], ...]
    join_pairs: tuple[tuple[str, str], ...]


@dataclass
class SupportRow:
    entity_id: str
    rowid: int
    included: str
    group_key: dict[str, Any]
    join_partner_ids: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    flags: dict[str, int] = field(default_factory=dict)
    source: str = ""


def _ident(node: exp.Expression | None) -> str:
    if node is None:
        return ""
    return (node.alias or node.name or "").lower()


def query_shape(query_id: str, sql: str) -> QueryShape:
    tree = parse_sql(sql)
    aliases = table_aliases(tree)
    default = _default_entity(tree) or ""
    tables = tuple(dict.fromkeys(aliases.values() or ([default] if default else [])))
    primary_alias = ""
    primary = default
    for table in tree.find_all(exp.Table):
        primary_alias = table.alias or table.name
        primary = table.name.lower()
        break
    for proj in tree.expressions:
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        count = expr.find(exp.Count) if not isinstance(expr, exp.Count) else expr
        if count is None:
            continue
        for col in count.find_all(exp.Column):
            if col.table:
                primary_alias = col.table
                primary = aliases.get(col.table.lower(), col.table.lower())
    groups: list[tuple[str, str]] = []
    aggs: list[tuple[str, str]] = []
    for index, proj in enumerate(tree.expressions):
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        alias = proj.alias if isinstance(proj, exp.Alias) else f"c{index}"
        if expr.find(_AGGS):
            kind = "count_distinct" if expr.find(exp.Distinct) else ("sum" if expr.find(exp.Sum) else "count")
            aggs.append((alias, kind))
        else:
            groups.append((alias, expr.sql(dialect="sqlite")))
    joins: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    names = [primary] + [name for name in tables if name != primary]
    for left, right in zip(names, names[1:]):
        key = tuple(sorted((left, right)))
        if key in seen:
            continue
        seen.add(key)
        joins.append((left, right))
    return QueryShape(
        query_id=query_id,
        sql=sql,
        tables=tables,
        aliases=aliases,
        primary=primary,
        primary_alias=primary_alias or primary,
        group_aliases=tuple(name for name, _ in groups),
        group_sql=tuple(expr for _, expr in groups),
        aggregates=tuple(aggs),
        join_pairs=tuple(joins),
    )


def grain_sql(sql: str) -> str:
    """Same FROM/JOIN/WHERE as the count query; one row per contributing grain."""

    tree = parse_sql(sql)
    if not isinstance(tree, exp.Select):
        return sql
    kept: list[exp.Expression] = []
    for table in tree.find_all(exp.Table):
        qual = table.alias or table.name
        kept.append(
            exp.alias_(
                exp.Column(this=exp.to_identifier("rowid"), table=exp.to_identifier(qual)),
                f"{qual}__rid",
            )
        )
    for proj in tree.expressions:
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        if expr.find(_AGGS):
            continue
        kept.append(proj)
    if not kept:
        kept.append(exp.Literal.number(1))
    tree.set("expressions", kept)
    tree.set("group", None)
    tree.set("having", None)
    tree.set("order", None)
    return tree.sql(dialect="sqlite")


def _execute(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    try:
        cur = conn.execute(sql)
    except sqlite3.Error:
        return []
    cols = [item[0] for item in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def aprime_support(
    sqlite_path: str | Path,
    shape: QueryShape,
    predicates: Iterable[AtomicPredicate] | None = None,
    rid_to_entity: dict[int, str] | None = None,
) -> list[SupportRow]:
    conn = sqlite3.connect(str(sqlite_path))
    try:
        sql = official_sql(grain_sql(shape.sql), sqlite_path, list(predicates or []))
        rows = _execute(conn, sql)
    finally:
        conn.close()
    alias = shape.primary_alias
    mapping = rid_to_entity or {}
    out: list[SupportRow] = []
    for row in rows:
        rid = row.get(f"{alias}__rid")
        rid_i = int(rid or 0)
        entity = mapping.get(rid_i) or str(rid_i)
        groups = {name: row.get(name) for name in shape.group_aliases}
        out.append(
            SupportRow(
                entity_id=str(entity),
                rowid=rid_i,
                included="true",
                group_key=groups,
                source="aprime",
            )
        )
    return out


def universe(
    sqlite_path: str | Path,
    shape: QueryShape,
    documents: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    docs = documents or {}
    try:
        table = shape.primary
        cols = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
        rows = []
        for raw in conn.execute(f'SELECT rowid AS _rid, * FROM "{table}"'):
            payload = dict(raw)
            rid = int(payload.pop("_rid"))
            doc_id = payload.get("doc_id") or payload.get("id")
            name = (
                payload.get("generic_name")
                or payload.get("disease_name")
                or payload.get("institution_name")
                or payload.get("name")
                or doc_id
            )
            rows.append(
                {
                    "rowid": rid,
                    "entity_id": str(doc_id or rid),
                    "label": str(name or ""),
                    "table": table,
                    "cells": {key: payload.get(key) for key in payload if not str(key).startswith("sig_")},
                    "document": docs.get(str(doc_id), docs.get(Path(str(doc_id)).stem, "")),
                }
            )
        return rows
    finally:
        conn.close()


def count_from_support(shape: QueryShape, rows: Iterable[SupportRow]) -> list[dict[str, Any]]:
    kept = [row for row in rows if row.included == "true"]
    if not kept:
        return []
    buckets: dict[tuple[Any, ...], list[SupportRow]] = defaultdict(list)
    for row in kept:
        key = _freeze(tuple(row.group_key.get(name) for name in shape.group_aliases))
        buckets[key].append(row)
    out = []
    for key, items in buckets.items():
        record = {name: value for name, value in zip(shape.group_aliases, key)}
        ids = {item.entity_id for item in items}
        for alias, kind in shape.aggregates:
            if kind == "count_distinct":
                record[alias] = len(ids)
            elif kind == "sum":
                record[alias] = sum(int(item.flags.get(alias) or 0) for item in items)
            else:
                record[alias] = len(items)
        out.append(record)
    return out


def aprime_counts(sqlite_path: str | Path, sql: str, predicates: Iterable[AtomicPredicate] | None = None) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(sqlite_path))
    try:
        return _execute(conn, official_sql(sql, sqlite_path, predicates or []))
    finally:
        conn.close()


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def support_key(row: SupportRow) -> tuple[str, tuple[tuple[str, Any], ...]]:
    return (row.entity_id, _freeze(row.group_key))


def symmetric_diff(left: list[SupportRow], right: list[SupportRow]) -> list[str]:
    a = {support_key(row) for row in left if row.included == "true"}
    b = {support_key(row) for row in right if row.included == "true"}
    return sorted({item[0] for item in a.symmetric_difference(b)})


def clip_context(text: str, needle: str | None = None, limit: int = 700) -> str:
    body = text or ""
    if needle:
        index = body.lower().find(str(needle).lower())
        if index >= 0:
            start = max(0, index - limit // 4)
            return body[start : start + limit]
    return body[:limit]
