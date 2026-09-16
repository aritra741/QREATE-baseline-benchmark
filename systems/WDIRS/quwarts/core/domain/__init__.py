"""Declared value domains from SQL, and O(distinct) surface mapping.

Nothing here is corpus-specific. IN lists, equijoin pairs, and CASE
literal aliases are read from the workload AST.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

from quwarts.core.extract import _parse_llm_object
from quwarts.core.models import EvidenceRecord, Workload

JOIN_JACCARD_GATE = 0.05
IDENTITY_ALIGNED = 0.5
IDENTITY_MIN_CANON_RATIO = 0.25


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a = {item.strip().lower() for item in left if item and str(item).strip()}
    b = {item.strip().lower() for item in right if item and str(item).strip()}
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def domain_disjoint(surfaces: Iterable[str], domain: Iterable[str]) -> bool:
    a = {item.strip() for item in surfaces if item and str(item).strip()}
    b = {item.strip() for item in domain if item and str(item).strip()}
    if not a or not b:
        return False
    folded_a = {item.lower() for item in a}
    folded_b = {item.lower() for item in b}
    return folded_a.isdisjoint(folded_b)


def overlap_kind(surfaces: Iterable[str], domain: Iterable[str]) -> str:
    """disjoint | partial | subset | empty."""

    a = {item.strip().lower() for item in surfaces if item and str(item).strip()}
    b = {item.strip().lower() for item in domain if item and str(item).strip()}
    if not a or not b:
        return "empty"
    if a.isdisjoint(b):
        return "disjoint"
    if a <= b or b <= a:
        return "subset"
    return "partial"


def _col_values(rows: list[dict[str, Any]], name: str) -> list[str]:
    bare = name.split(".")[-1]
    values: list[str] = []
    for row in rows:
        value = row.get(name)
        if value in (None, ""):
            value = row.get(bare)
        if value not in (None, ""):
            values.append(str(value).strip())
    return values


def disjoint_attributes(rows: list[dict[str, Any]], workload: Workload) -> list[str]:
    flagged: list[str] = []
    for name, req in workload.requirements.items():
        if len(req.declared_domain) < 2:
            continue
        values = _col_values(rows, name)
        if domain_disjoint(values, req.declared_domain):
            flagged.append(name)
    return flagged


def join_disjoint_pairs(rows: list[dict[str, Any]], workload: Workload) -> list[dict[str, Any]]:
    """Equijoin sides whose materialized sets do not overlap."""

    flagged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for template in workload.templates:
        for left, right in template.join_pairs:
            key = tuple(sorted((left, right)))
            if key in seen or left == right:
                continue
            seen.add(key)
            left_vals = _col_values(rows, left)
            right_vals = _col_values(rows, right)
            if not left_vals or not right_vals:
                continue
            score = jaccard(left_vals, right_vals)
            if score <= JOIN_JACCARD_GATE:
                flagged.append({"left": left, "right": right, "jaccard": score})
    return flagged


def identity_components(workload: Workload) -> list[set[str]]:
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        parent[find(right)] = find(left)

    for template in workload.templates:
        for left, right in template.join_pairs:
            if left and right and left != right:
                union(left, right)
    groups: dict[str, set[str]] = defaultdict(set)
    for node in parent:
        groups[find(node)].add(node)
    return [group for group in groups.values() if len(group) >= 2]


def collision_report(mapping: dict[str, str]) -> dict[str, Any]:
    buckets: dict[str, set[str]] = defaultdict(set)
    for source, dest in mapping.items():
        if dest in (None, ""):
            continue
        buckets[str(dest)].add(source)
    n_canon = len(buckets)
    n_src = max(len(mapping), 1)
    max_bucket = max((len(items) for items in buckets.values()), default=0)
    return {
        "n_surfaces": len(mapping),
        "n_canonical": n_canon,
        "canon_ratio": n_canon / n_src,
        "max_bucket": max_bucket,
        "collapsed": {
            dest: sorted(items)
            for dest, items in buckets.items()
            if len(items) > 1
        },
    }


def _corroborate(mapping: dict[str, str], records: list[EvidenceRecord]) -> dict[str, str]:
    """Promote a merge only if more than one document mentions the pair."""

    docs: dict[str, set[str]] = defaultdict(set)
    for record in records:
        if record.surface_value in (None, ""):
            continue
        docs[str(record.surface_value).strip()].add(record.doc_id)
    kept: dict[str, str] = {}
    for source, dest in mapping.items():
        if source == dest:
            kept[source] = dest
            continue
        # The source mention is the merge evidence. Dest is often a common
        # team/city name and must not launder a single stray extraction.
        if len(docs.get(source, set())) >= 2:
            kept[source] = dest
    return kept


def classify_declared_domains(workload: Workload, records: list[EvidenceRecord]) -> None:
    """An IN list is a domain iff it is disjoint from extracted surfaces."""

    surfaces = _surfaces(records)
    for name, req in workload.requirements.items():
        lists = workload.in_lists.get(name) or workload.in_lists.get(name.split(".")[-1], [])
        extracted = set()
        for key in (name, name.split(".")[-1]):
            extracted.update(surfaces.get(key, ()))
        closed: set[str] = set()
        for item in lists:
            kind = overlap_kind(extracted, item)
            if kind == "disjoint":
                closed.update(item)
        req.declared_domain = sorted(closed)


def _exact_map(surface: str, domain: list[str]) -> str | None:
    folded = {item.lower(): item for item in domain}
    return folded.get(surface.strip().lower())


def _surfaces(records: list[EvidenceRecord]) -> dict[str, set[str]]:
    surfaces: dict[str, set[str]] = defaultdict(set)
    for record in records:
        if record.surface_value in (None, ""):
            continue
        text = str(record.surface_value).strip()
        surfaces[record.attribute].add(text)
        surfaces[record.attribute.split(".")[-1]].add(text)
    return surfaces


def build_domain_maps(
    records: list[EvidenceRecord],
    workload: Workload,
    caller=None,
    logical=None,
) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    """O(distinct) maps for disjoint IN lists and equijoin identity spaces."""

    surfaces = _surfaces(records)
    maps: dict[str, dict[str, str]] = {}
    identity_report: dict[str, Any] = {}

    def _remember(name: str, mapping: dict[str, str]) -> None:
        maps[name] = {**(maps.get(name) or {}), **mapping}
        maps[name.split(".")[-1]] = maps[name]

    for name, req in workload.requirements.items():
        domain = list(req.declared_domain)
        if len(domain) < 2:
            continue
        seen: set[str] = set()
        for key in (name, name.split(".")[-1]):
            seen.update(surfaces.get(key, ()))
        if not seen:
            continue
        mapping: dict[str, str] = {}
        unknown: list[str] = []
        for value in sorted(seen):
            hit = _exact_map(value, domain)
            if hit is not None:
                mapping[value] = hit
            else:
                unknown.append(value)
        if unknown and caller is not None:
            mapping.update(_llm_map(unknown, domain, caller, name))
        _remember(name, mapping)

    for component in identity_components(workload):
        seen: set[str] = set()
        for attr in component:
            seen.update(surfaces.get(attr) or ())
            seen.update(surfaces.get(attr.split(".")[-1]) or ())
        mapping = {
            source: dest
            for source, dest in workload.literal_aliases.items()
            if source and (source in seen or dest in seen)
        }
        pair_maps: list[dict[str, Any]] = []
        for left, right in _pairs_in(component, workload):
            left_vals = surfaces.get(left) or surfaces.get(left.split(".")[-1]) or set()
            right_vals = surfaces.get(right) or surfaces.get(right.split(".")[-1]) or set()
            if not left_vals or not right_vals:
                continue
            pair_maps.append(
                {
                    "left": left,
                    "right": right,
                    "jaccard_before": jaccard(left_vals, right_vals),
                }
            )
        linkage = {
            source: dest
            for source, dest in mapping.items()
            if source.strip().lower() != dest.strip().lower()
        }
        if linkage:
            identity_report.setdefault("linkage", {}).update(linkage)
        mapping = _corroborate(mapping, records)
        within = {
            source: dest
            for source, dest in mapping.items()
            if source.strip().lower() == dest.strip().lower()
        }
        report = collision_report(within)
        report["pairs"] = pair_maps
        report["n_linkage"] = len(linkage)
        identity_report["+".join(sorted(component))] = report
        if within:
            identity_report.setdefault("maps", {})
            for attr in component:
                identity_report["maps"][attr] = within
    return maps, identity_report


def _pairs_in(component: set[str], workload: Workload) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for template in workload.templates:
        for left, right in template.join_pairs:
            if left not in component or right not in component:
                continue
            key = tuple(sorted((left, right)))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((left, right))
    return pairs


def _atomic(values: Iterable[str]) -> list[str]:
    return [item for item in values if item and "," not in item]


def _source_and_targets(
    left: str,
    left_vals: set[str],
    right: str,
    right_vals: set[str],
) -> tuple[str, set[str], list[str]]:
    """Map the higher-cardinality side onto the other's atomic values."""

    if len(left_vals) >= len(right_vals):
        return left, left_vals, sorted(_atomic(right_vals) or right_vals)
    return right, right_vals, sorted(_atomic(left_vals) or left_vals)


