"""Workload-pruned schema, preprocessing, and synthesis candidate generation."""

from __future__ import annotations

from collections import defaultdict
from itertools import product
from typing import Dict, List, Optional, Sequence, Set, Tuple

from spp.population_config import (
    ER_STRATEGIES,
    MISS_STRATEGIES,
    NORM_STRATEGIES,
    TYPE_COERCION_STRATEGIES,
    UNIT_STRATEGIES,
    PopulationConfig,
)
from spp.spec import (
    PreprocessingPolicy,
    QueryRequirement,
    RelationSpec,
    SchemaDesign,
    SynthesisConfig,
)
from spp.workload_intent import WorkloadIntent


def _all_symbols(requirements: Sequence[QueryRequirement]) -> Tuple[Set[str], Set[str]]:
    entities = {entity for req in requirements for entity in req.entities}
    attributes = {attribute for req in requirements for attribute in req.attributes}
    for requirement in requirements:
        if requirement.plan:
            for reference in requirement.plan.attributes():
                entities.add(reference.entity)
                attributes.add(reference.attribute)
    return entities or {"record"}, attributes


def _covered_queries(
    relations: Sequence[RelationSpec], requirements: Sequence[QueryRequirement]
) -> Tuple[str, ...]:
    symbols = {relation.name for relation in relations}
    for relation in relations:
        symbols.update(relation.attributes)
        for column, target_table, target_column in relation.foreign_keys:
            symbols.update((column, target_table, target_column))
    return tuple(
        req.query_id for req in requirements if req.required_symbols() <= symbols
    )


