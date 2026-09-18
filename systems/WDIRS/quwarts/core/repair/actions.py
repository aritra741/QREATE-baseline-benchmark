"""Repair tools. Compiler plan stays frozen; these retarget extract and ER."""

from __future__ import annotations

from typing import Any

from quwarts.core.domain import apply_domain
from quwarts.core.extract import StagedExtractor, validate_cell
from quwarts.core.ledger import BudgetExhausted
from quwarts.core.models import PreprocessPolicy, SourceDocument, Workload
from quwarts.core.quality import multi_route, span_adjudicate
from quwarts.core.repair.diagnose import apply_coercion_reparse, inspect_coercion
from quwarts.core.repair.er import align_unmatched, resolve_shared_ids, stamp_shared_ids
from quwarts.core.repair.represent import (
    extract_unit_and_magnitude,
    map_boolean_encoding,
    map_category_to_numeric_band,
    mark_absence_as_null,
    parse_range_to_bounds,
)
from quwarts.core.repair.models import Repair


# These rewrite evidence in place. They never call the model.
_NO_TOKEN_ACTIONS = frozenset({
    "extract_unit_and_magnitude",
    "map_boolean_encoding",
    "parse_range_to_bounds",
    "map_category_to_numeric_band",
    "mark_absence_as_null",
    "normalize_to_declared_domain",
    "infeasible_representation",
})


def mean_observed_tokens(ledger, attributes: list[str] | None = None, purposes: tuple[str, ...] = ("extract",)) -> int:
    """Average tokens actually spent for these attributes. 0 if the ledger has no such spend."""

    if ledger is None:
        return 0
    keep = {name.lower() for name in (attributes or [])}
    keep |= {name.split(".")[-1].lower() for name in keep}
    rows: list[int] = []
    for record in getattr(ledger, "records", []) or []:
        if record.purpose not in purposes:
            continue
        if keep:
            meta = record.metadata or {}
            names = {str(meta.get("attribute") or "").lower()}
            extra = meta.get("attributes") or []
            if isinstance(extra, str):
                extra = [extra]
            names.update(str(item).lower() for item in extra)
            names.update(str(item).split(".")[-1].lower() for item in list(names))
            if not (names & keep):
                continue
        rows.append(int(record.tokens))
    if not rows:
        return 0
    return max(1, int(round(sum(rows) / len(rows))))


def estimate_cost(action: str, n_targets: int, ledger=None, attributes: list[str] | None = None) -> int:
    """Cost is observed spend × work units. Local repairs are 0."""

    work = max(int(n_targets), 1)
    if action in _NO_TOKEN_ACTIONS:
        return 0
    purposes = ("extract",)
    if action == "repair_join_vocabulary":
        purposes = ("identity_map", "extract")
    per = mean_observed_tokens(ledger, attributes, purposes)
    if per == 0:
        return work
    return per * work


def propose(issue, store, ledger=None) -> list[Repair]:
    names = issue.attributes or []
    n = max(len(names), 1)
    allowed = issue.detail.get("compatible_actions", None)
    if issue.kind == "dtype_coercion":
        action = "reextract_failed_cells"
    elif issue.kind == "join_yield":
        action = "repair_join_vocabulary"
    elif issue.kind == "domain":
        action = "normalize_to_declared_domain"
    elif issue.kind == "provenance":
        action = "adjudicate_disagreement"
    elif issue.kind == "infeasible_representation":
        action = "infeasible_representation"
    elif issue.kind in {"empty_query", "coverage", "high_null"}:
        action = "reextract_attribute_slice"
    else:
        action = "compare_extractors"
    extras: list[Repair] = []
    if allowed is None:
        if issue.kind == "high_null" and n:
            extras.append(
                Repair(
                    action="compare_extractors",
                    issue=issue,
                    estimated_cost=estimate_cost("compare_extractors", n, ledger, names),
                    priority=0.0,
                    params={"attributes": names},
                )
            )
        chosen = [action, *(item.action for item in extras)]
    else:
        chosen = [item for item in allowed if item]
        extras = []
    repairs = []
    for name in chosen:
        repairs.append(
            Repair(
                action=name,
                issue=issue,
                estimated_cost=estimate_cost(name, n, ledger, names),
                priority=0.0,
                params={
                    "attributes": names,
                    "unmatched": issue.detail.get("unmatched") or {},
                    "cause": issue.detail.get("cause"),
                    "literals": issue.detail.get("literals") or [],
                    "sql_bands": issue.detail.get("sql_bands") or [],
                    "query_ids": list(issue.query_ids),
                },
            )
        )
    return repairs


def eligible_repairs(issues, store, blocked: set[str] | None = None, ledger=None) -> list[Repair]:
    blocked = blocked or set()
    found: list[Repair] = []
    for issue in issues:
        allowed = issue.detail.get("compatible_actions", None)
        for repair in propose(issue, store, ledger):
            if repair.action in blocked:
                continue
            if allowed is not None and repair.action not in allowed:
                continue
            found.append(repair)
    return found


