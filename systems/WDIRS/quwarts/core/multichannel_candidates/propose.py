"""Charged router, proposal, and verification calls. Selection compiler is not used here."""

from __future__ import annotations

import json
from typing import Any

from quwarts.core.ledger import BudgetExhausted, TokenLedger
from quwarts.core.multichannel_candidates.context import context_for_proposal
from quwarts.core.multichannel_candidates.prompts import CHANNELS, proposal_bundle, router_bundle, verify_bundle
from quwarts.core.multichannel_candidates.representation import evidence_span, make_candidate
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.eval.finan_amortized_select_arm import issue_call, parse_tool, reserved_of, usage_of


def charge(ledger: TokenLedger, purpose: str, reserved: int, response: Any, meta: dict[str, Any], reserve_selection: int) -> tuple[int, int, int] | None:
    prompt, completion, actual = usage_of(response, reserved)
    if ledger.spent + actual > ledger.theta - reserve_selection:
        return None
    ledger.spend(actual, purpose, reserved=reserved, **meta)
    return prompt, completion, actual


def call_tool(ledger: TokenLedger, bundled: dict[str, Any], purpose: str, reserve_selection: int, meta: dict[str, Any]) -> dict[str, Any] | None:
    _prompt, reserved = reserved_of(bundled["user"], bundled["tools"])
    if ledger.remaining() - reserve_selection < reserved:
        return None
    try:
        response = issue_call(bundled["request"])
    except Exception as exc:
        return {"malformed": True, "error": str(exc), "parsed": {}, "actual": 0}
    used = charge(ledger, purpose, reserved, response, meta, reserve_selection)
    if used is None:
        raise BudgetExhausted(f"{purpose} would consume the selection reserve")
    parsed = parse_tool(response)
    parsed["actual"] = used[2]
    parsed["reserved"] = reserved
    return parsed


def route_attribute(
    ledger: TokenLedger,
    spec: Any,
    record: Any,
    labels: dict[str, Any],
    density: dict[str, Any],
    structures: list[str],
    reserve_selection: int,
) -> dict[str, Any]:
    bundled = router_bundle(spec, record, labels, density, structures)
    got = call_tool(ledger, bundled, "router", reserve_selection, {"attribute": spec.name})
    if got is None:
        channels = list(CHANNELS)
        return {"channels": channels, "reason": "budget_skip_default_all", "actual": 0, "malformed": False}
    parsed = got.get("parsed") or {}
    channels = [str(item) for item in (parsed.get("channels") or []) if str(item) in CHANNELS]
    if not channels or got.get("malformed"):
        channels = list(CHANNELS)
    required = ["surface", "normalized"]
    desc = str(spec.official_description or "").lower()
    if labels.get("all_labels") or spec.schema_domain or spec.task_class == "classification":
        required.extend(["workload_label", "semantic"])
    if any(token in desc for token in ("whether", "choose", "current", "status", "type", "count", "number of", "inferred")):
        required.append("semantic")
    if "multiple" in desc or "semicolon" in desc or getattr(spec, "allows_sum", False):
        required.append("composed")
    if density.get("empty", 0) > 0:
        required.append("semantic")
    channels = list(dict.fromkeys(list(channels) + required))
    return {
        "channels": channels,
        "reason": parsed.get("reason") or "",
        "actual": got.get("actual") or 0,
        "malformed": bool(got.get("malformed")),
        "raw": got.get("raw") or "",
    }


def locate_span(source: str, text: str, claimed_start: Any) -> tuple[int, int, str]:
    blob = str(text or "").strip()
    if not blob:
        start = int(claimed_start or 0)
        return start, start, ""
    start = source.find(blob)
    if start < 0:
        start = source.find(blob[:40]) if len(blob) >= 8 else -1
    if start < 0:
        try:
            claimed = int(claimed_start)
        except (TypeError, ValueError):
            claimed = 0
        start = max(0, min(claimed, max(0, len(source) - 1)))
        end = min(len(source), start + len(blob))
        return start, end, source[start:end] or blob
    return start, start + len(blob if source[start : start + len(blob)] == blob else source[start : start + min(len(blob), 80)]), source[start : start + len(blob)] or blob


