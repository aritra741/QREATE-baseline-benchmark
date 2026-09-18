"""Minimal acquisition controller. Chooses typed operators. No gold, no scorer."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.models import SourceDocument, Workload
from quwarts.core.signature import AtomicPredicate, rewrite_sql
from quwarts.core.signature_acquire import (
    AcquisitionAction,
    ActionOutcome,
    allowed_pred_ids,
    parse_action,
    validate_action,
)
from quwarts.core.signature_classify import _object, value_is_missing
from quwarts.core.signature_populate import (
    _close_labels,
    _doc_text,
    _entity_name,
    _quote,
    _surfaces,
    _write_row,
    apply_row_operators,
    atom_priority,
    atom_unresolved,
    clip_document,
    deterministic_labels,
    ensure_signature_columns,
    label_from_stored,
    resolve_table,
)
from quwarts.core.signature_realize import is_membership, is_presence, operator_kind
from quwarts.core.truth import PredicateLabel, is_label_resolved, merge_atoms

CONTROLLER_PROMPT = """Choose one acquisition action for unresolved signature cohorts.
You may use only grounded_existence, semantic_membership, or abstain.
grounded_existence requires a supporting span and writes presence atoms only.
semantic_membership classifies all membership atoms for one entity-attribute pair.
abstain spends nothing and leaves the original-expression fallback active.
Operate on the unresolved cohort, not individual cells.
Do not invent operators. Do not name evaluation metrics.
Return JSON: {"scope": {"predicate_ids": [], "attribute": "", "entity_cohort": "unresolved"},
"operator": "grounded_existence|semantic_membership|abstain",
"context": "value|entity_label|document", "model": "", "max_tokens": 0, "reason": ""}
STATE:
"""


@dataclass
class ControllerReport:
    policy: str
    outcomes: list[ActionOutcome] = field(default_factory=list)
    tokens_spent: int = 0
    tokens_controller: int = 0
    tokens_operators: int = 0
    n_resolved: int = 0
    n_unresolved: int = 0
    n_conflicts: int = 0
    n_abstentions: int = 0


def _documents(documents: list[SourceDocument] | dict[str, str] | None) -> dict[str, str]:
    if isinstance(documents, dict):
        return {str(key): value for key, value in documents.items()}
    if documents:
        return {doc.doc_id: doc.text for doc in documents}
    return {}


def _load_attr_rows(
    conn: sqlite3.Connection,
    predicates: list[AtomicPredicate],
    texts: dict[str, str],
) -> list[dict[str, Any]]:
    if not predicates:
        return []
    table = resolve_table(conn, predicates[0])
    if table is None:
        return []
    column = predicates[0].column
    rows = []
    for row in conn.execute(f"SELECT rowid AS _rid, * FROM {_quote(table)}"):
        payload = dict(row)
        rowid = int(payload.pop("_rid"))
        labels: dict[str, PredicateLabel] = {}
        for pred in predicates:
            stored = label_from_stored(payload.get(pred.sig_name), payload.get(pred.resolved_name))
            if stored is not None:
                labels[pred.pred_id] = stored
        cell = payload.get(column)
        labels = merge_atoms(
            labels,
            deterministic_labels(predicates, cell),
            {pred.pred_id for pred in predicates},
        )
        doc_id = payload.get("doc_id")
        rows.append(
            {
                "table": table,
                "rowid": rowid,
                "doc_id": doc_id,
                "cell": cell,
                "labels": labels,
                "document": _doc_text(texts, doc_id),
                "entity_name": _entity_name(payload, table),
                "surfaces": _surfaces(payload, column),
            }
        )
    return rows


def observe(
    sqlite_path: str | Path,
    predicates: Iterable[AtomicPredicate],
    workload: Workload | None = None,
    documents: list[SourceDocument] | dict[str, str] | None = None,
    prior: list[ActionOutcome] | None = None,
    statements: dict[str, str] | None = None,
    ledger: Any | None = None,
) -> dict[str, Any]:
    live = list(predicates)
    texts = _documents(documents)
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_signature_columns(conn, live)
        by_attr: dict[str, list[AtomicPredicate]] = defaultdict(list)
        for pred in live:
            by_attr[pred.attribute].append(pred)
        attributes = []
        samples: list[str] = []
        for attr, preds in by_attr.items():
            rows = _load_attr_rows(conn, preds, texts)
            unresolved = 0
            presence_u = 0
            member_u = 0
            nonempty = 0
            named = 0
            for row in rows:
                if not value_is_missing(row["cell"]):
                    nonempty += 1
                if row["entity_name"]:
                    named += 1
                for pred in preds:
                    if not atom_unresolved(row["labels"], pred):
                        continue
                    unresolved += 1
                    if is_presence(pred):
                        presence_u += 1
                    elif is_membership(pred):
                        member_u += 1
            amp_val = 0.0
            freq = sum(len(pred.query_ids) for pred in preds)
            if workload is not None:
                req = workload.requirements.get(attr)
                if req is not None:
                    amp_val = float(req.amp if req.amp is not None else 0.0)
                    roles = sorted(str(role) if not hasattr(role, "value") else role.value for role in (req.roles or []))
                else:
                    roles = []
            else:
                roles = []
            attributes.append(
                {
                    "attribute": attr,
                    "n_rows": len(rows),
                    "unresolved_atoms": unresolved,
                    "unresolved_presence": presence_u,
                    "unresolved_membership": member_u,
                    "query_frequency": freq,
                    "amplification": amp_val,
                    "roles": roles,
                    "kinds": {operator_kind(pred): 1 for pred in preds},
                    "surface_rate": (nonempty / len(rows)) if rows else 0.0,
                    "entity_label_rate": (named / len(rows)) if rows else 0.0,
                    "predicate_ids": [pred.pred_id for pred in preds],
                }
            )
            for row in rows:
                if row["document"] and len(samples) < 2:
                    samples.append(clip_document(row["document"], 400))
        empty_rate = None
        if statements:
            empty_rate = _empty_rate(conn, statements, live)
        conn.commit()
    finally:
        conn.close()
    attributes.sort(
        key=lambda item: item["query_frequency"] * (item["amplification"] or 1.0) * (1 if item["unresolved_atoms"] else 0),
        reverse=True,
    )
    return {
        "attributes": attributes,
        "prior": [
            {
                "operator": item.action.operator,
                "attribute": item.action.attribute,
                "accepted": item.accepted,
                "n_resolved": item.n_resolved,
                "n_abstentions": item.n_abstentions,
                "tokens": item.tokens,
                "error": item.error,
            }
            for item in (prior or [])
        ],
        "spent": getattr(ledger, "spent", 0) if ledger is not None else 0,
        "remaining": ledger.remaining() if ledger is not None and hasattr(ledger, "remaining") else None,
        "representative_documents": samples,
        "empty_rate": empty_rate,
        "conflicts": sum(item.n_conflicts for item in (prior or [])),
        "abstentions": sum(item.n_abstentions for item in (prior or [])),
    }


def _empty_rate(conn: sqlite3.Connection, statements: dict[str, str], predicates: list[AtomicPredicate]) -> float:
    if not statements:
        return 0.0
    empty = 0
    n = 0
    for sql in list(statements.values())[:20]:
        rewritten = rewrite_sql(sql, predicates)
        try:
            rows = conn.execute(rewritten).fetchall()
        except sqlite3.Error:
            continue
        n += 1
        if not rows:
            empty += 1
    return empty / n if n else 0.0


def fixed_policy_action(observation: dict[str, Any]) -> AcquisitionAction:
    """Current generic policy: highest freq × amp unresolved cohort, then the needed operator."""

    for item in observation.get("attributes") or []:
        if item.get("unresolved_presence"):
            return AcquisitionAction(
                predicate_ids=tuple(item.get("predicate_ids") or []),
                attribute=item["attribute"],
                entity_cohort="unresolved",
                operator="grounded_existence",
                context="document",
                model="",
                max_tokens=120,
                reason="fixed_priority_presence",
            )
        if item.get("unresolved_membership"):
            return AcquisitionAction(
                predicate_ids=tuple(item.get("predicate_ids") or []),
                attribute=item["attribute"],
                entity_cohort="unresolved",
                operator="semantic_membership",
                context="document",
                model="",
                max_tokens=280,
                reason="fixed_priority_membership",
            )
    return AcquisitionAction(
        predicate_ids=(),
        attribute="",
        entity_cohort="unresolved",
        operator="abstain",
        context="document",
        model="",
        max_tokens=0,
        reason="fixed_nothing_unresolved",
    )


def propose_action(
    caller: BudgetedCaller,
    observation: dict[str, Any],
    predicates: list[AtomicPredicate],
) -> AcquisitionAction:
    try:
        text = caller.complete(
            CONTROLLER_PROMPT + json.dumps(observation, default=str)[:8000],
            purpose="sig_controller",
            system="Select one typed acquisition action. JSON only.",
            max_tokens=220,
        )
    except (BudgetExhausted, Exception):
        return AcquisitionAction(
            predicate_ids=(),
            attribute="",
            entity_cohort="unresolved",
            operator="abstain",
            context="document",
            model="",
            max_tokens=0,
            reason="controller_failed",
        )
    return validate_action(parse_action(_object(text)), predicates)


def execute_action(
    sqlite_path: str | Path,
    action: AcquisitionAction,
    predicates: Iterable[AtomicPredicate],
    documents: list[SourceDocument] | dict[str, str] | None = None,
    caller: BudgetedCaller | None = None,
    statements: dict[str, str] | None = None,
) -> ActionOutcome:
    live = list(predicates)
    action = validate_action(action, live)
    if action.operator == "abstain":
        return ActionOutcome(action=action, accepted=True, n_abstentions=1)
    allowed = allowed_pred_ids(action, live)
    scoped = [pred for pred in live if pred.attribute == action.attribute]
    if not scoped or not allowed:
        return ActionOutcome(action=action, accepted=False, error="empty_scope", n_abstentions=1)
    texts = _documents(documents)
    spent0 = caller.ledger.spent if caller is not None else 0
    grounded = 0
    grounded_ok = 0
    rows: list[dict[str, Any]] = []
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = ensure_signature_columns(conn, live)
        rows = _load_attr_rows(conn, scoped, texts)
        n_resolved = 0
        n_unresolved = 0
        n_conflicts = 0
        n_abstain = 0
        for row in rows:
            before = dict(row["labels"])
            if not any(pred.pred_id in allowed and atom_unresolved(before, pred) for pred in scoped):
                continue
            run_presence = action.operator == "grounded_existence"
            run_membership = action.operator == "semantic_membership"
            document = row["document"] if action.context == "document" or run_presence else ""
            entity_name = row["entity_name"] if action.context in {"entity_label", "document"} else ""
            surfaces = row["surfaces"] if action.context in {"value", "document"} else []
            merged = apply_row_operators(
                before,
                scoped,
                attribute=action.attribute,
                cell=row["cell"],
                document=document,
                entity_name=entity_name,
                surfaces=surfaces,
                caller=caller,
                run_presence=run_presence,
                run_membership=run_membership,
            )
            merged = merge_atoms(before, merged, allowed)
            merged, _violations = _close_labels(merged, scoped)
            if run_presence:
                grounded += 1
                if any(
                    is_presence(pred) and is_label_resolved(merged.get(pred.pred_id))
                    for pred in scoped
                ):
                    grounded_ok += 1
            n_conflicts += sum(1 for lab in merged.values() if lab.conflict)
            for pred in scoped:
                if pred.pred_id not in allowed and pred.pred_id not in before:
                    continue
                if is_label_resolved(merged.get(pred.pred_id)):
                    n_resolved += 1
                else:
                    n_unresolved += 1
                    if pred.pred_id in allowed:
                        n_abstain += 1
            table = row["table"]
            _write_row(conn, table, row["rowid"], scoped, merged, existing.get(table, set()))
        empty_rate = _empty_rate(conn, statements or {}, live) if statements else None
        conn.commit()
    finally:
        conn.close()
    tokens = (caller.ledger.spent - spent0) if caller is not None else 0
    remaining = caller.ledger.remaining() if caller is not None else None
    return ActionOutcome(
        action=action,
        accepted=True,
        n_rows=len(rows),
        n_resolved=n_resolved,
        n_unresolved=n_unresolved,
        n_conflicts=n_conflicts,
        n_abstentions=n_abstain,
        grounded_span_rate=(grounded_ok / grounded) if grounded else None,
        tokens=tokens,
        remaining=remaining,
        empty_rate=empty_rate,
    )


def run_acquisition(
    sqlite_path: str | Path,
    predicates: Iterable[AtomicPredicate],
    *,
    policy: str,
    documents: list[SourceDocument] | dict[str, str] | None = None,
    caller: BudgetedCaller | None = None,
    workload: Workload | None = None,
    statements: dict[str, str] | None = None,
    max_steps: int = 40,
) -> ControllerReport:
    live = list(predicates)
    report = ControllerReport(policy=policy)
    seen: set[tuple[str, str]] = set()
    for step in range(max_steps):
        observation = observe(
            sqlite_path, live, workload, documents, report.outcomes, statements,
            caller.ledger if caller is not None else None,
        )
        if not any(item.get("unresolved_atoms") for item in observation.get("attributes") or []):
            break
        if policy == "agent" and caller is not None:
            raw = propose_action(caller, observation, live)
        else:
            raw = fixed_policy_action(observation)
        action = validate_action(raw, live)
        key = (action.operator, action.attribute)
        if action.operator == "abstain":
            report.outcomes.append(ActionOutcome(action=action, accepted=True, n_abstentions=1))
            report.n_abstentions += 1
            if not action.attribute or key in seen:
                break
            seen.add(key)
            continue
        if key in seen and policy == "agent":
            report.outcomes.append(
                ActionOutcome(
                    action=AcquisitionAction(
                        predicate_ids=(),
                        attribute=action.attribute,
                        entity_cohort="unresolved",
                        operator="abstain",
                        context="document",
                        model="",
                        max_tokens=0,
                        reason="repeat_cohort",
                    ),
                    accepted=True,
                    n_abstentions=1,
                )
            )
            break
        seen.add(key)
        try:
            outcome = execute_action(sqlite_path, action, live, documents, caller, statements)
        except BudgetExhausted:
            report.outcomes.append(
                ActionOutcome(action=action, accepted=False, error="budget", n_abstentions=1)
            )
            break
        report.outcomes.append(outcome)
        report.n_resolved += outcome.n_resolved
        report.n_unresolved += outcome.n_unresolved
        report.n_conflicts += outcome.n_conflicts
        report.n_abstentions += outcome.n_abstentions
        if caller is not None and caller.ledger.remaining() <= 0:
            break
    if caller is not None:
        report.tokens_spent = caller.ledger.spent
        report.tokens_controller = sum(
            rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_controller"
        )
        report.tokens_operators = report.tokens_spent - report.tokens_controller
    return report
