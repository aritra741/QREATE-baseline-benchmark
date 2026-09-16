"""Static router. Zero tokens. No LLM. No score-based selection."""

from __future__ import annotations

from quwarts.core.models import Configuration, CoverageSet, MaterializedDB, Template, Workload
from quwarts.core.rewrite import rewritable


def cluster_of(template_id: str, cluster_map: dict[str, str]) -> str:
    return cluster_map[template_id]


def route_template(
    template: Template,
    configurations: list[Configuration],
    databases: dict[str, MaterializedDB],
    cluster_map: dict[str, str],
    workload: Workload,
) -> str | None:
    """First feasible configuration in deterministic id order."""

    cluster_id = cluster_map[template.id]
    # SPP insertion order. Sorting by id would reroute when a new
    # configuration with a smaller id is appended.
    candidates = [
        config
        for config in configurations
        if config.cluster_id == cluster_id
    ]
    for config in candidates:
        db = databases.get(config.id)
        coverage = db.coverage if db else None
        result = rewritable(template, config.schema_, coverage, workload.requirements)
        if not result.ok:
            continue
        if coverage is not None:
            ok = True
            for slot in template.param_slots:
                ranges = coverage.attribute_ranges.get(slot.attribute)
                if ranges is None or not ranges.contains_constants(slot.observed_constants):
                    ok = False
                    break
            if not ok:
                continue
        return config.id
    return None


def route_workload(
    workload: Workload,
    configurations: list[Configuration],
    databases: list[MaterializedDB],
    cluster_map: dict[str, str],
) -> dict[str, str]:
    by_id = {db.config_id: db for db in databases}
    routing: dict[str, str] = {}
    for template in sorted(workload.templates, key=lambda item: item.id):
        chosen = route_template(template, configurations, by_id, cluster_map, workload)
        if chosen is None:
            continue
        for stmt_id in template.statement_ids:
            routing[stmt_id] = chosen
        routing[template.id] = chosen
    return routing
