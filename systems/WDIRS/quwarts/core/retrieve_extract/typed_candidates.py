"""Deterministic typed candidates from document structure. No LLM, no corpus names."""

from __future__ import annotations

import re
from typing import Any, Iterable

from quwarts.core.retrieve_extract.index import DocumentIndex
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.retrieve import RetrievalSpec

_TOKEN = re.compile(r"[a-z0-9][a-z0-9]{1,}")
_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "into", "your",
    "are", "was", "were", "been", "have", "has", "not", "use", "used",
    "of", "or", "to", "in", "on", "by", "an", "a",
}
_KV = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9 /&._-]{2,80})\s*(?::|=|\||–|-)\s*(?P<value>[^\n|]{1,120})"
)
_NUM = re.compile(
    r"(?P<num>\(?-?\s*[$€£]?\s*-?\d[\d,]*(?:\.\d+)?\s*(?:%|k|m|bn|b|million|billion|thousand)?\)?)"
)
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_UNIT = re.compile(r"\b(usd|aud|gbp|eur|percent|pct|%|year|fy|million|billion|thousand)\b", re.I)
_PIPE_SPLIT = re.compile(r"\s*\|\s*")


def ident_tokens(text: str) -> list[str]:
    parts = _TOKEN.findall(str(text or "").lower().replace("_", " ").replace("-", " "))
    return [part for part in parts if part not in _STOP and len(part) > 1]


def ident_key(text: str) -> str:
    return " ".join(ident_tokens(text))


