"""O(distinct) representation repairs. No corpus re-extract."""

from __future__ import annotations

import re
from typing import Any

from quwarts.core.population import _as_number


_UNIT = re.compile(
    r"(?i)\b(\d+(?:\.\d+)?)\s*"
    r"(mg|mcg|ug|µg|g|kg|ml|l|iu|mmhg|mm|cm|%|years?|yrs?|yo|y/o|hours?|hrs?|days?|weeks?|months?)\b"
)
_RANGE = re.compile(
    r"(?i)(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)"
)
_BOOLEAN = {
    "yes": 1, "y": 1, "true": 1, "positive": 1, "present": 1, "pos": 1,
    "no": 0, "n": 0, "false": 0, "negative": 0, "absent": 0, "neg": 0,
}
_ABSENCE = frozenset({
    "none", "n/a", "na", "unknown", "unspecified", "missing",
    "none reported", "not reported", "not available", "no data",
    "null", "nil", "none given",
})


def extract_unit_and_magnitude(store, attributes: list[str]) -> dict[str, Any]:
    changed = 0
    for record in list(store.records.values()):
        if not _on_attr(record.attribute, attributes):
            continue
        text = str(record.surface_value or "").strip()
        if not text:
            continue
        match = _UNIT.search(text)
        if match is None:
            continue
        magnitude = _as_number(match.group(1))
        if not isinstance(magnitude, (int, float)):
            continue
        unit = match.group(2)
        keys = dict(record.candidate_keys or {})
        keys["representation"] = "unit"
        keys["magnitude"] = str(magnitude)
        keys["unit"] = unit
        record.parsed_value = magnitude
        record.null_reason = None
        record.candidate_keys = keys
        store.put(record)
        changed += 1
    return {"action": "extract_unit_and_magnitude", "n": changed}


def map_boolean_encoding(store, attributes: list[str], literals: list[Any] | None = None) -> dict[str, Any]:
    one, zero = _boolean_targets(literals)
    changed = 0
    for record in list(store.records.values()):
        if not _on_attr(record.attribute, attributes):
            continue
        folded = str(record.surface_value or "").strip().lower()
        if folded not in _BOOLEAN:
            continue
        mapped = one if _BOOLEAN[folded] == 1 else zero
        keys = dict(record.candidate_keys or {})
        keys["representation"] = "boolean"
        record.parsed_value = mapped
        record.null_reason = None
        record.candidate_keys = keys
        store.put(record)
        changed += 1
    return {"action": "map_boolean_encoding", "n": changed}


def parse_range_to_bounds(store, attributes: list[str]) -> dict[str, Any]:
    changed = 0
    for record in list(store.records.values()):
        if not _on_attr(record.attribute, attributes):
            continue
        text = str(record.surface_value or "").strip()
        match = _RANGE.search(text)
        if match is None:
            continue
        lo, hi = _as_number(match.group(1)), _as_number(match.group(2))
        if lo is None or hi is None:
            continue
        keys = dict(record.candidate_keys or {})
        keys["representation"] = "range"
        keys["lo"] = str(lo)
        keys["hi"] = str(hi)
        record.parsed_value = lo
        record.null_reason = None
        record.candidate_keys = keys
        store.put(record)
        changed += 1
    return {"action": "parse_range_to_bounds", "n": changed}


def map_category_to_numeric_band(
    store, attributes: list[str], bands: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Only when SQL already declares numeric CASE bands. No name lexicon."""

    if not bands:
        return {"action": "map_category_to_numeric_band", "n": 0, "skipped": "no_sql_bands"}
    mapping = {}
    for band in bands:
        label = str(band.get("label") or "").strip()
        if label:
            mapping[label.lower()] = band.get("value")
    if not mapping:
        return {"action": "map_category_to_numeric_band", "n": 0, "skipped": "no_sql_bands"}
    changed = 0
    for record in list(store.records.values()):
        if not _on_attr(record.attribute, attributes):
            continue
        folded = str(record.surface_value or "").strip().lower()
        if folded not in mapping or mapping[folded] is None:
            continue
        keys = dict(record.candidate_keys or {})
        keys["representation"] = "band"
        record.parsed_value = mapping[folded]
        record.null_reason = None
        record.candidate_keys = keys
        store.put(record)
        changed += 1
    return {"action": "map_category_to_numeric_band", "n": changed}


def mark_absence_as_null(store, attributes: list[str]) -> dict[str, Any]:
    changed = 0
    for record in list(store.records.values()):
        if not _on_attr(record.attribute, attributes):
            continue
        folded = " ".join(str(record.surface_value or "").strip().lower().split())
        if folded not in _ABSENCE:
            continue
        keys = dict(record.candidate_keys or {})
        keys["representation"] = "absence"
        record.surface_value = None
        record.parsed_value = None
        record.null_reason = "absence"
        record.candidate_keys = keys
        store.put(record)
        changed += 1
    return {"action": "mark_absence_as_null", "n": changed}


def _boolean_targets(literals: list[Any] | None) -> tuple[Any, Any]:
    values = [item for item in (literals or []) if item is not None]
    if any(item in {1, "1", True, "true"} for item in values) or any(
        item in {0, "0", False, "false"} for item in values
    ):
        return 1, 0
    return 1, 0


def _on_attr(attribute: str, names: list[str]) -> bool:
    if not names:
        return True
    bare = attribute.split(".")[-1].lower()
    return attribute in names or bare in {name.split(".")[-1].lower() for name in names}
