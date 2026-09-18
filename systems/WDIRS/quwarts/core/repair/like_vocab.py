"""LIKE tokens are declared vocabulary. Derived column only; surface stays."""

from __future__ import annotations

from typing import Any

from quwarts.core.domain import like_tokens_from_workload, overlap_kind
from quwarts.core.ledger import BudgetExhausted
from quwarts.core.models import EvidenceRecord, Workload


def _norm(text: str) -> str:
    return " ".join(str(text).replace("_", " ").casefold().split())


def _separators(text: str) -> list[str]:
    parts: list[str] = []
    buf = []
    for char in str(text):
        if char in ",;|/":
            piece = "".join(buf).strip()
            if piece:
                parts.append(piece)
            buf = []
        else:
            buf.append(char)
    piece = "".join(buf).strip()
    if piece:
        parts.append(piece)
    return parts


def token_hits(surface: str, tokens: list[str]) -> list[str]:
    folded = _norm(surface)
    hits = []
    for token in tokens:
        key = _norm(token)
        if not key:
            continue
        if key == folded or key in folded:
            hits.append(token)
    return hits


def column_is_multivalued(surfaces: list[str], tokens: list[str]) -> bool:
    if not surfaces:
        return False
    n_multi = 0
    for surface in surfaces:
        parts = _separators(surface)
        hits = token_hits(surface, tokens)
        if len(parts) >= 2 or len(hits) >= 2:
            n_multi += 1
    return n_multi / len(surfaces) >= 0.25


def measure_like_case(surfaces: list[str], tokens: list[str]) -> str:
    """a = overlapping map, b = disjoint classify, c = multivalued list."""

    if column_is_multivalued(surfaces, tokens):
        return "c"
    kind = overlap_kind(surfaces, tokens)
    if kind in {"empty", "disjoint"}:
        hit = any(token_hits(surface, tokens) for surface in surfaces)
        return "a" if hit else "b"
    return "a"


def dictionary_map(surfaces: list[str], tokens: list[str]) -> tuple[dict[str, str], list[str]]:
    mapped: dict[str, str] = {}
    residue: list[str] = []
    for surface in surfaces:
        hits = token_hits(surface, tokens)
        if len(hits) == 1:
            mapped[surface] = hits[0]
        else:
            residue.append(surface)
    return mapped, residue


def apply_like_vocabulary(
    records: list[EvidenceRecord],
    workload: Workload,
    caller=None,
) -> dict[str, Any]:
    """Write derived assignments. Do not mutate surface_value."""

    tokens = workload.like_tokens or like_tokens_from_workload(workload)
    by_attr: dict[str, list[EvidenceRecord]] = {}
    for record in records:
        by_attr.setdefault(record.attribute, []).append(record)

    report: dict[str, Any] = {"columns": {}, "n_mapped": 0, "n_classified": 0, "unverified": []}
    seen_bare: set[str] = set()
    for name, items in by_attr.items():
        bare = name.split(".")[-1]
        vocab = list(tokens.get(name) or tokens.get(bare) or [])
        if len(vocab) < 1 or bare in seen_bare:
            continue
        seen_bare.add(bare)
        surfaces = sorted({
            str(item.surface_value).strip()
            for item in items
            if item.surface_value not in (None, "")
        })
        if not surfaces:
            continue
        case = measure_like_case(surfaces, vocab)
        mapped, residue = dictionary_map(surfaces, vocab)
        classified = False
        if case == "b" and caller is not None:
            try:
                mapped.update(_classify(residue, vocab, caller))
                residue = [item for item in residue if item not in mapped]
                classified = True
            except BudgetExhausted:
                pass
        elif case in {"a", "c"} and residue and caller is not None:
            try:
                mapped.update(_classify(residue, vocab, caller))
                residue = [item for item in residue if item not in mapped]
            except BudgetExhausted:
                pass
        for record in items:
            surface = str(record.surface_value or "").strip()
            if not surface:
                continue
            assigned = mapped.get(surface)
            if case == "c" and assigned is None:
                hits = token_hits(surface, vocab)
                assigned = "|".join(hits) if hits else None
            if assigned in (None, ""):
                continue
            keys = dict(record.candidate_keys or {})
            keys["like_vocab"] = assigned
            keys["like_case"] = case
            record.candidate_keys = keys
            if classified:
                report["n_classified"] += 1
            else:
                report["n_mapped"] += 1
        report["columns"][name] = {
            "case": case,
            "n_surfaces": len(surfaces),
            "n_tokens": len(vocab),
            "n_mapped": len(mapped),
            "n_residue": len(residue),
            "classified": classified,
        }
        if classified:
            report["unverified"].append(name)
    return report


def _classify(values: list[str], vocab: list[str], caller) -> dict[str, str]:
    if not values or not vocab:
        return {}
    prompt = (
        "Assign each value to exactly one vocabulary token, or null if none apply. "
        "This is a classification onto the token set declared by SQL LIKE patterns. "
        "Return a JSON object. No commentary.\n"
        f"VOCABULARY: {vocab}\n"
        f"VALUES: {values}\n"
    )
    text = caller.complete(prompt, purpose="like_classify")
    from quwarts.core.extract import _parse_llm_object

    payload = _parse_llm_object(text)
    allowed = {_norm(item): item for item in vocab}
    mapped: dict[str, str] = {}
    for value in values:
        raw = payload.get(value)
        if raw is None:
            raw = payload.get(value.casefold())
        if raw in (None, "", "null"):
            continue
        hit = allowed.get(_norm(str(raw)))
        if hit is not None:
            mapped[value] = hit
    return mapped
