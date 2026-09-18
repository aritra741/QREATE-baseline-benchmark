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
        pop.type[name] = ModuleConfig(strategy=req.dtype, params={})
        pop.type[name.split(".")[-1]] = pop.type[name]
        pop.norm.setdefault(name, ModuleConfig(strategy="surface", params={}))
        pop.miss.setdefault(name, ModuleConfig(strategy="nulls_preserved", params={}))
        pop.er.setdefault(name, ModuleConfig(strategy="no_merge", params={}))
        pop.grain.setdefault(req.entity_type, req.finest_grain)
    for name, dtype in workload.join_types.items():
        pop.type[name] = ModuleConfig(strategy=dtype, params={})
        pop.type[name.split(".")[-1]] = pop.type[name]
    return pop


def refresh_population_types(pop: PopulationPolicy, workload: Workload) -> PopulationPolicy:
    """Write SQL-declared types onto an existing population policy."""

    for name, req in workload.requirements.items():
        pop.type[name] = ModuleConfig(strategy=req.dtype, params={})
        pop.type[name.split(".")[-1]] = pop.type[name]
    for name, dtype in workload.literal_types.items():
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
            if surface not in (None, ""):
                bare = record.attribute.split(".")[-1]
                canon = _canonical(record, config.pop, surface)
                if canon not in (None, ""):
                    row[f"{bare}__canonical"] = canon
                    row[f"{record.attribute}__canonical"] = canon
                keys = record.candidate_keys or {}
                if keys.get("lo") not in (None, ""):
                    row[f"{bare}__lo"] = keys["lo"]
                if keys.get("hi") not in (None, ""):
                    row[f"{bare}__hi"] = keys["hi"]
                if keys.get("unit") not in (None, ""):
                    row[f"{bare}__unit"] = keys["unit"]
            elif record.attribute not in row:
                row[record.attribute] = None
            if surface not in (None, ""):
                row.setdefault(f"{record.attribute}__surface", surface)
                bare = record.attribute.split(".")[-1]
                if row.get(bare) in (None, ""):
                    row[bare] = surface
            keys = record.candidate_keys or {}
            if keys.get("like_vocab") not in (None, ""):
                bare = record.attribute.split(".")[-1]
                row[f"{bare}__like"] = keys["like_vocab"]
                row[f"{record.attribute}__like"] = keys["like_vocab"]
            if keys.get("vocab") not in (None, ""):
                bare = record.attribute.split(".")[-1]
                row[f"{bare}__vocab"] = keys["vocab"]
                row[f"{record.attribute}__vocab"] = keys["vocab"]
        rows.append(row)

    clear_merge_audit()
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
    keys = record.candidate_keys or {}
    if keys.get("completed") == "join":
        return value
    if keys.get("representation") == "absence" or record.null_reason == "absence":
        return None
    if keys.get("representation") in {"unit", "boolean", "range", "band"} and record.parsed_value is not None:
        return record.parsed_value
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
    ident = pop.er.get(record.attribute) or pop.er.get(record.attribute.split(".")[-1])
    mapping = {}
    if ident is not None and ident.strategy == "identity":
        mapping = ident.params.get("map") or {}
    else:
        norm = pop.norm.get(record.attribute) or pop.norm.get(record.attribute.split(".")[-1])
        if norm is None or norm.strategy != "identity":
            return None
        mapping = norm.params.get("map") or {}
    return _lookup_id(surface, mapping)


def _lookup_id(surface: Any, mapping: dict[str, str]) -> Any:
    text = str(surface or "").strip()
    if not text or not mapping:
        return None
    if text in mapping:
        return mapping[text]
    folded = {}
    for key, dest in mapping.items():
        folded.setdefault(" ".join(str(key).replace("_", " ").casefold().split()), dest)
    return folded.get(" ".join(text.replace("_", " ").casefold().split()))


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


_MERGE_AUDIT: list[dict[str, Any]] = []


def clear_merge_audit() -> None:
    _MERGE_AUDIT.clear()


