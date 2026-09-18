"""Expression-local group signatures and join edges. Base columns stay immutable."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from sqlglot import exp

from quwarts.core.query_witness import JoinSpec, WitnessSpec, compile_witness_spec, group_sig_names
from quwarts.core.signature import table_aliases
from quwarts.core.workload import parse_sql

_AGGS = (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)

EDGES_DDL = """
CREATE TABLE IF NOT EXISTS signature_edges (
  join_signature_id TEXT NOT NULL,
  left_rowid INTEGER NOT NULL,
  right_rowid INTEGER NOT NULL,
  truth INTEGER,
  resolved INTEGER,
  provenance TEXT,
  PRIMARY KEY (join_signature_id, left_rowid, right_rowid)
)
"""


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _tables(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        row[0].lower(): row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({_quote(table)})")}


def ensure_edge_table(conn: sqlite3.Connection) -> None:
    conn.execute(EDGES_DDL)


def ensure_group_columns(conn: sqlite3.Connection, specs: Iterable[WitnessSpec]) -> list[tuple[str, str]]:
    added: list[tuple[str, str]] = []
    names = _tables(conn)
    for spec in specs:
        table = names.get(spec.primary.lower())
        if table is None:
            continue
        have = _columns(conn, table)
        for expr in spec.group_sql:
            sig, resolved = group_sig_names(expr)
            if sig not in have:
                conn.execute(f"ALTER TABLE {_quote(table)} ADD COLUMN {_quote(sig)} TEXT")
                have.add(sig)
                added.append((table, sig))
            if resolved not in have:
                conn.execute(
                    f"ALTER TABLE {_quote(table)} ADD COLUMN {_quote(resolved)} INTEGER DEFAULT 0"
                )
                have.add(resolved)
                added.append((table, resolved))
    return added


def snapshot_edges(conn: sqlite3.Connection) -> set[tuple[Any, ...]]:
    names = _tables(conn)
    if "signature_edges" not in names:
        return set()
    return {
        tuple(row)
        for row in conn.execute(
            "SELECT join_signature_id, left_rowid, right_rowid, truth, resolved FROM signature_edges"
        )
    }


def add_edge(
    conn: sqlite3.Connection,
    join_id: str,
    left_rowid: int,
    right_rowid: int,
    provenance: str = "residual",
) -> bool:
    ensure_edge_table(conn)
    existing = conn.execute(
        "SELECT resolved, truth FROM signature_edges "
        "WHERE join_signature_id = ? AND left_rowid = ? AND right_rowid = ?",
        [join_id, left_rowid, right_rowid],
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO signature_edges "
            "(join_signature_id, left_rowid, right_rowid, truth, resolved, provenance) "
            "VALUES (?, ?, ?, 1, 1, ?)",
            [join_id, left_rowid, right_rowid, provenance],
        )
        return True
    if int(existing[0] or 0) == 1:
        return False
    conn.execute(
        "UPDATE signature_edges SET truth = 1, resolved = 1, provenance = ? "
        "WHERE join_signature_id = ? AND left_rowid = ? AND right_rowid = ? AND resolved IS NOT 1",
        [provenance, join_id, left_rowid, right_rowid],
    )
    return True


def write_group(
    conn: sqlite3.Connection,
    table: str,
    rowid: int,
    expr_sql: str,
    value: Any,
    incumbent_rowids: set[int],
) -> None:
    if rowid in incumbent_rowids or value in (None, "", "unknown"):
        return
    sig, resolved = group_sig_names(expr_sql)
    cols = _columns(conn, table)
    if sig not in cols or resolved not in cols:
        return
    conn.execute(
        f"UPDATE {_quote(table)} SET {_quote(sig)} = ?, {_quote(resolved)} = 1 WHERE rowid = ?",
        [str(value), rowid],
    )


def _has_edges(sqlite_path: str | Path) -> bool:
    conn = sqlite3.connect(str(sqlite_path))
    try:
        return "signature_edges" in _tables(conn)
    finally:
        conn.close()


def _group_columns(sqlite_path: str | Path) -> dict[str, set[str]]:
    conn = sqlite3.connect(str(sqlite_path))
    try:
        found: dict[str, set[str]] = {}
        for table in _tables(conn).values():
            cols = {col for col in _columns(conn, table) if col.startswith("sig_group_")}
            if cols:
                found[table.lower()] = cols
        return found
    finally:
        conn.close()


def _wrap_case(resolved: exp.Expression, truth: exp.Expression, original: exp.Expression) -> exp.Case:
    case = exp.Case()
    case.set(
        "ifs",
        [exp.If(this=exp.EQ(this=resolved, expression=exp.Literal.number(1)), true=truth)],
    )
    case.set("default", original)
    return case


def rewrite_group_sql(sql: str, sqlite_path: str | Path) -> str:
    available = _group_columns(sqlite_path)
    if not available:
        return sql
    try:
        tree = parse_sql(sql)
    except Exception:
        return sql
    if not isinstance(tree, exp.Select):
        return sql
    aliases = table_aliases(tree)
    default = next(iter(aliases.values()), None)
    skip = set()
    for proj in tree.expressions:
        if isinstance(proj, exp.Alias) and proj.alias:
            skip.add(proj.alias.lower())
    changed = False

    def _owner(expr: exp.Expression) -> tuple[str, str] | None:
        for col in expr.find_all(exp.Column):
            raw = (col.table or "").lower()
            table = aliases.get(raw, raw or (default or ""))
            if table and table in available:
                return table, raw or table
        table = default or ""
        if table in available:
            return table, next((alias for alias, name in aliases.items() if name == table), table)
        return None

    def _wrap(expr: exp.Expression) -> exp.Expression:
        nonlocal changed
        if expr.find(_AGGS):
            return expr
        if isinstance(expr, exp.Column) and (expr.name or "").lower() in skip:
            return expr
        owner = _owner(expr)
        if owner is None:
            return expr
        table, qualifier = owner
        sig, resolved = group_sig_names(expr.sql(dialect="sqlite"))
        if sig not in available[table] or resolved not in available[table]:
            return expr
        changed = True
        qual = exp.to_identifier(qualifier) if qualifier else None
        return _wrap_case(
            exp.Column(this=exp.to_identifier(resolved), table=qual),
            exp.Column(this=exp.to_identifier(sig), table=qual),
            expr.copy(),
        )

    new_proj = []
    for proj in tree.expressions:
        if isinstance(proj, exp.Alias):
            new_proj.append(exp.alias_(_wrap(proj.this), proj.alias))
        else:
            new_proj.append(_wrap(proj))
    tree.set("expressions", new_proj)
    group = tree.args.get("group")
    if group is not None:
        group.set("expressions", [_wrap(item) for item in group.expressions])
    return tree.sql(dialect="sqlite") if changed else sql


def rewrite_edge_sql(sql: str, sqlite_path: str | Path) -> str:
    if not _has_edges(sqlite_path):
        return sql
    try:
        spec = compile_witness_spec("rewrite", sql)
    except Exception:
        return sql
    if not spec.joins:
        return sql
    try:
        tree = parse_sql(sql)
    except Exception:
        return sql
    joins = list(tree.find_all(exp.Join))
    if not joins:
        return sql
    by_on = {_norm_join(item.on_sql): item for item in spec.joins}
    changed = False
    for join in joins:
        on = join.args.get("on")
        if on is None:
            continue
        on_sql = on.sql(dialect="sqlite")
        item = by_on.get(_norm_join(on_sql))
        if item is None:
            continue
        join.set("on", _edge_predicate(item, on.copy()))
        changed = True
    return tree.sql(dialect="sqlite") if changed else sql


def _norm_join(sql: str) -> str:
    return " ".join((sql or "").lower().split())


def _edge_predicate(item: JoinSpec, original: exp.Expression) -> exp.Expression:
    join_id = item.join_id.replace("'", "''")
    left = f'"{item.left_alias}"."rowid"'
    right = f'"{item.right_alias}"."rowid"'
    lookup = (
        f"SELECT {{col}} FROM signature_edges "
        f"WHERE join_signature_id = '{join_id}' AND left_rowid = {left} "
        f"AND right_rowid = {right}"
    )
    wrapped = (
        f"CASE WHEN ({lookup.format(col='resolved')}) = 1 "
        f"THEN ({lookup.format(col='truth')}) "
        f"ELSE ({original.sql(dialect='sqlite')}) END"
    )
    return parse_sql(wrapped)


def rewrite_signature_views(sql: str, sqlite_path: str | Path) -> str:
    sql = rewrite_group_sql(sql, sqlite_path)
    return rewrite_edge_sql(sql, sqlite_path)


def related_canonicals(spec: WitnessSpec, predicates: Iterable[Any]) -> set[str]:
    found = {item.join_id for item in spec.joins}
    for expr in spec.group_sql:
        found.add(group_sig_names(expr)[0])
    for pred in predicates:
        if spec.query_id in getattr(pred, "query_ids", ()):
            found.add(pred.pred_id)
    return found
