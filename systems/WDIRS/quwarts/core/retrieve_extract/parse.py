"""Extractor JSON parse, deterministic normalization, and exact-span grounding."""

from __future__ import annotations

import json
import re
from typing import Any

STATUSES = {"found", "not_found", "uncertain"}
_NUM = re.compile(
    r"^\(?-?\s*[$€£]?\s*-?\d[\d,]*(?:\.\d+)?\s*(?:%|k|m|bn|b|million|billion|thousand)?\s*\)?$",
    re.I,
)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_UNIT = re.compile(r"\b(usd|aud|gbp|eur|percent|pct|%|year|fy|million|billion|thousand)\b", re.I)


def extract_json(text: str) -> Any:
    blob = (text or "").strip()
    if blob.startswith("```"):
        blob = re.sub(r"^```(?:json)?\s*", "", blob)
        blob = re.sub(r"\s*```$", "", blob)
    start = blob.find("{")
    if start < 0:
        raise ValueError("no_json_object")
    depth = 0
    for index, char in enumerate(blob[start:], start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(blob[start : index + 1])
    raise ValueError("unbalanced_json")


def normalize_number(text: str) -> tuple[Any, str | None]:
    raw = str(text).strip()
    if not raw:
        return None, "empty"
    negative = raw.startswith("(") and raw.endswith(")")
    body = raw.strip("()").strip()
    unit = None
    match_unit = _UNIT.search(body)
    if match_unit:
        unit = match_unit.group(0).lower()
    cleaned = re.sub(r"[$€£,\s]", "", body)
    suffix = ""
    match = re.search(r"(k|m|bn|b|million|billion|thousand|%)$", cleaned, re.I)
    if match:
        suffix = match.group(1).lower()
        cleaned = cleaned[: match.start()]
    try:
        value: Any = float(cleaned) if "." in cleaned else int(cleaned)
    except ValueError:
        return None, "dtype_coercion"
    scale = {
        "k": 1_000,
        "thousand": 1_000,
        "m": 1_000_000,
        "million": 1_000_000,
        "b": 1_000_000_000,
        "bn": 1_000_000_000,
        "billion": 1_000_000_000,
    }.get(suffix)
    if scale:
        value = float(value) * scale
        unit = unit or suffix
    if suffix == "%":
        unit = unit or "%"
    if negative:
        value = -value
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return value, None


def normalize_value(raw: Any, dtype: str) -> tuple[Any, str | None, str | None]:
    if raw in (None, "", "null", "none"):
        return None, None, None
    text = str(raw).strip()
    unit = None
    if dtype == "numeric" or _NUM.match(text):
        value, error = normalize_number(text)
        match = _UNIT.search(text)
        unit = match.group(0) if match else None
        return value, unit, error
    year = _YEAR.search(text)
    if dtype in {"date", "year"} or (year and len(text) <= 12):
        return (int(year.group(0)) if year else text), None, None
    if len(text) > 400:
        return text[:400], None, "truncated_text"
    return text, None, None


def _contains(haystack: str, needle: str) -> bool:
    return bool(haystack) and bool(needle) and needle.lower() in haystack.lower()


def _span_in_context(span: str, context: str) -> bool:
    return _contains(context, span)


def parse_extraction(
    raw_text: str,
    requested: list[str],
    context: str,
    source_ids: list[str],
    dtypes: dict[str, str],
) -> dict[str, Any]:
    errors: list[str] = []
    def _empty_items(reason: str) -> dict[str, Any]:
        return {
            name: {
                "attribute": name,
                "status": "malformed",
                "raw_value": None,
                "normalized_value": None,
                "unit": None,
                "period": None,
                "evidence": [],
                "errors": [reason],
            }
            for name in requested
        }

    try:
        payload = extract_json(raw_text)
    except Exception as exc:
        reason = f"invalid_json:{exc}"
        return {
            "ok": False,
            "malformed": True,
            "error": reason,
            "items": _empty_items(reason),
            "errors": [reason],
            "grounding_failures": 0,
            "counts": {"found": 0, "not_found": 0, "uncertain": 0, "malformed": len(requested), "grounding_failure": 0},
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "malformed": True,
            "error": "not_object",
            "items": _empty_items("not_object"),
            "errors": ["not_object"],
            "grounding_failures": 0,
            "counts": {"found": 0, "not_found": 0, "uncertain": 0, "malformed": len(requested), "grounding_failure": 0},
        }
    rows = payload.get("attributes")
    if not isinstance(rows, list):
        return {
            "ok": False,
            "malformed": True,
            "error": "missing_attributes",
            "items": _empty_items("missing_attributes"),
            "errors": ["missing_attributes"],
            "grounding_failures": 0,
            "counts": {"found": 0, "not_found": 0, "uncertain": 0, "malformed": len(requested), "grounding_failure": 0},
        }

    by_name: dict[str, dict[str, Any]] = {}
    seen: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            errors.append("non_object_attribute")
            continue
        name = str(row.get("attribute") or "").strip()
        seen.append(name)
        if name in by_name:
            errors.append(f"duplicate:{name}")
            continue
        by_name[name] = row

    requested_set = set(requested)
    if set(by_name) != requested_set:
        missing = sorted(requested_set - set(by_name))
        extra = sorted(set(by_name) - requested_set)
        if missing:
            errors.append("omitted:" + ",".join(missing))
        if extra:
            errors.append("unknown_attribute:" + ",".join(extra))

    items: dict[str, dict[str, Any]] = {}
    grounding_failures = 0
    found = not_found = uncertain = 0
    for name in requested:
        row = by_name.get(name)
        if row is None:
            items[name] = {
                "attribute": name,
                "status": "malformed",
                "raw_value": None,
                "normalized_value": None,
                "unit": None,
                "period": None,
                "evidence": [],
                "errors": ["omitted"],
            }
            continue
        status = str(row.get("status") or "").strip()
        if status not in STATUSES:
            errors.append(f"unknown_status:{name}:{status}")
            items[name] = {
                "attribute": name,
                "status": "malformed",
                "raw_value": row.get("raw_value"),
                "normalized_value": row.get("normalized_value"),
                "unit": row.get("unit"),
                "period": row.get("period"),
                "evidence": row.get("evidence") or [],
                "errors": [f"unknown_status:{status}"],
            }
            continue
        raw_value = row.get("raw_value")
        if raw_value in ("", "null"):
            raw_value = None
        evidence = row.get("evidence") or []
        if not isinstance(evidence, list):
            evidence = []
        spans = []
        for item in evidence:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id") or "")
            span = str(item.get("exact_span") or "")
            spans.append({"source_id": source_id, "exact_span": span})
        norm_error = None
        unit = row.get("unit")
        period = row.get("period")
        normalized = row.get("normalized_value")
        if normalized in ("", "null"):
            normalized = None
        if status == "found" and raw_value not in (None, ""):
            value, parsed_unit, norm_error = normalize_value(raw_value, dtypes.get(name, "string"))
            if value is not None:
                normalized = value
            if parsed_unit and not unit:
                unit = parsed_unit
        elif status in {"not_found", "uncertain"}:
            raw_value = None
            normalized = None
            unit = None
            period = None
            if status == "not_found":
                not_found += 1
            else:
                uncertain += 1
        grounded = False
        if status == "found":
            found += 1
            for item in spans:
                span = item["exact_span"]
                if not span or not _span_in_context(span, context):
                    continue
                if item["source_id"] and source_ids and item["source_id"] not in source_ids:
                    continue
                if raw_value not in (None, "") and (
                    _contains(span, str(raw_value)) or _contains(span, str(normalized) if normalized is not None else "")
                ):
                    grounded = True
                    break
                if normalized is not None and _contains(span, str(normalized)):
                    grounded = True
                    break
            if not grounded:
                errors.append(f"grounding_failure:{name}")
                grounding_failures += 1
        items[name] = {
            "attribute": name,
            "status": status,
            "raw_value": None if raw_value in (None, "") else str(raw_value),
            "normalized_value": normalized,
            "unit": None if unit in (None, "") else str(unit),
            "period": None if period in (None, "") else str(period),
            "evidence": spans,
            "errors": ([norm_error] if norm_error else []) + ([] if status != "found" or grounded else ["grounding_failure"]),
            "grounded": grounded if status == "found" else None,
            "norm_error": norm_error,
        }

    malformed_tokens = (
        "invalid_json",
        "omitted",
        "duplicate",
        "unknown_status",
        "unknown_attribute",
        "missing_attributes",
        "not_object",
    )
    malformed = any(item["status"] == "malformed" for item in items.values()) or any(
        any(token in err for token in malformed_tokens) for err in errors
    )
    return {
        "ok": not malformed and grounding_failures == 0,
        "malformed": malformed,
        "items": items,
        "errors": errors,
        "grounding_failures": grounding_failures,
        "counts": {
            "found": found,
            "not_found": not_found,
            "uncertain": uncertain,
            "malformed": sum(1 for item in items.values() if item["status"] == "malformed"),
            "grounding_failure": grounding_failures,
        },
        "entity_id": payload.get("entity_id") if isinstance(payload, dict) else None,
    }