def merge_audit() -> list[dict[str, Any]]:
    return list(_MERGE_AUDIT)


def identity_merge_keys(workload: Workload) -> dict[str, list[str]]:
    """Only identity-bearing attributes may authorize a merge.

    KEY roles identify the row. A join attribute does so only on a self-join.
    Cross-entity join attributes are foreign keys. GROUP/categorical attributes
    never establish identity.
    """

    from quwarts.core.models import Role

    by_entity: dict[str, set[str]] = defaultdict(set)
    for template in workload.templates:
        for name, roles in template.roles_by_attribute.items():
            entity = name.split(".")[0] if "." in name else ""
            # JOIN columns are also tagged KEY. A cross-entity join is a
            # foreign key and does not identify this row.
            if Role.KEY in roles and Role.JOIN not in roles and entity:
                by_entity[entity].add(name)
        for left, right in template.join_pairs:
            if not left or not right or "." not in left or "." not in right:
                continue
            left_ent, right_ent = left.split(".", 1)[0], right.split(".", 1)[0]
            if left_ent == right_ent:
                by_entity[left_ent].add(left)
                by_entity[right_ent].add(right)
    return {entity: sorted(names) for entity, names in by_entity.items() if names}


def _row_entity(row: dict[str, Any]) -> str:
    doc = str(row.get("doc_id") or "")
    if "/" in doc:
        return doc.split("/", 1)[0].lower()
    return ""


def _key_tuple(row: dict[str, Any], names: list[str]) -> tuple[str, ...]:
    values = []
    for name in names:
        bare = name.split(".")[-1]
        raw = row.get(f"{bare}__canonical")
        if raw in (None, ""):
            raw = row.get(name)
        if raw in (None, ""):
            raw = row.get(bare)
        values.append(str(raw or "").strip().lower())
    return tuple(values)


def _merge(rows: list[dict[str, Any]], config: Configuration, workload: Workload) -> list[dict[str, Any]]:
    """Same-relation merge on a nonempty identity key. Empty keys stay distinct."""

    clear_merge_audit()
    authorized = identity_merge_keys(workload)
    categorical = [
        name
        for name, cfg in config.pop.er.items()
        if cfg.strategy == "merge" and name not in {item for names in authorized.values() for item in names}
    ]
    by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unknown: list[dict[str, Any]] = []
    for row in rows:
        entity = _row_entity(row)
        if not entity:
            unknown.append(dict(row))
            continue
        by_entity[entity].append(row)

    out: list[dict[str, Any]] = list(unknown)
    for entity, group in by_entity.items():
        keys = authorized.get(entity) or []
        if not keys:
            out.extend(dict(row) for row in group)
            continue
        buckets: dict[tuple[str, ...], dict[str, Any]] = {}
        members: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for row in group:
            key = _key_tuple(row, keys)
            if not any(key):
                out.append(dict(row))
                continue
            doc = str(row.get("doc_id") or "")
            if key not in buckets:
                buckets[key] = dict(row)
                members[key].append(doc)
                continue
            current = buckets[key]
            members[key].append(doc)
            for field, value in row.items():
                if current.get(field) in (None, "") and value not in (None, ""):
                    current[field] = value
        for key, row in buckets.items():
            docs = [item for item in members[key] if item]
            if len(docs) >= 2:
                support = [
                    name
                    for name in categorical
                    if name.split(".")[0] == entity and _key_tuple(row, [name])[0]
                ]
                _MERGE_AUDIT.append(
                    {
                        "entity": entity,
                        "docs": docs,
                        "identity_key": list(keys),
                        "identity_values": list(key),
                        "categorical_support": support,
                        "justification": "nonempty identity key matched within one relation",
                    }
                )
            out.append(row)
    return out


def _coarsen(rows: list[dict[str, Any]], config: Configuration) -> list[dict[str, Any]]:
    # Finest grain is stored; coarsening is deferred to SQL GROUP BY when possible.
    return rows


def tokens_spent_during_population() -> int:
    return 0
