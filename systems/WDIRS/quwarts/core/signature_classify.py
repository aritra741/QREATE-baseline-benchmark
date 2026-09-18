"""Row-local predicate classification. Workload AST only. No gold ontology."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from quwarts.core.signature import AtomicPredicate
from quwarts.core.truth import (
    ClassifierStatus,
    PredicateLabel,
    SqlTruth,
    rewrite_cell,
)

_TRUTH = {
    "TRUE": "TRUE",
    "FALSE": "FALSE",
    "NULL": "NULL",
    "UNKNOWN": "NULL",
    "T": "TRUE",
    "F": "FALSE",
}
_STATUS = {
    "known": "known",
    "uncertain": "uncertain",
    "failed": "failed",
    "grounding-abstained": "grounding-abstained",
    "abstained": "grounding-abstained",
}
_APPLIES = {"true": "TRUE", "false": "FALSE", "unknown": "NULL", "yes": "TRUE", "no": "FALSE"}


@dataclass
class ClassifyResult:
    labels: dict[str, PredicateLabel]
    source: str
    raw: str
    tokens_purpose: str


def _fold(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def value_is_missing(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def emptiness_labels(predicates: Iterable[AtomicPredicate], missing: bool) -> dict[str, PredicateLabel]:
    labels: dict[str, PredicateLabel] = {}
    for pred in predicates:
        if pred.operator == "IS NULL":
            labels[pred.pred_id] = PredicateLabel("TRUE" if missing else "FALSE", "known")
        elif pred.operator == "IS NOT NULL":
            labels[pred.pred_id] = PredicateLabel("FALSE" if missing else "TRUE", "known")
        elif pred.operator == "!=" and pred.literal == "":
            if missing:
                continue
            labels[pred.pred_id] = PredicateLabel("FALSE" if missing else "TRUE", "known")
        elif pred.operator == "=" and pred.literal == "":
            if missing:
                continue
            labels[pred.pred_id] = PredicateLabel("TRUE" if missing else "FALSE", "known")
    return labels


def needs_model(pred: AtomicPredicate) -> bool:
    if pred.operator in {"IS NULL", "IS NOT NULL"}:
        return False
    if pred.operator in {"=", "!="} and pred.literal == "":
        return False
    return True


def predicate_lines(predicates: list[AtomicPredicate]) -> str:
    lines = []
    for index, pred in enumerate(predicates, 1):
        lit = "null" if pred.literal is None else json.dumps(pred.literal)
        trans = ",".join(pred.transforms) if pred.transforms else "none"
        lines.append(f"{index}. op={pred.operator} literal={lit} transforms={trans}")
    return "\n".join(lines)


def value_prompt(attribute: str, value: str, predicates: list[AtomicPredicate]) -> str:
    return (
        "Classify each workload predicate for one extracted attribute value. "
        "A predicate holds if the extracted value satisfies that operator and literal. "
        "If the value is not enough to decide, mark that predicate UNKNOWN / uncertain. "
        "Do not answer queries, aggregates, or CASE branches. "
        "Return JSON: {\"source_present\": true|false, \"labels\": "
        "[{\"i\": 1, \"sql_truth\": \"TRUE|FALSE|NULL\", "
        "\"classifier_status\": \"known|uncertain|failed\"}, ...]}\n"
        f"ATTRIBUTE: {attribute}\n"
        f"VALUE:\n{value}\n"
        f"PREDICATES:\n{predicate_lines(predicates)}\n"
    )


def document_prompt(
    attribute: str,
    value: str | None,
    predicates: list[AtomicPredicate],
    document: str,
) -> str:
    shown = value if value not in (None, "") else "<empty>"
    return (
        "Classify each workload predicate for one attribute of one document. "
        "Use the document. The extracted value may be incomplete. "
        "source_present is provenance only and must not change sql_truth. "
        "Do not answer queries, aggregates, or CASE branches. "
        "Return JSON: {\"source_present\": true|false, \"labels\": "
        "[{\"i\": 1, \"sql_truth\": \"TRUE|FALSE|NULL\", "
        "\"classifier_status\": \"known|uncertain|failed\"}, ...]}\n"
        f"ATTRIBUTE: {attribute}\n"
        f"EXTRACTED_VALUE: {shown}\n"
        f"PREDICATES:\n{predicate_lines(predicates)}\n"
        f"DOCUMENT:\n{document}\n"
    )


def parse_labels(text: str, predicates: list[AtomicPredicate]) -> tuple[bool | None, dict[str, PredicateLabel]]:
    payload = _object(text)
    present = payload.get("source_present")
    if isinstance(present, str):
        present = present.strip().lower() in {"true", "1", "yes"}
    elif present is not None:
        present = bool(present)
    raw_labels = payload.get("labels") or payload.get("predicates") or []
    by_index: dict[int, dict[str, Any]] = {}
    if isinstance(raw_labels, dict):
        raw_labels = [
            {"i": int(key), **(value if isinstance(value, dict) else {"sql_truth": value})}
            for key, value in raw_labels.items()
            if str(key).isdigit()
        ]
    if isinstance(raw_labels, list):
        for index, item in enumerate(raw_labels, 1):
            if not isinstance(item, dict):
                continue
            num = item.get("i") or item.get("index") or index
            try:
                by_index[int(num)] = item
            except (TypeError, ValueError):
                continue
    labels: dict[str, PredicateLabel] = {}
    for index, pred in enumerate(predicates, 1):
        item = by_index.get(index) or {}
        truth = str(item.get("sql_truth") or item.get("truth") or "NULL").strip().upper()
        status = str(item.get("classifier_status") or item.get("status") or "failed").strip().lower()
        sql_truth: SqlTruth = _TRUTH.get(truth, "NULL")  # type: ignore[assignment]
        classifier_status: ClassifierStatus = _STATUS.get(status, "failed")  # type: ignore[assignment]
        if sql_truth == "NULL" and classifier_status == "known":
            classifier_status = "uncertain"
        labels[pred.pred_id] = PredicateLabel(sql_truth, classifier_status)
    # source_present is provenance. It must not gate sql_truth.
    return present, labels


def _object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {}
    try:
        payload = json.loads(cleaned)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            return {}
        try:
            payload = json.loads(match.group())
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}


def labels_to_cells(labels: dict[str, PredicateLabel]) -> dict[str, int | None]:
    return {key: rewrite_cell(value) for key, value in labels.items()}


def v2_prompt(
    attribute: str,
    predicates: list[AtomicPredicate],
    *,
    entity_name: str | None,
    surfaces: list[str],
    document: str | None = None,
) -> str:
    names = entity_name or "<unknown>"
    shown = "; ".join(item for item in surfaces if item) or "<none>"
    extra = f"DOCUMENT:\n{document}\n" if document else ""
    return (
        "Classify whether each concept applies to this entity. "
        "Multiple concepts may be true at once. "
        "Absence of a literal string is not evidence of falsehood and is not SQL NULL. "
        "Infer from the entity name or context when the literal is not written. "
        "applies is the semantic result. basis and status are metadata only. "
        "Do not answer queries, aggregates, or CASE branches.\n"
        "Return JSON: {\"concepts\": [{\"i\": 1, \"applies\": \"true|false|unknown\", "
        "\"basis\": \"explicitly_stated|inferred_from_entity|inferred_from_context\", "
        "\"status\": \"known|uncertain\"}, ...]}\n"
        f"ATTRIBUTE: {attribute}\n"
        f"ENTITY: {names}\n"
        f"SURFACES: {shown}\n"
        f"CONCEPTS:\n{predicate_lines(predicates)}\n"
        f"{extra}"
    )


def parse_v2(text: str, predicates: list[AtomicPredicate]) -> dict[str, PredicateLabel]:
    payload = _object(text)
    raw = payload.get("concepts") or payload.get("labels") or payload.get("predicates") or []
    by_index: dict[int, dict[str, Any]] = {}
    if isinstance(raw, list):
        for index, item in enumerate(raw, 1):
            if not isinstance(item, dict):
                continue
            num = item.get("i") or item.get("index") or index
            try:
                by_index[int(num)] = item
            except (TypeError, ValueError):
                continue
    labels: dict[str, PredicateLabel] = {}
    for index, pred in enumerate(predicates, 1):
        item = by_index.get(index) or {}
        applies = str(item.get("applies") or item.get("sql_truth") or "unknown").strip().lower()
        status = str(item.get("status") or item.get("classifier_status") or "").strip().lower()
        sql_truth: SqlTruth = _APPLIES.get(applies) or _TRUTH.get(applies.upper(), "NULL")  # type: ignore[assignment]
        if not status:
            status = "uncertain" if sql_truth == "NULL" else "known"
        classifier_status: ClassifierStatus = _STATUS.get(status, "failed")  # type: ignore[assignment]
        if classifier_status == "failed" and sql_truth == "NULL" and item:
            classifier_status = "uncertain"
        if not item:
            labels[pred.pred_id] = PredicateLabel("NULL", "failed")
            continue
        labels[pred.pred_id] = PredicateLabel(sql_truth, classifier_status)
    return labels


def needs_document(labels: dict[str, PredicateLabel]) -> bool:
    return any(item.classifier_status in {"uncertain", "failed"} for item in labels.values())


def nonempty_prompt(attribute: str, document: str) -> str:
    return (
        "Find any value of the named attribute in the document. "
        "Return JSON only: {\"value\": <string or null>, "
        "\"span\": <exact document substring or null>}. "
        "The span must be copied verbatim from the document. "
        "If you cannot find a supporting span, both fields are null. "
        "Do not infer that the attribute is absent. Do not invent text. "
        "Do not answer queries, aggregates, or CASE branches.\n"
        f"ATTRIBUTE: {attribute}\n"
        f"DOCUMENT:\n{document}\n"
    )


def parse_nonempty(text: str, document: str) -> PredicateLabel:
    from quwarts.core.extract import find_surface_span

    payload = _object(text)
    span = payload.get("span") or payload.get("surface")
    value = payload.get("value")
    needle = span if span not in (None, "") else value
    if needle in (None, ""):
        return PredicateLabel("NULL", "uncertain", provenance=("nonempty_no_span",))
    if find_surface_span(document or "", str(needle)) is None:
        return PredicateLabel("NULL", "uncertain", provenance=("nonempty_ungrounded",))
    return PredicateLabel("TRUE", "known", provenance=("nonempty_span",))


def membership_prompt(
    attribute: str,
    predicates: list[AtomicPredicate],
    *,
    entity_name: str | None,
    surfaces: list[str],
    document: str | None = None,
) -> str:
    names = entity_name or "<unknown>"
    shown = "; ".join(item for item in surfaces if item) or "<none>"
    extra = f"DOCUMENT:\n{document}\n" if document else ""
    return (
        "Classify whether each concept applies to this entity-attribute pair. "
        "Multiple concepts may be true at once. "
        "Absence of a literal string is not evidence of falsehood and is not SQL NULL. "
        "Infer from the entity or document when the literal is not written. "
        "applies is the semantic result. status is metadata only. "
        "Do not answer queries, aggregates, or CASE branches.\n"
        "Return JSON: {\"concepts\": [{\"i\": 1, \"applies\": \"true|false|unknown\", "
        "\"status\": \"known|uncertain\"}, ...]}\n"
        f"ATTRIBUTE: {attribute}\n"
        f"ENTITY: {names}\n"
        f"SURFACES: {shown}\n"
        f"CONCEPTS:\n{predicate_lines(predicates)}\n"
        f"{extra}"
    )
