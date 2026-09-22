"""Layout-preserving blocks and deterministic BM25 packing. No corpus names or gold."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.experiments.extract_util import field_terms

_HEADING = re.compile(
    r"^(?:#{1,6}\s+\S.*|[A-Z][A-Z0-9][A-Z0-9 /&.,'()-]{6,}|(\d+(\.\d+){0,4})\s+[A-Z][^\n]{3,80})$"
)
_TABLE = re.compile(r"(?:\|.+\|)|(?:\b\d[\d,]*(?:\.\d+)?\b.*){3,}")
_LIST = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+\S")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_/%-]{0,}")
_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "into", "your",
    "are", "was", "were", "been", "have", "has", "not", "use", "used",
    "when", "then", "else", "end", "as", "of", "to", "in", "on", "or",
}
_STEM_SUFFIX = ("ational", "tional", "edness", "ization", "fulness", "iveness", "ingly", "edly", "ies", "ing", "ed", "ly", "es", "s")


@dataclass
class Block:
    block_id: str
    kind: str
    start: int
    end: int
    text: str
    heading: str
    tokens: int
    table_id: str | None = None
    row_index: int | None = None
    neighbors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
            "tokens": self.tokens,
            "heading": self.heading,
            "table_id": self.table_id,
            "row_index": self.row_index,
            "neighbors": list(self.neighbors),
            "text": self.text,
        }


def stem_token(token: str) -> str:
    text = token.lower()
    if len(text) <= 4:
        return text
    for suffix in _STEM_SUFFIX:
        if text.endswith(suffix) and len(text) - len(suffix) >= 3:
            return text[: -len(suffix)]
    return text


def normalize_token(token: str) -> str:
    return stem_token(re.sub(r"[^a-z0-9]+", "", token.lower()))


def tokens_of(text: str) -> list[str]:
    return [normalize_token(part) for part in _TOKEN.findall(text.lower()) if normalize_token(part) and normalize_token(part) not in _STOP]


def retrieval_terms(name: str, record: Any) -> list[str]:
    terms = list(field_terms(name))
    literals = list(getattr(record, "predicate_literals", None) or [])
    literals.extend(getattr(record, "categorical_literals", None) or [])
    for cmp in getattr(record, "numeric_comparisons", None) or []:
        terms.append(str(cmp.get("operator") or ""))
        terms.extend(str(cmp.get("literals") or "").split("|"))
    for expr in getattr(record, "expressions", None) or []:
        terms.extend(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(expr)))
        terms.extend(re.findall(r"'([^']+)'", str(expr)))
        terms.extend(re.findall(r"%([^%]+)%", str(expr)))
    for role in getattr(record, "roles", None) or {}:
        terms.extend(field_terms(str(role)))
    out: list[str] = []
    for item in terms + literals:
        raw = str(item).strip()
        if not raw or raw.lower() in _STOP:
            continue
        out.append(raw.lower())
        out.extend(field_terms(raw))
        stemmed = normalize_token(raw)
        if stemmed:
            out.append(stemmed)
    return list(dict.fromkeys(part for part in out if part and part not in _STOP))


def parse_layout(doc_id: str, text: str) -> list[Block]:
    blocks: list[Block] = []
    lines: list[tuple[int, int, str]] = []
    cursor = 0
    for line in text.splitlines(keepends=True):
        lines.append((cursor, cursor + len(line), line))
        cursor += len(line)
    i = 0
    heading = "document"
    table_n = 0
    while i < len(lines):
        start, end, line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if _HEADING.match(stripped) and not _TABLE.search(stripped):
            heading = " ".join(stripped.lstrip("#").split())[:160]
            blocks.append(_block(doc_id, f"h{len(blocks)}", "section_heading", start, end, stripped, heading))
            i += 1
            continue
        if _TABLE.search(stripped) or "|" in stripped:
            table_n += 1
            table_id = f"{doc_id}:t{table_n}"
            run = [(start, end, stripped)]
            j = i + 1
            while j < len(lines):
                ns, ne, nl = lines[j]
                body = nl.strip()
                if not body:
                    if j + 1 < len(lines) and _TABLE.search(lines[j + 1][2]):
                        j += 1
                        continue
                    break
                if _TABLE.search(body) or "|" in body:
                    run.append((ns, ne, body))
                    j += 1
                    continue
                break
            title = ""
            title_start = run[0][0]
            if i > 0:
                prev = lines[i - 1][2].strip()
                if prev and not _TABLE.search(prev) and len(prev) <= 160:
                    title = prev
                    title_start = lines[i - 1][0]
            if title:
                blocks.append(_block(doc_id, f"{table_id}:title", "table_title", title_start, run[0][0], title, heading, table_id))
            header = run[0][2]
            nxt = run[1][2] if len(run) > 1 else ""
            header_digits = len(re.findall(r"\d[\d,]*", header))
            next_digits = len(re.findall(r"\d[\d,]*", nxt))
            header_is_header = (
                "|" in header
                or header_digits < next_digits
                or bool(re.search(r"(year|total|item|usd|december|million|thousand)", header, re.I))
            )
            row_start = 0
            if header_is_header:
                blocks.append(_block(doc_id, f"{table_id}:header", "table_header", run[0][0], run[0][1], header, heading, table_id, 0))
                row_start = 1
            row_ids: list[str] = []
            for offset, (rs, re_, body) in enumerate(run[row_start:]):
                bid = f"{table_id}:r{offset}"
                row_ids.append(bid)
                blocks.append(_block(doc_id, bid, "table_row", rs, re_, body, heading, table_id, offset, title=title, header=header if header_is_header else ""))
            for index, bid in enumerate(row_ids):
                neighbors = []
                if index:
                    neighbors.append(row_ids[index - 1])
                if index + 1 < len(row_ids):
                    neighbors.append(row_ids[index + 1])
                if title:
                    neighbors.append(f"{table_id}:title")
                if header_is_header:
                    neighbors.append(f"{table_id}:header")
                for item in blocks:
                    if item.block_id == bid:
                        item.neighbors = neighbors
            i = j
            continue
        if _LIST.match(stripped):
            run_s, run_e = start, end
            body = [stripped]
            j = i + 1
            while j < len(lines) and _LIST.match(lines[j][2]):
                run_e = lines[j][1]
                body.append(lines[j][2].strip())
                j += 1
            blocks.append(_block(doc_id, f"l{len(blocks)}", "list", run_s, run_e, "\n".join(body), heading))
            i = j
            continue
        run_s, run_e = start, end
        body = [stripped]
        j = i + 1
        while j < len(lines):
            ns, ne, nl = lines[j]
            piece = nl.strip()
            if not piece or _HEADING.match(piece) or _TABLE.search(piece) or _LIST.match(piece):
                break
            body.append(piece)
            run_e = ne
            j += 1
        blocks.append(_block(doc_id, f"p{len(blocks)}", "paragraph", run_s, run_e, " ".join(body), heading))
        i = j
    return blocks


def _block(
    doc_id: str,
    suffix: str,
    kind: str,
    start: int,
    end: int,
    text: str,
    heading: str,
    table_id: str | None = None,
    row_index: int | None = None,
    title: str = "",
    header: str = "",
) -> Block:
    packed = text
    if kind == "table_row":
        extras = [part for part in (title, header) if part]
        if extras:
            packed = "\n".join(extras + [text])
    return Block(
        block_id=f"{doc_id}:{suffix}",
        kind=kind,
        start=start,
        end=end,
        text=packed,
        heading=heading,
        tokens=max(1, count_tokens(packed)),
        table_id=table_id,
        row_index=row_index,
    )


def _bm25(blocks: list[Block], terms: list[str], avgdl: float, df: dict[str, int], n: int) -> list[tuple[float, Block]]:
    k1 = 1.5
    b = 0.75
    q = [normalize_token(term) if " " not in term else term.lower() for term in terms if term]
    scored: list[tuple[float, Block]] = []
    for block in blocks:
        blob = f"{block.heading}\n{block.text}".lower()
        tf = Counter(tokens_of(blob))
        score = 0.0
        for term in q:
            if " " in term or any(ch in term for ch in "%/_-"):
                if term in blob:
                    score += 2.5
                continue
            key = normalize_token(term)
            freq = tf.get(key, 0)
            if not freq:
                continue
            idf = math.log((n - df.get(key, 0) + 0.5) / (df.get(key, 0) + 0.5) + 1.0)
            denom = freq + k1 * (1 - b + b * block.tokens / max(avgdl, 1.0))
            score += idf * freq * (k1 + 1) / denom
        if re.search(r"\d", block.text):
            score += 0.15
        if block.kind.startswith("table"):
            score += 0.35
        if score > 0:
            scored.append((score, block))
    scored.sort(key=lambda item: (-item[0], item[1].start, item[1].block_id))
    return scored


def _stats(blocks: list[Block]) -> tuple[float, dict[str, int], int]:
    n = max(1, len(blocks))
    avgdl = sum(item.tokens for item in blocks) / n
    df: dict[str, int] = defaultdict(int)
    for block in blocks:
        for token in set(tokens_of(f"{block.heading}\n{block.text}")):
            df[token] += 1
    return avgdl, dict(df), n


def pack_c1(
    blocks: list[Block],
    terms_by_attr: dict[str, list[str]],
    budget: int,
) -> dict[str, Any]:
    if budget <= 0 or not blocks:
        return {"text": "", "blocks": [], "used_tokens": 0, "kinds": {}}
    avgdl, df, n = _stats(blocks)
    by_id = {item.block_id: item for item in blocks}
    chosen: list[Block] = []
    seen: set[str] = set()
    used = 0
    attrs = [name for name in terms_by_attr if terms_by_attr[name]]
    share = max(1, budget // max(1, len(attrs)))
    leftovers: list[tuple[float, Block]] = []

    def take(block: Block, limit: int) -> bool:
        nonlocal used
        if block.block_id in seen:
            return False
        extras = [by_id[nid] for nid in block.neighbors if nid in by_id]
        bundle = extras + [block] if block.kind == "table_row" else [block]
        cost = sum(item.tokens for item in bundle if item.block_id not in seen)
        if chosen and used + cost > limit:
            return False
        for item in bundle:
            if item.block_id in seen:
                continue
            if chosen and used + item.tokens > limit:
                continue
            seen.add(item.block_id)
            chosen.append(item)
            used += item.tokens
        return True

    for name in attrs:
        ranked = _bm25(blocks, terms_by_attr[name], avgdl, df, n)
        local = 0
        start_used = used
        for score, block in ranked:
            if used - start_used >= share:
                leftovers.append((score, block))
                continue
            if not take(block, min(budget, start_used + share)):
                leftovers.append((score, block))
        local = used - start_used
        del local
    leftovers.sort(key=lambda item: (-item[0], item[1].start, item[1].block_id))
    for _score, block in leftovers:
        if used >= budget:
            break
        take(block, budget)
    chosen.sort(key=lambda item: (item.start, item.block_id))
    text = "\n\n".join(item.text for item in chosen)
    kinds = Counter(item.kind for item in chosen)
    return {
        "text": text,
        "blocks": [item.as_dict() for item in chosen],
        "used_tokens": count_tokens(text) if text else 0,
        "kinds": dict(kinds),
    }


def overlap_report(left: str, right: str) -> dict[str, Any]:
    a = Counter(tokens_of(left))
    b = Counter(tokens_of(right))
    shared = sum((a & b).values())
    union = sum((a | b).values()) or 1
    return {
        "shared_tokens": shared,
        "jaccard": shared / union,
        "left_tokens": sum(a.values()),
        "right_tokens": sum(b.values()),
    }


def head_tail_midcut(text: str, keep_tokens: int) -> str:
    from quwarts.core.full_window_additive.truncate import mid_cut
    from quwarts.core.retrieve_extract.tokens import count_tokens as ntok

    have = ntok(text)
    if have <= keep_tokens:
        return text
    return mid_cut(text, have - keep_tokens + 8)


def dedupe_overlap(first: str, second: str) -> str:
    if not first:
        return second
    if not second:
        return first
    if second in first:
        return first
    if first in second:
        return second
    return first.rstrip() + "\n\n" + second
