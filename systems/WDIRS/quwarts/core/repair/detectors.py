"""Compile-time detectors. No gold, no official_query_error."""

from __future__ import annotations

import sqlite3
from quwarts.core.domain import disjoint_attributes
from quwarts.core.models import FrozenPortfolio, Workload
from quwarts.core.population import apply_population
from quwarts.core.repair.models import DetectorSnapshot, RepairIssue
from quwarts.core.rewrite import join_yield


HIGH_NULL = 0.5


def _plans_for(portfolio: FrozenPortfolio, statements: dict[str, str]) -> dict[str, dict[str, str | None]]:
    from quwarts.core.pipeline import serve_plans

    return serve_plans(portfolio, statements)


def detect_empty_queries(
    portfolio: FrozenPortfolio,
    statements: dict[str, str],
    plans: dict[str, dict[str, str | None]] | None = None,
) -> list[str]:
    plans = plans or _plans_for(portfolio, statements)
    empty: list[str] = []
    for stmt_id, sql in statements.items():
        plan = plans.get(stmt_id) or {}
        rewritten = plan.get("sql")
        path = plan.get("sqlite_path")
        if not rewritten or not path:
            empty.append(stmt_id)
            continue
        try:
            conn = sqlite3.connect(path)
            try:
                rows = conn.execute(rewritten).fetchall()
            finally:
                conn.close()
        except sqlite3.Error:
            empty.append(stmt_id)
            continue
        if not rows:
            empty.append(stmt_id)
    return empty


def detect_join_yields(
    portfolio: FrozenPortfolio,
    statements: dict[str, str],
    plans: dict[str, dict[str, str | None]] | None = None,
) -> dict[str, float]:
    plans = plans or _plans_for(portfolio, statements)
    scores: dict[str, float] = {}
    for stmt_id, plan in plans.items():
        sql = plan.get("sql")
        path = plan.get("sqlite_path")
        if not sql or not path:
            continue
        scores[stmt_id] = join_yield(sql, path)
    return scores


def detect_coercion(store) -> int:
    return sum(
        1
        for record in store.records.values()
        if record.null_reason == "dtype_coercion"
    )


def detect_high_null(store, workload: Workload) -> dict[str, float]:
    counts: dict[str, list[int]] = {name: [0, 0] for name in workload.requirements}
    for record in store.records.values():
        bucket = counts.get(record.attribute)
        if bucket is None:
            continue
        bucket[1] += 1
        if record.surface_value in (None, ""):
            bucket[0] += 1
    return {
        name: empty / total
        for name, (empty, total) in counts.items()
        if total and empty / total >= HIGH_NULL
    }


def detect_domain(store, workload: Workload, portfolio: FrozenPortfolio) -> list[str]:
    if not portfolio.configurations:
        return []
    rows = apply_population(list(store.records.values()), portfolio.configurations[0], workload)
    return disjoint_attributes(rows, workload)


def detect_coverage(workload: Workload, store) -> list[str]:
    present = {record.attribute for record in store.records.values() if record.surface_value not in (None, "")}
    missing = []
    for name in workload.requirements:
        if name in present or name.split(".")[-1] in {item.split(".")[-1] for item in present}:
            continue
        missing.append(name)
    return missing


def detect_provenance(store) -> int:
    return sum(
        1
        for record in store.records.values()
        if record.surface_value not in (None, "") and record.span is None
    )


def detect_constraints(store) -> int:
    return sum(
        1
        for record in store.records.values()
        if (record.candidate_keys or {}).get("constrained") == "other"
        or record.null_reason in {"ungrounded", "constraint"}
    )


def snapshot(
    store,
    workload: Workload,
    portfolio: FrozenPortfolio,
    statements: dict[str, str],
    plans: dict[str, dict[str, str | None]] | None = None,
) -> DetectorSnapshot:
    plans = plans or _plans_for(portfolio, statements)
    return DetectorSnapshot(
        empty_query_ids=detect_empty_queries(portfolio, statements, plans),
        join_yield=detect_join_yields(portfolio, statements, plans),
        coercion_count=detect_coercion(store),
        high_null=detect_high_null(store, workload),
        domain_disjoint=detect_domain(store, workload, portfolio),
        coverage_gaps=detect_coverage(workload, store),
        provenance_gaps=detect_provenance(store),
        constraint_failures=detect_constraints(store),
    )


