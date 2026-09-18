"""Diagnose rewrite-missing empties. Zero tokens. No gold."""

from __future__ import annotations

from typing import Any

from quwarts.core.logical import SchemaConflict, bind_identifier
from quwarts.core.models import FrozenPortfolio, Workload
from quwarts.core.rewrite import rewritable


def diagnose_rewrite_failures(
    query_ids: list[str],
    statements: dict[str, str],
    portfolio: FrozenPortfolio,
    workload: Workload,
) -> list[dict[str, Any]]:
    """Classify each rewrite miss: absent from L, coverage, slice-unsafe, unbound."""

    from quwarts.core.pipeline import serve_plans
    from quwarts.core.workload import analyze_workload

    logical = portfolio.logical_schema
    _, live = analyze_workload(statements, logical)
    plans = serve_plans(portfolio, statements)
    config = portfolio.configurations[0] if portfolio.configurations else None
    db = portfolio.databases[0] if portfolio.databases else None
    schema = config.schema_ if config else None
    coverage = db.coverage if db else None
    by_stmt = {stmt_id: template for template in live.templates for stmt_id in template.statement_ids}

    reports: list[dict[str, Any]] = []
    for query_id in query_ids:
        plan = plans.get(query_id) or {}
        if plan.get("sql"):
            continue
        sql = statements.get(query_id) or ""
        template = by_stmt.get(query_id)
        reasons: list[str] = []
        detail: dict[str, Any] = {"query_id": query_id, "sql": sql}

        if template is None:
            reasons.append("template_unbound")
            reports.append({**detail, "reasons": reasons})
            continue

        detail["slice_safe"] = template.slice_safe
        detail["shape"] = str(template.shape)
        if not template.slice_safe:
            reasons.append("slice_unsafe")

        if template.binding_errors:
            reasons.append("identifier_unbound")
            detail["binding_errors"] = list(template.binding_errors)

        needed = sorted(
            set(template.roles_by_attribute)
            | set(template.aggregated_attributes)
            | set(template.predicate_attributes)
            | set(template.project_attributes)
            | set(template.group_attributes)
        )
        absent = []
        unbound = []
        l_names = {
            f"{item.entity_type}.{item.name}".lower()
            for item in logical.attributes
        }
        l_names |= {item.name.lower() for item in logical.attributes}
        for name in needed:
            entity, _, attr = name.partition(".")
            if attr and entity:
                try:
                    bind_identifier(logical, entity, attr)
                except SchemaConflict:
                    unbound.append(name)
            if name.lower() not in l_names and name.split(".")[-1].lower() not in l_names:
                absent.append(name)
        if absent:
            reasons.append("absent_from_L")
            detail["absent_from_L"] = absent
        if unbound:
            reasons.append("identifier_unbound")
            detail["unbound"] = unbound

        rewrite = None
        if schema is not None:
            rewrite = rewritable(template, schema, coverage, live.requirements)
            detail["rewrite_reason"] = rewrite.reason
            if rewrite.reason.startswith("missing attributes"):
                reasons.append("absent_from_physical")
            if "coverage" in rewrite.reason or "constants outside" in rewrite.reason:
                reasons.append("coverage_rejected")
                detail["coverage"] = _coverage_detail(template, coverage)
            if rewrite.reason.startswith("missing forms") or rewrite.reason.startswith("grain"):
                reasons.append("coverage_rejected")
        if not reasons:
            reasons.append("rewrite_rejected")
        reports.append({**detail, "reasons": sorted(set(reasons)), "ok": bool(rewrite and rewrite.ok)})
    return reports


def _coverage_detail(template, coverage) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if coverage is None:
        return rows
    for slot in template.param_slots:
        ranges = coverage.attribute_ranges.get(slot.attribute) or coverage.attribute_ranges.get(
            slot.attribute.split(".")[-1]
        )
        interval = None
        if ranges is not None:
            interval = ranges.contains_constants(slot.observed_constants, op=slot.op)
        rows.append(
            {
                "attribute": slot.attribute,
                "op": slot.op,
                "constants": list(slot.observed_constants)[:8],
                "coverage_kind": None if ranges is None else ranges.kind,
                "contains": interval,
                "lookup": "interval_or_presence" if ranges is not None else "missing",
            }
        )
    return rows
