"""Bounded extraction repair. One typed action per attempt. Same ledger."""

from __future__ import annotations

import json
import re
from typing import Any

from quwarts.core.ledger import BudgetedCaller
from quwarts.core.retrieve_extract.config import FROZEN, MODEL, REPAIR_SYSTEM
from quwarts.core.retrieve_extract.extract import can_afford, complete, estimate_cost
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.route import TokenMeasurements

ACTIONS = (
    "retry_format",
    "repair_missing_field",
    "repair_normalization",
    "retrieve_alternate",
    "expand_adjacent",
    "switch_to_whole_document",
    "switch_to_retrieved_chunks",
    "build_section_map",
    "retry_single_attribute",
    "abstain",
)


FIRST_PASS_ACTIONS = (
    "retry_format",
    "repair_missing_field",
    "repair_normalization",
    "abstain",
)
REFINE_ACTIONS = (
    "retry_format",
    "repair_missing_field",
    "repair_normalization",
    "retrieve_alternate",
    "expand_adjacent",
    "retry_single_attribute",
    "abstain",
)


def eligible_actions(
    parsed: dict[str, Any],
    mode: str,
    measurements: TokenMeasurements,
    remaining: int,
    malformed_retries: int,
    attempts: int,
    allowed: tuple[str, ...] | None = None,
) -> list[str]:
    errors = list(parsed.get("errors") or [])
    items = parsed.get("items") or {}
    missing = any(str(err).startswith("omitted") for err in errors)
    bad_json = parsed.get("malformed") and any("invalid_json" in str(err) for err in errors)
    unknown_status = any("unknown_status" in str(err) for err in errors)
    grounding = int(parsed.get("grounding_failures") or 0) > 0
    unresolved = [
        name
        for name, item in items.items()
        if item.get("status") in {"not_found", "uncertain", "malformed"}
        or "grounding_failure" in (item.get("errors") or [])
    ]
    norm_fail = [
        name
        for name, item in items.items()
        if item.get("norm_error") and item.get("raw_value") and item.get("grounded")
    ]
    out: list[str] = []
    if (bad_json or unknown_status or parsed.get("malformed")) and malformed_retries < int(FROZEN["max_malformed_retry"]):
        out.append("retry_format")
    if missing and malformed_retries < int(FROZEN["max_malformed_retry"]):
        out.append("repair_missing_field")
    if norm_fail:
        out.append("repair_normalization")
    if grounding or unresolved:
        out.extend(["retrieve_alternate", "expand_adjacent"])
        if mode != "retrieved_chunks":
            out.append("switch_to_retrieved_chunks")
        if mode != "section_map":
            out.append("build_section_map")
    if (
        mode != "whole_document"
        and measurements.hard_fit
        and measurements.effective_fit
        and measurements.estimated_call_cost <= remaining
    ):
        out.append("switch_to_whole_document")
    if len(items) > 1:
        out.append("retry_single_attribute")
    out.append("abstain")
    if allowed is not None:
        allowed_set = set(allowed)
        out = [action for action in out if action in allowed_set]
    if "abstain" not in out:
        out.append("abstain")
    if attempts >= int(FROZEN["max_repairs_per_job"]) and "abstain" in out:
        return ["abstain"]
    return list(dict.fromkeys(out))


def choose_deterministic(eligible: list[str]) -> str:
    prefer = (
        "retry_format",
        "repair_missing_field",
        "repair_normalization",
        "expand_adjacent",
        "retrieve_alternate",
        "switch_to_whole_document",
        "build_section_map",
        "switch_to_retrieved_chunks",
        "retry_single_attribute",
        "abstain",
    )
    for action in prefer:
        if action in eligible:
            return action
    return "abstain"


