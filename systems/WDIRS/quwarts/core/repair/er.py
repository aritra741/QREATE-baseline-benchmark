"""One ER pass. One shared canonical ID. No per-join bridges."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from quwarts.core.domain import _llm_identity_map, _surfaces, identity_components
from quwarts.core.ledger import BudgetExhausted
from quwarts.core.models import EvidenceRecord, Workload


def _fold(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _threshold_merge(values: list[str], threshold: float = 0.92) -> dict[str, str]:
    """Block on a prefix, merge pairs above a similarity threshold. No corpus rules."""

    from difflib import SequenceMatcher

    blocks: dict[str, list[str]] = {}
    for value in values:
        blocks.setdefault(_fold(value)[:3], []).append(value)
    merged: dict[str, str] = {}
    for group in blocks.values():
        for index, left in enumerate(group):
            if left in merged:
                continue
            for right in group[index + 1 :]:
                if right in merged:
                    continue
                if SequenceMatcher(None, _fold(left), _fold(right)).ratio() >= threshold:
                    merged[right] = left
    return merged


def _canon_id(surface: str) -> str:
    digest = hashlib.sha256(_fold(surface).encode()).hexdigest()[:12]
    return f"er:{digest}"


def resolve_shared_ids(
    records: list[EvidenceRecord],
    workload: Workload,
    caller=None,
) -> dict[str, Any]:
    """Run ER once over distinct values. The same ID is used in every database."""

    surfaces = _surfaces(records)
    table: list[dict[str, Any]] = []
    maps: dict[str, dict[str, str]] = {}
    linkage: dict[str, str] = {}
    seen_ids: dict[str, str] = {}

    components = identity_components(workload)
    if not components:
        return {"table": table, "maps": maps, "linkage": linkage}

    for component in components:
        values: set[str] = set()
        for attr in component:
            values.update(surfaces.get(attr) or ())
            values.update(surfaces.get(attr.split(".")[-1]) or ())
        groups: dict[str, str] = {}
        mapping: dict[str, str] = {}
        provenance: dict[str, str] = {}
        confidence: dict[str, float] = {}
        for value in sorted(values):
            key = _fold(value)
            if not key:
                continue
            groups.setdefault(key, value)
            mapping[value] = groups[key]
            provenance[value] = "exact_fold"
            confidence[value] = 1.0
        leftovers = sorted({groups[key] for key in groups})
        for source, dest in _threshold_merge(leftovers).items():
            dest_id = mapping.get(dest) or dest
            for surface, current in list(mapping.items()):
                if current == source or _fold(surface) == _fold(source):
                    mapping[surface] = dest_id
                    provenance[surface] = "blocked_threshold"
                    confidence[surface] = 0.85
            leftovers = [item for item in leftovers if item != source]
        leftovers = sorted({mapping.get(item, item) for item in leftovers})
        if caller is not None and len(leftovers) >= 2:
            try:
                merged = _llm_identity_map(leftovers, leftovers, caller, "+".join(sorted(component)))
            except BudgetExhausted:
                merged = {}
            for source, dest in merged.items():
                if not dest:
                    continue
                dest_id = mapping.get(dest) or dest
                for surface, current in list(mapping.items()):
                    if current == source or _fold(surface) == _fold(source):
                        mapping[surface] = dest_id
                        provenance[surface] = "llm"
                        confidence[surface] = 0.7
                linkage[source] = dest
        id_for: dict[str, str] = {}
        for dest in mapping.values():
            id_for.setdefault(dest, seen_ids.setdefault(_fold(dest), _canon_id(dest)))
        attr_map = {
            surface: id_for[dest]
            for surface, dest in mapping.items()
            if dest in id_for
        }
        for surface, dest in mapping.items():
            cid = id_for.get(dest)
            if cid is None:
                continue
            table.append(
                {
                    "surface": surface,
                    "canonical_id": cid,
                    "match_confidence": confidence.get(surface, 1.0),
                    "provenance": provenance.get(surface, "exact_fold"),
                }
            )
        for attr in component:
            maps[attr] = dict(attr_map)
            maps[attr.split(".")[-1]] = dict(attr_map)
    return {"table": table, "maps": maps, "linkage": linkage}


def align_unmatched(
    left_values: list[str],
    right_values: list[str],
    caller=None,
    label: str = "join",
) -> dict[str, str]:
    """Map unmatched left surfaces onto right representatives."""

    mapping: dict[str, str] = {}
    right_fold = {_fold(item): item for item in right_values if item}
    for value in left_values:
        hit = right_fold.get(_fold(value))
        if hit is not None:
            mapping[value] = hit
    leftover = [item for item in left_values if item not in mapping]
    if caller is not None and leftover and right_values:
        try:
            mapping.update(_llm_identity_map(leftover, list(right_values), caller, label))
        except BudgetExhausted:
            pass
    return mapping


def stamp_shared_ids(identity_report: dict[str, Any], shared: dict[str, Any]) -> dict[str, Any]:
    """Replace per-join maps with the shared ER table."""

    report = dict(identity_report or {})
    report["maps"] = dict(shared.get("maps") or {})
    report["linkage"] = dict(shared.get("linkage") or {})
    report["shared_er"] = {
        "n_surfaces": len(shared.get("table") or []),
        "n_ids": len({row["canonical_id"] for row in shared.get("table") or []}),
        "table": shared.get("table") or [],
    }
    return report
