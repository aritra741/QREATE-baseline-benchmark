"""SQLite writer, hashing, coverage sets. Hashed files are never mutated."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from quwarts.core.models import (
    Configuration,
    CoverageSet,
    EvidenceRecord,
    MaterializedDB,
    SliceSpec,
    SourceDocument,
    SurrogateReport,
    Workload,
)
from quwarts.core.extract import _slug
from quwarts.core.population import apply_population


def corpus_fingerprint(documents: list[SourceDocument]) -> str:
    digest = hashlib.sha256()
    for doc in sorted(documents, key=lambda item: item.doc_id):
        digest.update(doc.doc_id.encode())
        digest.update(doc.text.encode())
    return digest.hexdigest()


def coverage_set(
    records: list[EvidenceRecord],
    config: Configuration,
    workload: Workload,
    documents: list[SourceDocument],
) -> CoverageSet:
    ranges: dict[str, SliceSpec] = {}
    forms: dict[str, set[str]] = {}
    present: set[str] = set()
    for record in records:
        present.add(record.attribute)
        forms.setdefault(record.attribute, set()).update({"surface", "parsed"})
        if record.original_unit:
            forms[record.attribute].add(f"unit:{record.original_unit}")
        req = workload.requirements.get(record.attribute)
        if record.surface_value is not None:
            ranges[record.attribute] = SliceSpec(kind="full")
        if req is not None:
            forms[record.attribute].update(req.required_forms)
    grain = dict(config.pop.grain)
    return CoverageSet(
        attribute_ranges=ranges,
        attributes_present=present,
        grain=grain,
        forms=forms,
        corpus_fingerprint=corpus_fingerprint(documents),
    )


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def write_sqlite(
    config: Configuration,
    rows: list[dict[str, Any]],
    output_dir: Path,
) -> tuple[Path, dict[str, int]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{config.id}.db"
    if path.exists():
        path = output_dir / f"{config.id}-{_payload_hash(rows)[:8]}.db"
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    for relation in config.schema_.relations:
        for attr in relation.attributes:
            if attr not in seen:
                seen.add(attr)
                columns.append(attr)
    if not columns:
        columns = ["doc_id"]
    conn = sqlite3.connect(path)
    try:
        col_sql = ", ".join(f"{_quote(col)} TEXT" for col in columns)
        conn.execute(f"CREATE TABLE {_quote('fact')} ({col_sql})")
        if config.schema_.pattern != "denormalized":
            for relation in config.schema_.relations:
                if relation.name == "fact":
                    continue
                rel_cols = _relation_columns(relation, seen)
                rel_sql = ", ".join(f"{_quote(col)} TEXT" for col in rel_cols)
                conn.execute(f"CREATE TABLE {_quote(relation.name)} ({rel_sql})")
        placeholders = ", ".join("?" for _ in columns)
        insert = f"INSERT INTO {_quote('fact')} VALUES ({placeholders})"
        for row in rows:
            conn.execute(insert, [ _cell(row.get(col)) for col in columns ])
        if config.schema_.pattern != "denormalized":
            for relation in config.schema_.relations:
                if relation.name == "fact":
                    continue
                rel_cols = _relation_columns(relation, seen)
                marks = ", ".join("?" for _ in rel_cols)
                sql = f"INSERT INTO {_quote(relation.name)} VALUES ({marks})"
                for row in rows:
                    if not _row_belongs(row, relation):
                        continue
                    conn.execute(sql, [_cell(_value(row, col)) for col in rel_cols])
        conn.commit()
        counts = {}
        for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            counts[name] = conn.execute(f"SELECT COUNT(*) FROM {_quote(name)}").fetchone()[0]
    finally:
        conn.close()
    return path, counts


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stamp_authority_domains(sqlite_path: str, domains: dict[str, list[str]]) -> None:
    """Write the same authority identity set into every database."""

    if not domains:
        return
    conn = sqlite3.connect(sqlite_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for auth, values in domains.items():
            if "." not in auth:
                continue
            entity, bare = auth.split(".", 1)
            if entity not in tables or bare in {"", }:
                continue
            cols = [row[1] for row in conn.execute(f'PRAGMA table_info("{entity}")')]
            if bare not in cols:
                continue
            wanted: list[str] = []
            seen: set[str] = set()
            for value in values:
                text = str(value).strip()
                if not text or text.lower() in seen:
                    continue
                seen.add(text.lower())
                wanted.append(text)
            existing = [
                str(row[0]).strip()
                for row in conn.execute(f'SELECT "{bare}" FROM "{entity}"')
                if row[0] not in (None, "")
            ]
            have = {item.lower() for item in existing}
            for value in wanted:
                if value.lower() in have:
                    continue
                _insert_identity_row(conn, entity, cols, bare, value)
                have.add(value.lower())
            if wanted:
                marks = ", ".join("?" for _ in wanted)
                conn.execute(
                    f'DELETE FROM "{entity}" WHERE "{bare}" IS NULL OR '
                    f'lower("{bare}") NOT IN ({marks})',
                    [item.lower() for item in wanted],
                )
            for value in wanted:
                conn.execute(
                    f'UPDATE "{entity}" SET "{bare}"=? WHERE lower("{bare}")=?',
                    (value, value.lower()),
                )
        conn.commit()
    finally:
        conn.close()


def authority_column_values(sqlite_path: str, auth: str) -> tuple[str, ...]:
    if "." not in auth:
        return ()
    entity, bare = auth.split(".", 1)
    conn = sqlite3.connect(sqlite_path)
    try:
        rows = conn.execute(
            f'SELECT DISTINCT "{bare}" FROM "{entity}" WHERE "{bare}" IS NOT NULL'
        ).fetchall()
    except sqlite3.Error:
        return ()
    finally:
        conn.close()
    return tuple(sorted({str(row[0]) for row in rows if row[0] not in (None, "")}))


def _insert_identity_row(
    conn: sqlite3.Connection,
    table: str,
    cols: list[str],
    bare: str,
    value: str,
) -> None:
    payload = {name: None for name in cols}
    if "doc_id" in payload:
        payload["doc_id"] = f"{table}/join_complete/{_slug(value)}"
    payload[bare] = value
    quoted = ", ".join(f'"{name}"' for name in cols)
    marks = ", ".join("?" for _ in cols)
    conn.execute(
        f'INSERT INTO "{table}" ({quoted}) VALUES ({marks})',
        [payload[name] for name in cols],
    )


def materialize(
    config: Configuration,
    records: list[EvidenceRecord],
    workload: Workload,
    documents: list[SourceDocument],
    output_dir: Path,
    tokens_spent: int,
    surrogate: SurrogateReport | None = None,
    authority: dict[str, list[str]] | None = None,
) -> MaterializedDB:
    rows = apply_population(records, config, workload)
    path, counts = write_sqlite(config, rows, output_dir)
    if authority:
        stamp_authority_domains(str(path), authority)
        counts = {}
        conn = sqlite3.connect(path)
        try:
            for name, in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ):
                counts[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        finally:
            conn.close()
    digest = file_sha256(path)
    coverage = coverage_set(records, config, workload, documents)
    return MaterializedDB(
        config_id=config.id,
        sqlite_path=str(path),
        sha256=digest,
        row_counts=counts,
        tokens_spent=tokens_spent,
        coverage=coverage,
        surrogate=surrogate or SurrogateReport(U_hat=0.0, signals={}),
    )


def _relation_columns(relation: Any, seen: set[str]) -> list[str]:
    columns = ["doc_id"]
    for attr in relation.attributes:
        bare = attr.split(".")[-1]
        if bare not in columns:
            columns.append(bare)
        canon = f"{bare}__canonical"
        if canon not in columns and (canon in seen or f"{attr}__canonical" in seen):
            columns.append(canon)
    return columns


def _value(row: dict[str, Any], column: str) -> Any:
    if row.get(column) not in (None, ""):
        return row.get(column)
    fallback = None
    for key, value in row.items():
        bare = str(key).split(".")[-1]
        if value in (None, ""):
            continue
        if bare == column:
            return value
        if bare == f"{column}__surface":
            fallback = value
    return fallback


def _row_belongs(row: dict[str, Any], relation: Any) -> bool:
    entity = getattr(relation, "entity_type", None)
    if not entity:
        return True
    doc_id = str(row.get("doc_id") or "")
    prefix = doc_id.split("/", 1)[0].lower()
    if "/" in doc_id:
        return prefix == entity.lower()
    return any(
        _value(row, attr.split(".")[-1]) not in (None, "")
        for attr in relation.attributes
    )


def _cell(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _payload_hash(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256(repr(rows).encode())
    return digest.hexdigest()
