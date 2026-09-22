"""Budget-aware job order. No attribute-name or dataset branches."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def quality_rank(existing: list[dict[str, Any]], labels: list[str]) -> int:
    if not existing:
        return 0
    if all(item.get("derivation") == "surface" and float(item.get("score") or 0) < 0.15 for item in existing):
        return 1
    values = {str(item.get("normalized") or "").lower() for item in existing}
    if labels and not any(str(label).lower() in values for label in labels):
        return 2
    if any(not item.get("period") and not item.get("component_scope") for item in existing):
        return 3
    return 4


def attribute_priority(record: Any, unresolved: int, density: float, est_cost: int) -> float:
    amplify = max(1, int(record.n_queries))
    occ = max(1, int(record.occurrence_count))
    cost = max(1, int(est_cost))
    return (occ * amplify * max(1, unresolved) * (1.0 / (1.0 + density))) / cost


def order_jobs(
    cells: list[dict[str, Any]],
    records: dict[str, Any],
    labels_by_attr: dict[str, dict[str, Any]],
    est_cost: int,
) -> list[dict[str, Any]]:
    by_attr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    density: dict[str, float] = {}
    unresolved: dict[str, int] = {}
    for cell in cells:
        by_attr[cell["attribute"]].append(cell)
    scores = {}
    for name, rows in by_attr.items():
        empty = sum(1 for row in rows if not row.get("existing"))
        mean_n = sum(len(row.get("existing") or []) for row in rows) / max(1, len(rows))
        density[name] = mean_n
        unresolved[name] = empty
        scores[name] = attribute_priority(records[name], empty, mean_n, est_cost)
        rows.sort(key=lambda row: (quality_rank(row.get("existing") or [], (labels_by_attr.get(name) or {}).get("all_labels") or []), row["entity_id"]))
    attrs = sorted(by_attr, key=lambda name: (-scores[name], name))
    queues = {name: list(by_attr[name]) for name in attrs}
    ordered: list[dict[str, Any]] = []
    while any(queues[name] for name in attrs):
        for name in attrs:
            if queues[name]:
                ordered.append(queues[name].pop(0))
    return ordered
