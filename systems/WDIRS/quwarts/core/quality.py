"""Detector-guided extract repair. Route counts come from amp, not scores."""

from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from typing import Any

from quwarts.core.amplify import amp
from quwarts.core.extract import StagedExtractor, cluster_document_formats, validate_cell
from quwarts.core.ledger import BudgetExhausted
from quwarts.core.models import (
    AttributeRequirement,
    PreprocessPolicy,
    Role,
    SourceDocument,
    Workload,
)
from quwarts.core.pilot import estimate_rho_from_disagreement, estimate_stats
RHO_VOTE_MAX = 0.5
CELL_CHANGE_STOP = 0.02
VOTE_BUDGET = 1_100_000
ADJUDICATE_BUDGET = 300_000
RHO_SAMPLE_FRACTION = 0.2
RHO_SAMPLE_MIN = 20
RHO_SAMPLE_MAX = 80
DISSIMILAR_MODEL = "meta-llama/llama-3.1-8b-instruct"

_CHUNK = PreprocessPolicy(mode="fixed_chunk", chunk_tokens=256, overlap_tokens=32)


def route_count(requirement: AttributeRequirement) -> int:
    value = amp(requirement)
    roles = requirement.roles or {Role.PROJECT}
    if value >= 2.0:
        return 3
    if value >= 1.2:
        return 2
    if roles & {Role.AGG_ADDITIVE, Role.AGG_EXTREMAL, Role.AGG_DISTINCT, Role.GROUP}:
        return 2
    return 1


