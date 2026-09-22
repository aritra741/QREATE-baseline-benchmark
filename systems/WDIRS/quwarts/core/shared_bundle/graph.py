"""Attribute co-occurrence graph and deterministic max-3 bundle partition."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from quwarts.core.shared_bundle.config import MAX_BUNDLE_SIZE
from quwarts.core.shared_bundle.inventory import AttributeRecord


@dataclass(frozen=True)
class Bundle:
    attributes: tuple[str, ...]

    @property
    def signature(self) -> str:
        return "+".join(self.attributes)

    def as_dict(self) -> dict[str, Any]:
        return {"attributes": list(self.attributes), "signature": self.signature, "size": len(self.attributes)}


@dataclass
class AttributeGraph:
    nodes: dict[str, dict[str, Any]]
    edges: dict[str, int]

    def weight(self, left: str, right: str) -> int:
        if left == right:
            return 0
        key = "|".join(sorted((left, right)))
        return int(self.edges.get(key) or 0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "nodes": {name: self.nodes[name] for name in sorted(self.nodes)},
            "edges": {key: self.edges[key] for key in sorted(self.edges)},
        }


def build_graph(records: dict[str, AttributeRecord], statements: dict[str, str]) -> AttributeGraph:
    per_query: list[set[str]] = []
    for _qid, sql in statements.items():
        used = {name for name, rec in records.items() if _qid in rec.queries}
        per_query.append(used)
    edges: dict[str, int] = {}
    for used in per_query:
        names = sorted(used)
        for i, left in enumerate(names):
            for right in names[i + 1 :]:
                key = f"{left}|{right}"
                edges[key] = edges.get(key, 0) + 1
    nodes = {
        name: {
            "occurrence_count": rec.occurrence_count,
            "n_queries": rec.n_queries,
            "roles": dict(rec.roles),
        }
        for name, rec in records.items()
    }
    return AttributeGraph(nodes=nodes, edges=edges)


def _affinity(name: str, members: Iterable[str], graph: AttributeGraph) -> int:
    return sum(graph.weight(name, other) for other in members)


def partition_bundles(records: dict[str, AttributeRecord], graph: AttributeGraph) -> list[Bundle]:
    ordered = sorted(records, key=lambda name: (-records[name].occurrence_count, name))
    groups: list[list[str]] = []
    for name in ordered:
        best_index = None
        best_key = None
        for index, members in enumerate(groups):
            if len(members) >= MAX_BUNDLE_SIZE:
                continue
            affinity = _affinity(name, members, graph)
            if affinity <= 0:
                continue
            key = (-affinity, len(members), "+".join(sorted(members + [name])))
            if best_key is None or key < best_key:
                best_key = key
                best_index = index
        if best_index is None:
            groups.append([name])
        else:
            groups[best_index].append(name)
    bundles = [Bundle(attributes=tuple(sorted(group))) for group in groups]
    bundles.sort(key=lambda item: item.signature)
    for bundle in bundles:
        if not 1 <= len(bundle.attributes) <= MAX_BUNDLE_SIZE:
            raise SystemExit(f"illegal bundle {bundle.signature}")
    assigned = [name for bundle in bundles for name in bundle.attributes]
    if sorted(assigned) != sorted(records):
        raise SystemExit("bundle partition dropped or duplicated an attribute")
    return bundles


def graph_hash(graph: AttributeGraph) -> str:
    return hashlib.sha256(json.dumps(graph.as_dict(), sort_keys=True).encode()).hexdigest()


def bundles_hash(bundles: list[Bundle]) -> str:
    payload = [item.as_dict() for item in bundles]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
