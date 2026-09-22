"""Budgeted extraction calls and verified-cache lookups."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from quwarts.core.ledger import BudgetExhausted, BudgetedCaller, TokenLedger
from quwarts.core.retrieve_extract.cache import VerifiedCache
from quwarts.core.retrieve_extract.config import (
    EXTRACT_INSTRUCTIONS,
    EXTRACT_SYSTEM,
    FROZEN,
    MODEL,
    OPERATOR,
    TIER,
    config_hash,
    prompt_hash,
)
from quwarts.core.retrieve_extract.parse import parse_extraction
from quwarts.core.retrieve_extract.tokens import count_tokens


@dataclass
class ExtractCall:
    raw: str
    parsed: dict[str, Any]
    prompt: str
    estimated_cost: int
    actual_tokens: int
    from_cache: bool
    purpose: str
    system: str


def schema_block(attributes: list[str], descriptions: dict[str, str], dtypes: dict[str, str]) -> str:
    lines = []
    for name in attributes:
        lines.append(f"- {name} ({dtypes.get(name, 'string')}): {descriptions.get(name, '')}")
    return "\n".join(lines)


def extract_prompt(
    entity_id: str,
    attributes: list[str],
    descriptions: dict[str, str],
    dtypes: dict[str, str],
    context: str,
    source_ids: list[str],
) -> str:
    return (
        f"{EXTRACT_INSTRUCTIONS}\n"
        f"entity_id: {entity_id}\n"
        f"requested_attributes: {attributes}\n"
        f"source_ids: {source_ids}\n"
        f"{schema_block(attributes, descriptions, dtypes)}\n\n"
        f"SOURCE:\n{context}\n"
    )


def estimate_cost(prompt: str) -> int:
    return count_tokens(prompt) + int(FROZEN["reserved_completion_tokens"])


def can_afford(ledger: TokenLedger, cost: int) -> bool:
    return cost > 0 and cost + 8 <= ledger.remaining()


def manifest_for(
    *,
    corpus_id: str,
    source_document_hash: str,
    entity_identity: str,
    attributes: list[str],
    mode: str,
    context_hashes: list[str],
    schema_hash: str,
    operator: str | None = None,
    configuration_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "corpus_id": corpus_id,
        "source_document_hash": source_document_hash,
        "entity_identity": entity_identity,
        "attribute_bundle": list(attributes),
        "context_mode": mode,
        "context_hashes": list(context_hashes),
        "schema_hash": schema_hash,
        "prompt_hash": prompt_hash(),
        "model_id": MODEL,
        "configuration_hash": configuration_hash or config_hash(),
        "operator": operator or OPERATOR,
        "tier": TIER,
    }


def complete(
    caller: BudgetedCaller,
    prompt: str,
    purpose: str,
    system: str,
) -> tuple[str, int]:
    before = caller.ledger.spent
    text = caller.complete(
        prompt,
        purpose,
        system=system,
        model=MODEL,
    )
    return text, caller.ledger.spent - before


def run_extract(
    caller: BudgetedCaller,
    cache: VerifiedCache,
    *,
    corpus_id: str,
    source_document_hash: str,
    entity_identity: str,
    attributes: list[str],
    mode: str,
    context: str,
    source_ids: list[str],
    context_hashes: list[str],
    schema_hash: str,
    descriptions: dict[str, str],
    dtypes: dict[str, str],
    purpose: str = "extract",
    system: str = EXTRACT_SYSTEM,
    operator: str | None = None,
    configuration_hash: str | None = None,
) -> ExtractCall | None:
    prompt = extract_prompt(entity_identity, attributes, descriptions, dtypes, context, source_ids)
    cost = estimate_cost(prompt)
    if not can_afford(caller.ledger, cost):
        return None
    manifest = manifest_for(
        corpus_id=corpus_id,
        source_document_hash=source_document_hash,
        entity_identity=entity_identity,
        attributes=attributes,
        mode=mode,
        context_hashes=context_hashes,
        schema_hash=schema_hash,
        operator=operator,
        configuration_hash=configuration_hash,
    )
    cached = cache.get(manifest)
    if cached is not None:
        raw = str((cached.get("record") or {}).get("raw") or "")
        parsed = (cached.get("record") or {}).get("parsed") or parse_extraction(
            raw, attributes, context, source_ids, dtypes
        )
        return ExtractCall(raw, parsed, prompt, cost, 0, True, purpose, system)
    try:
        raw, used = complete(caller, prompt, purpose, system)
    except BudgetExhausted:
        return None
    parsed = parse_extraction(raw, attributes, context, source_ids, dtypes)
    cache.put(manifest, {"raw": raw, "parsed": parsed})
    return ExtractCall(raw, parsed, prompt, cost, used, False, purpose, system)


def context_digest(parts: list[str]) -> str:
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()