def _fold(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def majority(values: list[str]) -> str | None:
    folded: list[str] = []
    original: dict[str, str] = {}
    for value in values:
        if value in (None, ""):
            continue
        key = _fold(value)
        if not key:
            continue
        folded.append(key)
        original.setdefault(key, value)
    if not folded:
        return None
    winner, _ = Counter(folded).most_common(1)[0]
    return original[winner]


def _surface_map(store, attribute: str) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for record in store.for_attribute(attribute):
        found[record.doc_id] = record.surface_value
    return found


def _snapshot(store) -> dict[tuple[str, str], str | None]:
    return {
        (record.doc_id, record.attribute): record.surface_value
        for record in store.records.values()
    }


def _changed_fraction(before: dict, after: dict) -> float:
    keys = set(before) | set(after)
    if not keys:
        return 0.0
    changed = sum(1 for key in keys if before.get(key) != after.get(key))
    return changed / len(keys)


def measure_rho(
    extractor: StagedExtractor,
    documents: list[SourceDocument],
    workload: Workload,
    tiers: dict[str, str],
    *,
    seed: int = 0,
) -> dict[str, float]:
    """Second dissimilar route on a document sample. Updates req.stats.rho."""

    rng = random.Random(seed)
    ordered = list(documents)
    rng.shuffle(ordered)
    n = min(
        RHO_SAMPLE_MAX,
        max(RHO_SAMPLE_MIN, int(len(ordered) * RHO_SAMPLE_FRACTION)),
    )
    n = min(n, len(ordered))
    sample = ordered[:n]
    clusters = cluster_document_formats(sample)
    names = list(workload.requirements)
    extractor.configure_route(
        route="dissimilar",
        prompt_kind="dissimilar",
        model=DISSIMILAR_MODEL,
        policy=_CHUNK,
    )
    try:
        extractor.extract_attributes(
            sample, names, tiers, stage=2, logical=None, workload=workload,
        )
    except BudgetExhausted:
        pass
    finally:
        extractor.configure_route()

    rhos: dict[str, float] = {}
    for name in names:
        primary = _surface_map_route(extractor.store, name, "primary")
        other = _surface_map_route(extractor.store, name, "dissimilar")
        docs = sorted(set(primary) | set(other))
        values_a = [_fold(primary.get(doc) or "") for doc in docs]
        values_b = [_fold(other.get(doc) or "") for doc in docs]
        labels = [clusters.get(doc, "default") for doc in docs]
        rho = estimate_rho_from_disagreement(values_a, values_b, labels)
        rhos[name] = rho
        req = workload.requirements[name]
        if req.stats is None:
            estimate_stats(sample, workload, extractor.store)
        if req.stats is not None:
            req.stats.rho = rho
    return rhos


def _surface_map_route(store, attribute: str, route: str) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for record in store.for_attribute(attribute):
        if (record.candidate_keys or {}).get("route", "primary") != route:
            continue
        found[record.doc_id] = record.surface_value
    if found:
        return found
    return _surface_map(store, attribute)


def multi_route(
    extractor: StagedExtractor,
    documents: list[SourceDocument],
    workload: Workload,
    tiers: dict[str, str],
    *,
    vote_ceiling: int = VOTE_BUDGET,
) -> dict[str, Any]:
    """Extra routes by amp. High-rho attributes get a different strategy."""

    start = extractor.ledger.spent
    by_attr: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for name, req in workload.requirements.items():
        n = route_count(req)
        rho = req.stats.rho if req.stats is not None else 0.5
        high = rho > RHO_VOTE_MAX
        primary = _surface_map(extractor.store, name)
        for doc_id, value in primary.items():
            if value:
                by_attr[name][doc_id].append(str(value))
        if extractor.ledger.spent - start >= vote_ceiling:
            break
        if n <= 1 and not high:
            continue
        try:
            if high:
                extractor.configure_route(
                    route="focused",
                    prompt_kind="focused",
                    model=None,
                    policy=_CHUNK,
                )
                extractor.extract_attributes(
                    documents, [name], {name: "expensive"}, stage=3,
                    workload=workload,
                )
            else:
                extra = min(n - 1, 2)
                if extra >= 1:
                    extractor.configure_route(
                        route="dissimilar",
                        prompt_kind="dissimilar",
                        model=DISSIMILAR_MODEL,
                        policy=_CHUNK,
                    )
                    extractor.extract_attributes(
                        documents, [name], tiers, stage=2, workload=workload,
                    )
                if extra >= 2:
                    extractor.configure_route(
                        route="repeat",
                        prompt_kind="primary",
                        model=None,
                        policy=PreprocessPolicy(mode="whole_document"),
                    )
                    extractor.extract_attributes(
                        documents, [name], tiers, stage=2, workload=workload,
                    )
        except BudgetExhausted:
            break
        finally:
            extractor.configure_route()
        for record in extractor.store.for_attribute(name):
            if record.surface_value:
                by_attr[name][record.doc_id].append(str(record.surface_value))

    disagreements: dict[str, set[str]] = defaultdict(set)
    voted = 0
    for name, per_doc in by_attr.items():
        req = workload.requirements[name]
        dtype = req.dtype
        for doc_id, values in per_doc.items():
            unique = {_fold(item) for item in values if _fold(item)}
            if len(unique) > 1:
                disagreements[name].add(doc_id)
                if route_count(req) >= 2 and extractor.ledger.spent - start < vote_ceiling:
                    try:
                        extractor.configure_route(
                            route="escalate",
                            prompt_kind="focused",
                            model=None,
                            policy=PreprocessPolicy(mode="whole_document"),
                        )
                        docs = [row for row in documents if row.doc_id == doc_id]
                        extractor.extract_attributes(
                            docs, [name], {name: "expensive"}, stage=3,
                            workload=workload,
                        )
                    except BudgetExhausted:
                        pass
                    finally:
                        extractor.configure_route()
                    for record in extractor.store.for_attribute(name):
                        if record.doc_id == doc_id and record.surface_value:
                            values.append(str(record.surface_value))
            winner = majority(values)
            if winner is None:
                continue
            surface, parsed, reason = validate_cell(winner, dtype)
            if extractor.commit_vote(doc_id, name, surface, parsed, reason):
                voted += 1
    return {
        "voted": voted,
        "disagreements": {name: sorted(docs) for name, docs in disagreements.items()},
        "tokens": extractor.ledger.spent - start,
    }


def span_adjudicate(
    extractor: StagedExtractor,
    documents: list[SourceDocument],
    workload: Workload,
    disagreements: dict[str, list[str]],
    *,
    ceiling: int = ADJUDICATE_BUDGET,
) -> dict[str, Any]:
    """Keep a disagreed cell only if its surface appears in the document."""

    start = extractor.ledger.spent
    by_doc = {doc.doc_id: doc for doc in documents}
    cleared = 0
    nulled = 0
    try:
        for name, doc_ids in disagreements.items():
            dtype = workload.requirements[name].dtype
            for doc_id in doc_ids:
                if extractor.ledger.spent - start >= ceiling:
                    raise BudgetExhausted("adjudicate ceiling")
                doc = by_doc.get(doc_id)
                if doc is None:
                    continue
                current = None
                for record in extractor.store.for_attribute(name):
                    if record.doc_id == doc_id and record.surface_value:
                        current = record.surface_value
                if current and _surface_in_text(current, doc.text):
                    cleared += 1
                    continue
                extractor.configure_route(
                    route="span",
                    prompt_kind="focused",
                    model=None,
                    policy=PreprocessPolicy(mode="whole_document"),
                )
                extractor.extract_attributes(
                    [doc], [name], {name: "expensive"}, stage=3, workload=workload,
                )
                extractor.configure_route()
                kept = False
                for record in extractor.store.for_attribute(name):
                    if record.doc_id != doc_id or not record.surface_value:
                        continue
                    if _surface_in_text(record.surface_value, doc.text):
                        kept = True
                        break
                if kept:
                    cleared += 1
                else:
                    extractor.commit_vote(doc_id, name, None, None, "ungrounded")
                    nulled += 1
    except BudgetExhausted:
        pass
    finally:
        extractor.configure_route()
    return {"cleared": cleared, "nulled": nulled, "tokens": extractor.ledger.spent - start}


def _surface_in_text(surface: str, text: str) -> bool:
    folded = _fold(surface)
    if not folded:
        return False
    hay = _fold(text)
    if folded in hay:
        return True
    tokens = folded.split()
    return len(tokens) >= 2 and all(token in hay for token in tokens[:3])


def repair_until_stable(
    extractor: StagedExtractor,
    documents: list[SourceDocument],
    workload: Workload,
    policy: PreprocessPolicy,
    tiers: dict[str, str],
    logical=None,
    *,
    seed: int = 0,
) -> dict[str, Any]:
    """Keep repairing while budget remains and cells still move."""

    _ = policy
    _ = logical
    estimate_stats(documents, workload, extractor.store)
    rhos = {}
    try:
        rhos = measure_rho(extractor, documents, workload, tiers, seed=seed)
    except BudgetExhausted:
        pass
    passes = []
    last_change = 1.0
    while extractor.ledger.remaining() > 0 and last_change >= CELL_CHANGE_STOP:
        before = _snapshot(extractor.store)
        vote = {}
        adj = {}
        try:
            vote = multi_route(extractor, documents, workload, tiers)
            adj = span_adjudicate(
                extractor, documents, workload, vote.get("disagreements") or {},
            )
        except BudgetExhausted:
            after = _snapshot(extractor.store)
            last_change = _changed_fraction(before, after)
            passes.append({"change": last_change, "vote": vote, "adjudicate": adj})
            break
        after = _snapshot(extractor.store)
        last_change = _changed_fraction(before, after)
        passes.append({"change": last_change, "vote": vote, "adjudicate": adj})
        if last_change < CELL_CHANGE_STOP:
            break
        if len(passes) >= 8:
            break
    return {"rho": rhos, "passes": passes, "last_change": last_change}
