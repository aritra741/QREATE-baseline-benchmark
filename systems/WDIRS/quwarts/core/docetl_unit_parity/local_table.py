"""Query-local finance tables. Isolated from plumbing and from each other."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from quwarts.core.docetl_unit_parity.schema import QuerySchema
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.schema_columns import assert_queries_execute


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _norm_bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(key), json.dumps(row.get(key), default=str)) for key in row)))
    return tuple(sorted(frozen))


def fetch_sql(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    try:
        cur = conn.execute(sql)
    except sqlite3.Error:
        return []
    cols = [item[0] for item in cur.description] if cur.description else []
    return [dict(zip(cols, rec)) for rec in cur.fetchall()]


def create_local_db(path: Path, schema: QuerySchema) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    cols = ["doc_id TEXT"] + [f"{_q(item.name)} {item.sql_type}" for item in schema.fields]
    conn.execute(f"CREATE TABLE finance ({', '.join(cols)})")
    conn.commit()
    conn.close()
    return path


def insert_row(path: Path, schema: QuerySchema, doc_id: str, values: dict[str, Any]) -> None:
    conn = sqlite3.connect(str(path))
    cols = ["doc_id"] + schema.names
    placeholders = ", ".join("?" for _ in cols)
    payload = [doc_id]
    for name in schema.names:
        value = values.get(name)
        if value in (None, "", "null", "none", False):
            payload.append(None)
        else:
            payload.append(value)
    conn.execute(
        f"INSERT INTO finance ({', '.join(_q(col) for col in cols)}) VALUES ({placeholders})",
        payload,
    )
    conn.commit()
    conn.close()


def execute_original(path: Path, sql: str) -> tuple[list[dict[str, Any]], str | None]:
    conn = sqlite3.connect(str(path))
    try:
        return fetch_sql(conn, sql), None
    except sqlite3.Error as exc:
        return [], str(exc)
    finally:
        conn.close()


def plumbing_bag(db: Path, sql: str, predicates, query_id: str) -> tuple:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return _norm_bag(fetch_sql(conn, official_sql(sql, db, predicates, query_id=query_id)))
    finally:
        conn.close()


def bag_of(path: Path, sql: str) -> tuple:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return _norm_bag(fetch_sql(conn, sql))
    except sqlite3.Error:
        return tuple()
    finally:
        conn.close()


def fixture_program(schema: QuerySchema, document_ids: list[str], dest: Path) -> dict[str, Any]:
    create_local_db(dest, schema)
    for index, doc_id in enumerate(document_ids):
        values = {}
        for item in schema.fields:
            if item.dtype == "numeric":
                values[item.name] = float(index + 1)
            elif item.semantic:
                values[item.name] = item.literals[0] if item.literals else "Yes"
            else:
                values[item.name] = item.literals[0] if item.literals else f"fixture-{doc_id}"
        insert_row(dest, schema, doc_id, values)
    conn = sqlite3.connect(str(dest))
    try:
        assert_queries_execute(conn, {schema.query_id: schema.sql}, any_error=True)
        rows = fetch_sql(conn, schema.sql)
        return {"ok": True, "n_rows": len(rows), "sha256": file_sha256(dest)}
    finally:
        conn.close()


def empty_override_reproduces(
    plumbing: Path,
    statements: dict[str, str],
    predicates,
) -> bool:
    empty: dict[str, Path] = {}
    return isolation_and_fallback(plumbing, statements, predicates, empty)["fallback_ok"]


def isolation_and_fallback(
    plumbing: Path,
    statements: dict[str, str],
    predicates,
    completed: dict[str, Path],
) -> dict[str, Any]:
    plumbing_bags = {qid: plumbing_bag(plumbing, sql, predicates, qid) for qid, sql in statements.items()}
    fallback_ok = True
    leaked = []
    hashes = {qid: file_sha256(path) for qid, path in completed.items() if path.is_file()}
    for qid, sql in statements.items():
        if qid not in completed:
            if plumbing_bag(plumbing, sql, predicates, qid) != plumbing_bags[qid]:
                fallback_ok = False
    for qid, path in completed.items():
        before = hashes[qid]
        for other, other_path in completed.items():
            if other == qid:
                continue
            if file_sha256(other_path) != hashes[other]:
                leaked.append((qid, other))
        if file_sha256(path) != before:
            leaked.append((qid, qid))
    return {
        "fallback_ok": fallback_ok,
        "isolation_ok": not leaked,
        "leaked": leaked,
        "plumbing_bags": {qid: hashlib.sha256(repr(bag).encode()).hexdigest() for qid, bag in plumbing_bags.items()},
    }
