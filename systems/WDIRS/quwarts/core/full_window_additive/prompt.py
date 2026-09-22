"""DocETL extract_fields prompt structure, rendered through QuWARTS."""

from __future__ import annotations

from quwarts.core.docetl_unit_parity.schema import QuerySchema
from quwarts.core.full_window_additive.config import PROMPT_TEMPLATE, SYSTEM
from quwarts.core.full_window_additive.truncate import truncate_messages


def render_user(schema: QuerySchema, document: str, sql: str) -> str:
    numeric = [item.name for item in schema.fields if item.dtype == "numeric"]
    return PROMPT_TEMPLATE.format(
        table="finance",
        nl_query=sql,
        field_list="\n".join(f"- {item.name}" for item in schema.fields),
        numeric_guidance=", ".join(numeric) if numeric else "none",
        document=document,
    )


def render_messages(
    schema: QuerySchema,
    document: str,
    sql: str,
    input_cap: int,
    document_tokens: int | None = None,
) -> dict:
    from quwarts.core.retrieve_extract.tokens import count_tokens
    from quwarts.core.full_window_additive.truncate import mid_cut

    prefix = render_user(schema, "", sql)
    overhead = count_tokens(SYSTEM) + count_tokens(prefix)
    doc_tokens = document_tokens if document_tokens is not None else count_tokens(document)
    used_doc = document
    did_cut = False
    if overhead + doc_tokens > input_cap:
        used_doc = mid_cut(document, overhead + doc_tokens - input_cap + 8)
        did_cut = True
    user = render_user(schema, used_doc, sql)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    after = count_tokens(SYSTEM) + count_tokens(user)
    guard = 0
    while after > input_cap and guard < 6:
        messages, did_cut, _before, after = truncate_messages(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            input_cap,
        )
        user = messages[1]["content"]
        after = count_tokens(SYSTEM) + count_tokens(user)
        guard += 1
    if after > input_cap:
        extra = after - input_cap + 16
        user = mid_cut(user, extra)
        after = count_tokens(SYSTEM) + count_tokens(user)
    return {
        "messages": messages,
        "system": SYSTEM,
        "user": user,
        "truncated": did_cut,
        "tokens_before": overhead + doc_tokens,
        "tokens_after": after,
    }
