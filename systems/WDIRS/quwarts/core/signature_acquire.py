"""Cohort acquisition actions. Typed operators only. No gold, no corpus names."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal

from quwarts.core.signature import AtomicPredicate
from quwarts.core.signature_realize import is_membership, is_presence, operator_kind

OPERATORS = frozenset({"grounded_existence", "semantic_membership", "abstain"})
CONTEXTS = frozenset({"value", "entity_label", "document"})
COHORTS = frozenset({"unresolved"})


@dataclass(frozen=True)
class AcquisitionAction:
    predicate_ids: tuple[str, ...]
    attribute: str
    entity_cohort: str
    operator: Literal["grounded_existence", "semantic_membership", "abstain"]
    context: Literal["value", "entity_label", "document"]
    model: str
    max_tokens: int
    reason: str

    def as_json(self) -> dict[str, Any]:
        return {
            "scope": {
                "predicate_ids": list(self.predicate_ids),
                "attribute": self.attribute,
                "entity_cohort": self.entity_cohort,
            },
            "operator": self.operator,
            "context": self.context,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "reason": self.reason,
        }


@dataclass
class ActionOutcome:
    action: AcquisitionAction
    accepted: bool
    n_rows: int = 0
    n_resolved: int = 0
    n_unresolved: int = 0
    n_conflicts: int = 0
    n_abstentions: int = 0
    grounded_span_rate: float | None = None
    tokens: int = 0
    remaining: int | None = None
    empty_rate: float | None = None
    join_yield: float | None = None
    error: str = ""


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    return tuple(str(item) for item in value if item not in (None, ""))


def parse_action(payload: dict[str, Any]) -> AcquisitionAction:
    scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
    operator = str(payload.get("operator") or "abstain").strip()
    context = str(payload.get("context") or "document").strip()
    cohort = str(scope.get("entity_cohort") or payload.get("entity_cohort") or "unresolved").strip()
    return AcquisitionAction(
        predicate_ids=_as_tuple(scope.get("predicate_ids") or payload.get("predicate_ids")),
        attribute=str(scope.get("attribute") or payload.get("attribute") or ""),
        entity_cohort=cohort if cohort in COHORTS else "unresolved",
        operator=operator if operator in OPERATORS else "abstain",  # type: ignore[arg-type]
        context=context if context in CONTEXTS else "document",  # type: ignore[arg-type]
        model=str(payload.get("model") or ""),
        max_tokens=int(payload.get("max_tokens") or 0),
        reason=str(payload.get("reason") or ""),
    )


def validate_action(
    action: AcquisitionAction,
    predicates: Iterable[AtomicPredicate],
) -> AcquisitionAction:
    """Drop out-of-scope atoms. Invalid operators become abstain."""

    by_id = {pred.pred_id: pred for pred in predicates}
    wanted = [by_id[pred_id] for pred_id in action.predicate_ids if pred_id in by_id]
    if action.attribute:
        wanted = [pred for pred in wanted if pred.attribute == action.attribute]
    if not wanted and action.attribute:
        wanted = [pred for pred in predicates if pred.attribute == action.attribute]
    if action.operator == "grounded_existence":
        wanted = [pred for pred in wanted if is_presence(pred)]
    elif action.operator == "semantic_membership":
        wanted = [pred for pred in wanted if is_membership(pred)]
    elif action.operator != "abstain":
        return AcquisitionAction(
            predicate_ids=(),
            attribute=action.attribute,
            entity_cohort="unresolved",
            operator="abstain",
            context=action.context,
            model=action.model,
            max_tokens=0,
            reason="invalid_operator",
        )
    if action.operator != "abstain" and not wanted:
        return AcquisitionAction(
            predicate_ids=(),
            attribute=action.attribute,
            entity_cohort="unresolved",
            operator="abstain",
            context=action.context,
            model=action.model,
            max_tokens=0,
            reason="empty_scope",
        )
    return AcquisitionAction(
        predicate_ids=tuple(pred.pred_id for pred in wanted),
        attribute=action.attribute or (wanted[0].attribute if wanted else ""),
        entity_cohort="unresolved",
        operator=action.operator,
        context=action.context if action.context in CONTEXTS else "document",
        model=action.model,
        max_tokens=max(0, int(action.max_tokens)),
        reason=action.reason,
    )


def allowed_pred_ids(action: AcquisitionAction, predicates: Iterable[AtomicPredicate]) -> set[str]:
    by_id = {pred.pred_id: pred for pred in predicates}
    allowed: set[str] = set()
    for pred_id in action.predicate_ids:
        pred = by_id.get(pred_id)
        if pred is None:
            continue
        if action.operator == "grounded_existence" and is_presence(pred):
            allowed.add(pred_id)
        elif action.operator == "semantic_membership" and is_membership(pred):
            allowed.add(pred_id)
    return allowed


def cohort_kind_counts(predicates: Iterable[AtomicPredicate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pred in predicates:
        kind = operator_kind(pred)
        counts[kind] = counts.get(kind, 0) + 1
    return counts
