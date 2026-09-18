"""Presupposition extraction, destructive conflict graph, clustering."""

from __future__ import annotations

import hashlib
from collections import defaultdict

from quwarts.core.logical import is_coarsening
from quwarts.core.models import (
    ConflictCluster,
    ConflictEdge,
    DerivedExpression,
    Presupposition,
    Role,
    Template,
    Workload,
)


def _cell(entity: str, attribute: str | None, module: str) -> tuple[str, str, str]:
    return (entity, attribute or "*", module)


def presuppositions(template: Template) -> list[Presupposition]:
    demands: list[Presupposition] = []
    for attribute, roles in template.roles_by_attribute.items():
        entity = attribute.split(".")[0] if "." in attribute else next(iter(template.entity_types), "entity")
        if Role.KEY in roles or Role.JOIN in roles:
            demands.append(
                Presupposition(
                    entity_type=entity,
                    attribute=attribute,
                    module="er",
                    demand="no_merge",
                    destructive=True,
                )
            )
            demands.append(
                Presupposition(
                    entity_type=entity,
                    attribute=attribute,
                    module="grain",
                    demand="mention",
                    destructive=True,
                )
            )
        if Role.GROUP in roles:
            # Grouping is SQL GROUP BY. It does not authorize row-level ER.
            demands.append(
                Presupposition(
                    entity_type=entity,
                    attribute=attribute,
                    module="grain",
                    demand="mention",
                    destructive=False,
                )
            )
        if Role.AGG_ADDITIVE in roles or Role.AGG_EXTREMAL in roles:
            demands.append(
                Presupposition(
                    entity_type=entity,
                    attribute=attribute,
                    module="unit",
                    demand="unit:canonical",
                    destructive=True,
                )
            )
            demands.append(
                Presupposition(
                    entity_type=entity,
                    attribute=attribute,
                    module="type",
                    demand="numeric",
                    destructive=False,
                )
            )
        if Role.PREDICATE in roles:
            demands.append(
                Presupposition(
                    entity_type=entity,
                    attribute=attribute,
                    module="miss",
                    demand="nulls_preserved",
                    destructive=True,
                )
            )
            demands.append(
                Presupposition(
                    entity_type=entity,
                    attribute=attribute,
                    module="norm",
                    demand="surface",
                    destructive=False,
                )
            )
        if Role.PROJECT in roles:
            demands.append(
                Presupposition(
                    entity_type=entity,
                    attribute=attribute,
                    module="norm",
                    demand="surface",
                    destructive=False,
                )
            )
    return demands


def _contradicts(a: str, b: str) -> bool:
    if a == b:
        return False
    pairs = {
        frozenset({"merge", "no_merge"}),
        frozenset({"nulls_preserved", "impute"}),
        frozenset({"surface", "canonical"}),
        frozenset({"unit:canonical", "unit:original"}),
        frozenset({"mention", "entity"}),
    }
    return frozenset({a, b}) in pairs or (a != b and a.split(":")[0] == b.split(":")[0] and ":" in a)


def _coarsening_derivable(
    left: str | None,
    right: str | None,
    expressions: list[DerivedExpression] | None,
) -> bool:
    """True when the conflict is a coarsening of the same base, not a true clash."""

    if not left or not right:
        return False
    bare_l = left.split(".")[-1].lower()
    bare_r = right.split(".")[-1].lower()
    if is_coarsening(bare_l) or is_coarsening(bare_r):
        return True
    if not expressions:
        return False
    names = {bare_l, bare_r, left.lower(), right.lower()}
    for item in expressions:
        alias = item.alias.lower()
        bases = {base.lower() for base in item.base_attributes}
        bases.update(base.split(".")[-1].lower() for base in item.base_attributes)
        if alias in names and (bases & names):
            return True
    return False


def conflict_graph(
    workload: Workload,
    expressions: list[DerivedExpression] | None = None,
) -> list[ConflictEdge]:
    per_template = {template.id: presuppositions(template) for template in workload.templates}
    edges: list[ConflictEdge] = []
    ids = list(per_template)
    for i, left_id in enumerate(ids):
        for right_id in ids[i + 1 :]:
            left = per_template[left_id]
            right = per_template[right_id]
            for a in left:
                for b in right:
                    if a.entity_type != b.entity_type or a.module != b.module:
                        continue
                    if a.attribute != b.attribute and a.attribute and b.attribute:
                        continue
                    if not _contradicts(a.demand, b.demand):
                        continue
                    destructive = a.destructive or b.destructive
                    if _coarsening_derivable(a.attribute, b.attribute, expressions):
                        destructive = False
                    edges.append(
                        ConflictEdge(
                            template_a=left_id,
                            template_b=right_id,
                            cell=_cell(a.entity_type, a.attribute, a.module),
                            demands=(a.demand, b.demand),
                            destructive=destructive,
                        )
                    )
    return edges


def cluster_templates(
    workload: Workload,
    expressions: list[DerivedExpression] | None = None,
) -> list[ConflictCluster]:
    """Greedy coloring on destructive edges only. Minimize cluster count."""

    edges = [edge for edge in conflict_graph(workload, expressions) if edge.destructive]
    adjacency: dict[str, set[str]] = {template.id: set() for template in workload.templates}
    for edge in edges:
        adjacency[edge.template_a].add(edge.template_b)
        adjacency[edge.template_b].add(edge.template_a)

    order = sorted(adjacency, key=lambda node: (-len(adjacency[node]), node))
    color: dict[str, int] = {}
    for node in order:
        forbidden = {color[nbr] for nbr in adjacency[node] if nbr in color}
        chosen = 0
        while chosen in forbidden:
            chosen += 1
        color[node] = chosen

    buckets: dict[int, list[str]] = defaultdict(list)
    for node, tint in color.items():
        buckets[tint].append(node)

    clusters: list[ConflictCluster] = []
    for tint, template_ids in sorted(buckets.items()):
        resolved = _resolved_demands(workload, template_ids)
        digest = hashlib.sha256(",".join(sorted(template_ids)).encode()).hexdigest()[:8]
        clusters.append(
            ConflictCluster(
                id=f"c{tint}-{digest}",
                template_ids=sorted(template_ids),
                resolved_demands=resolved,
            )
        )
    return clusters


def _resolved_demands(workload: Workload, template_ids: list[str]) -> dict[str, str]:
    chosen: dict[str, str] = {}
    wanted = set(template_ids)
    for template in workload.templates:
        if template.id not in wanted:
            continue
        for item in presuppositions(template):
            key = f"{item.entity_type}|{item.attribute}|{item.module}"
            if key not in chosen:
                chosen[key] = item.demand
            elif item.demand == "mention" or item.demand == "no_merge" or item.demand == "nulls_preserved":
                chosen[key] = item.demand
    return chosen


def conflict_mix(edges: list[ConflictEdge]) -> dict[str, int]:
    return {
        "destructive": sum(1 for edge in edges if edge.destructive),
        "non_destructive": sum(1 for edge in edges if not edge.destructive),
        "total": len(edges),
    }
