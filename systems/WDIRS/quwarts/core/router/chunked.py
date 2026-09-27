"""Chained reads of long documents: long chunks read in order, with carried document context.

A document that fits the shared-read window is read once, as before. A longer one is split into
long chunks (the same window, less room for the carried notes), cut at a line break where possible,
and read in document order. Each chunk's call returns the fields that chunk states and a short note
for the next chunk: what a reader of the next part needs to interpret it (the entity the document is
about, the reporting period, currency and units, the current section). The next call gets that note
before its text, so a chunk that never names the company or the fiscal year is still read as being
about them. This is the sequential worker chain of Chain-of-Agents (Zhang et al., NeurIPS 2024) and
of DocETL's split / gather (whose gather attaches context from earlier chunks), with the carried
context written by the model instead of copied from neighbouring chunks.

Chunk answers are combined per field without further calls:

* nulls and the field's declared absence value ("No", "0 if none") are "not stated in this chunk"
  and do not vote; a field no chunk states takes its absence value at commit, as a single read does;
* a multi-valued field takes the union of its parts, in document order;
* any other field takes the most frequent committed value, ties to the earliest chunk.

The rule is declared here, before any run, and is not selected on scores. Every chunk call is
journaled with its index and prompt hash; the chain is resumable because the carried note is
recomputed from the journaled responses.
"""

from __future__ import annotations

import bisect
import json
import math
import re
from collections import Counter
from dataclasses import replace
from typing import Any

from quwarts.core.retrieve_extract.tokens import count_tokens, encode_offsets
from quwarts.core.router.comparator import as_text, is_null
from quwarts.core.router.context_probe import FieldSpec, truncate

CARRY_KEY = "context_for_next_part"
CARRY_ROOM = 300  # tokens kept free in each chunk's prompt for the carried note and chunk header
CARRY_MAX_TOKENS = 200  # a longer note is cut (it is a note, not a summary of the document)
LINE_BREAK_SLACK = 0.10  # cut at the last line break in a chunk's final 10%, if there is one


def chunk_tokens(window: int) -> int:
    return window - CARRY_ROOM


def split_chunks(text: str, max_tokens: int) -> list[str]:
    """Consecutive chunks of at most ``max_tokens`` Qwen tokens that concatenate to ``text``."""

    _ids, offsets = encode_offsets(text)
    if len(offsets) <= max_tokens:
        return [text]
    ends = [end for _start, end in offsets]
    chunks: list[str] = []
    token, start_char = 0, 0
    while token < len(offsets):
        # Even chunks (no short tail): split what remains into the fewest chunks of at most max_tokens.
        remaining = len(offsets) - token
        step = math.ceil(remaining / math.ceil(remaining / max_tokens))
        stop = min(token + step, len(offsets))
        end_char = len(text) if stop == len(offsets) else ends[stop - 1]
        if stop < len(offsets):
            floor = start_char + int((1 - LINE_BREAK_SLACK) * (end_char - start_char))
            newline = text.rfind("\n", floor, end_char)
            if newline > floor:
                end_char = newline + 1
        chunks.append(text[start_char:end_char])
        start_char = end_char
        nxt = bisect.bisect_right(ends, end_char)
        token = nxt if nxt > token else stop
    if start_char < len(text):
        chunks[-1] += text[start_char:]
    return chunks


def render_chunk_prompt(chunk: str, fields: list[FieldSpec], carry: str, index: int, total: int) -> str:
    """One chunk's prompt. Fields are asked as nullable: a chunk that does not state a field says so;
    never-null fields get their declared absence value when no chunk states them."""

    lines = [replace(f, nullable=True).line() for f in fields]
    head = (
        f"You are reading part {index} of {total} of one long document, in order. "
        "Extract the following fields about the single entity the document describes.\n"
        "Give a field only if this part states it for that entity; otherwise null.\n"
    )
    if any(f.choices for f in fields):
        head += "Follow each field's allowed values.\n"
    notes = carry.strip() or "None: this is the first part."
    body = (
        "\nDOCUMENT CONTEXT (notes carried from the earlier parts; use them to know which entity, period "
        f"and units this part refers to):\n{notes}\n\n"
        f"PART {index} OF {total}:\n{chunk}\n\n"
        "FIELDS:\n" + "\n".join(lines) + "\n\n"
        f"Then write {CARRY_KEY}: at most 80 words that a reader of the next part needs in order to "
        "interpret it, such as the entity the document is about and its name, the document type, the "
        "reporting period or date, currency and units, and the current section. Keep what is still true "
        "from the earlier notes and add what this part establishes.\n\n"
        'Return JSON with this shape and no other keys: {"fields": {"<field>": <value or null>}, '
        f'"{CARRY_KEY}": "<notes>"}}'
    )
    return head + body


_CARRY_RE = re.compile(r'"' + CARRY_KEY + r'"\s*:\s*"((?:[^"\\]|\\.)*)"', re.S)


def parse_carry(response: str, previous: str) -> str:
    """The note a chunk's response passes on; the previous note when the response has none."""

    body = re.sub(r"^```(?:json)?|```$", "", (response or "").strip(), flags=re.M).strip()
    note: Any = None
    start, end = body.find("{"), body.rfind("}")
    if start >= 0 and end > start:
        try:
            payload = json.loads(body[start : end + 1])
            if isinstance(payload, dict):
                note = payload.get(CARRY_KEY)
        except json.JSONDecodeError:
            pass
    if note is None:
        match = _CARRY_RE.search(body)
        if match:
            try:
                note = json.loads(f'"{match.group(1)}"')
            except json.JSONDecodeError:
                note = match.group(1)
    if isinstance(note, (dict, list)):
        note = json.dumps(note, ensure_ascii=False)
    if not isinstance(note, str) or not note.strip():
        return previous
    note = note.strip()
    return truncate(note, CARRY_MAX_TOKENS) if count_tokens(note) > CARRY_MAX_TOKENS else note


def _multi(field: FieldSpec) -> bool:
    return field.value_type.startswith("multi") or field.multi_choice


def reduce_chunks(answers: list[dict[str, Any]], field: FieldSpec) -> tuple[Any, list[int]]:
    """Combine one field's per-chunk raw answers (in document order). Returns the value to commit
    and the indices of the chunks that support it (its where-provenance)."""

    from quwarts.core.router.executor import commit_value

    absent = commit_value(None, field)
    votes: list[tuple[int, Any]] = []
    for index, answer in enumerate(answers):
        raw = answer.get(field.name)
        if is_null(raw):
            continue
        value = commit_value(raw, field)
        if value is None or (absent is not None and value == absent):
            continue
        votes.append((index, value))
    if not votes:
        return None, []
    if _multi(field):
        parts: list[str] = []
        support: dict[str, list[int]] = {}
        for index, value in votes:
            for part in (p.strip() for p in as_text(value).split("||")):
                key = part.casefold()
                if part and key not in support:
                    parts.append(part)
                    support[key] = []
                if part:
                    support[key].append(index)
        chunks = sorted({i for s in support.values() for i in s})
        return " || ".join(parts), chunks

    def key(value: Any) -> Any:
        return value.strip().casefold() if isinstance(value, str) else value

    counts = Counter(key(v) for _i, v in votes)
    first: dict[Any, int] = {}
    for position, (_i, v) in enumerate(votes):
        first.setdefault(key(v), position)
    best = max(counts, key=lambda k: (counts[k], -first[k]))
    value = votes[first[best]][1]
    return value, [i for i, v in votes if key(v) == best]
