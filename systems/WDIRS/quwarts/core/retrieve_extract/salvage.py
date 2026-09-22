"""Conservative zero-token salvage of extractor JSON. Never invents fields."""

from __future__ import annotations

import json
import re
from typing import Any

from quwarts.core.retrieve_extract.parse import STATUSES, normalize_value

FAILURE_CLASSES = (
    "wrapper/prose",
    "truncated JSON",
    "quote/comma/bracket",
    "missing requested attribute",
    "duplicate attribute",
    "invalid status",
    "valid partial response",
    "unrecoverable",
)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I | re.M)
_TRAIL_COMMA = re.compile(r",(\s*[}\]])")
_ATTR_KEY = re.compile(r'\{\s*"attribute"\s*:\s*"([^"]+)"')


def _strip_wrapper(text: str) -> tuple[str, list[str]]:
    steps: list[str] = []
    blob = (text or "").strip()
    if not blob:
        return "", steps
    if blob.startswith("```") or "```" in blob[:20]:
        cleaned = _FENCE.sub("", blob).strip()
        if cleaned != blob:
            steps.append("strip_markdown_fence")
            blob = cleaned
    start = blob.find("{")
    arr = blob.find("[")
    if start < 0 and arr < 0:
        return blob, steps
    if 0 <= arr < start or start < 0:
        if arr > 0:
            steps.append("strip_leading_prose")
        return blob[arr:], steps
    if start > 0:
        steps.append("strip_leading_prose")
    return blob[start:], steps


def _outermost(text: str) -> tuple[str, str | None]:
    start_obj = text.find("{")
    start_arr = text.find("[")
    if start_obj < 0 and start_arr < 0:
        return text, None
    if start_arr >= 0 and (start_obj < 0 or start_arr < start_obj):
        opener, closer, start = "[", "]", start_arr
    else:
        opener, closer, start = "{", "}", start_obj
    depth = 0
    in_str = False
    esc = False
    for index, char in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif char == "\\":
                esc = True
            elif char == '"':
                in_str = False
            continue
        if char == '"':
            in_str = True
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1], None
    return text[start:], "truncated JSON"


def _repair_punctuation(text: str) -> tuple[str, list[str]]:
    steps: list[str] = []
    blob = _TRAIL_COMMA.sub(r"\1", text)
    if blob != text:
        steps.append("strip_trailing_comma")
    quote_count = blob.count('"')
    if quote_count % 2 == 1 and blob.rstrip().endswith('"'):
        blob = blob + '"'
        steps.append("close_dangling_quote")
    opens = {"{": 0, "[": 0}
    closes = {"}": "{", "]": "["}
    in_str = False
    esc = False
    for char in blob:
        if in_str:
            if esc:
                esc = False
            elif char == "\\":
                esc = True
            elif char == '"':
                in_str = False
            continue
        if char == '"':
            in_str = True
        elif char in opens:
            opens[char] += 1
        elif char in closes:
            opens[closes[char]] = max(0, opens[closes[char]] - 1)
    if in_str:
        blob += '"'
        steps.append("close_unclosed_string")
        opens = {"{": 0, "[": 0}
        in_str = False
        esc = False
        for char in blob:
            if in_str:
                if esc:
                    esc = False
                elif char == "\\":
                    esc = True
                elif char == '"':
                    in_str = False
                continue
            if char == '"':
                in_str = True
            elif char in opens:
                opens[char] += 1
            elif char in closes:
                opens[closes[char]] = max(0, opens[closes[char]] - 1)
    suffix = "]" * opens["["] + "}" * opens["{"]
    if suffix:
        blob += suffix
        steps.append("close_unbalanced_brackets")
    return blob, steps


