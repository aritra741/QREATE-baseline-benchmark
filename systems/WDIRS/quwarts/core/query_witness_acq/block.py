"""Deterministic witness blocking. Never sends a Cartesian universe to the model."""

from __future__ import annotations

import re
from typing import Any

from quwarts.core.query_witness_acq.programs import WitnessProgram
from quwarts.core.retrieve_extract.index import DocumentIndex
from quwarts.core.retrieve_extract.retrieve import Hit, adjacent_chunks, pack_chunks, retrieve, section_map_from_hits
from quwarts.core.retrieve_extract.route import decide_coverage_route, measure, prompt_and_schema_tokens
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.retrieve_extract.config import FROZEN
from quwarts.core.retrieve_extract.retrieve import RetrievalSpec, concentration
from quwarts.core.retrieve_extract.typed_candidates import ident_tokens

_TOKEN = re.compile(r"[a-z0-9][a-z0-9]{2,}")


def _terms(program: WitnessProgram) -> list[str]:
    terms = []
    for col in program.columns:
        terms.extend(ident_tokens(col))
        terms.append(col.replace("_", " "))
    terms.extend(str(lit).lower() for lit in program.literals if lit)
    return list(dict.fromkeys(item for item in terms if item))


def spec_for(program: WitnessProgram) -> RetrievalSpec:
    return RetrievalSpec(
        attribute=program.condition_id,
        terms=_terms(program),
        literals=[str(lit) for lit in program.literals if lit],
        numeric=any(token in program.agg_sql for token in ("sum(", "avg(", "max(", "min(")),
        description=program.condition_sql,
    )


def block_witness(
    program: WitnessProgram,
    index: DocumentIndex,
    *,
    incumbent: bool,
    plumbing_values: dict[str, Any],
) -> dict[str, Any]:
    if incumbent:
        return {"include": False, "reason": "incumbent_support", "hits": [], "score": 0.0}
    terms = _terms(program)
    blob = index.text.lower()
    heading_blob = " ".join(str(section.get("heading") or "").lower() for section in index.sections[:80])
    header_blob = " ".join(chunk.header_text.lower() for chunk in index.chunks if chunk.header_text)
    exact = [lit for lit in program.literals if lit and lit.lower() in blob]
    term_hits = [term for term in terms if term in blob]
    heading_hits = [term for term in terms if term in heading_blob]
    header_hits = [term for term in terms if term in header_blob]
    grounded = [
        name
        for name in program.columns
        if plumbing_values.get(name) not in (None, "")
    ]
    spec = spec_for(program)
    hits = retrieve(index, spec)
    score = float(len(exact) * 3 + len(heading_hits) + len(header_hits) + min(len(term_hits), 4) + (2 if grounded else 0))
    if hits:
        score += min(hits[0].score, 4.0)
    include = bool(exact or heading_hits or header_hits or grounded or (hits and hits[0].score >= 1.5))
    reason = "blocked_in"
    if not include:
        reason = "no_literal_heading_header_or_grounded_overlap"
    elif exact:
        reason = "query_literal"
    elif header_hits:
        reason = "table_header"
    elif heading_hits:
        reason = "section_heading"
    elif grounded:
        reason = "existing_grounded_evidence"
    return {
        "include": include,
        "reason": reason,
        "hits": hits,
        "score": score,
        "exact_literals": exact[:12],
        "term_overlap": term_hits[:12],
        "heading_overlap": heading_hits[:8],
        "header_overlap": header_hits[:8],
        "grounded_columns": grounded,
    }


def pack_context(index: DocumentIndex, hits: list[Hit], descriptions: dict[str, str]) -> dict[str, Any]:
    prompt = prompt_and_schema_tokens(["condition"], descriptions)
    extra = adjacent_chunks(index, hits)
    packed, _, _ = pack_chunks(hits, extra=extra)
    packed_tokens = count_tokens(packed) if packed else int(FROZEN["retrieve_context_cap"])
    meas = measure(index.document_tokens, prompt, packed_tokens)
    mode, reason = decide_coverage_route(meas, concentration(hits))
    cap = min(
        int(FROZEN["retrieve_context_cap"]),
        max(256, int(FROZEN["effective_input_limit"]) - prompt),
    )
    if mode == "whole_document":
        context, source_ids, hashes = index.text, [index.doc_id], [index.digest]
    elif mode == "section_map":
        context, source_ids, hashes = section_map_from_hits(index, hits, cap=cap)
    else:
        context, source_ids, hashes = pack_chunks(hits, cap=cap, extra=extra)
    return {
        "mode": mode,
        "reason": reason,
        "context": context,
        "source_ids": source_ids,
        "context_hashes": hashes,
        "measurements": meas.__dict__,
        "router_tokens": 0,
        "estimated_cost": meas.estimated_call_cost if mode == "whole_document" else packed_tokens + prompt + int(FROZEN["reserved_completion_tokens"]),
    }
