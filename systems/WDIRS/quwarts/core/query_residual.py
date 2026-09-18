"""Residual inclusion testing. Incumbent support is never replaced."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from quwarts.core.extract import find_surface_span
from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.pipeline import official_sql
from quwarts.core.query_plans import obligation_group, obligation_join, obligation_pred
from quwarts.core.query_support import (
    QueryShape,
    SupportRow,
    aprime_counts,
    aprime_support,
    clip_context,
    excluded_universe,
    grain_sql,
    query_shape,
    universe,
)
from quwarts.core.schema_columns import ensure_referenced_columns
from quwarts.core.signature import AtomicPredicate
from quwarts.core.signature_cache import CachedCaller, ResponseCache
from quwarts.core.signature_populate import ensure_signature_columns, resolve_table
from quwarts.core.signature_realize import is_membership, is_presence

STRATEGIES = ("direct", "decompose", "gleaning")
BATCH = 6

INCLUDE_PROMPT = """For each listed entity, decide whether it should be ADDED to the
existing count support. Do not list or replace a support set. Do not drop entities
that already support the query. Missing entities are unknown, not excluded.
Return JSON {"decisions":[{"entity_id":"...","include":"true|false|unknown",
"group":"...|unknown","conditions":[{"condition_id":"...","truth":"true|false|unknown",
"evidence":"..."}]}]}.
QUERY:
"""
DECOMPOSE_PROMPT = """Evaluate each listed entity against each condition independently.
Do not emit a support set. Missing entities are unknown, not excluded.
Return JSON {"decisions":[{"entity_id":"...","include":"true|false|unknown",
"group":"...|unknown","conditions":[{"condition_id":"...","truth":"true|false|unknown",
"evidence":"..."}]}]}.
QUERY:
"""
GLEANING_PROMPT = """Revise only the unknown inclusion decisions below. Same JSON schema.
Do not drop incumbent support. Missing entities stay unknown.
QUERY:
"""
CONDITION_PROMPT = """Does this one condition hold for the entity?
Return JSON {"truth":"true|false|unknown","evidence":"..."}.
CONDITION:
"""
GROUP_PROMPT = """What group key does this entity belong to for the expression?
Return JSON {"group":"...","evidence":"..."}.
EXPRESSION:
"""
JOIN_PROMPT = """Should these two entities be joined for the query?
Return JSON {"truth":"true|false|unknown","evidence":"..."}.
PAIR:
"""
INFER_A = """Using only the stated condition and context, is the condition true?
Return JSON {"truth": true|false}.
"""
INFER_B = """Ignore previous wording. From the evidence snippet, does the condition hold?
Return JSON {"truth": true|false}.
"""


@dataclass
class ConditionDecision:
    condition_id: str
    truth: str
    evidence: str = ""
    kind: str = "filter"


@dataclass
class EntityDecision:
    entity_id: str
    rowid: int
    include: str
    group: Any
    conditions: list[ConditionDecision] = field(default_factory=list)
    source: str = ""


@dataclass
class ResidualReport:
    tokens_spent: int = 0
    tokens_executor: int = 0
    tokens_refiner: int = 0
    tokens_validator: int = 0
    n_queries: int = 0
    n_proposed: int = 0
    n_added: int = 0
    n_unknown: int = 0
    n_new_groups: int = 0
    n_existing_groups: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    per_query: list[dict[str, Any]] = field(default_factory=list)


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


def decision_list(text: str) -> list[dict[str, Any]]:
    payload = _payload(text)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    items = payload.get("decisions") or payload.get("entities")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    if payload.get("entity_id"):
        return [payload]
    return []


def normalize_group(value: Any) -> str:
    if value in (None, "", "unknown"):
        return "unknown"
    if isinstance(value, dict):
        value = json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, (list, tuple)):
        value = json.dumps(list(value), default=str)
    return " ".join(str(value).casefold().split())


def query_conditions(shape: QueryShape, predicates: Iterable[AtomicPredicate]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for pred in predicates:
        if shape.query_id not in pred.query_ids:
            continue
        if pred.table and pred.table != shape.primary:
            continue
        kind = "filter"
        if is_presence(pred) or is_membership(pred) or pred.operator:
            kind = "filter"
        out.append(
            {
                "condition_id": pred.pred_id,
                "kind": kind,
                "sql": pred.bare_condition_sql or pred.condition_sql,
            }
        )
    for left, right in shape.join_pairs:
        out.append(
            {
                "condition_id": f"join:{left}:{right}",
                "kind": "join",
                "sql": f"{left} = {right}",
            }
        )
    for alias, expr in zip(shape.group_aliases, shape.group_sql):
        out.append({"condition_id": f"group:{alias}", "kind": "group", "sql": expr})
    return out


def required_ids(conditions: list[dict[str, str]]) -> list[str]:
    return [item["condition_id"] for item in conditions if item["kind"] in {"filter", "join"}]


def include_from_conditions(decisions: list[ConditionDecision], required: list[str]) -> str:
    truth = {item.condition_id: item.truth for item in decisions}
    for cond_id in required:
        value = truth.get(cond_id, "unknown")
        if value == "false":
            return "false"
        if value != "true":
            return "unknown"
    return "true"


def _relevant(entity: dict[str, Any], needle: str | None = None) -> str:
    cells = entity.get("cells")
    values = cells.values() if isinstance(cells, dict) else []
    shown = " ".join(str(value) for value in values if value not in (None, ""))
    return clip_context((entity.get("document") or "") + "\n" + shown, needle)


def _complete(caller: BudgetedCaller, prompt: str, purpose: str, **meta: Any) -> str:
    return caller.complete(prompt, purpose=purpose, **meta)


def _empty_decision(entity: dict[str, Any], source: str) -> EntityDecision:
    return EntityDecision(
        entity_id=entity["entity_id"],
        rowid=int(entity["rowid"]),
        include="unknown",
        group="unknown",
        source=source,
    )


def _from_payload(entity: dict[str, Any], payload: dict[str, Any], source: str) -> EntityDecision:
    conditions = []
    raw = payload.get("conditions") if isinstance(payload.get("conditions"), list) else []
    for item in raw:
        if not isinstance(item, dict):
            continue
        conditions.append(
            ConditionDecision(
                condition_id=str(item.get("condition_id") or ""),
                truth=_bool(item.get("truth")),
                evidence=str(item.get("evidence") or ""),
                kind=str(item.get("kind") or "filter"),
            )
        )
    return EntityDecision(
        entity_id=entity["entity_id"],
        rowid=int(entity["rowid"]),
        include=_bool(payload.get("include")),
        group=payload.get("group", "unknown"),
        conditions=conditions,
        source=source,
    )


def _entity_block(entities: list[dict[str, Any]]) -> str:
    lines = []
    for item in entities:
        lines.append(
            f"- entity_id={item['entity_id']} label={item.get('label') or ''}\n"
            f"CONTEXT:\n{_relevant(item)}\n"
        )
    return "\n".join(lines)


def _condition_block(conditions: list[dict[str, str]]) -> str:
    return "\n".join(f"- {item['condition_id']} [{item['kind']}] {item['sql']}" for item in conditions)


def _batch_decisions(
    caller: BudgetedCaller,
    prompt: str,
    purpose: str,
    plan: str,
    entities: list[dict[str, Any]],
    source: str,
) -> dict[str, EntityDecision]:
    by_id = {item["entity_id"]: item for item in entities}
    found: dict[str, EntityDecision] = {}
    for start in range(0, len(entities), BATCH):
        chunk = entities[start : start + BATCH]
        try:
            text = _complete(
                caller,
                prompt + _entity_block(chunk),
                purpose,
                system="Decide residual inclusion only. JSON only.",
                max_tokens=400,
                plan=plan,
            )
        except BudgetExhausted:
            raise
        except Exception:
            text = ""
        seen: set[str] = set()
        for payload in decision_list(text):
            entity_id = str(payload.get("entity_id") or "")
            entity = by_id.get(entity_id)
            if entity is None or entity_id in seen:
                continue
            seen.add(entity_id)
            found[entity_id] = _from_payload(entity, payload, source)
        for entity in chunk:
            if entity["entity_id"] not in found:
                found[entity["entity_id"]] = _empty_decision(entity, source)
    return found


def propose_direct(
    caller: BudgetedCaller,
    shape: QueryShape,
    entities: list[dict[str, Any]],
    conditions: list[dict[str, str]],
) -> dict[str, EntityDecision]:
    prompt = INCLUDE_PROMPT + shape.sql + "\nCONDITIONS:\n" + _condition_block(conditions) + "\nENTITIES:\n"
    return _batch_decisions(caller, prompt, "sig_executor", "residual_direct", entities, "direct")


def _apply_one_condition(
    cache: dict[str, ConditionDecision],
    caller: BudgetedCaller,
    entity: dict[str, Any],
    item: dict[str, str],
    pred: AtomicPredicate | None,
) -> ConditionDecision:
    if item["kind"] == "group":
        key = obligation_group(entity["entity_id"], item["sql"])
    elif item["kind"] == "join":
        key = obligation_join(entity["entity_id"], item["sql"], item["condition_id"])
    else:
        key = obligation_pred(entity["entity_id"], pred) if pred is not None else f"cond|{entity['entity_id']}|{item['condition_id']}"
    if key in cache:
        return cache[key]
    if pred is not None and is_presence(pred):
        cell = (entity.get("cells") or {}).get(pred.column)
        if cell not in (None, ""):
            decision = ConditionDecision(item["condition_id"], "true", str(cell), "filter")
            cache[key] = decision
            return decision
    prompt_head = GROUP_PROMPT if item["kind"] == "group" else (JOIN_PROMPT if item["kind"] == "join" else CONDITION_PROMPT)
    prompt = (
        prompt_head
        + item["sql"]
        + f"\nENTITY_LABEL: {entity.get('label') or ''}\nCONTEXT:\n{_relevant(entity, pred.literal if pred else None)}\n"
    )
    try:
        text = _complete(
            caller, prompt, "sig_executor",
            system="Evaluate one condition. JSON only.",
            max_tokens=80,
            plan="residual_decompose",
        )
    except BudgetExhausted:
        raise
    except Exception:
        text = ""
    payload = _payload(text) if isinstance(_payload(text), dict) else {}
    if item["kind"] == "group":
        group_value = payload.get("group", "unknown")
        decision = ConditionDecision(
            item["condition_id"],
            "true" if group_value not in (None, "", "unknown") else "unknown",
            str(group_value),
            "group",
        )
        cache[key] = decision
        return decision
    decision = ConditionDecision(
        item["condition_id"],
        _bool(payload.get("truth")),
        str(payload.get("evidence") or ""),
        item["kind"],
    )
    cache[key] = decision
    return decision


def propose_decompose(
    caller: BudgetedCaller,
    shape: QueryShape,
    entities: list[dict[str, Any]],
    conditions: list[dict[str, str]],
    predicates: list[AtomicPredicate],
    cache: dict[str, ConditionDecision],
    refine: bool = False,
    prior: dict[str, EntityDecision] | None = None,
) -> dict[str, EntityDecision]:
    pred_by_id = {pred.pred_id: pred for pred in predicates}
    required = required_ids(conditions)
    out: dict[str, EntityDecision] = {}
    unknown = [
        entity for entity in entities
        if prior is None or (prior.get(entity["entity_id"]) or _empty_decision(entity, "")).include == "unknown"
    ]
    if refine and unknown:
        prompt = GLEANING_PROMPT + shape.sql + "\nCONDITIONS:\n" + _condition_block(conditions) + "\nENTITIES:\n"
        refined = _batch_decisions(caller, prompt, "sig_refiner", "residual_gleaning", unknown, "gleaning")
    else:
        refined = {}
    for entity in entities:
        if refine and entity["entity_id"] in refined and refined[entity["entity_id"]].include != "unknown":
            out[entity["entity_id"]] = refined[entity["entity_id"]]
            continue
        if refine and prior is not None:
            previous = prior.get(entity["entity_id"]) or _empty_decision(entity, "decompose")
            if previous.include != "unknown":
                previous.source = "gleaning"
                out[entity["entity_id"]] = previous
                continue
            out[entity["entity_id"]] = refined.get(entity["entity_id"]) or previous
            continue
        decisions: list[ConditionDecision] = []
        group_value: Any = "unknown"
        for item in conditions:
            pred = pred_by_id.get(item["condition_id"])
            try:
                decision = _apply_one_condition(cache, caller, entity, item, pred)
            except BudgetExhausted:
                raise
            except Exception:
                decision = ConditionDecision(item["condition_id"], "unknown", "", item["kind"])
            decisions.append(decision)
            if item["kind"] == "group" and decision.evidence not in (None, "", "unknown"):
                group_value = decision.evidence
        include = include_from_conditions(decisions, required)
        out[entity["entity_id"]] = EntityDecision(
            entity_id=entity["entity_id"],
            rowid=int(entity["rowid"]),
            include=include,
            group=group_value,
            conditions=decisions,
            source="gleaning" if refine else "decompose",
        )
    return out


def proposed_union(plans: dict[str, dict[str, EntityDecision]]) -> dict[str, dict[str, EntityDecision]]:
    found: dict[str, dict[str, EntityDecision]] = {}
    for name, rows in plans.items():
        for entity_id, row in rows.items():
            if row.include != "true":
                continue
            found.setdefault(entity_id, {})[name] = row
    return found


def _span_ok(document: str, span: str | None) -> bool:
    if not span:
        return False
    return find_surface_span(document or "", span) is not None


def _judge_truth(caller: BudgetedCaller, prompt: str, grounded: bool, document: str) -> str:
    text = _complete(
        caller, prompt, "sig_validator",
        system="Answer one binary condition question. JSON only.",
        max_tokens=60,
        plan="residual_validate",
    )
    payload = _payload(text) if isinstance(_payload(text), dict) else {}
    truth = _bool(payload.get("truth"))
    if grounded:
        span = str(payload.get("evidence") or payload.get("span") or "")
        if truth == "true" and not _span_ok(document, span):
            return "unknown"
    return truth


def validate_condition(
    caller: BudgetedCaller,
    entity: dict[str, Any],
    item: dict[str, str],
    pred: AtomicPredicate | None,
    proposal: ConditionDecision | None,
) -> str:
    document = entity.get("document") or ""
    evidence = proposal.evidence if proposal else ""
    stated = _span_ok(document, evidence)
    if pred is not None and is_presence(pred):
        cell = (entity.get("cells") or {}).get(pred.column)
        if cell not in (None, ""):
            return "true"
    body = (
        f"CONDITION: {item['sql']}\nENTITY_LABEL: {entity.get('label') or ''}\n"
        f"CONTEXT:\n{_relevant(entity, pred.literal if pred else None)}\n"
    )
    if stated:
        return _judge_truth(caller, CONDITION_PROMPT + body + f"EVIDENCE_SPAN: {evidence}\n", True, document)
    first = _judge_truth(caller, INFER_A + body, False, document)
    second = _judge_truth(caller, INFER_B + body, False, document)
    if first == second and first in {"true", "false"}:
        return first
    return "unknown"


def validate_addition(
    caller: BudgetedCaller,
    entity: dict[str, Any],
    shape: QueryShape,
    conditions: list[dict[str, str]],
    predicates: list[AtomicPredicate],
    proposals: dict[str, EntityDecision],
    incumbent_groups: set[str],
) -> EntityDecision | None:
    pred_by_id = {pred.pred_id: pred for pred in predicates}
    required = required_ids(conditions)
    merged_conditions: list[ConditionDecision] = []
    nonempty = [
        normalize_group(row.group)
        for row in proposals.values()
        if normalize_group(row.group) != "unknown"
    ]
    incumbent_hits = [item for item in nonempty if item in incumbent_groups]
    if incumbent_hits:
        group = incumbent_hits[0]
        new_group = False
    else:
        unique = list(dict.fromkeys(nonempty))
        if len(unique) == 1:
            group = unique[0]
            new_group = bool(shape.group_aliases)
        elif not unique and not shape.group_aliases:
            group = ""
            new_group = False
        else:
            return None
    if new_group:
        agreeing = [
            name for name, row in proposals.items()
            if row.include == "true" and normalize_group(row.group) == group
        ]
        if len(agreeing) < 2:
            return None
    by_cond: dict[str, ConditionDecision] = {}
    for row in proposals.values():
        for item in row.conditions:
            by_cond.setdefault(item.condition_id, item)
    for item in conditions:
        if item["kind"] == "group":
            continue
        try:
            truth = validate_condition(
                caller, entity, item, pred_by_id.get(item["condition_id"]), by_cond.get(item["condition_id"]),
            )
        except BudgetExhausted:
            raise
        except Exception:
            truth = "unknown"
        merged_conditions.append(ConditionDecision(item["condition_id"], truth, "", item["kind"]))
        if item["condition_id"] in required and truth != "true":
            return None
    if include_from_conditions(merged_conditions, required) != "true":
        return None
    if shape.group_aliases and group == "unknown":
        return None
    return EntityDecision(
        entity_id=entity["entity_id"],
        rowid=int(entity["rowid"]),
        include="true",
        group=group,
        conditions=merged_conditions,
        source="validated",
    )


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _group_token(row: SupportRow, shape: QueryShape) -> str:
    if not shape.group_aliases:
        return ""
    if len(shape.group_aliases) == 1:
        return normalize_group(row.group_key.get(shape.group_aliases[0]))
    return normalize_group([row.group_key.get(name) for name in shape.group_aliases])


def _write_true_flags(
    conn: sqlite3.Connection,
    table: str,
    rowid: int,
    predicates: list[AtomicPredicate],
    accepted: set[str],
    incumbent_rowids: set[int],
) -> None:
    if rowid in incumbent_rowids:
        return
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({_quote(table)})")}
    for pred in predicates:
        if pred.pred_id not in accepted:
            continue
        if pred.sig_name not in cols or pred.resolved_name not in cols:
            continue
        conn.execute(
            f"UPDATE {_quote(table)} SET {_quote(pred.sig_name)} = 1, {_quote(pred.resolved_name)} = 1 "
            f"WHERE rowid = ?",
            [rowid],
        )


def _maybe_write_group(
    conn: sqlite3.Connection,
    table: str,
    rowid: int,
    shape: QueryShape,
    group: Any,
    incumbent_rowids: set[int],
) -> None:
    if rowid in incumbent_rowids or group in (None, "", "unknown"):
        return
    if len(shape.group_sql) != 1:
        return
    bare = shape.group_sql[0].strip().strip('"').split(".")[-1]
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({_quote(table)})")}
    if bare not in cols or "(" in shape.group_sql[0]:
        return
    conn.execute(
        f"UPDATE {_quote(table)} SET {_quote(bare)} = ? "
        f"WHERE rowid = ? AND ({_quote(bare)} IS NULL OR {_quote(bare)} = '')",
        [str(group), rowid],
    )


def _grain_rowids(conn: sqlite3.Connection, sql: str, alias: str) -> set[int]:
    try:
        cur = conn.execute(sql)
    except sqlite3.Error:
        return set()
    cols = [item[0] for item in cur.description] if cur.description else []
    key = f"{alias}__rid"
    if key not in cols:
        return set()
    index = cols.index(key)
    found = set()
    for row in cur.fetchall():
        try:
            found.add(int(row[index] or 0))
        except (TypeError, ValueError):
            continue
    return found


def apply_addition(
    conn: sqlite3.Connection,
    sqlite_path: str | Path,
    entity: dict[str, Any],
    decision: EntityDecision,
    shape: QueryShape,
    predicates: list[AtomicPredicate],
    incumbent_rowids: set[int],
) -> bool:
    if decision.rowid in incumbent_rowids or decision.include != "true":
        return False
    names = {
        row[0].lower(): row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    table = names.get(shape.primary.lower())
    if table is None and predicates:
        table = resolve_table(conn, predicates[0])
    table = table or shape.primary
    accepted = {item.condition_id for item in decision.conditions if item.truth == "true" and item.kind == "filter"}
    grain = official_sql(grain_sql(shape.sql), sqlite_path, predicates)
    before = _grain_rowids(conn, grain, shape.primary_alias)
    conn.execute("SAVEPOINT residual_add")
    try:
        _write_true_flags(conn, table, decision.rowid, predicates, accepted, incumbent_rowids)
        _maybe_write_group(conn, table, decision.rowid, shape, decision.group, incumbent_rowids)
        conn.execute(official_sql(shape.sql, sqlite_path, predicates))
        after = _grain_rowids(conn, grain, shape.primary_alias)
        if before - after:
            raise sqlite3.Error("incumbent support dropped")
        if decision.rowid not in after:
            raise sqlite3.Error("addition did not appear")
        conn.execute("RELEASE residual_add")
        return True
    except sqlite3.Error:
        conn.execute("ROLLBACK TO residual_add")
        conn.execute("RELEASE residual_add")
        return False


def is_count_query(shape: QueryShape) -> bool:
    return any(kind.startswith("count") for _alias, kind in shape.aggregates)


def prioritize_queries(
    queries: list[dict[str, str]],
    sqlite_path: str | Path,
    predicates: list[AtomicPredicate],
    documents: dict[str, str] | None,
) -> list[tuple[dict[str, str], QueryShape, list[SupportRow], list[dict[str, Any]], list[dict[str, Any]]]]:
    ranked = []
    for row in queries:
        shape = query_shape(row["query_id"], row["sql"])
        if not is_count_query(shape):
            continue
        entities = universe(sqlite_path, shape, documents)
        rid_map = {item["rowid"]: item["entity_id"] for item in entities}
        support = aprime_support(sqlite_path, shape, predicates, rid_map)
        excluded = excluded_universe(entities, support)
        ranked.append((0 if support else 1, len(excluded), row, shape, support, entities, excluded))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]["query_id"]))
    return [(row, shape, support, entities, excluded) for _e, _n, row, shape, support, entities, excluded in ranked]


def run_residual_arm(
    sqlite_path: str | Path,
    queries: list[dict[str, str]],
    predicates: Iterable[AtomicPredicate],
    *,
    documents: dict[str, str] | None = None,
    caller: BudgetedCaller | None = None,
    statements: dict[str, str] | None = None,
    checkpoint: str | Path | None = None,
) -> ResidualReport:
    live = list(predicates)
    report = ResidualReport()
    cache_store = ResponseCache()
    cond_cache: dict[str, ConditionDecision] = {}
    path = Path(sqlite_path)
    conn = sqlite3.connect(str(path))
    try:
        ensure_referenced_columns(conn, statements or {row["query_id"]: row["sql"] for row in queries})
        ensure_signature_columns(conn, live)
        conn.commit()
        if statements:
            from quwarts.core.schema_columns import assert_queries_execute

            rewritten = {row["query_id"]: official_sql(row["sql"], path, live) for row in queries}
            rewritten.update(
                {qid: official_sql(sql, path, live) for qid, sql in statements.items() if qid not in rewritten}
            )
            assert_queries_execute(conn, rewritten)
    finally:
        conn.close()
    if caller is None:
        return report
    bound = CachedCaller(caller, cache_store, plan="residual")
    ranked = prioritize_queries(queries, path, live, documents)
    done: set[str] = set()
    ckpt = Path(checkpoint) if checkpoint else None
    if ckpt and ckpt.is_file():
        saved = json.loads(ckpt.read_text())
        report.per_query.extend(saved.get("per_query") or [])
        report.n_queries = int(saved.get("n_queries") or 0)
        report.n_added = int(saved.get("n_added") or 0)
        report.n_proposed = int(saved.get("n_proposed") or 0)
        done = {item["query_id"] for item in report.per_query}
        print(f"resume {len(done)} residual queries from {ckpt}", flush=True)
    for row, shape, support, entities, excluded in ranked:
        if shape.query_id in done:
            continue
        if caller.ledger.remaining() <= 0:
            break
        print(
            f"residual {shape.query_id} excluded={len(excluded)} remaining={caller.ledger.remaining()}",
            flush=True,
        )
        report.n_queries += 1
        conditions = query_conditions(shape, live)
        incumbent_rowids = {item.rowid for item in support if item.included == "true"}
        incumbent_groups = {_group_token(item, shape) for item in support if item.included == "true"}
        by_entity = {item["entity_id"]: item for item in entities}
        added = 0
        proposed = 0
        unknown = 0
        new_groups = 0
        existing_groups = 0
        try:
            plans = {
                "direct": propose_direct(bound, shape, excluded, conditions),
                "decompose": propose_decompose(bound, shape, excluded, conditions, live, cond_cache),
            }
            plans["gleaning"] = propose_decompose(
                bound, shape, excluded, conditions, live, cond_cache, refine=True, prior=plans["decompose"],
            )
            union = proposed_union(plans)
            proposed = len(union)
            conn = sqlite3.connect(str(path))
            try:
                for entity_id, proposals in union.items():
                    entity = by_entity.get(entity_id)
                    if entity is None:
                        continue
                    try:
                        accepted = validate_addition(
                            bound, entity, shape, conditions, live, proposals, incumbent_groups,
                        )
                    except BudgetExhausted:
                        raise
                    except Exception:
                        accepted = None
                    if accepted is None:
                        unknown += 1
                        continue
                    token = normalize_group(accepted.group) if shape.group_aliases else ""
                    is_new = bool(shape.group_aliases) and token not in incumbent_groups and token != "unknown"
                    if apply_addition(conn, path, entity, accepted, shape, live, incumbent_rowids):
                        added += 1
                        if is_new:
                            new_groups += 1
                            incumbent_groups.add(token)
                        else:
                            existing_groups += 1
                conn.commit()
            finally:
                conn.close()
        except BudgetExhausted:
            print(f"  budget exhausted at {shape.query_id}", flush=True)
        except Exception as exc:
            print(f"  residual error {shape.query_id}: {exc}", flush=True)
        report.n_proposed += proposed
        report.n_added += added
        report.n_unknown += unknown
        report.n_new_groups += new_groups
        report.n_existing_groups += existing_groups
        report.per_query.append(
            {
                "query_id": shape.query_id,
                "n_excluded": len(excluded),
                "n_proposed": proposed,
                "n_added": added,
                "n_unknown": unknown,
                "n_new_groups": new_groups,
                "n_existing_groups": existing_groups,
                "incumbent_n": len(incumbent_rowids),
            }
        )
        print(f"  proposed={proposed} added={added}", flush=True)
        if ckpt:
            ckpt.parent.mkdir(parents=True, exist_ok=True)
            ckpt.write_text(
                json.dumps(
                    {
                        "per_query": report.per_query,
                        "n_queries": report.n_queries,
                        "n_added": report.n_added,
                        "n_proposed": report.n_proposed,
                    },
                    default=str,
                )
            )
    report.tokens_spent = caller.ledger.spent
    report.tokens_executor = sum(rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_executor")
    report.tokens_refiner = sum(rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_refiner")
    report.tokens_validator = sum(rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_validator")
    report.cache_hits = cache_store.hits
    report.cache_misses = cache_store.misses
    return report


def residual_counts(
    sqlite_path: str | Path,
    sql: str,
    predicates: Iterable[AtomicPredicate] | None = None,
) -> list[dict[str, Any]]:
    return aprime_counts(sqlite_path, sql, predicates)
