"""Deterministic grounded candidates from layout blocks and an official description.

Ranking uses only the attribute name and its schema description. No corpus
word lists, currency inventories, or domain stop lists.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from quwarts.core.candidate_select.config import MAX_CANDIDATES
from quwarts.core.candidate_select.schema_spec import AttrSpec
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.shared_bundle.context_blocks import Block, tokens_of
from quwarts.experiments.extract_util import field_terms

_NUM = re.compile(r"(?P<span>\(?-?\d[\d,]*(?:\.\d+)?%?\)?)")
_YEAR = re.compile(r"\b(\d{4})\b")
_SENT = re.compile(r"(?<=[.!?])\s+")
_CODE3 = re.compile(r"\b[A-Z]{3}\b")
_SCALE = {
    "thousand": 1_000,
    "thousands": 1_000,
    "k": 1_000,
    "million": 1_000_000,
    "millions": 1_000_000,
    "m": 1_000_000,
    "billion": 1_000_000_000,
    "billions": 1_000_000_000,
    "b": 1_000_000_000,
    "bn": 1_000_000_000,
}


@dataclass
class Candidate:
    opaque_id: str
    raw_span: str
    normalized: Any
    row_label: str
    column_header: str
    table_title: str
    heading: str
    period: str | None
    unit: str | None
    currency: str | None
    start: int
    end: int
    neighbors: str
    local_text: str
    in_c1: bool
    score: float
    kind: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.opaque_id,
            "raw_span": self.raw_span,
            "normalized": self.normalized,
            "row_label": self.row_label,
            "column_header": self.column_header,
            "table_title": self.table_title,
            "heading": self.heading,
            "period": self.period,
            "unit": self.unit,
            "currency": self.currency,
            "start": self.start,
            "end": self.end,
            "neighbors": self.neighbors,
            "in_c1": self.in_c1,
            "score": round(self.score, 4),
            "kind": self.kind,
        }


def query_tokens(spec: AttrSpec) -> set[str]:
    return set(field_terms(spec.name) + tokens_of(spec.official_description))


def _overlap(query: set[str], text: str) -> float:
    have = set(tokens_of(text) + field_terms(text))
    if not query or not have:
        return 0.0
    return len(query & have) / len(query | have)


def _period(*parts: str) -> str | None:
    years = []
    for part in parts:
        years.extend(_YEAR.findall(part or ""))
    return years[-1] if years else None


def _adjacent_code(text: str) -> str | None:
    match = _CODE3.search(text or "")
    return match.group(0) if match else None


def _header_scale(text: str) -> tuple[str | None, int]:
    tokens = tokens_of(text or "")
    for token in tokens:
        if token in _SCALE:
            return token, _SCALE[token]
    return None, 1


def apply_header_scale(value: Any, header_text: str) -> Any:
    if not isinstance(value, (int, float)):
        return value
    _name, factor = _header_scale(header_text)
    if factor == 1:
        return value
    if abs(value) >= factor:
        return value
    scaled = value * factor
    return int(scaled) if float(scaled) == int(scaled) else scaled


def _row_label(text: str) -> str:
    cells = [part.strip() for part in re.split(r"\s*\|\s*|\s{2,}", text) if part.strip()]
    if not cells:
        return text[:80]
    for cell in cells:
        if not _NUM.search(cell):
            return cell[:120]
    return cells[0][:120]


def _parts(block: Block) -> tuple[str, str, str, str]:
    local = block.text
    heading = block.heading
    title = header = ""
    if block.kind == "table_row":
        lines = local.splitlines()
        if len(lines) >= 3:
            title, header, body = lines[0], lines[1], lines[-1]
        elif len(lines) == 2:
            header, body = lines[0], lines[1]
        else:
            body = local
        return _row_label(body), header, title, body
    return heading, heading, "", local


def generate_pool(blocks: list[Block], spec: AttrSpec, source: str, c1: str) -> list[Candidate]:
    query = query_tokens(spec)
    name_toks = set(field_terms(spec.name))
    c1_l = (c1 or "").lower()
    pool: list[Candidate] = []
    numeric = spec.dtype == "numeric" and spec.task_class == "extractive"
    for block in blocks:
        label, header, title, body = _parts(block)
        local = " ".join(part for part in (label, header, title, block.heading, body[:240]) if part)
        if name_toks.isdisjoint(tokens_of(local)) and query.isdisjoint(tokens_of(local)):
            continue
        score = max(
            _overlap(query, label),
            _overlap(query, header),
            _overlap(query, block.heading),
            _overlap(query, body[:240]),
            _overlap(name_toks, local),
        )
        if score <= 0:
            continue
        unit_text = " ".join(part for part in (header, title, block.heading) if part)
        period = _period(header, title, block.heading, body)
        if numeric:
            for match in _NUM.finditer(body):
                raw = match.group("span").strip()
                norm, span_unit, err = normalize_value(raw, "numeric")
                if err or norm is None:
                    continue
                norm = apply_header_scale(norm, unit_text)
                rel = body.find(raw)
                start = block.start + rel if rel >= 0 else block.start
                in_c1 = raw.lower() in c1_l or body[:80].lower() in c1_l
                pool.append(
                    Candidate(
                        opaque_id="",
                        raw_span=raw,
                        normalized=norm,
                        row_label=label,
                        column_header=header[:160],
                        table_title=title[:160],
                        heading=block.heading,
                        period=period,
                        unit=span_unit or _header_scale(unit_text)[0],
                        currency=_adjacent_code(raw) or _adjacent_code(unit_text),
                        start=start,
                        end=start + len(raw),
                        neighbors=" ".join(block.neighbors)[:160],
                        local_text=body[:240],
                        in_c1=in_c1,
                        score=score + (0.1 if in_c1 else 0.0),
                        kind=block.kind,
                    )
                )
            continue
        pieces = _SENT.split(body) if block.kind == "paragraph" else [body]
        for piece in pieces:
            text = " ".join(piece.split())
            if len(text) < 2:
                continue
            piece_score = max(score, _overlap(query, text))
            if piece_score <= 0:
                continue
            start = source.find(text[:40]) if text[:40] else block.start
            if start < 0:
                start = block.start
            clipped = text[:180]
            in_c1 = clipped[:80].lower() in c1_l
            pool.append(
                Candidate(
                    opaque_id="",
                    raw_span=clipped,
                    normalized=clipped,
                    row_label=label,
                    column_header=header[:160],
                    table_title=title[:160],
                    heading=block.heading,
                    period=_period(header, title, block.heading, text),
                    unit=_header_scale(unit_text)[0],
                    currency=_adjacent_code(text),
                    start=start,
                    end=start + len(clipped),
                    neighbors=" ".join(block.neighbors)[:160],
                    local_text=text[:240],
                    in_c1=in_c1,
                    score=piece_score + (0.1 if in_c1 else 0.0),
                    kind=block.kind,
                )
            )
    return pool


def rank_and_cap(pool: list[Candidate], spec: AttrSpec) -> list[Candidate]:
    pool.sort(key=lambda item: (-item.score, item.start, str(item.normalized)))
    kept: list[Candidate] = []
    seen: set[tuple[Any, ...]] = set()
    groups: dict[tuple[Any, ...], int] = {}
    for item in pool:
        key = (item.normalized, item.period, item.unit, item.start, item.end)
        if key in seen:
            continue
        bucket = (item.period, item.heading, item.normalized)
        if groups.get(bucket, 0) >= 2 and len(kept) >= 3:
            continue
        seen.add(key)
        groups[bucket] = groups.get(bucket, 0) + 1
        kept.append(item)
        if len(kept) >= MAX_CANDIDATES:
            break
    for index, item in enumerate(kept, start=1):
        item.opaque_id = f"C{index}"
    return kept


def candidates_hash(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