def _overlap(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _period(text: str) -> str | None:
    years = _YEAR.findall(text or "")
    return years[-1] if years else None


def _unit(text: str) -> str | None:
    match = _UNIT.search(text or "")
    return match.group(0) if match else None


def _span_at(text: str, start: int, end: int) -> str:
    return text[max(0, start) : min(len(text), end)]


def _candidate(
    *,
    entity_id: str,
    attribute: str,
    raw: str,
    dtype: str,
    span: str,
    digest: str,
    rule: str,
    score: float,
    features: dict[str, Any],
    unit: str | None = None,
    period: str | None = None,
) -> dict[str, Any] | None:
    raw = " ".join(str(raw).split())
    if not raw or not span:
        return None
    if raw.lower() not in span.lower():
        return None
    value, parsed_unit, error = normalize_value(raw, dtype)
    if dtype == "numeric" and error:
        return None
    return {
        "entity_id": entity_id,
        "attribute": attribute,
        "raw_value": raw,
        "normalized_value": value if value is not None else raw,
        "unit": unit or parsed_unit,
        "period": period,
        "source_span": span.strip(),
        "document_hash": digest,
        "extraction_rule": rule,
        "match_score": round(score, 4),
        "features": features,
        "norm_error": error,
        "scalar": rule != "table_header_row",
    }


def _header_score(header: str, spec: RetrievalSpec) -> float:
    tokens = ident_tokens(header)
    attr = ident_tokens(spec.attribute.split(".")[-1])
    desc = ident_tokens(spec.description)
    jacc = max(_overlap(tokens, attr), _overlap(tokens, attr + desc) * 0.85)
    if ident_key(header) == ident_key(spec.attribute.split(".")[-1]):
        jacc = max(jacc, 1.0)
    if spec.literals:
        blob = header.lower()
        if any(str(item).lower() in blob for item in spec.literals if item):
            jacc = max(jacc, 0.55)
    return jacc


def _from_tables(index: DocumentIndex, spec: RetrievalSpec, entity_id: str, dtype: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    lines = index.text.splitlines()
    header_cells: list[str] = []
    header_scores: list[float] = []
    for line in lines:
        if "|" not in line and not re.search(r"\s{2,}\S+\s{2,}", line):
            if line.strip() and _header_score(line, spec) >= 0.55:
                header_cells = [line.strip()]
                header_scores = [_header_score(line, spec)]
            continue
        cells = [part.strip() for part in _PIPE_SPLIT.split(line.strip().strip("|")) if part.strip()]
        if not cells:
            continue
        numeric_cells = [cell for cell in cells if _NUM.search(cell)]
        label_like = len(numeric_cells) <= max(1, len(cells) // 2)
        if label_like and not numeric_cells:
            header_cells = cells
            header_scores = [_header_score(cell, spec) for cell in cells]
            continue
        if not header_cells:
            continue
        best_i = max(range(len(header_cells)), key=lambda i: header_scores[i] if i < len(header_scores) else 0.0)
        score = header_scores[best_i] if best_i < len(header_scores) else 0.0
        if score < 0.45:
            continue
        value = None
        if best_i < len(cells) and cells[best_i] != header_cells[best_i]:
            value = cells[best_i]
        if value is None:
            nums = [cell for cell in cells if _NUM.search(cell)]
            value = nums[-1] if nums else (cells[-1] if cells else None)
        if value is None:
            continue
        num = _NUM.search(value)
        raw = num.group("num") if num and spec.numeric else value
        span = line.strip()
        cand = _candidate(
            entity_id=entity_id,
            attribute=spec.attribute,
            raw=raw,
            dtype=dtype,
            span=span,
            digest=index.digest,
            rule="table_header_row",
            score=score + (0.1 if spec.numeric and num else 0.0),
            features={"header": header_cells[best_i] if best_i < len(header_cells) else "", "n_cells": len(cells)},
            unit=_unit(span),
            period=_period(span) or _period(" ".join(header_cells)),
        )
        if cand:
            out.append(cand)
    return out


def _from_kv(index: DocumentIndex, spec: RetrievalSpec, entity_id: str, dtype: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for match in _KV.finditer(index.text):
        label = match.group("label")
        value = match.group("value").strip()
        score = _header_score(label, spec)
        if score < 0.5:
            continue
        num = _NUM.search(value)
        raw = num.group("num") if num and spec.numeric else value.split("  ")[0].strip()
        if spec.numeric and not num:
            continue
        span = _span_at(index.text, match.start(), match.end())
        cand = _candidate(
            entity_id=entity_id,
            attribute=spec.attribute,
            raw=raw,
            dtype=dtype,
            span=span,
            digest=index.digest,
            rule="key_value",
            score=score,
            features={"label": label},
            unit=_unit(span),
            period=_period(span),
        )
        if cand:
            out.append(cand)
    return out


def _from_nearby_numeric(index: DocumentIndex, spec: RetrievalSpec, entity_id: str, dtype: str) -> list[dict[str, Any]]:
    if not spec.numeric:
        return []
    out: list[dict[str, Any]] = []
    terms = [term for term in spec.terms if len(term) > 2][:12]
    blob = index.text
    lower = blob.lower()
    for term in terms:
        start = 0
        hits = 0
        while hits < 6:
            pos = lower.find(term, start)
            if pos < 0:
                break
            hits += 1
            window = blob[pos : pos + 180]
            num = _NUM.search(window)
            if num:
                span = window[: num.end() + 8]
                cand = _candidate(
                    entity_id=entity_id,
                    attribute=spec.attribute,
                    raw=num.group("num"),
                    dtype=dtype,
                    span=span,
                    digest=index.digest,
                    rule="nearby_numeric",
                    score=0.5 + min(0.3, len(term) / 40.0),
                    features={"term": term},
                    unit=_unit(span),
                    period=_period(span),
                )
                if cand:
                    out.append(cand)
            start = pos + max(len(term), 1)
            if len(out) > 24:
                return out
    return out


def _from_heading(index: DocumentIndex, spec: RetrievalSpec, entity_id: str, dtype: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for section in index.sections:
        heading = str(section.get("heading") or "")
        score = _header_score(heading, spec)
        if score < 0.5:
            continue
        body = index.text[int(section["start"]) : int(section["end"])]
        prose = " ".join(body.split())[:240]
        raw = None
        rule = "heading_adjacent"
        if spec.numeric:
            num = _NUM.search(body[:400])
            if not num:
                continue
            raw = num.group("num")
            rule = "heading_adjacent_numeric"
            prose = body[: num.end() + 20]
        else:
            sentence = re.split(r"(?<=[.?!])\s+", prose)
            raw = (sentence[0] if sentence else prose)[:160]
        cand = _candidate(
            entity_id=entity_id,
            attribute=spec.attribute,
            raw=raw,
            dtype=dtype,
            span=prose[:400],
            digest=index.digest,
            rule=rule,
            score=score,
            features={"heading": heading},
            unit=_unit(prose),
            period=_period(heading) or _period(prose),
        )
        if cand:
            out.append(cand)
    return out


def _from_literals(index: DocumentIndex, spec: RetrievalSpec, entity_id: str, dtype: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    lower = index.text.lower()
    for lit in spec.literals:
        token = str(lit or "").strip()
        if len(token) < 2:
            continue
        pos = lower.find(token.lower())
        if pos < 0:
            continue
        span = _span_at(index.text, pos, pos + len(token))
        cand = _candidate(
            entity_id=entity_id,
            attribute=spec.attribute,
            raw=span,
            dtype=dtype,
            span=span,
            digest=index.digest,
            rule="workload_literal",
            score=0.9,
            features={"literal": token},
            period=_period(_span_at(index.text, max(0, pos - 40), pos + len(token) + 40)),
        )
        if cand:
            out.append(cand)
    return out


def candidates_for_document(
    index: DocumentIndex,
    specs: dict[str, RetrievalSpec],
    dtypes: dict[str, str],
    entity_id: str,
    *,
    per_attr: int = 8,
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for name, spec in specs.items():
        dtype = dtypes.get(name, "string")
        pool = []
        pool.extend(_from_tables(index, spec, entity_id, dtype))
        pool.extend(_from_kv(index, spec, entity_id, dtype))
        pool.extend(_from_literals(index, spec, entity_id, dtype))
        pool.extend(_from_heading(index, spec, entity_id, dtype))
        if spec.numeric and len(pool) < per_attr:
            pool.extend(_from_nearby_numeric(index, spec, entity_id, dtype))
        pool.sort(key=lambda item: (-float(item["match_score"]), item["extraction_rule"], item["raw_value"]))
        seen: set[str] = set()
        kept = 0
        for item in pool:
            key = f"{item['normalized_value']}|{item['source_span'][:80]}"
            if key in seen:
                continue
            seen.add(key)
            found.append(item)
            kept += 1
            if kept >= per_attr:
                break
    return found
