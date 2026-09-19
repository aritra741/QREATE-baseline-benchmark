"""Query-local component oracles. Sidecars only; base tables are never updated."""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any, Iterable

from sqlglot import exp

from quwarts.core.distinct_diag import extract_distinct_measures
from quwarts.core.query_filter import (
    _outer_tables,
    alias_order,
    has_row_filter,
)
from quwarts.core.query_support import query_shape
from quwarts.core.workload import parse_sql

COMPONENTS = (
    "base_row",
    "filter",
    "join",
    "group",
    "presence",
    "distinct",
    "full_witness",
)
SIDECAR_TABLES = {
    "base_row": "oracle_base",
    "filter": "oracle_filter",
    "join": "oracle_join",
    "group": "oracle_group",
    "presence": "oracle_presence",
    "distinct": "oracle_distinct",
}
ALL_SIDECARS = tuple(SIDECAR_TABLES.values())

DDL = {
    "oracle_base": """
CREATE TABLE IF NOT EXISTS oracle_base (
  table_name TEXT NOT NULL,
  stem TEXT NOT NULL,
  available INTEGER NOT NULL,
  PRIMARY KEY (table_name, stem)
)""",
    "oracle_filter": """
CREATE TABLE IF NOT EXISTS oracle_filter (
  query_id TEXT NOT NULL,
  witness_key TEXT NOT NULL,
  admit INTEGER NOT NULL,
  old_admit INTEGER,
  PRIMARY KEY (query_id, witness_key)
)""",
    "oracle_join": """
CREATE TABLE IF NOT EXISTS oracle_join (
  query_id TEXT NOT NULL,
  join_id TEXT NOT NULL,
  left_key TEXT NOT NULL,
  right_key TEXT NOT NULL,
  admit INTEGER NOT NULL,
  old_admit INTEGER,
  PRIMARY KEY (query_id, join_id, left_key, right_key)
)""",
    "oracle_group": """
CREATE TABLE IF NOT EXISTS oracle_group (
  query_id TEXT NOT NULL,
  alias TEXT NOT NULL,
  witness_key TEXT NOT NULL,
  label TEXT,
  old_label TEXT,
  PRIMARY KEY (query_id, alias, witness_key)
)""",
    "oracle_presence": """
CREATE TABLE IF NOT EXISTS oracle_presence (
  query_id TEXT NOT NULL,
  measure TEXT NOT NULL,
  witness_key TEXT NOT NULL,
  present INTEGER NOT NULL,
  old_present INTEGER,
  PRIMARY KEY (query_id, measure, witness_key)
)""",
    "oracle_distinct": """
CREATE TABLE IF NOT EXISTS oracle_distinct (
  query_id TEXT NOT NULL,
  measure TEXT NOT NULL,
  witness_key TEXT NOT NULL,
  is_null INTEGER NOT NULL,
  partition TEXT,
  old_null INTEGER,
  old_partition TEXT,
  PRIMARY KEY (query_id, measure, witness_key)
)""",
}


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def uses_component(sql: str, component: str) -> bool:
    if component == "full_witness":
        return True
    if component == "base_row":
        return True
    if component == "filter":
        return has_row_filter(sql)
    try:
        tree = parse_sql(sql)
    except Exception:
        return False
    if component == "join":
        return any(True for _ in tree.find_all(exp.Join))
    if component == "group":
        shape = query_shape("q", sql)
        return bool(shape.group_aliases)
    if component == "presence":
        return any(
            isinstance(node, exp.Count)
            and not node.args.get("distinct")
            and not isinstance(node.this, exp.Distinct)
            and not (node.args.get("star") or isinstance(node.this, exp.Star) or node.this is None)
            for node in tree.find_all(exp.Count)
        )
    if component == "distinct":
        return bool(extract_distinct_measures(sql))
    return False


def ensure_oracle_tables(conn: sqlite3.Connection) -> None:
    for ddl in DDL.values():
        conn.execute(ddl)


def user_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%' "
            "AND name NOT LIKE 'oracle_%' AND name NOT LIKE 'filter_additions' "
            "AND name NOT LIKE 'group_labels'"
        )
    ]


