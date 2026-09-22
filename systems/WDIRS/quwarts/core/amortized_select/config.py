"""Locked amortized selection-program constants. No dataset lists."""

from __future__ import annotations

import hashlib
import json
from typing import Any

OPERATOR = "amortized_attribute_selection_program"
COMPLETION_RESERVATION = 192
COMPILER_BUDGET_FRACTION = 0.20
SAMPLE_SETS_PER_ATTRIBUTE = 4
THETA_25 = 345_457
ALLOWED_TASK_CLASS = ("extractive", "categorical")
ALLOWED_PERIOD = ("reporting_period", "latest", "period_end", "any")
ALLOWED_SCOPE = ("total", "consolidated", "entity_level", "component", "any")
ALLOWED_UNIT = ("preserve", "resolve_from_header", "percent", "any")
ALLOWED_VALUE_FORM = ("number", "full_legal_name", "short_code", "categorical", "text")
ALLOWED_OPS = ("identity", "none")
ALLOWED_TIE_BREAK = (
    "preferred_metadata",
    "scope",
    "period",
    "unit",
    "value_form",
    "lexical_similarity",
    "occurrence_count",
    "document_position",
    "source_type",
)
GENERIC_VOCAB = frozenset(
    {
        "total",
        "totals",
        "consolidated",
        "consolidation",
        "current",
        "latest",
        "external",
        "auditor",
        "auditors",
        "independent",
        "period",
        "end",
        "reporting",
        "net",
        "gross",
        "component",
        "segment",
        "segments",
        "entity",
        "group",
        "parent",
        "name",
        "code",
        "percent",
        "percentage",
        "million",
        "billion",
        "thousand",
        "operating",
        "outstanding",
        "legal",
        "full",
        "short",
        "any",
        "preserve",
        "identity",
        "table",
        "paragraph",
        "heading",
        "list",
        "row",
        "column",
        "header",
        "title",
        "section",
        "equivalent",
        "equivalents",
        "cash",
        "share",
        "shares",
        "policy",
        "yes",
        "no",
    }
)
SOURCE_KIND = {
    "table_row": "table",
    "table_header": "table",
    "table_title": "table",
    "paragraph": "paragraph",
    "section_heading": "heading",
    "list": "list",
}


def policy_payload(*, model: str, theta_25: int, completion_reservation: int) -> dict[str, Any]:
    return {
        "operator": OPERATOR,
        "model": model,
        "theta_25": theta_25,
        "theta_100": None,
        "completion_reservation": completion_reservation,
        "compiler_budget_fraction": COMPILER_BUDGET_FRACTION,
        "sample_sets_per_attribute": SAMPLE_SETS_PER_ATTRIBUTE,
        "qwen_generates_values": False,
        "compiler_emits_dsl_only": True,
        "executor_is_deterministic": True,
        "executor_has_attribute_branches": False,
        "residual_returns_candidate_ids": True,
        "sql_literals_in_prompts": False,
        "overwrite_nonnull": False,
        "sentinels_materialized": False,
        "shared_extracted_values": True,
        "bypass_cache": True,
        "workers": 1,
        "seed": 42,
        "legal_arm": False,
        "theta_100_arm": False,
    }


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
