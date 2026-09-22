"""Deterministic values from selected candidate IDs. Never uses model text as a value."""

from __future__ import annotations

from typing import Any

from quwarts.core.candidate_select.candidates import Candidate, apply_header_scale
from quwarts.core.candidate_select.config import ALLOWED_OPERATIONS
from quwarts.core.candidate_select.schema_spec import AttrSpec
from quwarts.core.retrieve_extract.parse import normalize_value


def lookup(candidates: list[Candidate], ids: list[str]) -> list[Candidate]:
    by_id = {item.opaque_id: item for item in candidates}
    out = []
    for cid in ids:
        item = by_id.get(str(cid).strip())
        if item is not None:
            out.append(item)
    return out


def _numeric(item: Candidate, spec: AttrSpec) -> Any:
    value = item.normalized
    if not isinstance(value, (int, float)):
        value, _, err = normalize_value(item.raw_span, "numeric")
        if err or value is None:
            return None
        value = apply_header_scale(value, " ".join(part for part in (item.unit or "", item.column_header, item.table_title) if part))
    target = (spec.target_currency or "").lower()
    if spec.requires_usd and item.currency and target and item.currency.lower() != target:
        return None
    return value


def construct_extractive(
    *,
    spec: AttrSpec,
    candidates: list[Candidate],
    candidate_ids: list[str],
    operation: str,
    status: str,
) -> dict[str, Any]:
    if status != "selected" or operation == "none":
        return {"value": None, "reason": "abstain", "used_ids": []}
    op = operation if operation in ALLOWED_OPERATIONS else "identity"
    chosen = lookup(candidates, candidate_ids)
    if not chosen:
        return {"value": None, "reason": "unknown_candidate_id", "used_ids": []}
    if spec.dtype == "numeric":
        if op in {"sum", "difference", "percentage"} and not spec.allows_sum and op == "sum":
            return {"value": None, "reason": "sum_not_in_schema", "used_ids": [item.opaque_id for item in chosen]}
        if op == "sum" and spec.allows_sum:
            values = [_numeric(item, spec) for item in chosen]
            if any(item is None for item in values) or not values:
                return {"value": None, "reason": "fx_or_unnormalized", "used_ids": [item.opaque_id for item in chosen]}
            total = sum(float(item) for item in values)
            return {"value": int(total) if float(total) == int(total) else total, "reason": None, "used_ids": [item.opaque_id for item in chosen], "operation": "sum"}
        if op == "difference" and len(chosen) >= 2:
            left, right = _numeric(chosen[0], spec), _numeric(chosen[1], spec)
            if left is None or right is None:
                return {"value": None, "reason": "fx_or_unnormalized", "used_ids": [item.opaque_id for item in chosen[:2]]}
            value = float(left) - float(right)
            return {"value": int(value) if value == int(value) else value, "reason": None, "used_ids": [item.opaque_id for item in chosen[:2]], "operation": "difference"}
        if op == "percentage" and len(chosen) >= 2:
            left, right = _numeric(chosen[0], spec), _numeric(chosen[1], spec)
            if left is None or right is None or not right:
                return {"value": None, "reason": "fx_or_unnormalized", "used_ids": [item.opaque_id for item in chosen[:2]]}
            value = 100.0 * float(left) / float(right)
            return {"value": value, "reason": None, "used_ids": [item.opaque_id for item in chosen[:2]], "operation": "percentage"}
        value = _numeric(chosen[0], spec)
        if value is None:
            return {"value": None, "reason": "fx_or_unnormalized", "used_ids": [chosen[0].opaque_id]}
        return {"value": value, "reason": None, "used_ids": [chosen[0].opaque_id], "operation": "identity", "period": chosen[0].period, "unit": chosen[0].unit}
    text = str(chosen[0].normalized or chosen[0].raw_span).strip()
    if not text:
        return {"value": None, "reason": "empty_span", "used_ids": [chosen[0].opaque_id]}
    return {"value": text, "reason": None, "used_ids": [chosen[0].opaque_id], "operation": "identity"}


def construct_classification(
    *,
    spec: AttrSpec,
    label: Any,
    status: str,
    evidence_ids: list[str],
    candidates: list[Candidate],
) -> dict[str, Any]:
    if status != "selected":
        return {"value": None, "reason": "abstain", "used_ids": []}
    text = str(label or "").strip()
    domain = {item.lower(): item for item in spec.schema_domain}
    if text.lower() not in domain:
        return {"value": None, "reason": "label_not_in_schema_domain", "used_ids": []}
    used = [item.opaque_id for item in lookup(candidates, evidence_ids)]
    return {"value": domain[text.lower()], "reason": None, "used_ids": used, "operation": "identity"}
