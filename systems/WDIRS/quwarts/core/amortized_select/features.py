"""Deterministic unlabeled candidate features. No gold or query literals."""

from __future__ import annotations

import re
from typing import Any

from quwarts.core.amortized_select.config import SOURCE_KIND
from quwarts.core.shared_bundle.context_blocks import tokens_of
from quwarts.experiments.extract_util import field_terms

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_CODE = re.compile(r"^[A-Z]{2,6}$")
_SCOPE_TOTAL = frozenset({"total", "totals", "consolidated", "consolidation", "overall", "aggregate"})
_SCOPE_SEGMENT = frozenset({"segment", "segments", "division", "divisions", "subsidiary", "subsidiaries"})
_SCOPE_COMPONENT = frozenset({"component", "including", "ofwhich", "portion", "part"})


def _norm_tokens(text: str) -> list[str]:
    return [tok for tok in tokens_of(text or "") + field_terms(text or "") if tok]


def value_shape(raw: str, normalized: Any) -> str:
    text = str(raw or "").strip()
    if isinstance(normalized, (int, float)) or re.fullmatch(r"\(?-?[\d,]+(?:\.\d+)?%?\)?", text):
        return "percent" if "%" in text else "number"
    compact = re.sub(r"[^A-Za-z]", "", text)
    if compact and _CODE.match(compact) and len(text.split()) <= 2:
        return "short_code"
    words = [part for part in re.split(r"\s+", text) if part]
    if len(words) >= 2 and sum(1 for part in words if part[:1].isupper()) >= 2:
        return "full_legal_name"
    return "text"


def scope_role(*parts: str) -> str:
    toks = set()
    for part in parts:
        toks.update(_norm_tokens(part))
    if toks & _SCOPE_TOTAL:
        return "consolidated" if toks & {"consolidated", "consolidation"} else "total"
    if toks & _SCOPE_SEGMENT:
        return "segment"
    if toks & _SCOPE_COMPONENT:
        return "component"
    return "entity_level"


def position_bin(start: int, doc_len: int) -> str:
    if doc_len <= 0:
        return "unknown"
    frac = max(0.0, min(1.0, start / doc_len))
    if frac < 0.33:
        return "early"
    if frac < 0.67:
        return "middle"
    return "late"


def lexical_scores(spec_tokens: set[str], item: dict[str, Any]) -> dict[str, float]:
    def score(text: str) -> float:
        have = set(_norm_tokens(text))
        if not spec_tokens or not have:
            return 0.0
        return len(spec_tokens & have) / len(spec_tokens | have)

    fields = {
        "row_label": score(str(item.get("row_label") or "")),
        "column_header": score(str(item.get("column_header") or "")),
        "table_title": score(str(item.get("table_title") or "")),
        "section_title": score(str(item.get("heading") or "")),
        "raw": score(str(item.get("raw_span") or "")),
    }
    fields["max"] = max(fields.values()) if fields else 0.0
    return fields


def annotate_candidate(item: dict[str, Any], spec_tokens: set[str], doc_len: int, occurrence: int) -> dict[str, Any]:
    raw = str(item.get("raw_span") or "")
    shape = value_shape(raw, item.get("normalized"))
    source = SOURCE_KIND.get(str(item.get("kind") or ""), "paragraph")
    lex = lexical_scores(spec_tokens, item)
    return {
        "id": item.get("id"),
        "raw_span": raw,
        "value_shape": shape,
        "normalized_is_number": isinstance(item.get("normalized"), (int, float)),
        "row_label": item.get("row_label") or "",
        "column_header": item.get("column_header") or "",
        "table_title": item.get("table_title") or "",
        "section_title": item.get("heading") or "",
        "period": item.get("period") or "",
        "unit": item.get("unit") or "",
        "currency": item.get("currency") or "",
        "document_position": position_bin(int(item.get("start") or 0), doc_len),
        "start": int(item.get("start") or 0),
        "source_type": source,
        "scope_role": scope_role(
            str(item.get("row_label") or ""),
            str(item.get("column_header") or ""),
            str(item.get("table_title") or ""),
            str(item.get("heading") or ""),
        ),
        "lexical": lex,
        "occurrence_count": int(occurrence),
        "kind": item.get("kind") or "",
    }


def spec_tokens(name: str, description: str) -> set[str]:
    return set(field_terms(name) + tokens_of(description or ""))


def occurrence_map(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in candidates:
        key = str(item.get("raw_span") or "")
        counts[key] = counts.get(key, 0) + 1
    return counts


def annotate_set(row: dict[str, Any], spec_tokens_set: set[str], doc_len: int) -> list[dict[str, Any]]:
    counts = occurrence_map(row.get("candidates") or [])
    return [
        annotate_candidate(item, spec_tokens_set, doc_len, counts.get(str(item.get("raw_span") or ""), 1))
        for item in row.get("candidates") or []
    ]


def card_line(feat: dict[str, Any], include_raw: bool = True) -> str:
    raw = f" raw={feat['raw_span']};" if include_raw else ""
    return (
        f"{feat['id']}:{raw} shape={feat['value_shape']}; row={feat['row_label']}; "
        f"header={feat['column_header']}; title={feat['table_title']}; "
        f"section={feat['section_title']}; period={feat['period'] or 'unknown'}; "
        f"unit={feat['unit'] or 'unknown'}; currency={feat['currency'] or 'unspecified'}; "
        f"pos={feat['document_position']}; source={feat['source_type']}; "
        f"scope={feat['scope_role']}; lex={feat['lexical']['max']:.2f}; n={feat['occurrence_count']}"
    )
