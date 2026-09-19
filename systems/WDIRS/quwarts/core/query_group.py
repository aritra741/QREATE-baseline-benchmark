"""Isolated group-classification. Query-local sidecar; base tables never change."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from sqlglot import exp

from quwarts.core.extract import find_surface_span
from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.query_filter import (
    NULL_SENTINEL,
    _outer_tables,
    alias_order,
    encode_witness_key,
    outer_alias_tables,
    witness_key_sql,
)
from quwarts.core.query_support import clip_context, grain_sql, query_shape
from quwarts.core.query_witness import compile_witness_spec, grain_sql_for, normalize_group
from quwarts.core.signature import table_aliases
from quwarts.core.signature_cache import CachedCaller, ResponseCache
from quwarts.core.workload import parse_sql

EST_TOKENS_PER_CALL = 350
CANDIDATE_BATCH = 4
SIDECAR = "group_labels"
_AGGS = (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)

GROUP_DDL = """
CREATE TABLE IF NOT EXISTS group_labels (
  expr_id TEXT NOT NULL,
  witness_key TEXT NOT NULL,
  group_value TEXT,
  resolved INTEGER NOT NULL DEFAULT 0,
  direct_decision TEXT,
  branch_decision TEXT,
  adjudicator_decision TEXT,
  raw TEXT,
  evidence TEXT,
  context_hash TEXT,
  token_cost INTEGER,
  provenance TEXT,
  PRIMARY KEY (expr_id, witness_key)
)
"""

GROUP_DDL_SITE = """
CREATE TABLE IF NOT EXISTS group_labels (
  expr_id TEXT NOT NULL,
  witness_key TEXT NOT NULL,
  group_value TEXT,
  resolved INTEGER NOT NULL DEFAULT 0,
  direct_decision TEXT,
  branch_decision TEXT,
  adjudicator_decision TEXT,
  raw TEXT,
  evidence TEXT,
  context_hash TEXT,
  token_cost INTEGER,
  provenance TEXT NOT NULL,
  PRIMARY KEY (expr_id, witness_key, provenance)
)
"""

DIRECT_PROMPT = """Choose exactly one group label from the allowed result set.
The set is the complete CASE definition: every THEN result and the ELSE/NULL result.
Literal absence is not automatically FALSE. Semantic inference is allowed.
Return JSON {"label":"<one allowed label>","evidence":"..."}.
ALLOWED_LABELS:
"""

BRANCH_PROMPT = """Judge this single CASE branch condition independently.
Do not choose the final group label. Return whether THIS condition holds.
Literal absence is not automatically FALSE. Semantic inference is allowed.
Return JSON {"truth":"true|false|unknown","evidence":"..."}.
BRANCH_CONDITION:
"""

ADJUDICATOR_PROMPT = """Two strategies proposed different group labels for the same CASE.
See the expression, source context, and both labels. Do not invent a third label
unless it is in the allowed set. Return one allowed label.
Return JSON {"label":"<one allowed label>","evidence":"..."}.
"""

LIVE_GROUP_POLICY = "unknown_else_escape"
FROZEN_GROUP_POLICY = {
    "policy": LIVE_GROUP_POLICY,
    "site_local": True,
    "compile": "finite_case_from_workload_ast",
    "dataset_allowlists": False,
    "query_allowlists": False,
    "attribute_allowlists": False,
    "resolve": "direct_branch_or_majority_of_2",
    "never_overwrite_true_branch": True,
    "case_eval": "sqlite_3vl",
    "all_else_escape": "diagnostic_only",
    "writes": "query_site_local_sidecar",
    "preserve": [
        "witness_support",
        "filters",
        "joins",
        "presence",
        "distinct_identity",
        "base_checksums",
    ],
}


def frozen_group_policy_digest() -> str:
    return hashlib.sha256(json.dumps(FROZEN_GROUP_POLICY, sort_keys=True).encode()).hexdigest()


@dataclass
class GroupExpr:
    expr_id: str
    alias: str
    sql: str
    allowed: tuple[Any, ...]
    branches: tuple[tuple[str, Any], ...]
    else_value: Any
    reason: str
    eligible: bool


@dataclass
class GroupVote:
    expr_id: str
    witness_key: str
    direct: Any
    branch: Any
    adjudicator: Any
    resolved: bool
    value: Any
    agreement: str
    retried: list[str] = field(default_factory=list)
    evidence: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    context_hash: str = ""
    tokens: int = 0


@dataclass
class GroupReport:
    tokens_spent: int = 0
    tokens_direct: int = 0
    tokens_branch: int = 0
    tokens_adjudicator: int = 0
    n_eligible: int = 0
    n_ineligible: int = 0
    n_witnesses: int = 0
    n_attempted: int = 0
    n_resolved: int = 0
    n_fallback: int = 0
    n_sql_visible: int = 0
    n_materialized: int = 0
    n_agreement_direct_branch: int = 0
    n_disagreement: int = 0
    n_adjudicator: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    retries: int = 0
    rollbacks: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    expressions: list[dict[str, Any]] = field(default_factory=list)
    per_query: list[dict[str, Any]] = field(default_factory=list)
    gates: dict[str, Any] = field(default_factory=dict)
    agreement: dict[str, int] = field(default_factory=dict)
    labels: dict[str, int] = field(default_factory=dict)


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _qid(value: str) -> str:
    return str(value).replace("'", "''")


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


def _norm_bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(key), json.dumps(row.get(key), default=str)) for key in row)))
    return tuple(sorted(frozen))


def _fetch(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    try:
        cur = conn.execute(sql)
    except sqlite3.Error:
        return []
    cols = [item[0] for item in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def canonicalize_group_sql(sql: str) -> str:
    try:
        tree = parse_sql(sql)
    except Exception:
        return " ".join((sql or "").lower().split())
    mapping: dict[str, str] = {}
    for col in tree.find_all(exp.Column):
        raw = (col.table or "").lower()
        if raw and raw not in mapping:
            mapping[raw] = f"${len(mapping)}"
        if raw in mapping:
            col.set("table", exp.to_identifier(mapping[raw]))
    return " ".join(tree.sql(dialect="sqlite").lower().split())


def group_expr_id(sql: str) -> str:
    return hashlib.sha256(canonicalize_group_sql(sql).encode()).hexdigest()[:16]


def _is_static(node: exp.Expression | None) -> bool:
    if node is None:
        return True
    if isinstance(node, exp.Null):
        return True
    if isinstance(node, exp.Literal):
        return True
    if isinstance(node, exp.Boolean):
        return True
    return False


def _static_value(node: exp.Expression | None) -> Any:
    if node is None or isinstance(node, exp.Null):
        return None
    if isinstance(node, exp.Literal):
        raw = node.this
        if node.is_number:
            try:
                return int(raw) if "." not in str(raw) else float(raw)
            except (TypeError, ValueError):
                return raw
        return str(raw)
    if isinstance(node, exp.Boolean):
        return bool(node.this)
    return None


def _has_agg(node: exp.Expression | None) -> bool:
    return bool(node is not None and node.find(_AGGS))


def compile_group_expr(alias: str, sql: str) -> GroupExpr:
    reason = "eligible"
    eligible = False
    allowed: tuple[Any, ...] = ()
    branches: tuple[tuple[str, Any], ...] = ()
    else_value: Any = None
    try:
        tree = parse_sql(sql)
    except Exception:
        return GroupExpr(group_expr_id(sql), alias, sql, (), (), None, "unparseable", False)
    if _has_agg(tree):
        return GroupExpr(group_expr_id(sql), alias, sql, (), (), None, "nested_aggregate", False)
    case = tree if isinstance(tree, exp.Case) else tree.find(exp.Case)
    if case is None:
        return GroupExpr(group_expr_id(sql), alias, sql, (), (), None, "open_ended_projection", False)
    found: list[tuple[str, Any]] = []
    labels: list[Any] = []
    for pair in case.args.get("ifs") or []:
        cond = pair.this
        result = pair.args.get("true")
        if not _is_static(result) or _has_agg(cond):
            return GroupExpr(group_expr_id(sql), alias, sql, (), (), None, "open_ended_result", False)
        value = _static_value(result)
        found.append((cond.sql(dialect="sqlite") if cond is not None else "1", value))
        labels.append(value)
    default = case.args.get("default")
    if default is None:
        else_value = None
        labels.append(None)
    elif not _is_static(default) or _has_agg(default):
        return GroupExpr(group_expr_id(sql), alias, sql, (), (), None, "open_ended_result", False)
    else:
        else_value = _static_value(default)
        labels.append(else_value)
    uniq = tuple(dict.fromkeys(labels))
    if not uniq:
        return GroupExpr(group_expr_id(sql), alias, sql, (), (), else_value, "empty_result_set", False)
    return GroupExpr(
        group_expr_id(sql),
        alias,
        sql,
        uniq,
        tuple(found),
        else_value,
        "case_finite",
        True,
    )


def extract_group_expressions(sql: str) -> list[GroupExpr]:
    shape = query_shape("q", sql)
    found: list[GroupExpr] = []
    seen: set[str] = set()
    for alias, expr_sql in zip(shape.group_aliases, shape.group_sql):
        item = compile_group_expr(alias, expr_sql)
        if item.expr_id in seen:
            continue
        seen.add(item.expr_id)
        found.append(item)
    return found


def ensure_group_table(conn: sqlite3.Connection, site_local: bool = False) -> None:
    conn.execute(GROUP_DDL_SITE if site_local else GROUP_DDL)


def _has_group_table(sqlite_path: str | Path) -> bool:
    conn = sqlite3.connect(str(sqlite_path))
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return SIDECAR in names
    finally:
        conn.close()


def allowed_text(values: Iterable[Any]) -> list[str]:
    out = []
    for value in values:
        if value is None:
            out.append("NULL")
        else:
            out.append(str(value))
    return out


def same_label(left: Any, right: Any) -> bool:
    return normalize_group(left) == normalize_group(right)


def parse_allowed(raw: Any, allowed: Iterable[Any]) -> Any | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text.lower() in {"null", "none", ""}:
        target = None
    else:
        target = text
    for item in allowed:
        if same_label(item, target):
            return item
    return None


def wrap_group_sql(expr_sql: str, expr_id: str, key_sql: str, site_id: str | None = None) -> str:
    site = f" AND g.provenance = '{_qid(site_id)}'" if site_id else ""
    return (
        f"CASE WHEN (SELECT g.resolved FROM group_labels g "
        f"WHERE g.expr_id = '{_qid(expr_id)}' AND g.witness_key = {key_sql}{site}) = 1 "
        f"THEN (SELECT g.group_value FROM group_labels g "
        f"WHERE g.expr_id = '{_qid(expr_id)}' AND g.witness_key = {key_sql}{site}) "
        f"ELSE ({expr_sql}) END"
    )


def _replace_expr(
    node: exp.Expression,
    targets: dict[str, GroupExpr],
    key_sql: str,
    site_id: str | None = None,
) -> exp.Expression:
    if "group_labels" in node.sql(dialect="sqlite").lower():
        return node
    digest = group_expr_id(node.sql(dialect="sqlite"))
    item = targets.get(digest)
    if item is None or not item.eligible:
        return node
    return parse_sql(wrap_group_sql(node.sql(dialect="sqlite"), item.expr_id, key_sql, site_id=site_id))


def rewrite_group_sql(sql: str, expressions: Iterable[GroupExpr], site_id: str | None = None) -> str:
    wanted = {item.expr_id: item for item in expressions if item.eligible}
    if not wanted:
        return sql
    tree = parse_sql(sql)
    if not isinstance(tree, exp.Select):
        return sql
    if "group_labels" in sql.lower():
        return sql
    key = witness_key_sql(tree)
    by_alias = {item.alias.lower(): item for item in wanted.values()}

    replaced = []
    for proj in tree.expressions:
        alias = (proj.alias if isinstance(proj, exp.Alias) else "").lower()
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        if expr.find(_AGGS):
            replaced.append(proj)
            continue
        item = by_alias.get(alias) or wanted.get(group_expr_id(expr.sql(dialect="sqlite")))
        if item is None or not item.eligible:
            replaced.append(proj)
            continue
        wrapped = parse_sql(wrap_group_sql(expr.sql(dialect="sqlite"), item.expr_id, key, site_id=site_id))
        replaced.append(exp.alias_(wrapped, alias or item.alias))
    tree.set("expressions", replaced)

    group = tree.args.get("group")
    if group is not None:
        items = []
        for node in group.expressions:
            if isinstance(node, exp.Column) and not node.table:
                items.append(node)
                continue
            items.append(_replace_expr(node, wanted, key, site_id=site_id))
        group.set("expressions", items)

    having = tree.args.get("having")
    if having is not None:
        tree.set("having", exp.Having(this=_replace_expr(having.this, wanted, key, site_id=site_id)))

    order = tree.args.get("order")
    if order is not None:
        ordered = []
        for node in order.expressions:
            payload = node.this if isinstance(node, exp.Ordered) else node
            if isinstance(payload, exp.Column) and not payload.table:
                ordered.append(node)
                continue
            swapped = _replace_expr(payload, wanted, key, site_id=site_id)
            if isinstance(node, exp.Ordered):
                node.set("this", swapped)
                ordered.append(node)
            else:
                ordered.append(swapped)
        order.set("expressions", ordered)
    return tree.sql(dialect="sqlite")


def rewrite_sites(sql: str, expressions: Iterable[GroupExpr], site_id: str | None = None) -> list[dict[str, str]]:
    tree = parse_sql(rewrite_group_sql(sql, expressions, site_id=site_id))
    wanted = {item.expr_id for item in expressions if item.eligible}
    found = []
    if not isinstance(tree, exp.Select):
        return found

    def note(clause: str, node: exp.Expression) -> None:
        text = node.sql(dialect="sqlite")
        if "group_labels" not in text.lower():
            return
        for expr_id in wanted:
            if expr_id in text:
                found.append({"clause": clause, "expr_id": expr_id, "sql": text})

    for proj in tree.expressions:
        note("select", proj)
    group = tree.args.get("group")
    if group is not None:
        for node in group.expressions:
            note("group", node)
    having = tree.args.get("having")
    if having is not None:
        note("having", having.this)
    order = tree.args.get("order")
    if order is not None:
        for node in order.expressions:
            note("order", node.this if isinstance(node, exp.Ordered) else node)
    return found


def same_sidecar_rewrite(sql: str, expressions: Iterable[GroupExpr]) -> bool:
    sites = rewrite_sites(sql, expressions)
    by_id: dict[str, set[str]] = defaultdict(set)
    for item in sites:
        if item["clause"] in {"select", "group", "having", "order"}:
            by_id[item["expr_id"]].add(
                "resolved = 1" in item["sql"].replace("g.resolved", "resolved")
                or "resolved=1" in item["sql"].replace(" ", "")
            )
    for item in sites:
        if "THEN (SELECT g.group_value" not in item["sql"] and "then (select g.group_value" not in item["sql"].lower():
            return False
        if "ELSE (" not in item["sql"] and "else (" not in item["sql"].lower():
            return False
    return True


def reaggregate_sql(sql: str) -> str:
    tree = parse_sql(sql)
    if not isinstance(tree, exp.Select):
        return sql
    groups: list[tuple[str, exp.Expression]] = []
    aggs: list[tuple[str, exp.Expression]] = []
    for index, proj in enumerate(tree.expressions):
        alias = proj.alias if isinstance(proj, exp.Alias) else f"c{index}"
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        if expr.find(_AGGS):
            aggs.append((alias, expr))
        else:
            groups.append((alias, proj))
    inner = tree.copy()
    inner.set("group", None)
    inner.set("having", None)
    inner.set("order", None)
    kept: list[exp.Expression] = []
    for alias, proj in groups:
        kept.append(proj if isinstance(proj, exp.Alias) else exp.alias_(proj, alias))
    for index, (alias, expr) in enumerate(aggs):
        count = expr if isinstance(expr, exp.Count) else expr.find(exp.Count)
        total = expr if isinstance(expr, exp.Sum) else expr.find(exp.Sum)
        if count is not None and (count.args.get("distinct") or isinstance(count.this, exp.Distinct)):
            inner_expr = count.this
            if isinstance(inner_expr, exp.Distinct) and inner_expr.expressions:
                inner_expr = inner_expr.expressions[0]
            kept.append(exp.alias_(inner_expr or exp.Null(), f"__d{index}"))
        elif total is not None:
            kept.append(exp.alias_(total.this or exp.Literal.number(0), f"__s{index}"))
        else:
            kept.append(exp.alias_(exp.Literal.number(1), f"__c{index}"))
    if not kept:
        kept.append(exp.Literal.number(1))
    inner.set("expressions", kept)
    select = [f'{_quote(name)}' for name, _ in groups]
    for index, (alias, expr) in enumerate(aggs):
        count = expr if isinstance(expr, exp.Count) else expr.find(exp.Count)
        total = expr if isinstance(expr, exp.Sum) else expr.find(exp.Sum)
        if count is not None and (count.args.get("distinct") or isinstance(count.this, exp.Distinct)):
            select.append(f'COUNT(DISTINCT { _quote(f"__d{index}") }) AS {_quote(alias)}')
        elif total is not None:
            select.append(f'SUM({_quote(f"__s{index}")}) AS {_quote(alias)}')
        else:
            select.append(f'COUNT({_quote(f"__c{index}")}) AS {_quote(alias)}')
    body = f"SELECT {', '.join(select) if select else 'COUNT(*)'} FROM ({inner.sql(dialect='sqlite')})"
    if groups:
        body += " GROUP BY " + ", ".join(_quote(name) for name, _ in groups)
    return body


def traces_reaggregate_ok(conn: sqlite3.Connection, sql: str) -> bool:
    return _norm_bag(_fetch(conn, sql)) == _norm_bag(_fetch(conn, reaggregate_sql(sql)))


def apply_official_group(
    sql: str,
    sqlite_path: str | Path,
    predicates: list[Any] | None = None,
    site_id: str | None = None,
) -> tuple[str, list[GroupExpr]]:
    from quwarts.core.pipeline import official_sql

    official = official_sql(sql, sqlite_path, predicates)
    exprs = extract_group_expressions(official)
    if not any(item.eligible for item in exprs):
        exprs = extract_group_expressions(sql)
    return rewrite_group_sql(official, exprs, site_id=site_id), exprs


def group_bags(
    sqlite_path: str | Path,
    statements: dict[str, str],
    predicates: list[Any],
    conn: sqlite3.Connection | None = None,
    site_local: bool = False,
) -> dict[str, tuple]:
    own = conn is None
    if own:
        conn = sqlite3.connect(str(sqlite_path))
    try:
        out = {}
        for qid, sql in statements.items():
            rewritten, _ = apply_official_group(
                sql, sqlite_path, predicates, site_id=qid if site_local else None
            )
            out[qid] = _norm_bag(_fetch(conn, rewritten))
        return out
    finally:
        if own:
            conn.close()


def apply_branch_votes(expr: GroupExpr, votes: list[str]) -> Any:
    for (cond, result), vote in zip(expr.branches, votes):
        if str(vote).strip().lower() == "true":
            return result
    return expr.else_value


def _bool(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return "true"
    if text in {"false", "no", "0"}:
        return "false"
    return "unknown"


def _row_context(conn: sqlite3.Connection, table: str, rowid: int | None, documents: dict[str, str] | None) -> dict[str, Any]:
    docs = documents or {}
    if rowid is None:
        return {"rowid": None, "table": table, "label": "", "entity_id": "", "cells": {}, "document": ""}
    names = {row[0].lower(): row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    real = names.get(table.lower(), table)
    raw = conn.execute(f"SELECT rowid AS _rid, * FROM {_quote(real)} WHERE rowid = ?", [rowid]).fetchone()
    if raw is None:
        return {"rowid": rowid, "table": table, "label": "", "entity_id": "", "cells": {}, "document": ""}
    cols = [item[0] for item in conn.execute(f"PRAGMA table_info({_quote(real)})")]
    payload = dict(zip(["_rid", *cols], raw))
    cells = {
        key: payload.get(key)
        for key in cols
        if not str(key).startswith("sig_") and str(key).lower() != "rowid"
    }
    doc_id = payload.get("doc_id") or payload.get("id")
    label = next(
        (payload.get(name) for name in cells if str(name).lower().endswith("name") and payload.get(name) not in (None, "")),
        doc_id or rowid,
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


def _snippets(document: str, cells: dict[str, Any], needles: list[str], limit: int = 700) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for needle in needles:
        snippet = clip_context(document, needle if needle else None, limit=limit)
        if snippet and snippet not in seen:
            seen.add(snippet)
            parts.append(snippet)
        find_surface_span(document or "", needle)
    if not parts and document:
        parts.append(clip_context(document, limit=limit))
    return "\n---\n".join(parts)[:1400]


def _context_block(item: dict[str, Any], broad: bool = False) -> str:
    cells = item.get("cells") or {}
    shown = "\n".join(f"  {key}: {cells[key]}" for key in cells if cells[key] not in (None, ""))
    snippets = item.get("broad_snippets") if broad and item.get("broad_snippets") else item.get("snippets")
    return (
        f"ENTITY_LABEL: {item.get('label') or ''}\n"
        f"WITNESS_KEY: {item.get('witness_key')}\n"
        f"GROUP_EXPRESSION:\n{item.get('expr_sql')}\n"
        f"EXTRACTED_VALUES:\n{shown or '  (none)'}\n"
        f"DOCUMENT_SNIPPETS:\n{snippets or ''}\n"
    )


def _ask_label(caller: BudgetedCaller, prompt: str, purpose: str, allowed: Iterable[Any]) -> tuple[Any, dict[str, Any], bool]:
    retried = False
    payload: Any = {}
    for attempt in range(2):
        try:
            text = caller.complete(
                prompt,
                purpose=purpose,
                system="Classify one group label. JSON only.",
                max_tokens=220,
                plan=purpose,
            )
        except BudgetExhausted:
            raise
        except Exception:
            text = ""
            payload = {}
        else:
            payload = _payload(text)
        label = parse_allowed((payload or {}).get("label") if isinstance(payload, dict) else None, allowed)
        if label is not None or (isinstance(payload, dict) and payload.get("label") in {"NULL", "null", None} and any(v is None for v in allowed)):
            if label is None and any(v is None for v in allowed) and str((payload or {}).get("label")).lower() in {"null", "none", ""}:
                return None, payload if isinstance(payload, dict) else {}, retried
            if label is not None:
                return label, payload if isinstance(payload, dict) else {}, retried
        retried = True
        if attempt == 0:
            continue
    return None, payload if isinstance(payload, dict) else {}, True


def _ask_truth(caller: BudgetedCaller, prompt: str, purpose: str) -> tuple[str, dict[str, Any], bool]:
    retried = False
    payload: Any = {}
    for attempt in range(2):
        try:
            text = caller.complete(
                prompt,
                purpose=purpose,
                system="Judge one CASE branch. JSON only.",
                max_tokens=160,
                plan=purpose,
            )
        except BudgetExhausted:
            raise
        except Exception:
            text = ""
            payload = {}
        else:
            payload = _payload(text)
        if isinstance(payload, dict) and payload.get("truth") is not None:
            return _bool(payload.get("truth")), payload, retried
        retried = True
        if attempt == 0:
            continue
    return "unknown", payload if isinstance(payload, dict) else {}, True


def classify_group(caller: BudgetedCaller, item: dict[str, Any], expr: GroupExpr) -> GroupVote:
    labels = allowed_text(expr.allowed)
    body = _context_block(item)
    context_hash = hashlib.sha256(body.encode()).hexdigest()[:16]
    spent0 = caller.ledger.spent
    direct, d_raw, d_retry = _ask_label(
        caller,
        DIRECT_PROMPT + json.dumps(labels) + "\n" + body,
        "group_direct",
        expr.allowed,
    )
    branch_votes = []
    branch_raw = []
    b_retry = False
    for cond, result in expr.branches:
        truth, raw, retried = _ask_truth(
            caller,
            BRANCH_PROMPT + cond + f"\nTHEN {result}\n" + body,
            "group_branch",
        )
        branch_votes.append(truth)
        branch_raw.append(raw)
        b_retry = b_retry or retried
    branch = apply_branch_votes(expr, branch_votes)
    adjudicator = None
    a_raw: dict[str, Any] | None = None
    a_retry = False
    agreement = "direct_branch" if same_label(direct, branch) and direct is not None else "disagree"
    value = direct if agreement == "direct_branch" else None
    if agreement != "direct_branch":
        extra = (
            f"PROPOSED_A: {direct}\nPROPOSED_B: {branch}\n"
            f"ALLOWED_LABELS: {json.dumps(labels)}\n"
        )
        broad = _context_block(item, broad=True)
        adjudicator, a_raw, a_retry = _ask_label(
            caller,
            ADJUDICATOR_PROMPT + extra + broad,
            "group_adjudicator",
            expr.allowed,
        )
        votes = [direct, branch, adjudicator]
        counts = Counter(normalize_group(item) for item in votes if item is not None or item in expr.allowed)
        winner, n = (counts.most_common(1)[0] if counts else (None, 0))
        if n >= 2:
            agreement = "majority"
            for candidate in votes:
                if normalize_group(candidate) == winner:
                    value = candidate
                    break
        else:
            agreement = "fallback"
            value = None
    resolved = agreement in {"direct_branch", "majority"}
    retried = []
    if d_retry:
        retried.append("direct")
    if b_retry:
        retried.append("branch")
    if a_retry:
        retried.append("adjudicator")
    evidence = None
    for raw in (d_raw, a_raw, *(branch_raw or [])):
        if isinstance(raw, dict) and str(raw.get("evidence") or "").strip():
            evidence = str(raw.get("evidence"))
            break
    return GroupVote(
        expr_id=expr.expr_id,
        witness_key=str(item["witness_key"]),
        direct=direct,
        branch=branch,
        adjudicator=adjudicator,
        resolved=resolved,
        value=value,
        agreement=agreement,
        retried=retried,
        evidence=evidence,
        raw={"direct": d_raw, "branch": branch_raw, "adjudicator": a_raw, "branch_votes": branch_votes},
        context_hash=context_hash,
        tokens=caller.ledger.spent - spent0,
    )


def persist_group_vote(path: str | Path, query_id: str, item: dict[str, Any], vote: GroupVote) -> None:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "query_id": query_id,
        "expr_id": vote.expr_id,
        "witness_key": vote.witness_key,
        "group_value": vote.value,
        "resolved": vote.resolved and vote.agreement != "fallback",
        "direct_decision": vote.direct,
        "branch_decision": vote.branch,
        "adjudicator_decision": vote.adjudicator,
        "raw": vote.raw,
        "evidence": vote.evidence,
        "context_hash": vote.context_hash,
        "token_cost": vote.tokens,
        "provenance": query_id,
        "agreement": vote.agreement,
        "retried": vote.retried,
        "old_label": item.get("old_label"),
        "allowed": item.get("allowed"),
    }
    with dest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def _policy_write(item: dict[str, Any]) -> dict[str, Any]:
    vote = item["vote"]
    return {
        "query_id": item["query_id"],
        "expr_id": item["expr_id"],
        "witness_key": item["witness_key"],
        "group_value": vote.get("group_value"),
        "old_label": vote.get("old_label"),
        "resolved": True,
        "agreement": vote.get("agreement"),
        "direct_decision": vote.get("direct_decision"),
        "branch_decision": vote.get("branch_decision"),
        "adjudicator_decision": vote.get("adjudicator_decision"),
        "raw": vote.get("raw") or {},
        "context_hash": vote.get("context_hash") or "",
        "token_cost": vote.get("token_cost") or 0,
        "evidence": vote.get("evidence"),
    }


def accept_live_materialize(state: dict[str, Any], vote: dict[str, Any]) -> bool:
    from quwarts.core.group_case_escape import unknown_else_escape

    return unknown_else_escape(state, vote)


def apply_live_group_policy(
    dest: str | Path,
    queries: list[dict[str, str]],
    predicates: Iterable[Any],
    votes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Materialize persisted votes under the frozen live CASE policy. No model or gold."""
    from quwarts.core.group_case_escape import inspect_votes
    from quwarts.core.group_consensus import replay_consensus

    live = list(predicates)
    statements = {row["query_id"]: row["sql"] for row in queries}
    inspected = inspect_votes(dest, queries, live, votes)
    writes = [
        _policy_write(item) for item in inspected if accept_live_materialize(item["state"], item["vote"])
    ]
    report = replay_consensus(Path(dest), statements, live, writes)
    report["policy"] = LIVE_GROUP_POLICY
    report["frozen_policy"] = dict(FROZEN_GROUP_POLICY)
    report["policy_digest"] = frozen_group_policy_digest()
    report["n_inspected"] = len(inspected)
    report["n_policy_pass"] = len(writes)
    return report


