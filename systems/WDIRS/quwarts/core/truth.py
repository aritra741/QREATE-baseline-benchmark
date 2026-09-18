"""Two-column truth. Only sql_truth enters a rewrite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SqlTruth = Literal["TRUE", "FALSE", "NULL"]
ClassifierStatus = Literal["known", "uncertain", "failed", "grounding-abstained", "conflict"]
ABSTAIN_STATUS = frozenset({"uncertain", "failed", "grounding-abstained"})


@dataclass(frozen=True)
class PredicateLabel:
    sql_truth: SqlTruth
    classifier_status: ClassifierStatus
    provenance: tuple[str, ...] = ()
    conflict: bool = False
    alt_sql_truth: SqlTruth | None = None


def sql_from_source(source_is_null: bool, matched: bool | None) -> SqlTruth:
    if source_is_null:
        return "NULL"
    if matched is None:
        return "NULL"
    return "TRUE" if matched else "FALSE"


def label_from_classifier(
    source_is_null: bool,
    matched: bool | None,
    status: ClassifierStatus,
) -> PredicateLabel:
    if source_is_null:
        return PredicateLabel("NULL", status if status != "known" else "known")
    if status == "uncertain":
        return PredicateLabel("NULL", "uncertain")
    if status == "failed":
        return PredicateLabel("NULL", "failed")
    if status == "grounding-abstained":
        return PredicateLabel("NULL", "grounding-abstained")
    if matched is None:
        return PredicateLabel("NULL", "failed")
    return PredicateLabel("TRUE" if matched else "FALSE", "known")


def as_sql_int(value: SqlTruth) -> int | None:
    if value == "TRUE":
        return 1
    if value == "FALSE":
        return 0
    return None


def sql_not(value: SqlTruth) -> SqlTruth:
    if value == "NULL":
        return "NULL"
    return "FALSE" if value == "TRUE" else "TRUE"


def sql_and(left: SqlTruth, right: SqlTruth) -> SqlTruth:
    if left == "FALSE" or right == "FALSE":
        return "FALSE"
    if left == "NULL" or right == "NULL":
        return "NULL"
    return "TRUE"


def sql_or(left: SqlTruth, right: SqlTruth) -> SqlTruth:
    if left == "TRUE" or right == "TRUE":
        return "TRUE"
    if left == "NULL" or right == "NULL":
        return "NULL"
    return "FALSE"


def assert_null_shared(source_is_null: bool, truths: list[SqlTruth]) -> None:
    if not source_is_null:
        return
    if any(item != "NULL" for item in truths):
        raise AssertionError("NULL source must make every derived predicate NULL")


def rewrite_cell(label: PredicateLabel) -> int | None:
    """Only sql_truth enters the rewritten column. Status stays metadata."""

    _ = label.classifier_status
    return as_sql_int(label.sql_truth)


def combine_provenance(old: PredicateLabel, new: PredicateLabel) -> PredicateLabel:
    return PredicateLabel(
        sql_truth=old.sql_truth,
        classifier_status="known",
        provenance=tuple(dict.fromkeys((*old.provenance, *new.provenance))),
        conflict=False,
        alt_sql_truth=None,
    )


def mark_conflict(old: PredicateLabel, new: PredicateLabel) -> PredicateLabel:
    return PredicateLabel(
        sql_truth=old.sql_truth,
        classifier_status="conflict",
        provenance=tuple(dict.fromkeys((*old.provenance, *new.provenance, "conflict"))),
        conflict=True,
        alt_sql_truth=new.sql_truth,
    )


def merge(old: PredicateLabel | None, new: PredicateLabel | None) -> PredicateLabel | None:
    """Non-destructive evidence merge. Abstention never erases established truth."""

    if new is None:
        return old
    if new.sql_truth == "NULL" or new.classifier_status in ABSTAIN_STATUS:
        return old
    if old is None or old.sql_truth == "NULL":
        return new
    if old.sql_truth == new.sql_truth:
        return combine_provenance(old, new)
    return mark_conflict(old, new)


def merge_atoms(
    old: dict[str, PredicateLabel],
    new: dict[str, PredicateLabel],
    allowed: set[str],
) -> dict[str, PredicateLabel]:
    """Merge only the atoms an operator is allowed to write."""

    merged = dict(old)
    for pred_id, label in new.items():
        if pred_id not in allowed:
            continue
        result = merge(old.get(pred_id), label)
        if result is not None:
            merged[pred_id] = result
    return merged


def cells_for_source(
    source_is_null: bool,
    decisions: list[tuple[bool | None, ClassifierStatus]],
) -> list[PredicateLabel]:
    labels = [label_from_classifier(source_is_null, matched, status) for matched, status in decisions]
    assert_null_shared(source_is_null, [item.sql_truth for item in labels])
    return labels
