"""Recreate DocETL extract_fields primary messages without copying stored prompts."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

DOCETL_MODEL = "openrouter/qwen/qwen-2.5-7b-instruct"
DOCETL_SYSTEM = (
    "You are a a helpful assistant, helping the user make sense of their data. "
    "The dataset description is: a collection of unstructured documents. "
    "You will be performing a map operation (one input:one output). "
    "You will perform the specified task on the provided data, as precisely and "
    "exhaustively (i.e., high recall) as possible. The result should be a structured "
    "output that you will send back to the user, with the `send_output` function. "
    "Do not influence your answers too much based on the `send_output` function "
    "parameter names; just use them to send the result back to the user."
)

TRANSPORT_KEYS = {
    "call_index",
    "ts",
    "latency_s",
    "spent_after",
    "cache_status",
    "bypass_cache",
    "retry_index",
    "provider_error",
    "raw_response",
    "raw_response_sha256",
    "parsed_response",
    "parse_validation_failure",
    "api_prompt_tokens",
    "api_completion_tokens",
}


def numeric_fields_from_attributes(path: Path) -> set[str]:
    payload = json.loads(path.read_text())
    out: set[str] = set()
    tables = payload.get("finance") or payload
    if isinstance(tables, dict) and "finance" in tables:
        tables = tables["finance"]
    for name, spec in (tables or {}).items():
        value_type = str((spec or {}).get("value_type") or "").lower()
        if value_type in {"int", "integer", "float", "number", "real"}:
            out.add(str(name).strip().lower())
    out.add("total_debt")
    return out


def schema_from_ast(sql: str, table: str = "finance") -> list[str]:
    tree = sqlglot.parse_one(sql)
    alias_to_table: dict[str, str] = {}
    tables: list[str] = []
    for node in tree.find_all(exp.Table):
        base = (node.name or "").strip().lower()
        if not base:
            continue
        alias_to_table[base] = base
        alias = (node.alias_or_name or "").strip().lower()
        if alias:
            alias_to_table[alias] = base
        if base not in tables:
            tables.append(base)
    select_aliases: set[str] = set()
    for select in tree.find_all(exp.Select):
        for expr in select.expressions:
            alias = (expr.alias or "").strip().lower()
            if not alias:
                continue
            inner = expr.this if isinstance(expr, exp.Alias) else expr
            if isinstance(inner, exp.Column) and (inner.name or "").strip().lower() == alias:
                continue
            select_aliases.add(alias)
    by_table: dict[str, set[str]] = defaultdict(set)
    unqualified: list[str] = []
    for col in tree.find_all(exp.Column):
        cname = (col.name or "").strip().lower()
        if not cname:
            continue
        tname = (col.table or "").strip().lower()
        if not tname and cname in select_aliases:
            continue
        if tname:
            by_table[alias_to_table.get(tname, tname)].add(cname)
        else:
            unqualified.append(cname)
    for cname in unqualified:
        if cname in select_aliases:
            continue
        if len(tables) == 1:
            by_table[tables[0]].add(cname)
    return sorted(by_table.get(table, set()))


def extract_fields_user(table: str, sql: str, fields: list[str], numeric: set[str], document: str) -> str:
    field_list = "\n".join(f"- {name}" for name in fields)
    numeric_guidance = ", ".join(name for name in fields if name in numeric) or "none"
    return (
        f"You are building a structured {table} table for this natural-language query:\n"
        f"{sql}\n\n"
        f"From this {table} document, extract exactly one record with these fields:\n"
        f"{field_list}\n\n"
        "For numeric fields, return numbers (not quoted strings). "
        f"Numeric fields in this extraction: {numeric_guidance}.\n"
        "If a numeric field is unknown, return -1. "
        "If a text field is unknown, return empty string. "
        "Keep names concise and normalized.\n\n"
        f"Document:\n{document}"
    )


def tools_for_schema(output_schema: dict[str, str], model: str = DOCETL_MODEL) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from docetl.operations.utils.validation import convert_val

    props = {key: convert_val(value, model) for key, value in output_schema.items()}
    parameters: dict[str, Any] = {"type": "object", "properties": props, "required": list(props.keys())}
    if "gemini" not in model and "claude" not in model:
        parameters["additionalProperties"] = False
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "send_output",
                "description": "Send output back to the user",
                "parameters": parameters,
            },
        }
    ]
    if "claude" not in model:
        tools[0]["additionalProperties"] = False
        tools[0]["strict"] = True
    tool_choice = {"type": "function", "function": {"name": "send_output"}}
    return tools, tool_choice


def canonical_request(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    tool_choice: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": row.get("role"), "content": row.get("content")} for row in messages],
        "tools": tools,
        "tool_choice": tool_choice,
    }


def generate_primary_request(
    sql: str,
    document: str,
    numeric: set[str],
    *,
    table: str = "finance",
    model: str = DOCETL_MODEL,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    generated = generate_primary_messages(sql, document, numeric, table=table, model=model, fields=fields)
    tools, tool_choice = tools_for_schema(generated["output_schema"], model)
    request = canonical_request(model=model, messages=generated["messages"], tools=tools, tool_choice=tool_choice)
    return {
        **generated,
        "tools": tools,
        "tool_choice": tool_choice,
        "request": request,
    }


def stored_primary_request(row: dict[str, Any]) -> dict[str, Any]:
    schema = dict(row.get("output_schema") or {})
    tools, tool_choice = tools_for_schema(schema, str(row.get("model") or DOCETL_MODEL))
    messages = [
        {"role": "system", "content": row.get("system_message") or ""},
        {"role": "user", "content": row.get("user_message") or ""},
    ]
    return canonical_request(model=str(row.get("model") or DOCETL_MODEL), messages=messages, tools=tools, tool_choice=tool_choice)


def requests_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return json.dumps(left, ensure_ascii=False, default=str) == json.dumps(right, ensure_ascii=False, default=str)


def generate_primary_messages(
    sql: str,
    document: str,
    numeric: set[str],
    *,
    table: str = "finance",
    model: str = DOCETL_MODEL,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    from docetl.operations.utils.llm import truncate_messages

    names = list(fields) if fields is not None else schema_from_ast(sql, table)
    user = extract_fields_user(table, sql, names, numeric, document)
    messages = [{"role": "system", "content": DOCETL_SYSTEM}, {"role": "user", "content": user}]
    truncated = truncate_messages(json.loads(json.dumps(messages)), model)
    system = "".join(str(row.get("content") or "") for row in truncated if row.get("role") == "system")
    user_out = "".join(str(row.get("content") or "") for row in truncated if row.get("role") == "user")
    return {
        "messages": truncated,
        "system": system,
        "user": user_out,
        "fields": names,
        "output_schema": {name: ("number" if name in numeric else "str") for name in names},
        "model": model,
        "temperature": None,
        "completion_cap": None,
    }


def tools_for_schema(output_schema: dict[str, str], model: str = DOCETL_MODEL) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from docetl.operations.utils.validation import convert_val

    props = {key: convert_val(value, model) for key, value in output_schema.items()}
    parameters: dict[str, Any] = {"type": "object", "properties": props, "required": list(props.keys())}
    if "gemini" not in model and "claude" not in model:
        parameters["additionalProperties"] = False
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "send_output",
                "description": "Send output back to the user",
                "parameters": parameters,
            },
        }
    ]
    if "claude" not in model:
        tools[0]["additionalProperties"] = False
        tools[0]["strict"] = True
    tool_choice = {"type": "function", "function": {"name": "send_output"}}
    return tools, tool_choice


def canonical_request(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    tool_choice: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": row.get("role"), "content": row.get("content")} for row in messages],
        "tools": tools,
        "tool_choice": tool_choice,
    }


def generate_primary_request(
    sql: str,
    document: str,
    numeric: set[str],
    *,
    table: str = "finance",
    model: str = DOCETL_MODEL,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    generated = generate_primary_messages(sql, document, numeric, table=table, model=model, fields=fields)
    tools, tool_choice = tools_for_schema(generated["output_schema"], model)
    request = canonical_request(model=model, messages=generated["messages"], tools=tools, tool_choice=tool_choice)
    return {**generated, "tools": tools, "tool_choice": tool_choice, "request": request}


def stored_primary_request(row: dict[str, Any]) -> dict[str, Any]:
    schema = dict(row.get("output_schema") or {})
    tools, tool_choice = tools_for_schema(schema, str(row.get("model") or DOCETL_MODEL))
    messages = [
        {"role": "system", "content": row.get("system_message") or ""},
        {"role": "user", "content": row.get("user_message") or ""},
    ]
    return canonical_request(model=str(row.get("model") or DOCETL_MODEL), messages=messages, tools=tools, tool_choice=tool_choice)


def requests_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return json.dumps(left, ensure_ascii=False, default=str) == json.dumps(right, ensure_ascii=False, default=str)


def strip_transport(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "query_id": row.get("query_id"),
        "document_id": None if row.get("document_id") in (None, "") else str(row.get("document_id")),
        "model": row.get("model"),
        "system": row.get("system_message") if "system_message" in row else row.get("system"),
        "user": row.get("user_message") if "user_message" in row else row.get("user"),
        "output_schema": row.get("output_schema"),
        "temperature": row.get("temperature"),
        "completion_cap": row.get("completion_cap"),
    }


def first_differing_byte(left: str, right: str) -> int | None:
    raw_l = (left or "").encode("utf-8")
    raw_r = (right or "").encode("utf-8")
    n = min(len(raw_l), len(raw_r))
    for index in range(n):
        if raw_l[index] != raw_r[index]:
            return index
    if len(raw_l) != len(raw_r):
        return n
    return None
