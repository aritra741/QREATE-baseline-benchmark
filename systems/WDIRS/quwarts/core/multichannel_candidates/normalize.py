"""Typed, replayable transforms. No model calls and no corpus word lists."""

from __future__ import annotations

import re
from typing import Any

from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.multichannel_candidates.representation import evidence_span, make_candidate

_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_DATE = re.compile(
    r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+((?:19|20)\d{2})\b|\b((?:19|20)\d{2})[-/](\d{1,2})[-/](\d{1,2})\b"
)
_ORDINAL = re.compile(r"\b(\d+)(?:st|nd|rd|th)\b", re.I)
_WS = re.compile(r"\s+")
_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/#:-]{1,}")
_CITE = re.compile(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)\s+v\.?\s+([A-Z][A-Za-z0-9'&. -]{2,80})")
_SECTION = re.compile(r"\b(?:s(?:ection)?\.?|sec\.?)\s*(\d+[A-Za-z]?)\b", re.I)
_MULTI = re.compile(r"semicolon|multiple values|multi[_ -]?str|\|\|", re.I)


def _year_from(text: str) -> str | None:
    found = _YEAR.findall(text or "")
    return found[-1] if found else None


def _norm_ws(text: str) -> str:
    return _WS.sub(" ", str(text or "")).strip(" \t\n\r\"'`.,;")


def _citation(text: str) -> str | None:
    match = _CITE.search(text or "")
    if not match:
        return None
    left = _norm_ws(match.group(1))
    right = _norm_ws(match.group(2))
    return f"{left} v {right}"


def allows_multi(description: str, value_type: str = "") -> bool:
    return bool(_MULTI.search(description or "") or str(value_type).lower() in {"multi_str", "list"})


def expand_normalized(
    surface: list[dict[str, Any]],
    spec: Any,
    document_id: str,
    source: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in surface:
        raw = str(item.get("raw_span") or item.get("value") or "")
        start = int(item.get("start") or 0)
        end = int(item.get("end") or start + len(raw))
        span = evidence_span(document_id, start, end, source[start:end] if 0 <= start < end <= len(source) else raw)
        base = {
            "attribute": spec.name,
            "document_id": document_id,
            "evidence_spans": [span],
            "heading": str(item.get("heading") or ""),
            "row_label": str(item.get("row_label") or ""),
            "column_header": str(item.get("column_header") or ""),
            "table_title": str(item.get("table_title") or ""),
            "neighbors": str(item.get("neighbors") or ""),
            "kind": "normalized",
            "score": float(item.get("score") or 0.0),
            "generator_status": "verified",
            "channel": "normalized",
        }
        year = _year_from(raw)
        if year and (spec.dtype == "numeric" or "year" in spec.name.lower() or "year" in (spec.official_description or "").lower()):
            typed, _, err = normalize_value(year, spec.dtype)
            if not err and typed is not None:
                out.append(
                    make_candidate(
                        value=typed,
                        derivation="normalized",
                        raw_span=year,
                        period=year,
                        normalization_trace=["extract_year"],
                        **base,
                    )
                )
        date = _DATE.search(raw)
        if date:
            year = date.group(3) or date.group(4)
            if year:
                typed, _, err = normalize_value(year, spec.dtype)
                if not err and typed is not None:
                    out.append(
                        make_candidate(
                            value=typed,
                            derivation="normalized",
                            raw_span=date.group(0),
                            period=year,
                            normalization_trace=["date_to_year"],
                            **base,
                        )
                    )
        for match in _ORDINAL.finditer(raw):
            typed, _, err = normalize_value(match.group(1), spec.dtype)
            if not err and typed is not None:
                out.append(
                    make_candidate(
                        value=typed,
                        derivation="normalized",
                        raw_span=match.group(0),
                        normalization_trace=["ordinal_to_int"],
                        **base,
                    )
                )
        typed, unit, err = normalize_value(raw, spec.dtype)
        if not err and typed is not None and typed != item.get("normalized"):
            out.append(
                make_candidate(
                    value=typed,
                    derivation="normalized",
                    raw_span=raw,
                    unit=unit or item.get("unit"),
                    period=item.get("period"),
                    normalization_trace=["typed_normalize"],
                    **base,
                )
            )
        compact = _norm_ws(raw)
        if compact and compact != raw:
            typed, _, err = normalize_value(compact, spec.dtype)
            value = typed if not err and typed is not None else compact
            out.append(
                make_candidate(
                    value=value,
                    derivation="normalized",
                    raw_span=compact,
                    period=item.get("period") or _year_from(compact),
                    normalization_trace=["whitespace_punctuation"],
                    **base,
                )
            )
        cite = _citation(raw)
        if cite:
            out.append(
                make_candidate(
                    value=cite,
                    derivation="normalized",
                    raw_span=cite,
                    normalization_trace=["citation_whitespace"],
                    **base,
                )
            )
        section = _SECTION.search(raw)
        if section:
            typed, _, err = normalize_value(section.group(1), spec.dtype)
            if not err and typed is not None:
                out.append(
                    make_candidate(
                        value=typed,
                        derivation="normalized",
                        raw_span=section.group(0),
                        normalization_trace=["section_number"],
                        **base,
                    )
                )
        if allows_multi(spec.official_description, getattr(spec, "sql_type", "")):
            parts = [part.strip() for part in re.split(r"[;|]|,", compact) if part.strip()]
            if len(parts) > 1:
                joined = "; ".join(parts)
                out.append(
                    make_candidate(
                        value=joined,
                        derivation="normalized",
                        raw_span=joined,
                        normalization_trace=["delimiter_join"],
                        **base,
                    )
                )
                for part in parts:
                    typed, _, err = normalize_value(part, spec.dtype)
                    value = typed if not err and typed is not None else part
                    out.append(
                        make_candidate(
                            value=value,
                            derivation="normalized",
                            raw_span=part,
                            normalization_trace=["delimiter_split"],
                            **base,
                        )
                    )
    return out


def compose_deterministic(
    surface: list[dict[str, Any]],
    spec: Any,
    document_id: str,
    source: str,
) -> list[dict[str, Any]]:
    if not allows_multi(spec.official_description, getattr(spec, "sql_type", "")):
        return []
    spans = []
    values = []
    for item in surface:
        raw = str(item.get("normalized") or item.get("raw_span") or "").strip()
        if not raw:
            continue
        start = int(item.get("start") or 0)
        end = int(item.get("end") or start + len(raw))
        spans.append(evidence_span(document_id, start, end, source[start:end] if 0 <= start < end <= len(source) else raw))
        values.append(raw)
    if len(values) < 2:
        return []
    joined = "; ".join(dict.fromkeys(values))
    return [
        make_candidate(
            attribute=spec.name,
            value=joined,
            derivation="composed",
            evidence_spans=spans,
            document_id=document_id,
            raw_span=joined,
            generator_status="verified",
            normalization_trace=["join_independent_spans"],
            channel="composed",
            heading="",
            kind="composed",
            score=0.0,
        )
    ]


def replay_trace(value: Any, trace: list[str], raw: str, dtype: str) -> Any:
    current = raw
    for step in trace:
        if step == "extract_year":
            current = _year_from(str(current)) or current
        elif step == "date_to_year":
            match = _DATE.search(str(current))
            current = (match.group(3) or match.group(4)) if match else current
        elif step == "ordinal_to_int":
            match = _ORDINAL.search(str(current))
            current = match.group(1) if match else current
        elif step == "whitespace_punctuation":
            current = _norm_ws(str(current))
        elif step == "citation_whitespace":
            current = _citation(str(current)) or current
        elif step == "typed_normalize":
            typed, _, err = normalize_value(current, dtype)
            current = typed if not err and typed is not None else current
        elif step == "delimiter_join":
            parts = [part.strip() for part in re.split(r"[;|]|,", str(current)) if part.strip()]
            current = "; ".join(parts) if parts else current
        elif step == "delimiter_split":
            current = current
    typed, _, err = normalize_value(current, dtype)
    return typed if not err and typed is not None else current
