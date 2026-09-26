"""Zero-token SQL-sensitive residue on an incumbent database.

The residue of attribute ``a`` counts incumbent rows whose value of ``a``
makes some workload condition evaluate to SQL UNKNOWN, or that are NULL where
the workload groups, aggregates, or projects ``a``. Repair work is proportional
to this residue, not to corpus size.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from quwarts.core.router.constants import FROZEN
from quwarts.core.router.corpus_features import deterministic_sample
from quwarts.core.router.registry import CorpusSpec
from quwarts.core.router.text import grounded, is_null, prepare_document
from quwarts.core.router.workload_features import alias_map, resolve_column, table_attribute_names


def _conjuncts(node: exp.Expression) -> list[exp.Expression]:
    if isinstance(node, exp.And):
        return _conjuncts(node.left) + _conjuncts(node.right)
    if isinstance(node, exp.Paren):
        return _conjuncts(node.this)
    return [node]


def conditions(tree: exp.Expression) -> list[exp.Expression]:
    """WHERE conjuncts and CASE WHEN conditions of one statement."""

    found: list[exp.Expression] = []
    for where in tree.find_all(exp.Where):
        found.extend(_conjuncts(where.this))
    for case in tree.find_all(exp.Case):
        for branch in case.args.get("ifs") or []:
            found.append(branch.this)
    return found


def _single_table_sql(node: exp.Expression, aliases: dict[str, str], table_attrs: dict[str, set[str]]) -> tuple[str, str, list[str]] | None:
    columns = list(node.find_all(exp.Column))
    if not columns or node.find(exp.Subquery, exp.Select):
        return None
    tables = {resolve_column(column, aliases, table_attrs) for column in columns}
    if len(tables) != 1 or None in tables:
        return None
    table = tables.pop()
    copy = node.copy()
    for column in copy.find_all(exp.Column):
        column.set("table", None)
    return table, copy.sql(dialect="sqlite"), sorted({column.name for column in columns})


def _db_columns(conn: sqlite3.Connection) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')"):
        out[name] = {row[1] for row in conn.execute(f'PRAGMA table_info("{name}")')}
    return out


def _doc_path(spec: CorpusSpec, table: str, doc_id: str) -> Path | None:
    table_spec = spec.table(table)
    if table_spec is None or not doc_id:
        return None
    path = table_spec.doc_dir / Path(str(doc_id)).name
    return path if path.is_file() else None


def incumbent_grounding(conn, spec: CorpusSpec, table: str, attribute: str, columns: set[str]) -> float | None:
    """Share of the incumbent's non-null values that are spans of their source document."""

    if "doc_id" not in columns:
        return None
    rows = conn.execute(
        f'SELECT doc_id, "{attribute}" FROM "{table}" WHERE "{attribute}" IS NOT NULL'
    ).fetchall()
    rows = [row for row in rows if not is_null(row[1])]
    rows = deterministic_sample(rows, 30, f"ground:{table}.{attribute}")
    checked = hits = 0
    for doc_id, value in rows:
        path = _doc_path(spec, table, doc_id)
        if path is None:
            continue
        checked += 1
        hits += grounded(value, prepare_document(path.read_text(errors="replace")))
    return hits / checked if checked else None



_CHOICES = re.compile(r"\[([^\]]+)\]")


def declared_labels(use) -> set[str]:
    """Closed label vocabulary: the workload's compared literals."""

    # SQL-only: the values the workload compares the attribute with.
    return {label.lower() for label in use.literals}


def incumbent_label_validity(conn, table: str, attribute: str, labels: set[str]) -> float | None:
    """Share of non-null incumbent values inside the declared label vocabulary."""

    if not labels:
        return None
    rows = [row[0] for row in conn.execute(f'SELECT "{attribute}" FROM "{table}" WHERE "{attribute}" IS NOT NULL')]
    rows = [value for value in rows if not is_null(value)]
    if not rows:
        return None
    def valid(value) -> bool:
        text = str(value).lower()
        return text in labels or any(label in text for label in labels)
    return sum(valid(value) for value in rows) / len(rows)