def _llm_identity_map(
    values: list[str],
    representatives: list[str],
    caller,
    label: str,
) -> dict[str, str]:
    prompt = (
        "These extracted strings belong to columns that SQL equijoins, "
        "so they share an identity space. Map each value to exactly one "
        "representative, or null if it matches none.\n"
        f"REPRESENTATIVES: {json.dumps(representatives)}\n"
        f"VALUES: {json.dumps(values)}\n"
        "When several values name the same entity, use the same representative. "
        "Prefer the longest representative. Return a JSON object. No commentary."
    )
    text = caller.complete(prompt, purpose="identity_map", attribute=label)
    payload = _parse_llm_object(text)
    mapped: dict[str, str] = {}
    allowed = {item.lower(): item for item in representatives}
    for value in values:
        raw = payload.get(value)
        if raw is None:
            raw = payload.get(value.lower())
        if raw in (None, "", "null"):
            continue
        hit = allowed.get(str(raw).strip().lower())
        if hit is not None:
            mapped[value] = hit
    return mapped


def _llm_map(
    values: list[str],
    domain: list[str],
    caller,
    attribute: str,
) -> dict[str, str]:
    prompt = (
        f"Map each extracted {attribute} value to exactly one declared domain "
        "member, or null if it does not belong.\n"
        f"DOMAIN: {json.dumps(domain)}\n"
        f"VALUES: {json.dumps(values)}\n"
        "Return a JSON object mapping each value to a domain member or null. "
        "No commentary."
    )
    text = caller.complete(prompt, purpose="domain_map", attribute=attribute)
    payload = _parse_llm_object(text)
    mapped: dict[str, str] = {}
    allowed = {item.lower(): item for item in domain}
    for value in values:
        raw = payload.get(value)
        if raw is None:
            raw = payload.get(value.lower())
        if raw in (None, "", "null"):
            continue
        hit = allowed.get(str(raw).strip().lower())
        if hit is not None:
            mapped[value] = hit
    return mapped


def apply_domain(value: Any, mapping: dict[str, str], domain: list[str]) -> Any:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text in mapping:
        return mapping[text]
    hit = _exact_map(text, domain) if domain else None
    if hit is not None:
        return hit
    folded = {key.lower(): dest for key, dest in mapping.items()}
    mapped = folded.get(text.lower())
    if mapped is not None:
        return mapped
    if len(domain) >= 2:
        return None
    return text
