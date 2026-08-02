"""Workload-wide, value-free contracts for evidence-backed extraction.

The intent analyzer describes each query independently. Extraction needs the
dual view: one shared symbol table that retains every query's use of a symbol.
Natural-language hints remain attached to their query ids because they are
legitimate synthesis input and disambiguate field/taxonomy meaning. This module
contains no corpus- or benchmark-specific vocabulary.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from spp.spec import AttributeRef, PredicateSpec, QueryRequirement

if TYPE_CHECKING:
    from spp.workload_intent import WorkloadIntent


QueryContext = Tuple[Tuple[str, Tuple[str, ...]], ...]
QueryHints = Tuple[Tuple[str, str], ...]


def _ordered(values: Iterable[str]) -> Tuple[str, ...]:
    """Return non-empty strings once, in deterministic lexical order."""

    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


def _symbol_key(value: object) -> str:
    """Normalize only symbol typography, never a possible data value."""

    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _freeze_context(context: Mapping[str, Iterable[str]]) -> QueryContext:
    return tuple(
        (query_id, _ordered(roles))
        for query_id, roles in sorted(context.items())
        if query_id
    )


@dataclass(frozen=True)
class EntityContract:
    """A logical entity shared by all workload queries.

    ``alternatives`` contains evidenced aliases rather than silently selecting
    one spelling. ``contexts`` maps query ids to structural roles such as
    ``projection`` or ``join`` and ``query_hints`` preserves the authorized NL
    meaning. ``identity_attributes`` lists only workload-observed join keys
    that may identify instances.
    """

    name: str
    alternatives: Tuple[str, ...] = ()
    query_ids: Tuple[str, ...] = ()
    contexts: QueryContext = ()
    identity_attributes: Tuple[str, ...] = ()
    query_hints: QueryHints = ()

    def __post_init__(self) -> None:
        if not _symbol_key(self.name):
            raise ValueError("entity contract requires a non-empty name")

    @property
    def symbols(self) -> Tuple[str, ...]:
        """Return the canonical entity name followed by its aliases."""

        return tuple(dict.fromkeys((self.name, *self.alternatives)))

    @property
    def contract_id(self) -> str:
        return _object_contract_id("entity", self)


@dataclass(frozen=True)
class AttributeContract:
    """A field requested by the workload, including unresolved alternatives.

    ``entity`` is empty only when ownership was not resolved by the intent.
    In that case ``entity_alternatives`` retains all possible owners.
    ``semantic_types`` and ``units`` are alternative constraints, not votes;
    validators accept a value supported by any retained alternative.
    """

    entity: str
    name: str
    entity_alternatives: Tuple[str, ...] = ()
    alternatives: Tuple[str, ...] = ()
    semantic_types: Tuple[str, ...] = ("text",)
    units: Tuple[str, ...] = ()
    query_ids: Tuple[str, ...] = ()
    contexts: QueryContext = ()
    operators: Tuple[str, ...] = ()
    query_hints: QueryHints = ()

    def __post_init__(self) -> None:
        if not _symbol_key(self.name):
            raise ValueError("attribute contract requires a non-empty name")
        allowed = {"text", "integer", "real", "date", "boolean"}
        unsupported = set(self.semantic_types) - allowed
        if unsupported:
            raise ValueError(f"unsupported semantic types: {sorted(unsupported)}")
        if not self.entity and not self.entity_alternatives:
            # Ownerless fields are valid for schema-poor intents; extraction
            # routes them over the unpartitioned corpus.
            return

    @property
    def owners(self) -> Tuple[str, ...]:
        """Return every possible owner without resolving an ambiguity."""

        return tuple(
            dict.fromkeys(
                value
                for value in (self.entity, *self.entity_alternatives)
                if value
            )
        )

    @property
    def symbols(self) -> Tuple[str, ...]:
        """Return the canonical field name followed by its aliases."""

        return tuple(dict.fromkeys((self.name, *self.alternatives)))

    @property
    def contract_id(self) -> str:
        return _object_contract_id("attribute", self)


@dataclass(frozen=True)
class RelationshipContract:
    """A workload-observed relationship and all endpoint alternatives."""

    name: str
    left_entity: str
    right_entity: str
    alternatives: Tuple[str, ...] = ()
    left_attributes: Tuple[str, ...] = ()
    right_attributes: Tuple[str, ...] = ()
    query_ids: Tuple[str, ...] = ()
    contexts: QueryContext = ()
    query_hints: QueryHints = ()

    def __post_init__(self) -> None:
        if not self.left_entity or not self.right_entity:
            raise ValueError("relationship endpoints must be non-empty")

    @property
    def endpoint_pairs(self) -> Tuple[Tuple[Optional[str], Optional[str]], ...]:
        """Return retained join-key alternatives without inventing pairings."""

        if not self.left_attributes and not self.right_attributes:
            return ((None, None),)
        width = max(len(self.left_attributes), len(self.right_attributes))
        return tuple(
            (
                self.left_attributes[index]
                if index < len(self.left_attributes)
                else None,
                self.right_attributes[index]
                if index < len(self.right_attributes)
                else None,
            )
            for index in range(width)
        )

    @property
    def contract_id(self) -> str:
        return _object_contract_id("relationship", self)


@dataclass(frozen=True)
class WorkloadContract:
    """Immutable extraction contract compiled from a complete workload.

    The payload is safe to cache and prompt with because it contains only the
    NL workload's schema symbols, structural roles, semantic types, units, and
    query hints. It never serializes reference SQL, expected answers, or source
    data.
    """

    entities: Tuple[EntityContract, ...]
    attributes: Tuple[AttributeContract, ...]
    relationships: Tuple[RelationshipContract, ...]
    query_contexts: QueryContext = ()
    version: int = 1

    def entity(self, name: str) -> Optional[EntityContract]:
        """Look up an entity by canonical name or retained alias."""

        key = _symbol_key(name)
        return next(
            (
                entity
                for entity in self.entities
                if key in {_symbol_key(value) for value in entity.symbols}
            ),
            None,
        )

    def attributes_for(self, entity: str) -> Tuple[AttributeContract, ...]:
        """Return fields that can belong to ``entity``."""

        key = _symbol_key(entity)
        return tuple(
            attribute
            for attribute in self.attributes
            if key in {_symbol_key(owner) for owner in attribute.owners}
        )

    def to_payload(self) -> dict:
        """Return a deterministic, JSON-compatible cache payload."""

        return asdict(self)

    @property
    def fingerprint(self) -> str:
        """Content hash used to share extraction artifacts across candidates."""

        encoded = json.dumps(
            self.to_payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _object_contract_id(kind: str, value: object) -> str:
    payload = json.dumps(
        asdict(value), sort_keys=True, separators=(",", ":")
    )
    return f"{kind}:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonicalization(intent: WorkloadIntent) -> Mapping[str, Any]:
    """Read only symbol-alias diagnostics from known analyzer envelopes."""

    diagnostics: object = intent.analysis_diagnostics
    if not isinstance(diagnostics, Mapping):
        return {}
    workload = diagnostics.get("_workload", diagnostics)
    if isinstance(workload, Mapping):
        value = workload.get("canonicalization", workload)
        if isinstance(value, Mapping):
            return value
    return {}


def _plan_uses(
    requirement: QueryRequirement,
) -> List[Tuple[AttributeRef, str]]:
    """Collect field roles while deliberately discarding predicate values."""

    plan = requirement.plan
    if plan is None:
        return []
    uses: List[Tuple[AttributeRef, str]] = []
    uses.extend((reference, "projection") for reference in plan.projections)
    uses.extend((reference, "group_by") for reference in plan.group_by)
    for aggregate in plan.aggregates:
        if aggregate.attribute is not None:
            uses.append((aggregate.attribute, f"aggregate:{aggregate.function}"))
    for condition in plan.having:
        if condition.aggregate.attribute is not None:
            uses.append(
                (
                    condition.aggregate.attribute,
                    f"having:{condition.aggregate.function}:{condition.operator}",
                )
            )

    def visit(predicate: Optional[PredicateSpec]) -> None:
        if predicate is None:
            return
        if predicate.kind == "predicate" and predicate.attribute is not None:
            uses.append((predicate.attribute, f"filter:{predicate.operator}"))
        for child in predicate.children:
            visit(child)

    visit(plan.predicate)
    for join in plan.joins:
        uses.append((join.left, "join:left"))
        uses.append((join.right, "join:right"))
    return uses


def _relationship_name(left_attribute: str, right_attribute: str) -> str:
    if left_attribute or right_attribute:
        return f"{left_attribute}={right_attribute}"
    return "related"


def compile_workload_contract(intent: WorkloadIntent) -> WorkloadContract:
    """Compile query-local intent into one literal-free extraction contract.

    Shared entity/attribute symbols are merged across queries.  Aliases,
    conflicting semantic types, unresolved owners, relationship labels, join
    keys, units, and per-query structural roles remain explicit alternatives.
    Query prose is retained only as an explicitly labelled NL hint; typed
    predicate values remain represented by the query plan, not copied into a
    separate schema rule.
    """

    canonicalization = _canonicalization(intent)
    query_hints = {
        str(requirement.query_id): str(requirement.text)
        for requirement in intent.requirements
    }
    entity_alias_map = {
        _symbol_key(alias): str(canonical).strip()
        for alias, canonical in (
            canonicalization.get("entity_aliases", {}).items()
            if isinstance(canonicalization.get("entity_aliases"), Mapping)
            else ()
        )
        if _symbol_key(alias) and _symbol_key(canonical)
    }

    def canonical_entity(value: object) -> str:
        rendered = str(value or "").strip()
        return entity_alias_map.get(_symbol_key(rendered), rendered)

    entity_aliases: Dict[str, Set[str]] = defaultdict(set)
    attribute_aliases: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    for alias, canonical in entity_alias_map.items():
        entity_aliases[_symbol_key(canonical)].add(alias)
    alias_evidence = canonicalization.get("alias_evidence", ())
    if isinstance(alias_evidence, Sequence) and not isinstance(
        alias_evidence, (str, bytes)
    ):
        for item in alias_evidence:
            if not isinstance(item, Mapping):
                continue
            if item.get("kind") == "entity":
                canonical = canonical_entity(item.get("canonical"))
                alias = str(item.get("alias", "")).strip()
                if canonical and alias:
                    entity_aliases[_symbol_key(canonical)].add(alias)
            elif item.get("kind") == "attribute":
                entity = canonical_entity(item.get("entity"))
                canonical = str(item.get("canonical", "")).strip()
                alias = str(item.get("alias", "")).strip()
                if entity and canonical and alias:
                    attribute_aliases[
                        (_symbol_key(entity), _symbol_key(canonical))
                    ].add(alias)

    entity_names: Dict[str, str] = {}
    entity_context: Dict[str, Dict[str, Set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    identity_attributes: Dict[str, Set[str]] = defaultdict(set)

    # Attribute aggregation key includes all possible owners so an unresolved
    # owner is not accidentally fused with a resolved one.
    attributes: Dict[
        Tuple[str, str, Tuple[str, ...]], Dict[str, Any]
    ] = {}
    relationships: Dict[Tuple[str, str], Dict[str, Any]] = {}
    workload_context: Dict[str, Set[str]] = defaultdict(set)

    def observe_entity(entity: str, query_id: str, role: str) -> str:
        entity = canonical_entity(entity)
        key = _symbol_key(entity)
        if not key:
            return ""
        entity_names.setdefault(key, entity)
        entity_context[key][query_id].add(role)
        return entity_names[key]

    def observe_attribute(
        *,
        entity: str,
        owner_alternatives: Iterable[str],
        name: str,
        semantic_type: str,
        query_id: str,
        role: str,
        operators: Iterable[str],
        units: Iterable[str],
    ) -> None:
        rendered_name = str(name or "").strip()
        if not _symbol_key(rendered_name):
            return
        owner = canonical_entity(entity)
        alternatives = _ordered(
            canonical_entity(value) for value in owner_alternatives
        )
        if owner:
            observe_entity(owner, query_id, role)
            alternatives = tuple(
                value
                for value in alternatives
                if _symbol_key(value) != _symbol_key(owner)
            )
        else:
            for candidate in alternatives:
                observe_entity(candidate, query_id, f"possible_owner:{role}")
        key = (_symbol_key(owner), _symbol_key(rendered_name), alternatives)
        state = attributes.setdefault(
            key,
            {
                "entity": owner,
                "name": rendered_name,
                "entity_alternatives": set(alternatives),
                "semantic_types": set(),
                "units": set(),
                "operators": set(),
                "context": defaultdict(set),
            },
        )
        candidate_type = str(semantic_type or "text").strip().lower()
        if candidate_type not in {"text", "integer", "real", "date", "boolean"}:
            candidate_type = "text"
        state["semantic_types"].add(candidate_type)
        state["units"].update(str(value).strip() for value in units if str(value).strip())
        state["operators"].update(
            str(value).strip() for value in operators if str(value).strip()
        )
        state["context"][query_id].add(role)

    for requirement in intent.requirements:
        query_id = str(requirement.query_id)
        plan_uses = _plan_uses(requirement)
        for operator in requirement.operators:
            workload_context[query_id].add(f"operator:{operator}")
        for unit in requirement.units:
            workload_context[query_id].add(f"unit:{unit}")

        query_entities = _ordered(
            canonical_entity(value)
            for value in (
                *requirement.entities,
                *(entity for entity, _attribute in requirement.attribute_bindings),
                *(
                    reference.entity
                    for reference, _role in plan_uses
                ),
            )
        )
        for entity in query_entities:
            observe_entity(entity, query_id, "mentioned")

        observed_names: Set[Tuple[str, str]] = set()
        plan_types: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
        for reference, _role in plan_uses:
            plan_types[
                (
                    _symbol_key(canonical_entity(reference.entity)),
                    _symbol_key(reference.attribute),
                )
            ].add(reference.semantic_type)
        for entity, attribute in requirement.attribute_bindings:
            owner = canonical_entity(entity)
            binding_key = (_symbol_key(owner), _symbol_key(attribute))
            observed_names.add(binding_key)
            for semantic_type in plan_types.get(binding_key, {"text"}):
                observe_attribute(
                    entity=owner,
                    owner_alternatives=(),
                    name=attribute,
                    semantic_type=semantic_type,
                    query_id=query_id,
                    role="binding",
                    operators=requirement.operators,
                    units=(),
                )

        numeric_refs = {
            (_symbol_key(reference.entity), _symbol_key(reference.attribute))
            for reference, role in plan_uses
            if reference.semantic_type in {"integer", "real"}
            or role.startswith(("aggregate:", "having:"))
        }
        unit_targets = numeric_refs if len(numeric_refs) == 1 else set()
        for reference, role in plan_uses:
            owner = canonical_entity(reference.entity)
            ref_key = (_symbol_key(owner), _symbol_key(reference.attribute))
            observed_names.add(ref_key)
            observe_attribute(
                entity=owner,
                owner_alternatives=(),
                name=reference.attribute,
                semantic_type=reference.semantic_type,
                query_id=query_id,
                role=role,
                operators=requirement.operators,
                units=requirement.units if ref_key in unit_targets else (),
            )

        # Preserve unbound owner alternatives instead of assigning a field to
        # whichever entity happens to occur first.
        for attribute in requirement.attributes:
            if any(
                name == _symbol_key(attribute) for _entity, name in observed_names
            ):
                continue
            if len(query_entities) == 1:
                owner, possible = query_entities[0], ()
            else:
                owner, possible = "", query_entities
            observe_attribute(
                entity=owner,
                owner_alternatives=possible,
                name=attribute,
                semantic_type="text",
                query_id=query_id,
                role="mentioned",
                operators=requirement.operators,
                units=requirement.units if len(requirement.attributes) == 1 else (),
            )

        def observe_relationship(
            left: str,
            right: str,
            *,
            name: str,
            left_attribute: str = "",
            right_attribute: str = "",
            role: str,
        ) -> None:
            left_name = observe_entity(left, query_id, role)
            right_name = observe_entity(right, query_id, role)
            if not left_name or not right_name:
                return
            key = (_symbol_key(left_name), _symbol_key(right_name))
            state = relationships.setdefault(
                key,
                {
                    "left_entity": left_name,
                    "right_entity": right_name,
                    "names": set(),
                    "left_attributes": set(),
                    "right_attributes": set(),
                    "context": defaultdict(set),
                },
            )
            state["names"].add(str(name or "related").strip() or "related")
            if left_attribute:
                state["left_attributes"].add(left_attribute)
                identity_attributes[key[0]].add(left_attribute)
            if right_attribute:
                state["right_attributes"].add(right_attribute)
                identity_attributes[key[1]].add(right_attribute)
            state["context"][query_id].add(role)

        for left, relation, right in requirement.relationships:
            rendered = str(relation).strip()
            left_attribute = right_attribute = ""
            if "=" in rendered:
                left_attribute, right_attribute = (
                    part.strip() for part in rendered.split("=", 1)
                )
                observe_attribute(
                    entity=left,
                    owner_alternatives=(),
                    name=left_attribute,
                    semantic_type="text",
                    query_id=query_id,
                    role="join:left",
                    operators=requirement.operators,
                    units=(),
                )
                observe_attribute(
                    entity=right,
                    owner_alternatives=(),
                    name=right_attribute,
                    semantic_type="text",
                    query_id=query_id,
                    role="join:right",
                    operators=requirement.operators,
                    units=(),
                )
            observe_relationship(
                left,
                right,
                name=rendered or _relationship_name(
                    left_attribute, right_attribute
                ),
                left_attribute=left_attribute,
                right_attribute=right_attribute,
                role="relationship",
            )
        if requirement.plan is not None:
            for join in requirement.plan.joins:
                observe_relationship(
                    join.left.entity,
                    join.right.entity,
                    name=_relationship_name(
                        join.left.attribute, join.right.attribute
                    ),
                    left_attribute=join.left.attribute,
                    right_attribute=join.right.attribute,
                    role=f"join:{join.join_type}",
                )

    entity_contracts = tuple(
        EntityContract(
            name=entity_names[key],
            alternatives=_ordered(
                value
                for value in entity_aliases.get(key, set())
                if _symbol_key(value) != key
            ),
            query_ids=tuple(sorted(entity_context[key])),
            contexts=_freeze_context(entity_context[key]),
            identity_attributes=_ordered(identity_attributes.get(key, set())),
            query_hints=tuple(
                (query_id, query_hints[query_id])
                for query_id in sorted(entity_context[key])
            ),
        )
        for key in sorted(entity_names)
    )

    attribute_contracts: List[AttributeContract] = []
    for (entity_key, name_key, _owners), state in sorted(attributes.items()):
        aliases = attribute_aliases.get((entity_key, name_key), set())
        attribute_contracts.append(
            AttributeContract(
                entity=state["entity"],
                name=state["name"],
                entity_alternatives=_ordered(state["entity_alternatives"]),
                alternatives=_ordered(
                    value
                    for value in aliases
                    if _symbol_key(value) != name_key
                ),
                semantic_types=_ordered(state["semantic_types"]) or ("text",),
                units=_ordered(state["units"]),
                query_ids=tuple(sorted(state["context"])),
                contexts=_freeze_context(state["context"]),
                operators=_ordered(state["operators"]),
                query_hints=tuple(
                    (query_id, query_hints[query_id])
                    for query_id in sorted(state["context"])
                ),
            )
        )

    relationship_contracts: List[RelationshipContract] = []
    for state in relationships.values():
        names = _ordered(state["names"]) or ("related",)
        relationship_contracts.append(
            RelationshipContract(
                name=names[0],
                alternatives=names[1:],
                left_entity=state["left_entity"],
                right_entity=state["right_entity"],
                left_attributes=_ordered(state["left_attributes"]),
                right_attributes=_ordered(state["right_attributes"]),
                query_ids=tuple(sorted(state["context"])),
                contexts=_freeze_context(state["context"]),
                query_hints=tuple(
                    (query_id, query_hints[query_id])
                    for query_id in sorted(state["context"])
                ),
            )
        )

    return WorkloadContract(
        entities=entity_contracts,
        attributes=tuple(
            sorted(
                attribute_contracts,
                key=lambda item: (
                    _symbol_key(item.entity),
                    _symbol_key(item.name),
                    tuple(_symbol_key(value) for value in item.entity_alternatives),
                ),
            )
        ),
        relationships=tuple(
            sorted(
                relationship_contracts,
                key=lambda item: (
                    _symbol_key(item.left_entity),
                    _symbol_key(item.right_entity),
                    _symbol_key(item.name),
                ),
            )
        ),
        query_contexts=_freeze_context(workload_context),
    )
