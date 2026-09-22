"""Deterministic query-aware context router. No router-model calls."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from quwarts.core.docetl_unit_parity.config import POLICY
from quwarts.core.docetl_unit_parity.prompt import build_map_prompt
from quwarts.core.docetl_unit_parity.schema import QuerySchema
from quwarts.core.retrieve_extract.index import DocumentIndex
from quwarts.core.retrieve_extract.retrieve import (
    Hit,
    RetrievalSpec,
    adjacent_chunks,
    pack_chunks,
    retrieve,
)
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.experiments.extract_util import field_terms


@dataclass
class RoutedContext:
    mode: str
    context: str
    source_ids: list[str]
    context_hashes: list[str]
    context_tokens: int
    request_tokens: int
    reason: str


def _header(index: DocumentIndex) -> str:
    reserve = int(POLICY["header_reserve_chars"])
    title = (index.sections[0]["heading"] if index.sections else index.doc_id)
    head = index.text[:reserve].strip()
    headings = [str(section["heading"]) for section in index.sections[:6] if section.get("heading")]
    return f"TITLE: {title}\nHEADINGS: {' | '.join(headings)}\nHEADER:\n{head}"


def _specs(schema: QuerySchema) -> list[RetrievalSpec]:
    specs = []
    for item in schema.fields:
        terms = [term.lower() for term in field_terms(item.name) + field_terms(item.description)]
        terms.extend(str(lit).lower() for lit in item.literals)
        specs.append(
            RetrievalSpec(
                attribute=item.name,
                terms=list(dict.fromkeys(term for term in terms if term)),
                literals=list(item.literals),
                numeric=item.dtype == "numeric",
                description=item.description,
            )
        )
    return specs


def _joint_hits(index: DocumentIndex, schema: QuerySchema, idf: dict[str, float] | None) -> list[Hit]:
    combined: dict[str, Hit] = {}
    for spec in _specs(schema):
        for hit in retrieve(index, spec, idf=idf, k=int(POLICY["retrieve_top_k"])):
            prior = combined.get(hit.chunk.source_id)
            if prior is None or hit.score > prior.score:
                combined[hit.chunk.source_id] = hit
    return sorted(combined.values(), key=lambda item: (-item.score, item.chunk.start))


def _pack(index: DocumentIndex, schema: QuerySchema, idf: dict[str, float] | None) -> tuple[str, list[str], list[str]]:
    hits = _joint_hits(index, schema, idf)
    extra = adjacent_chunks(index, hits)
    packed, source_ids, digests = pack_chunks(hits, cap=int(POLICY["retrieve_context_cap"]), extra=extra)
    header = _header(index)
    context = f"{header}\n\n{packed}" if packed else header
    hashes = [hashlib.sha256(header.encode()).hexdigest(), *digests]
    return context, source_ids, hashes


def route(
    schema: QuerySchema,
    index: DocumentIndex,
    idf: dict[str, float] | None = None,
) -> RoutedContext:
    header = _header(index)
    whole = f"{header}\n\nDOCUMENT:\n{index.text}"
    whole_prompt = build_map_prompt(schema, whole)
    whole_request = count_tokens(whole_prompt) + 24
    reserved = int(POLICY["reserved_completion_tokens"])
    margin = int(POLICY["safety_margin"])
    hard = whole_request + reserved + margin <= int(POLICY["model_context_limit"])
    effective = whole_request <= int(POLICY["effective_input_limit"])
    if hard and effective:
        return RoutedContext(
            mode="whole_document",
            context=whole,
            source_ids=[index.doc_id],
            context_hashes=[index.digest],
            context_tokens=index.document_tokens,
            request_tokens=whole_request,
            reason="hard_and_effective_fit",
        )
    packed, source_ids, hashes = _pack(index, schema, idf)
    prompt = build_map_prompt(schema, packed)
    return RoutedContext(
        mode="retrieved_context",
        context=packed,
        source_ids=source_ids,
        context_hashes=hashes,
        context_tokens=count_tokens(packed),
        request_tokens=count_tokens(prompt) + 24,
        reason="exceeds_hard_or_effective_threshold",
    )
