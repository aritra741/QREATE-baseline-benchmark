"""Generic router, proposal, and verification prompts. No dataset names."""

from __future__ import annotations

from typing import Any

from quwarts.core.amortized_select.prompt import assemble_tools

ROUTER_SCHEMA = {
    "channels": "list[str]",
    "reason": "str",
}
PROPOSAL_SCHEMA = {
    "values": "list[str]",
    "derivations": "list[str]",
    "evidence_texts": "list[str]",
    "none": "bool",
}
VERIFY_SCHEMA = {
    "verdict": "str",
    "reason": "str",
}
CHANNELS = ["surface", "normalized", "workload_label", "semantic", "composed"]


def router_user(spec: Any, record: Any, labels: dict[str, Any], density: dict[str, Any], structures: list[str]) -> str:
    return (
        "Choose every candidate-generation channel that could produce a valid value for this attribute. "
        "Do not pick a single exclusive channel when several could work. "
        "Do not use gold values, scores, or corpus-specific instructions.\n"
        f"Attribute: {spec.name}\n"
        f"Official description: {spec.official_description}\n"
        f"Type: {spec.dtype} ({spec.sql_type}); task_class={spec.task_class}\n"
        f"AST roles: {dict(record.roles)}\n"
        f"Occurrence count: {record.occurrence_count}; queries: {record.n_queries}\n"
        f"Cardinality hint: one value unless the description allows multiple.\n"
        f"Workload-visible labels: {labels.get('all_labels') or []}\n"
        f"LIKE anchors: {labels.get('like_anchors') or []}\n"
        f"Candidate-density statistics: {density}\n"
        f"Representative source structures: {structures}\n"
        "Allowed channels: surface, normalized, workload_label, semantic, composed.\n"
        "surface = exact spans already extracted from the document.\n"
        "normalized = deterministic typed transforms of those spans.\n"
        "workload_label = finite AST literals that may apply if evidence supports them.\n"
        "semantic = inferred labels that need not occur verbatim.\n"
        "composed = values assembled from multiple supporting spans.\n"
        "Return channels as a list. Never invent attribute-specific rules."
    )


def proposal_user(
    spec: Any,
    labels: list[str],
    entity_label: str,
    context: str,
    existing: list[dict[str, Any]],
    allow_composed: bool,
) -> str:
    cards = []
    for item in existing[:12]:
        cards.append(
            f"{item.get('id')}: value={item.get('normalized')!r} raw={item.get('raw_span')!r} "
            f"derivation={item.get('derivation')} start={item.get('start')}"
        )
    compose = (
        "You may also emit composed values that combine multiple cited spans when one span is incomplete."
        if allow_composed
        else "Do not compose values from multiple spans."
    )
    return (
        "Propose up to four candidate values for this one entity-attribute pair, or NONE.\n"
        "Cite evidence spans from the provided context. A value need not occur verbatim if the evidence supports the inference.\n"
        "Distinguish the requested attribute from related concepts.\n"
        "Distinguish current status from historical events.\n"
        "Distinguish outcome from a claim, request, or allegation.\n"
        "Distinguish document metadata from the entity value.\n"
        "Do not copy examples, SQL thresholds, or labels that the context does not support.\n"
        "Retain multiple plausible values instead of forcing one answer.\n"
        "Keep SQL NULL, false, unknown, and absence distinct. Do not emit NULL as a value.\n"
        f"{compose}\n"
        f"Attribute: {spec.name}\n"
        f"Official description: {spec.official_description}\n"
        f"Expected type: {spec.dtype}; cardinality: single unless the description allows multiple.\n"
        f"Workload-visible labels that may apply: {labels or '(none)'}\n"
        f"Entity label: {entity_label}\n"
        "Existing surface/normalized candidates:\n"
        + ("\n".join(cards) or "(none)")
        + "\n\nDocument or retrieved context:\n"
        + context
        + "\n\nReturn parallel lists values, derivations, and evidence_texts of equal length, at most four items. "
        "derivation is semantic, composed, or workload_label. evidence_texts are verbatim excerpts from the context. "
        "Set none=true if no supported candidate exists."
    )


def verify_user(spec: Any, candidate: dict[str, Any], entity_label: str, context: str) -> str:
    spans = candidate.get("evidence_spans") or []
    return (
        "Decide whether the cited evidence supports this candidate for the stated attribute. "
        "Do not rewrite the value. Output exactly one of: supported, unsupported, uncertain.\n"
        "supported = the evidence justifies the value for this entity and attribute.\n"
        "unsupported = the evidence does not justify the value.\n"
        "uncertain = the evidence is incomplete or ambiguous. Do not delete a merely uncertain value.\n"
        "Missing or malformed output must be treated as uncertain by the caller, not as false.\n"
        f"Attribute: {spec.name}\n"
        f"Official description: {spec.official_description}\n"
        f"Entity label: {entity_label}\n"
        f"Candidate value: {candidate.get('value')!r}\n"
        f"Derivation: {candidate.get('derivation')}\n"
        f"Claimed evidence: {spans}\n"
        f"Context:\n{context}"
    )


def router_bundle(spec: Any, record: Any, labels: dict[str, Any], density: dict[str, Any], structures: list[str]) -> dict[str, Any]:
    return assemble_tools(ROUTER_SCHEMA, router_user(spec, record, labels, density, structures))


def proposal_bundle(spec: Any, labels: list[str], entity_label: str, context: str, existing: list[dict[str, Any]], allow_composed: bool) -> dict[str, Any]:
    return assemble_tools(PROPOSAL_SCHEMA, proposal_user(spec, labels, entity_label, context, existing, allow_composed))


def verify_bundle(spec: Any, candidate: dict[str, Any], entity_label: str, context: str) -> dict[str, Any]:
    return assemble_tools(VERIFY_SCHEMA, verify_user(spec, candidate, entity_label, context))
