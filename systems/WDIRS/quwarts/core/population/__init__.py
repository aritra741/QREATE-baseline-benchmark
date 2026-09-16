"""Deterministic views over evidence. No tokens. I7."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from quwarts.core.domain import apply_domain
from quwarts.core.models import (
    Configuration,
    EvidenceRecord,
    ModuleConfig,
    PopulationPolicy,
    Role,
    Workload,
)


def policy_from_demands(
    resolved_demands: dict[str, str],
    workload: Workload,
) -> PopulationPolicy:
    pop = PopulationPolicy()
    for key, demand in resolved_demands.items():
        entity, attribute, module = key.split("|", 2)
        cfg = ModuleConfig(strategy=demand, params={})
        if module == "er":
            pop.er[attribute] = cfg
        elif module == "norm":
            pop.norm[attribute] = cfg
        elif module == "unit":
            pop.unit[attribute] = cfg
        elif module == "type":
            pop.type[attribute] = cfg
        elif module == "miss":
            pop.miss[attribute] = cfg
        elif module == "grain":
            pop.grain[entity] = demand
    for name, req in workload.requirements.items():
        pop.type.setdefault(name, ModuleConfig(strategy=req.dtype, params={}))
        pop.norm.setdefault(name, ModuleConfig(strategy="surface", params={}))
        pop.miss.setdefault(name, ModuleConfig(strategy="nulls_preserved", params={}))
        pop.er.setdefault(name, ModuleConfig(strategy="no_merge", params={}))
        pop.grain.setdefault(req.entity_type, req.finest_grain)
    for name, dtype in workload.join_types.items():
        pop.type[name] = ModuleConfig(strategy=dtype, params={})
        pop.type[name.split(".")[-1]] = pop.type[name]
    return pop


def apply_population(
    records: list[EvidenceRecord],
    config: Configuration,
    workload: Workload,
) -> list[dict[str, Any]]:
    """Pure view. Must not touch the ledger."""

    grouped: dict[str, list[EvidenceRecord]] = defaultdict(list)
    for record in records:
        grouped[record.doc_id].append(record)

    rows: list[dict[str, Any]] = []
    for doc_id, items in grouped.items():
        row: dict[str, Any] = {"doc_id": doc_id}
        for record in items:
            surface = record.surface_value
            if isinstance(surface, str):
                surface = surface.strip()
            committed = _commit(record, config.pop)
            if committed is not None:
                row[record.attribute] = committed
                bare = record.attribute.split(".")[-1]
                if row.get(bare) in (None, ""):
                    row[bare] = committed
                canon = _canonical(record, config.pop, surface if surface not in (None, "") else committed)
                if canon not in (None, ""):
                    row[f"{bare}__canonical"] = canon
                    row[f"{record.attribute}__canonical"] = canon
            elif record.attribute not in row:
                row[record.attribute] = None
            if surface not in (None, ""):
                row.setdefault(f"{record.attribute}__surface", surface)
        rows.append(row)

    if any(cfg.strategy == "merge" for cfg in config.pop.er.values()):
        rows = _merge(rows, config, workload)
    grain = config.pop.grain
    if grain and any(value != "mention" for value in grain.values()):
        rows = _coarsen(rows, config)
    return rows


def _commit(record: EvidenceRecord, pop: PopulationPolicy) -> Any:
    miss = pop.miss.get(record.attribute)
    if record.surface_value is None:
        if miss and miss.strategy == "impute":
            return miss.params.get("value", 0)
        return None
    value: Any = record.surface_value
    if isinstance(value, str):
        value = value.strip()
    if (record.candidate_keys or {}).get("completed") == "join":
        return value
    unit = pop.unit.get(record.attribute)
    if unit and unit.strategy == "unit:canonical" and record.parsed_value is not None:
        value = record.parsed_value
    typ = pop.type.get(record.attribute)
    if typ and typ.strategy == "numeric":
        value = _as_number(record.parsed_value if record.parsed_value is not None else value)
    elif isinstance(record.parsed_value, (int, float)) and typ and typ.strategy in {"numeric"}:
        value = record.parsed_value
    norm = pop.norm.get(record.attribute) or pop.norm.get(record.attribute.split(".")[-1])
    if norm and norm.strategy == "domain":
        value = apply_domain(
            value,
            norm.params.get("map") or {},
            list(norm.params.get("domain") or []),
        )
    elif norm and norm.strategy == "canonical" and isinstance(value, str):
        value = value.strip().lower()
    return value


def _canonical(record: EvidenceRecord, pop: PopulationPolicy, surface: Any) -> Any:
    norm = pop.norm.get(record.attribute) or pop.norm.get(record.attribute.split(".")[-1])
    if norm is None or norm.strategy != "identity":
        return None
    return apply_domain(surface, norm.params.get("map") or {}, [])


_UNIT_SCALE = {
    "k": 1_000,
    "thousand": 1_000,
    "m": 1_000_000,
    "mn": 1_000_000,
    "mm": 1_000_000,
    "million": 1_000_000,
    "b": 1_000_000_000,
    "bn": 1_000_000_000,
    "billion": 1_000_000_000,
}
_NUMBER_PREFIX = re.compile(
    r"^(over|about|approx(?:imately)?|under|around|nearly|more than|less than)\s+",
    re.I,
)
_NUMBER_TOKEN = re.compile(
    r"([+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?)\s*"
    r"(thousand|million|billion|bn|mn|mm|k|m|b)?",
    re.I,
)


def _as_number(value: Any) -> Any:
    """Parse a numeric surface, including currency marks and scale suffixes."""

    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "").replace("$", "").replace("£", "").replace("€", "")
    text = _NUMBER_PREFIX.sub("", text)
    match = _NUMBER_TOKEN.search(text)
    if match is None:
        return None
    raw, suffix = match.group(1), (match.group(2) or "").lower()
    number = float(raw) if ("." in raw or "e" in raw.lower()) else int(raw)
    scale = _UNIT_SCALE.get(suffix, 1)
    scaled = number * scale
    if isinstance(scaled, float) and scaled.is_integer():
        return int(scaled)
    return scaled


def _merge(rows: list[dict[str, Any]], config: Configuration, workload: Workload) -> list[dict[str, Any]]:
    keys = [
        name
        for name, cfg in config.pop.er.items()
        if cfg.strategy == "merge"
    ]
    if not keys:
        return rows
    buckets: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(
            str(
                row.get(f"{name.split('.')[-1]}__canonical")
                or row.get(name, "")
            ).strip().lower()
            for name in keys
        )
        if key not in buckets:
            buckets[key] = dict(row)
            continue
        current = buckets[key]
        for field, value in row.items():
            if current.get(field) in (None, "") and value not in (None, ""):
                current[field] = value
    return list(buckets.values())


def _coarsen(rows: list[dict[str, Any]], config: Configuration) -> list[dict[str, Any]]:
    # Finest grain is stored; coarsening is deferred to SQL GROUP BY when possible.
    return rows


def tokens_spent_during_population() -> int:
    return 0
