"""Repair ranker. Uses amp(a) directly. No key/join > projection."""

from __future__ import annotations

from quwarts.core.amplify import amp
from quwarts.core.models import Workload
from quwarts.core.repair.models import Repair, RepairIssue


def attribute_amp(workload: Workload, name: str) -> float:
    req = workload.requirements.get(name)
    if req is None:
        bare = name.split(".")[-1]
        for key, item in workload.requirements.items():
            if key.split(".")[-1] == bare:
                req = item
                break
    if req is None:
        return 1.0
    return req.amp if req.amp is not None else amp(req)


def query_frequency(workload: Workload, query_ids: list[str]) -> float:
    if not query_ids:
        return 1.0
    by_stmt = {
        stmt_id: template.freq
        for template in workload.templates
        for stmt_id in template.statement_ids
    }
    by_template = {template.id: template.freq for template in workload.templates}
    total = 0.0
    for item in query_ids:
        total += float(by_stmt.get(item) or by_template.get(item) or 1.0)
    return max(total, 1.0)


def recoverable_mass(issue: RepairIssue, n_queries: int) -> float:
    if issue.kind == "empty_query":
        return float(len(issue.query_ids) or issue.detail.get("count") or 1)
    if issue.kind == "join_yield":
        missing = 1.0 - float(issue.detail.get("yield") or 0.0)
        return max(missing, 0.0) * max(len(issue.query_ids), 1)
    if issue.kind == "dtype_coercion":
        return min(float(issue.detail.get("count") or 1) / 10.0, float(n_queries or 1))
    return max(float(issue.severity), 0.1)


def priority(
    issue: RepairIssue,
    workload: Workload,
    estimated_cost: int,
    n_queries: int,
) -> float:
    """
    priority = freq × max amp(a) × severity × recoverable mass / token cost
    """

    names = issue.attributes or list(workload.requirements)
    impact = max((attribute_amp(workload, name) for name in names), default=1.0)
    freq = query_frequency(workload, issue.query_ids)
    mass = recoverable_mass(issue, n_queries)
    cost = max(int(estimated_cost), 1)
    return (freq * impact * max(issue.severity, 1e-6) * mass) / cost


def rank_repairs(
    repairs: list[Repair],
    workload: Workload,
    n_queries: int,
) -> list[Repair]:
    scored: list[Repair] = []
    for repair in repairs:
        repair.priority = priority(repair.issue, workload, repair.estimated_cost, n_queries)
        scored.append(repair)
    return sorted(scored, key=lambda item: item.priority, reverse=True)
