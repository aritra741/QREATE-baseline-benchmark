"""Compiler, critic, repair, and residual prompts. No query literals."""

from __future__ import annotations

from typing import Any

from quwarts.core.amortized_select.features import card_line
from quwarts.core.docetl_exact_message.adapter import DOCETL_MODEL, DOCETL_SYSTEM, canonical_request, tools_for_schema

COMPILER_SCHEMA = {
    "attribute": "str",
    "task_class": "str",
    "preferred_metadata_terms": "{row_label: list[str], column_header: list[str], table_title: list[str], section_title: list[str]}",
    "rejected_metadata_terms": "{row_label: list[str], column_header: list[str], table_title: list[str], section_title: list[str]}",
    "period_policy": "str",
    "scope_policy": "str",
    "unit_policy": "str",
    "value_form": "str",
    "allowed_operations": "list[str]",
    "tie_break_order": "list[str]",
    "abstain_on_conflict": "bool",
}
CRITIC_SCHEMA = {
    "violations": "list[str]",
    "invalid_terms": "list[str]",
    "predicate_literal_risk": "str",
    "component_vs_total": "str",
    "name_vs_code": "str",
    "period_ambiguity": "str",
    "unit_ambiguity": "str",
    "corpus_leakage": "str",
    "unresolved_contradiction": "str",
}
DSL_TEXT = """{
  "attribute": "",
  "task_class": "extractive | categorical",
  "preferred_metadata_terms": {"row_label": [], "column_header": [], "table_title": [], "section_title": []},
  "rejected_metadata_terms": {"row_label": [], "column_header": [], "table_title": [], "section_title": []},
  "period_policy": "reporting_period | latest | period_end | any",
  "scope_policy": "total | consolidated | entity_level | component | any",
  "unit_policy": "preserve | resolve_from_header | percent | any",
  "value_form": "number | full_legal_name | short_code | categorical | text",
  "allowed_operations": ["identity"],
  "tie_break_order": [],
  "abstain_on_conflict": true
}"""


def compiler_user(spec: Any, samples: list[dict[str, Any]], feats_by_key: dict[tuple[str, str], list[dict[str, Any]]]) -> str:
    blocks = []
    for index, row in enumerate(samples, start=1):
        feats = feats_by_key.get((row["entity_id"], row["attribute"])) or []
        cards = "\n".join(card_line(item) for item in feats) or "(no candidates)"
        blocks.append(f"Representative set {index} (unlabeled):\n{cards}")
    labels = ", ".join(spec.schema_domain) if spec.schema_domain else "(none)"
    ops = "identity, none"
    if spec.allows_sum:
        ops = "identity, none"
    return (
        "Compile one reusable selection specification for this attribute. "
        "Do not select candidates for any entity. Do not emit a cell value.\n"
        f"Attribute: {spec.name}\n"
        f"Official description: {spec.official_description}\n"
        f"SQL type: {spec.sql_type}\n"
        f"Authoritative categorical domain: {labels}\n"
        f"Permitted operations: {ops}\n"
        "Use only the safe DSL. Terms must come from the official description, "
        "metadata tokens shared by at least two representative sets, or generic words "
        "such as total, consolidated, current, external auditor, period end.\n"
        "Do not include candidate IDs, numeric values, company names, document-specific phrases, "
        "Python, regex, SQL, weights, or thresholds.\n"
        f"DSL:\n{DSL_TEXT}\n\n"
        + "\n\n".join(blocks)
    )


def critic_user(spec: Any, compiled: dict[str, Any], samples: list[dict[str, Any]], feats_by_key: dict[tuple[str, str], list[dict[str, Any]]]) -> str:
    cards = []
    for index, row in enumerate(samples, start=1):
        feats = feats_by_key.get((row["entity_id"], row["attribute"])) or []
        cards.append(f"Set {index}:\n" + "\n".join(card_line(item, include_raw=False) for item in feats))
    return (
        "Critique this selection specification. Return structured violations only. "
        "Do not write a replacement specification. Do not emit a cell value.\n"
        f"Official description: {spec.official_description}\n"
        f"Specification JSON: {compiled}\n"
        "Check only: conflict with the official description; accidental preference for a "
        "predicate literal; selecting components where totals are required; abbreviations "
        "where a full legal name is required; period ambiguity; unit ambiguity; "
        "corpus- or entity-specific leakage.\n"
        "Representative metadata (values omitted):\n"
        + "\n\n".join(cards)
    )


def repair_user(malformed: str) -> str:
    return (
        "Repair this object so it matches the DSL exactly. Output only the DSL object. "
        "Do not add candidate IDs, values, or extra keys.\n"
        f"DSL:\n{DSL_TEXT}\n\n"
        f"Malformed JSON:\n{malformed}"
    )


def residual_user(
    spec: Any,
    feats: list[dict[str, Any]],
    metadata: str,
    program: dict[str, Any],
) -> str:
    cards = "\n".join(card_line(item) for item in feats) or "(no grounded candidates)"
    ops = "identity, none"
    if spec.task_class == "classification":
        labels = ", ".join(spec.schema_domain)
        return (
            "Classify one unresolved attribute using the official label space and remaining grounded cards.\n"
            "Do not invent a label outside the official domain. Do not emit a free-form extractive value.\n"
            f"Attribute: {spec.name}\n"
            f"Official description: {spec.official_description}\n"
            f"Official labels: {labels}\n"
            f"Program status: {program.get('status')}; reason: {program.get('reason')}; "
            f"survivors: {program.get('survivors')}\n"
            f"Document metadata: {metadata}\n\n"
            f"Evidence cards:\n{cards}"
        )
    return (
        "Select grounded candidate IDs for one unresolved attribute. Do not emit a value.\n"
        f"Attribute: {spec.name}\n"
        f"Official description: {spec.official_description}\n"
        f"Requested type: {spec.dtype} ({spec.sql_type})\n"
        f"Allowed operations: {ops}\n"
        f"Program status: {program.get('status')}; reason: {program.get('reason')}; "
        f"unresolved conflict: {program.get('tie')}\n"
        "Return status selected with one or more candidate_ids, or status abstain with operation none.\n"
        f"Document metadata: {metadata}\n\n"
        f"Candidates:\n{cards}"
    )


def assemble_tools(schema: dict[str, str], user: str, model: str = DOCETL_MODEL) -> dict[str, Any]:
    tools, tool_choice = tools_for_schema(schema, model)
    messages = [{"role": "system", "content": DOCETL_SYSTEM}, {"role": "user", "content": user}]
    return {
        "user": user,
        "messages": messages,
        "tools": tools,
        "tool_choice": tool_choice,
        "request": canonical_request(model=model, messages=messages, tools=tools, tool_choice=tool_choice),
        "output_schema": schema,
        "model": model,
    }