def issues_from_snapshot(
    snap: DetectorSnapshot,
    workload: Workload,
    statements: dict[str, str],
) -> list[RepairIssue]:
    issues: list[RepairIssue] = []
    if snap.empty_query_ids:
        attrs = _attrs_for_queries(workload, snap.empty_query_ids)
        issues.append(
            RepairIssue(
                kind="empty_query",
                attributes=attrs,
                query_ids=list(snap.empty_query_ids),
                severity=min(1.0, len(snap.empty_query_ids) / max(len(statements), 1)),
                detail={"count": len(snap.empty_query_ids)},
            )
        )
    for stmt_id, score in snap.join_yield.items():
        if score > 0:
            continue
        issues.append(
            RepairIssue(
                kind="join_yield",
                attributes=_attrs_for_queries(workload, [stmt_id]),
                query_ids=[stmt_id],
                severity=1.0,
                detail={"yield": score},
            )
        )
    if snap.coercion_count:
        issues.append(
            RepairIssue(
                kind="dtype_coercion",
                attributes=_coerced_attrs(workload),
                query_ids=[],
                severity=min(1.0, snap.coercion_count / 20.0),
                detail={"count": snap.coercion_count},
            )
        )
    if snap.domain_disjoint:
        issues.append(
            RepairIssue(
                kind="domain",
                attributes=list(snap.domain_disjoint),
                query_ids=[],
                severity=0.8,
            )
        )
    if snap.coverage_gaps:
        issues.append(
            RepairIssue(
                kind="coverage",
                attributes=list(snap.coverage_gaps),
                query_ids=[],
                severity=0.7,
            )
        )
    if snap.provenance_gaps:
        issues.append(
            RepairIssue(
                kind="provenance",
                attributes=list(workload.requirements),
                query_ids=[],
                severity=min(1.0, snap.provenance_gaps / 50.0),
                detail={"count": snap.provenance_gaps},
            )
        )
    if snap.constraint_failures:
        issues.append(
            RepairIssue(
                kind="constraint",
                attributes=list(workload.requirements),
                query_ids=[],
                severity=min(1.0, snap.constraint_failures / 20.0),
                detail={"count": snap.constraint_failures},
            )
        )
    if snap.high_null:
        issues.append(
            RepairIssue(
                kind="high_null",
                attributes=list(snap.high_null),
                query_ids=[],
                severity=max(snap.high_null.values()),
                detail={"rates": dict(snap.high_null)},
            )
        )
    return issues


def _attrs_for_queries(workload: Workload, query_ids: list[str]) -> list[str]:
    names: set[str] = set()
    wanted = set(query_ids)
    for template in workload.templates:
        if wanted & set(template.statement_ids) or template.id in wanted:
            names.update(template.roles_by_attribute)
            names.update(template.aggregated_attributes)
            names.update(template.predicate_attributes)
            for left, right in template.join_pairs:
                names.add(left)
                names.add(right)
    return sorted(names) or list(workload.requirements)


def _coerced_attrs(workload: Workload) -> list[str]:
    return list(workload.requirements)


def proxy_score(snap: DetectorSnapshot) -> float:
    """Gold-free improvement signal. Lower is worse."""

    empty = len(snap.empty_query_ids)
    zero_join = sum(1 for score in snap.join_yield.values() if score <= 0)
    return -(
        empty
        + zero_join
        + 0.05 * snap.coercion_count
        + 0.1 * len(snap.coverage_gaps)
        + 0.1 * len(snap.domain_disjoint)
        + 0.02 * snap.provenance_gaps
        + 0.05 * snap.constraint_failures
        + sum(snap.high_null.values())
    )
