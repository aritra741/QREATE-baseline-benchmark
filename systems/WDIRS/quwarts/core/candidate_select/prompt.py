"""Selector prompts. Official schema only. No query predicate literals."""

from __future__ import annotations

import json
from typing import Any

from quwarts.core.candidate_select.candidates import Candidate
from quwarts.core.candidate_select.schema_spec import AttrSpec
from quwarts.core.docetl_exact_message.adapter import DOCETL_MODEL, DOCETL_SYSTEM, canonical_request, tools_for_schema

EXTRACTIVE_SCHEMA = {"candidate_ids": "list[str]", "operation": "str", "status": "str"}
CLASSIFY_SCHEMA = {"label": "str", "evidence_ids": "list[str]", "status": "str"}


def document_metadata(text: str) -> str:
    head = " ".join((text or "")[:800].split())
    return head[:400]


def card_lines(candidates: list[Candidate], spec: AttrSpec) -> str:
    lines = []
    for item in candidates:
        if spec.dtype == "numeric" and spec.task_class == "extractive":
            lines.append(
                f"{item.opaque_id}: span={item.raw_span}; row={item.row_label}; "
                f"header={item.column_header}; title={item.table_title}; "
                f"period={item.period or 'unknown'}; unit={item.unit or 'unknown'}; "
                f"currency={item.currency or 'unspecified'}; offset={item.start}"
            )
        else:
            lines.append(
                f"{item.opaque_id}: text={item.raw_span}; heading={item.heading}; "
                f"row={item.row_label}; period={item.period or 'unknown'}; offset={item.start}"
            )
    return "\n".join(lines) if lines else "(no grounded candidates)"


def extractive_user(spec: AttrSpec, candidates: list[Candidate], metadata: str) -> str:
    ops = "identity, none"
    if spec.allows_sum:
        ops = "identity, sum, none"
    return (
        "Select grounded candidate IDs for one attribute. Do not emit a value.\n"
        f"Attribute: {spec.name}\n"
        f"Official description: {spec.official_description}\n"
        f"Requested type: {spec.dtype} ({spec.sql_type})\n"
        f"Allowed operations: {ops}\n"
        "Return status selected with one or more candidate_ids, or status abstain with operation none.\n"
        "Use sum only if the official description requires aggregating segments.\n"
        f"Document metadata: {metadata}\n\n"
        f"Candidates:\n{card_lines(candidates, spec)}"
    )


def classify_user(spec: AttrSpec, candidates: list[Candidate], metadata: str) -> str:
    labels = ", ".join(spec.schema_domain)
    return (
        "Classify one attribute using the official label space and grounded evidence cards.\n"
        "Do not invent a label outside the official domain. Do not emit a free-form extractive value.\n"
        f"Attribute: {spec.name}\n"
        f"Official description: {spec.official_description}\n"
        f"Official labels: {labels}\n"
        f"Document metadata: {metadata}\n\n"
        f"Evidence cards:\n{card_lines(candidates, spec)}"
    )


def assemble(spec: AttrSpec, candidates: list[Candidate], metadata: str, model: str = DOCETL_MODEL) -> dict[str, Any]:
    if spec.task_class == "classification":
        user = classify_user(spec, candidates, metadata)
        schema = CLASSIFY_SCHEMA
    else:
        user = extractive_user(spec, candidates, metadata)
        schema = EXTRACTIVE_SCHEMA
    tools, tool_choice = tools_for_schema(schema, model)
    messages = [{"role": "system", "content": DOCETL_SYSTEM}, {"role": "user", "content": user}]
    request = canonical_request(model=model, messages=messages, tools=tools, tool_choice=tool_choice)
    return {
        "task_class": spec.task_class,
        "user": user,
        "messages": messages,
        "tools": tools,
        "tool_choice": tool_choice,
        "request": request,
        "output_schema": schema,
        "model": model,
    }


def prefix_contains_literal(
    user: str,
    literals: list[str],
    cards: str,
    allowed_text: str = "",
) -> list[str]:
    """Workload literals injected into the instruction, excluding official schema text and source cards."""
    marker = "Candidates:\n" if "Candidates:\n" in user else "Evidence cards:\n"
    prefix = user[: user.find(marker)] if marker in user else user
    allowed = f"{allowed_text}\n{cards}"
    leaked = []
    for lit in literals:
        token = str(lit).strip()
        if not token or token in {"%", "0"}:
            continue
        bare = token.strip("%")
        if not bare or len(bare) < 3:
            continue
        if bare in prefix and bare not in allowed:
            leaked.append(token)
    return leaked
