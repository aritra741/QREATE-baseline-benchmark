"""EmptyQueryDiagnosis: first SQL stage that yields zero rows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from sqlglot import exp

from quwarts.core.domain import _looks_numeric
from quwarts.core.extract import _parse
from quwarts.core.models import Workload
from quwarts.core.workload import parse_sql


CAUSE_ACTIONS = {
    "rewrite_missing": (),
    "sql_error": (),
    "base": ("reextract_attribute_slice", "compare_extractors"),
    "filter": (),
    "filter_coercion": (),
    "join": ("repair_join_vocabulary",),
    "group": ("reextract_attribute_slice",),
    "having": ("reextract_attribute_slice",),
    "empty_result": ("reextract_attribute_slice",),
}


@dataclass
class EmptyQueryDiagnosis:
    query_id: str
    cause: str
    first_zero_stage: str | None
    attributes: list[str]
    compatible_actions: tuple[str, ...]
    stages: list[dict[str, Any]] = field(default_factory=list)
    unmatched: dict[str, Any] = field(default_factory=dict)
    coercion: dict[str, Any] = field(default_factory=dict)
    predicate: str = ""
    literals: list[Any] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "cause": self.cause,
            "first_zero_stage": self.first_zero_stage,
            "attributes": list(self.attributes),
            "compatible_actions": list(self.compatible_actions),
            "stages": list(self.stages),
            "unmatched": dict(self.unmatched),
            "coercion": dict(self.coercion),
            "predicate": self.predicate,
            "literals": list(self.literals),
            "detail": self.detail,
        }


@dataclass
class FilterFailureDiagnosis:
    attribute: str
    query_ids: list[str]
    predicate: str
    literals: list[Any]
    expected_type: str
    samples: list[str]
    n_distinct: int
    n_digits: int
    n_units: int
    n_ranges: int
    n_boolean: int
    n_absence: int
    n_literal_hits: int
    has_sql_bands: bool
    shape: str
    compatible_actions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "attribute": self.attribute,
            "query_ids": list(self.query_ids),
            "predicate": self.predicate,
            "literals": list(self.literals),
            "expected_type": self.expected_type,
            "samples": list(self.samples),
            "n_distinct": self.n_distinct,
            "n_digits": self.n_digits,
            "n_units": self.n_units,
            "n_ranges": self.n_ranges,
            "n_boolean": self.n_boolean,
            "n_absence": self.n_absence,
            "n_literal_hits": self.n_literal_hits,
            "has_sql_bands": self.has_sql_bands,
            "shape": self.shape,
            "compatible_actions": list(self.compatible_actions),
        }


def diagnose_empty_query(
    query_id: str,
    sql: str | None,
    sqlite_path: str | None,
    store=None,
    workload: Workload | None = None,
) -> EmptyQueryDiagnosis:
    """Execute FROM, filters, joins, GROUP, HAVING. Name the first empty stage."""

    if not sql or not sqlite_path:
        return EmptyQueryDiagnosis(
            query_id=query_id,
            cause="rewrite_missing",
            first_zero_stage=None,
            attributes=_attrs_for(workload, [query_id]),
            compatible_actions=CAUSE_ACTIONS["rewrite_missing"],
            detail="no rewritten SQL or database",
        )
    try:
        tree = parse_sql(sql)
    except Exception as exc:
        return EmptyQueryDiagnosis(
            query_id=query_id,
            cause="sql_error",
            first_zero_stage=None,
            attributes=_attrs_for(workload, [query_id]),
            compatible_actions=CAUSE_ACTIONS["sql_error"],
            detail=str(exc),
        )
    if not isinstance(tree, exp.Select):
        return _full_only(query_id, sql, sqlite_path, workload)

    conn = sqlite3.connect(sqlite_path)
    stages: list[dict[str, Any]] = []
    cause = "empty_result"
    first_zero = None
    attributes: list[str] = []
    unmatched: dict[str, Any] = {}
    try:
        from_sql = _stage_from(tree)
        n_from = _count(conn, from_sql)
        if n_from is None:
            raise sqlite3.Error(f"from stage failed: {from_sql}")
        stages.append({"stage": "from", "n_rows": n_from, "sql": from_sql})
        if n_from == 0:
            cause = "base"
            first_zero = "from"
            attributes = _columns_in(tree, workload, joins=False, where=False)
            return _finish(query_id, cause, first_zero, attributes, stages, unmatched)

        available = _from_tables(tree)
        conjuncts = _where_conjuncts(tree)
        pending = list(conjuncts)
        applied: list = []
        filter_index = 0

        def _ready(item) -> bool:
            refs = _expr_tables(item)
            return not refs or refs <= available

        for item in list(pending):
            if not _ready(item):
                continue
            applied.append(item)
            pending.remove(item)
            prefix = _with_where(tree, applied)
            n_rows = _count(conn, prefix)
            stages.append({"stage": f"filter:{filter_index}", "n_rows": n_rows, "sql": prefix})
            if n_rows is None:
                raise sqlite3.Error(f"filter stage failed: {prefix}")
            if n_rows == 0:
                cause = "filter"
                first_zero = f"filter:{filter_index}"
                attributes = _expr_attrs(item, workload)
                return _finish(
                    query_id, cause, first_zero, attributes, stages, unmatched,
                    store=store, workload=workload,
                    predicate=item.sql(dialect="sqlite"),
                    literals=_literals(item),
                )
            filter_index += 1

        joins = list(tree.args.get("joins") or [])
        built: list = []
        for index, join in enumerate(joins):
            built.append(join)
            available |= _join_tables(join)
            prefix = _with_joins(tree, applied, built)
            n_rows = _count(conn, prefix)
            stages.append({"stage": f"join:{index}", "n_rows": n_rows, "sql": prefix})
            if n_rows is None:
                raise sqlite3.Error(f"join stage failed: {prefix}")
            if n_rows == 0:
                cause = "join"
                first_zero = f"join:{index}"
                attributes = _join_attrs(join, workload)
                prev = _with_joins(tree, applied, built[:-1]) if built[:-1] or applied else _stage_from(tree)
                unmatched = _unmatched_values(conn, join, prev)
                return _finish(
                    query_id, cause, first_zero, attributes, stages, unmatched,
                    store=store, workload=workload,
                )
            newly = [item for item in pending if _ready(item)]
            for item in newly:
                pending.remove(item)
                applied.append(item)
                prefix = _with_joins(tree, applied, built)
                n_rows = _count(conn, prefix)
                stages.append({"stage": f"filter:{filter_index}", "n_rows": n_rows, "sql": prefix})
                if n_rows is None:
                    raise sqlite3.Error(f"filter stage failed: {prefix}")
                if n_rows == 0:
                    cause = "filter"
                    first_zero = f"filter:{filter_index}"
                    attributes = _expr_attrs(item, workload)
                    return _finish(
                        query_id, cause, first_zero, attributes, stages, unmatched,
                        store=store, workload=workload,
                        predicate=item.sql(dialect="sqlite"),
                        literals=_literals(item),
                    )
                filter_index += 1

        if tree.args.get("group"):
            grouped = _with_group(tree, applied, joins)
            n_rows = _count(conn, grouped)
            stages.append({"stage": "group", "n_rows": n_rows, "sql": grouped})
            if n_rows is None:
                raise sqlite3.Error(f"group stage failed: {grouped}")
            if n_rows == 0:
                cause = "group"
                first_zero = "group"
                attributes = _columns_in(tree, workload, group=True)
                return _finish(query_id, cause, first_zero, attributes, stages, unmatched)

        if tree.args.get("having"):
            having = sql
            n_rows = _count(conn, having)
            stages.append({"stage": "having", "n_rows": n_rows, "sql": having})
            if n_rows is None:
                raise sqlite3.Error(f"having stage failed: {having}")
            if n_rows == 0:
                cause = "having"
                first_zero = "having"
                attributes = _columns_in(tree, workload, having=True)
                return _finish(query_id, cause, first_zero, attributes, stages, unmatched)

        n_full = _count(conn, sql)
        stages.append({"stage": "full", "n_rows": n_full, "sql": sql})
        if n_full is None:
            raise sqlite3.Error(f"full stage failed: {sql}")
        if n_full == 0:
            first_zero = "full"
            attributes = _attrs_for(workload, [query_id])
    except sqlite3.Error as exc:
        return EmptyQueryDiagnosis(
            query_id=query_id,
            cause="sql_error",
            first_zero_stage=None,
            attributes=_attrs_for(workload, [query_id]),
            compatible_actions=CAUSE_ACTIONS["sql_error"],
            stages=stages,
            detail=str(exc),
        )
    finally:
        conn.close()
    return _finish(query_id, cause, first_zero, attributes, stages, unmatched, store=store, workload=workload)


def diagnose_empty_queries(
    query_ids: list[str],
    statements: dict[str, str],
    plans: dict[str, dict[str, str | None]],
    store=None,
    workload: Workload | None = None,
) -> list[EmptyQueryDiagnosis]:
    found: list[EmptyQueryDiagnosis] = []
    for query_id in query_ids:
        plan = plans.get(query_id) or {}
        found.append(
            diagnose_empty_query(
                query_id,
                plan.get("sql"),
                plan.get("sqlite_path"),
                store=store,
                workload=workload,
            )
        )
    return found


def inspect_coercion(store, workload: Workload, names: list[str] | None = None) -> dict[str, Any]:
    """Look at raw surfaces and parse results before any re-extract."""

    wanted = {_bare(name) for name in (names or [])}
    reparse: list[dict[str, Any]] = []
    reextract: list[tuple[str, str]] = []
    skip: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    for record in store.records.values():
        if record.null_reason != "dtype_coercion":
            continue
        if wanted and _bare(record.attribute) not in wanted and record.attribute not in (names or []):
            continue
        req = workload.requirements.get(record.attribute)
        dtype = req.dtype if req is not None else "unknown"
        surface = record.surface_value
        parsed = _parse(str(surface)) if surface not in (None, "") else None
        looks = bool(surface) and _looks_numeric(str(surface))
        cell = {
            "doc_id": record.doc_id,
            "attribute": record.attribute,
            "surface": surface,
            "dtype": dtype,
            "parsed": parsed,
            "looks_numeric": looks,
        }
        cells.append(cell)
        if dtype == "numeric" and looks and isinstance(parsed, (int, float)):
            reparse.append(cell)
        elif dtype == "numeric" and not looks:
            skip.append(cell)
        elif surface not in (None, ""):
            reextract.append((record.doc_id, record.attribute))
        else:
            skip.append(cell)
    return {
        "n": len(cells),
        "reparse": reparse,
        "reextract": reextract,
        "skip": skip,
        "cells": cells[:40],
    }


def apply_coercion_reparse(store, inspection: dict[str, Any]) -> int:
    changed = 0
    by_key = {(row["doc_id"], row["attribute"]): row for row in inspection.get("reparse") or []}
    if not by_key:
        return 0
    for record in list(store.records.values()):
        hit = by_key.get((record.doc_id, record.attribute))
        if hit is None:
            continue
        record.parsed_value = hit["parsed"]
        record.null_reason = None
        store.put(record)
        changed += 1
    return changed


def _literals(node) -> list[Any]:
    found: list[Any] = []
    for lit in node.find_all(exp.Literal):
        raw = lit.this
        if lit.is_number:
            try:
                found.append(int(raw) if "." not in str(raw) else float(raw))
                continue
            except (TypeError, ValueError):
                pass
        if raw is not None:
            found.append(raw)
    return found


def diagnose_filter_failure(
    attribute: str,
    query_ids: list[str],
    predicate: str,
    literals: list[Any],
    store,
    workload: Workload | None = None,
) -> FilterFailureDiagnosis:
    """Shape of a filter-zero column. Representation, not extraction."""

    from quwarts.core.repair.represent import _ABSENCE, _BOOLEAN, _RANGE, _UNIT

    surfaces = _column_surfaces(store, attribute)
    distinct = sorted(surfaces, key=lambda item: item.lower())
    n_digits = sum(1 for item in distinct if any(ch.isdigit() for ch in item))
    n_units = sum(1 for item in distinct if _UNIT.search(item))
    n_ranges = sum(1 for item in distinct if _RANGE.search(item))
    n_boolean = sum(1 for item in distinct if item.strip().lower() in _BOOLEAN)
    n_absence = sum(
        1 for item in distinct if " ".join(item.strip().lower().split()) in _ABSENCE
    )
    folded_lits = {_fold_lit(item) for item in literals}
    n_literal_hits = sum(1 for item in distinct if _literal_in_surface(item, folded_lits, literals))
    expected = _expected_type(literals, workload, attribute)
    has_bands = any(band.get("value") is not None for band in _sql_bands(workload, attribute))
    shape, actions = _filter_shape(
        expected, n_digits, n_units, n_ranges, n_boolean, n_absence,
        n_literal_hits, len(distinct), has_bands, predicate,
    )
    return FilterFailureDiagnosis(
        attribute=attribute,
        query_ids=list(query_ids),
        predicate=predicate,
        literals=list(literals),
        expected_type=expected,
        samples=distinct[:20],
        n_distinct=len(distinct),
        n_digits=n_digits,
        n_units=n_units,
        n_ranges=n_ranges,
        n_boolean=n_boolean,
        n_absence=n_absence,
        n_literal_hits=n_literal_hits,
        has_sql_bands=has_bands,
        shape=shape,
        compatible_actions=actions,
    )


def diagnose_filter_failures(
    diagnoses: list[EmptyQueryDiagnosis],
    store,
    workload: Workload | None = None,
) -> list[FilterFailureDiagnosis]:
    grouped: dict[str, list[EmptyQueryDiagnosis]] = {}
    for item in diagnoses:
        if item.cause not in {"filter", "filter_coercion"}:
            continue
        for name in item.attributes or ["?"]:
            grouped.setdefault(name, []).append(item)
    reports: list[FilterFailureDiagnosis] = []
    for name, rows in grouped.items():
        literals: list[Any] = []
        for row in rows:
            for value in row.literals:
                if value not in literals:
                    literals.append(value)
        reports.append(
            diagnose_filter_failure(
                name,
                [row.query_id for row in rows],
                rows[0].predicate,
                literals,
                store,
                workload,
            )
        )
    reports.sort(key=lambda row: (-len(row.query_ids), -row.n_distinct, row.attribute))
    return reports


def issues_from_filter_failures(
    reports: list[FilterFailureDiagnosis],
    workload: Workload | None = None,
) -> list[Any]:
    from quwarts.core.repair.models import RepairIssue

    issues: list[RepairIssue] = []
    for report in reports:
        kind = "infeasible_representation" if report.shape == "infeasible" else "empty_query"
        issues.append(
            RepairIssue(
                kind=kind,
                attributes=[report.attribute],
                query_ids=list(report.query_ids),
                severity=min(1.0, len(report.query_ids) / 10.0),
                detail={
                    "cause": "filter",
                    "shape": report.shape,
                    "compatible_actions": list(report.compatible_actions),
                    "literals": list(report.literals),
                    "predicate": report.predicate,
                    "filter_diagnosis": report.as_dict(),
                    "sql_bands": _sql_bands(workload, report.attribute),
                },
            )
        )
    return issues


def _column_surfaces(store, attribute: str) -> set[str]:
    found: set[str] = set()
    if store is None:
        return found
    bare = attribute.split(".")[-1].lower()
    for record in store.records.values():
        if record.attribute != attribute and record.attribute.split(".")[-1].lower() != bare:
            continue
        if record.surface_value in (None, ""):
            continue
        found.add(str(record.surface_value).strip())
    return found


def _expected_type(literals: list[Any], workload: Workload | None, attribute: str) -> str:
    if workload is not None:
        req = workload.requirements.get(attribute)
        if req is None:
            for key, item in workload.requirements.items():
                if key.split(".")[-1] == attribute.split(".")[-1]:
                    req = item
                    break
        declared = (req.dtype if req is not None else "") or ""
        if attribute in (workload.literal_types or {}) or attribute.split(".")[-1] in (workload.literal_types or {}):
            return workload.literal_types.get(attribute) or workload.literal_types.get(attribute.split(".")[-1], declared)
        if declared and declared != "unknown":
            return declared
    if literals and all(_looks_numeric(str(item)) for item in literals if item not in (None, "")):
        return "numeric"
    if literals:
        return "string"
    return "unknown"


def _sql_bands(workload: Workload | None, attribute: str) -> list[dict[str, Any]]:
    if workload is None:
        return []
    bare = attribute.split(".")[-1].lower()
    bands: list[dict[str, Any]] = []
    for template in workload.templates:
        sql = template.raw_sql or template.canonical_sql
        if not sql or "case" not in sql.lower():
            continue
        try:
            tree = parse_sql(sql)
        except Exception:
            continue
        for case in tree.find_all(exp.Case):
            for pair in case.args.get("ifs") or []:
                pred = pair.this
                then = pair.args.get("true")
                cols = [col.name.lower() for col in pred.find_all(exp.Column) if col.name]
                if bare not in cols:
                    continue
                label = then.name if isinstance(then, exp.Literal) else (then.sql(dialect="sqlite") if then is not None else "")
                value = None
                for lit in pred.find_all(exp.Literal):
                    if lit.is_number:
                        try:
                            value = float(lit.this) if "." in str(lit.this) else int(lit.this)
                        except (TypeError, ValueError):
                            value = None
                if label:
                    bands.append({"label": str(label), "value": value})
    return bands


def _filter_shape(
    expected: str,
    n_digits: int,
    n_units: int,
    n_ranges: int,
    n_boolean: int,
    n_absence: int,
    n_literal_hits: int,
    n_distinct: int,
    has_bands: bool,
    predicate: str = "",
) -> tuple[str, tuple[str, ...]]:
    actions: list[str] = []
    if n_units:
        actions.append("extract_unit_and_magnitude")
    if n_boolean:
        actions.append("map_boolean_encoding")
    if n_ranges:
        actions.append("parse_range_to_bounds")
    if n_absence:
        actions.append("mark_absence_as_null")
    if has_bands:
        actions.append("map_category_to_numeric_band")
    if n_units and n_units >= max(n_boolean, n_ranges, n_absence):
        shape = "unit"
    elif n_boolean and n_boolean >= max(n_units, n_ranges, n_absence):
        shape = "boolean"
    elif n_ranges and n_ranges >= max(n_units, n_boolean, n_absence):
        shape = "range"
    elif n_absence and n_absence >= max(n_units, n_boolean, n_ranges, 1):
        shape = "absence"
    elif has_bands:
        shape = "category"
    elif expected == "numeric" and n_digits == 0 and n_literal_hits == 0:
        shape = "infeasible"
        actions = ["infeasible_representation"]
    elif not actions and n_literal_hits == 0:
        shape = "infeasible"
        actions = ["infeasible_representation"]
    else:
        shape = "mixed"
    if not actions:
        if n_distinct > 0 and _nonempty_predicate(predicate):
            return "empty_materialization", ()
        actions = ["infeasible_representation"]
        shape = "infeasible"
    return shape, tuple(actions)


def _nonempty_predicate(predicate: str) -> bool:
    text = " ".join(predicate.lower().split())
    return "<> ''" in text or "<> \"\"" in text or "is not null" in text


def _fold_lit(value: Any) -> str:
    return str(value).strip().lower()


def _literal_in_surface(surface: str, folded_lits: set[str], literals: list[Any]) -> bool:
    folded = surface.strip().lower()
    if folded in folded_lits:
        return True
    for lit in literals:
        text = _fold_lit(lit)
        if not text or text in {"0", "1"} or _looks_numeric(text):
            continue
        if text in folded:
            return True
    return False


def group_diagnoses(
    diagnoses: list[EmptyQueryDiagnosis],
    workload: Workload,
) -> list[Any]:
    """One RepairIssue per first-empty cause."""

    from quwarts.core.repair.models import RepairIssue

    grouped: dict[str, list[EmptyQueryDiagnosis]] = {}
    for item in diagnoses:
        if item.cause in {"filter", "filter_coercion"}:
            continue
        grouped.setdefault(item.cause, []).append(item)
    issues: list[RepairIssue] = []
    for cause, rows in grouped.items():
        names: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for name in row.attributes:
                if name not in seen:
                    seen.add(name)
                    names.append(name)
        unmatched = {}
        for row in rows:
            if row.unmatched:
                unmatched = row.unmatched
                break
        issues.append(
            RepairIssue(
                kind="empty_query",
                attributes=names or _attrs_for(workload, [row.query_id for row in rows]),
                query_ids=[row.query_id for row in rows],
                severity=min(1.0, len(rows) / max(len(diagnoses), 1)),
                detail={
                    "cause": cause,
                    "count": len(rows),
                    "compatible_actions": list(CAUSE_ACTIONS.get(cause, ())),
                    "unmatched": unmatched,
                    "diagnoses": [row.as_dict() for row in rows[:8]],
                },
            )
        )
    return issues


def _finish(
    query_id: str,
    cause: str,
    first_zero: str | None,
    attributes: list[str],
    stages: list[dict[str, Any]],
    unmatched: dict[str, Any],
    store=None,
    workload: Workload | None = None,
    predicate: str = "",
    literals: list[Any] | None = None,
) -> EmptyQueryDiagnosis:
    resolved = cause
    coercion: dict[str, Any] = {}
    if cause == "filter" and store is not None and workload is not None:
        coercion = inspect_coercion(store, workload, attributes)
        if coercion.get("n"):
            resolved = "filter_coercion"
    return EmptyQueryDiagnosis(
        query_id=query_id,
        cause=resolved,
        first_zero_stage=first_zero,
        attributes=attributes,
        compatible_actions=CAUSE_ACTIONS.get(resolved, ()),
        stages=stages,
        unmatched=unmatched,
        coercion=coercion,
        predicate=predicate,
        literals=list(literals or []),
    )


def _full_only(query_id: str, sql: str, sqlite_path: str, workload) -> EmptyQueryDiagnosis:
    conn = sqlite3.connect(sqlite_path)
    try:
        n_rows = _count(conn, sql)
    finally:
        conn.close()
    cause = "empty_result" if n_rows == 0 else "empty_result"
    return EmptyQueryDiagnosis(
        query_id=query_id,
        cause=cause,
        first_zero_stage="full",
        attributes=_attrs_for(workload, [query_id]),
        compatible_actions=CAUSE_ACTIONS[cause],
        stages=[{"stage": "full", "n_rows": n_rows, "sql": sql}],
    )


def _star(tree: exp.Select) -> exp.Select:
    clone = tree.copy()
    clone.set("expressions", [exp.Star()])
    clone.set("group", None)
    clone.set("having", None)
    clone.set("order", None)
    clone.set("limit", None)
    clone.set("distinct", None)
    return clone


def _stage_from(tree: exp.Select) -> str:
    clone = _star(tree)
    clone.set("joins", None)
    clone.set("where", None)
    return clone.sql(dialect="sqlite")


def _where_conjuncts(tree: exp.Select) -> list:
    where = tree.args.get("where")
    if where is None:
        return []
    node = where.this
    if isinstance(node, exp.And):
        return list(node.flatten())
    return [node]


def _with_where(tree: exp.Select, conjuncts: list) -> str:
    clone = _star(tree)
    clone.set("joins", None)
    if conjuncts:
        clone.set("where", exp.Where(this=exp.and_(*[item.copy() for item in conjuncts])))
    else:
        clone.set("where", None)
    return clone.sql(dialect="sqlite")


def _with_joins(tree: exp.Select, conjuncts: list, joins: list) -> str:
    clone = _star(tree)
    clone.set("joins", [item.copy() for item in joins])
    if conjuncts:
        clone.set("where", exp.Where(this=exp.and_(*[item.copy() for item in conjuncts])))
    else:
        clone.set("where", None)
    return clone.sql(dialect="sqlite")


def _with_group(tree: exp.Select, conjuncts: list, joins: list) -> str:
    clone = _star(tree)
    clone.set("joins", [item.copy() for item in joins] if joins else None)
    if conjuncts:
        clone.set("where", exp.Where(this=exp.and_(*[item.copy() for item in conjuncts])))
    else:
        clone.set("where", None)
    clone.set("group", tree.args.get("group").copy() if tree.args.get("group") else None)
    return clone.sql(dialect="sqlite")


def _from_tables(tree: exp.Select) -> set[str]:
    found: set[str] = set()
    frm = tree.args.get("from_") or tree.args.get("from")
    if frm is None:
        return found
    for table in frm.find_all(exp.Table):
        found.add((table.alias_or_name or table.name or "").lower())
    return {name for name in found if name}


def _expr_tables(node) -> set[str]:
    return {
        (col.table or "").lower()
        for col in node.find_all(exp.Column)
        if col.table
    }


def _join_tables(join) -> set[str]:
    found: set[str] = set()
    this = join.this
    if this is not None:
        for table in this.find_all(exp.Table):
            found.add((table.alias_or_name or table.name or "").lower())
    return {name for name in found if name}


def _count(conn, sql: str) -> int | None:
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM ({sql})").fetchone()
    except sqlite3.Error:
        return None
    return int(row[0] or 0) if row else 0


def _distinct(conn, sql: str) -> list[str]:
    try:
        rows = conn.execute(sql).fetchall()
    except sqlite3.Error:
        return []
    values = []
    seen: set[str] = set()
    for row in rows:
        text = "" if row[0] is None else str(row[0]).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values


def _join_eq(join) -> tuple[str, str] | None:
    on = join.args.get("on")
    if on is None:
        return None
    eq = on if isinstance(on, exp.EQ) else None
    if eq is None and isinstance(on, exp.And):
        eqs = [item for item in on.flatten() if isinstance(item, exp.EQ)]
        eq = eqs[0] if eqs else None
    if eq is None:
        return None
    return eq.left.sql(dialect="sqlite"), eq.right.sql(dialect="sqlite")


def _unmatched_values(conn, join, prefix_sql: str) -> dict[str, Any]:
    pair = _join_eq(join)
    if pair is None:
        return {}
    left_expr, right_expr = pair
    left_vals = _distinct(conn, f"SELECT DISTINCT {left_expr} FROM ({prefix_sql})")
    if not left_vals:
        left_vals = _distinct(conn, f"SELECT DISTINCT {_bare_sql(left_expr)} FROM ({prefix_sql})")
    right_table = None
    right_alias = None
    if isinstance(join.this, exp.Table):
        right_table = join.this.name
        right_alias = join.this.alias
    right_vals: list[str] = []
    if right_table:
        quoted = f'"{right_table}"'
        if right_alias:
            quoted = f'{quoted} AS {right_alias}'
        right_vals = _distinct(conn, f"SELECT DISTINCT {right_expr} FROM {quoted}")
    left_fold = {_fold(item) for item in left_vals}
    right_fold = {_fold(item) for item in right_vals}
    left_unmatched = [item for item in left_vals if _fold(item) not in right_fold]
    right_unmatched = [item for item in right_vals if _fold(item) not in left_fold]
    return {
        "left_expr": left_expr,
        "right_expr": right_expr,
        "left_values": left_vals[:80],
        "right_values": right_vals[:80],
        "left_unmatched": left_unmatched[:80],
        "right_unmatched": right_unmatched[:80],
        "n_left": len(left_vals),
        "n_right": len(right_vals),
        "n_left_unmatched": len(left_unmatched),
        "n_right_unmatched": len(right_unmatched),
    }


def _bare_sql(expr: str) -> str:
    text = expr.strip()
    if "." in text and "(" not in text:
        return text.split(".")[-1]
    return text


def _fold(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _bare(name: str) -> str:
    text = name.split(".")[-1].lower()
    if text.endswith("__canonical"):
        text = text[: -len("__canonical")]
    if text.endswith("__surface"):
        text = text[: -len("__surface")]
    return text


def _map_name(name: str, workload: Workload | None) -> str:
    bare = _bare(name)
    if workload is None:
        return bare
    for key in workload.requirements:
        if key.lower() == name.lower() or key.split(".")[-1].lower() == bare:
            return key
    return bare


def _expr_attrs(node, workload: Workload | None) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for col in node.find_all(exp.Column):
        mapped = _map_name((col.table + "." + col.name) if col.table else col.name, workload)
        if mapped not in seen:
            seen.add(mapped)
            names.append(mapped)
    return names


def _join_attrs(join, workload: Workload | None) -> list[str]:
    on = join.args.get("on")
    if on is None:
        return []
    return _expr_attrs(on, workload)


def _columns_in(
    tree: exp.Select,
    workload: Workload | None,
    *,
    joins: bool = True,
    where: bool = True,
    group: bool = False,
    having: bool = False,
) -> list[str]:
    nodes = []
    if where and tree.args.get("where"):
        nodes.append(tree.args["where"])
    if joins:
        for join in tree.args.get("joins") or []:
            if join.args.get("on") is not None:
                nodes.append(join.args["on"])
    if group and tree.args.get("group"):
        nodes.append(tree.args["group"])
    if having and tree.args.get("having"):
        nodes.append(tree.args["having"])
    names: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        for name in _expr_attrs(node, workload):
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _attrs_for(workload: Workload | None, query_ids: list[str]) -> list[str]:
    if workload is None:
        return []
    wanted = set(query_ids)
    names: list[str] = []
    seen: set[str] = set()
    for template in workload.templates:
        if not (wanted & set(template.statement_ids) or template.id in wanted):
            continue
        for name in (
            *template.roles_by_attribute,
            *template.aggregated_attributes,
            *template.predicate_attributes,
        ):
            if name not in seen:
                seen.add(name)
                names.append(name)
        for left, right in template.join_pairs:
            for name in (left, right):
                if name not in seen:
                    seen.add(name)
                    names.append(name)
    return names or list(workload.requirements)
