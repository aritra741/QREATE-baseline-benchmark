"""Locked Finan full-window additive policy. Frozen before the first model call."""

from __future__ import annotations

import hashlib
import json
from typing import Any

MODEL = "qwen/qwen-2.5-7b-instruct"
OPERATOR = "full_window_additive"
THETA_25 = 345_457
THETA_100 = 1_381_827

POLICY: dict[str, Any] = {
    "model": MODEL,
    "operator": OPERATOR,
    "corpus": "Finan",
    "theta_25": THETA_25,
    "theta_100": THETA_100,
    "primary_tasks": 112,
    "documents_per_query": 7,
    "router_llm": False,
    "qwen_validation_retry": False,
    "qwen_format_repair": False,
    "exact_span_required": False,
    "sentinels_materialized": False,
    "overwrite_nonnull": False,
    "shared_extracted_values": False,
    "temperature": 0.1,
    "completion_cap": 400,
    "per_call_tokenizer_slack": 200,
    "ledger_safety_margin": 2048,
    "target_input_lo": 10000,
    "target_input_hi": 12000,
    "workers": 1,
    "seed": 42,
    "scheduling": "docetl_manifest_order",
    "note": "Seven-document set is derived from frozen DocETL pipeline_output IDs for this controlled arm; it is not the generic selection policy.",
}

SYSTEM = "Return one JSON object. Do not explain."

PROMPT_TEMPLATE = (
    "You are building a structured {table} table for this natural-language query:\n"
    "{nl_query}\n\n"
    "From this {table} document, extract exactly one record with these fields:\n"
    "{field_list}\n\n"
    "For numeric fields, return numbers (not quoted strings). "
    "Numeric fields in this extraction: {numeric_guidance}.\n"
    "If a numeric field is unknown, return -1. "
    "If a text field is unknown, return empty string. "
    "Keep names concise and normalized.\n\n"
    "Document:\n{document}"
)


def policy_hash() -> str:
    return hashlib.sha256(json.dumps(POLICY, sort_keys=True, default=str).encode()).hexdigest()


def prompt_hash() -> str:
    return hashlib.sha256(json.dumps({"system": SYSTEM, "template": PROMPT_TEMPLATE}, sort_keys=True).encode()).hexdigest()


def verify_budgets() -> dict[str, int]:
    if THETA_25 != 345_457 or THETA_100 != 1_381_827:
        raise SystemExit(f"budget lock failed: {THETA_25} {THETA_100}")
    return {"theta_25": THETA_25, "theta_100": THETA_100}
