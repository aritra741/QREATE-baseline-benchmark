"""Parse, relocate, and normalize evidence-graph nodes."""

from __future__ import annotations

import json
import re
from typing import Any

from quwarts.core.evidence_graph.config import (
    ALLOWED_ATTRIBUTES,
    COMPONENT_ROLES,
    ENTITY_ROLES,
    STATED,
    TEMPORAL_ROLES,
    VALUE_TYPES,
)

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)
_TRAIL_COMMA = re.compile(r",\s*([}\]])")


def salvage_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    candidates = [raw]
    match = _JSON_BLOCK.search(raw)
    if match:
        candidates.append(match.group(0))
    for item in candidates:
        try:
            payload = json.loads(item)
            if isinstance(payload, dict):
                return payload
            if isinstance(payload, list):
                return {"facts": payload}
        except json.JSONDecodeError:
            cleaned = _TRAIL_COMMA.sub(r"\1", item)
            try:
                payload = json.loads(cleaned)
                if isinstance(payload, dict):
                    return payload
                if isinstance(payload, list):
                    return {"facts": payload}
            except json.JSONDecodeError:
                continue
    return None


def relocate_quote(document: str, quote: str, start: int, end: int, windows: list[tuple[int, int]] | None = None) -> tuple[int, int, bool]:
    if not quote:
        return -1, -1, False
    if 0 <= start < end <= len(document) and document[start:end] == quote:
        return start, end, True
    found: list[int] = []
    cursor = 0
    while True:
        idx = document.find(quote, cursor)
        if idx < 0:
            break
        found.append(idx)
        cursor = idx + max(1, len(quote))
    if not found:
        return start, end, False
    if windows:
        inside = [idx for idx in found if any(lo <= idx < hi for lo, hi in windows)]
        if len(inside) == 1:
            return inside[0], inside[0] + len(quote), True
        if len(inside) > 1:
            return inside[0], inside[0] + len(quote), True
    if len(found) == 1 or windows is None:
        return found[0], found[0] + len(quote), True
    return found[0], found[0] + len(quote), True


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"[|,]", text) if part.strip()]


def _norm_type(value: Any) -> str:
    text = str(value or "string").strip().lower()
    if text in VALUE_TYPES:
        return text
    if text in {"int", "int64"}:
        return "integer"
    if text in {"float", "number"}:
        return "decimal"
    if text in {"cat", "categorical"}:
        return "label"
    return "string"


def _norm_role(value: Any, allowed: tuple[str, ...]) -> str:
    text = str(value or "").strip().lower()
    for item in allowed:
        if item and item == text:
            return item
    return text if text in allowed else ""


def normalize_fact(raw: dict[str, Any], prefix: str, index: int, document: str, windows: list[tuple[int, int]] | None = None) -> dict[str, Any] | None:
    attrs = [name for name in _as_list(raw.get("attribute_candidates") or raw.get("attribute")) if name in ALLOWED_ATTRIBUTES]
    if not attrs:
        return None
    quote = str(raw.get("source_quote") or "")
    stated = str(raw.get("stated_or_inferred") or "stated").strip().lower()
    if stated not in STATED:
        stated = "stated" if quote else "inferred"
    try:
        start = int(raw.get("source_start", -1))
        end = int(raw.get("source_end", -1))
    except (TypeError, ValueError):
        start, end = -1, -1
    valid = False
    if stated == "stated":
        if not quote:
            return None
        start, end, valid = relocate_quote(document, quote, start, end, windows)
        if not valid:
            return None
    fact = {
        "fact_id": str(raw.get("fact_id") or f"{prefix}_{index:02d}"),
        "attribute_candidates": attrs,
        "raw_value": str(raw.get("raw_value") or quote or ""),
        "normalized_value": raw.get("normalized_value"),
        "value_type": _norm_type(raw.get("value_type")),
        "entity_role": _norm_role(raw.get("entity_role"), ENTITY_ROLES),
        "temporal_role": _norm_role(raw.get("temporal_role"), TEMPORAL_ROLES),
        "component_role": _norm_role(raw.get("component_role"), COMPONENT_ROLES),
        "heading": str(raw.get("heading") or ""),
        "source_start": start,
        "source_end": end,
        "source_quote": quote,
        "stated_or_inferred": stated,
        "confidence": float(raw.get("confidence") or 0.0),
        "offset_valid": bool(valid or stated == "inferred"),
    }
    if str(fact["raw_value"]).strip().upper() == "NOT_FOUND":
        return None
    if fact["normalized_value"] is None or fact["normalized_value"] == "":
        fact["normalized_value"] = _default_normalized(fact)
    return fact