def _parse_attr_objects(text: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for match in _ATTR_KEY.finditer(text):
        start = match.start()
        depth = 0
        in_str = False
        esc = False
        end = None
        for index, char in enumerate(text[start:], start):
            if in_str:
                if esc:
                    esc = False
                elif char == "\\":
                    esc = True
                elif char == '"':
                    in_str = False
                continue
            if char == '"':
                in_str = True
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            continue
        blob = text[start:end]
        try:
            payload = json.loads(blob)
        except json.JSONDecodeError:
            repaired, _ = _repair_punctuation(blob)
            try:
                payload = json.loads(repaired)
            except json.JSONDecodeError:
                continue
        if isinstance(payload, dict) and payload.get("attribute"):
            objects.append(payload)
    return objects


def _loads(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def salvage_completion(raw: str, requested: list[str]) -> dict[str, Any]:
    transformations: list[str] = []
    classes: list[str] = []
    original = raw or ""
    stripped, wrap_steps = _strip_wrapper(original)
    transformations.extend(wrap_steps)
    if wrap_steps:
        classes.append("wrapper/prose")
    if not stripped.strip():
        return {
            "ok": False,
            "parseable_unmodified": False,
            "repaired": False,
            "partial": False,
            "payload": None,
            "rows": [],
            "by_name": {},
            "rejected": [],
            "transformations": transformations,
            "classes": ["unrecoverable"],
            "unmodified_ok": False,
        }

    unmodified = _loads(stripped)
    parseable_unmodified = isinstance(unmodified, (dict, list))
    outer, trunc = _outermost(stripped)
    if trunc:
        classes.append("truncated JSON")
        transformations.append("take_outermost_truncated")
    repaired_text, punct = _repair_punctuation(outer)
    if punct:
        classes.append("quote/comma/bracket")
        transformations.extend(punct)
    payload = unmodified if parseable_unmodified else _loads(repaired_text)
    if payload is None:
        payload = unmodified

    rows: list[dict[str, Any]] = []
    if isinstance(payload, dict) and isinstance(payload.get("attributes"), list):
        rows = [row for row in payload["attributes"] if isinstance(row, dict)]
    elif isinstance(payload, list):
        rows = [row for row in payload if isinstance(row, dict)]
        transformations.append("array_as_attributes")

    object_rows = _parse_attr_objects(stripped)
    if object_rows and (not rows or len(object_rows) > len(rows)):
        if rows and len(object_rows) > len(rows):
            transformations.append("recover_sibling_attribute_objects")
        elif not rows:
            transformations.append("parse_individual_attribute_objects")
        rows = object_rows
        if not parseable_unmodified:
            classes.append("valid partial response")

    requested_set = set(requested)
    by_name: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row.get("attribute") or "").strip()
        if name not in requested_set:
            rejected.append({"attribute": name, "reason": "not_requested"})
            continue
        if name in seen:
            classes.append("duplicate attribute")
            prev = seen[name]
            same = (
                prev.get("status") == row.get("status")
                and prev.get("raw_value") == row.get("raw_value")
                and prev.get("normalized_value") == row.get("normalized_value")
            )
            rejected.append({"attribute": name, "reason": "duplicate" if same else "contradictory_duplicate"})
            by_name.pop(name, None)
            continue
        seen[name] = row
        status = str(row.get("status") or "").strip()
        if status not in STATUSES:
            classes.append("invalid status")
            rejected.append({"attribute": name, "reason": f"invalid_status:{status}"})
            continue
        by_name[name] = row
    missing = [name for name in requested if name not in by_name]
    if missing:
        classes.append("missing requested attribute")
    if by_name and missing:
        classes.append("valid partial response")
    if not by_name:
        classes.append("unrecoverable")

    repaired = bool(transformations) and bool(by_name)
    return {
        "ok": bool(by_name) and not missing and "duplicate attribute" not in classes,
        "parseable_unmodified": parseable_unmodified and isinstance(unmodified, dict),
        "repaired": repaired,
        "partial": bool(by_name) and bool(missing),
        "payload": payload if isinstance(payload, dict) else None,
        "rows": rows,
        "by_name": by_name,
        "rejected": rejected,
        "missing": missing,
        "transformations": transformations,
        "classes": list(dict.fromkeys(classes)),
        "raw": original,
    }


def validate_salvaged(
    by_name: dict[str, dict[str, Any]],
    *,
    text: str,
    digest: str,
    dtypes: dict[str, str],
    plumbing_null: dict[str, bool],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, row in by_name.items():
        status = str(row.get("status") or "")
        raw = row.get("raw_value")
        if raw in ("", "null"):
            raw = None
        evidence = row.get("evidence") or []
        if not isinstance(evidence, list):
            evidence = []
        span = None
        source_id = ""
        for item in evidence:
            if not isinstance(item, dict):
                continue
            cand = str(item.get("exact_span") or "")
            if cand:
                span = cand
                source_id = str(item.get("source_id") or "")
                break
        grounded = bool(status == "found" and span and text and span.lower() in text.lower())
        if status == "found" and raw not in (None, "") and span and str(raw).lower() not in str(span).lower():
            grounded = False
        value, unit, norm_err = normalize_value(raw, dtypes.get(name, "string"))
        commit = value if dtypes.get(name) == "numeric" and value is not None else raw
        reasons = []
        if status != "found":
            reasons.append(f"status:{status}")
        if not grounded:
            reasons.append("ungrounded")
        if not plumbing_null.get(name, True):
            reasons.append("plumbing_nonnull")
        if dtypes.get(name) == "numeric" and norm_err:
            reasons.append("normalization_failed")
        if raw not in (None, "") and not span:
            reasons.append("missing_span")
        out.append(
            {
                "attribute": name,
                "status": status,
                "raw_value": None if raw in (None, "") else str(raw),
                "normalized_value": value if value is not None else row.get("normalized_value"),
                "unit": unit or row.get("unit"),
                "period": row.get("period"),
                "span": span,
                "source_id": source_id,
                "document_hash": digest,
                "grounded": grounded,
                "norm_error": norm_err,
                "commit": commit,
                "sql_eligible": not reasons,
                "reject_reasons": reasons,
            }
        )
    return out