def generate_schema_designs(intent: WorkloadIntent) -> List[SchemaDesign]:
    """Generate deterministic denormalized, star, and snowflake candidates.

    The generator is deliberately conservative when attribute ownership is
    ambiguous: all workload attributes remain represented, so schema variation
    changes organization rather than silently dropping query requirements.
    """
    requirements = intent.requirements
    entities, attributes = _all_symbols(requirements)
    sorted_entities = sorted(entities)
    sorted_attributes = sorted(attributes)
    attributes_by_entity: Dict[str, Set[str]] = defaultdict(set)
    semantic_types_by_attribute: Dict[Tuple[str, str], str] = {}
    for requirement in requirements:
        for entity, attribute in requirement.attribute_bindings:
            attributes_by_entity[entity].add(attribute)
        if requirement.plan:
            for reference in requirement.plan.attributes():
                attributes_by_entity[reference.entity].add(reference.attribute)
                key = (reference.entity, reference.attribute)
                current = semantic_types_by_attribute.get(key, "text")
                if current == "text" or reference.semantic_type != "text":
                    semantic_types_by_attribute[key] = reference.semantic_type
    bound_attributes = {
        attribute
        for owned in attributes_by_entity.values()
        for attribute in owned
    }
    unowned_attributes = set(sorted_attributes) - bound_attributes
    relationship_columns: Dict[Tuple[str, str], Tuple[str, str]] = {}
    for requirement in requirements:
        for left, relation, right in requirement.relationships:
            if "=" in relation:
                left_column, right_column = relation.split("=", 1)
                relationship_columns[(left, right)] = (
                    left_column,
                    right_column,
                )
                relationship_columns[(right, left)] = (
                    right_column,
                    left_column,
                )
        if requirement.plan:
            for join in requirement.plan.joins:
                relationship_columns[(join.left.entity, join.right.entity)] = (
                    join.left.attribute,
                    join.right.attribute,
                )
                relationship_columns[(join.right.entity, join.left.entity)] = (
                    join.right.attribute,
                    join.left.attribute,
                )

    def relation_types(
        relation_entity: Optional[str], relation_attributes: Sequence[str]
    ) -> Tuple[Tuple[str, str], ...]:
        result = []
        for attribute in relation_attributes:
            semantic_type = "text"
            if relation_entity is not None:
                semantic_type = semantic_types_by_attribute.get(
                    (relation_entity, attribute), semantic_type
                )
            else:
                candidates = {
                    value
                    for (entity, name), value in semantic_types_by_attribute.items()
                    if name == attribute
                }
                if len(candidates) == 1:
                    semantic_type = next(iter(candidates))
                elif candidates & {"integer", "real"}:
                    semantic_type = (
                        "real" if "real" in candidates else "integer"
                    )
            result.append((attribute, semantic_type))
        return tuple(result)

    def entity_key(entity: str) -> str:
        owned = attributes_by_entity.get(entity, set())
        for candidate in (
            entity,
            f"{entity}_id",
            f"{entity}_name",
            "id",
            "name",
        ):
            if candidate in owned:
                return candidate
        return entity
    designs: List[SchemaDesign] = []

    flat_attributes = tuple(sorted(set(sorted_entities + sorted_attributes)))
    flat_relations = (
        RelationSpec(
            name="workload_flat",
            attributes=flat_attributes,
            primary_key=entity_key(sorted_entities[0]) if sorted_entities else None,
            semantic_types=relation_types(None, flat_attributes),
        ),
    )
    designs.append(
        SchemaDesign(
            pattern="denormalized",
            relations=flat_relations,
            covered_query_ids=_covered_queries(flat_relations, requirements),
            description="One relation containing the union of workload-required symbols.",
        )
    )

    central = max(
        sorted_entities,
        key=lambda entity: (intent.entity_frequency.get(entity, 0), entity),
    )
    dimension_entities = [entity for entity in sorted_entities if entity != central]
    central_key = entity_key(central)
    central_fk_columns = {
        entity: relationship_columns.get(
            (central, entity), (f"{entity}_id", entity_key(entity))
        )
        for entity in dimension_entities
    }
    central_attrs = tuple(
        sorted(
            set(
                [central_key]
                + sorted(attributes_by_entity.get(central, set()))
                + sorted(unowned_attributes)
                + [
                    central_fk_columns[entity][0]
                    for entity in dimension_entities
                ]
                + dimension_entities
            )
        )
    )
    central_fks = tuple(
        (
            central_fk_columns[entity][0],
            entity,
            central_fk_columns[entity][1],
        )
        for entity in dimension_entities
    )
    star_relations: List[RelationSpec] = [
        RelationSpec(
            name=central,
            attributes=central_attrs,
            primary_key=central_key,
            foreign_keys=central_fks,
            semantic_types=relation_types(central, central_attrs),
        )
    ]
    for entity in dimension_entities:
        key = entity_key(entity)
        star_relations.append(
            RelationSpec(
                name=entity,
                attributes=tuple(
                    sorted({key} | attributes_by_entity.get(entity, set()))
                ),
                primary_key=key,
                semantic_types=relation_types(
                    entity,
                    tuple(
                        sorted({key} | attributes_by_entity.get(entity, set()))
                    ),
                ),
            )
        )
    designs.append(
        SchemaDesign(
            pattern="star",
            relations=tuple(star_relations),
            covered_query_ids=_covered_queries(star_relations, requirements),
            description=f"Star centered on the most workload-referenced entity '{central}'.",
        )
    )

    relationship_neighbors: Dict[str, Set[str]] = defaultdict(set)
    for requirement in requirements:
        for left, _relation, right in requirement.relationships:
            relationship_neighbors[left].add(right)
            relationship_neighbors[right].add(left)
        if requirement.plan:
            for join in requirement.plan.joins:
                relationship_neighbors[join.left.entity].add(join.right.entity)
                relationship_neighbors[join.right.entity].add(join.left.entity)
    snowflake_relations: List[RelationSpec] = []
    for index, entity in enumerate(sorted_entities):
        key = entity_key(entity)
        # Keep all otherwise-unowned attributes on the first/root relation.
        owned_attrs = set(attributes_by_entity.get(entity, set()))
        if index == 0:
            owned_attrs |= unowned_attributes
        neighbors = sorted(relationship_neighbors.get(entity, set()))
        attributes_for_entity = tuple(
            sorted(
                set(
                    [key]
                    + sorted(owned_attrs)
                    + [
                        relationship_columns.get(
                            (entity, neighbor),
                            (f"{neighbor}_id", entity_key(neighbor)),
                        )[0]
                        for neighbor in neighbors
                    ]
                    + neighbors
                )
            )
        )
        foreign_keys = tuple(
            (
                relationship_columns.get(
                    (entity, neighbor),
                    (f"{neighbor}_id", entity_key(neighbor)),
                )[0],
                neighbor,
                relationship_columns.get(
                    (entity, neighbor),
                    (f"{neighbor}_id", entity_key(neighbor)),
                )[1],
            )
            for neighbor in neighbors
        )
        snowflake_relations.append(
            RelationSpec(
                name=entity,
                attributes=attributes_for_entity,
                primary_key=key,
                foreign_keys=foreign_keys,
                semantic_types=relation_types(entity, attributes_for_entity),
            )
        )
    designs.append(
        SchemaDesign(
            pattern="snowflake",
            relations=tuple(snowflake_relations),
            covered_query_ids=_covered_queries(snowflake_relations, requirements),
            description="Entity relations linked along workload-referenced relationships.",
        )
    )

    # Do not emit an under-specified design. Different patterns may cover
    # different subsets, but at least one candidate must cover the full workload.
    query_ids = set(intent.query_ids())
    if not any(set(design.covered_query_ids) == query_ids for design in designs):
        raise ValueError("schema generator failed to produce a full-workload design")
    return designs


