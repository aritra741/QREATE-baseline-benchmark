"""Scalar realizability over signatures. No gold, no corpus names."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from quwarts.core.signature import AtomicPredicate


def is_presence(pred: AtomicPredicate) -> bool:
    return pred.operator == "!=" and pred.literal == ""


def is_absence(pred: AtomicPredicate) -> bool:
    return pred.operator == "=" and pred.literal == ""


def is_membership(pred: AtomicPredicate) -> bool:
    if pred.operator == "LIKE":
        return True
    if pred.operator in {"=", "IN"} and pred.literal not in (None, ""):
        return True
    return False


def is_null_test(pred: AtomicPredicate) -> bool:
    return pred.operator in {"IS NULL", "IS NOT NULL"}


def is_numeric_compare(pred: AtomicPredicate) -> bool:
    return pred.operator in {">", ">=", "<", "<=", "BETWEEN"}


def is_variable_compare(pred: AtomicPredicate) -> bool:
    return pred.operator == "VAR"


def is_supported_signature(pred: AtomicPredicate) -> bool:
    return is_presence(pred) or is_membership(pred)


def operator_kind(pred: AtomicPredicate) -> str:
    if is_presence(pred):
        return "presence"
    if is_membership(pred):
        return "membership"
    if is_absence(pred):
        return "absence"
    if is_null_test(pred):
        return "null_test"
    if is_numeric_compare(pred):
        return "numeric"
    if is_variable_compare(pred):
        return "variable"
    return "unsupported"


def live_predicates(predicates: Iterable[AtomicPredicate]) -> list[AtomicPredicate]:
    """Presence and membership only. Other forms stay on the original column."""

    return [pred for pred in predicates if is_supported_signature(pred)]


def close_attribute(
    truths: dict[str, int | None],
    predicates: Iterable[AtomicPredicate],
) -> tuple[dict[str, int | None], list[str]]:
    """Force a row-local signature into a state a scalar source can produce.

    LIKE=TRUE => nonempty=TRUE.
    nonempty=FALSE => every LIKE=FALSE.
    Classifier uncertainty is overwritten only when a confident membership
    forces relational nonemptiness.
    """

    preds = list(predicates)
    closed = dict(truths)
    violations: list[str] = []
    members = [p for p in preds if is_membership(p)]
    presence = [p for p in preds if is_presence(p)]
    any_like_true = any(closed.get(p.pred_id) == 1 for p in members)
    any_like_null = any(closed.get(p.pred_id) is None for p in members)
    if any_like_true:
        for pred in presence:
            if closed.get(pred.pred_id) != 1:
                violations.append("membership_true_nonempty_not_true")
                closed[pred.pred_id] = 1
    nonempty_false = any(closed.get(p.pred_id) == 0 for p in presence)
    if nonempty_false and any_like_true:
        violations.append("nonempty_false_with_membership_true")
        for pred in presence:
            closed[pred.pred_id] = 1
    elif nonempty_false:
        for pred in members:
            if closed.get(pred.pred_id) == 1:
                violations.append("nonempty_false_membership_true")
                closed[pred.pred_id] = 0
            elif closed.get(pred.pred_id) is None:
                closed[pred.pred_id] = 0
    _ = any_like_null
    return closed, violations


def audit_rows(
    rows: list[dict[str, int | None]],
    predicates: Iterable[AtomicPredicate],
) -> dict:
    preds = list(predicates)
    by_attr: dict[str, list[AtomicPredicate]] = defaultdict(list)
    for pred in preds:
        by_attr[pred.attribute].append(pred)
    n_illegal = 0
    kinds: dict[str, int] = defaultdict(int)
    repaired = 0
    for row in rows:
        illegal = False
        for attr, group in by_attr.items():
            subset = {p.pred_id: row.get(p.pred_id) for p in group}
            _, violations = close_attribute(subset, group)
            if violations:
                illegal = True
                for item in violations:
                    kinds[item] += 1
                repaired += 1
        if illegal:
            n_illegal += 1
    return {
        "n_rows": len(rows),
        "n_illegal_rows": n_illegal,
        "n_attribute_repairs": repaired,
        "violation_kinds": dict(kinds),
    }
