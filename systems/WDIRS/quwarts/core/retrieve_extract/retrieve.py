"""Attribute retrieval specifications and lexical passage ranking."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from quwarts.core.models import Workload
from quwarts.core.retrieve_extract.config import FROZEN
from quwarts.core.retrieve_extract.index import Chunk, DocumentIndex
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.experiments.extract_util import field_terms

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_/-]{1,}")
_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "into", "your",
    "are", "was", "were", "been", "have", "has", "not", "use", "used",
}


@dataclass
class RetrievalSpec:
    attribute: str
    terms: list[str]
    literals: list[str]
    numeric: bool
    description: str = ""


@dataclass
class Hit:
    chunk: Chunk
    score: float


def _variants(text: str) -> list[str]:
    parts = field_terms(text)
    extra: list[str] = []
    for part in list(parts):
        extra.append(part.replace("_", " "))
        extra.append(part.replace("_", "-"))
        if part.endswith("s") and len(part) > 4:
            extra.append(part[:-1])
        if part.endswith("num"):
            extra.append("number")
            extra.append("count")
    return list(dict.fromkeys(item for item in parts + extra if item and item not in _STOP))


def build_specs(
    attributes: Iterable[str],
    workload: Workload,
    catalog: dict[str, dict[str, Any]] | None = None,
    expansions: dict[str, list[str]] | None = None,
) -> dict[str, RetrievalSpec]:
    catalog = catalog or {}
    expansions = expansions or {}
    specs: dict[str, RetrievalSpec] = {}
    for name in attributes:
        bare = name.split(".")[-1]
        req = workload.requirements.get(name)
        info = catalog.get(bare.lower()) or catalog.get(bare) or {}
        description = str(info.get("description") or "")
        terms = _variants(bare) + _variants(description)
        literals: list[str] = []
        for values in workload.in_lists.get(name, []) + workload.in_lists.get(bare, []):
            literals.extend(str(item) for item in values if item not in (None, ""))
        literals.extend(workload.like_tokens.get(name, []) or workload.like_tokens.get(bare, []) or [])
        for alias in (workload.literal_aliases or {}):
            if bare.lower() in alias.lower() or name.lower() in alias.lower():
                literals.append(str(alias))
        if req and req.declared_domain:
            literals.extend(str(item) for item in req.declared_domain)
        terms.extend(_variants(" ".join(literals[:12])))
        terms.extend(expansions.get(name, []))
        numeric = bool(req and req.dtype == "numeric") or str(info.get("value_type") or "").lower() in {
            "int",
            "float",
            "number",
        }
        if req:
            roles = {item.value if hasattr(item, "value") else str(item) for item in (req.roles or set())}
            if any(token in roles for token in ("agg_additive", "agg_extremal", "predicate")):
                numeric = numeric or req.dtype == "numeric"
        specs[name] = RetrievalSpec(
            attribute=name,
            terms=list(dict.fromkeys(term.lower() for term in terms if term)),
            literals=list(dict.fromkeys(str(item) for item in literals if item)),
            numeric=numeric,
            description=description,
        )
    return specs


def _idf(indexes: list[DocumentIndex]) -> dict[str, float]:
    df: Counter[str] = Counter()
    n_docs = max(1, len(indexes))
    for index in indexes:
        seen: set[str] = set()
        for chunk in index.chunks[:400]:
            seen.update(_TOKEN.findall(chunk.text.lower()))
        df.update(seen)
    return {term: math.log((n_docs + 1) / (1 + count)) + 1.0 for term, count in df.items()}


def retrieve(
    index: DocumentIndex,
    spec: RetrievalSpec,
    *,
    idf: dict[str, float] | None = None,
    exclude: set[str] | None = None,
    k: int | None = None,
) -> list[Hit]:
    top_k = int(k or FROZEN["retrieve_top_k"])
    exclude = exclude or set()
    weights = idf or {}
    hits: list[Hit] = []
    terms = [term for term in spec.terms if term]
    for chunk in index.chunks:
        if chunk.source_id in exclude:
            continue
        blob = f"{chunk.heading}\n{chunk.packed_text()}".lower()
        score = 0.0
        for term in terms:
            count = blob.count(term)
            if count:
                score += (1.0 + math.log(count + 1.0)) * weights.get(term, 1.0)
        for literal in spec.literals:
            if literal and literal.lower() in blob:
                score += 2.5
        if spec.numeric and re.search(r"\d", chunk.text):
            score += 0.15
        if chunk.is_table and spec.numeric:
            score += 0.35
        if score > 0:
            hits.append(Hit(chunk=chunk, score=score))
    hits.sort(key=lambda item: (-item.score, item.chunk.start))
    return hits[:top_k]


def concentration(hits: list[Hit]) -> dict[str, Any]:
    if not hits:
        return {
            "n_hits": 0,
            "unique_sections": 0,
            "top2_share": 0.0,
            "diffuse": True,
            "max_score": 0.0,
        }
    total = sum(max(hit.score, 0.0) for hit in hits) or 1.0
    by_section: dict[str, float] = defaultdict(float)
    for hit in hits:
        by_section[hit.chunk.heading or hit.chunk.source_id] += hit.score
    ranked = sorted(by_section.values(), reverse=True)
    top2 = sum(ranked[:2]) / total
    unique = len(by_section)
    return {
        "n_hits": len(hits),
        "unique_sections": unique,
        "top2_share": top2,
        "diffuse": unique >= int(FROZEN["diffuse_unique_sections"]) and top2 < float(FROZEN["diffuse_top2_share"]),
        "max_score": hits[0].score,
    }


def adjacent_chunks(index: DocumentIndex, hits: list[Hit]) -> list[Chunk]:
    by_id = index.chunk_map()
    extra: list[Chunk] = []
    for hit in hits:
        for neighbor in (hit.chunk.adjacent_prev, hit.chunk.adjacent_next):
            chunk = by_id.get(neighbor or "")
            if chunk is not None:
                extra.append(chunk)
    return extra


def section_map_from_hits(index: DocumentIndex, hits: list[Hit], *, cap: int | None = None) -> tuple[str, list[str], list[str]]:
    scores: dict[str, float] = {}
    for hit in hits:
        for section in index.sections:
            start, end = int(section["start"]), int(section["end"])
            if start <= hit.chunk.start < end:
                sid = str(section["section_id"])
                scores[sid] = scores.get(sid, 0.0) + float(hit.score)
    if not scores:
        scores = {str(section["section_id"]): 1.0 for section in index.sections[:3]}
    ordered = [sid for sid, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
    by_id = {str(section["section_id"]): pos for pos, section in enumerate(index.sections)}
    expanded: list[str] = []
    for sid in ordered:
        pos = by_id.get(sid)
        if pos is None:
            continue
        for neighbor in (pos - 1, pos, pos + 1):
            if 0 <= neighbor < len(index.sections):
                expanded.append(str(index.sections[neighbor]["section_id"]))
    return sections_for(index, list(dict.fromkeys(expanded)), cap=cap)


def pack_chunks(hits: list[Hit], *, cap: int | None = None, extra: list[Chunk] | None = None) -> tuple[str, list[str], list[str]]:
    limit = int(cap or FROZEN["retrieve_context_cap"])
    ordered: list[Chunk] = []
    seen: set[str] = set()
    for item in list(extra or []) + [hit.chunk for hit in hits]:
        if item.source_id in seen:
            continue
        seen.add(item.source_id)
        ordered.append(item)
    parts: list[str] = []
    source_ids: list[str] = []
    digests: list[str] = []
    used = 0
    for chunk in ordered:
        block = f"[{chunk.source_id} page={chunk.page} {chunk.heading}]\n{chunk.packed_text()}"
        tokens = count_tokens(block)
        if parts and used + tokens > limit:
            break
        if not parts and tokens > limit:
            block = block[: max(200, limit * 4)]
            tokens = count_tokens(block)
        parts.append(block)
        source_ids.append(chunk.source_id)
        digests.append(chunk.digest)
        used += tokens
    return "\n\n".join(parts), source_ids, digests


def outline(index: DocumentIndex, *, cap: int | None = None) -> str:
    limit = int(cap or FROZEN["section_outline_cap"])
    lines = []
    used = 0
    for section in index.sections[:80]:
        start = int(section["start"])
        snippet = " ".join(index.text[start : start + 160].split())
        line = f"{section['section_id']} | {section['heading']} | {snippet}"
        tokens = count_tokens(line)
        if used + tokens > limit and lines:
            break
        lines.append(line)
        used += tokens
    return "\n".join(lines)


def sections_for(index: DocumentIndex, section_ids: list[str], *, cap: int | None = None) -> tuple[str, list[str], list[str]]:
    limit = int(cap or FROZEN["retrieve_context_cap"])
    wanted = set(section_ids)
    parts: list[str] = []
    ids: list[str] = []
    digests: list[str] = []
    used = 0
    for section in index.sections:
        if wanted and section["section_id"] not in wanted:
            continue
        body = index.text[int(section["start"]) : int(section["end"])]
        block = f"[{section['section_id']} {section['heading']}]\n{body}"
        tokens = count_tokens(block)
        if parts and used + tokens > limit:
            break
        if not parts and tokens > limit:
            block = block[: max(200, limit * 4)]
            tokens = count_tokens(block)
        parts.append(block)
        ids.append(section["section_id"])
        digests.append(hashlib_sha(body))
        used += tokens
    return "\n\n".join(parts), ids, digests


def hashlib_sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()
