"""Incremental maintenance of a QuWARTS database when source documents change.

Given a new version of the corpus (the original documents with an overlay of changed, added and
deleted files), the maintainer decides, per level, whether anything must change and how much:

1. **Document.** An unchanged content hash (and field list) means nothing to do. A deleted document
   loses its row; a new one is read.
2. **Chunk.** A changed chained document is aligned with its stored snapshot: every old chunk that
   still occurs verbatim, in order, keeps its boundaries, and only the text between those anchors is
   re-chunked. Stable boundaries are what content-defined chunking gives a file system (LBFS,
   Muthitacharoen et al. 2001); here they come from the old chunks themselves. The document is then
   replayed in order against the read memo: a chunk whose inputs (text, carried note, field list)
   were read before reuses that read; the others are read. When a re-read chunk passes on the same note
   as before, the chunks after it are hits again: early cutoff (build systems). Policy ``exact``
   requires the same note verbatim; ``facts`` accepts a note stating the same facts (numbers and names);
   ``answers`` also ends the ripple when an unchanged chunk, re-read because its note changed, gives the
   same answers as before: the changed note is then observably equivalent for what follows (the re-read
   chunk is the probe), and the rest of the document continues with the old notes and reads.
   Optionally (``attribute``), a re-read value that differs from the stored one is committed only if the
   edit explains it: the stored value's evidence changed (it is stated verbatim and its number of
   occurrences changed), the new value is stated in the added text, or, for a stored value that is not
   stated verbatim, the changed text names the field. Otherwise the change is read noise and the stored
   value is kept (a change must be explained by a change in its provenance).
3. **Cell.** The new database is built with the system's own builder from the reads of the current
   version (reused and new), diffed against the maintained database, and only the differing cells and
   rows are written (the delta); a re-read value equal to the old one writes nothing. The maintained
   database is checked to equal the rebuilt one (maintained view = recomputed view over the same reads,
   the correctness criterion of incremental view maintenance; Gupta & Mumick 1995).
4. **Query.** Column-level lineage names the workload queries a delta can affect; only those are
   re-executed, and the ones whose answers changed are reported.

Under a token budget, documents are refreshed in order of how many workload queries read their table,
cheapest first; the rest keep their old version, are marked stale, and the queries that read them are
flagged (deferred maintenance; Colby et al. 1996). Every read is written to the memo as soon as it
returns, so an interrupted run resumes without paying twice.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from quwarts.core.lineage import store as S
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.router import chunked
from quwarts.core.router.context_probe import SYSTEM, V3, render_prompt, truncate
from quwarts.core.router.corpus_features import list_documents, read_document

OVERHEAD = 1300  # prompt wrapper, field list and answer, per chunk read (cost estimate only)


class Incomplete(Exception):
    """The deadline passed: reads made so far are memoized; run again to finish."""


class Deferred(Exception):
    """The token budget does not cover this document now."""


# --------------------------------------------------------------------------- capture


def capture(store_path: Path, spec, reads, fields, journal: Path, db: Path, queries: dict[str, str]) -> dict[str, Any]:
    """Record the provenance of a finished run (no model calls). ``db`` becomes the maintained database."""

    from quwarts.core.router.executor import load_values

    if store_path.exists():
        raise SystemExit(f"{store_path} exists")
    window = int(V3["window_tokens"])
    by_sha = {}
    for line in journal.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            by_sha[row["prompt_sha"]] = row
    conn = S.open_store(store_path)
    stats = defaultdict(int)
    for read in reads:
        specs = [fields[f"{read.table}.{a}"] for a in read.attributes]
        fsha = S.fields_sha(specs)
        for path in list_documents(spec.table(read.table)):
            text = read_document(path)
            tokens = count_tokens(text)
            if tokens <= window:
                prompt = render_prompt(truncate(text, window), specs, None)
                row = by_sha.get(S.sha(prompt))
                if row is None:
                    stats["unread_documents"] += 1
                    continue
                key = S.single_key(row["prompt_sha"])
                S.put_read(conn, {"read_key": key, "kind": "single", "text_sha": S.sha(text), "fields_sha": fsha,
                                  "response": row["response"], "tokens": row["tokens"], "prompt_sha": row["prompt_sha"]})
                conn.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?)", (read.table, path.name, 0, 0, len(text), S.sha(text), key))
                mode, n = "single", 1
            else:
                pieces = chunked.split_chunks(text, chunked.chunk_tokens(window))
                carry, start, complete = "", 0, True
                for i, piece in enumerate(pieces):
                    plain = chunked.render_chunk_prompt(piece, specs, carry, i + 1, len(pieces))
                    packed = chunked.render_chunk_prompt(chunked.compact(piece), specs, carry, i + 1, len(pieces))
                    row = by_sha.get(S.sha(plain)) or by_sha.get(S.sha(packed))
                    if row is None:
                        complete = False
                        break
                    out = chunked.parse_carry(row["response"], carry)
                    key = S.chunk_key(S.sha(piece), carry, fsha)
                    S.put_read(conn, {"read_key": key, "kind": "chunk", "text_sha": S.sha(piece), "carry_in": carry,
                                      "fields_sha": fsha, "response": row["response"], "carry_out": out,
                                      "tokens": row["tokens"], "compacted": row.get("compacted"), "prompt_sha": row["prompt_sha"]})
                    conn.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?)",
                                 (read.table, path.name, i, start, start + len(piece), S.sha(piece), key))
                    carry, start = out, start + len(piece)
                if not complete:
                    conn.execute("DELETE FROM chunks WHERE tbl = ? AND doc = ?", (read.table, path.name))
                    stats["unread_documents"] += 1
                    continue
                mode, n = "chain", len(pieces)
            conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (read.table, path.name, S.sha(text), tokens, mode, n, fsha, S.snapshot(text), 0, 0))
            stats[f"{mode}_documents"] += 1
    maintained = store_path.parent / "maintained.db"
    shutil.copy2(db, maintained)
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('maintained_sha', ?)", (_file_sha(maintained),))
    support: dict = {}
    load_values(journal, fields, support)
    _store_cells(conn, maintained, reads, support, version=0)
    _store_queries(conn, maintained, queries, version=0)
    conn.execute("INSERT INTO versions VALUES (0, 'capture', ?)", (json.dumps(dict(stats)),))
    conn.commit()
    conn.close()
    return dict(stats)


def _file_sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _store_cells(conn, db: Path, reads, support: dict, version: int, only: set[tuple[str, str]] | None = None) -> None:
    src = sqlite3.connect(db)
    for read in reads:
        for attr in read.attributes:
            for doc, value in src.execute(f'SELECT doc_id, "{attr}" FROM "{read.table}"'):
                if only is not None and (read.table, doc) not in only:
                    continue
                sup = support.get((read.table, read.context, doc, attr))
                conn.execute("INSERT OR REPLACE INTO cells VALUES (?,?,?,?,?,?)",
                             (read.table, doc, attr, S.dump_value(value), json.dumps(sup), version))
    src.close()


def query_lineage(sql: str) -> tuple[list[str], list[str]]:
    from sqlglot import exp

    from quwarts.core.router.templates import _parse, column_set

    tables = sorted({t.name for t in _parse(sql).find_all(exp.Table)})
    return tables, sorted(column_set(sql))


def query_answers(db: Path, queries: dict[str, str], only: set[str] | None = None) -> dict[str, tuple[str, int]]:
    """Each query's answer through the official SQL path, as (hash of the sorted rows, row count).
    The predicate rewriting depends on the whole query set, so it is computed from all ``queries``
    even when only the queries in ``only`` are executed."""

    from quwarts.core.pipeline import official_sql
    from quwarts.core.signature import audit_workload, enumerate_predicates
    from quwarts.core.signature_realize import live_predicates

    audit = audit_workload([{"query_id": q, "sql": s} for q, s in queries.items()])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    conn = sqlite3.connect(db)
    out = {}
    for q, s in queries.items():
        if only is not None and q not in only:
            continue
        rows = conn.execute(official_sql(s, db, predicates, query_id=q)).fetchall()
        out[q] = (S.sha(json.dumps(sorted(repr(r) for r in rows))), len(rows))
    conn.close()
    return out


def _store_queries(conn, db: Path, queries: dict[str, str], version: int) -> None:
    answers = query_answers(db, queries)
    for q, s in queries.items():
        tables, cols = query_lineage(s)
        conn.execute("INSERT OR REPLACE INTO queries VALUES (?,?,?,?,?,?,?)",
                     (q, s, json.dumps(tables), json.dumps(cols), answers[q][0], answers[q][1], version))


# --------------------------------------------------------------------------- change detection


def effective_documents(spec, overlay: Path | None) -> dict[str, dict[str, Path]]:
    """The corpus version to maintain against: each table's documents, overridden and extended by
    ``overlay/<table>/*.txt`` and less the names listed in ``overlay/<table>/DELETED``."""

    out = {}
    for table in spec.tables:
        docs = {p.name: p for p in list_documents(table)}
        if overlay is not None and (overlay / table.sql_name).is_dir():
            layer = overlay / table.sql_name
            docs.update({p.name: p for p in sorted(layer.glob("*.txt"))})
            deleted = layer / "DELETED"
            if deleted.exists():
                for name in deleted.read_text().split():
                    docs.pop(name, None)
        out[table.sql_name] = docs
    return out


def realign(old_text: str, bounds: list[tuple[int, int]], new_text: str, max_tokens: int) -> tuple[list[str], list[int | None]]:
    """Chunks of ``new_text`` that keep every old chunk still present verbatim (in order) and re-chunk
    only the text between them. Returns the chunks and, per chunk, the old index it keeps (or None)."""

    anchors, pos = [], 0
    for i, (a, b) in enumerate(bounds):
        piece = old_text[a:b]
        j = new_text.find(piece, pos)
        if j >= 0:
            anchors.append((j, j + len(piece), i))
            pos = j + len(piece)
    chunks: list[str] = []
    kept: list[int | None] = []
    cur = 0
    for a, b, i in anchors + [(len(new_text), len(new_text), None)]:
        if a > cur:
            new = chunked.split_chunks(new_text[cur:a], max_tokens)
            chunks += new
            kept += [None] * len(new)
        if i is not None:
            chunks.append(new_text[a:b])
            kept.append(i)
        cur = b
    return chunks, kept


@dataclass
class DocPlan:
    table: str
    doc: str
    status: str  # unchanged | new | changed | deleted
    mode: str = ""
    path: Path | None = None
    chunks: list[str] = field(default_factory=list)
    kept: list[int | None] = field(default_factory=list)
    certain: int = 0  # reads needed whatever the re-reads return
    conditional: int = 0  # reads needed unless an upstream re-read passes on an equivalent note
    tokens_estimate: int = 0

    def summary(self) -> dict[str, Any]:
        return {"table": self.table, "doc": self.doc, "status": self.status, "mode": self.mode,
                "chunks": len(self.chunks), "kept_chunks": sum(k is not None for k in self.kept),
                "certain_reads": self.certain, "conditional_reads": self.conditional, "tokens_estimate": self.tokens_estimate}


def plan(conn: sqlite3.Connection, spec, reads, fields, overlay: Path | None, policy: str) -> list[DocPlan]:
    window = int(V3["window_tokens"])
    current = effective_documents(spec, overlay)
    out = []
    for read in reads:
        specs = [fields[f"{read.table}.{a}"] for a in read.attributes]
        fsha = S.fields_sha(specs)
        stored = {doc: (h, mode, fs) for doc, h, mode, fs in
                  conn.execute("SELECT doc, sha, mode, fields_sha FROM documents WHERE tbl = ?", (read.table,))}
        docs = current[read.table]
        for doc in sorted(set(stored) - set(docs)):
            out.append(DocPlan(read.table, doc, "deleted"))
        for doc, path in sorted(docs.items()):
            text = read_document(path)
            old = stored.get(doc)
            if old is not None and old[0] == S.sha(text) and old[2] == fsha:
                out.append(DocPlan(read.table, doc, "unchanged", old[1], path))
                continue
            dp = DocPlan(read.table, doc, "new" if old is None else "changed", path=path)
            if count_tokens(text) <= window:
                dp.mode, dp.chunks, dp.kept = "single", [text], [None]
                prompt = render_prompt(truncate(text, window), specs, None)
                hit = S.get_read(conn, S.single_key(S.sha(prompt))) is not None
                dp.certain = 0 if hit else 1
                dp.tokens_estimate = 0 if hit else count_tokens(prompt) + 400
            else:
                dp.mode = "chain"
                max_tokens = chunked.chunk_tokens(window)
                if old is not None and old[1] == "chain":
                    blob, = conn.execute("SELECT snapshot FROM documents WHERE tbl = ? AND doc = ?", (read.table, doc)).fetchone()
                    bounds = [(a, b) for a, b in conn.execute(
                        "SELECT start, stop FROM chunks WHERE tbl = ? AND doc = ? ORDER BY idx", (read.table, doc))]
                    dp.chunks, dp.kept = realign(S.unsnapshot(blob), bounds, text, max_tokens)
                else:
                    dp.chunks = chunked.split_chunks(text, max_tokens)
                    dp.kept = [None] * len(dp.chunks)
                carry, known = "", True
                for piece in dp.chunks:
                    tsha = S.sha(piece)
                    if known:
                        rec = S.find_chunk_read(conn, tsha, carry, fsha, policy)
                        if rec is not None:
                            carry = rec["carry_out"]
                            continue
                        known = False
                        dp.certain += 1
                        dp.tokens_estimate += count_tokens(piece) + OVERHEAD
                    elif S.has_chunk_text(conn, tsha, fsha):
                        dp.conditional += 1
                    else:
                        dp.certain += 1
                        dp.tokens_estimate += count_tokens(piece) + OVERHEAD
            out.append(dp)
    return out


# --------------------------------------------------------------------------- apply


def _call(caller, prompt: str, meta: dict) -> str:
    return caller.complete(prompt, "provenance_maintain", **meta)


def refresh_document(conn, lock, dp: DocPlan, specs, fsha: str, context: str, caller, policy: str,
                     budget: int | None, deadline: float | None, stats: dict) -> list[dict[str, Any]]:
    """Journal rows for a changed or new document's current version (memo hits and new reads)."""

    from quwarts.core.ledger import BudgetExhausted

    attributes = [f.name for f in specs]
    meta = dict(system=SYSTEM, table=dp.table, doc=dp.doc, context=context)

    def guard(estimate: int) -> None:
        if deadline is not None and time.monotonic() > deadline:
            raise Incomplete(dp.doc)
        if budget is not None and caller.ledger.spent + estimate > budget:
            raise Deferred(dp.doc)

    def row(rec: dict, extra: dict) -> dict:
        return {"table": dp.table, "context": context, "attributes": attributes, "doc": dp.doc,
                "prompt_sha": rec["prompt_sha"], "response": rec["response"], "tokens": rec["tokens"], **extra}

    if dp.mode == "single":
        prompt = render_prompt(truncate(dp.chunks[0], int(V3["window_tokens"])), specs, None)
        key = S.single_key(S.sha(prompt))
        with lock:
            rec = S.get_read(conn, key)
        if rec is None:
            guard(count_tokens(prompt) + 400)
            try:
                text = _call(caller, prompt, meta)
            except BudgetExhausted as exc:
                raise Deferred(dp.doc) from exc
            rec = {"read_key": key, "kind": "single", "text_sha": S.sha(dp.chunks[0]), "fields_sha": fsha,
                   "response": text, "tokens": count_tokens(prompt) + count_tokens(text), "prompt_sha": S.sha(prompt)}
            with lock:
                S.put_read(conn, rec)
                conn.commit()
                stats["reads"] += 1
                stats["read_tokens"] += rec["tokens"]
        else:
            with lock:
                stats["memo_hits"] += 1
        return [row(rec, {})]

    rows, carry, n = [], "", len(dp.chunks)
    lookup = "facts" if policy == "answers" else policy
    old_reads: dict[int, dict] = {}
    if policy == "answers" and dp.status == "changed":
        with lock:
            for i, key in conn.execute("SELECT idx, read_key FROM chunks WHERE tbl = ? AND doc = ? ORDER BY idx",
                                       (dp.table, dp.doc)).fetchall():
                old_reads[i] = S.get_read(conn, key)
    for idx, piece in enumerate(dp.chunks):
        tsha = S.sha(piece)
        with lock:
            rec = S.find_chunk_read(conn, tsha, carry, fsha, lookup)
        if rec is None:
            prompt = chunked.render_chunk_prompt(piece, specs, carry, idx + 1, n)
            guard(count_tokens(prompt) + 400)
            compacted = False
            try:
                try:
                    text = _call(caller, prompt, meta)
                except BudgetExhausted:
                    raise
                except Exception as exc:  # noqa: BLE001
                    if not chunked.too_long(exc):
                        raise
                    prompt, compacted = chunked.render_chunk_prompt(chunked.compact(piece), specs, carry, idx + 1, n), True
                    text = _call(caller, prompt, meta)
            except BudgetExhausted as exc:
                raise Deferred(dp.doc) from exc
            rec = {"read_key": S.chunk_key(tsha, carry, fsha), "kind": "chunk", "text_sha": tsha, "carry_in": carry,
                   "fields_sha": fsha, "response": text, "carry_out": chunked.parse_carry(text, carry),
                   "tokens": count_tokens(prompt) + count_tokens(text), "compacted": compacted, "prompt_sha": S.sha(prompt)}
            with lock:
                S.put_read(conn, rec)
                conn.commit()
                stats["reads"] += 1
                stats["read_tokens"] += rec["tokens"]
                if dp.kept[idx] is not None:
                    stats["reads_of_kept_chunks"] += 1  # an unchanged chunk re-read because its note changed
        else:
            with lock:
                stats["memo_hits"] += 1
        rows.append(row(rec, {"chunk": idx, "chunks": n, "_key": rec["read_key"]}))
        carry = rec["carry_out"]
        before = old_reads.get(dp.kept[idx]) if dp.kept[idx] is not None else None
        if before is not None and before["read_key"] != rec["read_key"] and same_answers(before["response"], rec["response"], specs):
            carry = before["carry_out"]  # probe cutoff: continue with the old notes (their reads are memo hits)
            with lock:
                stats["answer_cutoffs"] += 1
    return rows


def same_answers(a: str, b: str, specs) -> bool:
    from quwarts.core.router.executor import commit_value
    from quwarts.core.router.probes import parse_fields

    names = [f.name for f in specs]
    pa, pb = parse_fields(a, names), parse_fields(b, names)
    return all(same_value(commit_value(pa.get(f.name), f), commit_value(pb.get(f.name), f)) for f in specs)


def same_value(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a)))
    return str(a).strip().casefold() == str(b).strip().casefold()


# ---- evidence attribution of cell changes

_NAME_STOP = {"the", "and", "for", "num", "of", "or", "is", "has", "any", "per"}


def _surfaces(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = abs(float(value))
        if v.is_integer():
            return [f"{int(v):,}", f"{int(v)}"]
        return [f"{v:,.2f}", f"{v:.2f}", f"{v:g}"]
    text = str(value).strip()
    return [p.strip() for p in text.split("||") if len(p.strip()) >= 3] if text else []


def _count(text: str, value: Any) -> int:
    import re

    n = 0
    for surface in _surfaces(value):
        n += len(re.findall(r"(?<![\w.,])" + re.escape(surface) + r"(?![\w]|[.,]\d)", text, flags=re.I))
    return n


def line_diff(old: str, new: str) -> tuple[str, str]:
    """Added and removed text as multiset differences of lines (order-free, linear time)."""

    from collections import Counter

    a, b = Counter(old.splitlines()), Counter(new.splitlines())
    added = "\n".join(line for line, k in (b - a).items() for _ in range(k))
    removed = "\n".join(line for line, k in (a - b).items() for _ in range(k))
    return added, removed


def explained(field, old_value: Any, new_value: Any, old_text: str, new_text: str, added: str, removed: str) -> bool:
    """Is a change of this cell from ``old_value`` to ``new_value`` explained by the edit?"""

    import re

    before = _count(old_text, old_value)
    if before and _count(new_text, old_value) != before:
        return True  # the stored value's evidence changed
    if _count(added, new_value):
        return True  # the new value is stated in the added text
    if not before:
        names = {w for w in field.name.lower().split("_") if len(w) >= 3 and w not in _NAME_STOP}
        diff = (added + "\n" + removed).lower()
        return any(re.search(r"\b" + re.escape(w), diff) for w in names)
    return False


def _table_rows(conn: sqlite3.Connection, table: str) -> tuple[list[str], dict[Any, tuple]]:
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    body = {}
    rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
    if "doc_id" not in cols:  # not a document table: compared as a whole
        return cols, {"__all__": tuple(sorted(map(repr, rows)))}
    for r in rows:
        body[r[cols.index("doc_id")]] = tuple(r)
    return cols, body


def diff_databases(old: Path, new: Path) -> dict[str, Any]:
    """Row and cell differences between two databases with the same tables (keyed by doc_id)."""

    a, b = sqlite3.connect(old), sqlite3.connect(new)
    tables = [n for (n,) in b.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    out: dict[str, Any] = {"tables": {}, "schema_changed": False}
    for t in tables:
        cols_b, rows_b = _table_rows(b, t)
        try:
            cols_a, rows_a = _table_rows(a, t)
        except sqlite3.OperationalError:
            out["schema_changed"] = True
            continue
        if cols_a != cols_b or ("doc_id" not in cols_b and rows_a != rows_b):
            out["schema_changed"] = True
            continue
        if "doc_id" not in cols_b:
            continue
        cells = []
        for doc in sorted(set(rows_a) & set(rows_b)):
            for c, x, y in zip(cols_b, rows_a[doc], rows_b[doc]):
                if x != y:
                    cells.append((doc, c, x, y))
        out["tables"][t] = {"columns": cols_b, "deleted": sorted(set(rows_a) - set(rows_b)),
                            "inserted": [rows_b[d] for d in sorted(set(rows_b) - set(rows_a))], "cells": cells}
    a.close()
    b.close()
    return out


def apply_delta(db: Path, delta: dict[str, Any]) -> None:
    conn = sqlite3.connect(db)
    with conn:
        for t, d in delta["tables"].items():
            cols = d["columns"]
            conn.executemany(f'DELETE FROM "{t}" WHERE doc_id = ?', [(x,) for x in d["deleted"]])
            conn.executemany(f'INSERT INTO "{t}" VALUES ({",".join("?" * len(cols))})', d["inserted"])
            for doc, col, _old, new in d["cells"]:
                conn.execute(f'UPDATE "{t}" SET "{col}" = ? WHERE doc_id = ?', (new, doc))
    conn.close()


def _view(spec, current: dict[str, dict[str, Path]]):
    """A corpus spec whose table directories hold (links to) the current version of every document."""

    root = Path(tempfile.mkdtemp(prefix="quwarts_view_"))
    tables = []
    for t in spec.tables:
        d = root / t.sql_name
        d.mkdir()
        for name, path in current[t.sql_name].items():
            os.symlink(Path(path).resolve(), d / name)
        tables.append(replace(t, doc_dir=d))
    return replace(spec, tables=tuple(tables)), root


def _incumbent_view(spec, current: dict[str, dict[str, Path]], dest: Path) -> Path:
    """The incumbent database with its document rows matched to the current version: rows of deleted
    documents removed, a row added (all NULL) per new document. The builder blanks it as before."""

    shutil.copy2(spec.incumbent_db, dest)
    conn = sqlite3.connect(dest)
    with conn:
        for t in spec.tables:
            ids = [d for (d,) in conn.execute(f'SELECT doc_id FROM "{t.sql_name}"')]
            name = {(str(d) if str(d).endswith(".txt") else f"{Path(str(d)).name}.txt"): d for d in ids}
            suffix = all(str(d).endswith(".txt") for d in ids) if ids else True
            for n, d in name.items():
                if n not in current[t.sql_name]:
                    conn.execute(f'DELETE FROM "{t.sql_name}" WHERE doc_id = ?', (d,))
            for n in current[t.sql_name]:
                if n not in name:
                    conn.execute(f'INSERT INTO "{t.sql_name}" (doc_id) VALUES (?)', (n if suffix else n[:-4],))
    conn.close()
    return dest


def apply(store_path: Path, spec, reads, fields, queries: dict[str, str], overlay: Path | None, policy: str,
          caller, budget: int | None = None, workers: int = 16, deadline: float | None = None,
          workload: dict[str, str] | None = None, build=None, attribute: bool = False) -> dict[str, Any]:
    """Bring the maintained database to the corpus version ``spec`` + ``overlay``. ``queries``: every
    query the database serves; ``workload``: the reference workload used to prioritize (default: queries).
    ``build(spec, reads, values, fields, queries, dest)``: the system's database builder, the one
    that built the maintained database (passed in: core does not import the evaluation layer)."""

    from quwarts.core.router.executor import load_values

    if build is None:
        raise ValueError("apply needs the database builder")

    started = time.monotonic()
    stop_at = None if deadline is None else started + deadline
    conn = S.open_store(store_path)
    lock = threading.Lock()
    maintained = store_path.parent / "maintained.db"
    recorded = conn.execute("SELECT value FROM meta WHERE key = 'maintained_sha'").fetchone()
    if recorded is None or recorded[0] != _file_sha(maintained):
        raise RuntimeError(f"{maintained} does not match the version its store records (edited outside apply, "
                           "or an apply was interrupted while writing it)")
    plans = plan(conn, spec, reads, fields, overlay, policy)
    todo = [p for p in plans if p.status in ("new", "changed")]
    by_table = {r.table: r for r in reads}
    usage = defaultdict(int)
    for s in (workload or queries).values():
        for t in query_lineage(s)[0]:
            usage[t] += 1
    todo.sort(key=lambda p: (-usage[p.table], p.tokens_estimate, p.doc))
    stats: dict[str, Any] = defaultdict(int)
    fresh: dict[tuple[str, str], list[dict]] = {}
    deferred: list[str] = []

    def work(dp: DocPlan):
        read = by_table[dp.table]
        specs = [fields[f"{dp.table}.{a}"] for a in read.attributes]
        try:
            fresh[(dp.table, dp.doc)] = refresh_document(conn, lock, dp, specs, S.fields_sha(specs), read.context, caller,
                                                         policy, budget, stop_at, stats)
        except Deferred:
            deferred.append(f"{dp.table}/{dp.doc}")

    incomplete = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, dp) for dp in todo]
        for fut in futures:
            try:
                fut.result()
            except Incomplete:
                incomplete = True
    base = {"plan": [p.summary() for p in plans if p.status != "unchanged"],
            "documents": {s: sum(p.status == s for p in plans) for s in ("unchanged", "changed", "new", "deleted")},
            **{k: v for k, v in stats.items()}}
    if incomplete:
        conn.close()
        return {**base, "status": "incomplete", "seconds": round(time.monotonic() - started, 1)}

    # Journal of the current version: fresh rows for refreshed documents, stored rows for the rest.
    current = effective_documents(spec, overlay)
    rows: list[dict] = []
    stale: set[tuple[str, str]] = set()
    status = {(p.table, p.doc): p.status for p in plans}
    for read in reads:
        for doc in current[read.table]:
            key = (read.table, doc)
            if key in fresh:
                rows += [{k: v for k, v in r.items() if k != "_key"} for r in fresh[key]]
            elif status.get(key) == "unchanged" or (status.get(key) == "changed" and f"{read.table}/{doc}" in deferred):
                rows += S.journal_rows(conn, read.table, doc, list(read.attributes), read.context)
                if status.get(key) == "changed":
                    stale.add(key)
            else:
                stale.add(key)  # a new document deferred by the budget: its row stays NULL
    work_dir = Path(tempfile.mkdtemp(prefix="quwarts_maint_"))
    journal = work_dir / "reads.jsonl"
    journal.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    support: dict = {}
    values = load_values(journal, fields, support)
    if attribute:
        from quwarts.core.router.executor import commit_value

        for p in plans:
            key = (p.table, p.doc)
            if p.status != "changed" or key not in fresh:
                continue
            read = by_table[p.table]
            blob, = conn.execute("SELECT snapshot FROM documents WHERE tbl = ? AND doc = ?", key).fetchone()
            old_text, new_text = S.unsnapshot(blob), read_document(p.path)
            added, removed = line_diff(old_text, new_text)
            got = values[(p.table, read.context)][p.doc]
            for attr in read.attributes:
                f = fields[f"{p.table}.{attr}"]
                (stored,) = conn.execute("SELECT value FROM cells WHERE tbl = ? AND doc = ? AND attr = ?", (*key, attr)).fetchone()
                old_value, new_value = json.loads(stored), commit_value(got.get(attr), f)
                if same_value(old_value, new_value):
                    continue
                if explained(f, old_value, new_value, old_text, new_text, added, removed):
                    stats["changes_explained"] += 1
                else:
                    got[attr] = old_value
                    stats["changes_kept_unexplained"] += 1
    view, view_root = _view(spec, current)
    if spec.incumbent_db is not None and Path(spec.incumbent_db).is_file():
        view = replace(view, incumbent_db=_incumbent_view(spec, current, work_dir / "incumbent.db"))
    rebuilt = work_dir / "rebuilt.db"
    build(view, reads, values, fields, queries, rebuilt)
    delta = diff_databases(maintained, rebuilt)

    version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM versions").fetchone()[0]
    changed_cols: dict[str, set[str]] = defaultdict(set)
    row_changes: set[str] = set()
    n_cells = 0
    for t, d in delta["tables"].items():
        for doc, col, old, new in d["cells"]:
            changed_cols[t].add(col)
            n_cells += 1
            conn.execute("INSERT INTO history VALUES (?,?,?,?,?,?,?)",
                         (version, t, doc, col, S.dump_value(old), S.dump_value(new), status.get((t, doc), "")))
        for doc in d["deleted"]:
            row_changes.add(t)
            conn.execute("INSERT INTO history VALUES (?,?,?,?,?,?,?)", (version, t, doc, "*", "row", None, "deleted"))
        for r in d["inserted"]:
            row_changes.add(t)
            conn.execute("INSERT INTO history VALUES (?,?,?,?,?,?,?)",
                         (version, t, r[d["columns"].index("doc_id")], "*", None, "row", "new"))

    # Query impact through column lineage; stale documents flag the queries that read their table.
    affected, flagged = [], []
    stale_tables = {t for t, _d in stale}
    for qid, tables, cols in conn.execute("SELECT qid, tables, columns FROM queries").fetchall():
        tables, cols = set(json.loads(tables)), set(json.loads(cols))
        if delta["schema_changed"] or any(t in row_changes or (changed_cols[t] & (cols | {"*"})) or ("*" in cols and changed_cols[t])
                                          for t in tables):
            affected.append(qid)
        if tables & stale_tables:
            flagged.append(qid)
    answers = query_answers(rebuilt, queries, set(affected)) if affected else {}
    stored = {q: a for q, a in conn.execute("SELECT qid, answer_sha FROM queries")}
    answer_changed = sorted(q for q, (h, _n) in answers.items() if stored.get(q) != h)
    for q, (h, n) in answers.items():
        conn.execute("UPDATE queries SET answer_sha = ?, rows = ?, version = ? WHERE qid = ?", (h, n, version, q))

    # The store now describes the current version.
    for p in plans:
        key = (p.table, p.doc)
        if p.status == "deleted":
            conn.execute("DELETE FROM documents WHERE tbl = ? AND doc = ?", key)
            conn.execute("DELETE FROM chunks WHERE tbl = ? AND doc = ?", key)
            conn.execute("DELETE FROM cells WHERE tbl = ? AND doc = ?", key)
        elif key in fresh:
            text = read_document(p.path)
            read = by_table[p.table]
            specs = [fields[f"{p.table}.{a}"] for a in read.attributes]
            conn.execute("DELETE FROM chunks WHERE tbl = ? AND doc = ?", key)
            start = 0
            for idx, (piece, r) in enumerate(zip(p.chunks, fresh[key])):
                rk = r.get("_key") or S.single_key(r["prompt_sha"])
                conn.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?)", (*key, idx, start, start + len(piece), S.sha(piece), rk))
                start += len(piece)
            conn.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (*key, S.sha(text), count_tokens(text), p.mode, len(p.chunks), S.fields_sha(specs),
                          S.snapshot(text), 0, version))
        elif key in stale and p.status == "changed":
            conn.execute("UPDATE documents SET stale = 1 WHERE tbl = ? AND doc = ?", key)
    # Write the delta last, then record the database's hash in the same store transaction.
    if delta["schema_changed"]:
        shutil.copy2(rebuilt, maintained)
    else:
        apply_delta(maintained, delta)
        check = diff_databases(maintained, rebuilt)
        assert not any(d["cells"] or d["deleted"] or d["inserted"] for d in check["tables"].values()), "delta mismatch"
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('maintained_sha', ?)", (_file_sha(maintained),))
    _store_cells(conn, maintained, reads, support, version, only=set(fresh) | {k for k in stale})
    report = {**base, "status": "applied", "version": version, "policy": policy, "attribute": attribute,
              "changes_explained": stats.get("changes_explained", 0),
              "changes_kept_unexplained": stats.get("changes_kept_unexplained", 0),
              "answer_cutoffs": stats.get("answer_cutoffs", 0),
              "cells_changed": n_cells, "rows_deleted": sum(len(d["deleted"]) for d in delta["tables"].values()),
              "rows_inserted": sum(len(d["inserted"]) for d in delta["tables"].values()),
              "deferred_documents": sorted(deferred), "stale_documents": sorted(f"{t}/{d}" for t, d in stale),
              "queries_reexecuted": len(affected), "queries_answer_changed": answer_changed,
              "queries_flagged_stale": sorted(flagged), "spent_tokens": caller.ledger.spent if caller else 0,
              "seconds": round(time.monotonic() - started, 1)}
    conn.execute("INSERT INTO versions VALUES (?,?,?)", (version, f"apply {policy}", json.dumps(report, default=str)))
    conn.commit()
    conn.close()
    shutil.rmtree(view_root, ignore_errors=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    return report
