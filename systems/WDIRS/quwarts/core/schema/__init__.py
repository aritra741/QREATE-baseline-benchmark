"""Physical schema candidate generation. Always emits keys and implied FDs."""

from __future__ import annotations

import hashlib

from quwarts.core.models import (
    DenialConstraint,
    ForeignKey,
    FunctionalDependency,
    LogicalSchema,
    PhysicalSchema,
    Relation,
)
from quwarts.core.logical import identity_name, is_coarsening, qualify


def _attr_name(entity: str, name: str) -> str:
    return qualify(entity, name)


def _pk_for(entity: str, logical: LogicalSchema) -> list[str]:
    """Keys from declared relationships only. No ``*_name`` / ``*_id`` guess."""

    _ = identity_name
    for rel in logical.relationships:
        if rel.to_entity == entity and not is_coarsening(rel.to_attribute):
            return [_attr_name(rel.to_entity, rel.to_attribute)]
        if rel.from_entity == entity and not is_coarsening(rel.from_attribute):
            return [_attr_name(rel.from_entity, rel.from_attribute)]
    return []


def canonical_schema(logical: LogicalSchema) -> PhysicalSchema:
    """One physical pattern. Normalization is a view, not a search dimension."""

    schemas = generate_physical_schemas(logical)
    snowflake = [item for item in schemas if item.pattern == "snowflake"]
    return snowflake[0] if snowflake else schemas[0]


def _fds(logical: LogicalSchema, relation: str, attributes: list[str], pk: list[str]) -> list[FunctionalDependency]:
    dependent = [item for item in attributes if item not in pk]
    if not pk or not dependent:
        return []
    return [
        FunctionalDependency(relation=relation, determinant=pk, dependent=dependent)
    ]


def _dcs(relation: str, pk: list[str]) -> list[DenialConstraint]:
    return [
        DenialConstraint(
            relation=relation,
            description="primary key uniqueness",
            columns=pk,
        )
    ]


def generate_physical_schemas(logical: LogicalSchema) -> list[PhysicalSchema]:
    covered = {_attr_name(item.entity_type, item.name) for item in logical.attributes}
    schemas = [
        _denormalized(logical, covered),
        _star(logical, covered),
        _snowflake(logical, covered),
    ]
    return schemas


def _denormalized(logical: LogicalSchema, covered: set[str]) -> PhysicalSchema:
    attributes = sorted(covered)
    pk: list[str] = []
    for entity in logical.entity_types:
        pk.extend(_pk_for(entity, logical))
    pk = [item for item in pk if item in covered] or attributes[:1]
    relation = Relation(name="fact", attributes=attributes, entity_type=None)
    return PhysicalSchema(
        id=_sid("denormalized", attributes),
        pattern="denormalized",
        relations=[relation],
        primary_keys={"fact": pk},
        foreign_keys=[],
        declared_fds=_fds(logical, "fact", attributes, pk),
        declared_dcs=_dcs("fact", pk),
        covered_attributes=set(attributes),
    )


def _star(logical: LogicalSchema, covered: set[str]) -> PhysicalSchema:
    if not logical.entity_types:
        return _denormalized(logical, covered)
    fact_entity = logical.entity_types[0]
    relations = []
    pks: dict[str, list[str]] = {}
    fks: list[ForeignKey] = []
    fds: list[FunctionalDependency] = []
    dcs: list[DenialConstraint] = []
    fact_attrs = [
        _attr_name(item.entity_type, item.name)
        for item in logical.attributes
        if item.entity_type == fact_entity
    ]
    for rel in logical.relationships:
        fact_attrs.append(_attr_name(rel.from_entity, rel.from_attribute))
    fact_attrs = sorted(set(attr for attr in fact_attrs if attr in covered))
    fact_pk = _pk_for(fact_entity, logical)
    fact_pk = [item for item in fact_pk if item in covered]
    relations.append(Relation(name="fact", attributes=fact_attrs, entity_type=fact_entity))
    pks["fact"] = fact_pk
    fds.extend(_fds(logical, "fact", fact_attrs, fact_pk))
    dcs.extend(_dcs("fact", fact_pk))
    for entity in logical.entity_types[1:]:
        attrs = [
            _attr_name(item.entity_type, item.name)
            for item in logical.attributes
            if item.entity_type == entity and _attr_name(item.entity_type, item.name) in covered
        ]
        if not attrs:
            continue
        name = f"dim_{entity}"
        pk = _pk_for(entity, logical)
        pk = [item for item in pk if item in covered]
        relations.append(Relation(name=name, attributes=attrs, entity_type=entity))
        pks[name] = pk
        fds.extend(_fds(logical, name, attrs, pk))
        dcs.extend(_dcs(name, pk))
        for rel in logical.relationships:
            if rel.to_entity == entity or rel.from_entity == entity:
                fks.append(
                    ForeignKey(
                        from_relation="fact",
                        from_attrs=[_attr_name(rel.from_entity, rel.from_attribute)],
                        to_relation=name,
                        to_attrs=[_attr_name(rel.to_entity, rel.to_attribute)],
                    )
                )
                break
    return PhysicalSchema(
        id=_sid("star", sorted(covered)),
        pattern="star",
        relations=relations,
        primary_keys=pks,
        foreign_keys=fks,
        declared_fds=fds,
        declared_dcs=dcs,
        covered_attributes=set(covered),
    )


def _snowflake(logical: LogicalSchema, covered: set[str]) -> PhysicalSchema:
    relations = []
    pks: dict[str, list[str]] = {}
    fks: list[ForeignKey] = []
    fds: list[FunctionalDependency] = []
    dcs: list[DenialConstraint] = []
    for entity in logical.entity_types:
        attrs = [
            _attr_name(item.entity_type, item.name)
            for item in logical.attributes
            if item.entity_type == entity and _attr_name(item.entity_type, item.name) in covered
        ]
        if not attrs:
            continue
        name = entity
        pk = _pk_for(entity, logical)
        pk = [item for item in pk if item in covered] or attrs[:1]
        relations.append(Relation(name=name, attributes=attrs, entity_type=entity))
        pks[name] = pk
        fds.extend(_fds(logical, name, attrs, pk))
        dcs.extend(_dcs(name, pk))
    for rel in logical.relationships:
        fks.append(
            ForeignKey(
                from_relation=rel.from_entity,
                from_attrs=[_attr_name(rel.from_entity, rel.from_attribute)],
                to_relation=rel.to_entity,
                to_attrs=[_attr_name(rel.to_entity, rel.to_attribute)],
            )
        )
    if not relations:
        return _denormalized(logical, covered)
    return PhysicalSchema(
        id=_sid("snowflake", sorted(covered)),
        pattern="snowflake",
        relations=relations,
        primary_keys=pks,
        foreign_keys=fks,
        declared_fds=fds,
        declared_dcs=dcs,
        covered_attributes=set(covered),
    )


def _sid(pattern: str, attributes: list[str]) -> str:
    digest = hashlib.sha256(f"{pattern}|{','.join(attributes)}".encode()).hexdigest()[:10]
    return f"{pattern}-{digest}"