def generate_preprocessing_policies(
    *,
    observed_document_lengths: Optional[Sequence[int]] = None,
    exhaustive: bool = False,
) -> List[PreprocessingPolicy]:
    policies = [PreprocessingPolicy(strategy="whole_document")]
    lengths = [int(v) for v in (observed_document_lengths or []) if int(v) > 0]
    if exhaustive or not lengths or max(lengths) > 2_000:
        policies.extend(
            [
                PreprocessingPolicy(
                    strategy="chunked", chunk_size=2_000, chunk_overlap=200
                ),
                PreprocessingPolicy(
                    strategy="chunked", chunk_size=4_000, chunk_overlap=400
                ),
            ]
        )
    return policies


def _population_domains(
    intent: WorkloadIntent, *, exhaustive: bool
) -> Tuple[List[str], List[str], List[str], List[str], List[str]]:
    if exhaustive:
        return (
            list(ER_STRATEGIES),
            list(NORM_STRATEGIES),
            list(UNIT_STRATEGIES),
            list(MISS_STRATEGIES),
            list(TYPE_COERCION_STRATEGIES),
        )

    needs_entity_resolution = intent.has_joins or any(
        op in {"count", "group_by"} for op in intent.operator_frequency
    )
    ers = list(ER_STRATEGIES) if needs_entity_resolution else ["embedding_0.8"]
    units = list(UNIT_STRATEGIES) if intent.has_units else ["none"]
    coercions = (
        list(TYPE_COERCION_STRATEGIES)
        if intent.has_numeric_operations
        else ["strict", "permissive"]
    )
    # Keep cheap and semantic alternatives; remove expensive LLM imputation
    # when no filter/aggregate can observe missing-value behavior.
    missing_observable = any(
        op in {"filter", "count", "sum", "avg", "min", "max", "group_by"}
        for op in intent.operator_frequency
    )
    misses = list(MISS_STRATEGIES) if missing_observable else ["drop", "mode"]
    return ers, list(NORM_STRATEGIES), units, misses, coercions


def generate_synthesis_configs(
    intent: WorkloadIntent,
    *,
    observed_document_lengths: Optional[Sequence[int]] = None,
    exhaustive: bool = False,
) -> List[SynthesisConfig]:
    schemas = generate_schema_designs(intent)
    policies = generate_preprocessing_policies(
        observed_document_lengths=observed_document_lengths,
        exhaustive=exhaustive,
    )
    ers, norms, units, misses, coercions = _population_domains(
        intent, exhaustive=exhaustive
    )
    population_configs = [
        PopulationConfig(
            er_strategy=er,
            norm_strategy=norm,
            unit_strategy=unit,
            miss_strategy=miss,
            type_coercion=coercion,
        )
        for er, norm, unit, miss, coercion in product(
            ers, norms, units, misses, coercions
        )
    ]
    configs = [
        SynthesisConfig(
            schema=schema,
            population=population,
            preprocessing=policy,
        )
        for schema, policy, population in product(
            schemas, policies, population_configs
        )
        if schema.covered_query_ids
    ]
    return sorted(configs, key=lambda config: config.config_id)
