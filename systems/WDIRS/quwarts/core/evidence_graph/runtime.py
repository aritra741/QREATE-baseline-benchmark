"""Four-call evidence-graph runtime. Call 4 is conditional."""

from __future__ import annotations

import json
import time
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from quwarts.core.evidence_graph.config import (
    CALL1_PROMPT,
    CALL2_PROMPT,
    CALL3_PROMPT,
    CALL4_PROMPT,
    EXTRACT_MAX_TOKENS,
    MODEL,
    RESOLVE_MAX_TOKENS,
    SYSTEM,
    TEMPERATURE,
    VERIFY_MAX_TOKENS,
    load_observables,
)
from quwarts.core.evidence_graph.evaluate import evaluate_observables, reuse_stats
from quwarts.core.evidence_graph.graph import (
    compact_facts,
    facts_from_payload,
    observable_conflicts,
    salvage_json,
)
from quwarts.core.ledger import BudgetExhausted, TokenLedger
from quwarts.core.retrieve_extract.tokens import count_tokens

OPENROUTER_URL = "https://openrouter.ai/api/v1"


def make_client(api_key: str) -> OpenAI:
    return OpenAI(base_url=OPENROUTER_URL, api_key=api_key, timeout=90.0)


def complete(
    client: OpenAI,
    ledger: TokenLedger,
    prompt: str,
    purpose: str,
    max_tokens: int,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    delay = 5.0
    response = None
    for attempt in range(8):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                temperature=TEMPERATURE,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            break
        except (RateLimitError, APIStatusError, APITimeoutError, APIConnectionError) as exc:
            status = getattr(exc, "status_code", None)
            retryable = isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)) or status in {400, 429, 502, 503}
            if not retryable or attempt == 7:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 120)
    assert response is not None
    text = (response.choices[0].message.content or "").strip()
    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
    total = prompt_tokens + completion_tokens
    if total <= 0:
        prompt_tokens = count_tokens(SYSTEM + prompt)
        completion_tokens = count_tokens(text)
        total = max(1, prompt_tokens + completion_tokens)
    if ledger.spent + total > ledger.theta:
        raise BudgetExhausted(purpose)
    ledger.spend(
        total,
        purpose,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        **metadata,
    )
    return {
        "text": text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total,
        "parsed": salvage_json(text),
        "parse_ok": salvage_json(text) is not None,
    }


def _windows_from_route(route: dict[str, Any], call: str) -> list[tuple[int, int]]:
    rows = (route.get(call) or {}).get("selected_sections") or []
    return [(int(row["start"]), int(row["end"])) for row in rows if "start" in row and "end" in row]


def build_extract_prompt(instruction: str, descriptions: dict[str, Any], attributes: tuple[str, ...], body: str, mode: str) -> str:
    desc = "\n".join(f"- {name}: {descriptions.get(name, '')}" for name in attributes)
    return (
        f"{instruction}\n\n"
        f"Routing: {mode}. Offsets are 0-based into the original source document.\n"
        f"If a section header includes source_start/source_end, cite those original offsets.\n"
        f"Attribute definitions:\n{desc}\n\n"
        f"SOURCE:\n{body}"
    )


def build_resolve_prompt(facts: list[dict[str, Any]], observables: list[dict[str, Any]]) -> str:
    brief = [
        {
            "observable_id": item["observable_id"],
            "attribute": item["attribute"],
            "kind": item["kind"],
            "role": item["role"],
            "expression": item["expression"],
        }
        for item in observables
    ]
    return (
        f"{CALL3_PROMPT}\n\n"
        f"Workload observables:\n{json.dumps(brief, ensure_ascii=True)}\n\n"
        f"Compact facts:\n{json.dumps(compact_facts(facts), ensure_ascii=True)}"
    )


def build_verify_prompt(
    conflicts: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    document: str,
    observables: list[dict[str, Any]],
) -> str:
    by_id = {fact["fact_id"]: fact for fact in facts}
    nodes = []
    for conflict in conflicts:
        for fact_id in conflict.get("fact_ids") or []:
            fact = by_id.get(fact_id)
            if not fact:
                continue
            start = int(fact.get("source_start") or 0)
            end = int(fact.get("source_end") or 0)
            lo = max(0, start - 160)
            hi = min(len(document), end + 160)
            nodes.append({"conflict": conflict, "node": compact_facts([fact])[0], "window": document[lo:hi]})
    affected = [item for item in observables if item["observable_id"] in {oid for row in conflicts for oid in row.get("observable_ids") or []}]
    if not affected:
        affected = [item for item in observables if item["attribute"] in {row.get("attribute") for row in conflicts}]
    return (
        f"{CALL4_PROMPT}\n\n"
        f"Affected observables:\n{json.dumps(affected, ensure_ascii=True)}\n\n"
        f"Conflicts and local windows:\n{json.dumps(nodes, ensure_ascii=True)}"
    )


