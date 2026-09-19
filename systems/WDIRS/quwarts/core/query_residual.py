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
    group_owner_table,
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
from quwarts.core.join_block import (
    PER_LEFT_CAP,
    PER_QUERY_CAP,
    BlockStats,
    CandidateSet,
    block_join_pairs,
    pair_candidate,
)
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
CANDIDATE_BATCH = 6
EST_TOKENS_PER_CALL = 350

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
    n_validated: int = 0
    n_materialized: int = 0
    n_sql_visible: int = 0
    n_base_row: int = 0
    n_join_edge: int = 0
    n_distinct: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    rollbacks: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    blocking: list[dict[str, Any]] = field(default_factory=list)
    gates: dict[str, Any] = field(default_factory=dict)
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
            return found
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
    def _key(entity: dict[str, Any]) -> str:
        return str(entity.get("witness_id") or entity["entity_id"])

    unknown = [
        entity for entity in entities
        if prior is None or (prior.get(_key(entity)) or _empty_decision(entity, "")).include == "unknown"
    ]
    if refine and unknown:
        prompt = GLEANING_PROMPT + shape.sql + "\nCONDITIONS:\n" + _condition_block(conditions) + "\nENTITIES:\n"
        refined = _batch_decisions(caller, prompt, "sig_refiner", "residual_gleaning", unknown, "gleaning")
    else:
        refined = {}
    for entity in entities:
        key = _key(entity)
        if refine and key in refined and refined[key].include != "unknown":
            out[key] = refined[key]
            continue
        if refine and prior is not None:
            previous = prior.get(key) or _empty_decision(entity, "decompose")
            if previous.include != "unknown":
                previous.source = "gleaning"
                out[key] = previous
                continue
            out[key] = refined.get(key) or previous
            continue
        decisions: list[ConditionDecision] = []
        group_value: Any = "unknown"
        for item in conditions:
            pred = pred_by_id.get(item["condition_id"])
            try:
                decision = _apply_one_condition(cache, caller, entity, item, pred)
            except BudgetExhausted:
                return out
            except Exception:
                decision = ConditionDecision(item["condition_id"], "unknown", "", item["kind"])
            decisions.append(decision)
            if item["kind"] == "group" and decision.evidence not in (None, "", "unknown"):
                group_value = decision.evidence
        include = include_from_conditions(decisions, required)
        out[key] = EntityDecision(
            entity_id=entity["entity_id"],
            rowid=int(entity["rowid"]),
            include=include,
            group=group_value,
            conditions=decisions,
            source="gleaning" if refine else "decompose",
            witness_id=key,
            witness_key=tuple(entity.get("witness_key") or ()),
            rowids=dict(entity.get("rowids") or {}),
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
    *,
    per_left: int = PER_LEFT_CAP,
    per_query: int = PER_QUERY_CAP,
) -> CandidateSet:
    kept = {
        occupancy_key(row.rowids or {spec.primary: row.rowid}, row.distinct_value, row.entity_id)
        for row in support
        if row.included == "true"
    }
    incumbent_primary = {row.rowid for row in support if row.included == "true"}
    primary_rows = _table_rows(sqlite_path, spec.primary, documents)
    if spec.joins:
        join = spec.joins[0]
        left_rows = _table_rows(sqlite_path, join.left_table, documents)
        right_rows = _table_rows(sqlite_path, join.right_table, documents)
        cartesian = len(left_rows) * len(right_rows)
        pairs, skip_reason, signal = block_join_pairs(
            left_rows, right_rows, join, per_left=per_left, per_query=per_query,
        )
        out: list[dict[str, Any]] = []
        for left, right, _source in pairs:
            row = pair_candidate(spec, join, left, right, kept, incumbent_primary)
            if row is not None:
                out.append(row)
        out.sort(key=lambda item: (item.get("priority") or 0, str(item.get("witness_id"))))
        return CandidateSet(
            rows=out,
            stats=BlockStats(
                query_id=spec.query_id,
                cartesian=cartesian,
                blocked=len(out),
                skip_reason=skip_reason,
                per_left_cap=per_left,
                per_query_cap=per_query,
                signal=signal,
            ),
        )
    out = []
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
    if len(out) > per_query:
        out = out[:per_query]
    return CandidateSet(
        rows=out,
        stats=BlockStats(
            query_id=spec.query_id,
            cartesian=len(primary_rows),
            blocked=len(out),
            signal="row",
        ),
    )


