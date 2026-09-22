"""Choose whole-document vs retrieved evidence from length and density only."""

from __future__ import annotations

from typing import Any

from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.shared_bundle.context_blocks import pack_c1

EFFECTIVE_INPUT_LIMIT = 11_000
COMPLETION_SPACE = 192
WRAPPER_RESERVE = 700
RETRIEVED_PACK = 4_000


def context_for_proposal(
    source: str,
    layouts: list[Any],
    terms_by_attr: dict[str, list[str]],
    existing: list[dict[str, Any]],
) -> dict[str, Any]:
    doc_tokens = count_tokens(source)
    whole_budget = EFFECTIVE_INPUT_LIMIT - COMPLETION_SPACE - WRAPPER_RESERVE
    density = sum(1 for item in existing if item.get("score", 0) > 0)
    if doc_tokens <= whole_budget:
        return {
            "mode": "whole_document",
            "text": source,
            "document_tokens": doc_tokens,
            "context_tokens": doc_tokens,
            "reason": "document_fits_effective_input",
            "evidence_density": density,
        }
    budget = RETRIEVED_PACK
    if density <= 1:
        budget = min(whole_budget, RETRIEVED_PACK + 2_000)
    packed = pack_c1(layouts, terms_by_attr, budget)
    text = str(packed.get("text") or "")
    return {
        "mode": "retrieved_pack",
        "text": text,
        "document_tokens": doc_tokens,
        "context_tokens": int(packed.get("used_tokens") or count_tokens(text)),
        "reason": "document_exceeds_effective_input",
        "evidence_density": density,
        "pack_kinds": packed.get("kinds") or {},
    }
