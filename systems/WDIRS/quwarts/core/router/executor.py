"""Execute a router-v3 plan: run the chosen reads, materialize per-query databases.

Each query gets its own database: a copy of the incumbent (or an empty table per
source document when there is no incumbent) in which every need of that query
is filled from the provider the plan assigned to it. Two queries whose needs on
the same attribute were assigned different providers therefore see different
values for that column: this is how context-split columns are realized without
changing the query text. The official SQL path (``pipeline.official_sql``) then
runs each query against its own database.

Writes are additive by default (``fill``): a provider value fills an incumbent
NULL and never overwrites a non-null incumbent value (handoff finding 9.1).
``replace`` overwrites and is recorded when used. Every read is journaled with
its prompt hash and raw response, and reads are resumable by prompt hash.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.router.comparator import as_text, is_null
from quwarts.core.router.context_probe import SYSTEM, V3, FieldSpec, complete, render_prompt, truncate
from quwarts.core.router.corpus_features import list_documents, read_document
from quwarts.core.router.facility import INCUMBENT
from quwarts.core.router.needs import CANONICAL
from quwarts.core.router.probes import parse_fields
from quwarts.core.router.registry import CorpusSpec

_lock = threading.Lock()


@dataclass(frozen=True)
class Read:
    table: str
    context: str
    attributes: tuple[str, ...]


def reads_from_plan(plan: dict[str, Any]) -> list[Read]:
    wanted: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in plan["decisions"]:
        if row["provider"] != INCUMBENT:
            wanted[(row["table"], row["provider"])].add(row["attribute"])
    return [Read(t, c, tuple(sorted(a))) for (t, c), a in sorted(wanted.items())]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_reads(
    spec: CorpusSpec,
    reads: list[Read],
    queries: dict[str, str],
    fields: dict[str, FieldSpec],
    caller: BudgetedCaller | None,
    journal: Path,
    workers: int = 8,
    long_documents: str = "head",
    deadline: float | None = None,
) -> dict[str, Any]:
    """Run every (read, document) call not already in the journal. Returns coverage stats.

    ``long_documents``: ``head`` reads the first window of a longer document (the original
    behaviour); ``chain`` reads all of it as ordered long chunks with carried context
    (``core.router.chunked``). Documents that fit the window are read once either way.
    ``deadline`` (seconds, counted once the calls are planned): no new call starts after it; calls
    in flight finish and are journaled, and a later run resumes from the journal.
    """

    import time

    from quwarts.core.router import chunked
    from quwarts.core.retrieve_extract.tokens import count_tokens

    if long_documents not in ("head", "chain"):
        raise ValueError(long_documents)
    window = int(V3["window_tokens"])
    done: dict[str, str] = {}
    if journal.exists():
        for line in journal.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["prompt_sha"]] = row["response"]
    tasks = []
    chains = []
    for read in reads:
        specs = [fields[f"{read.table}.{a}"] for a in read.attributes]
        sql = queries.get(read.context)  # None for shared (query-independent) contexts
        for path in list_documents(spec.table(read.table)):
            text = read_document(path)
            if long_documents == "chain" and sql is None and count_tokens(text) > window:
                chains.append((read, path.name, chunked.split_chunks(text, chunked.chunk_tokens(window)), specs))
                continue
            prompt = render_prompt(truncate(text, window), specs, sql)
            sha = _sha(prompt)
            if sha not in done:
                tasks.append((read, path.name, prompt, sha))
    stats = {"planned_calls": len(tasks), "done_before": len(done), "exhausted": False,
             "chained_documents": len(chains), "chunks": sum(len(c[2]) for c in chains), "chunk_calls": 0}
    if caller is None or not (tasks or chains):
        return stats
    journal.parent.mkdir(parents=True, exist_ok=True)
    if deadline is not None:
        deadline = time.monotonic() + deadline

    def chain(task):
        read, doc, chunks, specs = task
        carry = ""
        for index, chunk in enumerate(chunks):
            prompt = chunked.render_chunk_prompt(chunk, specs, carry, index + 1, len(chunks))
            compacted = chunked.render_chunk_prompt(chunked.compact(chunk), specs, carry, index + 1, len(chunks))
            sha = _sha(prompt)
            text = done.get(sha)
            if text is None and _sha(compacted) in done:  # the endpoint rejected this chunk before
                sha, text = _sha(compacted), done[_sha(compacted)]
            if text is None:
                if deadline is not None and time.monotonic() > deadline:
                    stats["stopped_at_deadline"] = True
                    return
                meta = dict(system=SYSTEM, table=read.table, doc=doc, context=read.context)
                was_compacted = False
                try:
                    try:
                        text = caller.complete(prompt, "router_v3_execute_chunk", **meta)
                    except BudgetExhausted:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        if not chunked.too_long(exc):
                            raise
                        sha, was_compacted = _sha(compacted), True
                        text = caller.complete(compacted, "router_v3_execute_chunk", **meta)
                except BudgetExhausted:
                    stats["exhausted"] = True
                    return
                except Exception as exc:  # noqa: BLE001
                    if not chunked.too_long(exc):
                        raise
                    stats.setdefault("rejected_chunks", []).append(f"{doc}#{index}")
                    return  # still too long after compaction: the chain stops, the document keeps its head read
                row = {"table": read.table, "context": read.context, "attributes": list(read.attributes), "doc": doc,
                       "prompt_sha": sha, "response": text, "tokens": caller.ledger.records[-1].tokens,
                       "chunk": index, "chunks": len(chunks), "carry_in": carry, "compacted": was_compacted}
                with _lock, journal.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    stats["chunk_calls"] += 1
            carry = chunked.parse_carry(text, carry)

    def one(task):
        read, doc, prompt, sha = task
        if deadline is not None and time.monotonic() > deadline:
            stats["stopped_at_deadline"] = True
            return
        try:
            text = caller.complete(prompt, "router_v3_execute", system=SYSTEM, table=read.table, doc=doc, context=read.context)
        except BudgetExhausted:
            stats["exhausted"] = True
            return
        row = {"table": read.table, "context": read.context, "attributes": list(read.attributes), "doc": doc,
               "prompt_sha": sha, "response": text, "tokens": caller.ledger.records[-1].tokens}
        with _lock, journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Longest chains first: they are sequential inside a document and set the wall-clock time.
        futures = [pool.submit(chain, c) for c in sorted(chains, key=lambda c: -len(c[2]))]
        futures += [pool.submit(one, t) for t in tasks]
        for future in futures:
            future.result()
    return stats


def load_values(journal: Path, fields: dict[str, FieldSpec] | None = None,
                provenance: dict | None = None) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    """``{(table, context): {doc: {attribute: raw value}}}`` from the execution journal.

    Chunk rows of chained reads (``chunked``) are combined per field with ``chunked.reduce_chunks``,
    which needs the field specs, and take precedence over a single read of the same document.
    ``provenance``, when given, receives ``{(table, context, doc, attribute): [supporting chunks]}``.
    """

    from quwarts.core.router.chunked import reduce_chunks

    out: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    if not journal.exists():
        return out
    chunk_rows: dict[tuple[str, str, str], dict[int, dict[str, Any]]] = defaultdict(dict)
    for line in journal.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        parsed = parse_fields(row["response"], row["attributes"])
        answer = {a: parsed.get(a) for a in row["attributes"]}
        if "chunk" in row:
            chunk_rows[(row["table"], row["context"], row["doc"])][int(row["chunk"])] = {**row, "answer": answer}
            continue
        out[(row["table"], row["context"])][row["doc"]] = answer
    for (table, context, doc), rows in chunk_rows.items():
        if fields is None:
            raise ValueError("chained reads in the journal: load_values needs the field specs")
        first = rows[min(rows)]
        if sorted(rows) != list(range(int(first["chunks"]))):
            continue  # incomplete chain (an interrupted run): keep any single read of the document
        answers = [rows[i]["answer"] for i in sorted(rows)]
        values = {}
        for attribute in first["attributes"]:
            value, support = reduce_chunks(answers, fields[f"{table}.{attribute}"])
            values[attribute] = value
            if provenance is not None:
                provenance[(table, context, doc, attribute)] = support
        out[(table, context)][doc] = values
    return out


def commit_value(value: Any, field: FieldSpec) -> Any:
    """Commit-time normalization shared with the other QuWARTS arms (compiler rule 9)."""

    if is_null(value):
        # A null answer takes the field's declared absence value (never-null fields only; e.g.
        # "0 if none", a never-null count); a nullable field stays null.
        from quwarts.core.router.context_probe import absence_value

        value = absence_value(field)
        if value is None:
            return None
    if isinstance(value, list):
        value = " || ".join(as_text(v) for v in value if not is_null(v))
    value = complete(value, field)  # declared domain, then declared absence value
    if value is None:
        return None
    if isinstance(value, bool) or (isinstance(value, (int, float)) and field.value_type not in ("int", "float")):
        value = str(int(value)) if isinstance(value, (int, bool)) else str(value)
    dtype = "numeric" if field.value_type in ("int", "float") else "string"
    normalized, _unit, error = normalize_value(value, dtype)
    if dtype == "numeric" and (error or normalized is None):
        return None  # unparseable numbers stay null (rule 9)
    return normalized


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _surface_key(text: str) -> str:
    import re as _re

    return _re.sub(r"\s+", " ", text).strip().strip(".,;:").casefold()


def canonicalize_surface(conn: sqlite3.Connection, table: str, columns: list[str]) -> dict[str, int]:
    """Per text column, give values that differ only in case, spacing or edge punctuation the column's
    most frequent spelling ('TRACEY' and 'Tracey' become one group). Uses no constants: the spelling
    convention comes from the extracted column itself. Returns the number of rewritten cells per column."""

    changed: dict[str, int] = {}
    for col in columns:
        rows = [(rowid, v) for rowid, v in conn.execute(f'SELECT rowid, "{col}" FROM "{table}"')
                if isinstance(v, str) and v.strip()]
        spellings: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for _rowid, v in rows:
            for part in v.split("||"):
                spellings[_surface_key(part)][part.strip()] += 1
        best = {k: max(sorted(c), key=lambda s: c[s]) for k, c in spellings.items()}
        n = 0
        for rowid, v in rows:
            new = " || ".join(best[_surface_key(p)] for p in v.split("||"))
            if new != v:
                conn.execute(f'UPDATE "{table}" SET "{col}" = ? WHERE rowid = ?', (new, rowid))
                n += 1
        changed[col] = n
    return changed


def base_database(spec: CorpusSpec, needs_attrs: dict[str, set[str]], incumbent: Path | None, dest: Path,
                  fields: dict[str, FieldSpec] | None = None) -> Path:
    """The incumbent, or an empty table per source document with every needed column.

    Empty tables follow the missing-column invariant: numeric attributes are REAL,
    everything else TEXT, all NULL.
    """

    dest.parent.mkdir(parents=True, exist_ok=True)
    if incumbent is not None and Path(incumbent).is_file():
        shutil.copy2(incumbent, dest)
        return dest
    if dest.exists():
        dest.unlink()
    conn = sqlite3.connect(dest)
    for table, attrs in sorted(needs_attrs.items()):
        def kind(a: str) -> str:
            f = (fields or {}).get(f"{table}.{a}")
            return "REAL" if f is not None and f.value_type in ("int", "float") else "TEXT"

        cols = ", ".join(f"{_q(a)} {kind(a)}" for a in sorted(attrs))
        conn.execute(f"CREATE TABLE {_q(table)} (doc_id TEXT, __entity_id TEXT, {cols})")
        for path in list_documents(spec.table(table)):
            conn.execute(f"INSERT INTO {_q(table)} (doc_id, __entity_id) VALUES (?, ?)", (path.name, f"{table}:{path.stem}"))
    conn.commit()
    conn.close()
    return dest


def materialize_query(
    base: Path,
    dest: Path,
    query_id: str,
    decisions: list[dict[str, Any]],
    values: dict[tuple[str, str], dict[str, dict[str, Any]]],
    fields: dict[str, FieldSpec],
    policy: str = "fill",
) -> dict[str, Any]:
    shutil.copy2(base, dest)
    conn = sqlite3.connect(dest)
    stats = {"filled": 0, "overwritten": 0, "blocked": 0, "missing_rows": 0, "null_provider": 0}
    for row in decisions:
        if row["query_id"] != query_id or row["provider"] == INCUMBENT:
            continue
        table, attr = row["table"], row["attribute"]
        field = fields[f"{table}.{attr}"]
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({_q(table)})")}
        if attr not in cols:
            kind = "REAL" if field.value_type in ("int", "float") else "TEXT"
            conn.execute(f"ALTER TABLE {_q(table)} ADD COLUMN {_q(attr)} {kind}")
        existing = {Path(str(doc)).name if str(doc).endswith(".txt") else f"{Path(str(doc)).name}.txt": (doc, cur)
                    for doc, cur in conn.execute(f"SELECT doc_id, {_q(attr)} FROM {_q(table)}")}
        for doc, fields_read in values.get((table, row["provider"]), {}).items():
            value = commit_value(fields_read.get(attr), field)
            if doc not in existing:
                stats["missing_rows"] += 1
                continue
            doc_id, current = existing[doc]
            if value is None:
                stats["null_provider"] += 1
                continue
            if current is not None and not is_null(current) and policy == "fill":
                stats["blocked"] += 1
                continue
            stats["overwritten" if current is not None and not is_null(current) else "filled"] += 1
            conn.execute(f"UPDATE {_q(table)} SET {_q(attr)} = ? WHERE doc_id = ?", (value, doc_id))
    conn.commit()
    conn.close()
    return stats


def materialize_plan(
    spec: CorpusSpec,
    plan: dict[str, Any],
    values: dict[tuple[str, str], dict[str, dict[str, Any]]],
    fields: dict[str, FieldSpec],
    incumbent: Path | None,
    out_dir: Path,
    policy: str = "fill",
    queries: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-query databases. With ``queries``, the base gets the full physical schema
    (referenced columns and unresolved signature fallback columns) and every rewritten
    query must execute on its database: a SQL error is raised, never scored as empty."""

    from quwarts.core.pipeline import official_sql
    from quwarts.core.schema_columns import complete_physical_schema
    from quwarts.core.signature import audit_workload, enumerate_predicates
    from quwarts.core.signature_realize import live_predicates

    needs_attrs: dict[str, set[str]] = defaultdict(set)
    for row in plan["decisions"]:
        needs_attrs[row["table"]].add(row["attribute"])
    base = base_database(spec, needs_attrs, incumbent, out_dir / "base.db", fields)
    predicates = None
    if queries:
        audit = audit_workload([{"query_id": q, "sql": s} for q, s in queries.items()])
        predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
        conn = sqlite3.connect(base)
        complete_physical_schema(conn, queries, predicates)
        conn.commit()
        conn.close()
    out: dict[str, dict[str, Any]] = {}
    for query_id in sorted({row["query_id"] for row in plan["decisions"]}):
        dest = out_dir / f"{query_id.replace(':', '_')}.db"
        stats = materialize_query(base, dest, query_id, plan["decisions"], values, fields, policy)
        if queries and query_id in queries:
            conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
            try:
                conn.execute(official_sql(queries[query_id], dest, predicates, query_id=query_id)).fetchall()
            finally:
                conn.close()
        out[query_id] = {"db": str(dest), **stats}
    return out