def _statement_residue(conn, tree, db_columns, table_attrs) -> tuple[dict[str, int], list[str]]:
    """Rows, per attribute, where this statement's outcome depends on an unknown value.

    A row counts for attribute ``a`` when no other single-table WHERE conjunct on
    its table is known FALSE (UNKNOWN support is kept: the incumbent has not
    excluded the row), and either a condition over ``a`` is UNKNOWN or ``a``
    is NULL where the statement groups, aggregates, joins, or projects it.
    """

    aliases = alias_map(tree)
    per_table: dict[str, list[tuple[str, list[str]]]] = {}
    for where in tree.find_all(exp.Where):
        for node in _conjuncts(where.this):
            compiled = _single_table_sql(node, aliases, table_attrs)
            if compiled:
                table, sql, names = compiled
                per_table.setdefault(table, []).append((sql, names))
    case_conditions: list[tuple[str, str, list[str]]] = []
    for case in tree.find_all(exp.Case):
        for branch in case.args.get("ifs") or []:
            compiled = _single_table_sql(branch.this, aliases, table_attrs)
            if compiled:
                case_conditions.append(compiled)
    outside: dict[str, set[str]] = {}
    for column in tree.find_all(exp.Column):
        if column.find_ancestor(exp.Where) is not None:
            continue
        table = resolve_column(column, aliases, table_attrs)
        if table:
            outside.setdefault(table, set()).add(column.name)

    counts: dict[str, int] = {}
    errors: list[str] = []
    attrs_by_table: dict[str, set[str]] = {}
    for table, rows in per_table.items():
        for _, names in rows:
            attrs_by_table.setdefault(table, set()).update(names)
    for table, _, names in case_conditions:
        attrs_by_table.setdefault(table, set()).update(names)
    for table, names in outside.items():
        attrs_by_table.setdefault(table, set()).update(names)

    for table, names in attrs_by_table.items():
        if table not in db_columns:
            continue
        for name in sorted(names):
            if name not in db_columns[table]:
                continue
            support = [sql for sql, used in per_table.get(table, []) if name not in used]
            unknown = [f"({sql}) IS NULL" for sql, used in per_table.get(table, []) if name in used]
            unknown += [f"({sql}) IS NULL" for t, sql, used in case_conditions if t == table and name in used]
            if name in outside.get(table, set()):
                unknown.append(f'"{name}" IS NULL')
            if not unknown:
                continue
            where = "(" + " OR ".join(unknown) + ")"
            if support:
                where += " AND " + " AND ".join(f"COALESCE(({sql}), 1)" for sql in support)
            try:
                (count,) = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE {where}').fetchone()
            except sqlite3.Error as exc:
                errors.append(str(exc))
                continue
            counts[f"{table}.{name}"] = int(count)
    return counts, errors


def residue_features(spec: CorpusSpec, workload: dict[str, Any], db_path: Path | None = None) -> dict[str, Any]:
    db_path = db_path or spec.incumbent_db
    if db_path is None or not Path(db_path).is_file():
        return {"available": False, "attributes": {}}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db_columns = _db_columns(conn)
    table_attrs = table_attribute_names(spec)
    residue: dict[str, int] = {}
    residue_queries: dict[str, list[str]] = {}
    errors: list[str] = []
    for query_id, sql in spec.queries().items():
        tree = sqlglot.parse_one(sql, read="sqlite")
        counts, errs = _statement_residue(conn, tree, db_columns, table_attrs)
        errors.extend(f"{query_id}: {err}" for err in errs)
        for key, count in counts.items():
            residue[key] = max(residue.get(key, 0), count)
            if count:
                residue_queries.setdefault(key, []).append(query_id)

    attributes: dict[str, Any] = {}
    for use in workload["attributes"].values():
        table, name = use.table, use.name
        columns = db_columns.get(table, set())
        if name not in columns:
            attributes[use.qualified] = {"present": False}
            continue
        (rows,) = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
        (nulls,) = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{name}" IS NULL').fetchone()
        count = residue.get(use.qualified, 0)
        if use.closed_label:
            trust = incumbent_label_validity(conn, table, name, declared_labels(use))
            trust_kind = "label_validity"
        else:
            trust = incumbent_grounding(conn, spec, table, name, columns)
            trust_kind = "grounding"
        attributes[use.qualified] = {
            "present": True,
            "rows": int(rows),
            "null_rows": int(nulls),
            "residue_rows": count,
            "residue_fraction": count / rows if rows else 1.0,
            "residue_queries": sorted(set(residue_queries.get(use.qualified, []))),
            "incumbent_trust": trust,
            "incumbent_trust_kind": trust_kind,
        }
    conn.close()
    return {"available": True, "db": str(db_path), "attributes": attributes, "errors": errors[:20]}
