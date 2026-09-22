"""Query-local non-destructive overlay of type-valid candidates onto plumbing NULLs."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from quwarts.core.docetl_unit_parity.local_table import plumbing_bag
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.schema_columns import assert_queries_execute


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _identity(conn: sqlite3.Connection, table: str = "finance") -> str:
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({_q(table)})")]
    for cand in ("doc_id", "id", "document_id", "source_id"):
        if cand in cols:
            return cand
    return cols[0]


def plumbing_keys(doc_id: str, mapping: dict[str, str]) -> list[str]:
    mapped = mapping.get(doc_id, f"{doc_id}.txt")
    return list(dict.fromkeys([str(doc_id), f"{doc_id}.txt", mapped, Path(str(mapped)).stem]))


def copy_plumbing(base: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(base, dest)
    return dest


def apply_overlay(
    dest: Path,
    fills: dict[str, dict[str, Any]],
    mapping: dict[str, str],
    table: str = "finance",
) -> dict[str, Any]:
    conn = sqlite3.connect(str(dest))
    ident = _identity(conn, table)
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({_q(table)})")]
    protected = {ident, "__entity_id", "__provenance_label"}
    changed = 0
    blocked = 0
    missing_rows: list[str] = []
    sentinels_blocked = 0
    for doc_id, values in fills.items():
        existing = None
        for key in plumbing_keys(doc_id, mapping):
            existing = conn.execute(
                f"SELECT * FROM {_q(table)} WHERE CAST({_q(ident)} AS TEXT)=?",
                (key,),
            ).fetchone()
            if existing is not None:
                break
        if existing is None:
            missing_rows.append(doc_id)
            continue
        row = dict(zip(cols, existing))
        assignments = []
        payload: list[Any] = []
        for col, value in values.items():
            if col not in cols or col in protected:
                continue
            if value in (None, "", -1, "-1"):
                sentinels_blocked += 1
                continue
            if row.get(col) is not None:
                blocked += 1
                continue
            assignments.append(f"{_q(col)}=?")
            payload.append(value)
            changed += 1
        if assignments:
            payload.append(row[ident])
            conn.execute(f"UPDATE {_q(table)} SET {', '.join(assignments)} WHERE {_q(ident)}=?", payload)
    n_rows = conn.execute(f"SELECT COUNT(*) FROM {_q(table)}").fetchone()[0]
    identities = [rec[0] for rec in conn.execute(f"SELECT {_q(ident)} FROM {_q(table)} ORDER BY {_q(ident)}")]
    conn.commit()
    conn.close()
    return {
        "changed_cells": changed,
        "blocked_overwrites": blocked,
        "sentinels_blocked": sentinels_blocked,
        "missing_rows": missing_rows,
        "n_rows": n_rows,
        "identity_sha256": hashlib.sha256(json.dumps(identities).encode()).hexdigest(),
        "db_sha256": file_sha256(dest),
    }


def empty_overlay_matches(
    plumbing: Path,
    dest_dir: Path,
    statements: dict[str, str],
    predicates,
) -> bool:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for qid, sql in statements.items():
        dest = dest_dir / f"{qid.replace(':', '_')}.db"
        copy_plumbing(plumbing, dest)
        if plumbing_bag(plumbing, sql, predicates, qid) != plumbing_bag(dest, sql, predicates, qid):
            return False
    return True


def fixture_null_only(dest: Path, mapping: dict[str, str], doc_id: str, column: str) -> dict[str, bool]:
    conn = sqlite3.connect(str(dest))
    table = "finance"
    ident = _identity(conn, table)
    keys = plumbing_keys(doc_id, mapping)
    row = None
    key_used = None
    for key in keys:
        row = conn.execute(f"SELECT * FROM {_q(table)} WHERE CAST({_q(ident)} AS TEXT)=?", (key,)).fetchone()
        if row is not None:
            key_used = key
            break
    cols = [item[1] for item in conn.execute(f"PRAGMA table_info({_q(table)})")]
    before = dict(zip(cols, row)) if row else {}
    conn.close()
    if row is None:
        return {"found_row": False, "fill_only_null": False, "no_overwrite": False}
    apply_overlay(dest, {doc_id: {column: "__CANDIDATE__"}}, mapping)
    conn = sqlite3.connect(str(dest))
    after_row = conn.execute(f"SELECT * FROM {_q(table)} WHERE CAST({_q(ident)} AS TEXT)=?", (key_used,)).fetchone()
    after = dict(zip(cols, after_row))
    conn.close()
    if before.get(column) is None:
        return {"found_row": True, "fill_only_null": after.get(column) == "__CANDIDATE__", "no_overwrite": True}
    return {"found_row": True, "fill_only_null": True, "no_overwrite": after.get(column) == before.get(column)}


def official_bag(db: Path, sql: str, predicates, query_id: str) -> list[dict[str, Any]]:
    rewritten = official_sql(sql, db, predicates, query_id=query_id)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = conn.execute(rewritten)
        cols = [item[0] for item in cur.description] if cur.description else []
        return [dict(zip(cols, rec)) for rec in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def execute_all(db: Path, statements: dict[str, str]) -> bool:
    conn = sqlite3.connect(str(db))
    try:
        assert_queries_execute(conn, statements, any_error=True)
        return True
    finally:
        conn.close()