def repair_prompt(
    eligible: list[str],
    parsed: dict[str, Any],
    mode: str,
    measurements: TokenMeasurements,
    remaining: int,
    previous: list[str],
) -> str:
    compact = {
        "errors": parsed.get("errors"),
        "counts": parsed.get("counts"),
        "statuses": {name: item.get("status") for name, item in (parsed.get("items") or {}).items()},
        "norm_errors": {
            name: item.get("norm_error")
            for name, item in (parsed.get("items") or {}).items()
            if item.get("norm_error")
        },
    }
    return (
        "Choose exactly one repair action. Do not invent values. Do not write SQL.\n"
        f"eligible={list(eligible)}\n"
        f"mode={mode}\n"
        f"hard_fit={measurements.hard_fit}\n"
        f"effective_fit={measurements.effective_fit}\n"
        f"estimated_call_cost={measurements.estimated_call_cost}\n"
        f"remaining_budget={remaining}\n"
        f"previous_actions={previous}\n"
        f"validation={compact}\n"
        f'Allowed: {list(ACTIONS)}\n'
        'Reply {"action":"...","reason":"..."}\n'
    )


def parse_action(text: str, eligible: list[str]) -> tuple[str | None, str]:
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return None, "unparsed"
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None, "invalid_json"
    action = str(payload.get("action") or "").strip()
    reason = str(payload.get("reason") or "model")
    if action not in eligible:
        return None, f"ineligible:{action}"
    return action, reason


def decide_action(
    caller: BudgetedCaller,
    parsed: dict[str, Any],
    mode: str,
    measurements: TokenMeasurements,
    previous: list[str],
    malformed_retries: int,
    attempts: int,
    allowed: tuple[str, ...] | None = None,
    planner: bool = True,
) -> dict[str, Any]:
    remaining = caller.ledger.remaining()
    eligible = eligible_actions(
        parsed, mode, measurements, remaining, malformed_retries, attempts, allowed=allowed
    )
    if not planner:
        action = choose_deterministic(eligible) if eligible else "abstain"
        return {
            "action": action,
            "reason": "deterministic_first_pass",
            "eligible": eligible,
            "prompt": None,
            "response": None,
            "tokens": 0,
        }
    if len(eligible) <= 1:
        action = eligible[0] if eligible else "abstain"
        return {
            "action": action,
            "reason": "deterministic_singleton",
            "eligible": eligible,
            "prompt": None,
            "response": None,
            "tokens": 0,
        }
    prompt = repair_prompt(eligible, parsed, mode, measurements, remaining, previous)
    cost = estimate_cost(prompt)
    if not can_afford(caller.ledger, min(cost, int(FROZEN["planner_max_tokens"]) + 80)):
        action = choose_deterministic(eligible)
        return {
            "action": action,
            "reason": "deterministic_no_budget",
            "eligible": eligible,
            "prompt": None,
            "response": None,
            "tokens": 0,
        }
    try:
        raw, used = complete(caller, prompt, "repair_planner", REPAIR_SYSTEM)
    except Exception:
        action = choose_deterministic(eligible)
        return {
            "action": action,
            "reason": "planner_failed_fallback",
            "eligible": eligible,
            "prompt": prompt,
            "response": None,
            "tokens": 0,
        }
    action, reason = parse_action(raw, eligible)
    if action is None:
        action = choose_deterministic(eligible)
        reason = f"fallback:{reason}"
    return {
        "action": action,
        "reason": reason,
        "eligible": eligible,
        "prompt": prompt,
        "response": raw,
        "tokens": used,
    }


def apply_normalization_repair(item: dict[str, Any], dtype: str) -> dict[str, Any]:
    raw = item.get("raw_value")
    value, unit, error = normalize_value(raw, dtype)
    out = dict(item)
    if value is not None:
        out["normalized_value"] = value
        out["norm_error"] = None
        out["errors"] = [err for err in (out.get("errors") or []) if err != "dtype_coercion"]
    else:
        out["norm_error"] = error
    if unit and not out.get("unit"):
        out["unit"] = unit
    return out