def apply_addition(
    conn: sqlite3.Connection,
    sqlite_path: str | Path,
    entity: dict[str, Any],
    decision: EntityDecision,
    shape: QueryShape,
    predicates: list[AtomicPredicate],
    incumbent_rowids: set[int],
    spec: WitnessSpec | None = None,
    reasons: list[str] | None = None,
) -> bool:
    spec = spec or compile_witness_spec(shape.query_id, shape.sql, shape)
    if decision.include != "true":
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
    occupied = {
        occupancy_key(row.rowids or {spec.primary: row.rowid}, row.distinct_value, row.entity_id)
        for row in before
        if row.included == "true"
    }
    intended_occ = occupancy_key(
        decision.rowids or entity.get("rowids") or {spec.primary: decision.rowid},
        entity.get("entity_id"),
    )
    if intended_occ in occupied and not spec.joins:
        return False
    if not spec.joins and decision.rowid in incumbent_rowids:
        return False
    before_groups = {row.rowid: dict(row.group_key) for row in before}
    before_edges = snapshot_edges(conn)
    conn.execute("SAVEPOINT residual_add")
    try:
        _write_true_flags(conn, table, decision.rowid, predicates, accepted, incumbent_rowids)
        if spec.group_sql and decision.group not in (None, "", "unknown"):
            owner = group_owner_table(spec.group_sql[0], spec)
            if owner is None:
                raise sqlite3.Error("multi-relation group fail-closed")
            owner_table = names.get(owner.lower()) or owner
            owner_rid = int((decision.rowids or entity.get("rowids") or {}).get(owner) or decision.rowid)
            write_group(conn, owner_table, owner_rid, spec.group_sql[0], decision.group, incumbent_rowids)
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
    except sqlite3.Error as exc:
        if reasons is not None:
            reasons.append(str(exc))
        conn.execute("ROLLBACK TO residual_add")
        conn.execute("RELEASE residual_add")
        return False


def is_related(query_id: str, sql: str, predicates: list[AtomicPredicate], updated: set[str]) -> bool:
    spec = compile_witness_spec(query_id, sql)
    return bool(related_canonicals(spec, predicates) & updated)


def estimate_batch_tokens(n_entities: int, n_conditions: int) -> int:
    if n_entities <= 0:
        return 0
    direct = 1
    decompose = max(1, n_conditions) * n_entities
    gleaning = 1
    validate = n_entities * (n_conditions + 2)
    return (direct + decompose + gleaning + validate) * EST_TOKENS_PER_CALL


