"""One-witness Qwen decision and conservative validation."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.query_witness_acq.config import (
    MODEL,
    OPERATOR,
    POLICY,
    WITNESS_INSTRUCTIONS,
    WITNESS_SYSTEM,
    policy_hash,
    prompt_hash,
)
from quwarts.core.query_witness_acq.programs import WitnessProgram, apply_case
from quwarts.core.retrieve_extract.cache import VerifiedCache
from quwarts.core.retrieve_extract.extract import can_afford, complete, estimate_cost
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.salvage import salvage_completion

_STATUS = {"true", "false", "unknown"}


def context_hash(parts: list[str]) -> str:
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def task_key(condition_id: str, witness_id: str, ctx_hash: str) -> str:
    return hashlib.sha256(f"{condition_id}|{witness_id}|{ctx_hash}".encode()).hexdigest()


def build_prompt(program: WitnessProgram, witness_id: str, context: str, source_ids: list[str]) -> str:
    fields = program.requested_fields
    legal = program.legal_group_values
    return (
        f"{WITNESS_INSTRUCTIONS}\n"
        f"requested_fields: {fields}\n"
        f"legal_group_values: {legal}\n"
        f"witness_id: {witness_id}\n"
        f"condition_sql: {program.condition_sql}\n"
        f"group_sql: {program.group_sql}\n"
        f"aggregate_sql: {program.agg_sql}\n"
        f"source_ids: {source_ids}\n\n"
        f"SOURCE:\n{context}\n"
    )


def parse_decision(raw: str, program: WitnessProgram, witness_id: str) -> dict[str, Any]:
    salvaged = salvage_completion(raw, [witness_id])
    payload = salvaged.get("payload")
    if not isinstance(payload, dict):
        match = re.search(r"\{.*\}", raw or "", re.S)
        if match:
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                payload = {}
        else:
            payload = {}
    condition = str(payload.get("condition") or "unknown").strip().lower()
    if condition not in _STATUS:
        condition = "unknown"
    if not payload:
        condition = "unknown"
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    spans = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        span = str(item.get("exact_span") or "")
        if span:
            spans.append(
                {
                    "condition_part": str(item.get("condition_part") or ""),
                    "source_id": str(item.get("source_id") or ""),
                    "exact_span": span,
                }
            )
    return {
        "witness_id": str(payload.get("witness_id") or witness_id),
        "condition": condition,
        "group_value": payload.get("group_value"),
        "aggregate_value": payload.get("aggregate_value"),
        "counted_value_present": payload.get("counted_value_present"),
        "evidence": spans,
        "raw": raw,
        "salvage_classes": salvaged.get("classes") or [],
        "malformed": not payload,
    }


def validate_decision(
    parsed: dict[str, Any],
    program: WitnessProgram,
    *,
    text: str,
    witness_id: str,
) -> dict[str, Any]:
    condition = parsed.get("condition") or "unknown"
    if parsed.get("witness_id") and str(parsed["witness_id"]) != str(witness_id):
        condition = "unknown"
    spans = parsed.get("evidence") or []
    grounded = []
    for item in spans:
        span = item.get("exact_span") or ""
        if span and text and span.lower() in text.lower():
            grounded.append(item)
    if condition == "true" and not grounded:
        condition = "unknown"
    group = parsed.get("group_value")
    legal = set(program.legal_group_values)
    surface = " ".join(item.get("exact_span") or "" for item in grounded)
    if program.group_sql:
        derived = apply_case(program.group_sql, surface)
        if group not in (None, "") and legal and str(group) not in legal:
            group = derived
        elif group in (None, ""):
            group = derived
    agg = parsed.get("aggregate_value")
    agg_norm = None
    if agg not in (None, "") and "aggregate_value" in program.requested_fields:
        value, _unit, err = normalize_value(agg, "numeric")
        if err or not any(str(agg) in (item.get("exact_span") or "") for item in grounded):
            agg_norm = None
        else:
            agg_norm = value
    counted = parsed.get("counted_value_present")
    if counted not in (None, "") and "counted_value_present" in program.requested_fields:
        if condition != "true":
            counted = None
    return {
        **parsed,
        "condition": condition,
        "group_value": None if group in (None, "") else str(group),
        "aggregate_value": agg_norm,
        "counted_value_present": counted,
        "grounded_evidence": grounded,
        "accepted": condition == "true" and bool(grounded),
    }


def decide_witness(
    caller: BudgetedCaller,
    cache: VerifiedCache,
    program: WitnessProgram,
    *,
    witness_id: str,
    context: str,
    source_ids: list[str],
    context_hashes: list[str],
    source_text: str,
    purpose: str = "witness",
) -> dict[str, Any] | None:
    prompt = build_prompt(program, witness_id, context, source_ids)
    cost = estimate_cost(prompt)
    if not can_afford(caller.ledger, min(cost, 4000)):
        return None
    manifest = {
        "corpus_id": "Finan",
        "source_document_hash": context_hash(context_hashes or [context[:200]]),
        "entity_identity": witness_id,
        "attribute_bundle": [program.condition_id],
        "context_mode": purpose,
        "context_hashes": list(context_hashes or [context_hash([context])]),
        "schema_hash": program.program_id,
        "prompt_hash": prompt_hash(),
        "model_id": MODEL,
        "configuration_hash": policy_hash(),
        "operator": OPERATOR,
        "tier": "witness",
    }
    cached = cache.get(manifest)
    if cached is not None:
        raw = str((cached.get("record") or {}).get("raw") or "")
        parsed = parse_decision(raw, program, witness_id)
        parsed["from_cache"] = True
        parsed["tokens"] = 0
        return validate_decision(parsed, program, text=source_text, witness_id=witness_id)
    try:
        raw, used = complete(caller, prompt, purpose, WITNESS_SYSTEM)
    except BudgetExhausted:
        return None
    parsed = parse_decision(raw, program, witness_id)
    if parsed["malformed"]:
        try:
            raw2, used2 = complete(caller, prompt + "\nReturn JSON only.", "retry", WITNESS_SYSTEM)
            used += used2
            parsed = parse_decision(raw2, program, witness_id)
            parsed["retried"] = True
            raw = raw2
        except BudgetExhausted:
            parsed["retried"] = False
    parsed["from_cache"] = False
    parsed["tokens"] = used
    cache.put(manifest, {"raw": raw, "parsed": parsed})
    return validate_decision(parsed, program, text=source_text, witness_id=witness_id)
