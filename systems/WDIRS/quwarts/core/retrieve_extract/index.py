"""Section/page-aware document index. Built even when whole-document mode wins."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from quwarts.core.retrieve_extract.config import FROZEN
from quwarts.core.retrieve_extract.tokens import count_tokens, encode_offsets

_HEADING = re.compile(
    r"^(?:#{1,6}\s+\S.*|[A-Z][A-Z0-9][A-Z0-9 /&.,'()-]{6,}|(\d+(\.\d+){0,4})\s+[A-Z][^\n]{3,80}|Page\s+\d+)\s*$",
    re.MULTILINE,
)
_PAGE = re.compile(r"\f|(?:^|\n)\s*(?:Page|PAGE)\s+(\d+)\b")
_TABLE_LINE = re.compile(r"(?:\|.+\|)|(?:\b\d[\d,]*(?:\.\d+)?\b.*){3,}")


@dataclass
class Chunk:
    source_id: str
    doc_id: str
    page: int
    heading: str
    heading_path: tuple[str, ...]
    start: int
    end: int
    text: str
    tokens: int
    adjacent_prev: str | None
    adjacent_next: str | None
    is_table: bool
    header_text: str
    digest: str

    def packed_text(self) -> str:
        if self.is_table and self.header_text and self.header_text not in self.text:
            return f"{self.header_text}\n{self.text}"
        return self.text


@dataclass
class DocumentIndex:
    doc_id: str
    text: str
    document_tokens: int
    digest: str
    chunks: list[Chunk] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)

    def chunk_map(self) -> dict[str, Chunk]:
        return {chunk.source_id: chunk for chunk in self.chunks}


def _char_to_token(offsets: list[tuple[int, int]], pos: int) -> int:
    lo, hi = 0, len(offsets)
    while lo < hi:
        mid = (lo + hi) // 2
        if offsets[mid][1] <= pos:
            lo = mid + 1
        else:
            hi = mid
    return min(lo, max(len(offsets) - 1, 0))


def _pages(text: str) -> list[tuple[int, int, int]]:
    marks = [(0, 1)]
    for match in _PAGE.finditer(text):
        page = int(match.group(1) or len(marks) + 1) if match.lastindex else len(marks) + 1
        marks.append((match.start(), page))
    marks.append((len(text), marks[-1][1]))
    spans = []
    for index, (start, page) in enumerate(marks[:-1]):
        end = marks[index + 1][0]
        if end > start:
            spans.append((start, end, page))
    return spans or [(0, len(text), 1)]


def _headings(text: str) -> list[tuple[int, str]]:
    found = [(0, "document")]
    for match in _HEADING.finditer(text):
        title = " ".join(match.group(0).split())
        if title:
            found.append((match.start(), title[:160]))
    return found


def _heading_at(headings: list[tuple[int, str]], pos: int) -> tuple[str, tuple[str, ...]]:
    current = headings[0]
    path: list[str] = [current[1]]
    for start, title in headings[1:]:
        if start <= pos:
            current = (start, title)
            path.append(title)
        else:
            break
    return current[1], tuple(path[-3:])


def _table_header(text: str, start: int) -> tuple[bool, str]:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", start)
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end]
    is_table = bool(_TABLE_LINE.search(line))
    header = ""
    if is_table:
        prev_end = max(0, line_start - 1)
        prev_start = text.rfind("\n", 0, prev_end) + 1
        prev = text[prev_start:prev_end].strip()
        if prev and (not _TABLE_LINE.search(prev) or "|" in prev):
            header = prev[:240]
    return is_table, header


def index_document(doc_id: str, text: str) -> DocumentIndex:
    target = int(FROZEN["chunk_target_tokens"])
    overlap = int(FROZEN["chunk_overlap_tokens"])
    digest = hashlib.sha256(f"{doc_id}\n{text}".encode()).hexdigest()
    if not text:
        return DocumentIndex(doc_id=doc_id, text=text, document_tokens=0, digest=digest)
    ids, offsets = encode_offsets(text)
    headings = _headings(text)
    pages = _pages(text)
    page_at = []
    cursor = 0
    for start, end, page in pages:
        while cursor < len(offsets) and offsets[cursor][0] < end:
            page_at.append(page)
            cursor += 1
    while len(page_at) < len(ids):
        page_at.append(pages[-1][2])

    chunks: list[Chunk] = []
    step = max(1, target - overlap)
    for index, token_start in enumerate(range(0, len(ids), step)):
        token_end = min(len(ids), token_start + target)
        if token_end <= token_start:
            continue
        start = offsets[token_start][0]
        end = offsets[token_end - 1][1]
        if end <= start:
            continue
        heading, path = _heading_at(headings, start)
        is_table, header = _table_header(text, start)
        source_id = f"{doc_id}:c{index}"
        body = text[start:end]
        chunks.append(
            Chunk(
                source_id=source_id,
                doc_id=doc_id,
                page=page_at[token_start] if token_start < len(page_at) else 1,
                heading=heading,
                heading_path=path,
                start=start,
                end=end,
                text=body,
                tokens=token_end - token_start,
                adjacent_prev=f"{doc_id}:c{index - 1}" if index else None,
                adjacent_next=None,
                is_table=is_table,
                header_text=header,
                digest=hashlib.sha256(body.encode()).hexdigest(),
            )
        )
    for index, chunk in enumerate(chunks[:-1]):
        chunk.adjacent_next = chunks[index + 1].source_id

    sections = []
    for index, (start, title) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
        section_text = text[start:end]
        sections.append(
            {
                "section_id": f"{doc_id}:s{index}",
                "heading": title,
                "start": start,
                "end": end,
                "tokens": count_tokens(section_text) if len(section_text) < 20000 else max(1, (end - start) // 4),
            }
        )
    return DocumentIndex(
        doc_id=doc_id,
        text=text,
        document_tokens=len(ids),
        digest=digest,
        chunks=chunks,
        sections=sections,
    )
