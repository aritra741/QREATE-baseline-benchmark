"""Repair tools. Compiler plan stays frozen; these retarget extract and ER."""

from __future__ import annotations

from typing import Any

from quwarts.core.domain import apply_domain
from quwarts.core.extract import StagedExtractor, validate_cell
from quwarts.core.ledger import BudgetExhausted
from quwarts.core.models import PreprocessPolicy, SourceDocument, Workload
from quwarts.core.quality import majority, multi_route, span_adjudicate
from quwarts.core.repair.er import resolve_shared_ids, stamp_shared_ids
from quwarts.core.repair.models import Repair


def estimate_cost(action: str, n_targets: int) -> int:
    base = {
        "reextract_failed_cells": 400,
        "reextract_attribute_slice": 800,
        "normalize_to_declared_domain": 80,
        "repair_join_vocabulary": 250,
        "compare_extractors": 1200,
        "adjudicate_disagreement": 600,
    }
    return max(int(base.get(action, 400) * max(n_targets, 1)), 1)


def propose(issue, store) -> list[Repair]:
    names = issue.attributes or []
    n = max(len(names), 1)
    if issue.kind == "dtype_coercion":
        action = "reextract_failed_cells"
    elif issue.kind in {"empty_query", "coverage", "high_null"}:
        action = "reextract_attribute_slice"
    elif issue.kind == "domain":
        action = "normalize_to_declared_domain"
    elif issue.kind == "join_yield":
        action = "repair_join_vocabulary"
    elif issue.kind == "provenance":
        action = "adjudicate_disagreement"
    else:
        action = "compare_extractors"
    extra = []
    if issue.kind in {"empty_query", "high_null"} and n:
        extra.append(
            Repair(
                action="compare_extractors",
                issue=issue,
                estimated_cost=estimate_cost("compare_extractors", n),
                priority=0.0,
                params={"attributes": names},
            )
        )
    return [
        Repair(
            action=action,
            issue=issue,
            estimated_cost=estimate_cost(action, n),
            priority=0.0,
            params={"attributes": names},
        ),
        *extra,
    ]


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
            n = extractor.reextract_coerced(documents, workload, policy, tiers, logical=logical)
            return {"action": action, "n": n, "bugfix": True}
        if action == "reextract_attribute_slice":
            extractor.extract_attributes(
                documents, names, {name: "expensive" for name in names},
                stage=3, workload=workload, logical=logical,
            )
            return {"action": action, "n": len(names)}
        if action == "normalize_to_declared_domain":
            return _normalize_domain(extractor, workload, names)
        if action == "repair_join_vocabulary":
            shared = resolve_shared_ids(list(extractor.store.records.values()), workload, extractor.caller)
            if identity_report is not None:
                identity_report.clear()
                identity_report.update(stamp_shared_ids({}, shared))
            return {"action": action, "n_ids": (identity_report or {}).get("shared_er", {}).get("n_ids", 0)}
        if action == "compare_extractors":
            vote = multi_route(
                extractor, documents, _subset(workload, names), tiers,
            )
            return {"action": action, "vote": {key: vote.get(key) for key in ("routes", "disagreements") if key in vote}}
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