def table_schemas(conn: sqlite3.Connection) -> dict[str, list[str]]:
    return {
        table: [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
        for table in user_tables(conn)
    }


def base_checksums(conn: sqlite3.Connection) -> dict[str, str]:
    out = {}
    for table in user_tables(conn):
        rows = conn.execute(f"SELECT * FROM {_quote(table)} ORDER BY rowid").fetchall()
        out[table] = hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()
    return out


def sidecar_counts(conn: sqlite3.Connection) -> dict[str, int]:
    have = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    out = {}
    for name in ALL_SIDECARS:
        out[name] = 0 if name not in have else int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
    return out


def declared_sidecars(component: str) -> set[str]:
    if component == "full_witness":
        return set(ALL_SIDECARS)
    return {SIDECAR_TABLES[component]}


def write_set_ok(conn: sqlite3.Connection, component: str, before: dict[str, str]) -> dict[str, Any]:
    after = base_checksums(conn)
    changed_base = [table for table, digest in after.items() if before.get(table) != digest]
    counts = sidecar_counts(conn)
    allowed = declared_sidecars(component)
    extra = [name for name, n in counts.items() if n and name not in allowed]
    empty_allowed = [name for name in allowed if counts.get(name, 0) == 0]
    return {
        "ok": not changed_base and not extra,
        "changed_base": changed_base,
        "extra_sidecars": extra,
        "sidecar_counts": counts,
        "empty_declared": empty_allowed,
    }


def _qid(value: str) -> str:
    return value.replace("'", "''")


def stem_sql(alias: str) -> str:
    doc = f"{_quote(alias)}.doc_id"
    ident = f"{_quote(alias)}.id"
    last = (
        f"CASE WHEN instr({doc}, '/') > 0 THEN substr({doc}, instr({doc}, '/') + 1) ELSE {doc} END"
    )
    return (
        f"COALESCE("
        f"CASE WHEN {doc} IS NULL THEN NULL "
        f"ELSE replace(replace({last}, '.txt', ''), '.json', '') END, "
        f"CAST({ident} AS TEXT))"
    )


def stem_key_sql(tree: exp.Expression) -> str:
    parts = [f"COALESCE({stem_sql(alias)}, 'NULL')" for alias in alias_order(tree)]
    if not parts:
        return "'NULL'"
    if len(parts) == 1:
        return parts[0]
    return " || '|' || ".join(parts)


def rewrite_filter(sql: str, query_id: str) -> str:
    if not uses_component(sql, "filter"):
        return sql
    tree = parse_sql(sql)
    if not isinstance(tree, exp.Select) or tree.args.get("where") is None:
        return sql
    current = tree.args["where"].this.sql(dialect="sqlite")
    if "oracle_filter" in current.lower():
        return sql
    key = stem_key_sql(tree)
    qid = _qid(query_id)
    wrapped = parse_sql(
        f"(({current}) OR EXISTS (SELECT 1 FROM oracle_filter f "
        f"WHERE f.query_id = '{qid}' AND f.witness_key = {key} AND f.admit = 1)) "
        f"AND NOT EXISTS (SELECT 1 FROM oracle_filter f "
        f"WHERE f.query_id = '{qid}' AND f.witness_key = {key} AND f.admit = 0)"
    )
    tree.set("where", exp.Where(this=wrapped))
    return tree.sql(dialect="sqlite")


def rewrite_join(sql: str, query_id: str, joins: Iterable[Any]) -> str:
    if not uses_component(sql, "join"):
        return sql
    tree = parse_sql(sql)
    if not isinstance(tree, exp.Select):
        return sql
    qid = _qid(query_id)
    by_alias = {(item.left_alias, item.right_alias): item for item in joins}
    for join in tree.find_all(exp.Join):
        table = join.this
        right = (getattr(table, "alias", None) or getattr(table, "name", None) or "").lower()
        on = join.args.get("on")
        if on is None:
            continue
        left = None
        for item in joins:
            if item.right_alias == right:
                left = item.left_alias
                spec = item
                break
        if left is None:
            continue
        current = on.sql(dialect="sqlite")
        if "oracle_join" in current.lower():
            continue
        jid = _qid(spec.join_id)
        left_key = f"CAST({stem_sql(left)} AS TEXT)"
        right_key = f"CAST({stem_sql(right)} AS TEXT)"
        wrapped = parse_sql(
            f"(({current}) OR EXISTS (SELECT 1 FROM oracle_join j "
            f"WHERE j.query_id = '{qid}' AND j.join_id = '{jid}' "
            f"AND j.left_key = {left_key} AND j.right_key = {right_key} AND j.admit = 1)) "
            f"AND NOT EXISTS (SELECT 1 FROM oracle_join j "
            f"WHERE j.query_id = '{qid}' AND j.join_id = '{jid}' "
            f"AND j.left_key = {left_key} AND j.right_key = {right_key} AND j.admit = 0)"
        )
        join.set("on", wrapped)
    return tree.sql(dialect="sqlite")


def rewrite_group(sql: str, query_id: str, group_aliases: Iterable[str]) -> str:
    aliases = {str(name).lower() for name in group_aliases}
    if not aliases:
        return sql
    tree = parse_sql(sql)
    if not isinstance(tree, exp.Select):
        return sql
    key = stem_key_sql(tree)
    qid = _qid(query_id)
    replaced = []
    for proj in tree.expressions:
        alias = (proj.alias if isinstance(proj, exp.Alias) else "").lower()
        if alias not in aliases:
            replaced.append(proj)
            continue
        inner = proj.this.sql(dialect="sqlite") if isinstance(proj, exp.Alias) else proj.sql(dialect="sqlite")
        if "oracle_group" in inner.lower():
            replaced.append(proj)
            continue
        wrapped = parse_sql(
            f"COALESCE((SELECT g.label FROM oracle_group g WHERE g.query_id = '{qid}' "
            f"AND g.alias = '{_qid(alias)}' AND g.witness_key = {key}), {inner})"
        )
        replaced.append(exp.alias_(wrapped, alias))
    tree.set("expressions", replaced)
    return tree.sql(dialect="sqlite")


def rewrite_presence(sql: str, query_id: str) -> str:
    if not uses_component(sql, "presence"):
        return sql
    tree = parse_sql(sql)
    if not isinstance(tree, exp.Select):
        return sql
    key = stem_key_sql(tree)
    qid = _qid(query_id)
    for proj in tree.expressions:
        alias = proj.alias if isinstance(proj, exp.Alias) else "n"
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        count = expr if isinstance(expr, exp.Count) else None
        if count is None or count.args.get("distinct") or isinstance(count.this, exp.Distinct):
            continue
        if count.args.get("star") or isinstance(count.this, exp.Star) or count.this is None:
            continue
        inner = count.this.sql(dialect="sqlite")
        if "oracle_presence" in inner.lower():
            continue
        flag = (
            f"COALESCE((SELECT p.present FROM oracle_presence p WHERE p.query_id = '{qid}' "
            f"AND p.measure = '{_qid(alias)}' AND p.witness_key = {key}), "
            f"CASE WHEN {inner} IS NULL OR CAST({inner} AS TEXT) = '' THEN 0 ELSE 1 END)"
        )
        count.set("this", parse_sql(f"CASE WHEN ({flag}) = 1 THEN 1 END"))
    return tree.sql(dialect="sqlite")


def rewrite_distinct(sql: str, query_id: str) -> str:
    measures = extract_distinct_measures(sql)
    if not measures:
        return sql
    tree = parse_sql(sql)
    if not isinstance(tree, exp.Select):
        return sql
    key = stem_key_sql(tree)
    qid = _qid(query_id)
    by_alias = {item["alias"]: item for item in measures}
    for proj in tree.expressions:
        alias = proj.alias if isinstance(proj, exp.Alias) else None
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        count = expr if isinstance(expr, exp.Count) else None
        if count is None or alias not in by_alias:
            continue
        if not (count.args.get("distinct") or isinstance(count.this, exp.Distinct)):
            continue
        inner = count.this
        if isinstance(inner, exp.Distinct) and inner.expressions:
            payload = inner.expressions[0]
        else:
            payload = inner
        current = payload.sql(dialect="sqlite") if payload is not None else "NULL"
        if "oracle_distinct" in current.lower():
            continue
        swapped = parse_sql(
            f"CASE WHEN EXISTS (SELECT 1 FROM oracle_distinct d WHERE d.query_id = '{qid}' "
            f"AND d.measure = '{_qid(alias)}' AND d.witness_key = {key} AND d.is_null = 1) "
            f"THEN NULL ELSE COALESCE((SELECT d.partition FROM oracle_distinct d "
            f"WHERE d.query_id = '{qid}' AND d.measure = '{_qid(alias)}' "
            f"AND d.witness_key = {key} AND d.is_null = 0), {current}) END"
        )
        if isinstance(inner, exp.Distinct):
            inner.set("expressions", [swapped])
        else:
            count.set("this", exp.Distinct(expressions=[swapped]))
            count.set("distinct", True)
    extra = []
    measure_sql = {item["sql"] for item in measures}
    for proj in tree.expressions:
        alias = (proj.alias if isinstance(proj, exp.Alias) else "").lower()
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        if isinstance(expr, exp.Count):
            extra.append(proj)
            continue
        current = expr.sql(dialect="sqlite")
        if alias not in {"distinct_value"} and not alias.startswith("distinct_") and current not in measure_sql:
            extra.append(proj)
            continue
        if "oracle_distinct" in current.lower():
            extra.append(proj)
            continue
        measure = alias if alias in by_alias else next(iter(by_alias), "n")
        swapped = parse_sql(
            f"CASE WHEN EXISTS (SELECT 1 FROM oracle_distinct d WHERE d.query_id = '{qid}' "
            f"AND d.measure = '{_qid(measure)}' AND d.witness_key = {key} AND d.is_null = 1) "
            f"THEN NULL ELSE COALESCE((SELECT d.partition FROM oracle_distinct d "
            f"WHERE d.query_id = '{qid}' AND d.measure = '{_qid(measure)}' "
            f"AND d.witness_key = {key} AND d.is_null = 0), {current}) END"
        )
        extra.append(exp.alias_(swapped, alias or measure))
    if extra:
        tree.set("expressions", extra)
    return tree.sql(dialect="sqlite")


def rewrite_base(
    sql: str,
    tables: Iterable[str],
    schemas: dict[str, list[str]] | None = None,
) -> str:
    wanted = {str(name).lower() for name in tables}
    if not wanted:
        return sql
    tree = parse_sql(sql)
    if not isinstance(tree, exp.Select):
        return sql
    schemas = {str(name).lower(): list(cols) for name, cols in (schemas or {}).items()}
    for table in list(_outer_tables(tree)):
        name = (table.name or "").lower()
        alias = (table.alias or table.name or "").lower()
        if name not in wanted or "oracle_base" in table.sql(dialect="sqlite").lower():
            continue
        hide = (
            f"SELECT * FROM {_quote(name)} AS {_quote(alias)} WHERE NOT EXISTS ("
            f"SELECT 1 FROM oracle_base b WHERE b.table_name = '{_qid(name)}' "
            f"AND b.stem = {stem_sql(alias)} AND b.available = 0)"
        )
        cols = schemas.get(name) or []
        if cols:
            proj = []
            for col in cols:
                low = col.lower()
                if low == "doc_id":
                    proj.append(f"'{_qid(name)}/' || b.stem || '.txt' AS {_quote(col)}")
                elif low == "id":
                    proj.append(f"b.stem AS {_quote(col)}")
                else:
                    proj.append(f"NULL AS {_quote(col)}")
            inject = (
                f"SELECT {', '.join(proj)} FROM oracle_base b "
                f"WHERE b.table_name = '{_qid(name)}' AND b.available = 1 AND NOT EXISTS ("
                f"SELECT 1 FROM {_quote(name)} t WHERE {stem_sql('t')} = b.stem)"
            )
            source = f"({hide} UNION ALL {inject})"
        else:
            source = f"({hide})"
        table.replace(exp.alias_(parse_sql(source), alias, table=True))
    return tree.sql(dialect="sqlite")


def apply_component_sql(
    sql: str,
    query_id: str,
    component: str,
    *,
    joins: Iterable[Any] = (),
    group_aliases: Iterable[str] = (),
    tables: Iterable[str] = (),
    schemas: dict[str, list[str]] | None = None,
) -> str:
    out = sql
    if component in {None, "", "incumbent"}:
        return out
    if component in {"join", "full_witness"}:
        out = rewrite_join(out, query_id, joins)
    if component in {"filter", "full_witness"}:
        out = rewrite_filter(out, query_id)
    if component in {"group", "full_witness"}:
        out = rewrite_group(out, query_id, group_aliases)
    if component in {"presence", "full_witness"}:
        out = rewrite_presence(out, query_id)
    if component in {"distinct", "full_witness"}:
        out = rewrite_distinct(out, query_id)
    if component in {"base_row", "full_witness"}:
        out = rewrite_base(out, tables, schemas)
    return out


def from_join_sql(sql: str) -> str:
    from quwarts.core.query_support import grain_sql

    tree = parse_sql(grain_sql(sql))
    if isinstance(tree, exp.Select):
        tree.set("where", None)
        tree.set("having", None)
        tree.set("group", None)
        tree.set("order", None)
    return tree.sql(dialect="sqlite")


def with_predicate_flag(sql: str, expr: exp.Expression | None, alias: str) -> str:
    from quwarts.core.query_support import grain_sql

    tree = parse_sql(grain_sql(sql))
    if not isinstance(tree, exp.Select):
        return sql
    tree.set("where", None)
    tree.set("having", None)
    tree.set("group", None)
    tree.set("order", None)
    flag = expr if expr is not None else exp.Literal.number(1)
    tree.set("expressions", list(tree.expressions) + [exp.alias_(flag, alias)])
    return tree.sql(dialect="sqlite")
