"""Deterministic parse, type-valid acceptance, no exact-span rejection."""

from __future__ import annotations

from typing import Any

from quwarts.core.docetl_unit_parity.parse import deterministic_repair, _as_object
from quwarts.core.docetl_unit_parity.schema import QuerySchema
from quwarts.core.retrieve_extract.parse import extract_json, normalize_value

MISSING = {None, "", -1, "-1"}


def _literal_compat(value: Any, literal: str) -> bool:
    text = str(value).strip().lower()
    lit = str(literal).strip().lower()
    if not text or not lit:
        return False
    if lit.startswith("%") and lit.endswith("%") and len(lit) > 2:
        return lit[1:-1] in text
    if lit.startswith("%"):
        return text.endswith(lit[1:])
    if lit.endswith("%"):
        return text.startswith(lit[:-1])
    return text == lit or lit in text or text in lit


def accept_field(raw: Any, dtype: str, literals: list[str], semantic: bool) -> tuple[Any, str | None]:
    if raw in MISSING:
        return None, "missing_marker"
    if isinstance(raw, str) and raw.strip() in {"", "-1", "null", "none"}:
        return None, "missing_marker"
    if isinstance(raw, (int, float)) and raw == -1:
        return None, "missing_marker"
    norm, _unit, err = normalize_value(raw, dtype)
    if err or norm is None:
        return None, f"typed_reject:{err or 'unnormalized'}"
    closed = bool(literals) and all("%" not in str(item) and len(str(item)) <= 24 for item in literals)
    if dtype == "string" and literals and (semantic or closed):
        if any(_literal_compat(norm, lit) for lit in literals) or semantic:
            return norm, None
        return None, "illegal_categorical"
    return norm, None


def parse_completion(raw_text: str, schema: QuerySchema) -> dict[str, Any]:
    repaired = False
    errors: list[str] = []
    try:
        payload = extract_json(raw_text)
    except Exception:
        blob = deterministic_repair(raw_text)
        repaired = blob is not None
        if blob is None:
            payload = None
            errors.append("invalid_json")
        else:
            try:
                payload = extract_json(blob)
            except Exception:
                try:
                    import json

                    payload = json.loads(blob)
                except Exception:
                    payload = None
                    errors.append("invalid_json")
    by_name = _as_object(payload, schema.names) if payload is not None else {}
    items: dict[str, dict[str, Any]] = {}
    accepted: dict[str, Any] = {}
    for item in schema.fields:
        row = by_name.get(item.name)
        raw = row
        evidence = ""
        if isinstance(row, dict) and ("value" in row or "status" in row):
            raw = row.get("value", row.get("raw_value"))
            ev = row.get("evidence")
            evidence = "" if ev in (None, "null") else str(ev)
        value, reason = accept_field(raw, item.dtype, item.literals, item.semantic)
        if value is not None:
            accepted[item.name] = value
        else:
            if payload is None:
                reason = reason or "invalid_json"
            elif item.name not in by_name and row is None:
                reason = "omitted"
        items[item.name] = {
            "raw": None if raw in MISSING else raw,
            "accepted": value,
            "reason": reason,
            "evidence": evidence,
        }
    return {
        "repaired": repaired,
        "malformed": payload is None,
        "accepted": accepted,
        "items": items,
        "errors": errors,
    }