def _default_normalized(fact: dict[str, Any]) -> Any:
    raw = str(fact.get("raw_value") or fact.get("source_quote") or "").strip()
    vtype = fact["value_type"]
    if vtype in {"integer", "year"}:
        match = re.search(r"-?\d+", raw.replace(",", ""))
        return int(match.group()) if match else None
    if vtype == "decimal":
        match = re.search(r"-?\d+(?:\.\d+)?", raw.replace(",", ""))
        return float(match.group()) if match else None
    return raw or None


def facts_from_payload(payload: dict[str, Any] | None, prefix: str, document: str, windows: list[tuple[int, int]] | None = None) -> list[dict[str, Any]]:
    if not payload:
        return []
    rows = payload.get("facts")
    if rows is None and all(key in payload for key in ("raw_value", "attribute_candidates")):
        rows = [payload]
    if not isinstance(rows, list):
        return []
    facts = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        fact = normalize_fact(row, prefix, index, document, windows)
        if fact:
            facts.append(fact)
    return facts


def compact_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for fact in facts:
        compact.append(
            {
                "fact_id": fact["fact_id"],
                "attribute_candidates": fact["attribute_candidates"],
                "raw_value": fact["raw_value"],
                "normalized_value": fact["normalized_value"],
                "value_type": fact["value_type"],
                "entity_role": fact["entity_role"],
                "temporal_role": fact["temporal_role"],
                "component_role": fact["component_role"],
                "heading": fact["heading"],
                "source_start": fact["source_start"],
                "source_end": fact["source_end"],
                "source_quote": fact["source_quote"][:240],
                "stated_or_inferred": fact["stated_or_inferred"],
                "confidence": fact["confidence"],
            }
        )
    return compact


def competing_by_attribute(facts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        for name in fact["attribute_candidates"]:
            grouped.setdefault(name, []).append(fact)
    return grouped


def observable_conflicts(facts: list[dict[str, Any]], observables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = competing_by_attribute(facts)
    conflicts = []
    for item in observables:
        name = item["attribute"]
        rows = grouped.get(name) or []
        values = []
        for fact in rows:
            if _usable_for(item, fact):
                values.append((str(fact.get("normalized_value")), fact["fact_id"]))
        distinct = {value for value, _fid in values if value not in {"", "None"}}
        if len(distinct) > 1:
            conflicts.append(
                {
                    "attribute": name,
                    "observable_ids": [item["observable_id"]],
                    "fact_ids": [fid for _value, fid in values],
                    "reason": "competing_normalized_values",
                    "values": sorted(distinct),
                }
            )
    return conflicts


def _usable_for(observable: dict[str, Any], fact: dict[str, Any]) -> bool:
    name = observable["attribute"]
    if name not in fact["attribute_candidates"]:
        return False
    if name == "hearing_year" and fact.get("temporal_role") not in {"", "hearing"}:
        return False
    if name == "case_number" and fact.get("component_role") in {"citation_id", "list_index"}:
        return False
    if name == "first_judge" and fact.get("component_role") == "list_index":
        return False
    if name == "legal_basis_num" and fact.get("component_role") == "citation_id":
        return False
    return True
