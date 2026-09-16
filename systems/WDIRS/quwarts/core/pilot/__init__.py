"""Pilot extraction statistics and rho."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Iterable

from quwarts.core.extract import EvidenceStore, StagedExtractor, cluster_document_formats, default_extractor
from quwarts.core.ledger import TokenLedger
from quwarts.core.models import (
    AttributeRequirement,
    AttributeStats,
    PreprocessPolicy,
    SourceDocument,
    Workload,
)
from quwarts.core.preprocess import Segment, segment_documents


def estimate_stats(
    documents: list[SourceDocument],
    workload: Workload,
    store: EvidenceStore,
) -> dict[str, AttributeStats]:
    format_clusters = cluster_document_formats(documents)
    stats: dict[str, AttributeStats] = {}
    for name, req in workload.requirements.items():
        records = store.for_attribute(name)
        values = [row.surface_value for row in records if row.surface_value]
        n_rows = max(len(records), 1)
        distinct = {str(value).strip().lower() for value in values}
        n_distinct = max(len(distinct), 1)
        group_keys = req.entity_type
        n_groups = max(len({row.doc_id for row in records}), 1)
        group_size = n_rows / n_groups
        multiplicity = n_rows / n_distinct
        rho = estimate_rho(records, default=0.5)
        scored = _scored_columns(workload, name)
        stats[name] = AttributeStats(
            n_rows=n_rows,
            n_groups=n_groups,
            group_size=group_size,
            n_distinct=n_distinct,
            multiplicity=multiplicity,
            rho=rho,
            n_scored_columns=scored,
        )
        req.stats = stats[name]
        _ = group_keys
        _ = format_clusters
    return stats


def estimate_rho(records: Iterable[object], default: float = 0.5) -> float:
    """within-cluster variance / total variance of a disagreement indicator.

    Disagreement is approximated by whether two records for the same document
    differ in surface value. Default 0.5 before enough data exists.
    """

    by_cluster: dict[str, list[str]] = defaultdict(list)
    all_values: list[str] = []
    for row in records:
        cluster = getattr(row, "template_cluster_id", None) or "default"
        value = str(getattr(row, "surface_value", "") or "")
        by_cluster[cluster].append(value)
        all_values.append(value)
    if len(all_values) < 4 or len(by_cluster) < 2:
        return default
    total = _value_variance(all_values)
    if total <= 1e-12:
        return default
    within_parts = [_value_variance(values) for values in by_cluster.values() if len(values) > 1]
    if not within_parts:
        return default
    within = sum(within_parts) / len(within_parts)
    return float(min(1.0, max(0.0, within / total)))


def estimate_rho_from_disagreement(
    values_a: list[str],
    values_b: list[str],
    clusters: list[str],
    default: float = 0.5,
) -> float:
    """Unit-testable estimator: disagreement between two extractors."""

    if len(values_a) != len(values_b) or not values_a:
        return default
    disagree = [0.0 if a == b else 1.0 for a, b in zip(values_a, values_b)]
    total = _numeric_variance(disagree)
    if total <= 1e-12:
        return default
    by_cluster: dict[str, list[float]] = defaultdict(list)
    for flag, cluster in zip(disagree, clusters):
        by_cluster[cluster].append(flag)
    parts = [_numeric_variance(vals) for vals in by_cluster.values() if len(vals) > 1]
    if not parts:
        return default
    within = sum(parts) / len(parts)
    return float(min(1.0, max(0.0, within / total)))


def _value_variance(values: list[str]) -> float:
    if len(values) < 2:
        return 0.0
    encoded = [float(hash(value) % 997) for value in values]
    return _numeric_variance(encoded)


def _numeric_variance(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return sum((item - mean) ** 2 for item in values) / len(values)


def _scored_columns(workload: Workload, attribute: str) -> int:
    count = 0
    for template in workload.templates:
        if attribute not in template.roles_by_attribute:
            continue
        count += max(1, len(template.project_attributes) + len(template.aggregated_attributes))
    return max(count, 1)


def run_pilot(
    documents: list[SourceDocument],
    workload: Workload,
    ledger: TokenLedger,
    store: EvidenceStore,
    sample_fraction: float = 0.2,
    seed: int = 0,
    caller=None,
) -> dict[str, AttributeStats]:
    rng = random.Random(seed)
    ordered = list(documents)
    rng.shuffle(ordered)
    n = max(1, math.ceil(len(ordered) * sample_fraction))
    sample = ordered[:n]
    extractor = StagedExtractor(
        store=store, ledger=ledger, extractor=default_extractor, caller=caller, seed=seed,
    )
    extractor.extract(
        sample,
        workload,
        PreprocessPolicy(mode="whole_document"),
        tiers={name: "cheap" for name in workload.requirements},
    )
    return estimate_stats(sample, workload, store)


def synthetic_stats(
    n_rows: int,
    n_groups: int,
    n_distinct: int,
    rho: float,
    n_scored_columns: int,
) -> AttributeStats:
    n_rows = max(n_rows, 1)
    n_groups = max(n_groups, 1)
    n_distinct = max(n_distinct, 1)
    return AttributeStats(
        n_rows=n_rows,
        n_groups=n_groups,
        group_size=n_rows / n_groups,
        n_distinct=n_distinct,
        multiplicity=n_rows / n_distinct,
        rho=min(1.0, max(0.0, rho)),
        n_scored_columns=n_scored_columns,
    )
