"""Deterministic parse, JSON repair, type normalization, and grounding."""

from __future__ import annotations

import json
import re
from typing import Any

from quwarts.core.docetl_unit_parity.schema import QuerySchema
from quwarts.core.retrieve_extract.parse import extract_json, normalize_value

STATUSES = {"found", "not_found", "uncertain"}
_TRAIL = re.compile(r",(\s*[}\]])")
_SINGLE = re.compile(r"(?<!\\)'")


def deterministic_repair(text: str) -> str | None:
    blob = (text or "").strip()
    if not blob:
        return None
    if blob.startswith("```"):
        blob = re.sub(r"^```(?:json)?\s*", "", blob)
        blob = re.sub(r"\s*```$", "", blob)
    blob = _TRAIL.sub(r"\1", blob)
    try:
        extract_json(blob)
        return blob
    except Exception:
        pass
    try:
        json.loads(blob)
        return blob
    except Exception:
        pass
    swapped = blob
    if swapped.count("'") >= 2 and swapped.count('"') < 2:
        swapped = swapped.replace("'", '"')
        try:
            extract_json(swapped)
            return swapped
        except Exception:
            pass
    start = blob.find("{")
    end = blob.rfind("}")
    if start >= 0 and end > start:
        clipped = _TRAIL.sub(r"\1", blob[start : end + 1])
        try:
            extract_json(clipped)
            return clipped
        except Exception:
            try:
                json.loads(clipped)
                return clipped
            except Exception:
                return clipped
    return None


def _as_object(payload: Any, requested: list[str]) -> dict[str, Any]:
    if isinstance(payload, dict) and "attributes" in payload and isinstance(payload["attributes"], list):
        out = {}
        for row in payload["attributes"]:
            if isinstance(row, dict) and row.get("attribute"):
                out[str(row["attribute"])] = row
        return out
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        out = {}
        for row in payload:
            if isinstance(row, dict) and row.get("attribute"):
                out[str(row["attribute"])] = row
        return out
    return {}


def _field_entry(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"value": None, "status": "malformed", "evidence": "", "raw": row}
    if "status" in row or "value" in row or "raw_value" in row:
        value = row.get("value", row.get("raw_value"))
        status = str(row.get("status") or "").strip()
        evidence = row.get("evidence")
        if isinstance(evidence, list):
            spans = [str(item.get("exact_span") or "") for item in evidence if isinstance(item, dict)]
            evidence = " ".join(part for part in spans if part)
        evidence = "" if evidence in (None, "null") else str(evidence)
        return {"value": value, "status": status, "evidence": evidence, "raw": row}
    if set(row) <= {"value", "status", "evidence"}:
        return {
            "value": row.get("value"),
            "status": str(row.get("status") or ""),
            "evidence": str(row.get("evidence") or ""),
            "raw": row,
        }
    return {"value": None, "status": "malformed", "evidence": "", "raw": row}


