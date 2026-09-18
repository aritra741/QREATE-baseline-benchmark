"""Three query-level support plans and disagreement-only validation. No gold."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from quwarts.core.extract import find_surface_span
from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.query_support import (
    QueryShape,
    SupportRow,
    aprime_counts,
    aprime_support,
    clip_context,
    count_from_support,
    query_shape,
    support_key,
    symmetric_diff,
    universe,
)
from quwarts.core.signature import AtomicPredicate
from quwarts.core.signature_cache import CachedCaller, ResponseCache
from quwarts.core.signature_classify import _object
from quwarts.core.signature_realize import is_membership, is_presence

STRATEGIES = ("direct", "decompose", "gleaning")
DIRECT_PROMPT = """Decide whether this entity contributes to the count query.
Return JSON {"included": true|false|unknown, "group_key": {}, "join_partner_ids": [],
"evidence": [{"span": "...", "note": "..."}]}.
Cite a verbatim span when the decision is grounded. Do not use gold or scorers.
QUERY:
"""
FILTER_PROMPT = """Does this condition hold for the entity?
Return JSON {"applies": true|false|unknown, "span": "..."}.
CONDITION:
"""
GROUP_PROMPT = """Assign the group label for this entity and expression.
Return JSON {"value": "...", "span": "..."}.
EXPRESSION:
"""
JOIN_PROMPT = """Should these two entities be joined?
Return JSON {"join": true|false|unknown, "span": "..."}.
PAIR:
"""
JUDGE_PROMPT = """Two candidates disagree on whether this entity contributes to a count/group.
Answer only this binary question. Return JSON {"contribute": true|false, "span": "..."}.
Cite a verbatim span when grounded.
"""
JUDGE_INFER_A = """Using only the stated condition and context, should this entity contribute to the count?
Return JSON {"contribute": true|false}.
"""
JUDGE_INFER_B = """Ignore previous wording. From the evidence snippet, is the entity in the counted set?
Return JSON {"contribute": true|false}.
"""


@dataclass
class PlanReport:
    tokens_spent: int = 0
    tokens_planner: int = 0
    tokens_executor: int = 0
    tokens_refiner: int = 0
    tokens_validator: int = 0
    n_queries: int = 0
    n_accepted: int = 0
    n_fallback: int = 0
    n_disputes: int = 0
    n_grounded: int = 0
    n_inferred: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    per_query: list[dict[str, Any]] = field(default_factory=list)


def _complete(caller: BudgetedCaller, prompt: str, purpose: str, **meta: Any) -> str:
    return caller.complete(prompt, purpose=purpose, **meta)


def _bool(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return "true"
    if text in {"false", "no", "0"}:
        return "false"
    return "unknown"


def obligation_pred(entity_id: str, pred: AtomicPredicate) -> str:
    return f"pred|{entity_id}|{pred.pred_id}|{pred.operator}|{pred.literal or ''}"


def obligation_group(entity_id: str, expr: str) -> str:
    return f"group|{entity_id}|{expr}"


def obligation_join(left: str, right: str, relation: str) -> str:
    return f"join|{left}|{right}|{relation}"


def _span_ok(document: str, span: str | None) -> bool:
    if not span:
        return False
    return find_surface_span(document or "", span) is not None


def _relevant(document: str, cells: dict[str, Any], pred: AtomicPredicate | None) -> str:
    needle = pred.literal if pred is not None else None
    if needle:
        clipped = clip_context(document, needle.replace("%", ""))
        if clipped:
            return clipped
    shown = " ".join(str(value) for value in list(cells.values())[:6] if value not in (None, ""))
    return clip_context((document or "") + "\n" + shown)


def judge_direct(
    caller: BudgetedCaller,
    shape: QueryShape,
    entity: dict[str, Any],
) -> SupportRow:
    prompt = (
        DIRECT_PROMPT
        + shape.sql
        + f"\nENTITY_LABEL: {entity['label']}\nCONTEXT:\n{_relevant(entity['document'], entity['cells'], None)}\n"
    )
    text = _complete(
        caller, prompt, "sig_executor",
        system="Decide query support. JSON only.",
        max_tokens=200,
        plan="direct",
    )
    payload = _object(text)
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    groups = payload.get("group_key") if isinstance(payload.get("group_key"), dict) else {}
    partners = payload.get("join_partner_ids") if isinstance(payload.get("join_partner_ids"), list) else []
    included = _bool(payload.get("included"))
    spans = [str(item.get("span") or "") for item in evidence if isinstance(item, dict)]
    grounded = any(_span_ok(entity["document"], span) for span in spans)
    if included == "true" and not grounded and spans:
        included = "unknown"
    return SupportRow(
        entity_id=entity["entity_id"],
        rowid=entity["rowid"],
        included=included,
        group_key={name: groups.get(name) for name in shape.group_aliases},
        join_partner_ids=tuple(str(item) for item in partners),
        evidence=tuple(item for item in evidence if isinstance(item, dict)),
        source="direct",
    )


def _apply_filter(
    cache: dict[str, str],
    caller: BudgetedCaller,
    entity: dict[str, Any],
    pred: AtomicPredicate,
) -> str:
    key = obligation_pred(entity["entity_id"], pred)
    if key in cache:
        return cache[key]
    prompt = (
        FILTER_PROMPT
        + f"{pred.operator} {pred.literal or ''}\n"
        + f"ENTITY_LABEL: {entity['label']}\nCONTEXT:\n{_relevant(entity['document'], entity['cells'], pred)}\n"
    )
    text = _complete(
        caller, prompt, "sig_executor",
        system="Evaluate one condition. JSON only.",
        max_tokens=80,
        plan="decompose",
    )
    payload = _object(text)
    applies = _bool(payload.get("applies"))
    span = str(payload.get("span") or "")
    if applies == "true" and not _span_ok(entity["document"], span):
        applies = "unknown"
    cache[key] = applies
    return applies


def _apply_group(
    cache: dict[str, str],
    caller: BudgetedCaller,
    entity: dict[str, Any],
    alias: str,
    expr: str,
) -> Any:
    key = obligation_group(entity["entity_id"], expr)
    if key in cache:
        return cache[key]
    prompt = (
        GROUP_PROMPT
        + expr
        + f"\nALIAS: {alias}\nENTITY_LABEL: {entity['label']}\nCONTEXT:\n{_relevant(entity['document'], entity['cells'], None)}\n"
    )
    text = _complete(
        caller, prompt, "sig_executor",
        system="Assign one group label. JSON only.",
        max_tokens=80,
        plan="decompose",
    )
    payload = _object(text)
    value = payload.get("value")
    cache[key] = value
    return value


def judge_decompose(
    caller: BudgetedCaller,
    shape: QueryShape,
    entity: dict[str, Any],
    predicates: list[AtomicPredicate],
    cache: dict[str, str],
    refine: bool = False,
) -> SupportRow:
    scoped = [
        pred for pred in predicates
        if pred.table == shape.primary and shape.query_id in pred.query_ids
    ]
    filters = [pred for pred in scoped if is_presence(pred)]
    members = [pred for pred in scoped if is_membership(pred)]
    included = "true"
    evidence = []
    for pred in filters[:8]:
        cell = entity["cells"].get(pred.column)
        applies = "true" if cell not in (None, "") else "unknown"
        cache[obligation_pred(entity["entity_id"], pred)] = applies
        evidence.append({"obligation": obligation_pred(entity["entity_id"], pred), "applies": applies})
        if applies == "false":
            included = "false"
            break
        if applies == "unknown" and included != "false":
            included = "unknown"
    for pred in members[:6]:
        applies = _apply_filter(cache, caller, entity, pred)
        evidence.append({"obligation": obligation_pred(entity["entity_id"], pred), "applies": applies})
    if refine and included == "unknown":
        try:
            text = _complete(
                caller,
                DIRECT_PROMPT + shape.sql + f"\nENTITY_LABEL: {entity['label']}\nCONTEXT:\n{_relevant(entity['document'], entity['cells'], None)}\nISSUE: refine unknown filter\n",
                "sig_refiner",
                system="Refine one support decision. JSON only.",
                max_tokens=120,
                plan="gleaning",
            )
            included = _bool(_object(text).get("included")) or included
        except (BudgetExhausted, Exception):
            pass
    groups = {}
    for alias, expr in zip(shape.group_aliases, shape.group_sql):
        groups[alias] = _apply_group(cache, caller, entity, alias, expr)
    return SupportRow(
        entity_id=entity["entity_id"],
        rowid=entity["rowid"],
        included=included,
        group_key=groups,
        evidence=tuple(evidence),
        source="gleaning" if refine else "decompose",
    )


def execute_plan(
    strategy: str,
    shape: QueryShape,
    entities: list[dict[str, Any]],
    predicates: list[AtomicPredicate],
    caller: BudgetedCaller,
    cache: dict[str, str],
    fallback: dict[str, SupportRow],
) -> list[SupportRow]:
    out = []
    for entity in entities:
        try:
            if strategy == "direct":
                row = judge_direct(caller, shape, entity)
            else:
                row = judge_decompose(
                    caller, shape, entity, predicates, cache, refine=strategy == "gleaning",
                )
        except BudgetExhausted:
            raise
        except Exception:
            row = fallback.get(entity["entity_id"]) or SupportRow(
                entity_id=entity["entity_id"], rowid=entity["rowid"], included="unknown", group_key={},
            )
        if row.included == "unknown" and entity["entity_id"] in fallback:
            row = fallback[entity["entity_id"]]
        out.append(row)
    return out


def _judge_binary(
    caller: BudgetedCaller,
    prompt: str,
    purpose: str,
    grounded: bool,
    document: str,
) -> str:
    text = _complete(
        caller, prompt, purpose,
        system="Answer one binary support question. JSON only.",
        max_tokens=60,
        plan="validator",
    )
    payload = _object(text)
    decision = _bool(payload.get("contribute"))
    if grounded:
        span = str(payload.get("span") or "")
        if decision == "true" and not _span_ok(document, span):
            return "unknown"
    return decision


def adjudicate(
    caller: BudgetedCaller,
    shape: QueryShape,
    entity: dict[str, Any],
    left: SupportRow,
    right: SupportRow,
    condition: str,
) -> str:
    context = _relevant(entity["document"], entity["cells"], None)
    body = (
        f"CONDITION: {condition}\nENTITY_LABEL: {entity['label']}\nCONTEXT:\n{context}\n"
        f"CANDIDATE A: included={left.included} group={json.dumps(left.group_key)} evidence={json.dumps(left.evidence)}\n"
        f"CANDIDATE B: included={right.included} group={json.dumps(right.group_key)} evidence={json.dumps(right.evidence)}\n"
    )
    grounded = bool(left.evidence or right.evidence)
    if grounded:
        return _judge_binary(caller, JUDGE_PROMPT + body, "sig_validator", True, entity["document"])
    first = _judge_binary(caller, JUDGE_INFER_A + body, "sig_validator", False, entity["document"])
    second = _judge_binary(caller, JUDGE_INFER_B + body, "sig_validator", False, entity["document"])
    if first == second and first in {"true", "false"}:
        return first
    return "unknown"


def select_support(
    plans: dict[str, list[SupportRow]],
    fallback: list[SupportRow],
    entities: list[dict[str, Any]],
    shape: QueryShape,
    caller: BudgetedCaller,
    stats: PlanReport,
) -> tuple[str, list[SupportRow]]:
    by_id = {row["entity_id"]: row for row in entities}
    fb_map = {row.entity_id: row for row in fallback}
    names = [name for name in STRATEGIES if name in plans]
    wins = {name: 0 for name in names}
    fb_net = {name: 0 for name in names}
    for i, left_name in enumerate(names):
        for right_name in names[i + 1 :]:
            disputed = symmetric_diff(plans[left_name], plans[right_name])
            stats.n_disputes += len(disputed)
            left_map = {row.entity_id: row for row in plans[left_name]}
            right_map = {row.entity_id: row for row in plans[right_name]}
            for entity_id in disputed:
                entity = by_id.get(entity_id)
                if entity is None:
                    continue
                try:
                    pick = adjudicate(
                        caller, shape, entity,
                        left_map.get(entity_id) or SupportRow(entity_id, 0, "unknown", {}),
                        right_map.get(entity_id) or SupportRow(entity_id, 0, "unknown", {}),
                        shape.sql[:240],
                    )
                except (BudgetExhausted, Exception):
                    pick = "unknown"
                if pick == "unknown":
                    continue
                left_in = (left_map.get(entity_id) or SupportRow(entity_id, 0, "false", {})).included == "true"
                if (pick == "true") == left_in:
                    wins[left_name] += 1
                else:
                    wins[right_name] += 1
    for name in names:
        disputed = symmetric_diff(plans[name], fallback)
        for entity_id in disputed:
            entity = by_id.get(entity_id)
            if entity is None:
                continue
            try:
                pick = adjudicate(
                    caller, shape, entity,
                    {row.entity_id: row for row in plans[name]}.get(entity_id) or SupportRow(entity_id, 0, "unknown", {}),
                    fb_map.get(entity_id) or SupportRow(entity_id, 0, "false", {}),
                    shape.sql[:240],
                )
            except (BudgetExhausted, Exception):
                pick = "unknown"
            plan_in = any(row.entity_id == entity_id and row.included == "true" for row in plans[name])
            if pick == "unknown":
                continue
            if (pick == "true") == plan_in:
                fb_net[name] += 1
            else:
                fb_net[name] -= 1
    if not names:
        return "aprime", fallback
    winner = max(names, key=lambda name: (wins[name], fb_net[name]))
    if fb_net[winner] < 2:
        return "aprime", fallback
    chosen = plans[winner]
    if fallback and not any(row.included == "true" for row in chosen):
        return "aprime", fallback
    return winner, chosen


def run_query_arm(
    sqlite_path: str | Path,
    queries: list[dict[str, str]],
    predicates: Iterable[AtomicPredicate],
    *,
    documents: dict[str, str] | None = None,
    caller: BudgetedCaller | None = None,
    max_queries: int | None = None,
    checkpoint: str | Path | None = None,
) -> tuple[PlanReport, dict[str, list[dict[str, Any]]]]:
    live = list(predicates)
    cache_store = ResponseCache()
    obl: dict[str, str] = {}
    report = PlanReport()
    outputs: dict[str, list[dict[str, Any]]] = {}
    if caller is None:
        return report, outputs
    bound = CachedCaller(caller, cache_store, plan="query")
    selected = list(queries[: max_queries or len(queries)])
    ckpt_path = Path(checkpoint) if checkpoint else None
    if ckpt_path and ckpt_path.is_file():
        saved = json.loads(ckpt_path.read_text())
        outputs.update(saved.get("outputs") or {})
        report.per_query.extend(saved.get("per_query") or [])
        report.n_queries = int(saved.get("n_queries") or 0)
        report.n_accepted = int(saved.get("n_accepted") or 0)
        report.n_fallback = int(saved.get("n_fallback") or 0)
        print(f"resume {len(outputs)} queries from {ckpt_path}", flush=True)
    for row in selected:
        if row["query_id"] in outputs:
            continue
        if caller.ledger.remaining() <= 0:
            break
        shape = query_shape(row["query_id"], row["sql"])
        print(f"query plan {shape.query_id} remaining={caller.ledger.remaining()}", flush=True)
        report.n_queries += 1
        fallback_rows: list[SupportRow] = []
        rid_to_entity: dict[int, str] | None = None
        try:
            entities = universe(sqlite_path, shape, documents)
            rid_to_entity = {item["rowid"]: item["entity_id"] for item in entities}
            fallback_rows = aprime_support(sqlite_path, shape, live, rid_to_entity)
            fb_map = {item.entity_id: item for item in fallback_rows}
            plans = {}
            for strategy in STRATEGIES:
                plans[strategy] = execute_plan(strategy, shape, entities, live, bound, obl, fb_map)
            winner, chosen = select_support(plans, fallback_rows, entities, shape, bound, report)
        except BudgetExhausted:
            fallback_rows = aprime_support(sqlite_path, shape, live, rid_to_entity)
            winner, chosen = "aprime", fallback_rows
        except Exception as exc:
            print(f"  fallback after error: {exc}", flush=True)
            fallback_rows = aprime_support(sqlite_path, shape, live, rid_to_entity)
            winner, chosen = "aprime", fallback_rows
        if winner == "aprime":
            report.n_fallback += 1
            outputs[shape.query_id] = aprime_counts(sqlite_path, shape.sql, live)
            chosen_ids = [row.entity_id for row in fallback_rows if row.included == "true"]
        else:
            report.n_accepted += 1
            try:
                outputs[shape.query_id] = count_from_support(shape, chosen)
            except Exception as exc:
                print(f"  count failed ({exc}); using A'", flush=True)
                outputs[shape.query_id] = aprime_counts(sqlite_path, shape.sql, live)
                winner = "aprime"
                report.n_accepted -= 1
                report.n_fallback += 1
            chosen_ids = [row.entity_id for row in chosen if row.included == "true"]
        report.per_query.append(
            {
                "query_id": shape.query_id,
                "winner": winner,
                "n_out": len(outputs[shape.query_id]),
                "entity_ids": chosen_ids,
                "groups": outputs[shape.query_id],
            }
        )
        print(f"  winner={winner} n={len(outputs[shape.query_id])}", flush=True)
        if ckpt_path:
            ckpt_path.parent.mkdir(parents=True, exist_ok=True)
            ckpt_path.write_text(
                json.dumps(
                    {
                        "outputs": outputs,
                        "per_query": report.per_query,
                        "n_queries": report.n_queries,
                        "n_accepted": report.n_accepted,
                        "n_fallback": report.n_fallback,
                    },
                    default=str,
                )
            )
    for qid, sql in ((row["query_id"], row["sql"]) for row in selected):
        if qid not in outputs:
            outputs[qid] = aprime_counts(sqlite_path, sql, live)
            report.n_fallback += 1
    report.tokens_spent = caller.ledger.spent
    report.tokens_planner = sum(rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_planner")
    report.tokens_executor = sum(rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_executor")
    report.tokens_refiner = sum(rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_refiner")
    report.tokens_validator = sum(rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_validator")
    report.cache_hits = cache_store.hits
    report.cache_misses = cache_store.misses
    return report, outputs
