"""DocETL system + tool-call request with a deterministic workload-use block."""

from __future__ import annotations

import json
from typing import Any

from quwarts.core.docetl_exact_message.adapter import DOCETL_MODEL, DOCETL_SYSTEM, canonical_request, tools_for_schema
from quwarts.core.shared_bundle.graph import Bundle
from quwarts.core.shared_bundle.inventory import AttributeRecord

_USE_LABELS = {
    "WHERE": "filtering",
    "JOIN": "filtering",
    "HAVING": "filtering",
    "GROUP BY": "grouping",
    "CASE": "CASE",
    "aggregate input": "aggregation",
}


def _uses(record: AttributeRecord) -> list[str]:
    labels = []
    for role, label in _USE_LABELS.items():
        if record.roles.get(role):
            if label not in labels:
                labels.append(label)
    return labels


def workload_use_block(bundle: Bundle, records: dict[str, AttributeRecord], table: str) -> str:
    parts = [f"Shared {table} workload extraction. Attributes are reused by every query that references them."]
    for name in bundle.attributes:
        rec = records[name]
        uses = ", ".join(_uses(rec)) or "referenced"
        exprs = "\n".join(f"  {text}" for text in rec.expressions) or "  (none)"
        lits = ", ".join(rec.predicate_literals) if rec.predicate_literals else "none"
        parts.append(
            f"Attribute: {name}\n"
            f"Declared type: {rec.sql_type}\n"
            f"Used by: {uses}\n"
            f"SQL expressions:\n{exprs}\n"
            f"Visible predicate literals: {lits}"
        )
    return "\n\n".join(parts)


def extract_fields_user(table: str, use_block: str, fields: list[str], numeric: list[str], document: str) -> str:
    field_list = "\n".join(f"- {name}" for name in fields)
    numeric_guidance = ", ".join(numeric) if numeric else "none"
    return (
        f"You are building a structured {table} table for this shared workload:\n"
        f"{use_block}\n\n"
        f"From this {table} document, extract exactly one record with these fields:\n"
        f"{field_list}\n\n"
        "For numeric fields, return numbers (not quoted strings). "
        f"Numeric fields in this extraction: {numeric_guidance}.\n"
        "If a numeric field is unknown, return -1. "
        "If a text field is unknown, return empty string. "
        "Keep names concise and normalized.\n\n"
        f"Document:\n{document}"
    )


def output_schema(bundle: Bundle, records: dict[str, AttributeRecord]) -> dict[str, str]:
    return {name: ("number" if records[name].dtype == "numeric" else "str") for name in bundle.attributes}


_TOOLS: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = {}


def cached_tools(schema: dict[str, str], model: str = DOCETL_MODEL) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    key = json.dumps({"model": model, "schema": schema}, sort_keys=True)
    if key not in _TOOLS:
        _TOOLS[key] = tools_for_schema(schema, model)
    return _TOOLS[key]


def render_bundle_template(
    *,
    table: str,
    bundle: Bundle,
    records: dict[str, AttributeRecord],
    model: str = DOCETL_MODEL,
) -> dict[str, Any]:
    fields = list(bundle.attributes)
    numeric = [name for name in fields if records[name].dtype == "numeric"]
    use_block = workload_use_block(bundle, records, table)
    prefix = extract_fields_user(table, use_block, fields, numeric, "")
    schema = output_schema(bundle, records)
    tools, tool_choice = cached_tools(schema, model)
    return {
        "system": DOCETL_SYSTEM,
        "prefix": prefix,
        "use_block": use_block,
        "fields": fields,
        "output_schema": schema,
        "tools": tools,
        "tool_choice": tool_choice,
        "model": model,
        "bundle_signature": bundle.signature,
    }


def assemble_request(template: dict[str, Any], document: str) -> dict[str, Any]:
    user = template["prefix"] + document
    messages = [{"role": "system", "content": template["system"]}, {"role": "user", "content": user}]
    request = canonical_request(model=template["model"], messages=messages, tools=template["tools"], tool_choice=template["tool_choice"])
    return {
        "messages": messages,
        "system": template["system"],
        "user": user,
        "use_block": template["use_block"],
        "fields": template["fields"],
        "output_schema": template["output_schema"],
        "tools": template["tools"],
        "tool_choice": template["tool_choice"],
        "request": request,
        "model": template["model"],
    }


def render_bundle_request(
    *,
    table: str,
    bundle: Bundle,
    records: dict[str, AttributeRecord],
    document: str,
    model: str = DOCETL_MODEL,
) -> dict[str, Any]:
    template = render_bundle_template(table=table, bundle=bundle, records=records, model=model)
    return assemble_request(template, document)