def upsert_group_label(conn: sqlite3.Connection, vote: GroupVote, provenance: str) -> None:
    ensure_group_table(conn, site_local=True)
    resolved = 1 if vote.resolved and vote.agreement != "fallback" else 0
    conn.execute(
        "INSERT OR REPLACE INTO group_labels("
        "expr_id, witness_key, group_value, resolved, direct_decision, branch_decision, "
        "adjudicator_decision, raw, evidence, context_hash, token_cost, provenance) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            vote.expr_id,
            vote.witness_key,
            None if vote.value is None else str(vote.value),
            resolved,
            None if vote.direct is None else str(vote.direct),
            None if vote.branch is None else str(vote.branch),
            None if vote.adjudicator is None else str(vote.adjudicator),
            json.dumps(vote.raw, default=str),
            vote.evidence,
            vote.context_hash,
            vote.tokens,
            provenance,
        ],
    )


def supported_group_witnesses(
    sqlite_path: str | Path,
    query_id: str,
    sql: str,
    predicates: list[Any],
    documents: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    from quwarts.core.pipeline import official_sql

    path = Path(sqlite_path)
    official = official_sql(sql, path, predicates)
    exprs = extract_group_expressions(official) or extract_group_expressions(sql)
    spec = compile_witness_spec(query_id, sql)
    tree = parse_sql(official)
    order = alias_order(tree)
    aliases = outer_alias_tables(tree) or table_aliases(tree)
    grain_tree = parse_sql(grain_sql(official))
    if isinstance(grain_tree, exp.Select):
        grain_tree.set("expressions", list(grain_tree.expressions) + [exp.alias_(parse_sql(witness_key_sql(tree)), "__wk")])
        grain = grain_tree.sql(dialect="sqlite")
    else:
        grain = grain_sql(official)
    conn = sqlite3.connect(str(path))
    try:
        rows = _fetch(conn, grain)
        out = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            rids = []
            contexts = []
            for alias in order:
                raw = row.get(f"{alias}__rid")
                rid = None if raw in (None, "") else int(raw)
                rids.append(rid)
                contexts.append(_row_context(conn, aliases.get(alias, alias), rid, documents))
            key = str(row.get("__wk") or (encode_witness_key(rids) if rids else encode_witness_key([0])))
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
            needles = []
            for item in exprs:
                needles.append(item.sql)
                needles.extend(re.findall(r"'([^']+)'", item.sql))
            for value in cells.values():
                if value not in (None, ""):
                    needles.append(str(value))
            snippets = _snippets(document, cells, needles)
            broad = _snippets(document, cells, needles, limit=2400)
            for item in exprs:
                if not item.eligible:
                    continue
                pair = (item.expr_id, key)
                if pair in seen:
                    continue
                seen.add(pair)
                out.append(
                    {
                        "query_id": query_id,
                        "expr_id": item.expr_id,
                        "alias": item.alias,
                        "expr_sql": item.sql,
                        "allowed": list(item.allowed),
                        "witness_key": key,
                        "old_label": row.get(item.alias),
                        "label": " | ".join(labels),
                        "cells": cells,
                        "document": document,
                        "snippets": snippets,
                        "broad_snippets": broad,
                        "expr": item,
                    }
                )
        return out
    finally:
        conn.close()


def _support_keys(conn: sqlite3.Connection, sqlite_path: str | Path, query_id: str, sql: str, predicates: list[Any]) -> set[str]:
    from quwarts.core.pipeline import official_sql

    spec = compile_witness_spec(query_id, sql)
    grain = official_sql(grain_sql_for(spec), sqlite_path, predicates)
    rows = _fetch(conn, grain)
    order = alias_order(parse_sql(official_sql(sql, sqlite_path, predicates)))
    keys = set()
    for row in rows:
        rids = [None if row.get(f"{alias}__rid") in (None, "") else int(row.get(f"{alias}__rid")) for alias in order]
        keys.add(encode_witness_key(rids) if rids else encode_witness_key([0]))
    return keys


def _join_pairs(conn: sqlite3.Connection, sqlite_path: str | Path, sql: str, predicates: list[Any]) -> frozenset:
    from quwarts.core.component_oracle import from_join_sql
    from quwarts.core.pipeline import official_sql

    spec = compile_witness_spec("q", sql)
    rows = _fetch(conn, official_sql(from_join_sql(sql), sqlite_path, predicates))
    pairs = []
    for join in spec.joins:
        for row in rows:
            left = row.get(f"{join.left_alias}__rid")
            right = row.get(f"{join.right_alias}__rid")
            if left in (None, "") or right in (None, ""):
                continue
            pairs.append((join.join_id, int(left), int(right)))
    return frozenset(pairs)


def _query_amp(sql: str, workload: Any | None) -> float:
    if workload is None:
        return 1.0
    try:
        tree = parse_sql(sql)
    except Exception:
        return 1.0
    values = []
    for col in tree.find_all(exp.Column):
        req = (workload.requirements or {}).get((col.name or "").lower())
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


def _checksums(conn: sqlite3.Connection) -> dict[str, str]:
    from quwarts.core.component_oracle import base_checksums

    return base_checksums(conn)


def _ids_for(conn: sqlite3.Connection, table: str, rowid: int) -> str:
    cols = {row[1].lower() for row in conn.execute(f'PRAGMA table_info("{table}")')}
    if "doc_id" in cols:
        row = conn.execute(f'SELECT doc_id FROM "{table}" WHERE rowid = ?', [rowid]).fetchone()
        if row and row[0] not in (None, ""):
            return Path(str(row[0])).stem
    if "id" in cols:
        row = conn.execute(f'SELECT id FROM "{table}" WHERE rowid = ?', [rowid]).fetchone()
        return "" if not row or row[0] in (None, "") else str(row[0])
    return str(rowid)


def _entity_tuple(conn: sqlite3.Connection, spec, row: dict[str, Any]) -> tuple:
    parts = []
    for alias, table in spec.alias_to_table:
        raw = row.get(f"{alias}__rid")
        if raw in (None, ""):
            continue
        parts.append((table, _ids_for(conn, table, int(raw))))
    return tuple(sorted(parts))


def fill_gold_group_labels(
    dest: Path,
    gold_conn: sqlite3.Connection,
    queries: list[dict[str, str]],
    predicates: list[Any],
) -> dict[str, Any]:
    from quwarts.core.component_oracle import base_checksums
    from quwarts.core.pipeline import official_sql

    qw = sqlite3.connect(str(dest))
    ensure_group_table(qw)
    before = base_checksums(qw)
    writes = 0
    try:
        for row in queries:
            spec = compile_witness_spec(row["query_id"], row["sql"])
            official = official_sql(row["sql"], dest, predicates)
            exprs = [item for item in extract_group_expressions(official) if item.eligible]
            if not exprs:
                exprs = [item for item in extract_group_expressions(row["sql"]) if item.eligible]
            if not exprs:
                continue
            official_tree = parse_sql(official)
            key_sql = witness_key_sql(official_tree)
            grain_tree = parse_sql(grain_sql(official))
            if isinstance(grain_tree, exp.Select):
                grain_tree.set("expressions", list(grain_tree.expressions) + [exp.alias_(parse_sql(key_sql), "__wk")])
                grain_sql_live = grain_tree.sql(dialect="sqlite")
            else:
                grain_sql_live = grain_sql(official)
            qw_grain = _fetch(qw, grain_sql_live)
            gold_grain = _fetch(gold_conn, grain_sql(row["sql"]))
            gold_by = {_entity_tuple(gold_conn, spec, item): item for item in gold_grain}
            for item in qw_grain:
                ent = _entity_tuple(qw, spec, item)
                gold_row = gold_by.get(ent)
                if gold_row is None:
                    continue
                key = str(item.get("__wk") or encode_witness_key([0]))
                for expr in exprs:
                    new = gold_row.get(expr.alias)
                    old = item.get(expr.alias)
                    if same_label(old, new):
                        continue
                    stored = None if new in (None, "") else str(new)
                    qw.execute(
                        "INSERT OR REPLACE INTO group_labels("
                        "expr_id, witness_key, group_value, resolved, provenance) "
                        "VALUES (?, ?, ?, 1, ?)",
                        [expr.expr_id, key, stored, row["query_id"]],
                    )
                    writes += 1
        qw.commit()
        after = base_checksums(qw)
        return {"n_writes": writes, "checksums_ok": before == after, "before": before, "after": after}
    finally:
        qw.close()


def official_bags(
    sqlite_path: str | Path,
    statements: dict[str, str],
    predicates: list[Any],
) -> dict[str, tuple]:
    from quwarts.core.pipeline import official_sql

    conn = sqlite3.connect(str(sqlite_path))
    try:
        out = {}
        for qid, sql in statements.items():
            out[qid] = _norm_bag(_fetch(conn, official_sql(sql, sqlite_path, predicates)))
        return out
    finally:
        conn.close()


def run_group_arm(
    sqlite_path: str | Path,
    queries: list[dict[str, str]],
    predicates: Iterable[Any],
    *,
    documents: dict[str, str] | None = None,
    caller: BudgetedCaller | None = None,
    statements: dict[str, str] | None = None,
    checkpoint: str | Path | None = None,
    vote_journal: str | Path | None = None,
) -> GroupReport:
    live = list(predicates)
    report = GroupReport()
    cache_store = ResponseCache()
    path = Path(sqlite_path)
    all_statements = statements or {row["query_id"]: row["sql"] for row in queries}
    conn = sqlite3.connect(str(path))
    try:
        ensure_group_table(conn, site_local=True)
        before_checksums = _checksums(conn)
        conn.commit()
    finally:
        conn.close()
    if caller is None:
        return report
    journal = Path(vote_journal) if vote_journal else (
        Path(checkpoint).with_name("group_votes.jsonl") if checkpoint else path.parent / "group_votes.jsonl"
    )
    bound = CachedCaller(caller, cache_store, plan="group")
    workload = _workload(all_statements)
    by_expr: dict[str, dict[str, Any]] = {}
    ineligible = []
    for row in queries:
        official, exprs = apply_official_group(row["sql"], path, live)
        _ = official
        witnesses = supported_group_witnesses(path, row["query_id"], row["sql"], live, documents)
        eligible = [item for item in exprs if item.eligible]
        if not eligible:
            for item in exprs:
                ineligible.append({"query_id": row["query_id"], "alias": item.alias, "reason": item.reason, "sql": item.sql})
            report.skipped.append({"query_id": row["query_id"], "reason": "no_eligible_group"})
            continue
        amp = _query_amp(" ".join(item.sql for item in eligible), workload)
        for item in eligible:
            bucket = by_expr.setdefault(
                item.expr_id,
                {"expr": item, "queries": [], "witnesses": [], "amp": amp, "freq": 0},
            )
            bucket["queries"].append(row["query_id"])
            bucket["freq"] += 1
            bucket["amp"] = max(bucket["amp"], amp)
        for witness in witnesses:
            by_expr[witness["expr_id"]]["witnesses"].append({**witness, "query_id": row["query_id"]})
    report.n_ineligible = len(ineligible)
    report.skipped.extend(ineligible)
    ranked = []
    seen_pair: set[tuple[str, str]] = set()
    for expr_id, bucket in by_expr.items():
        unique = []
        for item in bucket["witnesses"]:
            pair = (expr_id, item["witness_key"])
            if pair in seen_pair:
                continue
            seen_pair.add(pair)
            unique.append(item)
        cost = max(2 * EST_TOKENS_PER_CALL, 1)
        score = bucket["freq"] * bucket["amp"] * len(unique) / cost
        ranked.append({**bucket, "expr_id": expr_id, "unique": unique, "score": score})
        report.expressions.append(
            {
                "expr_id": expr_id,
                "sql": bucket["expr"].sql,
                "alias": bucket["expr"].alias,
                "allowed": list(bucket["expr"].allowed),
                "eligible": True,
                "reason": bucket["expr"].reason,
                "n_queries": len(set(bucket["queries"])),
                "n_witnesses": len(unique),
                "freq": bucket["freq"],
                "amp": bucket["amp"],
                "score": score,
            }
        )
    report.n_eligible = len(ranked)
    ranked.sort(key=lambda item: (-item["score"], item["expr_id"]))
    bags = group_bags(path, all_statements, live, site_local=True)
    ckpt = Path(checkpoint) if checkpoint else None
    done_chunks: set[str] = set()
    if ckpt and ckpt.is_file():
        saved = json.loads(ckpt.read_text())
        report.per_query = list(saved.get("per_query") or [])
        report.rollbacks = list(saved.get("rollbacks") or [])
        report.n_resolved = int(saved.get("n_resolved") or 0)
        report.n_fallback = int(saved.get("n_fallback") or 0)
        report.n_sql_visible = int(saved.get("n_sql_visible") or 0)
        report.n_materialized = int(saved.get("n_materialized") or 0)
        done_chunks = set(saved.get("done_chunks") or [])
    states = []
    for item in ranked:
        chunks = [item["unique"][i : i + CANDIDATE_BATCH] for i in range(0, len(item["unique"]), CANDIDATE_BATCH)]
        report.n_witnesses += len(item["unique"])
        states.append({"item": item, "chunks": chunks, "cursor": 0})
    uses_expr = defaultdict(set)
    for row in queries:
        for expr in extract_group_expressions(row["sql"]):
            uses_expr[expr.expr_id].add(row["query_id"])
        official = None
        try:
            from quwarts.core.pipeline import official_sql as _off

            official = _off(row["sql"], path, live)
            for expr in extract_group_expressions(official):
                uses_expr[expr.expr_id].add(row["query_id"])
        except Exception:
            pass
    active = True
    while active and caller.ledger.remaining() > 0:
        active = False
        remaining_batches = sum(
            1
            for state in states
            for index, _ in enumerate(state["chunks"])
            if f"{state['item']['expr_id']}:{index}" not in done_chunks
        )
        for state in states:
            if caller.ledger.remaining() <= 0:
                break
            expr_id = state["item"]["expr_id"]
            expr = state["item"]["expr"]
            while state["cursor"] < len(state["chunks"]):
                chunk_id = f"{expr_id}:{state['cursor']}"
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
                        print(f"  hold {expr_id} est={est} remaining={caller.ledger.remaining()}", flush=True)
                        break
                elif est > quota and len(chunk) > 1:
                    chunk = chunk[: max(1, len(chunk) * quota // est)]
                active = True
                print(
                    f"group {expr_id} batch={state['cursor']} n={len(chunk)} "
                    f"est={est} remaining={caller.ledger.remaining()}",
                    flush=True,
                )
                votes: list[tuple[dict[str, Any], GroupVote]] = []
                try:
                    for cand in chunk:
                        vote = classify_group(bound, cand, expr)
                        persist_group_vote(journal, cand["query_id"], cand, vote)
                        votes.append((cand, vote))
                except BudgetExhausted:
                    print(f"  budget during {expr_id}", flush=True)
                fallback = 0
                for cand, vote in votes:
                    report.agreement[vote.agreement] = report.agreement.get(vote.agreement, 0) + 1
                    if vote.agreement == "direct_branch":
                        report.n_agreement_direct_branch += 1
                    elif vote.agreement != "fallback":
                        report.n_disagreement += 1
                    if vote.adjudicator is not None:
                        report.n_adjudicator += 1
                    report.retries += len(vote.retried)
                    if vote.agreement == "fallback" or not vote.resolved:
                        fallback += 1
                        continue
                    if parse_allowed(vote.value, expr.allowed) is None and vote.value is not None:
                        fallback += 1
                    elif not same_label(vote.value, cand.get("old_label")):
                        report.labels[str(vote.value)] = report.labels.get(str(vote.value), 0) + 1
                report.n_fallback += fallback
                done_chunks.add(chunk_id)
                remaining_batches = max(0, remaining_batches - 1)
                state["cursor"] += 1
                print(f"  {expr_id} classified={len(votes)} fallback={fallback}", flush=True)
                if ckpt:
                    ckpt.write_text(
                        json.dumps(
                            {
                                "per_query": report.per_query,
                                "rollbacks": report.rollbacks,
                                "n_resolved": report.n_resolved,
                                "n_fallback": report.n_fallback,
                                "n_sql_visible": report.n_sql_visible,
                                "n_materialized": report.n_materialized,
                                "tokens_spent": caller.ledger.spent,
                                "done_chunks": sorted(done_chunks),
                            },
                            default=str,
                        )
                    )
                break
    from quwarts.core.group_replay import load_group_votes

    if journal.is_file():
        policy = apply_live_group_policy(path, queries, live, load_group_votes(journal))
        report.n_attempted = int(policy.get("n_attempted") or 0)
        report.n_materialized = int(policy.get("n_materialized") or 0)
        report.n_sql_visible = int(policy.get("n_sql_visible") or 0)
        report.n_resolved = int(policy.get("n_materialized") or 0)
        report.gates["live_policy"] = LIVE_GROUP_POLICY
        report.gates["n_isolation_fail"] = int(policy.get("n_isolation_fail") or 0)
    report.tokens_spent = caller.ledger.spent
    report.tokens_direct = _purpose_tokens(caller, "group_direct")
    report.tokens_branch = _purpose_tokens(caller, "group_branch")
    report.tokens_adjudicator = _purpose_tokens(caller, "group_adjudicator")
    report.cache_hits = cache_store.hits
    report.cache_misses = cache_store.misses
    return report
