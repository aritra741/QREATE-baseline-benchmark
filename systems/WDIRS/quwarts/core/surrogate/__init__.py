"""Ground-truth-free U_hat. No signal may read data/gold/."""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from pathlib import Path

from quwarts.core.models import (
    Configuration,
    MaterializedDB,
    SourceDocument,
    SurrogateReport,
    Template,
    Workload,
)


DEFAULT_WEIGHTS = {
    "cardinality_plausibility": 0.12,
    "key_provenance_coverage": 0.16,
    "key_null_dup_rate": 0.14,
    "cross_config_agreement": 0.08,
    "type_coercion_failure": 0.10,
    "constraint_violation": 0.14,
    "slice_boundary_mass": 0.10,
    "stage1_admission_rate": 0.08,
    "empty_result_rate": 0.08,
}


def _amp_weight(workload: Workload, attributes: list[str]) -> float:
    total = 0.0
    for name in attributes:
        req = workload.requirements.get(name)
        if req is None:
            continue
        total += req.amp or 1.0
    return max(total, 1.0)


def compute_signals(
    db: MaterializedDB,
    config: Configuration,
    documents: list[SourceDocument],
    workload: Workload,
    *,
    stage1_rate: float = 1.0,
    peer_keysets: list[set[str]] | None = None,
    empty_rate: float = 0.0,
) -> dict[str, float]:
    path = Path(db.sqlite_path)
    rows = _read_fact(path)
    n_docs = max(len(documents), 1)
    n_rows = max(len(rows), 1)
    rows_per_doc = n_rows / n_docs
    cardinality = 1.0 - min(1.0, abs(math.log2(max(rows_per_doc, 1e-6))))
    cardinality = max(0.0, min(1.0, (cardinality + 1.0) / 2.0))

    keys = []
    for relation, pk in config.schema_.primary_keys.items():
        keys.extend(pk)
    if not keys and rows:
        keys = [next(iter(rows[0]))]

    key_values = []
    nulls = 0
    for row in rows:
        parts = []
        for key in keys:
            value = row.get(key) or row.get(key.split(".")[-1])
            if value in (None, ""):
                nulls += 1
            parts.append(str(value or ""))
        key_values.append("|".join(parts))
    unique = set(key_values)
    dup_rate = 1.0 - (len(unique) / max(len(key_values), 1))
    null_rate = nulls / max(len(key_values) * max(len(keys), 1), 1)
    key_null_dup = 1.0 - min(1.0, dup_rate + null_rate)

    provenance = 1.0
    if db.coverage.attributes_present:
        covered = len(db.coverage.attributes_present)
        needed = max(len(workload.requirements), 1)
        provenance = min(1.0, covered / needed)

    agreement = 1.0
    if peer_keysets:
        current = unique
        scores = []
        for peer in peer_keysets:
            union = current | peer
            scores.append(len(current & peer) / max(len(union), 1))
        agreement = sum(scores) / len(scores)

    type_fail = 0.0
    numeric_attrs = [
        name for name, req in workload.requirements.items() if req.dtype == "numeric"
    ]
    checked = 0
    failed = 0
    for row in rows:
        for name in numeric_attrs:
            value = row.get(name) or row.get(name.split(".")[-1])
            if value in (None, ""):
                continue
            checked += 1
            try:
                float(str(value).replace(",", "").replace("$", ""))
            except ValueError:
                failed += 1
    if checked:
        type_fail = 1.0 - failed / checked
    else:
        type_fail = 1.0

    constraint = 1.0 - min(1.0, dup_rate)
    slice_mass = _slice_boundary(rows, workload)
    admission = min(1.0, stage1_rate / 0.5) if stage1_rate < 0.5 else max(0.4, 1.0 - (stage1_rate - 0.9))
    admission = max(0.0, min(1.0, admission))
    empty = 1.0 - empty_rate

    return {
        "cardinality_plausibility": max(0.0, min(1.0, cardinality)),
        "key_provenance_coverage": provenance,
        "key_null_dup_rate": max(0.0, key_null_dup),
        "cross_config_agreement": agreement,
        "type_coercion_failure": type_fail,
        "constraint_violation": constraint,
        "slice_boundary_mass": 1.0 - slice_mass,
        "stage1_admission_rate": admission,
        "empty_result_rate": empty,
    }


def U_hat(
    db: MaterializedDB,
    config: Configuration,
    documents: list[SourceDocument],
    workload: Workload,
    **kwargs,
) -> SurrogateReport:
    signals = compute_signals(db, config, documents, workload, **kwargs)
    weights = dict(DEFAULT_WEIGHTS)
    # Amplification-weighted: key-like attributes boost constraint/provenance.
    key_boost = 0.0
    for req in workload.requirements.values():
        if req.amp:
            key_boost += req.amp
    if key_boost > 0:
        scale = 1.0 + min(1.0, math.log1p(key_boost) / 10.0)
        weights["key_provenance_coverage"] *= scale
        weights["constraint_violation"] *= scale
        weights["key_null_dup_rate"] *= scale
    total_w = sum(weights.values())
    weighted = {name: signals[name] * (weights[name] / total_w) for name in signals}
    score = sum(weighted.values())
    return SurrogateReport(U_hat=score, signals=signals, weighted=weighted)


def _read_fact(path: Path) -> list[dict[str, str | None]]:
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        name = "fact" if "fact" in tables else (tables[0] if tables else None)
        if name is None:
            return []
        cur = conn.execute(f'SELECT * FROM "{name}"')
        cols = [item[0] for item in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def _slice_boundary(rows: list[dict], workload: Workload) -> float:
    if not rows:
        return 0.0
    hits = 0
    total = 0
    for req in workload.requirements.values():
        if req.slice.kind != "ranges" or not req.slice.ranges:
            continue
        constants = {str(value).lower() for rng in req.slice.ranges for value in rng.values}
        for row in rows:
            value = row.get(req.name) or row.get(req.name.split(".")[-1])
            if value is None:
                continue
            total += 1
            if str(value).lower() in constants:
                hits += 1
    if total == 0:
        return 0.0
    # high mass exactly on the slice edge is a staging-truncation smell when
    # almost every surviving row is a predicate constant.
    return hits / total
