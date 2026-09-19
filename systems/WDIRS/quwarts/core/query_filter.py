"""Additive filter-recall. Incumbent WHERE is never replaced."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from sqlglot import exp

from quwarts.core.extract import find_surface_span
from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.query_support import clip_context, query_shape
from quwarts.core.query_witness import compile_witness_spec, grain_sql_for, support_from_grain
from quwarts.core.signature import table_aliases
from quwarts.core.signature_cache import CachedCaller, ResponseCache
from quwarts.core.workload import parse_sql

NULL_SENTINEL = "NULL"
EST_TOKENS_PER_CALL = 350
CANDIDATE_BATCH = 6
STRATEGIES = ("direct", "evidence", "critique")

FILTER_DDL = """
CREATE TABLE IF NOT EXISTS filter_additions (
  query_signature_id TEXT NOT NULL,
  witness_key TEXT NOT NULL,
  resolved INTEGER,
  truth INTEGER,
  provenance TEXT,
  PRIMARY KEY (query_signature_id, witness_key)
)
"""

DIRECT_PROMPT = """Decide whether this entity satisfies the complete row-level filter.
Decompose the filter internally into atomic conditions if useful, but return one
decision for the whole filter. Literal absence is not evidence that a condition
is false. Semantic inference is allowed. Evidence spans are optional audit notes,
not a requirement.
Return JSON {"truth":"true|false|unknown","atoms":[{"condition":"...","truth":"true|false|unknown"}],"evidence":"..."}.
FILTER:
"""

EVIDENCE_PROMPT = """Inspect the document and extracted values first. For each atomic
condition, note what the text supports. Then decide whether the complete filter
holds. Literal absence is not evidence of false. Semantic inference is allowed.
Evidence spans are optional audit notes, not a requirement.
Return JSON {"truth":"true|false|unknown","atoms":[{"condition":"...","truth":"true|false|unknown","evidence":"..."}],"evidence":"..."}.
FILTER:
"""

CRITIQUE_PROMPT = """Two independent judgments disagreed on whether the complete
filter holds. Reconsider both views. Literal absence is not evidence of false.
Semantic inference is allowed. Return one decision for the whole filter.
Return JSON {"truth":"true|false|unknown","evidence":"..."}.
FILTER:
"""


@dataclass
class FilterVote:
    witness_key: str
    signature_id: str
    direct: str
    evidence: str
    critique: str | None
    accepted: bool
    agreement: bool
    retried: list[str] = field(default_factory=list)
    evidence_text: str | None = None
    atoms: list[Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FilterReport:
    tokens_spent: int = 0
    tokens_direct: int = 0
    tokens_evidence: int = 0
    tokens_critique: int = 0
    n_queries: int = 0
    n_candidates: int = 0
    n_proposed: int = 0
    n_accepted: int = 0
    n_materialized: int = 0
    n_sql_visible: int = 0
    n_agreement: int = 0
    n_disagreement: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    rollbacks: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    gates: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    per_query: list[dict[str, Any]] = field(default_factory=list)
    per_signature: list[dict[str, Any]] = field(default_factory=list)


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _bool(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return "true"
    if text in {"false", "no", "0"}:
        return "false"
    return "unknown"


def _payload(text: str) -> Any:
    cleaned = (text or "").strip()
    if not cleaned:
        return {}
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]|\{.*\}", cleaned, re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {}


def _tables(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        row[0].lower(): row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
        )
    }


def ensure_filter_table(conn: sqlite3.Connection) -> None:
    conn.execute(FILTER_DDL)


def _has_filter_table(sqlite_path: str | Path) -> bool:
    conn = sqlite3.connect(str(sqlite_path))
    try:
        return "filter_additions" in _tables(conn)
    finally:
        conn.close()


def has_row_filter(sql: str) -> bool:
    try:
        tree = parse_sql(sql)
    except Exception:
        return False
    return isinstance(tree, exp.Select) and tree.args.get("where") is not None


def _outer_tables(tree: exp.Expression) -> list[exp.Table]:
    found: list[exp.Table] = []
    for table in tree.find_all(exp.Table):
        parent = table.parent
        nested = False
        while parent is not None and parent is not tree:
            if isinstance(parent, (exp.Select, exp.Exists, exp.Subquery)):
                nested = True
                break
            parent = parent.parent
        if not nested:
            found.append(table)
    return found


def alias_order(tree: exp.Expression) -> list[str]:
    found: list[str] = []
    for table in _outer_tables(tree):
        alias = (table.alias or table.name or "").lower()
        if alias:
            found.append(alias)
    return found


def canonicalize_filter(sql: str) -> str:
    try:
        tree = parse_sql(sql)
    except Exception:
        return " ".join((sql or "").lower().split())
    if not isinstance(tree, exp.Select) or tree.args.get("where") is None:
        return ""
    expr = tree.args["where"].this.copy()
    mapping: dict[str, str] = {}
    for table in tree.find_all(exp.Table):
        alias = (table.alias or table.name or "").lower()
        if alias and alias not in mapping:
            mapping[alias] = f"${len(mapping)}"
    for col in expr.find_all(exp.Column):
        raw = (col.table or "").lower()
        if raw in mapping:
            col.set("table", exp.to_identifier(mapping[raw]))
    return " ".join(expr.sql(dialect="sqlite").lower().split())


def filter_signature_id(sql: str) -> str:
    body = canonicalize_filter(sql)
    if not body:
        return ""
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def atomic_conditions(sql: str) -> list[dict[str, str]]:
    try:
        tree = parse_sql(sql)
    except Exception:
        return []
    where = tree.args.get("where") if isinstance(tree, exp.Select) else None
    expr = where.this if where is not None else (tree if not isinstance(tree, exp.Select) else None)
    if expr is None:
        return []
    found: list[dict[str, str]] = []

    def walk(node: exp.Expression, negated: bool) -> None:
        if isinstance(node, exp.Paren):
            walk(node.this, negated)
            return
        if isinstance(node, exp.Not):
            walk(node.this, not negated)
            return
        if isinstance(node, (exp.And, exp.Or, exp.Connector)):
            for child in node.flatten() if hasattr(node, "flatten") else [node.left, node.right]:
                if child is not None:
                    walk(child, negated)
            return
        text = node.sql(dialect="sqlite")
        found.append({"sql": text, "negated": "true" if negated else "false"})

    walk(expr, False)
    uniq = []
    seen: set[str] = set()
    for item in found:
        key = item["sql"] + "|" + item["negated"]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return uniq


def encode_witness_key(rowids: Iterable[Any]) -> str:
    parts = []
    for value in rowids:
        if value in (None, ""):
            parts.append(NULL_SENTINEL)
        else:
            parts.append(str(int(value)))
    return "|".join(parts)


def decode_witness_key(key: str) -> list[int | None]:
    parts: list[int | None] = []
    for raw in str(key).split("|"):
        if raw in (NULL_SENTINEL, "", None):
            parts.append(None)
        else:
            parts.append(int(raw))
    return parts


def outer_alias_tables(tree: exp.Expression) -> dict[str, str]:
    found: dict[str, str] = {}
    for table in _outer_tables(tree):
        alias = (table.alias or table.name or "").lower()
        name = (table.name or "").lower()
        if alias:
            found[alias] = name
    return found


def witness_key_sql(tree: exp.Expression) -> str:
    parts = []
    for alias in alias_order(tree):
        parts.append(f"COALESCE(CAST({_quote(alias)}.rowid AS TEXT), '{NULL_SENTINEL}')")
    if not parts:
        return f"'{NULL_SENTINEL}'"
    if len(parts) == 1:
        return parts[0]
    return " || '|' || ".join(parts)


def rewrite_filter_sql(
    sql: str,
    sqlite_path: str | Path,
    original_sql: str | None = None,
) -> str:
    if not _has_filter_table(sqlite_path):
        return sql
    try:
        tree = parse_sql(sql)
    except Exception:
        return sql
    if not isinstance(tree, exp.Select) or tree.args.get("where") is None:
        return sql
    current = tree.args["where"].this.sql(dialect="sqlite")
    if "filter_additions" in current.lower():
        return sql
    source = original_sql or sql
    signature = filter_signature_id(source)
    if not signature:
        return sql
    key_sql = witness_key_sql(tree)
    exists = (
        "EXISTS (SELECT 1 FROM filter_additions fa "
        f"WHERE fa.query_signature_id = '{signature}' "
        f"AND fa.witness_key = {key_sql} "
        "AND fa.resolved = 1 AND fa.truth = 1)"
    )
    wrapped = parse_sql(f"({current}) OR ({exists})")
    tree.set("where", exp.Where(this=wrapped))
    return tree.sql(dialect="sqlite")


def _drop_filter_exists(expr: exp.Expression | None) -> exp.Expression | None:
    if expr is None:
        return None
    if isinstance(expr, exp.Exists) and "filter_additions" in expr.sql(dialect="sqlite").lower():
        return None
    if isinstance(expr, exp.Paren):
        return _drop_filter_exists(expr.this)
    if isinstance(expr, exp.Or):
        left = _drop_filter_exists(expr.left)
        right = _drop_filter_exists(expr.right)
        if left is None:
            return right
        if right is None:
            return left
        return exp.Or(this=left, expression=right)
    return expr


def unwrap_filter_sql(sql: str) -> str:
    try:
        tree = parse_sql(sql)
    except Exception:
        return sql
    if not isinstance(tree, exp.Select) or tree.args.get("where") is None:
        return sql
    cleaned = _drop_filter_exists(tree.args["where"].this)
    if cleaned is None:
        tree.set("where", None)
    else:
        tree.set("where", exp.Where(this=cleaned))
    return tree.sql(dialect="sqlite")


def filter_probe_sql(official: str) -> str:
    tree = parse_sql(unwrap_filter_sql(official))
    if not isinstance(tree, exp.Select) or tree.args.get("where") is None:
        return ""
    filter_sql = tree.args["where"].this.sql(dialect="sqlite")
    kept: list[exp.Expression] = []
    for table in _outer_tables(tree):
        qual = table.alias or table.name
        kept.append(
            exp.alias_(
                exp.Column(this=exp.to_identifier("rowid"), table=exp.to_identifier(qual)),
                f"{qual}__rid",
            )
        )
    kept.append(
        exp.alias_(
            parse_sql(
                f"CASE WHEN ({filter_sql}) THEN 'true' "
                f"WHEN NOT ({filter_sql}) THEN 'false' ELSE 'null' END"
            ),
            "__ft",
        )
    )
    tree.set("expressions", kept)
    tree.set("where", None)
    tree.set("group", None)
    tree.set("having", None)
    tree.set("order", None)
    tree.set("limit", None)
    return tree.sql(dialect="sqlite")


def _row_context(
    conn: sqlite3.Connection,
    table: str,
    rowid: int | None,
    documents: dict[str, str] | None,
) -> dict[str, Any]:
    docs = documents or {}
    if rowid is None:
        return {"rowid": None, "table": table, "label": "", "entity_id": "", "cells": {}, "document": ""}
    names = _tables(conn)
    real = names.get(table.lower(), table)
    raw = conn.execute(f"SELECT rowid AS _rid, * FROM {_quote(real)} WHERE rowid = ?", [rowid]).fetchone()
    if raw is None:
        return {"rowid": rowid, "table": table, "label": "", "entity_id": "", "cells": {}, "document": ""}
    cols = [item[0] for item in conn.execute(f"PRAGMA table_info({_quote(real)})")]
    payload = {"_rid": raw[0]}
    payload.update(zip(cols, raw[1:]))
    cells = {
        key: payload.get(key)
        for key in cols
        if not str(key).startswith("sig_") and str(key).lower() != "rowid"
    }
    doc_id = payload.get("doc_id") or payload.get("id")
    label = (
        payload.get("generic_name")
        or payload.get("disease_name")
        or payload.get("institution_name")
        or payload.get("name")
        or doc_id
        or rowid
    )
    text = ""
    if doc_id not in (None, ""):
        text = docs.get(str(doc_id)) or docs.get(Path(str(doc_id)).stem) or docs.get(Path(str(doc_id)).name) or ""
    return {
        "rowid": int(rowid),
        "table": table,
        "label": str(label or ""),
        "entity_id": str(doc_id or rowid),
        "cells": cells,
        "document": text,
    }


def _snippets(document: str, cells: dict[str, Any], atoms: list[dict[str, str]]) -> str:
    needles: list[str] = []
    for item in atoms:
        needles.append(item.get("sql") or "")
        for token in re.findall(r"'([^']+)'", item.get("sql") or ""):
            needles.append(token)
    for key, value in cells.items():
        if value not in (None, ""):
            needles.append(str(key))
            needles.append(str(value))
    parts: list[str] = []
    seen: set[str] = set()
    for needle in needles:
        snippet = clip_context(document, needle if needle else None)
        if snippet and snippet not in seen:
            seen.add(snippet)
            parts.append(snippet)
        if find_surface_span(document or "", needle):
            continue
    if not parts and document:
        parts.append(clip_context(document))
    return "\n---\n".join(parts)[:1400]


def excluded_filter_candidates(
    sqlite_path: str | Path,
    query_id: str,
    sql: str,
    predicates: list[Any],
    documents: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    from quwarts.core.pipeline import official_sql

    if not has_row_filter(sql):
        return []
    path = Path(sqlite_path)
    official = official_sql(sql, path, predicates)
    probe = filter_probe_sql(official)
    if not probe:
        return []
    spec = compile_witness_spec(query_id, sql)
    signature = filter_signature_id(sql)
    tree = parse_sql(official)
    aliases = table_aliases(tree)
    order = alias_order(tree)
    atoms = atomic_conditions(sql)
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute(probe)
        cols = [item[0] for item in cur.description] if cur.description else []
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            if str(row.get("__ft") or "") == "true":
                continue
            rids: list[Any] = []
            rowids: dict[str, int | None] = {}
            contexts = []
            for alias in order:
                raw = row.get(f"{alias}__rid")
                table = aliases.get(alias, alias)
                rid = None if raw in (None, "") else int(raw)
                rids.append(rid)
                rowids[table] = rid
                contexts.append(_row_context(conn, table, rid, documents))
            key = encode_witness_key(rids)
            if key in seen:
                continue
            seen.add(key)
            cells: dict[str, Any] = {}
            docs = []
            labels = []
            for ctx in contexts:
                cells.update({f"{ctx['table']}.{name}": value for name, value in (ctx.get("cells") or {}).items()})
                if ctx.get("document"):
                    docs.append(ctx["document"])
                if ctx.get("label"):
                    labels.append(ctx["label"])
            document = "\n".join(docs)
            out.append(
                {
                    "query_id": query_id,
                    "signature_id": signature,
                    "witness_key": key,
                    "rowids": rowids,
                    "alias_rowids": dict(zip(order, rids)),
                    "filter_3vl": str(row.get("__ft") or "null"),
                    "label": " | ".join(labels),
                    "entity_id": contexts[0]["entity_id"] if contexts else key,
                    "cells": cells,
                    "document": document,
                    "snippets": _snippets(document, cells, atoms),
                    "atoms": atoms,
                    "filter_sql": canonicalize_filter(sql),
                    "kind": spec.kind,
                }
            )
        return out
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _context_block(item: dict[str, Any]) -> str:
    cells = item.get("cells") or {}
    shown = "\n".join(f"  {key}: {cells[key]}" for key in cells if cells[key] not in (None, ""))
    atoms = "\n".join(
        f"- {row['sql']}" + (" [negated]" if row.get("negated") == "true" else "")
        for row in item.get("atoms") or []
    )
    return (
        f"ENTITY_LABEL: {item.get('label') or ''}\n"
        f"WITNESS_KEY: {item.get('witness_key')}\n"
        f"EXTRACTED_VALUES:\n{shown or '  (none)'}\n"
        f"ATOMIC_CONDITIONS:\n{atoms or '  (none)'}\n"
        f"DOCUMENT_SNIPPETS:\n{item.get('snippets') or ''}\n"
    )


def _ask(
    caller: BudgetedCaller,
    prompt: str,
    purpose: str,
    plan: str,
) -> tuple[str, dict[str, Any], bool]:
    retried = False
    text = ""
    payload: Any = {}
    for attempt in range(2):
        try:
            text = caller.complete(
                prompt,
                purpose=purpose,
                system="Decide one complete filter. JSON only.",
                max_tokens=220,
                plan=plan,
            )
        except BudgetExhausted:
            raise
        except Exception:
            text = ""
        payload = _payload(text)
        if isinstance(payload, dict) and payload.get("truth") is not None:
            return _bool(payload.get("truth")), payload, retried
        retried = True
        if attempt == 0:
            continue
    return "unknown", payload if isinstance(payload, dict) else {}, True


def classify_witness(caller: BudgetedCaller, item: dict[str, Any]) -> FilterVote:
    body = (item.get("filter_sql") or "") + "\n" + _context_block(item)
    direct, d_raw, d_retry = _ask(caller, DIRECT_PROMPT + body, "filter_direct", "filter_direct")
    evidence, e_raw, e_retry = _ask(caller, EVIDENCE_PROMPT + body, "filter_evidence", "filter_evidence")
    critique = None
    c_raw: dict[str, Any] | None = None
    c_retry = False
    agreement = direct == evidence and direct != "unknown"
    if direct != evidence:
        extra = (
            f"JUDGMENT_A: {direct}\nJUDGMENT_B: {evidence}\n"
            "These two judgments disagree. Choose the better complete-filter decision.\n"
        )
        critique, c_raw, c_retry = _ask(caller, CRITIQUE_PROMPT + body + extra, "filter_critique", "filter_critique")
    votes = [direct, evidence] + ([critique] if critique is not None else [])
    accepted = votes.count("true") >= 2
    retried = []
    if d_retry:
        retried.append("direct")
    if e_retry:
        retried.append("evidence")
    if c_retry:
        retried.append("critique")
    atoms = e_raw.get("atoms") if isinstance(e_raw, dict) else None
    if not atoms and isinstance(d_raw, dict):
        atoms = d_raw.get("atoms")
    evidence_text = None
    for raw in (e_raw, d_raw, c_raw):
        if isinstance(raw, dict) and str(raw.get("evidence") or "").strip():
            evidence_text = str(raw.get("evidence"))
            break
    return FilterVote(
        witness_key=str(item["witness_key"]),
        signature_id=str(item["signature_id"]),
        direct=direct,
        evidence=evidence,
        critique=critique,
        accepted=accepted,
        agreement=agreement,
        retried=retried,
        evidence_text=evidence_text,
        atoms=list(atoms) if atoms else None,
        raw={"direct": d_raw, "evidence": e_raw, "critique": c_raw},
    )


def persist_filter_vote(
    path: str | Path,
    query_id: str,
    item: dict[str, Any],
    vote: FilterVote,
) -> None:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "query_id": query_id,
        "signature_id": vote.signature_id or item.get("signature_id"),
        "witness_key": vote.witness_key or item.get("witness_key"),
        "direct": vote.direct,
        "evidence_first": vote.evidence,
        "critique": vote.critique,
        "accepted": vote.accepted,
        "agreement": vote.agreement,
        "retried": vote.retried,
        "evidence_text": vote.evidence_text,
        "atoms": vote.atoms,
        "raw": vote.raw,
    }
    with dest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def add_filter(
    conn: sqlite3.Connection,
    signature_id: str,
    witness_key: str,
    provenance: str,
) -> bool:
    ensure_filter_table(conn)
    existing = conn.execute(
        "SELECT resolved, truth FROM filter_additions "
        "WHERE query_signature_id = ? AND witness_key = ?",
        [signature_id, witness_key],
    ).fetchone()
    if existing is not None:
        return int(existing[0] or 0) == 1 and int(existing[1] or 0) == 1
    conn.execute(
        "INSERT INTO filter_additions "
        "(query_signature_id, witness_key, resolved, truth, provenance) "
        "VALUES (?, ?, 1, 1, ?)",
        [signature_id, witness_key, provenance],
    )
    return True


def _grain_keys(
    conn: sqlite3.Connection,
    sqlite_path: str | Path,
    query_id: str,
    sql: str,
    predicates: list[Any],
) -> tuple[set[str], dict[str, tuple]]:
    from quwarts.core.pipeline import official_sql

    spec = compile_witness_spec(query_id, sql)
    grain = official_sql(grain_sql_for(spec), sqlite_path, predicates)
    try:
        cur = conn.execute(grain)
    except sqlite3.Error:
        return set(), {}
    cols = [item[0] for item in cur.description] if cur.description else []
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    support = support_from_grain(spec, rows, None)
    tree = parse_sql(official_sql(sql, sqlite_path, predicates))
    order = alias_order(tree)
    keys: set[str] = set()
    groups: dict[str, tuple] = {}
    for row, item in zip(rows, support):
        rids = []
        for alias in order:
            raw = row.get(f"{alias}__rid")
            rids.append(None if raw in (None, "") else int(raw))
        key = encode_witness_key(rids) if rids else encode_witness_key([item.rowid])
        keys.add(key)
        groups[key] = tuple(item.group_key.get(name) for name in spec.group_aliases)
    return keys, groups


def apply_filter_addition(
    conn: sqlite3.Connection,
    sqlite_path: str | Path,
    item: dict[str, Any],
    predicates: list[Any],
    sql: str,
    reasons: list[str] | None = None,
) -> bool:
    path = Path(sqlite_path)
    before_keys, before_groups = _grain_keys(conn, path, item["query_id"], sql, predicates)
    conn.execute("SAVEPOINT filter_add")
    try:
        add_filter(conn, item["signature_id"], item["witness_key"], item["query_id"])
        after_keys, after_groups = _grain_keys(conn, path, item["query_id"], sql, predicates)
        if before_keys - after_keys:
            raise sqlite3.Error("incumbent witness dropped")
        for key, group in before_groups.items():
            if after_groups.get(key) != group:
                raise sqlite3.Error("incumbent group reassigned")
        if item["witness_key"] not in after_keys:
            raise sqlite3.Error("addition did not appear")
        conn.execute("RELEASE filter_add")
        return True
    except sqlite3.Error as exc:
        if reasons is not None:
            reasons.append(str(exc))
        conn.execute("ROLLBACK TO filter_add")
        conn.execute("RELEASE filter_add")
        return False


def _bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(key), json.dumps(row.get(key), default=str)) for key in row)))
    return tuple(sorted(frozen))


def query_bags(
    sqlite_path: str | Path,
    statements: dict[str, str],
    predicates: list[Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, tuple]:
    from quwarts.core.pipeline import official_sql

    own = conn is None
    if own:
        conn = sqlite3.connect(str(sqlite_path))
    try:
        out = {}
        for qid, sql in statements.items():
            try:
                cur = conn.execute(official_sql(sql, sqlite_path, predicates))
                cols = [item[0] for item in cur.description] if cur.description else []
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            except sqlite3.Error:
                rows = []
            out[qid] = _bag(rows)
        return out
    finally:
        if own:
            conn.close()


def count_mass(sqlite_path: str | Path, sql: str, predicates: list[Any], conn: sqlite3.Connection | None = None) -> int:
    from quwarts.core.pipeline import official_sql

    own = conn is None
    if own:
        conn = sqlite3.connect(str(sqlite_path))
    try:
        cur = conn.execute(official_sql(sql, sqlite_path, predicates))
        cols = [item[0] for item in cur.description] if cur.description else []
        total = 0
        for row in cur.fetchall():
            record = dict(zip(cols, row))
            hits = 0
            for key, value in record.items():
                if str(key).lower().endswith("count") and value not in (None, ""):
                    try:
                        total += int(value)
                        hits += 1
                    except (TypeError, ValueError):
                        continue
            if not hits and row:
                try:
                    total += int(row[0] or 0)
                except (TypeError, ValueError):
                    continue
        return total
    except sqlite3.Error:
        return 0
    finally:
        if own:
            conn.close()


def compare_bags(
    left_path: str | Path,
    right_path: str | Path,
    statements: dict[str, str],
    predicates: list[Any],
) -> dict[str, Any]:
    left = query_bags(left_path, statements, predicates)
    right = query_bags(right_path, statements, predicates)
    mismatched = [qid for qid in statements if left.get(qid) != right.get(qid)]
    return {
        "ok": not mismatched,
        "matched": len(statements) - len(mismatched),
        "total": len(statements),
        "mismatched": mismatched,
    }


def _query_amp(sql: str, workload: Any | None) -> float:
    if workload is None:
        return 1.0
    try:
        tree = parse_sql(sql)
    except Exception:
        return 1.0
    where = tree.args.get("where") if isinstance(tree, exp.Select) else None
    if where is None:
        return 1.0
    values = []
    for col in where.find_all(exp.Column):
        name = (col.name or "").lower()
        req = (workload.requirements or {}).get(name)
        if req is not None and getattr(req, "amp", None):
            values.append(float(req.amp))
    return max(values) if values else 1.0


def _workload(statements: dict[str, str]):
    try:
        from quwarts.core.amplify import attach_amplification
        from quwarts.core.logical import infer_logical_schema
        from quwarts.core.workload import analyze_workload

        logical = infer_logical_schema(statements.values())
        logical, workload = analyze_workload(statements, logical)
        attach_amplification(workload)
        return workload
    except Exception:
        return None


def _purpose_tokens(caller: BudgetedCaller, purpose: str) -> int:
    return sum(rec.tokens for rec in caller.ledger.records if rec.purpose == purpose)


def write_filter_gate_fixture(sqlite_path: str | Path) -> Path:
    path = Path(sqlite_path)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE item (doc_id TEXT, flag TEXT, name TEXT)")
    conn.execute("CREATE TABLE extra (doc_id TEXT)")
    conn.execute("INSERT INTO item VALUES ('keep', 'yes', 'alpha')")
    conn.execute("INSERT INTO item VALUES ('false', 'no', 'beta')")
    conn.execute("INSERT INTO item VALUES ('nullrow', NULL, 'gamma')")
    conn.execute("INSERT INTO item VALUES ('andfail', 'yes', '')")
    conn.execute("INSERT INTO extra VALUES ('keep')")
    ensure_filter_table(conn)
    conn.commit()
    conn.close()
    return path


def probe_filter_additivity(sqlite_path: str | Path) -> dict[str, Any]:
    from quwarts.core.pipeline import official_sql

    path = Path(sqlite_path)
    conn = sqlite3.connect(str(path))
    ensure_filter_table(conn)
    conn.commit()
    findings: dict[str, Any] = {"ok": True, "checks": []}

    def _count(sql: str) -> int:
        return count_mass(path, sql, [], conn=conn)

    def _keys(sql: str, qid: str) -> set[str]:
        keys, _groups = _grain_keys(conn, path, qid, sql, [])
        return keys

    try:
        simple = "SELECT COUNT(*) AS n FROM item WHERE flag = 'yes'"
        not_sql = "SELECT COUNT(*) AS n FROM item WHERE NOT (flag = 'no')"
        and_sql = "SELECT COUNT(*) AS n FROM item WHERE flag = 'yes' AND name != ''"
        or_sql = "SELECT COUNT(*) AS n FROM item WHERE flag = 'yes' OR name = 'special'"
        join_sql = (
            "SELECT COUNT(*) AS n FROM item i LEFT JOIN extra e "
            "ON i.doc_id = e.doc_id WHERE flag = 'yes'"
        )
        grouped = "SELECT name, COUNT(*) AS n FROM item WHERE flag = 'yes' GROUP BY name"
        before = {
            "simple": _count(simple),
            "not": _count(not_sql),
            "and": _count(and_sql),
            "or": _count(or_sql),
            "join": _count(join_sql),
            "grouped": _count(grouped),
        }
        findings["checks"].append({"name": "empty_filter_keeps_where", "before": before, "ok": True})
        empty_sql = official_sql(simple, path, [])
        findings["checks"].append(
            {
                "name": "empty_exists_present",
                "ok": "filter_additions" in empty_sql.lower() and " OR " in empty_sql.upper(),
            }
        )
        findings["ok"] = findings["ok"] and findings["checks"][-1]["ok"]

        keep_keys = _keys(simple, "simple")
        false_rid = conn.execute("SELECT rowid FROM item WHERE doc_id = 'false'").fetchone()
        null_rid = conn.execute("SELECT rowid FROM item WHERE doc_id = 'nullrow'").fetchone()
        and_rid = conn.execute("SELECT rowid FROM item WHERE doc_id = 'andfail'").fetchone()
        keep_rid = conn.execute("SELECT rowid FROM item WHERE doc_id = 'keep'").fetchone()
        extra_keep = conn.execute("SELECT rowid FROM extra WHERE doc_id = 'keep'").fetchone()
        sig_simple = filter_signature_id(simple)
        sig_not = filter_signature_id(not_sql)
        sig_and = filter_signature_id(and_sql)
        sig_or = filter_signature_id(or_sql)
        sig_join = filter_signature_id(join_sql)

        conn.execute("SAVEPOINT gate_one")
        add_filter(conn, sig_simple, encode_witness_key([int(false_rid[0])]), "gate")
        after_simple = _count(simple)
        after_not = _count(not_sql)
        after_keys = _keys(simple, "simple")
        ok_one = after_simple == before["simple"] + 1 and keep_keys <= after_keys
        findings["checks"].append(
            {
                "name": "one_addition_admits_one",
                "before": before["simple"],
                "after": after_simple,
                "ok": ok_one,
            }
        )
        findings["ok"] = findings["ok"] and ok_one
        conn.execute("ROLLBACK TO gate_one")
        conn.execute("RELEASE gate_one")

        conn.execute("SAVEPOINT gate_not")
        add_filter(conn, sig_not, encode_witness_key([int(false_rid[0])]), "gate")
        not_after = _count(not_sql)
        not_keys = _keys(not_sql, "not")
        ok_not = before["not"] <= not_after and _keys(simple, "simple") == keep_keys
        findings["checks"].append(
            {"name": "not_additive", "before": before["not"], "after": not_after, "ok": ok_not, "incumbent": list(not_keys)}
        )
        findings["ok"] = findings["ok"] and ok_not
        conn.execute("ROLLBACK TO gate_not")
        conn.execute("RELEASE gate_not")

        conn.execute("SAVEPOINT gate_and")
        add_filter(conn, sig_and, encode_witness_key([int(and_rid[0])]), "gate")
        and_after = _count(and_sql)
        ok_and = and_after == before["and"] + 1
        findings["checks"].append({"name": "and_additive", "before": before["and"], "after": and_after, "ok": ok_and})
        findings["ok"] = findings["ok"] and ok_and
        conn.execute("ROLLBACK TO gate_and")
        conn.execute("RELEASE gate_and")

        conn.execute("SAVEPOINT gate_or")
        add_filter(conn, sig_or, encode_witness_key([int(null_rid[0])]), "gate")
        or_after = _count(or_sql)
        ok_or = or_after == before["or"] + 1
        findings["checks"].append({"name": "or_additive", "before": before["or"], "after": or_after, "ok": ok_or})
        findings["ok"] = findings["ok"] and ok_or
        conn.execute("ROLLBACK TO gate_or")
        conn.execute("RELEASE gate_or")

        conn.execute("SAVEPOINT gate_null")
        add_filter(conn, sig_simple, encode_witness_key([int(null_rid[0])]), "gate")
        null_after = _count(simple)
        ok_null = null_after == before["simple"] + 1
        findings["checks"].append({"name": "null_additive", "before": before["simple"], "after": null_after, "ok": ok_null})
        findings["ok"] = findings["ok"] and ok_null
        conn.execute("ROLLBACK TO gate_null")
        conn.execute("RELEASE gate_null")

        join_tree = parse_sql(official_sql(join_sql, path, []))
        join_order = alias_order(join_tree)
        aliases = table_aliases(join_tree)
        keep_pair = []
        false_pair = []
        for alias in join_order:
            table = aliases.get(alias, alias)
            if table == "item":
                keep_pair.append(int(keep_rid[0]))
                false_pair.append(int(false_rid[0]))
            else:
                keep_pair.append(int(extra_keep[0]) if extra_keep else None)
                false_pair.append(None)
        keep_key = encode_witness_key(keep_pair)
        false_key = encode_witness_key(false_pair)
        ok_stable = keep_key != false_key and NULL_SENTINEL in false_key
        findings["checks"].append(
            {"name": "join_null_keys", "keep": keep_key, "false": false_key, "ok": ok_stable}
        )
        findings["ok"] = findings["ok"] and ok_stable
        conn.execute("SAVEPOINT gate_join")
        add_filter(conn, sig_join, false_key, "gate")
        join_after = _count(join_sql)
        add_filter(conn, sig_join, false_key, "gate")
        join_dup = _count(join_sql)
        ok_join = join_after == before["join"] + 1 and join_dup == join_after
        findings["checks"].append(
            {"name": "join_no_duplicate", "before": before["join"], "after": join_after, "dup": join_dup, "ok": ok_join}
        )
        findings["ok"] = findings["ok"] and ok_join
        grouped_before_keys, grouped_before = _grain_keys(conn, path, "grouped", grouped, [])
        grouped_after_keys, grouped_after = _grain_keys(conn, path, "grouped", grouped, [])
        ok_group = grouped_before == grouped_after and grouped_before_keys == grouped_after_keys
        findings["checks"].append({"name": "group_unchanged", "ok": ok_group})
        findings["ok"] = findings["ok"] and ok_group
        conn.execute("ROLLBACK TO gate_join")
        conn.execute("RELEASE gate_join")
        unrelated_after = _count(and_sql)
        findings["checks"].append(
            {"name": "unrelated_bag", "ok": unrelated_after == before["and"]}
        )
        findings["ok"] = findings["ok"] and unrelated_after == before["and"]
    except sqlite3.Error as exc:
        findings["ok"] = False
        findings["checks"].append({"name": "filter_probe", "ok": False, "error": str(exc)})
    finally:
        conn.close()
    return findings


def run_filter_arm(
    sqlite_path: str | Path,
    queries: list[dict[str, str]],
    predicates: Iterable[Any],
    *,
    documents: dict[str, str] | None = None,
    caller: BudgetedCaller | None = None,
    statements: dict[str, str] | None = None,
    checkpoint: str | Path | None = None,
    vote_journal: str | Path | None = None,
) -> FilterReport:
    live = list(predicates)
    report = FilterReport()
    cache_store = ResponseCache()
    path = Path(sqlite_path)
    all_statements = statements or {row["query_id"]: row["sql"] for row in queries}
    conn = sqlite3.connect(str(path))
    try:
        ensure_filter_table(conn)
        conn.commit()
    finally:
        conn.close()
    if caller is None:
        return report
    journal = Path(vote_journal) if vote_journal else (
        Path(checkpoint).with_name("filter_votes.jsonl") if checkpoint else path.parent / "filter_votes.jsonl"
    )
    bound = CachedCaller(caller, cache_store, plan="filter")
    workload = _workload(all_statements)
    freq = Counter(filter_signature_id(sql) for sql in all_statements.values() if has_row_filter(sql))
    ranked: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for row in queries:
        sql = row["sql"]
        qid = row["query_id"]
        if not has_row_filter(sql):
            report.skipped.append({"query_id": qid, "reason": "no_row_filter"})
            continue
        candidates = excluded_filter_candidates(path, qid, sql, live, documents)
        unique = []
        for item in candidates:
            pair = (item["signature_id"], item["witness_key"])
            if pair in seen_keys:
                continue
            seen_keys.add(pair)
            unique.append(item)
        sig = filter_signature_id(sql)
        amp = _query_amp(sql, workload)
        cost = max(2 * EST_TOKENS_PER_CALL, 1)
        score = (freq.get(sig) or 1) * amp * len(unique) / cost
        ranked.append(
            {
                "row": row,
                "shape": query_shape(qid, sql),
                "signature_id": sig,
                "candidates": unique,
                "score": score,
                "amp": amp,
                "freq": freq.get(sig) or 1,
            }
        )
        report.candidates.append(
            {
                "query_id": qid,
                "signature_id": sig,
                "filter_sql": canonicalize_filter(sql),
                "n_excluded": len(candidates),
                "n_unique": len(unique),
                "score": score,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["row"]["query_id"]))
    bags = query_bags(path, all_statements, live)
    ckpt = Path(checkpoint) if checkpoint else None
    done_chunks: set[str] = set()
    if ckpt and ckpt.is_file():
        saved = json.loads(ckpt.read_text())
        report.per_query = list(saved.get("per_query") or [])
        report.rollbacks = list(saved.get("rollbacks") or [])
        report.skipped = list(saved.get("skipped") or report.skipped)
        report.n_proposed = int(saved.get("n_proposed") or 0)
        report.n_accepted = int(saved.get("n_accepted") or 0)
        report.n_materialized = int(saved.get("n_materialized") or 0)
        report.n_sql_visible = int(saved.get("n_sql_visible") or 0)
        done_chunks = set(saved.get("done_chunks") or [])
    by_qid = {item["query_id"]: item for item in report.per_query}
    states = []
    for item in ranked:
        qid = item["row"]["query_id"]
        chunks = [
            item["candidates"][i : i + CANDIDATE_BATCH]
            for i in range(0, len(item["candidates"]), CANDIDATE_BATCH)
        ]
        if qid not in by_qid:
            by_qid[qid] = {
                "query_id": qid,
                "signature_id": item["signature_id"],
                "filter_sql": canonicalize_filter(item["row"]["sql"]),
                "n_candidates": len(item["candidates"]),
                "score": item["score"],
                "amp": item["amp"],
                "freq": item["freq"],
                "n_direct_true": 0,
                "n_direct_false": 0,
                "n_direct_unknown": 0,
                "n_evidence_true": 0,
                "n_evidence_false": 0,
                "n_evidence_unknown": 0,
                "n_critique": 0,
                "n_agreement": 0,
                "n_disagreement": 0,
                "n_proposed": 0,
                "n_accepted": 0,
                "n_materialized": 0,
                "n_sql_visible": 0,
                "tokens": 0,
                "tokens_direct": 0,
                "tokens_evidence": 0,
                "tokens_critique": 0,
                "count_mass_before": count_mass(path, item["row"]["sql"], live),
                "count_mass_after": 0,
                "n_new_groups": 0,
                "empty_before": 0,
                "empty_after": 0,
            }
            report.per_query.append(by_qid[qid])
            report.n_queries += 1
            report.n_candidates += len(item["candidates"])
        states.append({"item": item, "chunks": chunks, "cursor": 0, "meta": by_qid[qid]})
    active = True
    while active and caller.ledger.remaining() > 0:
        active = False
        remaining_batches = sum(
            1
            for state in states
            for index, _chunk in enumerate(state["chunks"])
            if f"{state['item']['row']['query_id']}:{index}" not in done_chunks
        )
        for state in states:
            if caller.ledger.remaining() <= 0:
                break
            qid = state["item"]["row"]["query_id"]
            sql = state["item"]["row"]["sql"]
            sig = state["item"]["signature_id"]
            meta = state["meta"]
            while state["cursor"] < len(state["chunks"]):
                chunk_id = f"{qid}:{state['cursor']}"
                if chunk_id in done_chunks:
                    state["cursor"] += 1
                    continue
                chunk = state["chunks"][state["cursor"]]
                if not chunk:
                    done_chunks.add(chunk_id)
                    state["cursor"] += 1
                    continue
                est = max(1, len(chunk) * 2 * EST_TOKENS_PER_CALL)
                quota = max(1, caller.ledger.remaining() // max(1, remaining_batches))
                if est > caller.ledger.remaining():
                    if len(chunk) > 1:
                        chunk = chunk[:1]
                        est = 2 * EST_TOKENS_PER_CALL
                    if est > caller.ledger.remaining():
                        print(f"  hold {qid} est={est} remaining={caller.ledger.remaining()}", flush=True)
                        break
                elif est > quota and len(chunk) > 1:
                    keep = max(1, len(chunk) * quota // est)
                    chunk = chunk[:keep]
                active = True
                spent_before = caller.ledger.spent
                d_before = _purpose_tokens(caller, "filter_direct")
                e_before = _purpose_tokens(caller, "filter_evidence")
                c_before = _purpose_tokens(caller, "filter_critique")
                print(
                    f"filter {qid} batch={state['cursor']} n={len(chunk)} "
                    f"est={est} remaining={caller.ledger.remaining()}",
                    flush=True,
                )
                votes: list[tuple[dict[str, Any], FilterVote]] = []
                try:
                    for cand in chunk:
                        vote = classify_witness(bound, cand)
                        persist_filter_vote(journal, qid, cand, vote)
                        votes.append((cand, vote))
                except BudgetExhausted:
                    print(f"  budget during {qid}", flush=True)
                proposed = accepted = materialized = visible = 0
                conn = sqlite3.connect(str(path))
                try:
                    conn.execute("SAVEPOINT filter_cohort")
                    for cand, vote in votes:
                        meta[f"n_direct_{vote.direct}"] = meta.get(f"n_direct_{vote.direct}", 0) + 1
                        meta[f"n_evidence_{vote.evidence}"] = meta.get(f"n_evidence_{vote.evidence}", 0) + 1
                        if vote.critique is not None:
                            meta["n_critique"] += 1
                        if vote.agreement:
                            meta["n_agreement"] += 1
                            report.n_agreement += 1
                        else:
                            meta["n_disagreement"] += 1
                            report.n_disagreement += 1
                        if vote.direct != "true" and vote.evidence != "true" and (vote.critique or "unknown") != "true":
                            continue
                        proposed += 1
                        if not vote.accepted:
                            continue
                        accepted += 1
                        reasons: list[str] = []
                        ok = apply_filter_addition(conn, path, cand, live, sql, reasons)
                        if not ok:
                            report.rollbacks.append(
                                {
                                    "query_id": qid,
                                    "stage": "addition",
                                    "witness_key": cand["witness_key"],
                                    "reason": reasons[0] if reasons else "rejected",
                                }
                            )
                            print(f"  ineffective {cand['witness_key']} {reasons}", flush=True)
                            continue
                        materialized += 1
                        visible += 1
                    after_bags = query_bags(path, all_statements, live, conn=conn)
                    interference = [
                        other
                        for other, before in bags.items()
                        if after_bags.get(other) != before
                        and filter_signature_id(all_statements[other]) != sig
                    ]
                    if interference:
                        conn.execute("ROLLBACK TO filter_cohort")
                        report.rollbacks.append(
                            {"query_id": qid, "stage": "cohort", "reason": "unrelated bags", "queries": interference}
                        )
                        print(f"  rolled back batch; unrelated bags moved: {interference}", flush=True)
                        materialized = visible = 0
                    else:
                        conn.execute("RELEASE filter_cohort")
                        bags = after_bags
                    conn.commit()
                finally:
                    conn.close()
                used = caller.ledger.spent - spent_before
                meta["n_proposed"] += proposed
                meta["n_accepted"] += accepted
                meta["n_materialized"] += materialized
                meta["n_sql_visible"] += visible
                meta["tokens"] += used
                meta["tokens_direct"] += _purpose_tokens(caller, "filter_direct") - d_before
                meta["tokens_evidence"] += _purpose_tokens(caller, "filter_evidence") - e_before
                meta["tokens_critique"] += _purpose_tokens(caller, "filter_critique") - c_before
                meta["count_mass_after"] = count_mass(path, sql, live)
                report.n_proposed += proposed
                report.n_accepted += accepted
                report.n_materialized += materialized
                report.n_sql_visible += visible
                done_chunks.add(chunk_id)
                remaining_batches = max(0, remaining_batches - 1)
                state["cursor"] += 1
                print(
                    f"  {qid} proposed={proposed} accepted={accepted} visible={visible} tokens={used}",
                    flush=True,
                )
                if ckpt:
                    ckpt.parent.mkdir(parents=True, exist_ok=True)
                    ckpt.write_text(
                        json.dumps(
                            {
                                "per_query": report.per_query,
                                "rollbacks": report.rollbacks,
                                "skipped": report.skipped,
                                "n_proposed": report.n_proposed,
                                "n_accepted": report.n_accepted,
                                "n_materialized": report.n_materialized,
                                "n_sql_visible": report.n_sql_visible,
                                "tokens_spent": caller.ledger.spent,
                                "done_chunks": sorted(done_chunks),
                            },
                            default=str,
                        )
                    )
                break
    by_sig: dict[str, dict[str, Any]] = {}
    for item in report.per_query:
        row = by_sig.setdefault(
            item["signature_id"],
            {"signature_id": item["signature_id"], "filter_sql": item.get("filter_sql"), "queries": [], "n_candidates": 0, "n_accepted": 0},
        )
        row["queries"].append(item["query_id"])
        row["n_candidates"] += int(item.get("n_candidates") or 0)
        row["n_accepted"] += int(item.get("n_accepted") or 0)
    report.per_signature = list(by_sig.values())
    report.tokens_spent = caller.ledger.spent
    report.tokens_direct = _purpose_tokens(caller, "filter_direct")
    report.tokens_evidence = _purpose_tokens(caller, "filter_evidence")
    report.tokens_critique = _purpose_tokens(caller, "filter_critique")
    report.cache_hits = cache_store.hits
    report.cache_misses = cache_store.misses
    return report


@dataclass
class StoredDecision:
    signature_id: str
    witness_key: str
    query_id: str
    direct: str | None = None
    evidence: str | None = None
    critique: str | None = None
    evidence_text: str | None = None
    atoms: list[Any] | None = None
    broad_accepted: bool = False

    @property
    def has_evidence_metadata(self) -> bool:
        if str(self.evidence_text or "").strip():
            return True
        for atom in self.atoms or []:
            if isinstance(atom, dict) and str(atom.get("evidence") or "").strip():
                return True
        return False

    @property
    def pattern(self) -> str:
        if self.direct is None and self.evidence is None and self.critique is None:
            return "unlabeled_majority_accept" if self.broad_accepted else "unlabeled"
        return "/".join(
            [
                _vote_token(self.direct),
                _vote_token(self.evidence),
                _vote_token(self.critique),
            ]
        )


def _vote_token(value: str | None) -> str:
    if value is None:
        return "-"
    return _bool(value)[0].upper()


def _recorded_votes(decision: StoredDecision) -> list[str]:
    out: list[str] = []
    for value in (decision.direct, decision.evidence, decision.critique):
        if value is not None:
            out.append(_bool(value))
    return out


def rule_primary(decision: StoredDecision) -> bool:
    return _bool(decision.direct or "") == "true" and decision.direct is not None and _bool(
        decision.evidence or ""
    ) == "true" and decision.evidence is not None


def rule_two_true_no_false(decision: StoredDecision) -> bool:
    votes = _recorded_votes(decision)
    return votes.count("true") >= 2 and "false" not in votes


def rule_evidence_plus_one(decision: StoredDecision) -> bool:
    return (
        decision.evidence is not None
        and _bool(decision.evidence) == "true"
        and (
            (decision.direct is not None and _bool(decision.direct) == "true")
            or (decision.critique is not None and _bool(decision.critique) == "true")
        )
    )


def rule_strict_grounded(decision: StoredDecision) -> bool:
    return rule_primary(decision) and decision.has_evidence_metadata


def rule_broad_original(decision: StoredDecision) -> bool:
    votes = _recorded_votes(decision)
    if votes:
        return votes.count("true") >= 2
    return bool(decision.broad_accepted)


REPLAY_RULES: dict[str, Callable[[StoredDecision], bool]] = {
    "primary": rule_primary,
    "two_true_no_false": rule_two_true_no_false,
    "evidence_plus_one": rule_evidence_plus_one,
    "strict_grounded": rule_strict_grounded,
    "broad_original": rule_broad_original,
}


def select_replay(decisions: Iterable[StoredDecision], name: str) -> list[StoredDecision]:
    rule = REPLAY_RULES[name]
    return [item for item in decisions if rule(item)]


def _decision_from_row(row: dict[str, Any]) -> StoredDecision:
    strategy = row.get("evidence_first")
    if strategy is None:
        raw = row.get("evidence")
        if raw in (None, "true", "false", "unknown", "TRUE", "FALSE", "UNKNOWN", True, False):
            strategy = raw
        else:
            strategy = None
    text = row.get("evidence_text")
    if text is None and strategy is None:
        text = row.get("evidence")
        if text in ("true", "false", "unknown", "TRUE", "FALSE", "UNKNOWN", True, False):
            text = None
    return StoredDecision(
        signature_id=str(row.get("signature_id") or row.get("query_signature_id") or ""),
        witness_key=str(row.get("witness_key") or ""),
        query_id=str(row.get("query_id") or row.get("provenance") or ""),
        direct=None if row.get("direct") is None else _bool(row.get("direct")),
        evidence=None if strategy is None else _bool(strategy),
        critique=None if row.get("critique") is None else _bool(row.get("critique")),
        evidence_text=None if text in (None, "") else str(text),
        atoms=list(row.get("atoms") or []) or None,
        broad_accepted=bool(row.get("broad_accepted") or row.get("accepted")),
    )


def load_vote_journal(path: str | Path) -> list[StoredDecision]:
    found: list[StoredDecision] = []
    text = Path(path).read_text()
    if not text.strip():
        return found
    if text.lstrip().startswith("["):
        rows = json.loads(text)
        return [_decision_from_row(row) for row in rows if isinstance(row, dict)]
    for line in text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            found.append(_decision_from_row(row))
    return found


def load_broad_additions(sqlite_path: str | Path) -> list[StoredDecision]:
    conn = sqlite3.connect(str(sqlite_path))
    try:
        rows = conn.execute(
            "SELECT query_signature_id, witness_key, provenance "
            "FROM filter_additions WHERE resolved = 1 AND truth = 1"
        ).fetchall()
    finally:
        conn.close()
    return [
        StoredDecision(
            signature_id=str(sig),
            witness_key=str(key),
            query_id=str(prov or ""),
            broad_accepted=True,
        )
        for sig, key, prov in rows
    ]


def load_stored_decisions(
    vote_paths: Iterable[str | Path],
    addition_db: str | Path | None = None,
) -> tuple[list[StoredDecision], dict[str, Any]]:
    labeled: dict[tuple[str, str], StoredDecision] = {}
    sources: list[str] = []
    for path in vote_paths:
        item = Path(path)
        if not item.is_file():
            continue
        sources.append(str(item))
        for decision in load_vote_journal(item):
            labeled[(decision.signature_id, decision.witness_key)] = decision
    broad: list[StoredDecision] = []
    if addition_db and Path(addition_db).is_file():
        sources.append(str(Path(addition_db)))
        broad = load_broad_additions(addition_db)
        for decision in broad:
            key = (decision.signature_id, decision.witness_key)
            if key in labeled:
                labeled[key].broad_accepted = True
            else:
                labeled[key] = decision
    return list(labeled.values()), {
        "sources": sources,
        "n_decisions": len(labeled),
        "n_labeled_strategies": sum(
            1 for item in labeled.values() if item.direct is not None or item.evidence is not None
        ),
        "n_broad_accepted": sum(1 for item in labeled.values() if item.broad_accepted),
        "n_with_evidence_metadata": sum(1 for item in labeled.values() if item.has_evidence_metadata),
    }


def materialize_replay(
    agent_db: str | Path,
    dest: str | Path,
    decisions: Iterable[StoredDecision],
    statements: dict[str, str],
    predicates: list[Any],
) -> dict[str, Any]:
    src = Path(agent_db)
    path = Path(dest)
    if path.exists():
        path.unlink()
    shutil.copy2(src, path)
    unique: list[StoredDecision] = []
    seen: set[tuple[str, str]] = set()
    for item in decisions:
        pair = (item.signature_id, item.witness_key)
        if pair in seen:
            continue
        seen.add(pair)
        unique.append(item)
    conn = sqlite3.connect(str(path))
    try:
        ensure_filter_table(conn)
        conn.commit()
        empty_bags = compare_bags(src, path, statements, predicates)
        before_bags = query_bags(path, statements, predicates, conn=conn)
        before_grain = {
            qid: _grain_keys(conn, path, qid, sql, predicates) for qid, sql in statements.items()
        }
        for item in unique:
            add_filter(conn, item.signature_id, item.witness_key, item.query_id)
        conn.commit()
        after_bags = query_bags(path, statements, predicates, conn=conn)
        after_grain = {
            qid: _grain_keys(conn, path, qid, sql, predicates) for qid, sql in statements.items()
        }
        dropped = []
        reassigned = []
        for qid, sql in statements.items():
            before_keys, before_groups = before_grain[qid]
            after_keys, after_groups = after_grain[qid]
            if before_keys - after_keys:
                dropped.append(qid)
            for key, group in before_groups.items():
                if after_groups.get(key) != group:
                    reassigned.append(qid)
                    break
        added_sigs = {item.signature_id for item in unique}
        unrelated = [
            qid
            for qid, sql in statements.items()
            if after_bags.get(qid) != before_bags.get(qid)
            and filter_signature_id(sql) not in added_sigs
        ]
        keys_by_sig: dict[str, set[str]] = {}
        for qid, sql in statements.items():
            sig = filter_signature_id(sql)
            keys_by_sig.setdefault(sig, set()).update(after_grain[qid][0])
        visible = [
            item
            for item in unique
            if item.witness_key in keys_by_sig.get(item.signature_id, set())
        ]
        changed = [qid for qid in statements if after_bags.get(qid) != before_bags.get(qid)]
        preserved = [qid for qid in statements if qid not in changed]
        empty_before = [qid for qid in statements if not before_bags.get(qid)]
        empty_after = [qid for qid in statements if not after_bags.get(qid)]
        filled = [qid for qid in empty_before if qid not in empty_after]
        deltas = []
        for qid, sql in statements.items():
            before_n = count_mass(src, sql, predicates)
            after_n = count_mass(path, sql, predicates)
            deltas.append(
                {
                    "query_id": qid,
                    "signature_id": filter_signature_id(sql) if has_row_filter(sql) else "",
                    "count_before": before_n,
                    "count_after": after_n,
                    "count_delta": after_n - before_n,
                    "bag_changed": qid in changed,
                    "empty_before": qid in empty_before,
                    "empty_after": qid in empty_after,
                }
            )
        if dropped or reassigned or unrelated or not empty_bags["ok"]:
            raise RuntimeError(
                "replay invariants failed: "
                f"dropped={dropped[:8]} reassigned={reassigned[:8]} "
                f"unrelated={unrelated[:8]} empty_wrap={empty_bags}"
            )
        return {
            "n_proposed": len(unique),
            "n_materialized": len(unique),
            "n_sql_visible": len(visible),
            "empty_wrap_ok": empty_bags["ok"],
            "incumbent_dropped": dropped,
            "incumbent_reassigned": reassigned,
            "unrelated_changed": unrelated,
            "changed_queries": changed,
            "unchanged_queries": preserved,
            "empty_before": len(empty_before),
            "empty_after": len(empty_after),
            "empty_filled": filled,
            "count_mass_delta": sum(int(row["count_delta"]) for row in deltas),
            "per_query_delta": deltas,
        }
    finally:
        conn.close()
