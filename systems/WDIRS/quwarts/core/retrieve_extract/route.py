"""Per-(document, entity, bundle) context routing. No gold, scorer, or corpus name."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from quwarts.core.retrieve_extract.config import FROZEN
from quwarts.core.retrieve_extract.tokens import count_tokens

MODES = ("whole_document", "retrieved_chunks", "section_map")


@dataclass
class TokenMeasurements:
    document_tokens: int
    prompt_and_schema_tokens: int
    reserved_completion_tokens: int
    safety_margin: int
    model_context_limit: int
    effective_input_limit: int
    estimated_call_cost: int
    hard_fit: bool
    effective_fit: bool


@dataclass
class RouteDecision:
    mode: str
    feasible: list[str]
    measurements: TokenMeasurements
    retrieval_concentration: dict[str, Any]
    estimated_cost: int
    remaining_budget: int
    reason: str
    planner_prompt: str | None = None
    planner_response: str | None = None


def measure(
    document_tokens: int,
    prompt_and_schema_tokens: int,
    packed_tokens: int,
) -> TokenMeasurements:
    reserved = int(FROZEN["reserved_completion_tokens"])
    margin = int(FROZEN["safety_margin"])
    limit = int(FROZEN["model_context_limit"])
    effective = int(FROZEN["effective_input_limit"])
    hard_fit = document_tokens + prompt_and_schema_tokens + reserved + margin <= limit
    effective_fit = document_tokens + prompt_and_schema_tokens <= effective
    whole_cost = document_tokens + prompt_and_schema_tokens + reserved
    packed_cost = packed_tokens + prompt_and_schema_tokens + reserved
    estimated = whole_cost if hard_fit and effective_fit else packed_cost
    return TokenMeasurements(
        document_tokens=document_tokens,
        prompt_and_schema_tokens=prompt_and_schema_tokens,
        reserved_completion_tokens=reserved,
        safety_margin=margin,
        model_context_limit=limit,
        effective_input_limit=effective,
        estimated_call_cost=estimated,
        hard_fit=hard_fit,
        effective_fit=effective_fit,
    )


def _disproportionate(document_tokens: int, remaining: int) -> bool:
    if document_tokens >= int(FROZEN["disproportionate_doc_tokens"]):
        return True
    if remaining > 0 and document_tokens > remaining * float(FROZEN["disproportionate_remaining_frac"]):
        return True
    return False


def feasible_modes(measurements: TokenMeasurements, remaining: int, concentration: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if (
        measurements.hard_fit
        and measurements.effective_fit
        and measurements.estimated_call_cost <= remaining
        and not _disproportionate(measurements.document_tokens, remaining)
    ):
        out.append("whole_document")
    out.append("retrieved_chunks")
    if measurements.document_tokens > measurements.effective_input_limit or concentration.get("diffuse"):
        out.append("section_map")
    return list(dict.fromkeys(out))


def is_borderline(measurements: TokenMeasurements, concentration: dict[str, Any], remaining: int) -> bool:
    gap = int(FROZEN["borderline_fit_gap"])
    lo = float(FROZEN["borderline_concentration_lo"])
    hi = float(FROZEN["borderline_concentration_hi"])
    near_effective = abs(
        measurements.document_tokens + measurements.prompt_and_schema_tokens - measurements.effective_input_limit
    ) <= gap
    share = float(concentration.get("top2_share") or 0.0)
    mid_concentration = lo <= share <= hi
    tight_ledger = remaining < measurements.estimated_call_cost * 2
    return bool(near_effective or mid_concentration or tight_ledger)


def decide_coverage_route(measurements: TokenMeasurements, concentration: dict[str, Any]) -> tuple[str, str]:
    """Zero-token router. No ledger planner and no corpus name."""

    if measurements.hard_fit and measurements.effective_fit:
        return "whole_document", "hard_and_effective_fit"
    concentrated = not bool(concentration.get("diffuse")) and int(concentration.get("n_hits") or 0) > 0
    if concentrated:
        return "retrieved_chunks", "concentrated_retrieval"
    return "section_map", "diffuse_or_weak_retrieval"


def decide_deterministic(
    measurements: TokenMeasurements,
    remaining: int,
    concentration: dict[str, Any],
) -> tuple[str, str]:
    feasible = feasible_modes(measurements, remaining, concentration)
    if "whole_document" in feasible:
        return "whole_document", "hard_fit_and_effective_fit_and_ledger"
    if concentration.get("diffuse") and "section_map" in feasible:
        return "section_map", "long_or_unfit_and_diffuse_retrieval"
    if measurements.document_tokens > measurements.effective_input_limit or _disproportionate(
        measurements.document_tokens, remaining
    ):
        return "retrieved_chunks", "document_too_long_or_disproportionate"
    return "retrieved_chunks", "default_retrieved_chunks"


def planner_prompt(measurements: TokenMeasurements, remaining: int, concentration: dict[str, Any], feasible: list[str]) -> str:
    return (
        "Choose one context mode. Do not mention any corpus or dataset.\n"
        f"feasible={feasible}\n"
        f"document_tokens={measurements.document_tokens}\n"
        f"prompt_and_schema_tokens={measurements.prompt_and_schema_tokens}\n"
        f"reserved_completion_tokens={measurements.reserved_completion_tokens}\n"
        f"safety_margin={measurements.safety_margin}\n"
        f"model_context_limit={measurements.model_context_limit}\n"
        f"effective_input_limit={measurements.effective_input_limit}\n"
        f"hard_fit={measurements.hard_fit}\n"
        f"effective_fit={measurements.effective_fit}\n"
        f"estimated_call_cost={measurements.estimated_call_cost}\n"
        f"remaining_budget={remaining}\n"
        f"retrieval_concentration={concentration}\n"
        'Reply {"mode":"whole_document|retrieved_chunks|section_map","reason":"..."}\n'
    )


def parse_planner(text: str, feasible: list[str]) -> tuple[str | None, str]:
    import json
    import re

    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return None, "planner_unparsed"
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None, "planner_invalid_json"
    mode = str(payload.get("mode") or "").strip()
    reason = str(payload.get("reason") or "planner")
    if mode not in feasible:
        return None, f"planner_infeasible:{mode}"
    return mode, reason


def prompt_and_schema_tokens(attributes: list[str], descriptions: dict[str, str]) -> int:
    from quwarts.core.retrieve_extract.config import EXTRACT_INSTRUCTIONS

    lines = [EXTRACT_INSTRUCTIONS, "Attributes:"]
    for name in attributes:
        lines.append(f"- {name}: {descriptions.get(name, '')}")
    return count_tokens("\n".join(lines))
