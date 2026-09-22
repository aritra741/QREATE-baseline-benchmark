"""Mid-cut truncation matching DocETL truncate_messages, counted with the Qwen tokenizer."""

from __future__ import annotations

from quwarts.core.retrieve_extract.tokens import count_tokens, qwen_tokenizer


def message_tokens(messages: list[dict[str, str]]) -> int:
    return sum(count_tokens(str(row.get("content") or "")) for row in messages)


def mid_cut(text: str, tokens_to_remove: int) -> str:
    tokenizer = qwen_tokenizer()
    encoded = tokenizer.encode(text)
    ids = list(encoded.ids)
    if tokens_to_remove <= 0 or not ids:
        return text
    tokens_to_remove = min(len(ids), tokens_to_remove)
    marker = tokenizer.encode(f" ... [{tokens_to_remove} tokens truncated] ... ").ids
    mid = len(ids) // 2
    left = mid - tokens_to_remove // 2
    right = mid + tokens_to_remove // 2
    left = max(0, left)
    right = min(len(ids), right)
    kept = ids[:left] + list(marker) + ids[right:]
    return tokenizer.decode(kept)


def truncate_messages(messages: list[dict[str, str]], input_cap: int) -> tuple[list[dict[str, str]], bool, int, int]:
    before = message_tokens(messages)
    if before <= input_cap:
        return [dict(row) for row in messages], False, before, before
    out = [dict(row) for row in messages]
    longest = max(range(len(out)), key=lambda i: count_tokens(str(out[i].get("content") or "")))
    excess = before - input_cap + 8
    out[longest]["content"] = mid_cut(str(out[longest].get("content") or ""), excess)
    after = message_tokens(out)
    if after > input_cap:
        extra = after - input_cap + 8
        out[longest]["content"] = mid_cut(str(out[longest].get("content") or ""), extra)
        after = message_tokens(out)
    return out, True, before, after
