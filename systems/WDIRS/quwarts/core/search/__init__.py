"""Budget-aware search over complete <schema, pop, pre> triples."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

from quwarts.core.models import (
    Configuration,
    ConflictCluster,
    LogicalSchema,
    PhysicalSchema,
    PopulationPolicy,
    PreprocessPolicy,
    Workload,
)
from quwarts.core.preprocess import default_policies
from quwarts.core.rewrite import rewritable
from quwarts.core.schema import generate_physical_schemas


widen_coef = 1.5
widen_exp = 0.5
explore_coef = 1.0


@dataclass
class SearchNode:
    config: Configuration
    visits: int = 0
    U_hat: float = 0.0
    cost: float = 1.0
    children: list["SearchNode"] = field(default_factory=list)


def child_cap(n_visits: int) -> int:
    return max(1, math.ceil(widen_coef * (max(n_visits, 1) ** widen_exp)))


def score(node: SearchNode, t: int, eps: float = 1.0) -> float:
    bonus = explore_coef * math.sqrt(2.0 * math.log(max(t, 2)) / max(node.visits, 1))
    return (node.U_hat + bonus) / (node.cost + eps)


def marginal_cost(config: Configuration, seen_pre: set[str], seen_attrs: set[str], new_attrs: set[str]) -> float:
    """Set-level cost. Shared extraction is not charged again."""

    cost = 0.0
    pre_key = f"{config.pre.mode}|{config.pre.chunk_tokens}"
    if pre_key not in seen_pre:
        cost += 10.0
    novel = new_attrs - seen_attrs
    cost += 3.0 * len(novel)
    return max(cost, 0.25)


def config_id(schema: PhysicalSchema, pop: PopulationPolicy, pre: PreprocessPolicy, cluster_id: str) -> str:
    payload = f"{schema.id}|{cluster_id}|{pre.mode}|{pre.chunk_tokens}|{pop.model_dump_json()}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def generate_candidates(
    logical: LogicalSchema,
    workload: Workload,
    clusters: list[ConflictCluster],
    pops: dict[str, PopulationPolicy],
) -> list[Configuration]:
    schemas = generate_physical_schemas(logical)
    policies = default_policies()
    configs: list[Configuration] = []
    for cluster in clusters:
        pop = pops[cluster.id]
        for schema in schemas:
            feasible = any(
                rewritable(template, schema).ok
                for template in workload.templates
                if template.id in cluster.template_ids
            )
            if not feasible:
                continue
            for pre in policies:
                ident = config_id(schema, pop, pre, cluster.id)
                configs.append(
                    Configuration(
                        id=ident,
                        schema_=schema,
                        pop=pop,
                        pre=pre,
                        cluster_id=cluster.id,
                    )
                )
    return configs


def select_portfolio(
    candidates: list[Configuration],
    utilities: dict[str, float],
    costs: dict[str, float],
    clusters: list[ConflictCluster],
    theta_remaining: float,
) -> list[Configuration]:
    """Cost-weighted greedy. Static clusters keep the objective monotone."""

    by_cluster: dict[str, list[Configuration]] = {cluster.id: [] for cluster in clusters}
    for config in candidates:
        by_cluster.setdefault(config.cluster_id, []).append(config)

    selected: list[Configuration] = []
    spent = 0.0
    for cluster in clusters:
        options = by_cluster.get(cluster.id, [])
        options.sort(
            key=lambda config: utilities.get(config.id, 0.0) / (costs.get(config.id, 1.0) + 1e-6),
            reverse=True,
        )
        if not options:
            continue
        chosen = options[0]
        price = costs.get(chosen.id, 1.0)
        if spent + price > theta_remaining and selected:
            continue
        selected.append(chosen)
        spent += price
        for extra in options[1:]:
            extra_price = costs.get(extra.id, 1.0)
            gain = utilities.get(extra.id, 0.0) - utilities.get(chosen.id, 0.0)
            if gain <= 0:
                continue
            if spent + extra_price <= theta_remaining:
                selected.append(extra)
                spent += extra_price
    return selected


def select_for_labeling(
    utilities: dict[str, float],
    label_cost: float,
    budget_slice: float,
) -> list[str]:
    """M9 validation-fallback hook. ``U_hat`` picks which configs get a label."""

    ordered = sorted(utilities, key=lambda key: utilities[key], reverse=True)
    chosen: list[str] = []
    spent = 0.0
    for config_id in ordered:
        if spent + label_cost > budget_slice:
            break
        chosen.append(config_id)
        spent += label_cost
    return chosen