def prioritize_queries(
    queries: list[dict[str, str]],
    sqlite_path: str | Path,
    predicates: list[AtomicPredicate],
    documents: dict[str, str] | None,
) -> list[tuple[dict[str, str], QueryShape, WitnessSpec, list[SupportRow], CandidateSet]]:
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
        n = len(excluded.rows)
        ranked.append((0 if support else 1, n, row, shape, spec, support, excluded))
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
    ckpt = Path(checkpoint) if checkpoint else None
    done_chunks: set[str] = set()
    if ckpt and ckpt.is_file():
        saved = json.loads(ckpt.read_text())
        report.per_query = list(saved.get("per_query") or [])
        report.skipped = list(saved.get("skipped") or [])
        report.blocking = list(saved.get("blocking") or [])
        report.rollbacks = list(saved.get("rollbacks") or [])
        report.n_queries = int(saved.get("n_queries") or 0)
        report.n_added = int(saved.get("n_added") or 0)
        report.n_proposed = int(saved.get("n_proposed") or 0)
        report.n_validated = int(saved.get("n_validated") or 0)
        report.n_materialized = int(saved.get("n_materialized") or 0)
        report.n_sql_visible = int(saved.get("n_sql_visible") or 0)
        report.n_base_row = int(saved.get("n_base_row") or 0)
        report.n_join_edge = int(saved.get("n_join_edge") or 0)
        report.n_distinct = int(saved.get("n_distinct") or 0)
        report.n_new_groups = int(saved.get("n_new_groups") or 0)
        report.n_existing_groups = int(saved.get("n_existing_groups") or 0)
        done_chunks = set(saved.get("done_chunks") or [])
        print(f"resume {len(done_chunks)} residual batches from {ckpt}", flush=True)
    states: list[dict[str, Any]] = []
    by_qid = {item["query_id"]: item for item in report.per_query}
    for row, shape, spec, support, excluded in ranked:
        stats = excluded.stats
        if stats is not None:
            report.blocking.append(stats.__dict__)
        if spec.joins and (not excluded.rows) and stats and stats.skip_reason:
            report.skipped.append(
                {"query_id": shape.query_id, "reason": stats.skip_reason, "cartesian": stats.cartesian}
            )
            print(f"skip {shape.query_id} {stats.skip_reason} cartesian={stats.cartesian}", flush=True)
            continue
        chunks = [
            excluded.rows[i : i + CANDIDATE_BATCH]
            for i in range(0, len(excluded.rows), CANDIDATE_BATCH)
        ]
        if shape.query_id not in by_qid:
            by_qid[shape.query_id] = {
                "query_id": shape.query_id,
                "witness_type": spec.kind,
                "incumbent_witnesses": len(support),
                "excluded_universe": len(excluded.rows),
                "n_cartesian": stats.cartesian if stats else len(excluded.rows),
                "n_blocked": stats.blocked if stats else len(excluded.rows),
                "skip_reason": (stats.skip_reason if stats else "") or "",
                "block_signal": (stats.signal if stats else "") or "",
                "n_proposed": 0,
                "n_validated": 0,
                "n_materialized": 0,
                "n_sql_visible": 0,
                "n_ineffective": 0,
                "n_added": 0,
                "n_unknown": 0,
                "n_base_row": 0,
                "n_join_edge": 0,
                "n_distinct": 0,
                "n_new_groups": 0,
                "n_existing_groups": 0,
                "join_edges_added": 0,
                "groups_added": 0,
                "count_mass_before": count_mass(path, shape.sql, live),
                "count_mass_after": 0,
                "tokens": 0,
                "tokens_executor": 0,
                "tokens_refiner": 0,
                "tokens_validator": 0,
                "incumbent_n": len({item.rowid for item in support if item.included == "true"}),
            }
            report.per_query.append(by_qid[shape.query_id])
            report.n_queries += 1
        states.append(
            {
                "row": row,
                "shape": shape,
                "spec": spec,
                "support": support,
                "chunks": chunks,
                "cursor": 0,
                "meta": by_qid[shape.query_id],
                "incumbent_rowids": {item.rowid for item in support if item.included == "true"},
                "incumbent_groups": {group_token(item, spec) for item in support if item.included == "true"},
                "conditions": query_conditions(shape, live),
            }
        )
    active = True
    while active and caller.ledger.remaining() > 0:
        active = False
        remaining_batches = sum(
            1
            for state in states
            for index, _chunk in enumerate(state["chunks"])
            if f"{state['shape'].query_id}:{index}" not in done_chunks
        )
        for state in states:
            if caller.ledger.remaining() <= 0:
                break
            shape = state["shape"]
            spec = state["spec"]
            meta = state["meta"]
            while state["cursor"] < len(state["chunks"]):
                chunk_id = f"{shape.query_id}:{state['cursor']}"
                if chunk_id in done_chunks:
                    state["cursor"] += 1
                    continue
                chunk = state["chunks"][state["cursor"]]
                if not chunk:
                    done_chunks.add(chunk_id)
                    state["cursor"] += 1
                    continue
                est = estimate_batch_tokens(len(chunk), len(state["conditions"]))
                quota = max(1, caller.ledger.remaining() // max(1, remaining_batches))
                if est > caller.ledger.remaining():
                    if len(chunk) > 1:
                        chunk = chunk[:1]
                        est = estimate_batch_tokens(1, len(state["conditions"]))
                    if est > caller.ledger.remaining():
                        print(f"  hold {shape.query_id} est={est} remaining={caller.ledger.remaining()}", flush=True)
                        break
                elif est > quota and len(chunk) > 1:
                    keep = max(1, len(chunk) * quota // est)
                    chunk = chunk[:keep]
                active = True
                spent_before = caller.ledger.spent
                exec_before = _purpose_tokens(caller, "sig_executor")
                ref_before = _purpose_tokens(caller, "sig_refiner")
                val_before = _purpose_tokens(caller, "sig_validator")
                print(
                    f"residual {shape.query_id} batch={state['cursor']} n={len(chunk)} "
                    f"est={est} quota={quota} remaining={caller.ledger.remaining()}",
                    flush=True,
                )
                by_id = {item.get("witness_id") or item["entity_id"]: item for item in chunk}
                by_id.update({item["entity_id"]: item for item in chunk})
                plans = {
                    "direct": propose_direct(bound, shape, chunk, state["conditions"]),
                    "decompose": propose_decompose(
                        bound, shape, chunk, state["conditions"], live, cond_cache,
                    ),
                }
                plans["gleaning"] = propose_decompose(
                    bound, shape, chunk, state["conditions"], live, cond_cache,
                    refine=True, prior=plans["decompose"],
                )
                union = proposed_union(plans)
                added = proposed = unknown = validated = 0
                materialized = sql_visible = ineffective = 0
                new_groups = existing_groups = edges_added = groups_added = 0
                n_base = n_join = n_dist = 0
                updated: set[str] = set()
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
                                bound, entity, shape, state["conditions"], live, proposals, state["incumbent_groups"],
                            )
                        except BudgetExhausted:
                            break
                        except Exception:
                            accepted = None
                        if accepted is None:
                            unknown += 1
                            continue
                        validated += 1
                        token = normalize_group(accepted.group) if spec.group_aliases else ""
                        is_new = bool(spec.group_aliases) and token not in state["incumbent_groups"] and token != "unknown"
                        reasons: list[str] = []
                        ok = apply_addition(
                            conn, path, entity, accepted, shape, live, state["incumbent_rowids"],
                            spec=spec, reasons=reasons,
                        )
                        if not ok:
                            ineffective += 1
                            cause = reasons[0] if reasons else "rejected"
                            report.rollbacks.append(
                                {
                                    "query_id": shape.query_id,
                                    "stage": "addition",
                                    "entity_id": entity_id,
                                    "reason": cause,
                                }
                            )
                            print(f"  ineffective {entity_id} reason={cause}", flush=True)
                            continue
                        added += 1
                        materialized += 1
                        sql_visible += 1
                        if spec.joins:
                            edges_added += 1
                            n_join += 1
                        if spec.distinct_sql:
                            n_dist += 1
                        if not spec.joins and not spec.distinct_sql:
                            n_base += 1
                        if spec.group_sql:
                            groups_added += 1
                        if is_new:
                            new_groups += 1
                            state["incumbent_groups"].add(token)
                        elif spec.group_aliases:
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
                        print(f"  rolled back batch; unrelated bags moved: {interference}", flush=True)
                        report.rollbacks.append(
                            {
                                "query_id": shape.query_id,
                                "stage": "cohort",
                                "reason": "unrelated bags",
                                "queries": interference,
                            }
                        )
                        added = materialized = sql_visible = new_groups = existing_groups = 0
                        edges_added = groups_added = n_base = n_join = n_dist = 0
                    else:
                        conn.execute("RELEASE residual_cohort")
                        bags = after_bags
                    conn.commit()
                finally:
                    conn.close()
                used = caller.ledger.spent - spent_before
                meta["n_proposed"] += proposed
                meta["n_validated"] += validated
                meta["n_materialized"] += materialized
                meta["n_sql_visible"] += sql_visible
                meta["n_ineffective"] += ineffective
                meta["n_added"] += added
                meta["n_unknown"] += unknown
                meta["n_base_row"] += n_base
                meta["n_join_edge"] += n_join
                meta["n_distinct"] += n_dist
                meta["n_new_groups"] += new_groups
                meta["n_existing_groups"] += existing_groups
                meta["join_edges_added"] += edges_added
                meta["groups_added"] += groups_added
                meta["tokens"] += used
                meta["tokens_executor"] += _purpose_tokens(caller, "sig_executor") - exec_before
                meta["tokens_refiner"] += _purpose_tokens(caller, "sig_refiner") - ref_before
                meta["tokens_validator"] += _purpose_tokens(caller, "sig_validator") - val_before
                meta["count_mass_after"] = count_mass(path, shape.sql, live)
                report.n_proposed += proposed
                report.n_added += added
                report.n_unknown += unknown
                report.n_validated += validated
                report.n_materialized += materialized
                report.n_sql_visible += sql_visible
                report.n_base_row += n_base
                report.n_join_edge += n_join
                report.n_distinct += n_dist
                report.n_new_groups += new_groups
                report.n_existing_groups += existing_groups
                done_chunks.add(chunk_id)
                remaining_batches = max(0, remaining_batches - 1)
                state["cursor"] += 1
                print(
                    f"  {shape.query_id} proposed={proposed} added={added} ineffective={ineffective} tokens={used}",
                    flush=True,
                )
                if ckpt:
                    ckpt.parent.mkdir(parents=True, exist_ok=True)
                    ckpt.write_text(
                        json.dumps(
                            {
                                "per_query": report.per_query,
                                "skipped": report.skipped,
                                "blocking": report.blocking,
                                "n_queries": report.n_queries,
                                "n_added": report.n_added,
                                "n_proposed": report.n_proposed,
                                "n_validated": report.n_validated,
                                "n_materialized": report.n_materialized,
                                "n_sql_visible": report.n_sql_visible,
                                "n_base_row": report.n_base_row,
                                "n_join_edge": report.n_join_edge,
                                "n_distinct": report.n_distinct,
                                "n_new_groups": report.n_new_groups,
                                "n_existing_groups": report.n_existing_groups,
                                "rollbacks": report.rollbacks,
                                "done_chunks": sorted(done_chunks),
                            },
                            default=str,
                        )
                    )
                break
    report.tokens_spent = caller.ledger.spent
    report.tokens_executor = _purpose_tokens(caller, "sig_executor")
    report.tokens_refiner = _purpose_tokens(caller, "sig_refiner")
    report.tokens_validator = _purpose_tokens(caller, "sig_validator")
    report.cache_hits = cache_store.hits
    report.cache_misses = cache_store.misses
    return report


def _purpose_tokens(caller: BudgetedCaller, purpose: str) -> int:
    return sum(rec.tokens for rec in caller.ledger.records if rec.purpose == purpose)


def residual_counts(
    sqlite_path: str | Path,
    sql: str,
    predicates: Iterable[AtomicPredicate] | None = None,
) -> list[dict[str, Any]]:
    return aprime_counts(sqlite_path, sql, predicates)


def compare_bags(
    left_path: str | Path,
    right_path: str | Path,
    statements: dict[str, str],
    predicates: list[AtomicPredicate],
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


def _count_sql(conn: sqlite3.Connection, sql: str, sqlite_path: str | Path, predicates: list[AtomicPredicate]) -> int:
    cur = conn.execute(official_sql(sql, sqlite_path, predicates))
    cols = [item[0] for item in cur.description] if cur.description else []
    total = 0
    for row in cur.fetchall():
        record = dict(zip(cols, row))
        for key, value in record.items():
            if str(key).lower().endswith("count") and value not in (None, ""):
                try:
                    total += int(value)
                except (TypeError, ValueError):
                    continue
        if not any(str(key).lower().endswith("count") for key in record):
            if row:
                try:
                    total += int(row[0] or 0)
                except (TypeError, ValueError):
                    continue
    return total


def write_gate_fixture(sqlite_path: str | Path) -> Path:
    path = Path(sqlite_path)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT)")
    conn.execute("CREATE TABLE extra (doc_id TEXT)")
    conn.execute("INSERT INTO item VALUES ('a', 'tablet')")
    conn.execute("INSERT INTO item VALUES ('b', 'capsule')")
    conn.execute("INSERT INTO extra VALUES ('a')")
    conn.execute("INSERT INTO extra VALUES ('z')")
    ensure_edge_table(conn)
    conn.commit()
    conn.close()
    return path


def probe_live_join(
    sqlite_path: str | Path,
    statements: dict[str, str],
    predicates: list[AtomicPredicate],
) -> dict[str, Any]:
    path = Path(sqlite_path)
    live = list(predicates)
    conn = sqlite3.connect(str(path))
    out: dict[str, Any] = {"ok": True, "checks": []}
    try:
        ensure_edge_table(conn)
        for qid, sql in statements.items():
            spec = compile_witness_spec(qid, sql)
            if not spec.joins:
                continue
            join = spec.joins[0]
            left = f'"{join.left_alias}"'
            right = f'"{join.right_alias}"'
            try:
                miss = conn.execute(
                    f'SELECT {left}.rowid, {right}.rowid FROM "{join.left_table}" AS {left}, '
                    f'"{join.right_table}" AS {right} WHERE NOT ({join.on_sql}) LIMIT 1'
                ).fetchone()
                hit = conn.execute(
                    f'SELECT {left}.rowid, {right}.rowid FROM "{join.left_table}" AS {left} '
                    f'JOIN "{join.right_table}" AS {right} ON {join.on_sql} LIMIT 1'
                ).fetchone()
            except sqlite3.Error as exc:
                out["checks"].append({"name": "live_pair", "query_id": qid, "ok": False, "error": str(exc)})
                out["ok"] = False
                break
            before = _count_sql(conn, sql, path, live)
            if miss:
                conn.execute("SAVEPOINT gate_live_add")
                add_edge(conn, join.join_id, int(miss[0]), int(miss[1]), provenance="gate")
                after = _count_sql(conn, sql, path, live)
                conn.execute("ROLLBACK TO gate_live_add")
                conn.execute("RELEASE gate_live_add")
                ok = before <= after <= before + 1
                out["checks"].append(
                    {
                        "name": "live_positive_edge",
                        "query_id": qid,
                        "before": before,
                        "after": after,
                        "ok": ok,
                    }
                )
                out["ok"] = out["ok"] and ok
            if hit:
                conn.execute("SAVEPOINT gate_live_dup")
                add_edge(conn, join.join_id, int(hit[0]), int(hit[1]), provenance="gate")
                after = _count_sql(conn, sql, path, live)
                conn.execute("ROLLBACK TO gate_live_dup")
                conn.execute("RELEASE gate_live_dup")
                ok = after == before
                out["checks"].append(
                    {
                        "name": "live_no_duplicate",
                        "query_id": qid,
                        "before": before,
                        "after": after,
                        "ok": ok,
                    }
                )
                out["ok"] = out["ok"] and ok
            break
    finally:
        conn.close()
    return out


def probe_edge_additivity(sqlite_path: str | Path, predicates: list[AtomicPredicate] | None = None) -> dict[str, Any]:
    path = Path(sqlite_path)
    live = list(predicates or [])
    conn = sqlite3.connect(str(path))
    ensure_edge_table(conn)
    conn.commit()
    findings: dict[str, Any] = {"ok": True, "checks": []}
    try:
        sql = "SELECT COUNT(*) AS n FROM item i JOIN extra e ON i.doc_id = e.doc_id"
        try:
            spec = compile_witness_spec("gate_join", sql)
            before = _count_sql(conn, sql, path, live)
            findings["checks"].append({"name": "empty_edge_keeps_on", "before": before, "ok": True})
            join = spec.joins[0]
            extra = conn.execute("SELECT rowid FROM extra WHERE doc_id != (SELECT doc_id FROM item LIMIT 1) LIMIT 1").fetchone()
            item = conn.execute("SELECT rowid FROM item LIMIT 1").fetchone()
            if extra and item:
                conn.execute("SAVEPOINT gate_add")
                add_edge(conn, join.join_id, int(item[0]), int(extra[0]), provenance="gate")
                after = _count_sql(conn, sql, path, live)
                conn.execute("ROLLBACK TO gate_add")
                conn.execute("RELEASE gate_add")
                ok = after == before + 1
                findings["checks"].append({"name": "positive_edge_adds_one", "before": before, "after": after, "ok": ok})
                findings["ok"] = findings["ok"] and ok
                conn.execute("SAVEPOINT gate_dup")
                match = conn.execute(
                    "SELECT i.rowid, e.rowid FROM item i JOIN extra e ON i.doc_id = e.doc_id LIMIT 1"
                ).fetchone()
                if match:
                    add_edge(conn, join.join_id, int(match[0]), int(match[1]), provenance="gate")
                    dup = _count_sql(conn, sql, path, live)
                    ok_dup = dup == before
                    findings["checks"].append({"name": "exists_no_duplicate", "before": before, "after": dup, "ok": ok_dup})
                    findings["ok"] = findings["ok"] and ok_dup
                conn.execute("ROLLBACK TO gate_dup")
                conn.execute("RELEASE gate_dup")
        except sqlite3.Error as exc:
            findings["ok"] = False
            findings["checks"].append({"name": "join_probe", "ok": False, "error": str(exc)})
        self_sql = "SELECT COUNT(*) AS n FROM item a JOIN item b ON a.doc_id = b.form"
        try:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='item'").fetchone():
                spec = compile_witness_spec("gate_self", self_sql)
                before = _count_sql(conn, self_sql, path, live)
                join = spec.joins[0]
                left = conn.execute("SELECT rowid FROM item LIMIT 1").fetchone()
                right = conn.execute("SELECT rowid FROM item LIMIT 1 OFFSET 1").fetchone()
                if left and right and spec.joins:
                    conn.execute("SAVEPOINT gate_self")
                    add_edge(conn, join.join_id, int(left[0]), int(right[0]), provenance="gate")
                    after = _count_sql(conn, self_sql, path, live)
                    conn.execute("ROLLBACK TO gate_self")
                    conn.execute("RELEASE gate_self")
                    ok = before <= after <= before + 1
                    findings["checks"].append(
                        {
                            "name": "self_join_aliases",
                            "before": before,
                            "after": after,
                            "ok": ok,
                            "left_alias": join.left_alias,
                            "right_alias": join.right_alias,
                        }
                    )
                    findings["ok"] = findings["ok"] and ok
        except sqlite3.Error as exc:
            findings["checks"].append({"name": "self_join_aliases", "ok": False, "error": str(exc)})
            findings["ok"] = False
    finally:
        conn.close()
    return findings
