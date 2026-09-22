"""Compile finite AST-visible labels. Occurrence in SQL is not evidence of truth."""

from __future__ import annotations

from typing import Any

from sqlglot import exp

from quwarts.core.shared_bundle.inventory import _literals
from quwarts.core.signature import resolve_attribute, select_aliases, table_aliases
from quwarts.core.workload import _default_entity, parse_sql
from quwarts.core.multichannel_candidates.representation import evidence_span, make_candidate


ABSENCE = frozenset({"", "null", "none", "unknown", "n/a", "na"})


def case_output_labels(sql: str, attribute: str) -> list[str]:
    tree = parse_sql(sql)
    aliases = table_aliases(tree)
    default = _default_entity(tree)
    labels: list[str] = []
    for case in tree.find_all(exp.Case):
        names = []
        for column in case.find_all(exp.Column):
            resolved = resolve_attribute(column, aliases, default)
            if resolved is not None:
                names.append(resolved[2])
        if attribute not in names:
            continue
        for clause in case.args.get("ifs") or []:
            labels.extend(_literals(clause.args.get("true")))
            labels.extend(_literals(getattr(clause, "this", None)))
        labels.extend(_literals(case.args.get("default")))
    return [item for item in labels if str(item).strip().lower() not in ABSENCE]


def compile_visible_labels(statements: dict[str, str], records: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, record in records.items():
        equality = [item for item in record.predicate_literals if str(item).strip().lower() not in ABSENCE]
        members = list(record.categorical_literals)
        likes = [item for item in record.categorical_literals if "%" in str(item)]
        case_labels = []
        for qid in record.queries:
            case_labels.extend(case_output_labels(statements[qid], name))
        labels = []
        for item in equality + members + case_labels:
            text = str(item).strip()
            if text and text.lower() not in ABSENCE:
                labels.append(text)
        out[name] = {
            "equality_and_in": list(dict.fromkeys(equality + members)),
            "like_anchors": list(dict.fromkeys(likes)),
            "case_outputs": list(dict.fromkeys(case_labels)),
            "all_labels": list(dict.fromkeys(labels)),
            "keep_null_distinct": True,
        }
    return out


def find_literal_spans(source: str, label: str) -> list[tuple[int, int, str]]:
    if not source or not label:
        return []
    found: list[tuple[int, int, str]] = []
    lower = source.lower()
    needle = label.lower()
    start = 0
    while True:
        index = lower.find(needle, start)
        if index < 0:
            break
        found.append((index, index + len(label), source[index : index + len(label)]))
        start = index + len(label)
        if len(found) >= 4:
            break
    return found


def attach_supported_labels(
    labels: list[str],
    spec: Any,
    document_id: str,
    source: str,
    heading: str = "",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for label in labels:
        spans = find_literal_spans(source, label)
        if not spans:
            continue
        evidence = [evidence_span(document_id, start, end, text) for start, end, text in spans[:2]]
        out.append(
            make_candidate(
                attribute=spec.name,
                value=label,
                derivation="workload_label",
                evidence_spans=evidence,
                document_id=document_id,
                raw_span=label,
                generator_status="verified",
                normalization_trace=["literal_occurs_in_source"],
                heading=heading,
                channel="workload_label",
                kind="workload_label",
                score=0.5,
            )
        )
    return out
