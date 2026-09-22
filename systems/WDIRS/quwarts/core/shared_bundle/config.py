"""Locked shared-bundle algorithm constants. No dataset, query, document, or attribute lists."""

from __future__ import annotations

import hashlib
import json
from typing import Any

MAX_BUNDLE_SIZE = 3
MODEL_CONTEXT_LIMIT = 32768
TARGET_INPUT_LO = 10000
TARGET_INPUT_HI = 12000
LEDGER_SAFETY_MARGIN = 2048
COMPLETION_SAFETY = 64
OPERATOR = "shared_bundle_full_window"


def policy_payload(
    *,
    model: str,
    theta_25: int,
    theta_100: int,
    completion_reservation: int,
    input_cap: int,
    max_observed_completion: int,
) -> dict[str, Any]:
    return {
        "operator": OPERATOR,
        "model": model,
        "theta_25": theta_25,
        "theta_100": theta_100,
        "max_bundle_size": MAX_BUNDLE_SIZE,
        "model_context_limit": MODEL_CONTEXT_LIMIT,
        "target_input_lo": TARGET_INPUT_LO,
        "target_input_hi": TARGET_INPUT_HI,
        "ledger_safety_margin": LEDGER_SAFETY_MARGIN,
        "completion_safety": COMPLETION_SAFETY,
        "completion_reservation": completion_reservation,
        "max_observed_primary_completion": max_observed_completion,
        "input_cap": input_cap,
        "router_llm": False,
        "qwen_validation_retry": False,
        "qwen_format_repair": False,
        "exact_span_required": False,
        "sentinels_materialized": False,
        "overwrite_nonnull": False,
        "shared_extracted_values": True,
        "temperature": "omitted",
        "max_tokens": "omitted",
        "bypass_cache": True,
        "workers": 1,
        "seed": 42,
        "scheduling": "complete_entity_package impact/reserved_cost",
        "ranking": "total_impact / reserved_package_cost, tie-break __entity_id",
        "context_router": "whole_document_if_fits else recovered_mid_cut_at_input_cap",
    }


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
