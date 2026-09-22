"""Role-separated workload observables and exact-SQL fallback.

Base columns are never updated. A resolved sidecar value replaces one
expression. Unresolved lookups fall through to that original expression.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import sqlglot
from sqlglot import exp

from quwarts.core.pipeline import official_sql

TABLE = "observable_decisions"
SPEC_TABLE = "observable_specs"
EDGE_TABLE = "observable_edges"


@dataclass
class Observable:
    observable_id: str
    kind: str
    role: str
    attribute: str
    match_sql: str
    legal_labels: tuple[str, ...]
    raw_occurrences: int
    query_ids: tuple[str, ...]
    expression: str

    def to_json(self) -> dict[str, Any]:
        row = asdict(self)
        row["legal_labels"] = list(self.legal_labels)
        row["query_ids"] = list(self.query_ids)
        return row


@dataclass
class Inventory:
    observables: list[Observable] = field(default_factory=list)
    raw_occurrences: int = 0
    joins: int = 0
    derived: list[dict[str, Any]] = field(default_factory=list)

    @property
    def canonical(self) -> int:
        return len(self.observables)

    @property
    def reuse_ratio(self) -> float:
        if self.raw_occurrences <= 0:
            return 0.0
        return 1.0 - (self.canonical / self.raw_occurrences)


def norm_sql(node: exp.Expression) -> str:
    return " ".join(node.sql(dialect="sqlite").lower().split())


def _digest(kind: str, role: str, match_sql: str) -> str:
    payload = f"{kind}|{role}|{match_sql}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _labels_of_case(node: exp.Case) -> tuple[str, ...]:
    found: list[str] = []
    for item in node.args.get("ifs") or []:
        true = item.args.get("true")
        cond = item.this
        if isinstance(true, exp.Literal) and not true.is_number:
            found.append(str(true.this))
        elif isinstance(true, exp.Column) and isinstance(cond, exp.In):
            for lit in cond.expressions:
                if isinstance(lit, exp.Literal):
                    found.append(str(lit.this))
        elif isinstance(true, exp.Column):
            found.append(true.name)
    default = node.args.get("default")
    if isinstance(default, exp.Literal) and not default.is_number:
        found.append(str(default.this))
    return tuple(dict.fromkeys(found))


def _attribute_of(node: exp.Expression) -> str:
    cols = [col.name.lower() for col in node.find_all(exp.Column) if col.name]
    return cols[0] if len(set(cols)) == 1 else (cols[0] if cols else "")


def _where_atoms(node: exp.Expression | None) -> list[exp.Expression]:
    if node is None:
        return []
    if isinstance(node, exp.And):
        return _where_atoms(node.left) + _where_atoms(node.right)
    if isinstance(node, exp.Paren):
        return _where_atoms(node.this)
    return [node]


def _kind_of_atom(node: exp.Expression) -> tuple[str, str]:
    text = norm_sql(node)
    if text.startswith("not ") and " is null" in text:
        return "presence", "is_not_null"
    if "<> ''" in text or "!= ''" in text:
        return "presence", "nonempty"
    return "predicate", "filter"


def compile_observables(queries: Iterable[dict[str, str]]) -> Inventory:
    """Walk every AST occurrence. Dedup only identical semantics and role."""

    inventory = Inventory()
    bucket: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add(kind: str, role: str, match: str, attribute: str, labels: tuple[str, ...], query_id: str, expression: str) -> None:
        inventory.raw_occurrences += 1
        key = (kind, role, match)
        row = bucket.get(key)
        if row is None:
            bucket[key] = {
                "kind": kind,
                "role": role,
                "match_sql": match,
                "attribute": attribute,
                "legal_labels": labels,
                "query_ids": [query_id],
                "raw": 1,
                "expression": expression,
            }
        else:
            row["raw"] += 1
            if query_id not in row["query_ids"]:
                row["query_ids"].append(query_id)

    for query in queries:
        query_id = str(query["query_id"])
        tree = sqlglot.parse_one(query["sql"], read="sqlite")
        inventory.joins += len(list(tree.find_all(exp.Join)))
        where = tree.args.get("where")
        for atom in _where_atoms(where.this if where is not None else None):
            kind, role = _kind_of_atom(atom)
            add(kind, role, norm_sql(atom), _attribute_of(atom), (), query_id, atom.sql(dialect="sqlite"))
        having = tree.args.get("having")
        if having is not None:
            inventory.derived.append(
                {"kind": "having", "query_id": query_id, "expression": having.this.sql(dialect="sqlite")}
            )
        for count in tree.find_all(exp.Count):
            inventory.derived.append(
                {"kind": "count_star" if count.find(exp.Star) or not count.this else "count_expr", "query_id": query_id, "expression": count.sql(dialect="sqlite")}
            )
        group_cases: set[int] = set()
        for node in tree.find_all(exp.Case):
            parent = node.parent
            while isinstance(parent, exp.Paren):
                parent = parent.parent
            if isinstance(parent, exp.Sum):
                for item in node.args.get("ifs") or []:
                    cond = item.this
                    add(
                        "predicate",
                        "aggregate_indicator",
                        norm_sql(cond),
                        _attribute_of(cond),
                        ("TRUE", "FALSE"),
                        query_id,
                        cond.sql(dialect="sqlite"),
                    )
                continue
            group_cases.add(id(node))
            add(
                "group",
                "case_branch",
                norm_sql(node),
                _attribute_of(node),
                _labels_of_case(node),
                query_id,
                node.sql(dialect="sqlite"),
            )
        for node in list(tree.find_all(exp.Avg)) + list(tree.find_all(exp.Max)) + list(tree.find_all(exp.Sum)):
            if isinstance(node, exp.Sum) and isinstance(node.this, exp.Case):
                continue
            if not isinstance(node.this, exp.Column):
                continue
            role = {exp.Avg: "numeric_avg", exp.Max: "numeric_max", exp.Sum: "numeric_sum"}[type(node)]
            add("numeric", role, norm_sql(node), node.this.name.lower(), (), query_id, node.sql(dialect="sqlite"))
        alias_names = set()
        projections = []
        for proj in tree.expressions:
            if isinstance(proj, exp.Alias) and proj.alias:
                alias_names.add(proj.alias.lower())
                projections.append(proj.this)
            else:
                projections.append(proj)
        group = tree.args.get("group")
        group_exprs = list(group.expressions) if group is not None else []
        for expr in projections + group_exprs:
            if not isinstance(expr, exp.Column):
                continue
            if not expr.table and (expr.name or "").lower() in alias_names:
                continue
            add("group", "group_key", norm_sql(expr), expr.name.lower(), (), query_id, expr.sql(dialect="sqlite"))

    for row in bucket.values():
        inventory.observables.append(
            Observable(
                observable_id=_digest(row["kind"], row["role"], row["match_sql"]),
                kind=row["kind"],
                role=row["role"],
                attribute=row["attribute"],
                match_sql=row["match_sql"],
                legal_labels=tuple(row["legal_labels"]),
                raw_occurrences=int(row["raw"]),
                query_ids=tuple(row["query_ids"]),
                expression=row["expression"],
            )
        )
    inventory.observables.sort(key=lambda item: (item.kind, item.role, item.attribute, item.observable_id))
    return inventory


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {SPEC_TABLE} (
            observable_id TEXT PRIMARY KEY,
            kind TEXT,
            role TEXT,
            attribute TEXT,
            match_sql TEXT,
            legal_labels TEXT,
            raw_occurrences INTEGER,
            query_ids TEXT,
            expression TEXT
        )"""
    )
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {TABLE} (
            observable_id TEXT,
            entity_id TEXT,
            resolved INTEGER,
            sql_truth TEXT,
            value_text TEXT,
            provenance TEXT,
            PRIMARY KEY (observable_id, entity_id)
        )"""
    )
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {EDGE_TABLE} (
            edge_id TEXT,
            left_entity TEXT,
            right_entity TEXT,
            resolved INTEGER
        )"""
    )
    conn.commit()


