"""Locked candidate-selection constants. No dataset or attribute lists."""

from __future__ import annotations

import hashlib
import json
from typing import Any

OPERATOR = "schema_grounded_candidate_select"
MAX_CANDIDATES = 8
COMPLETION_RESERVATION = 192
LEDGER_SAFETY_MARGIN = 2048
MODEL_CONTEXT_LIMIT = 32768
ALLOWED_OPERATIONS = ("identity", "sum", "difference", "percentage", "none")
EXTRACTIVE_STATUS = ("selected", "abstain")


def policy_payload(
    *,
    model: str,
    theta_25: int,
    theta_100: int,
    completion_reservation: int,
) -> dict[str, Any]:
    return {
        "operator": OPERATOR,
        "model": model,
        "theta_25": theta_25,
        "theta_100": theta_100,
        "max_candidates": MAX_CANDIDATES,
        "completion_reservation": completion_reservation,
        "ledger_safety_margin": LEDGER_SAFETY_MARGIN,
        "model_context_limit": MODEL_CONTEXT_LIMIT,
        "qwen_generates_values": False,
        "selector_returns_candidate_ids": True,
        "sql_literals_in_extractive_prompts": False,
        "router_llm": False,
        "overwrite_nonnull": False,
        "sentinels_materialized": False,
        "shared_extracted_values": True,
        "temperature": "omitted",
        "max_tokens": "omitted",
        "bypass_cache": True,
        "workers": 1,
        "seed": 42,
        "ranking": "n_distinct_workload_expressions / reserved_cost",
        "fx_invention": False,
    }


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
