"""One ER pass. One shared canonical ID. No per-join bridges."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any

from quwarts.core.domain import _llm_identity_map, _surfaces, identity_components
from quwarts.core.ledger import BudgetExhausted
from quwarts.core.models import EvidenceRecord, Workload


def _fold(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


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
