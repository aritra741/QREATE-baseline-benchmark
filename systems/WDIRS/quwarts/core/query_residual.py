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
    query_shape,
    universe,
)
from quwarts.core.query_witness import (
    WitnessSpec,
    compile_witness_spec,
    grain_sql_for,
    group_token,
    make_witness_key,
    occupancy_key,
    support_from_grain,
    witness_key_of,
)
from quwarts.core.schema_columns import ensure_referenced_columns
from quwarts.core.signature import AtomicPredicate
from quwarts.core.signature_cache import CachedCaller, ResponseCache
from quwarts.core.signature_populate import ensure_signature_columns, resolve_table
from quwarts.core.signature_realize import is_membership, is_presence
from quwarts.core.signature_views import (
    add_edge,
    ensure_edge_table,
    ensure_group_columns,
    related_canonicals,
    snapshot_edges,
    write_group,
)

STRATEGIES = ("direct", "decompose", "gleaning")
BATCH = 6

INCLUDE_PROMPT = """For each listed witness, decide whether it should be ADDED to the
existing count support. Do not list or replace a support set. Do not drop witnesses
that already support the query. Missing witnesses are unknown, not excluded.
Return JSON {"decisions":[{"witness_id":"...","entity_id":"...","include":"true|false|unknown",
"group":"...|unknown","join_partners":[],"conditions":[{"condition_id":"...","truth":"true|false|unknown",
"evidence":"..."}]}]}.
QUERY:
"""
DECOMPOSE_PROMPT = """Evaluate each listed witness against each condition independently.
Do not emit a support set. Missing witnesses are unknown, not excluded.
Return JSON {"decisions":[{"witness_id":"...","entity_id":"...","include":"true|false|unknown",
"group":"...|unknown","join_partners":[],"conditions":[{"condition_id":"...","truth":"true|false|unknown",
"evidence":"..."}]}]}.
QUERY:
"""
GLEANING_PROMPT = """Revise only the unknown inclusion decisions below. Same JSON schema.
Do not drop incumbent support. Missing witnesses stay unknown.
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
    witness_id: str = ""
    witness_key: tuple = ()
    rowids: dict[str, int] = field(default_factory=dict)
    join_partners: tuple[str, ...] = ()


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
    spec = compile_witness_spec(shape.query_id, shape.sql, shape)
    for join in spec.joins:
        out.append(
            {
                "condition_id": f"join:{join.join_id}",
                "kind": "join",
                "sql": join.on_sql,
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
        witness_id=str(entity.get("witness_id") or entity["entity_id"]),
        witness_key=tuple(entity.get("witness_key") or ()),
        rowids=dict(entity.get("rowids") or {}),
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
    partners = payload.get("join_partners") if isinstance(payload.get("join_partners"), list) else []
    return EntityDecision(
        entity_id=entity["entity_id"],
        rowid=int(entity["rowid"]),
        include=_bool(payload.get("include")),
        group=payload.get("group", "unknown"),
        conditions=conditions,
        source=source,
        witness_id=str(payload.get("witness_id") or entity.get("witness_id") or entity["entity_id"]),
        witness_key=tuple(entity.get("witness_key") or ()),
        rowids=dict(entity.get("rowids") or {}),
        join_partners=tuple(str(item) for item in partners),
    )


def _entity_block(entities: list[dict[str, Any]]) -> str:
    lines = []
    for item in entities:
        lines.append(
            f"- witness_id={item.get('witness_id') or item['entity_id']} "
            f"entity_id={item['entity_id']} label={item.get('label') or ''}\n"
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
    by_id: dict[str, dict[str, Any]] = {}
    for item in entities:
        by_id[item["entity_id"]] = item
        if item.get("witness_id"):
            by_id[str(item["witness_id"])] = item
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
            entity_id = str(payload.get("witness_id") or payload.get("entity_id") or "")
            entity = by_id.get(entity_id)
            if entity is None or entity_id in seen:
                continue
            seen.add(entity_id)
            key = str(entity.get("witness_id") or entity["entity_id"])
            found[key] = _from_payload(entity, payload, source)
        for entity in chunk:
            key = str(entity.get("witness_id") or entity["entity_id"])
            if key not in found:
                found[key] = _empty_decision(entity, source)
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
            key = row.witness_id or entity_id
            found.setdefault(key, {})[name] = row
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
    sample = next(iter(proposals.values()))
    return EntityDecision(
        entity_id=entity["entity_id"],
        rowid=int(entity["rowid"]),
        include="true",
        group=group,
        conditions=merged_conditions,
        source="validated",
        witness_id=str(entity.get("witness_id") or sample.witness_id or entity["entity_id"]),
        witness_key=tuple(entity.get("witness_key") or sample.witness_key or ()),
        rowids=dict(entity.get("rowids") or sample.rowids or {}),
        join_partners=sample.join_partners,
    )


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


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


def is_count_query(shape: QueryShape) -> bool:
    return any(kind.startswith("count") for _alias, kind in shape.aggregates)


def _bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(key), json.dumps(row.get(key), default=str)) for key in row)))
    return tuple(sorted(frozen))


def query_bags(
    sqlite_path: str | Path,
    statements: dict[str, str],
    predicates: list[AtomicPredicate],
    conn: sqlite3.Connection | None = None,
) -> dict[str, tuple]:
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


def count_mass(sqlite_path: str | Path, sql: str, predicates: list[AtomicPredicate]) -> int:
    rows = aprime_counts(sqlite_path, sql, predicates)
    total = 0
    for row in rows:
        for key, value in row.items():
            if str(key).lower().endswith("count") and value not in (None, ""):
                try:
                    total += int(value)
                except (TypeError, ValueError):
                    continue
    return total


def current_support(
    sqlite_path: str | Path,
    spec: WitnessSpec,
    predicates: list[AtomicPredicate],
    rid_to_entity: dict[int, str] | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[SupportRow]:
    own = conn is None
    if own:
        conn = sqlite3.connect(str(sqlite_path))
    try:
        sql = official_sql(grain_sql_for(spec), sqlite_path, predicates)
        cur = conn.execute(sql)
        cols = [item[0] for item in cur.description] if cur.description else []
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    except sqlite3.Error:
        rows = []
    finally:
        if own:
            conn.close()
    return support_from_grain(spec, rows, rid_to_entity)


def _table_rows(
    sqlite_path: str | Path,
    table: str,
    documents: dict[str, str] | None,
) -> list[dict[str, Any]]:
    shape = QueryShape(
        query_id="",
        sql=f'SELECT COUNT(*) FROM "{table}"',
        tables=(table,),
        aliases={table: table},
        primary=table,
        primary_alias=table,
        group_aliases=(),
        group_sql=(),
        aggregates=(("n", "count"),),
        join_pairs=(),
    )
    return universe(sqlite_path, shape, documents)


def excluded_candidates(
    sqlite_path: str | Path,
    spec: WitnessSpec,
    support: list[SupportRow],
    documents: dict[str, str] | None,
) -> list[dict[str, Any]]:
    kept = {
        occupancy_key(row.rowids or {spec.primary: row.rowid}, row.distinct_value, row.entity_id)
        for row in support
        if row.included == "true"
    }
    incumbent_primary = {row.rowid for row in support if row.included == "true"}
    primary_rows = _table_rows(sqlite_path, spec.primary, documents)
    out: list[dict[str, Any]] = []
    if spec.joins:
        join = spec.joins[0]
        left_rows = _table_rows(sqlite_path, join.left_table, documents)
        right_rows = _table_rows(sqlite_path, join.right_table, documents)
        for left in left_rows:
            for right in right_rows:
                rowids = {join.left_table: left["rowid"], join.right_table: right["rowid"]}
                primary = left if spec.primary == join.left_table else right
                other = right if primary is left else left
                key = make_witness_key(
                    spec,
                    rowids,
                    distinct_value=primary.get("entity_id"),
                    group_key={},
                )
                if occupancy_key(rowids, primary.get("entity_id")) in kept:
                    continue
                witness_id = f"{primary['entity_id']}|{other['entity_id']}|{left['rowid']}|{right['rowid']}"
                cells = dict(primary.get("cells") or {})
                cells.update({f"{other['table']}.{k}": v for k, v in (other.get("cells") or {}).items()})
                out.append(
                    {
                        "witness_id": witness_id,
                        "witness_key": key,
                        "entity_id": primary["entity_id"],
                        "rowid": primary["rowid"],
                        "rowids": rowids,
                        "label": f"{primary.get('label') or ''} / {other.get('label') or ''}",
                        "table": spec.primary,
                        "cells": cells,
                        "document": (primary.get("document") or "") + "\n" + (other.get("document") or ""),
                        "priority": 0 if primary["rowid"] not in incumbent_primary else 1,
                    }
                )
    else:
        for item in primary_rows:
            rowids = {spec.primary: item["rowid"]}
            key = make_witness_key(spec, rowids, distinct_value=item.get("entity_id"), group_key={})
            if occupancy_key(rowids, item.get("entity_id")) in kept:
                continue
            row = dict(item)
            row["witness_id"] = item["entity_id"]
            row["witness_key"] = key
            row["rowids"] = rowids
            row["priority"] = 0
            out.append(row)
    out.sort(key=lambda item: (item.get("priority") or 0, str(item.get("witness_id"))))
    return out


def apply_addition(
    conn: sqlite3.Connection,
    sqlite_path: str | Path,
    entity: dict[str, Any],
    decision: EntityDecision,
    shape: QueryShape,
    predicates: list[AtomicPredicate],
    incumbent_rowids: set[int],
    spec: WitnessSpec | None = None,
) -> bool:
    spec = spec or compile_witness_spec(shape.query_id, shape.sql, shape)
    if decision.include != "true":
        return False
    if decision.rowid in incumbent_rowids:
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
    before = current_support(sqlite_path, spec, predicates, conn=conn)
    before_keys = {witness_key_of(row) for row in before}
    before_groups = {row.rowid: dict(row.group_key) for row in before}
    before_edges = snapshot_edges(conn)
    conn.execute("SAVEPOINT residual_add")
    try:
        _write_true_flags(conn, table, decision.rowid, predicates, accepted, incumbent_rowids)
        if spec.group_sql:
            write_group(conn, table, decision.rowid, spec.group_sql[0], decision.group, incumbent_rowids)
        for join in spec.joins:
            rowids = decision.rowids or entity.get("rowids") or {}
            left_rid = int(rowids.get(join.left_table) or 0)
            right_rid = int(rowids.get(join.right_table) or 0)
            if left_rid and right_rid:
                add_edge(conn, join.join_id, left_rid, right_rid, provenance=spec.query_id)
        conn.execute(official_sql(shape.sql, sqlite_path, predicates))
        after = current_support(sqlite_path, spec, predicates, conn=conn)
        after_keys = {witness_key_of(row) for row in after}
        if before_keys - after_keys:
            raise sqlite3.Error("incumbent support dropped")
        for row in after:
            if row.rowid in before_groups and row.group_key != before_groups[row.rowid]:
                raise sqlite3.Error("incumbent group reassigned")
        if snapshot_edges(conn) < before_edges:
            raise sqlite3.Error("incumbent join edge removed")
        intended = decision.witness_key or make_witness_key(
            spec,
            decision.rowids or {spec.primary: decision.rowid},
            distinct_value=entity.get("entity_id"),
            group_key={spec.group_aliases[0]: decision.group} if spec.group_aliases else {},
        )
        visible = intended in after_keys or any(
            row.rowid == decision.rowid and row.included == "true" for row in after
        )
        if not visible:
            raise sqlite3.Error("addition did not appear")
        conn.execute("RELEASE residual_add")
        return True
    except sqlite3.Error:
        conn.execute("ROLLBACK TO residual_add")
        conn.execute("RELEASE residual_add")
        return False


def is_related(query_id: str, sql: str, predicates: list[AtomicPredicate], updated: set[str]) -> bool:
    spec = compile_witness_spec(query_id, sql)
    return bool(related_canonicals(spec, predicates) & updated)


def prioritize_queries(
    queries: list[dict[str, str]],
    sqlite_path: str | Path,
    predicates: list[AtomicPredicate],
    documents: dict[str, str] | None,
) -> list[tuple[dict[str, str], QueryShape, WitnessSpec, list[SupportRow], list[dict[str, Any]]]]:
    ranked = []
    for row in queries:
        shape = query_shape(row["query_id"], row["sql"])
        if not is_count_query(shape):
            continue
        spec = compile_witness_spec(row["query_id"], row["sql"], shape)
        entities = universe(sqlite_path, shape, documents)
        rid_map = {item["rowid"]: item["entity_id"] for item in entities}
        support = aprime_support(sqlite_path, shape, predicates, rid_map)
        excluded = excluded_candidates(sqlite_path, spec, support, documents)
        ranked.append((0 if support else 1, len(excluded), row, shape, spec, support, excluded))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]["query_id"]))
    return [(row, shape, spec, support, excluded) for _e, _n, row, shape, spec, support, excluded in ranked]


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
    all_statements = statements or {row["query_id"]: row["sql"] for row in queries}
    specs = [compile_witness_spec(qid, sql) for qid, sql in all_statements.items()]
    conn = sqlite3.connect(str(path))
    try:
        ensure_referenced_columns(conn, all_statements)
        ensure_signature_columns(conn, live)
        ensure_edge_table(conn)
        ensure_group_columns(conn, specs)
        conn.commit()
        from quwarts.core.schema_columns import assert_queries_execute

        rewritten = {qid: official_sql(sql, path, live) for qid, sql in all_statements.items()}
        assert_queries_execute(conn, rewritten)
    finally:
        conn.close()
    if caller is None:
        return report
    bound = CachedCaller(caller, cache_store, plan="residual")
    ranked = prioritize_queries(queries, path, live, documents)
    bags = query_bags(path, all_statements, live)
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
    for row, shape, spec, support, excluded in ranked:
        if shape.query_id in done:
            continue
        if caller.ledger.remaining() <= 0:
            break
        spent_before = caller.ledger.spent
        mass_before = count_mass(path, shape.sql, live)
        print(
            f"residual {shape.query_id} kind={spec.kind} excluded={len(excluded)} remaining={caller.ledger.remaining()}",
            flush=True,
        )
        report.n_queries += 1
        conditions = query_conditions(shape, live)
        incumbent_rowids = {item.rowid for item in support if item.included == "true"}
        incumbent_groups = {group_token(item, spec) for item in support if item.included == "true"}
        by_id = {item.get("witness_id") or item["entity_id"]: item for item in excluded}
        by_id.update({item["entity_id"]: item for item in excluded})
        added = 0
        proposed = 0
        unknown = 0
        new_groups = 0
        existing_groups = 0
        materialized = 0
        sql_visible = 0
        ineffective = 0
        edges_added = 0
        groups_added = 0
        updated: set[str] = set()
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
                conn.execute("SAVEPOINT residual_cohort")
                for entity_id, proposals in union.items():
                    entity = by_id.get(entity_id)
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
                    token = normalize_group(accepted.group) if spec.group_aliases else ""
                    is_new = bool(spec.group_aliases) and token not in incumbent_groups and token != "unknown"
                    ok = apply_addition(
                        conn, path, entity, accepted, shape, live, incumbent_rowids, spec=spec,
                    )
                    if not ok:
                        ineffective += 1
                        print(f"  ineffective {entity_id}", flush=True)
                        continue
                    added += 1
                    materialized += 1
                    sql_visible += 1
                    if spec.joins:
                        edges_added += 1
                    if spec.group_sql:
                        groups_added += 1
                    if is_new:
                        new_groups += 1
                        incumbent_groups.add(token)
                    else:
                        existing_groups += 1
                    updated |= related_canonicals(spec, live)
                after_bags = query_bags(path, all_statements, live, conn=conn)
                interference = []
                for qid, before in bags.items():
                    if after_bags.get(qid) == before:
                        continue
                    sql = all_statements[qid]
                    if not is_related(qid, sql, live, updated):
                        interference.append(qid)
                if interference:
                    conn.execute("ROLLBACK TO residual_cohort")
                    print(f"  rolled back cohort; unrelated bags moved: {interference}", flush=True)
                    added = materialized = sql_visible = new_groups = existing_groups = edges_added = groups_added = 0
                else:
                    conn.execute("RELEASE residual_cohort")
                    bags = after_bags
                conn.commit()
            finally:
                conn.close()
        except BudgetExhausted:
            print(f"  budget exhausted at {shape.query_id}", flush=True)
        except Exception as exc:
            print(f"  residual error {shape.query_id}: {exc}", flush=True)
        mass_after = count_mass(path, shape.sql, live)
        report.n_proposed += proposed
        report.n_added += added
        report.n_unknown += unknown
        report.n_new_groups += new_groups
        report.n_existing_groups += existing_groups
        report.per_query.append(
            {
                "query_id": shape.query_id,
                "witness_type": spec.kind,
                "incumbent_witnesses": len(support),
                "excluded_universe": len(excluded),
                "n_proposed": proposed,
                "n_validated": proposed - unknown,
                "n_materialized": materialized,
                "n_sql_visible": sql_visible,
                "n_ineffective": ineffective,
                "n_added": added,
                "n_unknown": unknown,
                "n_new_groups": new_groups,
                "n_existing_groups": existing_groups,
                "join_edges_added": edges_added,
                "groups_added": groups_added,
                "count_mass_before": mass_before,
                "count_mass_after": mass_after,
                "tokens": caller.ledger.spent - spent_before,
                "incumbent_n": len(incumbent_rowids),
            }
        )
        print(f"  proposed={proposed} added={added} ineffective={ineffective}", flush=True)
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
