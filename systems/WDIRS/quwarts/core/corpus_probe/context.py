"""Choose whole-document versus exhaustive chunk-and-reduce from rendered size only."""

from __future__ import annotations

from typing import Any

from quwarts.core.retrieve_extract.tokens import count_tokens

EFFECTIVE_INPUT_LIMIT = 11_000
COMPLETION_SPACE = 192
SAFETY_MARGIN = 700
CHUNK_TOKENS = 2_800


def route_context(wrapper_tokens: int, document_tokens: int) -> str:
    if wrapper_tokens + document_tokens + COMPLETION_SPACE + SAFETY_MARGIN <= EFFECTIVE_INPUT_LIMIT:
        return "whole_document"
    return "exhaustive_chunk_reduce"


def whole_document_budget() -> int:
    return EFFECTIVE_INPUT_LIMIT - COMPLETION_SPACE - SAFETY_MARGIN


def exhaustive_chunks(text: str, max_tokens: int = CHUNK_TOKENS) -> list[dict[str, Any]]:
    body = text or ""
    if not body:
        return []
    paragraphs: list[tuple[int, int, str]] = []
    cursor = 0
    for part in body.splitlines(keepends=True):
        if part.strip():
            paragraphs.append((cursor, cursor + len(part), part))
        cursor += len(part)
    chunks: list[dict[str, Any]] = []
    buf: list[str] = []
    start = 0
    end = 0
    used = 0
    for p_start, p_end, para in paragraphs or [(0, len(body), body)]:
        tok = max(1, count_tokens(para))
        if buf and used + tok > max_tokens:
            text_chunk = "".join(buf)
            chunks.append({"index": len(chunks), "start": start, "end": end, "text": text_chunk, "tokens": count_tokens(text_chunk)})
            buf = []
            used = 0
        if not buf:
            start = p_start
        buf.append(para)
        end = p_end
        used += tok
    if buf:
        text_chunk = "".join(buf)
        chunks.append({"index": len(chunks), "start": start, "end": end, "text": text_chunk, "tokens": count_tokens(text_chunk)})
    return chunks


def inspect_record(mode: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "mode": mode,
        "n_chunks": len(chunks),
        "chunk_offsets": [{"index": row["index"], "start": row["start"], "end": row["end"], "tokens": row["tokens"]} for row in chunks],
    }
