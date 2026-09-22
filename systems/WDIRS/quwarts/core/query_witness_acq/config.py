"""Locked query-witness acquisition policy. Budgets come from the experiment config."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from quwarts.core.retrieve_extract.config import FROZEN as RETRIEVE_FROZEN
from quwarts.experiments.synthesize_case80 import budget_from_docetl, docetl_tokens

MODEL = "qwen/qwen-2.5-7b-instruct"
OPERATOR = "query_witness_acq"
THETA_25 = budget_from_docetl("Finan", 0.25)
THETA_100 = budget_from_docetl("Finan", 1.0)
DOCETL_TOKENS = docetl_tokens("Finan")

POLICY: dict[str, Any] = {
    "model": MODEL,
    "operator": OPERATOR,
    "corpus": "Finan",
    "theta_25": THETA_25,
    "theta_100": THETA_100,
    "docetl_tokens": DOCETL_TOKENS,
    "four_times_theta_25": THETA_25 * 4,
    "budget_authority": "budget_from_docetl / docetl_tokens",
    "router_llm": False,
    "query_expansion": False,
    "group_classification": False,
    "unknown_else_escape": False,
    "base_column_writes": False,
    "replace_incumbent_support": False,
    "batch_size": 1,
    "max_malformed_retry": 1,
    "max_refine": 1,
    "temperature": 0.1,
    "max_tokens": 280,
    "reserved_completion_tokens": 220,
    "retrieve_context_cap": int(RETRIEVE_FROZEN["retrieve_context_cap"]),
    "effective_input_limit": int(RETRIEVE_FROZEN["effective_input_limit"]),
    "model_context_limit": int(RETRIEVE_FROZEN["model_context_limit"]),
    "safety_margin": int(RETRIEVE_FROZEN["safety_margin"]),
    "workers": 1,
    "seed": 42,
    "scheduling": "frequency * amplification * excluded_mass / cost, round-robin programs",
}

WITNESS_SYSTEM = (
    "Decide whether one existing witness satisfies the complete row-level condition. "
    "Return one JSON object. Do not invent a new row or change identity."
)

WITNESS_INSTRUCTIONS = """Return JSON with this exact shape:
{"witness_id":"<id>","condition":"true|false|unknown","group_value":null,"aggregate_value":null,"counted_value_present":null,"evidence":[{"condition_part":"","source_id":"","exact_span":""}]}
Rules:
- Only fill fields listed in requested_fields. Omit others or set them null.
- Missing evidence or an unclear fact is unknown, never false.
- true requires exact_span text copied from the source.
- Numeric aggregate_value must be copied from an exact_span.
- group_value must be one of legal_group_values when that set is finite.
- Do not propose new witnesses or change witness_id.
"""


def policy_hash() -> str:
    return hashlib.sha256(json.dumps(POLICY, sort_keys=True, default=str).encode()).hexdigest()


def prompt_hash() -> str:
    payload = {"system": WITNESS_SYSTEM, "instructions": WITNESS_INSTRUCTIONS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def verify_budgets() -> dict[str, Any]:
    if THETA_25 != 345457:
        raise SystemExit(f"theta_25 mismatch: configured {THETA_25} != 345457")
    if THETA_100 <= 0 or DOCETL_TOKENS <= 0:
        raise SystemExit("missing DocETL token total for Finan")
    if THETA_100 != DOCETL_TOKENS:
        raise SystemExit(f"theta_100 {THETA_100} != docetl_tokens {DOCETL_TOKENS}")
    return {
        "theta_25": THETA_25,
        "theta_100": THETA_100,
        "docetl_tokens": DOCETL_TOKENS,
        "four_times_theta_25": THETA_25 * 4,
        "theta_100_is_exactly_4x_theta_25": THETA_100 == THETA_25 * 4,
        "authority": "experiments.synthesize_case80.budget_from_docetl",
    }