def run_document(
    client: OpenAI,
    ledger: TokenLedger,
    entity: dict[str, Any],
    document: str,
    route: dict[str, Any],
    descriptions: dict[str, str],
) -> dict[str, Any]:
    observables = load_observables()
    calls: list[dict[str, Any]] = []
    prompt_tokens = completion_tokens = retry_tokens = verify_tokens = 0

    def record(name: str, prompt: str, max_tokens: int) -> dict[str, Any]:
        nonlocal prompt_tokens, completion_tokens, retry_tokens, verify_tokens
        got = complete(client, ledger, prompt, f"{entity['stem']}_{name}", max_tokens, {"doc_id": entity["doc_id"], "call": name})
        calls.append({"call": name, **{k: got[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens", "parse_ok")}})
        prompt_tokens += got["prompt_tokens"]
        completion_tokens += got["completion_tokens"]
        if name == "call4":
            verify_tokens += got["total_tokens"]
        return got

    call1 = record(
        "call1",
        build_extract_prompt(CALL1_PROMPT, descriptions, ("case_number", "hearing_year", "legal_basis_num", "first_judge"), route["call1_text"], route["mode"]),
        EXTRACT_MAX_TOKENS,
    )
    call2 = record(
        "call2",
        build_extract_prompt(CALL2_PROMPT, descriptions, ("case_type", "plaintiff_current_status", "defendant_current_status", "verdict"), route["call2_text"], route["mode"]),
        EXTRACT_MAX_TOKENS,
    )
    facts = facts_from_payload(call1.get("parsed"), "c1", document, _windows_from_route(route, "call1"))
    facts.extend(facts_from_payload(call2.get("parsed"), "c2", document, _windows_from_route(route, "call2")))
    call3 = record("call3", build_resolve_prompt(facts, observables), RESOLVE_MAX_TOKENS)
    resolved = facts_from_payload(call3.get("parsed"), "r", document, None) or facts
    if resolved:
        facts = resolved
    reported = []
    parsed3 = call3.get("parsed") or {}
    if isinstance(parsed3.get("workload_conflicts"), list):
        reported = [row for row in parsed3["workload_conflicts"] if isinstance(row, dict)]
    detected = observable_conflicts(facts, observables)
    conflicts = reported or detected
    used_call4 = bool(conflicts)
    if used_call4:
        call4 = record("call4", build_verify_prompt(conflicts, facts, document, observables), VERIFY_MAX_TOKENS)
        verified = facts_from_payload(call4.get("parsed"), "v", document, None)
        if verified:
            keep = {fact["fact_id"] for fact in verified}
            replaced = {fid for row in conflicts for fid in row.get("fact_ids") or []}
            facts = [fact for fact in facts if fact["fact_id"] not in replaced] + verified
            if keep:
                facts = [fact for fact in facts if fact["fact_id"] in keep or fact["fact_id"] not in replaced]
    coverage = "whole_document" if route["mode"] == "whole_document" else "packed_sections"
    traces = evaluate_observables(facts, observables, coverage)
    reuse = reuse_stats(traces)
    resolved_n = sum(1 for row in traces if row["state"] == "RESOLVED")
    return {
        "entity_id": entity["entity_id"],
        "doc_id": entity["doc_id"],
        "stem": entity["stem"],
        "mode": route["mode"],
        "n_calls": len(calls),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "retry_tokens": retry_tokens,
        "verification_tokens": verify_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "graph_nodes": len(facts),
        "resolved_observables": resolved_n,
        "unresolved_observables": len(traces) - resolved_n,
        "used_call4": used_call4,
        "conflicts": conflicts,
        "calls": calls,
        "facts": facts,
        "traces": traces,
        "reuse": reuse,
        "parse": {"call1": call1.get("parse_ok"), "call2": call2.get("parse_ok"), "call3": call3.get("parse_ok")},
    }
