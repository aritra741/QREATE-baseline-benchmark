"""Document-size router: whole document if it fits, else recovered DocETL mid-cut."""

from __future__ import annotations

import json
from typing import Any

from quwarts.core.full_window_additive.truncate import mid_cut, truncate_messages
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.shared_bundle.config import (
    LEDGER_SAFETY_MARGIN,
    MODEL_CONTEXT_LIMIT,
    TARGET_INPUT_HI,
    TARGET_INPUT_LO,
)


def request_input_tokens(request: dict[str, Any]) -> int:
    messages = request.get("messages") or []
    text = "".join(str(row.get("content") or "") for row in messages)
    return count_tokens(text) + count_tokens(json.dumps(request.get("tools") or [], default=str))


def instruction_tokens(rendered: dict[str, Any]) -> int:
    """Tokens of system + user without the document body + tools."""
    prefix = rendered.get("prefix")
    if prefix is None:
        user = str(rendered.get("user") or "")
        marker = "\nDocument:\n"
        prefix = user.rsplit(marker, 1)[0] + marker if marker in user else user
    return count_tokens(str(rendered.get("system") or "")) + count_tokens(str(prefix)) + count_tokens(
        json.dumps(rendered.get("tools") or [], default=str)
    )


def route_from_sizes(
    *,
    template: dict[str, Any],
    document: str,
    document_tokens: int,
    instruction_token_count: int,
    input_cap: int,
) -> dict[str, Any]:
    """Route from document size. Mid-cut only the document body when it overflows."""
    from quwarts.core.shared_bundle.prompt import assemble_request

    full_tokens = instruction_token_count + int(document_tokens)
    used_doc = document
    truncated = full_tokens > input_cap
    if truncated:
        room = max(1, int(input_cap) - int(instruction_token_count))
        extra = int(document_tokens) - room + 8
        used_doc = mid_cut(document, extra)
        guard = 0
        after_doc = count_tokens(used_doc)
        while instruction_token_count + after_doc > input_cap and guard < 6:
            used_doc = mid_cut(used_doc, instruction_token_count + after_doc - input_cap + 8)
            after_doc = count_tokens(used_doc)
            guard += 1
    assembled = assemble_request(template, used_doc)
    after = request_input_tokens(assembled["request"]) if truncated else full_tokens
    if after > input_cap:
        assembled = route_prompt(assembled, used_doc, input_cap)
        return assembled
    return {
        "request": assembled["request"],
        "messages": assembled["messages"],
        "user": assembled["user"],
        "truncated": truncated,
        "tokens_before": full_tokens,
        "tokens_after": after,
        "route": "mid_cut" if truncated else "whole_document",
    }


def derive_input_cap(*, completion_reservation: int, max_instruction_tokens: int) -> dict[str, int]:
    hard = MODEL_CONTEXT_LIMIT - int(completion_reservation) - LEDGER_SAFETY_MARGIN
    if hard < TARGET_INPUT_LO:
        raise SystemExit(f"derived input room {hard} is below {TARGET_INPUT_LO}")
    cap = min(TARGET_INPUT_HI, hard)
    if cap < TARGET_INPUT_LO:
        raise SystemExit(f"uniform cap {cap} is below target {TARGET_INPUT_LO}")
    if max_instruction_tokens >= cap:
        raise SystemExit(f"instruction/tool schema {max_instruction_tokens} exceeds input cap {cap}")
    return {
        "input_cap": cap,
        "model_context_limit": MODEL_CONTEXT_LIMIT,
        "completion_reservation": int(completion_reservation),
        "ledger_safety_margin": LEDGER_SAFETY_MARGIN,
        "max_instruction_tokens": int(max_instruction_tokens),
        "document_room": cap - int(max_instruction_tokens),
    }


def route_prompt(rendered: dict[str, Any], document: str, input_cap: int) -> dict[str, Any]:
    full_tokens = request_input_tokens(rendered["request"])
    if full_tokens <= input_cap:
        return {
            "request": rendered["request"],
            "messages": rendered["messages"],
            "user": rendered["user"],
            "truncated": False,
            "tokens_before": full_tokens,
            "tokens_after": full_tokens,
            "route": "whole_document",
        }
    tool_tokens = count_tokens(json.dumps(rendered["request"].get("tools") or [], default=str))
    message_cap = max(1, int(input_cap) - tool_tokens)
    messages = [dict(row) for row in rendered["messages"]]
    truncated, did_cut, before, after = truncate_messages(messages, message_cap)
    guard = 0
    while after > message_cap and guard < 6:
        extra = after - message_cap + 8
        longest = max(range(len(truncated)), key=lambda i: count_tokens(str(truncated[i].get("content") or "")))
        truncated[longest]["content"] = mid_cut(str(truncated[longest].get("content") or ""), extra)
        after = sum(count_tokens(str(row.get("content") or "")) for row in truncated)
        did_cut = True
        guard += 1
    if after > message_cap:
        extra = after - message_cap + 16
        longest = max(range(len(truncated)), key=lambda i: count_tokens(str(truncated[i].get("content") or "")))
        truncated[longest]["content"] = mid_cut(str(truncated[longest].get("content") or ""), extra)
        after = sum(count_tokens(str(row.get("content") or "")) for row in truncated)
        did_cut = True
    user = "".join(str(row.get("content") or "") for row in truncated if row.get("role") == "user")
    request = {
        "model": rendered["request"]["model"],
        "messages": [{"role": row.get("role"), "content": row.get("content")} for row in truncated],
        "tools": rendered["request"]["tools"],
        "tool_choice": rendered["request"]["tool_choice"],
    }
    after_full = request_input_tokens(request)
    return {
        "request": request,
        "messages": truncated,
        "user": user,
        "truncated": True,
        "tokens_before": full_tokens,
        "tokens_after": after_full,
        "route": "mid_cut",
        "message_tokens_after": after,
        "did_cut": did_cut,
        "tokens_before_messages": before,
    }