def proposals_from_response(
    parsed: dict[str, Any],
    spec: Any,
    document_id: str,
    source: str,
    allow_composed: bool,
) -> list[dict[str, Any]]:
    if parsed.get("none") is True:
        return []
    values = parsed.get("values") or parsed.get("proposals") or []
    derivations = parsed.get("derivations") or []
    texts = parsed.get("evidence_texts") or []
    if not isinstance(values, list):
        return []
    out: list[dict[str, Any]] = []
    for index, raw_value in enumerate(values[:4]):
        if isinstance(raw_value, dict):
            derivation = str(raw_value.get("derivation") or "semantic")
            evidence_text = ""
            if raw_value.get("evidence"):
                first = raw_value["evidence"][0] if isinstance(raw_value["evidence"], list) else {}
                evidence_text = str((first or {}).get("text") or "")
            raw_value = raw_value.get("value")
        else:
            derivation = str(derivations[index] if index < len(derivations) else "semantic")
            evidence_text = str(texts[index] if index < len(texts) else "")
        if derivation not in {"semantic", "composed", "workload_label"}:
            derivation = "semantic"
        if derivation == "composed" and not allow_composed:
            derivation = "semantic"
        if raw_value in (None, "", "NONE", "null"):
            continue
        typed, _, err = normalize_value(raw_value, spec.dtype)
        value = typed if not err and typed is not None else raw_value
        start, end, excerpt = locate_span(source, evidence_text or str(raw_value), 0)
        if not excerpt:
            continue
        out.append(
            make_candidate(
                attribute=spec.name,
                value=value,
                derivation=derivation,
                evidence_spans=[evidence_span(document_id, start, end, excerpt)],
                document_id=document_id,
                raw_span=str(raw_value),
                generator_status="proposed",
                normalization_trace=["qwen_proposal"],
                channel=derivation if derivation in {"semantic", "composed", "workload_label"} else "semantic",
                kind=derivation,
                score=0.3,
            )
        )
    return out


def propose_cell(
    ledger: TokenLedger,
    spec: Any,
    labels: list[str],
    entity_label: str,
    source: str,
    layouts: list[Any],
    terms: dict[str, list[str]],
    existing: list[dict[str, Any]],
    allow_composed: bool,
    reserve_selection: int,
    document_id: str,
    entity_id: str,
) -> dict[str, Any]:
    packed = context_for_proposal(source, layouts, terms, existing)
    bundled = proposal_bundle(spec, labels, entity_label, packed["text"], existing, allow_composed)
    got = call_tool(
        ledger,
        bundled,
        "proposer",
        reserve_selection,
        {"attribute": spec.name, "entity_id": entity_id, "context_mode": packed["mode"]},
    )
    if got is None:
        return {"candidates": [], "context": packed, "actual": 0, "skipped": True}
    cands = [] if got.get("malformed") else proposals_from_response(got.get("parsed") or {}, spec, document_id, source, allow_composed)
    return {
        "candidates": cands,
        "context": packed,
        "actual": got.get("actual") or 0,
        "malformed": bool(got.get("malformed")),
        "raw": got.get("raw") or "",
        "skipped": False,
    }


def verify_candidate(
    ledger: TokenLedger,
    spec: Any,
    candidate: dict[str, Any],
    entity_label: str,
    context: str,
    reserve_selection: int,
    entity_id: str,
) -> dict[str, Any]:
    bundled = verify_bundle(spec, candidate, entity_label, context)
    got = call_tool(
        ledger,
        bundled,
        "verifier",
        reserve_selection,
        {"attribute": spec.name, "entity_id": entity_id, "candidate_id": candidate.get("id")},
    )
    if got is None or got.get("malformed"):
        verdict = "uncertain"
        actual = 0 if got is None else got.get("actual") or 0
        reason = "malformed_or_unbudgeted"
    else:
        verdict = str((got.get("parsed") or {}).get("verdict") or "").strip().lower()
        if verdict not in {"supported", "unsupported", "uncertain"}:
            verdict = "uncertain"
        actual = got.get("actual") or 0
        reason = str((got.get("parsed") or {}).get("reason") or "")
    candidate["generator_status"] = "verified" if verdict == "supported" else "uncertain"
    candidate["eligible"] = verdict != "unsupported"
    candidate["verification"] = verdict
    return {"verdict": verdict, "reason": reason, "actual": actual, "candidate": candidate}
