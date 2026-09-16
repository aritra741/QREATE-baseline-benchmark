"""Amplification calculus. ``amp`` is distinct from ``widen_coef``."""

from __future__ import annotations

import math

from quwarts.core.models import AttributeRequirement, AttributeStats, Role, Workload


def amp_role(role: Role, stats: AttributeStats) -> float:
    m = max(stats.group_size, 1.0)
    d = max(stats.n_distinct, 1)
    n = max(stats.n_rows, 1)
    rho = min(1.0, max(0.0, stats.rho))
    if role == Role.PROJECT:
        return 1.0
    if role in {Role.KEY, Role.JOIN}:
        return float(max(stats.n_scored_columns, 1))
    if role == Role.AGG_ADDITIVE:
        return max(1.0 / math.sqrt(m), math.sqrt(rho))
    if role == Role.GROUP:
        return 2.0 * m
    if role == Role.AGG_EXTREMAL:
        return m
    if role == Role.AGG_DISTINCT:
        return n / d
    if role == Role.PREDICATE:
        return 1.0
    return 1.0


def amp(requirement: AttributeRequirement) -> float:
    stats = requirement.stats
    if stats is None:
        stats = AttributeStats(
            n_rows=1, n_groups=1, group_size=1.0, n_distinct=1,
            multiplicity=1.0, rho=0.5, n_scored_columns=1,
        )
    roles = requirement.roles or {Role.PROJECT}
    return max(amp_role(role, stats) for role in roles) * requirement.freq_weight


def attach_amplification(workload: Workload) -> dict[str, float]:
    values: dict[str, float] = {}
    for name, req in workload.requirements.items():
        value = amp(req)
        req.amp = value
        values[name] = value
    return values


def allocation_weights(workload: Workload) -> dict[str, float]:
    """Tokens proportional to ``amp(a) * expected_marginal_quality(a)``."""

    weights: dict[str, float] = {}
    for name, req in workload.requirements.items():
        quality = 1.0
        if req.stats is not None:
            quality = 1.0 / (1.0 + req.stats.multiplicity * 0.1)
        weights[name] = max((req.amp or amp(req)) * quality, 1e-6)
    total = sum(weights.values())
    return {name: value / total for name, value in weights.items()}
