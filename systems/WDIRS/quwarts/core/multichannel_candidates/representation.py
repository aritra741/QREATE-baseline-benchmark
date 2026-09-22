"""Opaque, provenance-backed candidate records used by every channel."""

from __future__ import annotations

import hashlib
import json
from typing import Any


CHANNELS = ("surface", "normalized", "workload_label", "semantic", "composed")
DERIVATIONS = ("surface", "normalized", "workload_label", "semantic", "composed")
STATUSES = ("proposed", "verified", "uncertain")


def _hash(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def opaque_id(*parts: Any) -> str:
    return "X" + _hash(*parts)[:16]


def evidence_span(document_id: str, start: int, end: int, text: str) -> dict[str, Any]:
    return {
        "document_id": str(document_id),
        "start": int(start),
        "end": int(end),
        "text": str(text or "")[:400],
    }


def make_candidate(
    *,
    attribute: str,
    value: Any,
    derivation: str,
    evidence_spans: list[dict[str, Any]],
    document_id: str,
    raw_span: str = "",
    period: str | None = None,
    unit: str | None = None,
    component_scope: str | None = None,
    generator_status: str = "proposed",
    normalization_trace: list[str] | None = None,
    heading: str = "",
    row_label: str = "",
    column_header: str = "",
    table_title: str = "",
    neighbors: str = "",
    kind: str = "",
    score: float = 0.0,
    eligible: bool = True,
    channel: str | None = None,
) -> dict[str, Any]:
    spans = [dict(item) for item in evidence_spans if item]
    if not spans:
        raise ValueError("every candidate requires at least one evidence span")
    first = spans[0]
    start = int(first.get("start") or 0)
    end = int(first.get("end") or start)
    raw = raw_span or str(first.get("text") or value or "")
    cid = opaque_id(attribute, document_id, derivation, value, start, end, channel or derivation)
    return {
        "id": cid,
        "candidate_id": cid,
        "attribute": attribute,
        "value": value,
        "normalized": value,
        "raw_span": raw[:180],
        "derivation": derivation,
        "channel": channel or derivation,
        "evidence_spans": spans,
        "normalization_trace": list(normalization_trace or []),
        "period": period,
        "unit": unit,
        "component_scope": component_scope,
        "generator_status": generator_status,
        "eligible": bool(eligible),
        "row_label": row_label,
        "column_header": column_header,
        "table_title": table_title,
        "heading": heading,
        "currency": None,
        "start": start,
        "end": end,
        "neighbors": neighbors,
        "local_text": raw[:240],
        "in_c1": False,
        "score": float(score),
        "kind": kind or derivation,
    }


def surface_to_record(item: dict[str, Any], attribute: str, document_id: str, source: str) -> dict[str, Any]:
    start = int(item.get("start") or 0)
    end = int(item.get("end") or start)
    text = str(item.get("raw_span") or "")
    if end <= start and text:
        end = start + len(text)
    span_text = source[start:end] if 0 <= start < len(source) and end <= len(source) else text
    rec = make_candidate(
        attribute=attribute,
        value=item.get("normalized"),
        derivation="surface",
        evidence_spans=[evidence_span(document_id, start, end, span_text or text)],
        document_id=document_id,
        raw_span=text,
        period=item.get("period"),
        unit=item.get("unit"),
        generator_status="verified",
        heading=str(item.get("heading") or ""),
        row_label=str(item.get("row_label") or ""),
        column_header=str(item.get("column_header") or ""),
        table_title=str(item.get("table_title") or ""),
        neighbors=str(item.get("neighbors") or ""),
        kind=str(item.get("kind") or "surface"),
        score=float(item.get("score") or 0.0),
        channel="surface",
    )
    rec["id"] = str(item.get("id") or rec["id"])
    rec["candidate_id"] = rec["id"]
    return rec


def dedup_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in items:
        key = (item.get("derivation"), item.get("normalized"), item.get("start"), item.get("end"), str(item.get("value")))
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)
    return kept


def official_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if item.get("eligible") is not False]


def provenance_ok(item: dict[str, Any]) -> bool:
    spans = item.get("evidence_spans") or []
    if not spans:
        return False
    for span in spans:
        start, end = span.get("start"), span.get("end")
        if start is None or end is None or int(end) < int(start):
            return False
        if not str(span.get("text") or "").strip() and not str(span.get("document_id") or ""):
            return False
    if item.get("derivation") in {"semantic", "composed"} and not spans:
        return False
    return True
