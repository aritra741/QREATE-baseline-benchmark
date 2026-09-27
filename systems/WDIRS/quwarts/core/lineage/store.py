"""Provenance store: where every cell of a QuWARTS database comes from.

One SQLite file next to a run. Its tables, and the classical idea behind each:

* ``reads``: a content-addressed memo of model reads (the action cache of build systems: Bazel,
  Salsa; Mokhov et al., "Build Systems a la Carte"). A single read is keyed by the hash of its
  prompt. A chunk read of a chained document is keyed by the hash of its chunk text, the carried note
  it received and the field list: its inputs apart from the position label ("part 3 of 12"), which is
  the one declared approximation. Any document, under any name, whose chunk has the same inputs
  reuses the read.
* ``documents`` and ``chunks``: the version of each source document the database reflects (content
  hash, a compressed snapshot, the chunk boundaries and the read each chunk used). The snapshot is the
  before-image needed to align a changed document with its old chunks.
* ``cells``: each committed value and the chunks that support it (where-provenance: Buneman, Khanna
  & Tan 2001). A value no chunk states depends on the whole document (why-provenance / lineage: Cui &
  Widom 2000).
* ``queries``: each workload query's tables and columns (column-level lineage) and a hash of its
  current answer.
* ``history`` and ``versions``: every changed cell with its old and new value, per maintenance
  version.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import zlib
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS versions(version INTEGER PRIMARY KEY, note TEXT, stats TEXT);
CREATE TABLE IF NOT EXISTS documents(tbl TEXT, doc TEXT, sha TEXT, tokens INTEGER, mode TEXT, n_chunks INTEGER,
    fields_sha TEXT, snapshot BLOB, stale INTEGER DEFAULT 0, version INTEGER, PRIMARY KEY (tbl, doc));
CREATE TABLE IF NOT EXISTS chunks(tbl TEXT, doc TEXT, idx INTEGER, start INTEGER, stop INTEGER, text_sha TEXT,
    read_key TEXT, PRIMARY KEY (tbl, doc, idx));
CREATE TABLE IF NOT EXISTS reads(read_key TEXT PRIMARY KEY, kind TEXT, text_sha TEXT, carry_in TEXT,
    carry_facts TEXT, fields_sha TEXT, response TEXT, carry_out TEXT, tokens INTEGER, compacted INTEGER,
    prompt_sha TEXT);
CREATE INDEX IF NOT EXISTS reads_by_text ON reads(text_sha, fields_sha, carry_facts);
CREATE TABLE IF NOT EXISTS cells(tbl TEXT, doc TEXT, attr TEXT, value TEXT, support TEXT, version INTEGER,
    PRIMARY KEY (tbl, doc, attr));
CREATE TABLE IF NOT EXISTS queries(qid TEXT PRIMARY KEY, sql TEXT, tables TEXT, columns TEXT, answer_sha TEXT,
    rows INTEGER, version INTEGER);
CREATE TABLE IF NOT EXISTS history(version INTEGER, tbl TEXT, doc TEXT, attr TEXT, old TEXT, new TEXT, reason TEXT);
"""

# Words that carry no fact in a carried note (a standard function-word list plus the two words the chunk
# prompt itself uses for the text: "part" and "document").
_STOP = {
    "a", "an", "the", "this", "that", "these", "those", "it", "its", "is", "are", "was", "were", "be", "been",
    "in", "on", "of", "for", "and", "or", "to", "from", "by", "with", "as", "at", "which", "who", "has", "have",
    "part", "parts", "document",
}
_FACT = re.compile(r"\d[\d,.]*\d|\d|[A-Za-z][A-Za-z&'.-]*")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fields_sha(specs) -> str:
    return sha("\n".join(f.line() for f in specs))


def carry_facts(note: str) -> str:
    """The facts a carried note states: its numbers and its capitalized words, less function words.
    Two notes with the same facts are treated as the same input under the ``facts`` policy."""

    facts = set()
    for tok in _FACT.findall(note or ""):
        tok = tok.strip(".,'-")
        if not tok or tok.lower() in _STOP:
            continue
        if tok[0].isdigit() or tok[0].isupper():
            facts.add(tok.replace(",", ""))
    return " ".join(sorted(facts))


def single_key(prompt_sha: str) -> str:
    return "s:" + prompt_sha


def chunk_key(text_sha: str, carry: str, fsha: str) -> str:
    return "c:" + sha(f"{text_sha}\0{carry}\0{fsha}")


def open_store(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.executescript(SCHEMA)
    return conn


def snapshot(text: str) -> bytes:
    return zlib.compress(text.encode("utf-8"), 6)


def unsnapshot(blob: bytes) -> str:
    return zlib.decompress(blob).decode("utf-8")


def put_read(conn: sqlite3.Connection, rec: dict[str, Any]) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO reads VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (rec["read_key"], rec["kind"], rec["text_sha"], rec.get("carry_in", ""), carry_facts(rec.get("carry_in", "")),
         rec["fields_sha"], rec["response"], rec.get("carry_out", ""), int(rec.get("tokens", 0)),
         int(bool(rec.get("compacted"))), rec.get("prompt_sha", "")),
    )


def get_read(conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM reads WHERE read_key = ?", (key,)).fetchone()
    return _read_row(conn, row)


def find_chunk_read(conn: sqlite3.Connection, text_sha: str, carry: str, fsha: str, policy: str) -> dict[str, Any] | None:
    """The memoized read of a chunk with these inputs. ``exact``: same carried note. ``facts``: a note
    stating the same facts (the exact match is preferred)."""

    rec = get_read(conn, chunk_key(text_sha, carry, fsha))
    if rec is not None or policy == "exact":
        return rec
    row = conn.execute("SELECT * FROM reads WHERE kind = 'chunk' AND text_sha = ? AND fields_sha = ? AND carry_facts = ? "
                       "ORDER BY read_key LIMIT 1", (text_sha, fsha, carry_facts(carry))).fetchone()
    return _read_row(conn, row)


def has_chunk_text(conn: sqlite3.Connection, text_sha: str, fsha: str) -> bool:
    return conn.execute("SELECT 1 FROM reads WHERE kind = 'chunk' AND text_sha = ? AND fields_sha = ? LIMIT 1",
                        (text_sha, fsha)).fetchone() is not None


def _read_row(conn: sqlite3.Connection, row) -> dict[str, Any] | None:
    if row is None:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM reads LIMIT 0").description]
    return dict(zip(cols, row))


def journal_rows(conn: sqlite3.Connection, table: str, doc: str, attributes: list[str], context: str) -> list[dict[str, Any]]:
    """The reads a document's stored version used, as execution-journal rows (``executor.load_values``)."""

    mode, n = conn.execute("SELECT mode, n_chunks FROM documents WHERE tbl = ? AND doc = ?", (table, doc)).fetchone()
    out = []
    for idx, key in conn.execute("SELECT idx, read_key FROM chunks WHERE tbl = ? AND doc = ? ORDER BY idx", (table, doc)):
        rec = get_read(conn, key)
        row = {"table": table, "context": context, "attributes": attributes, "doc": doc,
               "prompt_sha": rec["prompt_sha"], "response": rec["response"], "tokens": rec["tokens"]}
        if mode == "chain":
            row.update(chunk=idx, chunks=n)
        out.append(row)
    return out


def dump_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