def write_specs(conn: sqlite3.Connection, inventory: Inventory) -> None:
    ensure_schema(conn)
    conn.execute(f"DELETE FROM {SPEC_TABLE}")
    for item in inventory.observables:
        conn.execute(
            f"""INSERT INTO {SPEC_TABLE}
            (observable_id, kind, role, attribute, match_sql, legal_labels, raw_occurrences, query_ids, expression)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                item.observable_id,
                item.kind,
                item.role,
                item.attribute,
                item.match_sql,
                json.dumps(list(item.legal_labels)),
                item.raw_occurrences,
                json.dumps(list(item.query_ids)),
                item.expression,
            ],
        )
    conn.commit()


def _has_specs(sqlite_path: str | Path) -> bool:
    path = str(sqlite_path)
    if path == ":memory:":
        return False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            [SPEC_TABLE],
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def load_specs(sqlite_path: str | Path) -> list[dict[str, Any]]:
    if not _has_specs(sqlite_path):
        return []
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        cols = ["observable_id", "kind", "role", "attribute", "match_sql", "legal_labels", "expression"]
        return [dict(zip(cols, row)) for row in conn.execute(f"SELECT {', '.join(cols)} FROM {SPEC_TABLE}")]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _entity_sql(tree: exp.Expression) -> str:
    table = next(tree.find_all(exp.Table), None)
    name = (table.name if table is not None else "legal") or "legal"
    return f'"{name}"."__entity_id"'


def _subquery(field: str, observable_id: str, entity_sql: str) -> str:
    oid = observable_id.replace("'", "''")
    return (
        f"(SELECT d.{field} FROM {TABLE} d "
        f"WHERE d.observable_id = '{oid}' AND d.entity_id = {entity_sql})"
    )


def _wrap_resolved(resolved_sql: str, value_sql: str, original: exp.Expression) -> exp.Expression:
    return sqlglot.parse_one(
        f"CASE WHEN {resolved_sql} = 1 THEN {value_sql} ELSE {original.sql(dialect='sqlite')} END",
        read="sqlite",
    )


def rewrite_observable_sql(sql: str, sqlite_path: str | Path) -> str:
    """No-op when this database has no observable spec table."""

    specs = load_specs(sqlite_path)
    if not specs:
        return sql
    by_match: dict[tuple[str, str], dict[str, Any]] = {}
    for spec in specs:
        by_match[(spec["kind"], spec["match_sql"])] = spec
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return sql
    if not isinstance(tree, exp.Select):
        return sql
    entity_sql = _entity_sql(tree)
    changed = False

    def resolved(spec: dict[str, Any]) -> str:
        return _subquery("resolved", spec["observable_id"], entity_sql)

    def replace(node: exp.Expression, spec: dict[str, Any], value_sql: str) -> None:
        nonlocal changed
        node.replace(_wrap_resolved(resolved(spec), value_sql, node.copy()))
        changed = True

    group_ids: set[int] = set()
    for node in list(tree.find_all(exp.Case)):
        parent = node.parent
        while isinstance(parent, exp.Paren):
            parent = parent.parent
        if isinstance(parent, exp.Sum):
            continue
        spec = by_match.get(("group", norm_sql(node)))
        if spec is None or spec["role"] != "case_branch":
            continue
        group_ids.add(id(node))
        replace(node, spec, _subquery("value_text", spec["observable_id"], entity_sql))

    def inside_group_case(node: exp.Expression) -> bool:
        parent = node.parent
        while parent is not None:
            if isinstance(parent, exp.Case):
                rendered = parent.sql(dialect="sqlite")
                if "observable_decisions" in rendered or ("group", norm_sql(parent)) in by_match:
                    return True
            parent = parent.parent
        return False

    for node in list(tree.find_all(exp.EQ, exp.NEQ, exp.In, exp.Between, exp.GTE, exp.LTE, exp.GT, exp.LT, exp.Not)):
        if inside_group_case(node):
            continue
        match = norm_sql(node)
        spec = by_match.get(("presence", match)) or by_match.get(("predicate", match))
        if spec is None:
            continue
        if spec["role"] == "aggregate_indicator":
            parent = node.parent
            inside_sum = False
            while parent is not None:
                if isinstance(parent, exp.Sum):
                    inside_sum = True
                    break
                parent = parent.parent
            if not inside_sum:
                continue
        truth = (
            "CASE "
            + _subquery("sql_truth", spec["observable_id"], entity_sql)
            + " WHEN 'TRUE' THEN 1 WHEN 'FALSE' THEN 0 ELSE NULL END"
        )
        replace(node, spec, truth)

    for node in list(tree.find_all(exp.Avg, exp.Max)):
        spec = by_match.get(("numeric", norm_sql(node)))
        if spec is None or not isinstance(node.this, exp.Column):
            continue
        value = f"CAST({_subquery('value_text', spec['observable_id'], entity_sql)} AS REAL)"
        original_arg = node.this.copy()
        node.set("this", _wrap_resolved(resolved(spec), value, original_arg))
        changed = True

    alias_names = set()
    for proj in tree.expressions:
        if isinstance(proj, exp.Alias) and proj.alias:
            alias_names.add(proj.alias.lower())
    for node in list(tree.find_all(exp.Column)):
        if not node.table and (node.name or "").lower() in alias_names:
            continue
        parent = node.parent
        if isinstance(parent, exp.Alias):
            host = parent.parent
            bare = parent
        else:
            host = parent
            bare = node
        in_select = isinstance(host, exp.Select) and bare in (host.expressions or [])
        in_group = isinstance(host, exp.Group) and bare in (host.expressions or [])
        if not in_select and not in_group:
            continue
        spec = by_match.get(("group", norm_sql(node)))
        if spec is None or spec["role"] != "group_key":
            continue
        wrapped = _wrap_resolved(resolved(spec), _subquery("value_text", spec["observable_id"], entity_sql), node.copy())
        if in_select and not isinstance(parent, exp.Alias):
            node.replace(exp.alias_(wrapped, node.name))
        else:
            node.replace(wrapped)
        changed = True

    if not changed:
        return sql
    return tree.sql(dialect="sqlite")


def base_checksum(conn: sqlite3.Connection, table: str = "legal") -> str:
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    rows = conn.execute(
        f"SELECT {', '.join(chr(34)+col+chr(34) for col in cols)} FROM {table} ORDER BY \"__entity_id\""
    ).fetchall()
    payload = json.dumps(rows, default=str, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def identity_checksum(conn: sqlite3.Connection, table: str = "legal") -> str:
    rows = conn.execute(f'SELECT "__entity_id", doc_id FROM {table} ORDER BY "__entity_id"').fetchall()
    return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()


def execute_bags(db: Path, statements: dict[str, str], predicates) -> dict[str, list[dict[str, Any]]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    bags: dict[str, list[dict[str, Any]]] = {}
    try:
        for query_id, sql in statements.items():
            rewritten = official_sql(sql, db, predicates, query_id=query_id)
            try:
                cur = conn.execute(rewritten)
            except sqlite3.Error as exc:
                raise RuntimeError(f"{query_id} failed: {exc}") from exc
            cols = [item[0] for item in cur.description] if cur.description else []
            bags[query_id] = [dict(zip(cols, rec)) for rec in cur.fetchall()]
    finally:
        conn.close()
    return bags


def bag_hash(bags: dict[str, list[dict[str, Any]]]) -> str:
    payload = json.dumps(bags, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_role_fixtures() -> dict[str, bool]:
    """Presence and numeric sidecars must not drive each other's SQL role."""

    conn = sqlite3.connect(":memory:")
    conn.execute('CREATE TABLE legal (doc_id TEXT, "__entity_id" TEXT, case_number TEXT, verdict TEXT)')
    conn.execute("INSERT INTO legal VALUES ('a.txt', 'e1', NULL, NULL)")
    inventory = compile_observables(
        [
            {
                "query_id": "q",
                "sql": "SELECT AVG(case_number) AS avg_precedents, COUNT(*) AS case_count FROM legal WHERE case_number IS NOT NULL",
            }
        ]
    )
    write_specs(conn, inventory)
    path_holder: dict[str, str] = {}

    def rewrite(sql: str) -> str:
        # In-memory connections cannot be reopened by path. Materialize a temp
        # file so the official rewriter sees the same sidecar tables.
        return sql

    import tempfile

    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    disk = Path(handle.name)
    file_conn = sqlite3.connect(disk)
    file_conn.executescript("".join(conn.iterdump()))
    file_conn.commit()
    path_holder["path"] = str(disk)

    def run(sql: str) -> list[tuple]:
        rewritten = rewrite_observable_sql(sql, disk)
        return file_conn.execute(rewritten).fetchall()

    sql = "SELECT COUNT(*) AS case_count, AVG(case_number) AS avg_precedents FROM legal WHERE case_number IS NOT NULL"
    empty = run(sql)
    presence = next(item for item in inventory.observables if item.kind == "presence")
    numeric = next(item for item in inventory.observables if item.kind == "numeric")
    file_conn.execute(
        f"INSERT INTO {TABLE} (observable_id, entity_id, resolved, sql_truth, value_text, provenance) VALUES (?, ?, 1, 'TRUE', NULL, 'fixture')",
        [presence.observable_id, "e1"],
    )
    file_conn.commit()
    after_presence = run(sql)
    file_conn.execute(f"DELETE FROM {TABLE}")
    file_conn.execute(
        f"INSERT INTO {TABLE} (observable_id, entity_id, resolved, sql_truth, value_text, provenance) VALUES (?, ?, 1, NULL, '10', 'fixture')",
        [numeric.observable_id, "e1"],
    )
    file_conn.commit()
    after_numeric = run(sql)
    file_conn.execute(
        f"INSERT INTO {TABLE} (observable_id, entity_id, resolved, sql_truth, value_text, provenance) VALUES (?, ?, 0, 'TRUE', NULL, 'unresolved')",
        [presence.observable_id, "e1"],
    )
    file_conn.commit()
    unresolved = run(sql)
    file_conn.close()
    disk.unlink(missing_ok=True)
    # empty: count 0, avg NULL. presence TRUE: count 1, avg still NULL.
    # numeric alone: count stays 0 because IS NOT NULL is unresolved.
    # unresolved presence flag stays on the plumbing predicate.
    return {
        "empty_count_zero": empty == [(0, None)],
        "presence_does_not_change_avg": after_presence == [(1, None)],
        "numeric_does_not_satisfy_presence": after_numeric == [(0, None)],
        "unresolved_matches_empty": unresolved == [(0, None)],
        "rewrite_unused": rewrite("SELECT 1") == "SELECT 1",
    }


def install_database(plumbing: Path, dest: Path, inventory: Inventory) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    import shutil

    shutil.copy2(plumbing, dest)
    conn = sqlite3.connect(dest)
    try:
        write_specs(conn, inventory)
    finally:
        conn.close()
    return dest