def parse_map(raw_text: str, schema: QuerySchema, context: str) -> dict[str, Any]:
    requested = schema.names
    semantic = schema.semantic_fields
    items: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    try:
        payload = extract_json(raw_text)
    except Exception as exc:
        repaired = deterministic_repair(raw_text)
        if repaired is None:
            payload = None
            errors.append(f"invalid_json:{exc}")
        else:
            try:
                payload = extract_json(repaired)
            except Exception as exc2:
                try:
                    payload = json.loads(repaired)
                except Exception:
                    payload = None
                    errors.append(f"invalid_json:{exc2}")
    by_name = _as_object(payload, requested) if payload is not None else {}
    found = not_found = uncertain = malformed = grounded_stated = inferred_semantic = 0
    for name in requested:
        row = by_name.get(name)
        if row is None:
            items[name] = {
                "attribute": name,
                "raw_value": None,
                "normalized_value": None,
                "status": "malformed" if payload is None else "not_found",
                "evidence": "",
                "grounding": "missing",
                "kind": "semantic" if name in semantic else "stated",
                "failure": "omitted" if payload is not None else "invalid_json",
            }
            if payload is None:
                malformed += 1
            else:
                not_found += 1
                errors.append(f"omitted:{name}")
            continue
        entry = _field_entry(row)
        status = entry["status"] if entry["status"] in STATUSES else ""
        raw_value = entry["value"]
        if raw_value in ("", "null", "none"):
            raw_value = None
        evidence = entry["evidence"]
        kind = "semantic" if name in semantic else "stated"
        if status not in STATUSES:
            items[name] = {
                "attribute": name,
                "raw_value": None if raw_value in (None, "") else str(raw_value),
                "normalized_value": None,
                "status": "malformed",
                "evidence": evidence,
                "grounding": "invalid_status",
                "kind": kind,
                "failure": f"unknown_status:{status}",
            }
            malformed += 1
            errors.append(f"unknown_status:{name}:{status}")
            continue
        if status in {"not_found", "uncertain"}:
            items[name] = {
                "attribute": name,
                "raw_value": None,
                "normalized_value": None,
                "status": status,
                "evidence": evidence,
                "grounding": "abstain",
                "kind": kind,
                "failure": None,
            }
            if status == "not_found":
                not_found += 1
            else:
                uncertain += 1
            continue
        normalized, _unit, norm_error = normalize_value(raw_value, schema.dtypes.get(name, "string"))
        if raw_value in (None, "") and normalized is None:
            items[name] = {
                "attribute": name,
                "raw_value": None,
                "normalized_value": None,
                "status": "uncertain",
                "evidence": evidence,
                "grounding": "empty_found",
                "kind": kind,
                "failure": "found_without_value",
            }
            uncertain += 1
            errors.append(f"found_without_value:{name}")
            continue
        grounded = "ungrounded"
        failure = None
        keep = normalized if normalized is not None else raw_value
        if kind == "stated":
            needle = str(raw_value if raw_value not in (None, "") else keep)
            in_evidence = bool(evidence) and needle.lower() in evidence.lower()
            in_context = bool(evidence) and evidence.lower() in context.lower()
            if in_evidence and in_context:
                grounded = "stated_span"
                grounded_stated += 1
            else:
                failure = "stated_span_failed"
                keep = None
                grounded = "rejected"
                errors.append(f"grounding_failure:{name}")
        else:
            if evidence and evidence.lower() in context.lower():
                grounded = "semantic_provenance"
            elif evidence:
                grounded = "semantic_unmatched_span"
            else:
                grounded = "semantic_inferred"
            inferred_semantic += 1
        items[name] = {
            "attribute": name,
            "raw_value": None if raw_value in (None, "") else str(raw_value),
            "normalized_value": keep,
            "status": status if keep is not None or kind == "semantic" else "uncertain",
            "evidence": evidence,
            "grounding": grounded,
            "kind": kind,
            "failure": failure or norm_error,
        }
        if items[name]["normalized_value"] is not None:
            found += 1
        elif items[name]["status"] == "uncertain":
            uncertain += 1
    extra = sorted(set(by_name) - set(requested) - {"attributes", "entity_id"})
    if extra:
        errors.append("unknown_attribute:" + ",".join(extra))
    malformed_flag = payload is None or any(item["status"] == "malformed" for item in items.values())
    return {
        "ok": not malformed_flag and not any(item.get("failure") == "stated_span_failed" for item in items.values()),
        "malformed": malformed_flag,
        "items": items,
        "errors": errors,
        "counts": {
            "found": found,
            "not_found": not_found,
            "uncertain": uncertain,
            "malformed": malformed,
            "grounded_stated": grounded_stated,
            "inferred_semantic": inferred_semantic,
        },
    }


def merge_partial(primary: dict[str, Any], secondary: dict[str, Any], schema: QuerySchema) -> dict[str, Any]:
    items = dict(primary.get("items") or {})
    other = secondary.get("items") or {}
    for name in schema.names:
        current = items.get(name) or {}
        if current.get("status") == "malformed" or current.get("normalized_value") is None and current.get("status") not in STATUSES:
            if name in other and other[name].get("status") in STATUSES:
                items[name] = other[name]
    merged = dict(primary)
    merged["items"] = items
    merged["malformed"] = any(item.get("status") == "malformed" for item in items.values())
    merged["ok"] = not merged["malformed"]
    return merged