def execute(
    repair: Repair,
    *,
    extractor: StagedExtractor,
    documents: list[SourceDocument],
    workload: Workload,
    policy: PreprocessPolicy,
    tiers: dict[str, str],
    logical=None,
    identity_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action = repair.action
    names = list(repair.params.get("attributes") or repair.issue.attributes)
    try:
        if action == "reextract_failed_cells":
            inspection = inspect_coercion(extractor.store, workload, names)
            n_reparse = apply_coercion_reparse(extractor.store, inspection)
            only = list(inspection.get("reextract") or [])
            n = 0
            if only:
                n = extractor.reextract_coerced(
                    documents, workload, policy, tiers, logical=logical, only=only,
                )
            return {
                "action": action,
                "n": n,
                "reparse": n_reparse,
                "skipped": len(inspection.get("skip") or []),
                "inspection": {
                    "n": inspection.get("n"),
                    "n_reparse": n_reparse,
                    "n_reextract": len(only),
                    "n_skip": len(inspection.get("skip") or []),
                },
                "bugfix": True,
            }
        if action == "reextract_attribute_slice":
            extractor.extract_attributes(
                documents, names, {name: "expensive" for name in names},
                stage=3, workload=workload, logical=logical,
            )
            return {"action": action, "n": len(names)}
        if action == "normalize_to_declared_domain":
            return _normalize_domain(extractor, workload, names)
        if action == "repair_join_vocabulary":
            unmatched = repair.params.get("unmatched") or {}
            shared = resolve_shared_ids(list(extractor.store.records.values()), workload, extractor.caller)
            aligned = align_unmatched(
                list(unmatched.get("left_unmatched") or []),
                list(unmatched.get("right_values") or unmatched.get("right_unmatched") or []),
                extractor.caller,
                label="+".join(names[:4]) or "join",
            )
            if aligned:
                maps = shared.setdefault("maps", {})
                for attr in names:
                    current = dict(maps.get(attr) or {})
                    current.update(aligned)
                    maps[attr] = current
                    maps[attr.split(".")[-1]] = current
                shared.setdefault("linkage", {}).update(aligned)
            if identity_report is not None:
                identity_report.clear()
                identity_report.update(stamp_shared_ids({}, shared))
            return {
                "action": action,
                "n_ids": (identity_report or {}).get("shared_er", {}).get("n_ids", 0),
                "n_aligned": len(aligned),
                "unmatched": {
                    "n_left_unmatched": unmatched.get("n_left_unmatched"),
                    "n_right_unmatched": unmatched.get("n_right_unmatched"),
                },
            }
        if action == "compare_extractors":
            vote = multi_route(
                extractor, documents, _subset(workload, names), tiers,
            )
            return {"action": action, "vote": {key: vote.get(key) for key in ("routes", "disagreements") if key in vote}}
        if action == "extract_unit_and_magnitude":
            return extract_unit_and_magnitude(extractor.store, names)
        if action == "map_boolean_encoding":
            return map_boolean_encoding(extractor.store, names, repair.params.get("literals"))
        if action == "parse_range_to_bounds":
            return parse_range_to_bounds(extractor.store, names)
        if action == "map_category_to_numeric_band":
            return map_category_to_numeric_band(extractor.store, names, repair.params.get("sql_bands"))
        if action == "mark_absence_as_null":
            return mark_absence_as_null(extractor.store, names)
        if action == "infeasible_representation":
            return {
                "action": action,
                "n": len(repair.params.get("query_ids") or repair.issue.query_ids),
                "query_ids": list(repair.params.get("query_ids") or repair.issue.query_ids),
                "attribute": names[0] if names else None,
                "infeasible": True,
            }
        if action == "adjudicate_disagreement":
            vote = multi_route(extractor, documents, _subset(workload, names), tiers)
            adj = span_adjudicate(
                extractor, documents, workload, vote.get("disagreements") or {},
            )
            return {"action": action, "adjudicate": adj}
    except BudgetExhausted:
        return {"action": action, "stopped": "budget"}
    return {"action": action, "skipped": True}


def _subset(workload: Workload, names: list[str]) -> Workload:
    if not names:
        return workload
    keep = set(names) | {name.split(".")[-1] for name in names}
    reqs = {
        key: value
        for key, value in workload.requirements.items()
        if key in keep or key.split(".")[-1] in keep
    }
    if not reqs:
        return workload
    return workload.model_copy(update={"requirements": reqs})


def _normalize_domain(extractor: StagedExtractor, workload: Workload, names: list[str]) -> dict[str, Any]:
    changed = 0
    for record in list(extractor.store.records.values()):
        if names and record.attribute not in names and record.attribute.split(".")[-1] not in {
            name.split(".")[-1] for name in names
        }:
            continue
        req = workload.requirements.get(record.attribute)
        if req is None or len(req.declared_domain) < 2 or record.surface_value in (None, ""):
            continue
        mapped = apply_domain(record.surface_value, {}, list(req.declared_domain))
        if mapped == record.surface_value:
            continue
        surface, parsed, reason = validate_cell(mapped, req.dtype)
        record.surface_value = surface
        record.parsed_value = parsed
        if reason:
            record.null_reason = reason
        extractor.store.put(record)
        changed += 1
    return {"action": "normalize_to_declared_domain", "n": changed}
