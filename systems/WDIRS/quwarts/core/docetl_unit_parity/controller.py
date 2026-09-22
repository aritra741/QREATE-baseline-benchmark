"""Sequential complete-query map execution with format-repair and caching."""

from __future__ import annotations

import hashlib
from typing import Any

from quwarts.core.docetl_unit_parity.config import (
    MAP_SYSTEM,
    MODEL,
    OPERATOR,
    POLICY,
    REPAIR_SYSTEM,
    TIER,
    prompt_hash,
    router_hash,
)
from quwarts.core.docetl_unit_parity.parse import merge_partial, parse_map
from quwarts.core.docetl_unit_parity.prompt import build_map_prompt, build_repair_prompt
from quwarts.core.docetl_unit_parity.router import RoutedContext
from quwarts.core.docetl_unit_parity.schema import QuerySchema
from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.retrieve_extract.cache import VerifiedCache
from quwarts.core.retrieve_extract.tokens import count_tokens


def estimate_map_cost(request_tokens: int) -> int:
    return (
        int(request_tokens)
        + int(POLICY["expected_completion_tokens"])
        + int(round(float(POLICY["expected_repair_p"]) * float(POLICY["expected_repair_tokens"])))
    )


def estimate_program_cost(tasks: list[dict[str, Any]]) -> int:
    return sum(int(task["expected_cost"]) for task in tasks)


def _manifest(
    *,
    query_id: str,
    doc_id: str,
    schema: QuerySchema,
    routed: RoutedContext,
    purpose: str,
) -> dict[str, Any]:
    return {
        "corpus_id": "Finan",
        "source_document_hash": routed.context_hashes[0] if routed.context_hashes else query_id,
        "entity_identity": f"{query_id}:{doc_id}:{purpose}",
        "attribute_bundle": list(schema.names),
        "context_mode": routed.mode,
        "context_hashes": list(routed.context_hashes),
        "schema_hash": hashlib.sha256("|".join(schema.names).encode()).hexdigest(),
        "prompt_hash": prompt_hash(),
        "model_id": MODEL,
        "configuration_hash": router_hash(),
        "operator": OPERATOR,
        "tier": TIER,
    }


def run_map(
    caller: BudgetedCaller,
    cache: VerifiedCache,
    *,
    schema: QuerySchema,
    doc_id: str,
    routed: RoutedContext,
    remaining_cap: int,
) -> dict[str, Any] | None:
    prompt = build_map_prompt(schema, routed.context)
    expected = estimate_map_cost(routed.request_tokens)
    if caller.ledger.spent + expected > remaining_cap and caller.ledger.spent + 64 > remaining_cap:
        return None
    manifest = _manifest(query_id=schema.query_id, doc_id=doc_id, schema=schema, routed=routed, purpose="map")
    cached = cache.get(manifest)
    from_cache = False
    repaired = False
    malformed = False
    tokens = 0
    raw = ""
    if cached is not None:
        raw = str((cached.get("record") or {}).get("raw") or "")
        parsed = (cached.get("record") or {}).get("parsed") or parse_map(raw, schema, routed.context)
        from_cache = True
    else:
        try:
            before = caller.ledger.spent
            raw = caller.complete(
                prompt,
                "map_extract",
                system=MAP_SYSTEM,
                model=MODEL,
                query_id=schema.query_id,
                doc_id=doc_id,
            )
            tokens += caller.ledger.spent - before
        except BudgetExhausted:
            return None
        parsed = parse_map(raw, schema, routed.context)
        if parsed["malformed"]:
            malformed = True
            repair_prompt = build_repair_prompt(schema, raw)
            repair_cost = count_tokens(repair_prompt) + int(POLICY["expected_repair_tokens"])
            if caller.ledger.spent + repair_cost <= remaining_cap:
                try:
                    before = caller.ledger.spent
                    repaired_raw = caller.complete(
                        repair_prompt,
                        "format_repair",
                        system=REPAIR_SYSTEM,
                        model=MODEL,
                        query_id=schema.query_id,
                        doc_id=doc_id,
                    )
                    tokens += caller.ledger.spent - before
                    repaired = True
                    repaired_parsed = parse_map(repaired_raw, schema, routed.context)
                    parsed = merge_partial(parsed, repaired_parsed, schema)
                    raw = repaired_raw
                except BudgetExhausted:
                    pass
        cache.put(manifest, {"raw": raw, "parsed": parsed})
    values = {
        name: item.get("normalized_value")
        for name, item in (parsed.get("items") or {}).items()
    }
    return {
        "query_id": schema.query_id,
        "doc_id": doc_id,
        "mode": routed.mode,
        "from_cache": from_cache,
        "repaired": repaired,
        "malformed": malformed or bool(parsed.get("malformed")),
        "tokens": tokens,
        "request_tokens": routed.request_tokens,
        "context_tokens": routed.context_tokens,
        "raw": raw,
        "parsed": parsed,
        "values": values,
        "prompt_tokens_est": count_tokens(prompt),
    }
