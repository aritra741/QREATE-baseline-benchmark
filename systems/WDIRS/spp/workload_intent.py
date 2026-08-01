"""Ground-truth-free workload intent analysis.

Natural-language queries are converted into a schema-independent requirement
IR. SQL input remains supported for diagnostics and migration experiments.
The analyzer never reads UDA-Bench tables or attributes metadata.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from json_repair import repair_json

from spp.budget_ledger import GlobalBudgetLedger
from spp.budgeted_llm import BudgetedLLMClient
from spp.spec import (
    AggregateSpec,
    AttributeRef,
    HavingSpec,
    JoinSpec,
    PredicateSpec,
    QueryPlan,
    QueryRequirement,
)
from spp.value_normalization import canonical_date

try:
    import sqlglot
    from sqlglot import exp
except ImportError:  # pragma: no cover - surfaced only in minimal deployments
    sqlglot = None
    exp = None


_AGGREGATES = {
    "count": "count",
    "how many": "count",
    "average": "avg",
    "avg": "avg",
    "sum": "sum",
    "total": "sum",
    "minimum": "min",
    "smallest": "min",
    "maximum": "max",
    "largest": "max",
}
_UNIT_RE = re.compile(
    r"\b(usd|dollars?|euros?|pounds?|kg|kilograms?|g|grams?|km|kilometers?|"
    r"miles?|meters?|percent|%)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "by", "did",
    "do", "does", "for", "from", "had", "has", "have", "how", "in", "is",
    "it", "of", "on", "or", "that", "the", "their", "to", "was", "were",
    "what", "when", "which", "who", "with",
}


@dataclass(frozen=True)
class WorkloadIntent:
    requirements: Tuple[QueryRequirement, ...]
    entity_frequency: Mapping[str, int]
    attribute_frequency: Mapping[str, int]
    operator_frequency: Mapping[str, int]
    analysis_diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def has_joins(self) -> bool:
        return any(
            r.relationships or (r.plan and r.plan.joins)
            for r in self.requirements
        )

    @property
    def has_units(self) -> bool:
        return any(r.units for r in self.requirements)

    @property
    def has_numeric_operations(self) -> bool:
        numeric_ops = {"count", "sum", "avg", "min", "max", "range"}
        return any(
            numeric_ops.intersection(r.operators)
            or (
                r.plan
                and any(
                    aggregate.function in numeric_ops
                    for aggregate in r.plan.aggregates
                )
            )
            for r in self.requirements
        )

    def query_ids(self) -> Tuple[str, ...]:
        return tuple(r.query_id for r in self.requirements)


@dataclass(frozen=True)
class SchemaVocabulary:
    entities: Tuple[str, ...]
    attributes: Mapping[str, Tuple[str, ...]]
    joins: Tuple[Tuple[str, str, str, str], ...] = ()


def schema_vocabulary_from_sql(
    sql_queries: Sequence[str],
) -> SchemaVocabulary:
    """Derive a canonical, ground-truth-free schema vocabulary from SQL."""
    attributes: Dict[str, set[str]] = {}
    joins: List[Tuple[str, str, str, str]] = []
    for index, sql in enumerate(sql_queries):
        requirement = _sql_requirement(f"schema_{index}", sql)
        for entity in requirement.entities:
            attributes.setdefault(entity, set())
        for entity, attribute in requirement.attribute_bindings:
            attributes.setdefault(entity, set()).add(attribute)
        if requirement.plan:
            for reference in requirement.plan.attributes():
                attributes.setdefault(reference.entity, set()).add(
                    reference.attribute
                )
            for join in requirement.plan.joins:
                value = (
                    join.left.entity,
                    join.left.attribute,
                    join.right.entity,
                    join.right.attribute,
                )
                if value not in joins:
                    joins.append(value)
    return SchemaVocabulary(
        entities=tuple(sorted(attributes)),
        attributes={
            entity: tuple(sorted(names))
            for entity, names in sorted(attributes.items())
        },
        joins=tuple(joins),
    )


def _is_sql(text: str) -> bool:
    return bool(re.match(r"^\s*(select|with)\b", text, re.IGNORECASE))


def _canonical_entity(
    value: object,
    entity_vocabulary: Sequence[str],
    default_entity: str = "",
) -> str:
    entity = str(value or "").strip().lower()
    allowed = tuple(
        dict.fromkeys(str(item).strip().lower() for item in entity_vocabulary)
    )
    if not allowed or entity in allowed:
        return entity
    parts = set(re.split(r"[^a-z0-9]+", entity))
    matches = [candidate for candidate in allowed if candidate in parts]
    if len(matches) == 1:
        return matches[0]
    # Use a high-confidence, vocabulary-bounded lexical match. This is generic
    # similarity over the full symbol—not a singular/plural rewrite rule.
    ranked = sorted(
        (
            SequenceMatcher(None, entity, candidate).ratio(),
            candidate,
        )
        for candidate in allowed
    )
    if ranked:
        best_score, best = ranked[-1]
        runner_up = ranked[-2][0] if len(ranked) > 1 else 0.0
        if best_score >= 0.82 and best_score - runner_up >= 0.08:
            return best
    return default_entity if default_entity in allowed else ""


def _attribute_ref(
    payload: object,
    entity_vocabulary: Sequence[str] = (),
    default_entity: str = "",
    attribute_vocabulary: Optional[Mapping[str, Sequence[str]]] = None,
) -> Optional[AttributeRef]:
    if not isinstance(payload, Mapping):
        return None
    if isinstance(payload.get("attribute"), Mapping):
        return _attribute_ref(
            payload["attribute"],
            entity_vocabulary,
            default_entity,
            attribute_vocabulary,
        )
    raw_entity = str(payload.get("entity", "")).strip().lower()
    entity = _canonical_entity(
        raw_entity, entity_vocabulary, default_entity
    )
    attribute = str(payload.get("attribute", "")).strip().lower()
    if (
        entity_vocabulary
        and raw_entity
        and raw_entity not in entity_vocabulary
        and entity != raw_entity
        and attribute in {"name", "label", "title", "value"}
    ):
        attribute = re.sub(r"[^a-z0-9]+", "_", raw_entity).strip("_")
    for prefix in (raw_entity, entity):
        if prefix:
            attribute = re.sub(
                rf"^{re.escape(prefix)}[./:]+", "", attribute
            )
    if attribute_vocabulary:
        candidates = [
            (owner, str(name).lower())
            for owner, names in attribute_vocabulary.items()
            for name in names
        ]
        exact = [
            (owner, name)
            for owner, name in candidates
            if name == attribute and (owner == entity or not entity)
        ]
        if exact:
            entity, attribute = exact[0]
        elif candidates:
            attribute_tokens = set(attribute.split("_"))

            def similarity(candidate: Tuple[str, str]) -> float:
                owner, name = candidate
                name_tokens = set(name.split("_"))
                overlap = (
                    len(attribute_tokens & name_tokens)
                    / max(len(attribute_tokens | name_tokens), 1)
                )
                sequence = SequenceMatcher(None, attribute, name).ratio()
                owner_bonus = 0.15 if owner == entity else 0.0
                return max(overlap, sequence) + owner_bonus

            best = max(candidates, key=similarity)
            if similarity(best) >= 0.58:
                entity, attribute = best
    semantic_type = str(
        payload.get("semantic_type", "text")
    ).strip().lower()
    if not entity or not attribute:
        return None
    aliases = {
        "str": "text", "string": "text", "int": "integer",
        "float": "real", "number": "real", "numeric": "real",
        "datetime": "date", "bool": "boolean",
    }
    semantic_type = aliases.get(semantic_type, semantic_type)
    try:
        return AttributeRef(entity, attribute, semantic_type)
    except ValueError:
        return AttributeRef(entity, attribute, "text")


def _predicate_spec(
    payload: object,
    entity_vocabulary: Sequence[str] = (),
    default_entity: str = "",
    attribute_vocabulary: Optional[Mapping[str, Sequence[str]]] = None,
) -> Optional[PredicateSpec]:
    if not isinstance(payload, Mapping):
        return None
    kind = str(payload.get("kind", "predicate")).strip().lower()
    if kind in {"and", "or"}:
        raw_children = payload.get("children", [])
        if not isinstance(raw_children, (list, tuple)):
            return None
        children = tuple(
            child
            for child in (
                _predicate_spec(
                    value,
                    entity_vocabulary,
                    default_entity,
                    attribute_vocabulary,
                )
                for value in raw_children
            )
            if child is not None
        )
        return PredicateSpec(kind=kind, children=children) if children else None
    reference = _attribute_ref(
        payload.get("attribute")
        if isinstance(payload.get("attribute"), Mapping)
        else payload,
        entity_vocabulary,
        default_entity,
        attribute_vocabulary,
    )
    if reference is None:
        return None
    operator = str(payload.get("operator", "=")).strip().lower()
    operator = {
        "==": "=",
        "eq": "=",
        "<>": "!=",
        "ne": "!=",
        "neq": "!=",
        "lt": "<",
        "lte": "<=",
        "le": "<=",
        "gt": ">",
        "gte": ">=",
        "ge": ">=",
        "like": "contains",
        "is null": "is_null",
        "not null": "is_not_null",
        "is not null": "is_not_null",
    }.get(operator, operator)
    try:
        return PredicateSpec(
            attribute=reference,
            operator=operator,
            value=payload.get("value"),
        )
    except ValueError:
        return None


def _query_plan(
    payload: object,
    entity_vocabulary: Sequence[str] = (),
    default_entity: str = "",
    attribute_vocabulary: Optional[Mapping[str, Sequence[str]]] = None,
) -> Optional[QueryPlan]:
    if not isinstance(payload, Mapping):
        return None

    def refs(name: str) -> Tuple[AttributeRef, ...]:
        values = payload.get(name, [])
        if not isinstance(values, (list, tuple)):
            return ()
        return tuple(
            reference
            for reference in (
                _attribute_ref(
                    value,
                    entity_vocabulary,
                    default_entity,
                    attribute_vocabulary,
                )
                for value in values
            )
            if reference is not None
        )

    aggregates: List[AggregateSpec] = []
    values = payload.get("aggregates", [])
    if isinstance(values, (list, tuple)):
        for value in values:
            if not isinstance(value, Mapping):
                continue
            function = str(value.get("function", "")).strip().lower()
            reference = _attribute_ref(
                value.get("attribute"),
                entity_vocabulary,
                default_entity,
                attribute_vocabulary,
            )
            try:
                aggregates.append(
                    AggregateSpec(
                        function=function,
                        attribute=reference,
                        alias=str(value.get("alias", "")).strip().lower(),
                        distinct=bool(value.get("distinct", False)),
                    )
                )
            except ValueError:
                continue

    having: List[HavingSpec] = []
    having_values = payload.get("having", [])
    if isinstance(having_values, Mapping):
        having_values = [having_values]
    if isinstance(having_values, (list, tuple)):
        for value in having_values:
            if not isinstance(value, Mapping):
                continue
            aggregate_payload = value.get("aggregate", value)
            if not isinstance(aggregate_payload, Mapping):
                continue
            reference = _attribute_ref(
                aggregate_payload.get("attribute"),
                entity_vocabulary,
                default_entity,
                attribute_vocabulary,
            )
            try:
                aggregate = AggregateSpec(
                    function=str(
                        aggregate_payload.get("function", "")
                    ).strip().lower(),
                    attribute=reference,
                    alias=str(
                        aggregate_payload.get("alias", "")
                    ).strip().lower(),
                    distinct=bool(
                        aggregate_payload.get("distinct", False)
                    ),
                )
                operator = str(value.get("operator", "")).strip().lower()
                operator = {
                    "==": "=",
                    "<>": "!=",
                    "greater_than": ">",
                    "greater_than_or_equal": ">=",
                    "less_than": "<",
                    "less_than_or_equal": "<=",
                }.get(operator, operator)
                having.append(
                    HavingSpec(
                        aggregate=aggregate,
                        operator=operator,
                        value=value.get("value"),
                    )
                )
            except ValueError:
                continue

    joins: List[JoinSpec] = []
    values = payload.get("joins", [])
    if isinstance(values, (list, tuple)):
        for value in values:
            if not isinstance(value, Mapping):
                continue
            left = _attribute_ref(
                value.get("left"),
                entity_vocabulary,
                default_entity,
                attribute_vocabulary,
            )
            right = _attribute_ref(
                value.get("right"),
                entity_vocabulary,
                default_entity,
                attribute_vocabulary,
            )
            if left is None or right is None:
                continue
            join_type = str(
                value.get("join_type", "inner")
            ).strip().lower()
            join_type = {
                "left join": "left",
                "left outer": "left",
                "left outer join": "left",
                "inner join": "inner",
            }.get(join_type, join_type)
            try:
                joins.append(
                    JoinSpec(
                        left,
                        right,
                        join_type,
                    )
                )
            except ValueError:
                continue
    plan = QueryPlan(
        projections=refs("projections"),
        group_by=refs("group_by"),
        aggregates=tuple(aggregates),
        predicate=_predicate_spec(
            payload.get("predicate"),
            entity_vocabulary,
            default_entity,
            attribute_vocabulary,
        ),
        joins=tuple(joins),
        having=tuple(having),
    )
    return plan if plan.attributes() or plan.aggregates or plan.having else None


def _expected_aggregate(text: str) -> Optional[str]:
    lowered = text.lower()
    if re.search(r"\b(average|mean)\b", lowered):
        return "avg"
    if re.search(
        r"\b(fewest|lowest|smallest|minimum|youngest|earliest)\b", lowered
    ):
        return "min"
    if re.search(
        r"\b(largest|highest|greatest|maximum|oldest|latest|most)\b", lowered
    ):
        return "max"
    if re.search(r"\b(total|combined|altogether|sum)\b", lowered):
        return "sum"
    # Treat ``count`` as an aggregate only when it is used as an instruction.
    # It can also be part of an arbitrary stored measure's natural-language
    # label, so a bare occurrence is insufficient.
    if re.search(
        r"\bhow many\b"
        r"|(?:^|[.!?]\s+|,\s+)\s*(?:please\s+)?count\b"
        r"|\bcount\s+(?:the|all|each|every|non[- ]?(?:missing|null))\b",
        lowered,
    ):
        return "count"
    return None


def _expects_group_cardinality_having(text: str) -> bool:
    """Detect explicit group-member count restrictions, not scalar magnitudes."""
    return bool(
        re.search(
            r"\bwith\s+(?:more|fewer|less)\s+than\s+"
            r"(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
            r"(?!(?:hundred|thousand|million|billion)\b)[a-z][a-z0-9_-]*",
            text.lower(),
        )
    )


def _repair_plan_aggregate(
    plan: Optional[QueryPlan],
    text: str,
    *,
    context_references: Sequence[AttributeRef] = (),
    attribute_vocabulary: Optional[Mapping[str, Sequence[str]]] = None,
) -> Optional[QueryPlan]:
    if plan is None:
        return None
    expected = _expected_aggregate(text)
    if expected is None:
        return plan


    aggregates = list(plan.aggregates)
    projections = list(plan.projections)
    grouped = set(plan.group_by)
    if not aggregates:
        candidates = [
            reference
            for reference in (*projections, *context_references)
            if reference not in grouped
        ]
        if expected != "count" and attribute_vocabulary:
            lowered = text.lower()
            existing = {
                (reference.entity, reference.attribute): reference
                for reference in (*plan.attributes(), *context_references)
            }
            candidates.extend(
                existing.get(
                    (entity, attribute),
                    AttributeRef(
                        entity,
                        attribute,
                        "real" if expected == "avg" else "integer",
                    ),
                )
                for entity, attributes in attribute_vocabulary.items()
                for attribute in attributes
                if all(
                    token in lowered
                    for token in attribute.replace("_", " ").split()
                )
            )
        candidates = list(dict.fromkeys(candidates))
        target = candidates[-1] if candidates and expected != "count" else None
        if expected == "count" and re.search(
            r"\b(known|non[- ]?null|with (?:an? )?[a-z_ ]+)\b",
            text.lower(),
        ):
            target = candidates[-1] if candidates else None
        if expected != "count" and target is None:
            return plan
        aggregates.append(
            AggregateSpec(
                expected,
                target,
                (
                    f"{expected}_{target.attribute}"
                    if target is not None
                    else "count_all"
                ),
            )
        )
        if target is not None:
            projections = [
                reference
                for reference in projections
                if reference != target
            ]
    else:
        repaired = []
        for aggregate in aggregates:
            function = expected
            target = aggregate.attribute
            if function != "count" and target is None:
                candidates = [
                    reference
                    for reference in (*projections, *context_references)
                    if reference not in grouped
                ]
                target = candidates[-1] if candidates else None
            try:
                repaired.append(
                    replace(
                        aggregate,
                        function=function,
                        attribute=target,
                        alias=(
                            f"{function}_{target.attribute}"
                            if target is not None
                            else "count_all"
                        ),
                    )
                )
            except ValueError:
                continue
        aggregates = repaired
    aggregate_refs = {
        aggregate.attribute
        for aggregate in aggregates
        if aggregate.attribute is not None
    }
    projections = [
        reference
        for reference in projections
        if reference in grouped or reference not in aggregate_refs
    ]
    return replace(
        plan,
        projections=tuple(projections),
        aggregates=tuple(aggregates),
    )


def _plan_from_clause_ledger(
    payload: object,
    entity_vocabulary: Sequence[str] = (),
    default_entity: str = "",
    attribute_vocabulary: Optional[Mapping[str, Sequence[str]]] = None,
) -> Optional[QueryPlan]:
    """Compile a flat, inspectable semantic ledger into the recursive IR."""
    if not isinstance(payload, Mapping):
        return None

    projections = payload.get("projections", [])
    group_by = payload.get("group_by", [])
    aggregate_payload = payload.get("aggregate")
    aggregates = (
        [aggregate_payload]
        if isinstance(aggregate_payload, Mapping)
        else payload.get("aggregates", [])
    )
    filters = payload.get("filters", [])
    joins = payload.get("joins", [])
    if not isinstance(filters, (list, tuple)):
        filters = []

    leaves: Dict[str, PredicateSpec] = {}
    for index, value in enumerate(filters):
        if not isinstance(value, Mapping):
            continue
        identifier = str(value.get("id", f"f{index + 1}")).strip().lower()
        reference = _attribute_ref(
            value.get("attribute_ref")
            or {
                "entity": value.get("entity"),
                "attribute": value.get("attribute"),
                "semantic_type": value.get("semantic_type", "text"),
            },
            entity_vocabulary,
            default_entity,
            attribute_vocabulary,
        )
        if not identifier or reference is None:
            continue
        rendered_operator = str(value.get("operator", "=")).strip().lower()
        operator = {
            "<>": "!=",
            "==": "=",
            "not equal": "!=",
            "at least": ">=",
            "at most": "<=",
            "greater than": ">",
            "less than": "<",
        }.get(rendered_operator, rendered_operator)
        try:
            leaves[identifier] = PredicateSpec(
                attribute=reference,
                operator=operator,
                value=value.get("value"),
            )
        except ValueError:
            continue

    expression = str(payload.get("boolean_expression", "")).strip().lower()
    tokens = re.findall(r"\(|\)|\band\b|\bor\b|[a-z][a-z0-9_-]*", expression)
    position = 0

    def parse_factor() -> Optional[PredicateSpec]:
        nonlocal position
        if position >= len(tokens):
            return None
        token = tokens[position]
        if token == "(":
            position += 1
            result = parse_or()
            if position < len(tokens) and tokens[position] == ")":
                position += 1
            return result
        position += 1
        return leaves.get(token)

    def combine(
        kind: str, values: List[PredicateSpec]
    ) -> Optional[PredicateSpec]:
        flattened: List[PredicateSpec] = []
        for value in values:
            if value.kind == kind:
                flattened.extend(value.children)
            else:
                flattened.append(value)
        if not flattened:
            return None
        if len(flattened) == 1:
            return flattened[0]
        return PredicateSpec(kind=kind, children=tuple(flattened))

    def parse_and() -> Optional[PredicateSpec]:
        nonlocal position
        values: List[PredicateSpec] = []
        first = parse_factor()
        if first is not None:
            values.append(first)
        while position < len(tokens) and tokens[position] == "and":
            position += 1
            value = parse_factor()
            if value is not None:
                values.append(value)
        return combine("and", values)

    def parse_or() -> Optional[PredicateSpec]:
        nonlocal position
        values: List[PredicateSpec] = []
        first = parse_and()
        if first is not None:
            values.append(first)
        while position < len(tokens) and tokens[position] == "or":
            position += 1
            value = parse_and()
            if value is not None:
                values.append(value)
        return combine("or", values)

    predicate = parse_or() if tokens else None
    if predicate is None and leaves:
        predicate = combine("and", list(leaves.values()))

    plan = _query_plan(
        {
            "projections": projections,
            "group_by": group_by,
            "aggregates": aggregates,
            "predicate": asdict(predicate) if predicate is not None else None,
            "joins": joins,
        },
        entity_vocabulary,
        default_entity,
        attribute_vocabulary,
    )
    if plan is None or (
        not plan.attributes()
        and not (
            plan.aggregates
            and plan.aggregates[0].function == "count"
        )
    ):
        return None
    return plan


def _normalize_plan_with_schema(
    plan: Optional[QueryPlan],
    text: str,
    *,
    attribute_vocabulary: Optional[Mapping[str, Sequence[str]]] = None,
    join_vocabulary: Sequence[Tuple[str, str, str, str]] = (),
    context_references: Sequence[AttributeRef] = (),
) -> Optional[QueryPlan]:
    if plan is None:
        return None
    lowered = text.lower()
    core_entities = {
        reference.entity
        for reference in (
            *plan.projections,
            *plan.group_by,
            *context_references,
        )
    }
    core_entities.update(
        aggregate.attribute.entity
        for aggregate in plan.aggregates
        if aggregate.attribute is not None
    )
    mentioned_entities = {
        entity
        for entity in (attribute_vocabulary or {})
        if re.search(rf"\b{re.escape(entity)}s?\b", lowered)
    }

    def clean_predicate(
        predicate: Optional[PredicateSpec],
    ) -> Optional[PredicateSpec]:
        if predicate is None:
            return None
        if predicate.kind in {"and", "or"}:
            children = tuple(
                child
                for child in (
                    clean_predicate(value)
                    for value in predicate.children
                )
                if child is not None
            )
            if not children:
                return None
            if len(children) == 1:
                return children[0]
            kind = predicate.kind
            explicit_disjunction = bool(
                re.search(r",\s*or\b", lowered)
                or re.search(r"\beither\b[^.?!]*\bor\b", lowered)
                or re.search(
                    r"\bor\s+(?:players?|owners?|teams?|cities|records?|"
                    r"those|who|whose)\b",
                    lowered,
                )
            )
            if (
                kind == "and"
                and explicit_disjunction
                and any(child.kind == "or" for child in children)
            ):
                kind = "or"
            flattened: List[PredicateSpec] = []
            for child in children:
                if child.kind == kind:
                    flattened.extend(child.children)
                else:
                    flattened.append(child)
            return replace(
                predicate,
                kind=kind,
                children=tuple(dict.fromkeys(flattened)),
            )
        value = predicate.value
        if isinstance(value, Mapping):
            return None
        if isinstance(value, (list, tuple)) and len(value) == 1:
            value = value[0]
        if (
            value is None
            and predicate.operator not in {"is_null", "is_not_null"}
        ):
            return None
        if isinstance(value, str) and re.fullmatch(
            r"\$?[a-z_][a-z0-9_]*[./][a-z_][a-z0-9_]*",
            value.strip().lower(),
        ):
            return None
        if (
            isinstance(value, str)
            and attribute_vocabulary
            and value.strip().lower()
            in {
                attribute.lower()
                for attributes in attribute_vocabulary.values()
                for attribute in attributes
            }
            and value.strip().lower().replace("_", " ") not in lowered
        ):
            # A schema column name used as a quoted literal is almost always a
            # leaked relationship equality (for example entity='entity_name').
            return None
        attribute = predicate.attribute
        if (
            attribute is not None
            and isinstance(value, str)
            and (
                attribute.semantic_type == "date"
                or "date" in attribute.attribute
            )
        ):
            value = canonical_date(value) or value
        if (
            attribute is not None
            and attribute_vocabulary
            and attribute.entity not in mentioned_entities
        ):
            allowed_owners = core_entities | mentioned_entities
            source_tokens = set(attribute.attribute.split("_"))
            alternatives = [
                AttributeRef(owner, name, attribute.semantic_type)
                for owner, names in attribute_vocabulary.items()
                if owner in allowed_owners
                for name in names
                if source_tokens & set(name.split("_"))
            ]
            if alternatives:
                attribute = max(
                    alternatives,
                    key=lambda candidate: (
                        len(
                            source_tokens
                            & set(candidate.attribute.split("_"))
                        )
                        / len(
                            source_tokens
                            | set(candidate.attribute.split("_"))
                        ),
                        candidate.entity in core_entities,
                    ),
                )
        if (
            attribute is not None
            and isinstance(value, str)
            and attribute_vocabulary
            and re.search(
                rf"\bbased\s+in\s+{re.escape(value.lower())}\b",
                lowered,
            )
        ):
            location_candidates = [
                AttributeRef(owner, name, "text")
                for owner, names in attribute_vocabulary.items()
                for name in names
                if any(
                    token in name
                    for token in (
                        "location", "city", "place", "region", "address",
                        "headquarter", "home", "base",
                    )
                )
            ]
            if location_candidates:
                attribute = max(
                    location_candidates,
                    key=lambda candidate: (
                        candidate.entity in mentioned_entities,
                        candidate.entity in core_entities,
                        "location" in candidate.attribute,
                        "city" in candidate.attribute,
                    ),
                )
        if (
            attribute is not None
            and isinstance(value, (int, float))
            and attribute.semantic_type == "text"
            and attribute_vocabulary
            and attribute.attribute.replace("_", " ") not in lowered
        ):
            source_tokens = set(re.findall(r"[a-z0-9]+", lowered))
            join_keys = {
                (entity, name)
                for left_entity, left_attr, right_entity, right_attr
                in join_vocabulary
                for entity, name in (
                    (left_entity, left_attr),
                    (right_entity, right_attr),
                )
            }
            candidates = [
                (
                    len(set(name.split("_")) & source_tokens),
                    (owner, name) not in join_keys,
                    len(name.split("_")),
                    AttributeRef(owner, name, "integer"),
                )
                for owner, names in attribute_vocabulary.items()
                if owner in (mentioned_entities | core_entities)
                for name in names
            ]
            best = max(candidates, default=None, key=lambda item: item[:3])
            if best is not None and best[0] > 0:
                attribute = best[3]
        original_operator = predicate.operator
        original_value = value
        operator = original_operator
        rendered = str(value).lower()
        position = lowered.find(rendered)
        if position < 0 and isinstance(value, int) and 0 <= value <= 20:
            number_words = (
                "zero one two three four five six seven eight nine ten "
                "eleven twelve thirteen fourteen fifteen sixteen seventeen "
                "eighteen nineteen twenty"
            ).split()
            word_match = re.search(
                rf"\b{number_words[value]}\b", lowered
            )
            if word_match:
                position = word_match.start()
        context = ""
        suffix_context = ""
        if position >= 0:
            prefix = lowered[:position]
            boundary = max(
                prefix.rfind(" or "),
                prefix.rfind(" and "),
                prefix.rfind(","),
                prefix.rfind(";"),
            )
            context = prefix[boundary + 1 :]
            suffix_context = lowered[
                position + len(rendered) : position + len(rendered) + 24
            ]
        if re.search(r"\b(not|other than|different from)\b", context):
            operator = "!="
        elif re.search(
            r"\b(more than|greater than|above|after)\b",
            context + suffix_context,
        ):
            operator = ">"
        elif re.search(
            r"\b(at least|no fewer than)\b", context + suffix_context
        ):
            operator = ">="
        elif re.search(
            r"\b(less than|fewer than|below|before)\b",
            context + suffix_context,
        ):
            operator = "<"
        elif re.search(
            r"\b(at most|no more than|or earlier)\b",
            context + suffix_context,
        ):
            operator = "<="
        if not input_predicate_missing:
            operator = original_operator
            value = original_value
        if (
            attribute is not None
            and re.search(
                rf"\bno\s+(?:[a-z-]+\s+){{0,4}}"
                rf"{re.escape(attribute.attribute.split('_')[-1])}\b",
                lowered,
            )
            and not re.search(r"\b(missing|unknown|known|null)\b", lowered)
            and not re.search(
                r"\bno\s+(?:more|fewer|less)\s+than\b", lowered
            )
        ):
            operator = "="
            value = 0
        return replace(
            predicate,
            attribute=attribute,
            operator=operator,
            value=value,
        )

    input_predicate_missing = plan.predicate is None
    predicate = clean_predicate(plan.predicate)
    context_pool = list(
        dict.fromkeys((*plan.attributes(), *context_references))
    )
    aggregate_keys = {
        (aggregate.attribute.entity, aggregate.attribute.attribute)
        for aggregate in plan.aggregates
        if aggregate.attribute is not None
    }
    grouped_keys = {
        (reference.entity, reference.attribute) for reference in plan.group_by
    }

    existing_values: set[str] = set()

    def collect_values(value: Optional[PredicateSpec]) -> None:
        if value is None:
            return
        if value.kind == "predicate":
            existing_values.add(str(value.value).strip().lower())
        for child in value.children:
            collect_values(child)

    collect_values(predicate)

    def add_recovered(value: PredicateSpec) -> None:
        nonlocal predicate
        predicate = (
            PredicateSpec(kind="and", children=(predicate, value))
            if predicate is not None
            else value
        )

    subject_entity = next(
        (
            aggregate.attribute.entity
            for aggregate in plan.aggregates
            if aggregate.attribute is not None
        ),
        plan.projections[0].entity if plan.projections else "",
    )
    date_spans: List[Tuple[int, int]] = []
    month_numbers = {
        name.lower(): index
        for index, name in enumerate(
            (
                "",
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            )
        )
        if name
    }
    for match in re.finditer(
        r"\b(" + "|".join(month_numbers) + r")\s+(\d{1,2}),\s+(\d{4})\b",
        text,
        re.IGNORECASE,
    ):
        date_spans.append(match.span())
        candidates = [
            reference
            for reference in context_pool
            if (
                reference.semantic_type == "date"
                or any(
                    token in reference.attribute
                    for token in ("date", "day", "time")
                )
            )
            and (reference.entity, reference.attribute)
            not in aggregate_keys | grouped_keys
        ]
        if not candidates:
            continue
        target = max(
            candidates,
            key=lambda reference: reference.entity == subject_entity,
        )
        value = (
            f"{int(match.group(3))}/"
            f"{month_numbers[match.group(1).lower()]}/"
            f"{int(match.group(2))}"
        )
        if value.lower() not in existing_values:
            add_recovered(
                PredicateSpec(attribute=target, operator="=", value=value)
            )
            existing_values.add(value.lower())

    schema_phrases = {
        attribute.replace("_", " ").lower()
        for attributes in (attribute_vocabulary or {}).values()
        for attribute in attributes
    }
    schema_tokens = {
        token
        for phrase in schema_phrases
        for token in phrase.split()
    }
    ignored_proper_literals = {
        "list", "show", "return", "match", "calculate", "find",
    }
    proper_literals = [
        match
        for match in re.finditer(
            r"\b[A-Z][a-z]+(?:[- ][A-Z][a-z]+)*\b", text
        )
        if match.start() > 0
        and not any(
            start <= match.start() < end for start, end in date_spans
        )
        and match.group(0).lower() not in ignored_proper_literals
        and not all(
            token.lower() in schema_tokens
            for token in match.group(0).split()
        )
    ]
    for match in proper_literals:
        literal = match.group(0)
        if literal.lower() in existing_values:
            continue
        following = text[match.end() : match.end() + 30].lower()
        preceding = text[max(0, match.start() - 35) : match.start()].lower()
        qualifies = any(
            re.match(rf"\s+{re.escape(entity)}s?\b", following)
            for entity in (attribute_vocabulary or {})
        ) or bool(
            re.search(
                r"\b(?:based|born|from|in|on|for|who|whose|not)\s*$",
                preceding,
            )
        )
        if not qualifies:
            continue
        candidates = [
            reference
            for reference in context_pool
            if (reference.entity, reference.attribute)
            not in aggregate_keys | grouped_keys
        ]
        if not candidates:
            continue
        join_columns = {
            (entity, attribute)
            for left_entity, left_attr, right_entity, right_attr
            in join_vocabulary
            for entity, attribute in (
                (left_entity, left_attr),
                (right_entity, right_attr),
            )
        }
        target = max(
            candidates,
            key=lambda reference: (
                reference.entity == subject_entity,
                (reference.entity, reference.attribute) in join_columns,
                reference.semantic_type == "text",
            ),
        )
        operator = "!=" if re.search(
            r"\b(?:not|other than)\s*$", preceding
        ) else "="
        recovered = clean_predicate(
            PredicateSpec(
                attribute=target,
                operator=operator,
                value=literal,
            )
        )
        if recovered is not None:
            add_recovered(recovered)
            existing_values.add(literal.lower())

    either_position = lowered.find("either")
    if (
        input_predicate_missing
        and either_position >= 0
        and re.search(r"\bbut\s+not\b", lowered[either_position:])
        and re.search(r"\bor\b", lowered[either_position:])
    ):
        alternatives = [
            match.group(0)
            for match in proper_literals
            if match.start() > either_position
        ]
        if len(alternatives) >= 3:
            category_candidates = [
                reference
                for reference in context_pool
                if (reference.entity, reference.attribute)
                not in aggregate_keys | grouped_keys
                and reference.semantic_type == "text"
            ]
            if category_candidates:
                category = max(
                    category_candidates,
                    key=lambda reference: (
                        reference.entity == subject_entity,
                        reference.attribute
                        not in {"name", f"{reference.entity}_name"},
                    ),
                )
                relationship_candidates = [
                    reference
                    for reference in context_pool
                    if reference.entity == subject_entity
                    and (
                        (reference.entity, reference.attribute)
                        in grouped_keys
                        or any(
                            (
                                reference.entity == left_entity
                                and reference.attribute == left_attr
                            )
                            or (
                                reference.entity == right_entity
                                and reference.attribute == right_attr
                            )
                            for (
                                left_entity,
                                left_attr,
                                right_entity,
                                right_attr,
                            ) in join_vocabulary
                        )
                    )
                ]
                if relationship_candidates:
                    relationship = relationship_candidates[0]
                    predicate = PredicateSpec(
                        kind="or",
                        children=(
                            PredicateSpec(
                                kind="and",
                                children=(
                                    PredicateSpec(
                                        attribute=category,
                                        operator="=",
                                        value=alternatives[0],
                                    ),
                                    PredicateSpec(
                                        attribute=category,
                                        operator="!=",
                                        value=alternatives[1],
                                    ),
                                ),
                            ),
                            PredicateSpec(
                                attribute=relationship,
                                operator="!=",
                                value=alternatives[2],
                            ),
                        ),
                    )

    elif input_predicate_missing and re.search(r",\s*or\b", lowered):
        restriction_text = re.split(
            r"\b(?:who|that)\b", text, maxsplit=1, flags=re.IGNORECASE
        )[-1]
        clauses = [
            clause.strip(" .")
            for clause in re.split(
                r",\s*(?:or\s+)?", restriction_text, flags=re.IGNORECASE
            )
            if clause.strip(" .")
        ]
        recovered_clauses: List[PredicateSpec] = []
        number_words = (
            "zero one two three four five six seven eight nine ten "
            "eleven twelve thirteen fourteen fifteen sixteen seventeen "
            "eighteen nineteen twenty"
        ).split()
        all_schema_refs = [
            AttributeRef(
                entity,
                attribute,
                (
                    "integer"
                    if any(
                        token in attribute
                        for token in (
                            "amount", "count", "number", "quantity", "year"
                        )
                    )
                    else "text"
                ),
            )
            for entity, attributes in (attribute_vocabulary or {}).items()
            for attribute in attributes
            if (entity, attribute) not in aggregate_keys | grouped_keys
        ]
        join_refs = [
            reference
            for reference in all_schema_refs
            if reference.entity == subject_entity
            and any(
                (
                    reference.entity == left_entity
                    and reference.attribute == left_attr
                )
                or (
                    reference.entity == right_entity
                    and reference.attribute == right_attr
                )
                for (
                    left_entity,
                    left_attr,
                    right_entity,
                    right_attr,
                ) in join_vocabulary
            )
        ]
        for clause in clauses:
            clause_lower = clause.lower()
            clause_tokens = set(re.findall(r"[a-z0-9]+", clause_lower))
            number_match = re.search(r"\b\d+(?:\.\d+)?\b", clause_lower)
            numeric_value: Optional[object] = None
            if number_match:
                numeric_value = (
                    float(number_match.group(0))
                    if "." in number_match.group(0)
                    else int(number_match.group(0))
                )
            else:
                for number, word in enumerate(number_words):
                    if re.search(rf"\b{word}\b", clause_lower):
                        numeric_value = number
                        break
            proper = [
                match.group(0)
                for match in re.finditer(
                    r"\b[A-Z][a-z]+(?:[- ][A-Z][a-z]+)*\b", clause
                )
                if match.start() > 0
            ]
            literal: Optional[object] = (
                numeric_value
                if numeric_value is not None
                else (proper[-1] if proper else None)
            )
            if literal is None:
                continue
            scored = [
                (
                    len(set(reference.attribute.split("_")) & clause_tokens),
                    reference.entity in {
                        entity
                        for entity in (attribute_vocabulary or {})
                        if re.search(
                            rf"\b{re.escape(entity)}s?\b", clause_lower
                        )
                    },
                    reference.entity == subject_entity,
                    reference,
                )
                for reference in all_schema_refs
            ]
            best = max(scored, default=None, key=lambda item: item[:3])
            target = best[3] if best is not None and best[0] > 0 else (
                join_refs[0] if join_refs else None
            )
            if target is None:
                continue
            if re.search(
                r"\b(?:not|other than|different from)\b", clause_lower
            ):
                operator = "!="
            elif re.search(
                r"\b(?:more than|greater than|above|over|after)\b",
                clause_lower,
            ):
                operator = ">"
            elif re.search(
                r"\b(?:less than|fewer than|below|under|before)\b",
                clause_lower,
            ):
                operator = "<"
            else:
                operator = "="
            recovered_clauses.append(
                PredicateSpec(
                    attribute=target,
                    operator=operator,
                    value=literal,
                )
            )
        if len(recovered_clauses) >= 2:
            predicate = PredicateSpec(
                kind="or", children=tuple(recovered_clauses)
            )

    existing_numbers = {
        value
        for value in existing_values
        if re.fullmatch(r"-?\d+(?:\.\d+)?", value)
    }
    numeric_pattern = (
        r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"
        r"|\b\d+(?:\.\d+)?\b"
    )
    for match in re.finditer(numeric_pattern, text):
        rendered_surface = match.group(0)
        rendered = rendered_surface.replace(",", "")
        if rendered in existing_numbers:
            continue
        preceding = text[max(0, match.start() - 45) : match.start()].lower()
        following = text[match.end() : match.end() + 20].lower()
        if not re.search(
            r"\b(?:above|after|at least|at most|before|below|earlier|"
            r"fewer|greater|less|more|over|under|founded)\b",
            preceding + following,
        ):
            continue
        candidates = [
            reference
            for reference in context_pool
            if (reference.entity, reference.attribute)
            not in aggregate_keys | grouped_keys
        ]
        if not candidates:
            continue
        context_tokens = set(
            re.findall(r"[a-z]+", preceding + following)
        )
        target = max(
            candidates,
            key=lambda reference: (
                len(set(reference.attribute.split("_")) & context_tokens),
                reference.semantic_type in {"integer", "real"},
            ),
        )
        recovered = clean_predicate(
            PredicateSpec(
                attribute=target,
                operator="=",
                value=(
                    float(rendered) if "." in rendered else int(rendered)
                ),
            )
        )
        if recovered is not None:
            add_recovered(recovered)
            existing_numbers.add(rendered)

    aggregates = list(plan.aggregates)
    if (
        aggregates
        and aggregates[0].function == "count"
        and re.search(r"\b(known|non[- ]?null)\b", lowered)
        and attribute_vocabulary
    ):
        candidates = [
            AttributeRef(entity, attribute, "text")
            for entity, attributes in attribute_vocabulary.items()
            for attribute in attributes
            if all(token in lowered for token in attribute.split("_"))
        ]
        context_entities = {
            reference.entity
            for reference in (*plan.projections, *plan.group_by)
        }
        if candidates:
            known_position = max(
                lowered.find("known"),
                lowered.find("non-null"),
                lowered.find("non null"),
            )

            def known_distance(value: AttributeRef) -> int:
                position = lowered.find(
                    value.attribute.replace("_", " ")
                )
                if position < 0:
                    position = lowered.find(
                        value.attribute.split("_")[-1]
                    )
                return (
                    abs(position - known_position)
                    if position >= 0 and known_position >= 0
                    else len(lowered)
                )

            target = max(
                candidates,
                key=lambda value: (
                    value.entity in context_entities,
                    -known_distance(value),
                    len(value.attribute),
                ),
            )
            aggregates[0] = replace(
                aggregates[0],
                attribute=target,
                alias=f"count_{target.attribute}",
            )
    if (
        aggregates
        and aggregates[0].function == "count"
        and not re.search(r"\b(known|non[- ]?null|not null)\b", lowered)
    ):
        aggregates[0] = replace(
            aggregates[0], attribute=None, alias="count_all"
        )

    group_by = list(plan.group_by) if aggregates else []
    group_clause = ""
    group_patterns = (
        r"\b(?:for|at|on|from|of)\s+(?:each|every)\s+(.+?)(?:,|\?|"
        r"\b(?:what|how|when|where|whose|who)\b)",
        r"\b(?:each|every)\s+(.+?)(?:,|\?|"
        r"\b(?:what|how|when|where|whose|who)\b)",
        r"\bbreak\b.+?\bdown by\b\s+(.+?)(?:,|\?|"
        r"\band\s+(?:report|tell|show)\b)",
        r"\bgroup(?:ed)?\b.+?\bby\b\s+(.+?)(?:,|\?|"
        r"\band\s+(?:report|tell|show)\b)",
        r"^\s*by\s+(.+?)(?:,|\?)",
        r"\bby\s+(.+?)(?:,|\?|\band\s+(?:report|tell|show)\b)",
    )
    for pattern in group_patterns:
        match = re.search(pattern, lowered)
        if match:
            group_clause = match.group(1).strip()
            break
    if aggregates and group_clause and attribute_vocabulary:
        excluded = {
            (aggregate.attribute.entity, aggregate.attribute.attribute)
            for aggregate in aggregates
            if aggregate.attribute is not None
        }

        clause_tokens = set(re.findall(r"[a-z0-9]+", group_clause))

        def mentioned(attribute: str) -> bool:
            tokens = attribute.split("_")
            return all(
                token in clause_tokens
                or (
                    token.endswith("s")
                    and token[:-1] in clause_tokens
                )
                for token in tokens
            )

        candidates = [
            AttributeRef(entity, attribute, "text")
            for entity, attributes in attribute_vocabulary.items()
            for attribute in attributes
            if (entity, attribute) not in excluded
            and mentioned(attribute)
        ]
        mentioned_candidates = [
            candidate
            for candidate in candidates
            if candidate.entity in mentioned_entities
        ]
        if mentioned_candidates:
            candidates = mentioned_candidates
        else:
            core_candidates = [
                candidate
                for candidate in candidates
                if candidate.entity in core_entities
            ]
            if core_candidates:
                candidates = core_candidates
        candidates = [
            candidate
            for candidate in candidates
            if not any(
                candidate.attribute == other.entity
                and candidate != other
                for other in candidates
            )
        ]
        for entity, attributes in attribute_vocabulary.items():
            entity_mentioned = (
                entity in clause_tokens
                or f"{entity}s" in clause_tokens
            )
            if not entity_mentioned or any(
                candidate.entity == entity for candidate in candidates
            ) or any(
                candidate.attribute == entity for candidate in candidates
            ):
                continue
            identity = next(
                (
                    value
                    for value in (
                        f"{entity}_name",
                        "name",
                        entity,
                    )
                    if value in attributes
                ),
                None,
            )
            if identity:
                candidates.append(AttributeRef(entity, identity, "text"))
        if candidates:
            group_by = sorted(
                dict.fromkeys(candidates),
                key=lambda value: (
                    group_clause.find(
                        value.attribute.replace("_", " ")
                    )
                    if value.attribute.replace("_", " ") in group_clause
                    else group_clause.find(value.entity),
                    value.entity,
                    value.attribute,
                ),
            )

    # COUNT over a categorical equality conventionally returns the filtered
    # category as its sole dimension, even when the question says only
    # "how many X entities". This is also necessary to retain the requested
    # category in a relational answer rather than returning an unlabeled count.
    if not group_by and aggregates and predicate is not None:
        equality_dimensions: List[AttributeRef] = []

        def collect_equality_dimensions(value: PredicateSpec) -> None:
            if value.kind in {"and", "or"}:
                for child in value.children:
                    collect_equality_dimensions(child)
                return
            if (
                value.attribute is not None
                and value.operator == "="
                and isinstance(value.value, str)
                and value.attribute.semantic_type != "date"
                and "date" not in value.attribute.attribute
            ):
                equality_dimensions.append(value.attribute)

        collect_equality_dimensions(predicate)
        group_by = list(dict.fromkeys(equality_dimensions))

    if aggregates and attribute_vocabulary:
        grouped_keys = {
            (reference.entity, reference.attribute) for reference in group_by
        }
        existing_refs = {
            (reference.entity, reference.attribute): reference
            for reference in (*plan.attributes(), *context_references)
        }
        cue_matches = list(
            re.finditer(
                r"\b(?:average|mean|fewest|lowest|smallest|minimum|largest|"
                r"highest|greatest|maximum|total|combined|altogether|sum|"
                r"how many|count)\b",
                lowered,
            )
        )
        cue_position = cue_matches[0].start() if cue_matches else 0

        def phrase_position(attribute: str) -> int:
            phrase = attribute.replace("_", " ")
            match = re.search(rf"\b{re.escape(phrase)}s?\b", lowered)
            if match:
                return match.start()
            tokens = attribute.split("_")
            inflected_phrase = r"\s+".join(
                rf"{re.escape(token[:-1] if token.endswith('s') else token)}s?"
                for token in tokens
            )
            match = re.search(rf"\b{inflected_phrase}\b", lowered)
            if match:
                return match.start()
            matches = [
                re.search(
                    rf"\b{re.escape(token[:-1] if token.endswith('s') else token)}s?\b",
                    lowered,
                )
                for token in tokens
            ]
            return (
                min(match.start() for match in matches if match is not None)
                if matches and all(match is not None for match in matches)
                else -1
            )

        candidates: List[AttributeRef] = []
        for entity, names in attribute_vocabulary.items():
            for attribute in names:
                position = phrase_position(attribute)
                key = (entity, attribute)
                if position < 0 or key in grouped_keys:
                    continue
                candidates.append(
                    existing_refs.get(
                        key,
                        AttributeRef(
                            entity,
                            attribute,
                            "real"
                            if aggregates[0].function == "avg"
                            else "integer",
                        ),
                    )
                )
        if candidates and aggregates[0].function != "count":
            mentioned_candidates = [
                reference
                for reference in candidates
                if reference.entity in mentioned_entities
            ]
            if mentioned_candidates:
                candidates = mentioned_candidates
            join_keys = {
                (entity, attribute)
                for left_entity, left_attr, right_entity, right_attr
                in join_vocabulary
                for entity, attribute in (
                    (left_entity, left_attr),
                    (right_entity, right_attr),
                )
            }
            target = max(
                candidates,
                key=lambda reference: (
                    -abs(phrase_position(reference.attribute) - cue_position),
                    (reference.entity, reference.attribute)
                    not in join_keys,
                    len(reference.attribute.split("_")),
                    reference.entity in mentioned_entities,
                    reference.semantic_type
                    in {"integer", "real", "boolean"},
                    reference.entity in core_entities,
                ),
            )
            aggregates[0] = replace(
                aggregates[0],
                attribute=target,
                alias=f"{aggregates[0].function}_{target.attribute}",
            )

    explicit_distinct = bool(
        re.search(r"\b(?:distinct|different|unique)\b", lowered)
    )
    aggregates = [
        replace(aggregate, distinct=False)
        if aggregate.distinct and not explicit_distinct
        else aggregate
        for aggregate in aggregates
    ]

    # Prefer a fact table's local relationship key when the question requests
    # only the related entity itself (for example, "by account"), not a remote
    # property (for example, "by account region"). This avoids a lossy join
    # without encoding any domain-specific table or column names.
    measure_entity = next(
        (
            aggregate.attribute.entity
            for aggregate in aggregates
            if aggregate.attribute is not None
        ),
        None,
    )
    if measure_entity and join_vocabulary:
        localized_groups: List[AttributeRef] = []
        for reference in group_by:
            replacement = None
            identity_names = {
                "id",
                "key",
                "name",
                reference.entity,
                f"{reference.entity}_id",
                f"{reference.entity}_key",
                f"{reference.entity}_name",
            }
            if (
                reference.entity != measure_entity
                and reference.attribute in identity_names
                and reference.attribute.replace("_", " ") not in lowered
            ):
                for left_entity, left_attr, right_entity, right_attr in (
                    join_vocabulary
                ):
                    if (
                        left_entity == reference.entity
                        and left_attr == reference.attribute
                        and right_entity == measure_entity
                    ):
                        replacement = AttributeRef(
                            right_entity, right_attr, "text"
                        )
                        break
                    if (
                        right_entity == reference.entity
                        and right_attr == reference.attribute
                        and left_entity == measure_entity
                    ):
                        replacement = AttributeRef(
                            left_entity, left_attr, "text"
                        )
                        break
            localized_groups.append(replacement or reference)
        group_by = list(dict.fromkeys(localized_groups))

    # In an aggregate query every non-aggregate output must be a grouping
    # dimension. Discard leaked projections from the LLM audit; otherwise
    # SQLite accepts them permissively and returns arbitrary values.
    if aggregates:
        projections = tuple(group_by)
    else:
        # Projection-only questions must never inherit grouping invented by an
        # LLM audit ("for every record" means rows, not GROUP BY record).
        # At this point all references have already been constrained to the
        # canonical schema. Do not discard valid model projections merely
        # because the question uses a morphological variant (for example,
        # "founding year" for a canonical ``founded_year`` column).
        projections = tuple(dict.fromkeys(plan.projections))

    required_entities = {
        reference.entity
        for reference in QueryPlan(
            projections=projections,
            group_by=tuple(group_by),
            aggregates=tuple(aggregates),
            predicate=predicate,
            joins=(),
            having=plan.having,
        ).attributes()
    }
    if re.search(
        r"\b(?:match(?:ed|ing)?|join(?:ed|ing)?|related|relationships?)\b",
        lowered,
    ):
        required_entities.update(mentioned_entities)
    normalized_joins: List[JoinSpec] = []
    allowed_join_keys = {
        frozenset(((left_entity, left_attr), (right_entity, right_attr)))
        for left_entity, left_attr, right_entity, right_attr in join_vocabulary
    }
    candidate_join_keys = {
        frozenset(
            (
                (join.left.entity, join.left.attribute),
                (join.right.entity, join.right.attribute),
            )
        )
        for join in plan.joins
    }
    candidate_connected: set[str] = set()
    if plan.joins:
        candidate_connected.add(plan.joins[0].left.entity)
        changed = True
        while changed:
            changed = False
            for join in plan.joins:
                if (
                    join.left.entity in candidate_connected
                    or join.right.entity in candidate_connected
                ):
                    before = len(candidate_connected)
                    candidate_connected.update(
                        (join.left.entity, join.right.entity)
                    )
                    changed = changed or len(candidate_connected) > before
    candidate_joins_valid = bool(plan.joins) and (
        candidate_join_keys <= allowed_join_keys
        and required_entities <= candidate_connected
    )
    if candidate_joins_valid:
        normalized_joins = list(dict.fromkeys(plan.joins))
    elif len(required_entities) > 1 and join_vocabulary:
        root = next(
            (
                reference.entity
                for reference in (
                    *group_by,
                    *plan.projections,
                    *(
                        aggregate.attribute
                        for aggregate in aggregates
                        if aggregate.attribute is not None
                    ),
                )
                if reference.entity in required_entities
            ),
            min(required_entities),
        )
        connected = {root}
        adjacency: Dict[str, List[Tuple[str, JoinSpec]]] = {}
        for left_entity, left_attr, right_entity, right_attr in join_vocabulary:
            edge = JoinSpec(
                AttributeRef(left_entity, left_attr),
                AttributeRef(right_entity, right_attr),
            )
            adjacency.setdefault(left_entity, []).append((right_entity, edge))
            adjacency.setdefault(right_entity, []).append((left_entity, edge))
        while required_entities - connected:
            target = min(required_entities - connected)
            queue: List[Tuple[str, List[Tuple[str, JoinSpec]]]] = [
                (entity, []) for entity in sorted(connected)
            ]
            visited = set(connected)
            path: Optional[List[Tuple[str, JoinSpec]]] = None
            while queue:
                entity, candidate_path = queue.pop(0)
                if entity == target:
                    path = candidate_path
                    break
                for neighbour, edge in adjacency.get(entity, []):
                    if neighbour in visited:
                        continue
                    visited.add(neighbour)
                    queue.append(
                        (neighbour, [*candidate_path, (neighbour, edge)])
                    )
            if path is None:
                break
            for neighbour, edge in path:
                if edge not in normalized_joins:
                    normalized_joins.append(edge)
                connected.add(edge.left.entity)
                connected.add(edge.right.entity)
                connected.add(neighbour)

    qualified_aliases = bool(normalized_joins)
    aggregates = [
        replace(
            aggregate,
            alias=(
                f"{aggregate.function}_{aggregate.attribute.entity}_"
                f"{aggregate.attribute.attribute}"
                if qualified_aliases and aggregate.attribute is not None
                else (
                    f"{aggregate.function}_{aggregate.attribute.attribute}"
                    if aggregate.attribute is not None
                    else "count_all"
                )
            ),
        )
        for aggregate in aggregates
    ]

    return replace(
        plan,
        projections=projections,
        group_by=tuple(group_by),
        aggregates=tuple(aggregates),
        predicate=predicate,
        joins=tuple(normalized_joins) if join_vocabulary else plan.joins,
    )


def _plan_contract_score(plan: Optional[QueryPlan], text: str) -> int:
    """Rank independent plans by explicit NL atoms, without corpus access."""
    if plan is None:
        return -10_000
    lowered = text.lower()
    score = 0
    # A predicate-only interpretation of a projection question cannot produce
    # executable SQL, regardless of how accurately it captured the filters.
    # Keep such partial ledgers as diagnostics, but never let them tie a
    # complete candidate.
    if not plan.projections and not plan.aggregates:
        score -= 100
    else:
        score += 10
    expected = _expected_aggregate(text)
    if expected is not None:
        score += 8 if any(
            aggregate.function == expected for aggregate in plan.aggregates
        ) else -8
    else:
        score += 6 if not plan.aggregates else -12
        score += 6 if not plan.group_by else -12
    if _expects_group_cardinality_having(text):
        score += 8 if plan.having else -12
    elif plan.having:
        score -= 8
    predicate_values: List[str] = []
    predicate_leaves: List[PredicateSpec] = []

    def visit(predicate: Optional[PredicateSpec]) -> None:
        if predicate is None:
            return
        if predicate.kind in {"and", "or"}:
            for child in predicate.children:
                visit(child)
            return
        predicate_leaves.append(predicate)
        predicate_values.append(str(predicate.value).strip().lower())

    visit(plan.predicate)
    for rendered_number in re.findall(
        r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b",
        lowered,
    ):
        number = rendered_number.replace(",", "")
        score += 3 if any(number in value for value in predicate_values) else -3
    attribute_tokens = {
        token
        for reference in plan.attributes()
        for token in reference.attribute.lower().split("_")
    }
    for match in re.finditer(
        r"\b[A-Z][a-z]+(?:[- ][A-Z][a-z]+)*\b", text
    ):
        if match.start() == 0:
            continue
        literal = match.group(0).lower()
        if (
            literal in {"list", "show", "return", "match", "calculate", "find"}
            or all(token in attribute_tokens for token in literal.split())
        ):
            continue
        score += 2 if any(
            literal in value for value in predicate_values
        ) else -2
    if expected is not None and re.search(
        r"\b(?:(?:for|by)\s+(?:each|every)|group(?:ed)?\s+by|"
        r"break\b.+\bdown by)\b",
        lowered,
    ):
        score += 4 if plan.group_by else -4
    if re.search(r"\b(?:matching|joined|related)\b", lowered):
        score += 4 if plan.joins else -4
    if (
        " no " in f" {lowered} "
        and not re.search(
            r"\bno\s+(?:more|fewer|less)\s+than\b", lowered
        )
    ):
        score += 3 if any(
            leaf.operator == "=" and leaf.value == 0
            for leaf in predicate_leaves
        ) else -3
    if plan.aggregates:
        score -= 2 * sum(
            reference not in plan.group_by for reference in plan.projections
        )
        target = plan.aggregates[0].attribute
        if target is not None:
            phrase = target.attribute.replace("_", " ")
            score += 3 if phrase in lowered else -1
    schema_name_literals = {
        reference.attribute.lower()
        for reference in plan.attributes()
    }
    score -= 4 * sum(
        value in schema_name_literals
        and value.replace("_", " ") not in lowered
        for value in predicate_values
    )
    synthetic = QueryRequirement(
        query_id="contract",
        text=text,
        operators=tuple(
            operator
            for operator in (
                _expected_aggregate(text),
                "group_by"
                if re.search(
                    r"\b(?:group(?:ed)?\s+by|by\s+each|"
                    r"(?:for|at|in|of)\s+(?:each|every)|"
                    r"(?:each|every)\s+[a-z])\b",
                    lowered,
                )
                else None,
                "filter"
                if re.search(
                    r"\b(?:where|whose|known|aged|drafted|before|after|at least|"
                    r"at most|or later|greater than|less than|equal to|"
                    r"more than (?:one|two|three|\d+) "
                    r"(?:hundred|thousand|million|billion)|matching)\b",
                    lowered,
                )
                else None,
            )
            if operator is not None
        ),
        plan=plan,
    )
    score -= 100 * len(_plan_contract_diagnostics(synthetic))
    return score


def _symbol_tokens(value: object) -> Tuple[str, ...]:
    """Normalize spelling and separators without inflection heuristics."""
    rendered = re.sub(
        r"([a-z0-9])([A-Z])", r"\1 \2", str(value or "").strip()
    ).lower()
    return tuple(re.findall(r"[a-z0-9]+", rendered))


def _canonicalize_workload_requirements(
    requirements: Sequence[QueryRequirement],
) -> Tuple[Tuple[QueryRequirement, ...], Mapping[str, Any]]:
    """Rewrite independently inferred symbols into one evidenced namespace.

    Alias edges require either normalized identity or corroboration from both
    lexical token overlap and shared attributes. A strong multi-attribute
    overlap can also corroborate aliases whose surface forms have no common
    token. No stemming or singular/plural suffix manipulation is performed.
    """
    entity_frequency: Counter[str] = Counter()
    entity_attributes: Dict[str, set[str]] = {}
    attribute_frequency: Counter[Tuple[str, str]] = Counter()
    entity_cooccurrences: set[frozenset[str]] = set()

    def observe(entity: str, attribute: Optional[str] = None) -> None:
        entity = str(entity or "").strip().lower()
        if not entity:
            return
        entity_frequency[entity] += 1
        entity_attributes.setdefault(entity, set())
        if attribute:
            attribute = str(attribute).strip().lower()
            entity_attributes[entity].add(attribute)
            attribute_frequency[(entity, attribute)] += 1

    for requirement in requirements:
        query_entities = {
            str(entity).strip().lower()
            for entity in requirement.entities
            if str(entity).strip()
        }
        query_entities.update(
            str(entity).strip().lower()
            for entity, _attribute in requirement.attribute_bindings
            if str(entity).strip()
        )
        if requirement.plan:
            query_entities.update(
                reference.entity.strip().lower()
                for reference in requirement.plan.attributes()
                if reference.entity.strip()
            )
        for left, _relation, right in requirement.relationships:
            query_entities.update(
                value for value in (left.strip().lower(), right.strip().lower())
                if value
            )
        for left in query_entities:
            for right in query_entities:
                if left < right:
                    entity_cooccurrences.add(frozenset((left, right)))
        for entity in requirement.entities:
            observe(entity)
        for entity, attribute in requirement.attribute_bindings:
            observe(entity, attribute)
        for left, _relation, right in requirement.relationships:
            observe(left)
            observe(right)
        if requirement.plan:
            for reference in requirement.plan.attributes():
                observe(reference.entity, reference.attribute)

    entities = sorted(entity_attributes)
    parent = {entity: entity for entity in entities}

    def root(entity: str) -> str:
        while parent[entity] != entity:
            parent[entity] = parent[parent[entity]]
            entity = parent[entity]
        return entity

    def union(left: str, right: str) -> None:
        left_root, right_root = root(left), root(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for index, left in enumerate(entities):
        left_tokens = set(_symbol_tokens(left))
        left_attrs = {
            _symbol_tokens(attribute)
            for attribute in entity_attributes[left]
            if _symbol_tokens(attribute)
        }
        for right in entities[index + 1 :]:
            right_tokens = set(_symbol_tokens(right))
            right_attrs = {
                _symbol_tokens(attribute)
                for attribute in entity_attributes[right]
                if _symbol_tokens(attribute)
            }
            shared_attributes = left_attrs & right_attrs
            attribute_union = left_attrs | right_attrs
            normalized_exact = bool(left_tokens) and left_tokens == right_tokens
            lexical_overlap = bool(left_tokens & right_tokens)
            explicitly_distinct = (
                frozenset((left, right)) in entity_cooccurrences
            )
            corroborated_lexical = (
                lexical_overlap
                and bool(shared_attributes)
                and not explicitly_distinct
            )
            strong_attribute_overlap = (
                len(shared_attributes) >= 2
                and len(shared_attributes) / max(len(attribute_union), 1) >= 0.67
                and not explicitly_distinct
            )
            if (
                normalized_exact
                or corroborated_lexical
                or strong_attribute_overlap
            ):
                union(left, right)

    clusters: Dict[str, List[str]] = {}
    for entity in entities:
        clusters.setdefault(root(entity), []).append(entity)

    entity_aliases: Dict[str, str] = {}
    alias_evidence: List[dict] = []
    for members in clusters.values():
        canonical = min(
            members,
            key=lambda value: (
                -entity_frequency[value],
                -len(entity_attributes[value]),
                len(_symbol_tokens(value)),
                len(value),
                value,
            ),
        )
        combined_attributes = {
            attribute
            for member in members
            for attribute in entity_attributes[member]
        }
        for member in members:
            entity_aliases[member] = canonical
            if member != canonical:
                alias_evidence.append(
                    {
                        "kind": "entity",
                        "alias": member,
                        "canonical": canonical,
                        "alias_frequency": entity_frequency[member],
                        "canonical_frequency": entity_frequency[canonical],
                        "shared_attributes": sorted(
                            entity_attributes[member]
                            & entity_attributes[canonical]
                        ),
                    }
                )
        entity_attributes[canonical] = combined_attributes

    attribute_aliases: Dict[Tuple[str, str], str] = {}
    for canonical_entity in sorted(set(entity_aliases.values())):
        variants = sorted(
            {
                attribute
                for entity, attributes in entity_attributes.items()
                if entity_aliases.get(entity, entity) == canonical_entity
                for attribute in attributes
            }
        )
        by_normalized: Dict[Tuple[str, ...], List[str]] = {}
        for attribute in variants:
            by_normalized.setdefault(_symbol_tokens(attribute), []).append(attribute)
        for normalized, members in by_normalized.items():
            if not normalized:
                continue
            canonical_attribute = min(
                members,
                key=lambda value: (
                    -sum(
                        count
                        for (entity, attribute), count in attribute_frequency.items()
                        if entity_aliases.get(entity, entity) == canonical_entity
                        and attribute == value
                    ),
                    len(value),
                    value,
                ),
            )
            for member in members:
                attribute_aliases[(canonical_entity, member)] = canonical_attribute
                if member != canonical_attribute:
                    alias_evidence.append(
                        {
                            "kind": "attribute",
                            "entity": canonical_entity,
                            "alias": member,
                            "canonical": canonical_attribute,
                        }
                    )

    def canonical_entity(value: str) -> str:
        rendered = str(value or "").strip().lower()
        return entity_aliases.get(rendered, rendered)

    def canonical_attribute(entity: str, value: str) -> str:
        rendered = str(value or "").strip().lower()
        return attribute_aliases.get(
            (canonical_entity(entity), rendered), rendered
        )

    def reference(value: AttributeRef) -> AttributeRef:
        entity = canonical_entity(value.entity)
        return replace(
            value,
            entity=entity,
            attribute=canonical_attribute(entity, value.attribute),
        )

    def predicate(value: Optional[PredicateSpec]) -> Optional[PredicateSpec]:
        if value is None:
            return None
        if value.kind == "predicate":
            return replace(
                value,
                attribute=reference(value.attribute)
                if value.attribute is not None
                else None,
            )
        return replace(
            value,
            children=tuple(predicate(child) for child in value.children),
        )

    def plan(value: Optional[QueryPlan]) -> Optional[QueryPlan]:
        if value is None:
            return None
        return QueryPlan(
            projections=tuple(reference(item) for item in value.projections),
            group_by=tuple(reference(item) for item in value.group_by),
            aggregates=tuple(
                replace(
                    aggregate,
                    attribute=(
                        reference(aggregate.attribute)
                        if aggregate.attribute is not None
                        else None
                    ),
                )
                for aggregate in value.aggregates
            ),
            predicate=predicate(value.predicate),
            joins=tuple(
                replace(
                    join,
                    left=reference(join.left),
                    right=reference(join.right),
                )
                for join in value.joins
            ),
            having=tuple(
                replace(
                    condition,
                    aggregate=replace(
                        condition.aggregate,
                        attribute=(
                            reference(condition.aggregate.attribute)
                            if condition.aggregate.attribute is not None
                            else None
                        ),
                    ),
                )
                for condition in value.having
            ),
        )

    rewritten: List[QueryRequirement] = []
    unresolved: List[dict] = []
    for requirement in requirements:
        rewritten_plan = plan(requirement.plan)
        bindings = tuple(
            dict.fromkeys(
                (
                    canonical_entity(entity),
                    canonical_attribute(entity, attribute),
                )
                for entity, attribute in requirement.attribute_bindings
            )
        )
        plan_references = (
            rewritten_plan.attributes() if rewritten_plan is not None else ()
        )
        rewritten_entities = tuple(
            dict.fromkeys(
                [
                    *(canonical_entity(entity) for entity in requirement.entities),
                    *(reference.entity for reference in plan_references),
                    *(entity for entity, _attribute in bindings),
                ]
            )
        )
        owned_attributes = [
            attribute for _entity, attribute in bindings
        ] + [item.attribute for item in plan_references]
        rewritten_attributes = tuple(
            dict.fromkeys(
                owned_attributes
                or (
                    str(attribute).strip().lower()
                    for attribute in requirement.attributes
                )
            )
        )
        relationships = []
        for left, relation, right in requirement.relationships:
            canonical_left = canonical_entity(left)
            canonical_right = canonical_entity(right)
            rendered_relation = str(relation).strip().lower()
            if "=" in rendered_relation:
                left_attribute, right_attribute = rendered_relation.split("=", 1)
                rendered_relation = (
                    f"{canonical_attribute(canonical_left, left_attribute)}="
                    f"{canonical_attribute(canonical_right, right_attribute)}"
                )
            relationships.append(
                (canonical_left, rendered_relation, canonical_right)
            )
        for item in plan_references:
            if item.entity not in rewritten_entities:
                unresolved.append(
                    {
                        "query_id": requirement.query_id,
                        "entity": item.entity,
                        "attribute": item.attribute,
                    }
                )
        rewritten.append(
            replace(
                requirement,
                entities=rewritten_entities,
                attributes=rewritten_attributes,
                attribute_bindings=bindings,
                relationships=tuple(dict.fromkeys(relationships)),
                plan=rewritten_plan,
            )
        )

    return tuple(rewritten), {
        "entity_aliases": {
            alias: canonical
            for alias, canonical in sorted(entity_aliases.items())
            if alias != canonical
        },
        "alias_evidence": alias_evidence,
        "unresolved_symbols": unresolved,
    }


def _plan_contract_diagnostics(
    requirement: QueryRequirement,
) -> Tuple[str, ...]:
    """Return hard structural defects derivable from operators and NL cues."""
    plan = requirement.plan
    lowered = requirement.text.lower()
    operators = set(requirement.operators)
    aggregate_operators = operators & {"count", "sum", "avg", "min", "max"}
    expected = _expected_aggregate(requirement.text)
    if expected is not None:
        aggregate_operators.add(expected)
    group_cue = bool(
        "group_by" in operators
        or re.search(
            r"\b(?:group(?:ed)?\s+by|by\s+each|"
            r"(?:for|at|in|of)\s+(?:each|every)|"
            r"(?:each|every)\s+[a-z]|per\s+(?:each\s+)?[a-z])",
            lowered,
        )
    )
    having_cue = (
        "having" in operators
        or bool(re.search(r"\bhaving\b", lowered))
        or _expects_group_cardinality_having(requirement.text)
    )
    group_cue = group_cue or having_cue
    filter_cue = bool(
        "filter" in operators
        or re.search(
            r"\b(?:where|whose|known|aged|drafted|before|after|at least|at most|"
            r"or later|greater than|less than|equal to|"
            r"more than (?:one|two|three|\d+) "
            r"(?:hundred|thousand|million|billion)|matching)\b",
            lowered,
        )
    )
    diagnostics: List[str] = []
    if plan is None:
        if aggregate_operators:
            diagnostics.append("missing_plan_for_aggregate")
        if group_cue:
            diagnostics.append("missing_plan_for_group")
        if filter_cue:
            diagnostics.append("missing_plan_for_filter")
        if having_cue:
            diagnostics.append("missing_plan_for_having")
        return tuple(diagnostics)
    plan_functions = {aggregate.function for aggregate in plan.aggregates}
    if aggregate_operators and not (aggregate_operators & plan_functions):
        diagnostics.append("missing_or_wrong_aggregate")
    if group_cue and aggregate_operators and not plan.group_by:
        diagnostics.append("missing_group_by")
    if filter_cue and plan.predicate is None:
        diagnostics.append("missing_filter")
    if having_cue and not plan.having:
        diagnostics.append("missing_having")
    if plan.aggregates and any(
        projection not in plan.group_by for projection in plan.projections
    ):
        diagnostics.append("bare_projection_in_aggregate")
    if plan.group_by and not plan.aggregates:
        diagnostics.append("group_by_without_aggregate")
    return tuple(dict.fromkeys(diagnostics))


def _sql_requirement(query_id: str, sql: str) -> QueryRequirement:
    if sqlglot is None or exp is None:
        raise RuntimeError("sqlglot is required to analyze SQL workloads")
    tree = sqlglot.parse_one(sql)
    aliases: Dict[str, str] = {}
    entities: List[str] = []
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name not in entities:
            entities.append(name)
        aliases[name] = name
        aliases[(table.alias_or_name or name).lower()] = name

    def column_ref(
        column: "exp.Column", semantic_type: str = "text"
    ) -> AttributeRef:
        fallback = entities[0] if entities else "record"
        entity = aliases.get((column.table or fallback).lower(), fallback)
        return AttributeRef(entity, column.name.lower(), semantic_type)

    attributes: List[str] = []
    attribute_bindings: List[Tuple[str, str]] = []
    for column in tree.find_all(exp.Column):
        name = column.name.lower()
        if name not in attributes:
            attributes.append(name)
        table_name = aliases.get((column.table or "").lower())
        if table_name is None and len(entities) == 1:
            table_name = entities[0]
        binding = (table_name, name) if table_name else None
        if binding and binding not in attribute_bindings:
            attribute_bindings.append(binding)

    relationships: List[Tuple[str, str, str]] = []
    for join in tree.find_all(exp.Join):
        on_expr = join.args.get("on")
        if on_expr is None:
            continue
        for equality in on_expr.find_all(exp.EQ):
            left, right = equality.left, equality.right
            if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                continue
            fallback_table = entities[0] if entities else "record"
            left_raw = (left.table or fallback_table).lower()
            right_raw = (right.table or fallback_table).lower()
            left_table = aliases.get(left_raw, left_raw)
            right_table = aliases.get(right_raw, right_raw)
            relationships.append(
                (left_table, f"{left.name.lower()}={right.name.lower()}", right_table)
            )

    operators: List[str] = []
    op_types = (
        (exp.Count, "count"),
        (exp.Sum, "sum"),
        (exp.Avg, "avg"),
        (exp.Min, "min"),
        (exp.Max, "max"),
        (exp.Group, "group_by"),
        (exp.Where, "filter"),
        (exp.Having, "having"),
        (exp.Join, "join"),
    )
    for node_type, label in op_types:
        if next(tree.find_all(node_type), None) is not None:
            operators.append(label)

    aggregate_types = (
        (exp.Count, "count"),
        (exp.Sum, "sum"),
        (exp.Avg, "avg"),
        (exp.Min, "min"),
        (exp.Max, "max"),
    )
    aggregates: List[AggregateSpec] = []
    projections: List[AttributeRef] = []
    for expression in tree.expressions:
        alias = expression.alias_or_name.lower() if expression.alias_or_name else ""
        value = expression.this if isinstance(expression, exp.Alias) else expression
        matched_aggregate = False
        for node_type, function in aggregate_types:
            if isinstance(value, node_type):
                argument = value.this
                reference = (
                    column_ref(
                        argument,
                        "integer" if function in {"count", "sum"} else "real",
                    )
                    if isinstance(argument, exp.Column)
                    else None
                )
                aggregates.append(
                    AggregateSpec(
                        function=function,
                        attribute=reference,
                        alias=alias,
                        distinct=bool(value.args.get("distinct")),
                    )
                )
                matched_aggregate = True
                break
        if not matched_aggregate and isinstance(value, exp.Column):
            projections.append(column_ref(value))

    group_by: List[AttributeRef] = []
    group = tree.args.get("group")
    if group is not None:
        for expression in group.expressions:
            if isinstance(expression, exp.Column):
                group_by.append(column_ref(expression))

    comparison_types = (
        (exp.EQ, "="), (exp.NEQ, "!="), (exp.LT, "<"),
        (exp.LTE, "<="), (exp.GT, ">"), (exp.GTE, ">="),
    )

    def literal_value(node: "exp.Expression") -> object:
        if isinstance(node, exp.Null):
            return None
        if isinstance(node, exp.Boolean):
            return str(node.this).lower() == "true"
        if isinstance(node, exp.Literal):
            if node.is_number:
                rendered = str(node.this)
                return float(rendered) if "." in rendered else int(rendered)
            return str(node.this)
        return node.sql()

    def predicate(node: Optional["exp.Expression"]) -> Optional[PredicateSpec]:
        if node is None:
            return None
        if isinstance(node, exp.Paren):
            return predicate(node.this)
        if isinstance(node, (exp.And, exp.Or)):
            children = tuple(
                child
                for child in (predicate(node.left), predicate(node.right))
                if child is not None
            )
            if not children:
                return None
            if len(children) == 1:
                return children[0]
            return PredicateSpec(
                kind="and" if isinstance(node, exp.And) else "or",
                children=children,
            )
        if isinstance(node, exp.Is) and isinstance(node.this, exp.Column):
            if isinstance(node.expression, exp.Null):
                return PredicateSpec(
                    attribute=column_ref(node.this), operator="is_null"
                )
        for node_type, operator in comparison_types:
            if isinstance(node, node_type):
                if isinstance(node.left, exp.Column):
                    value = literal_value(node.right)
                    semantic_type = (
                        "integer" if isinstance(value, int)
                        else "real" if isinstance(value, float)
                        else "date" if isinstance(value, str)
                        and bool(re.match(r"^\d{4}[-/]", value))
                        else "text"
                    )
                    return PredicateSpec(
                        attribute=column_ref(node.left, semantic_type),
                        operator=operator,
                        value=value,
                    )
        return None

    where = tree.args.get("where")
    parsed_predicate = predicate(where.this if where is not None else None)
    having_specs: List[HavingSpec] = []
    having_clause = tree.args.get("having")

    def collect_having(node: Optional["exp.Expression"]) -> None:
        if node is None:
            return
        if isinstance(node, exp.Paren):
            collect_having(node.this)
            return
        if isinstance(node, exp.And):
            collect_having(node.left)
            collect_having(node.right)
            return
        for node_type, operator in comparison_types:
            if not isinstance(node, node_type):
                continue
            aggregate_node = node.left
            for aggregate_type, function in aggregate_types:
                if not isinstance(aggregate_node, aggregate_type):
                    continue
                argument = aggregate_node.this
                distinct = isinstance(argument, exp.Distinct)
                if distinct:
                    argument = (
                        argument.expressions[0]
                        if argument.expressions
                        else argument
                    )
                reference = (
                    column_ref(
                        argument,
                        "integer" if function in {"count", "sum"} else "real",
                    )
                    if isinstance(argument, exp.Column)
                    else None
                )
                try:
                    having_specs.append(
                        HavingSpec(
                            AggregateSpec(
                                function=function,
                                attribute=reference,
                                distinct=distinct,
                            ),
                            operator=operator,
                            value=literal_value(node.right),
                        )
                    )
                except ValueError:
                    pass
                return

    collect_having(
        having_clause.this if having_clause is not None else None
    )
    join_specs: List[JoinSpec] = []
    for join in tree.find_all(exp.Join):
        on_expr = join.args.get("on")
        if on_expr is None:
            continue
        for equality in on_expr.find_all(exp.EQ):
            if isinstance(equality.left, exp.Column) and isinstance(
                equality.right, exp.Column
            ):
                join_specs.append(
                    JoinSpec(
                        column_ref(equality.left),
                        column_ref(equality.right),
                        "left"
                        if str(join.args.get("kind", "")).lower() == "left"
                        else "inner",
                    )
                )
    plan = QueryPlan(
        projections=tuple(projections),
        group_by=tuple(group_by),
        aggregates=tuple(aggregates),
        predicate=parsed_predicate,
        joins=tuple(join_specs),
        having=tuple(having_specs),
    )

    return QueryRequirement(
        query_id=query_id,
        text=sql,
        entities=tuple(entities),
        attributes=tuple(attributes),
        attribute_bindings=tuple(attribute_bindings),
        relationships=tuple(relationships),
        operators=tuple(operators),
        units=tuple(sorted({m.group(1).lower() for m in _UNIT_RE.finditer(sql)})),
        plan=plan,
    )


def _heuristic_nl_requirement(query_id: str, text: str) -> QueryRequirement:
    lowered = text.lower()
    operators: List[str] = []
    for phrase, operator in _AGGREGATES.items():
        if phrase in lowered and operator not in operators:
            operators.append(operator)
    if any(token in lowered for token in (" where ", " whose ", " with ", " before ", " after ")):
        operators.append("filter")
    if any(token in lowered for token in (" between ", " compared ", " per ", " each ")):
        operators.append("group_by")
    if any(token in lowered for token in (" related ", " owned by ", " belongs to ", " joined ")):
        operators.append("join")

    content_words = [
        word.lower()
        for word in _WORD_RE.findall(text)
        if word.lower() not in _STOPWORDS and len(word) > 2
    ]
    # Without an LLM we deliberately produce a conservative generic entity and
    # retain content terms as candidate attributes. This is auditable and never
    # pretends to have inferred a domain schema with high confidence.
    attributes = tuple(dict.fromkeys(content_words))
    return QueryRequirement(
        query_id=query_id,
        text=text,
        entities=("record",),
        attributes=attributes,
        operators=tuple(dict.fromkeys(operators)),
        units=tuple(sorted({m.group(1).lower() for m in _UNIT_RE.finditer(text)})),
    )


def _parse_llm_payload(
    payload: str,
    queries_by_id: Mapping[str, str],
    *,
    entity_vocabulary: Sequence[str] = (),
    attribute_vocabulary: Optional[Mapping[str, Sequence[str]]] = None,
) -> List[QueryRequirement]:
    start, end = payload.find("["), payload.rfind("]")
    if start < 0:
        raise ValueError("intent analyzer did not return a JSON array")
    candidate = payload[start : end + 1] if end >= start else payload[start:]
    try:
        rows = json.loads(candidate)
    except json.JSONDecodeError:
        rows = repair_json(candidate, return_objects=True)
    if not isinstance(rows, list):
        raise ValueError("intent payload must be a list")
    requirements: List[QueryRequirement] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        query_id = str(row.get("query_id", ""))
        if query_id not in queries_by_id or query_id in seen:
            continue
        seen.add(query_id)
        def list_field(name: str) -> list:
            value = row.get(name)
            return list(value) if isinstance(value, (list, tuple)) else []

        canonical_entities = [
            entity
            for entity in (
                _canonical_entity(value, entity_vocabulary)
                for value in list_field("entities")
            )
            if entity
        ]
        default_entity = canonical_entities[0] if canonical_entities else (
            entity_vocabulary[0] if len(entity_vocabulary) == 1 else ""
        )
        context_references: List[AttributeRef] = []
        for value in list_field("attribute_bindings"):
            if isinstance(value, Mapping):
                reference = _attribute_ref(
                    value,
                    entity_vocabulary,
                    default_entity,
                    attribute_vocabulary,
                )
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                reference = _attribute_ref(
                    {"entity": value[0], "attribute": value[1]},
                    entity_vocabulary,
                    default_entity,
                    attribute_vocabulary,
                )
            else:
                reference = None
            if reference is not None:
                context_references.append(reference)
        relationships = []
        for rel in list_field("relationships"):
            if isinstance(rel, Mapping):
                parsed = (
                    _canonical_entity(
                        rel.get("left"), entity_vocabulary, default_entity
                    ),
                    str(rel.get("relation", "")).lower(),
                    _canonical_entity(
                        rel.get("right"), entity_vocabulary, default_entity
                    ),
                )
                if all(parsed):
                    relationships.append(parsed)
            elif isinstance(rel, (list, tuple)) and len(rel) == 3:
                parsed = (
                    _canonical_entity(
                        rel[0], entity_vocabulary, default_entity
                    ),
                    str(rel[1]).lower(),
                    _canonical_entity(
                        rel[2], entity_vocabulary, default_entity
                    ),
                )
                if all(parsed):
                    relationships.append(parsed)
        plan = _query_plan(
            row.get("plan"),
            entity_vocabulary,
            default_entity,
            attribute_vocabulary,
        )
        plan = _repair_plan_aggregate(
            plan,
            queries_by_id[query_id],
            context_references=context_references,
            attribute_vocabulary=attribute_vocabulary,
        )
        plan_references = plan.attributes() if plan else ()
        entities = list(
            dict.fromkeys(
                [
                    *canonical_entities,
                    *(reference.entity for reference in plan_references),
                ]
            )
        )
        attributes = (
            list(
                dict.fromkeys(
                    reference.attribute
                    for reference in (*plan_references, *context_references)
                )
            )
            if plan
            else list(
                dict.fromkeys(
                    str(value).lower()
                    for value in list_field("attributes")
                )
            )
        )
        bindings = list(
            (reference.entity, reference.attribute)
            for reference in (*plan_references, *context_references)
        )
        bindings = list(dict.fromkeys(bindings))
        operators = list(
            dict.fromkeys(str(v).lower() for v in list_field("operators"))
        )
        if plan:
            operators.extend(
                aggregate.function
                for aggregate in plan.aggregates
                if aggregate.function not in operators
            )
            if plan.group_by and "group_by" not in operators:
                operators.append("group_by")
            if plan.predicate and "filter" not in operators:
                operators.append("filter")
            if plan.joins and "join" not in operators:
                operators.append("join")
        requirements.append(
            QueryRequirement(
                query_id=query_id,
                text=queries_by_id[query_id],
                entities=tuple(entities),
                attributes=tuple(attributes),
                attribute_bindings=tuple(bindings),
                relationships=tuple(relationships),
                operators=tuple(dict.fromkeys(operators)),
                units=tuple(
                    dict.fromkeys(str(v).lower() for v in list_field("units"))
                ),
                plan=plan,
            )
        )
    missing = set(queries_by_id) - seen
    requirements.extend(
        _heuristic_nl_requirement(query_id, queries_by_id[query_id])
        for query_id in sorted(missing)
    )
    return requirements


def analyze_workload(
    queries: Sequence[Mapping[str, Any] | str],
    *,
    llm_client: Optional[Any] = None,
    entity_vocabulary: Sequence[str] = (),
    attribute_vocabulary: Optional[Mapping[str, Sequence[str]]] = None,
    join_vocabulary: Sequence[Tuple[str, str, str, str]] = (),
    intent_max_workers: int = 1,
) -> WorkloadIntent:
    """Analyze SQL or NL workload without reading any ground-truth artifact."""
    if intent_max_workers < 1:
        raise ValueError("intent_max_workers must be at least 1")
    normalized: List[Tuple[str, str]] = []
    for index, query in enumerate(queries):
        if isinstance(query, str):
            normalized.append((f"q{index}", query))
        else:
            normalized.append(
                (
                    str(query.get("query_id", f"q{index}")),
                    str(query.get("text") or query.get("nl_query") or query.get("sql") or ""),
                )
            )
    if not normalized or any(not text.strip() for _, text in normalized):
        raise ValueError("workload queries must contain non-empty text")

    sql_requirements: Dict[str, QueryRequirement] = {}
    nl_queries: Dict[str, str] = {}
    for query_id, text in normalized:
        if _is_sql(text):
            sql_requirements[query_id] = _sql_requirement(query_id, text)
        else:
            nl_queries[query_id] = text

    nl_requirements: List[QueryRequirement]
    if nl_queries and llm_client is not None:
        entity_instruction = ""
        if entity_vocabulary:
            entity_instruction = (
                "The only available source entity types are "
                f"{json.dumps(list(entity_vocabulary))}. Every entity and every "
                "attribute owner must be one of these exact values. Treat all "
                "other nouns as attributes, measures, values, or relationship "
                "phrases—not as new entities. Do not invent identifier columns "
                "or relations; use a natural label relationship stated or "
                "implied by the question.\n\n"
            )
        if attribute_vocabulary:
            entity_instruction += (
                "Use only these canonical source attributes, selecting the "
                "closest semantically matching attribute for each query phrase:\n"
                f"{json.dumps(attribute_vocabulary, sort_keys=True)}\n\n"
            )
        if join_vocabulary:
            entity_instruction += (
                "Use only these canonical source join edges:\n"
                f"{json.dumps(list(join_vocabulary))}\n\n"
            )
        instructions = (
            "Convert every analytical question into a lossless, schema-independent "
            "query plan. Return ONLY a JSON array. Preserve every literal value "
            "exactly as written; never translate, expand, normalize, or replace "
            "categorical values and names. Preserve the analytical operation: "
            "COUNT measures entity cardinality or non-null values, SUM totals a "
            "numeric measure, AVG computes a numeric mean, and MIN/MAX compute "
            "extrema. Resolve potentially ambiguous phrases compositionally from "
            "what is being measured rather than from a keyword alone. Use concise "
            "lowercase snake_case names derived only from the query wording.\n\n"
            "Each item must contain query_id, entities, attributes, "
            "attribute_bindings, relationships, operators, units, and plan. "
            "plan must contain:\n"
            "- projections and group_by: arrays of {entity, attribute, "
            "semantic_type};\n"
            "- aggregates: array of {function, attribute (or null for COUNT(*)), "
            "alias, distinct};\n"
            "- having: array of {aggregate:{function, attribute (or null for "
            "COUNT(*)), alias, distinct}, operator, value}. Use this only for "
            "restrictions on grouped aggregate values such as groups with more "
            "than one member;\n"
            "- predicate: null or a recursive tree. Leaves are {kind:'predicate', "
            "entity, attribute, semantic_type, operator, value}; boolean nodes "
            "are {kind:'and'|'or', children:[...]};\n"
            "- joins: array of {left:{entity,attribute,semantic_type}, "
            "right:{...}, join_type:'inner'|'left'}.\n"
            "Allowed semantic types are text, integer, real, date, boolean. "
            "Allowed predicate operators are =, !=, <, <=, >, >=, contains, "
            "is_null, is_not_null. Bind each property to the entity that "
            "grammatically owns it in the question. Represent an implied "
            "relationship as a join only when the question requires combining "
            "entities. Do not use corpus contents, database metadata, or "
            "ground-truth data, and do not invent domain facts.\n\nQueries:\n"
        )
        instructions = entity_instruction + instructions
        items = list(nl_queries.items())
        # Small models frequently leak predicates and groupings between adjacent
        # questions. Each worker therefore owns one complete draft -> audit
        # chain. Chains are independent, while calls inside one chain remain
        # ordered. executor.map below preserves workload order.
        analysis_diagnostics: Dict[str, Any] = {}

        def _analyze_one(item: Tuple[str, str]) -> QueryRequirement:
            query_id, query_text = item
            batch = {query_id: query_text}
            prompt = instructions + json.dumps(
                [
                    {"query_id": query_id, "query": query_text}
                ],
                indent=2,
            )
            response = llm_client.generate(
                prompt, max_tokens=4096, temperature=0.0
            )
            drafts = _parse_llm_payload(
                response,
                batch,
                entity_vocabulary=entity_vocabulary,
                attribute_vocabulary=attribute_vocabulary,
            )
            draft = drafts[0]
            candidates = [draft]
            candidate_sources = ["json_draft"]

            def requirement_for_plan(plan: QueryPlan) -> QueryRequirement:
                references = plan.attributes()

                def predicate_operators(
                    predicate: Optional[PredicateSpec],
                ) -> Tuple[str, ...]:
                    if predicate is None:
                        return ()
                    if predicate.kind == "predicate":
                        return (predicate.operator,)
                    return tuple(
                        operator
                        for child in predicate.children
                        for operator in predicate_operators(child)
                    )

                return QueryRequirement(
                    query_id=query_id,
                    text=query_text,
                    entities=tuple(
                        dict.fromkeys(
                            reference.entity for reference in references
                        )
                    ),
                    attributes=tuple(
                        dict.fromkeys(
                            reference.attribute for reference in references
                        )
                    ),
                    attribute_bindings=tuple(
                        dict.fromkeys(
                            (reference.entity, reference.attribute)
                            for reference in references
                        )
                    ),
                    relationships=tuple(
                        (
                            join.left.entity,
                            "join",
                            join.right.entity,
                        )
                        for join in plan.joins
                    ),
                    operators=predicate_operators(plan.predicate),
                    plan=plan,
                )
            review_prompt = (
                "Audit and correct one schema-independent analytical query plan. "
                "Return ONLY a JSON array containing one complete corrected item "
                "in the same shape as the draft. Re-read the question rather than "
                "trusting the draft.\n\n"
                "Checklist:\n"
                "1. Preserve the exact requested aggregate and its numeric measure; "
                "COUNT(*) is only entity cardinality, while COUNT(attribute) counts "
                "known values.\n"
                "2. Include grouping dimensions only for aggregate queries. "
                "In a projection question, 'for every record' means return one "
                "row per matching record and MUST NOT create GROUP BY. In an "
                "aggregate question, include exactly the dimensions requested "
                "by 'for each', 'by', or 'group'. Do not group by a constant "
                "used only as a filter.\n"
                "3. Encode every record restriction from the question and no extra "
                "restriction. Before writing the plan, inventory every number, date, "
                "capitalized name/adjective, and negative cue (no/not/other than); "
                "each must appear in exactly one correctly scoped predicate. Preserve "
                "literals and comparison directions exactly. 'No <numeric measure>' "
                "means that measure equals zero.\n"
                "4. Preserve AND/OR/NOT scope. A relationship equality belongs in "
                "joins, never as a literal-valued predicate.\n"
                "5. Use only the supplied source entity types. Do not invent ID "
                "columns, tables, measures, or conditions not named or implied by "
                "the question.\n"
                "6. A property belongs to the entity grammatically possessing it. "
                "Use concise lowercase snake_case attribute names.\n\n"
                f"Allowed source entities: {json.dumps(list(entity_vocabulary))}\n"
                "Allowed canonical attributes: "
                f"{json.dumps(attribute_vocabulary or {}, sort_keys=True)}\n"
                "Allowed canonical joins: "
                f"{json.dumps(list(join_vocabulary))}\n"
                f"Question: {query_text}\n\n"
                "Draft:\n"
                f"{json.dumps(asdict(draft), indent=2, default=str)}"
            )
            try:
                reviewed_response = llm_client.generate(
                    review_prompt, max_tokens=4096, temperature=0.0
                )
                reviewed = _parse_llm_payload(
                    reviewed_response,
                    batch,
                    entity_vocabulary=entity_vocabulary,
                    attribute_vocabulary=attribute_vocabulary,
                )
                if reviewed and reviewed[0].plan is not None:
                    candidates.append(reviewed[0])
                    candidate_sources.append("json_audit")
            except (RuntimeError, ValueError, TypeError):
                # The independently budgeted draft remains usable and auditable
                # when the semantic reviewer emits malformed output.
                pass
            # Build an independent SQL-shaped interpretation. Small models are
            # often substantially better at familiar SQL syntax than deeply
            # nested JSON predicate trees. Parsing it back into the same IR
            # gives contract scoring an independent candidate without allowing
            # SQL to bypass the synthesis firewall.
            sql_prompt = (
                "Translate the analytical question into one SQLite SELECT "
                "query. Return SQL only. Use exactly the supplied tables, "
                "columns, and join edges. Preserve every predicate, Boolean "
                "operator, grouping dimension, aggregate target, and literal. "
                "Projection questions must not use GROUP BY. Do not add "
                "conditions merely because entities are joined.\n\n"
                f"Tables and columns: "
                f"{json.dumps(attribute_vocabulary or {}, sort_keys=True)}\n"
                f"Join edges: {json.dumps(list(join_vocabulary))}\n"
                f"Question: {query_text}"
            )
            try:
                sql_response = llm_client.generate(
                    sql_prompt, max_tokens=2048, temperature=0.0
                )
                fenced = re.search(
                    r"```(?:sql)?\s*(.*?)```",
                    sql_response,
                    re.IGNORECASE | re.DOTALL,
                )
                rendered_sql = (
                    fenced.group(1).strip()
                    if fenced is not None
                    else sql_response.strip()
                )
                sql_start = re.search(
                    r"\b(?:SELECT|WITH)\b", rendered_sql, re.IGNORECASE
                )
                if sql_start is None:
                    raise ValueError("SQL shadow contains no SELECT/WITH")
                rendered_sql = rendered_sql[sql_start.start() :].split(
                    ";", 1
                )[0]
                shadow = _sql_requirement(query_id, rendered_sql)
                candidates.append(replace(shadow, text=query_text))
                candidate_sources.append("sql_shadow")
            except (RuntimeError, ValueError, TypeError):
                pass

            # Extract the intent once more as a flat clause ledger. This avoids
            # asking a small model to simultaneously bind attributes and build
            # a recursive Boolean tree. The tree is compiled deterministically
            # from stable filter IDs after parsing.
            ledger_prompt = (
                "Extract a complete analytical clause ledger from one question. "
                "Use only the canonical schema below and return ONLY one JSON "
                "object. Do not emit SQL and do not emit a nested query plan.\n\n"
                "Required keys:\n"
                '- \"projections\": canonical {entity, attribute, semantic_type} '
                "columns returned directly (exclude aggregate measures);\n"
                '- \"group_by\": canonical grouping columns;\n'
                '- \"aggregate\": null or one {function, attribute, alias, '
                "distinct};\n"
                '- \"filters\": a flat array of {id, entity, attribute, '
                "semantic_type, operator, value}. Create exactly one filter for "
                "each restriction and no join equalities. Preserve every literal "
                "and comparison direction. \"no <numeric measure>\" means = 0, "
                "while non-missing means is_not_null;\n"
                '- \"boolean_expression\": an expression over filter IDs using '
                "only AND, OR, and parentheses;\n"
                '- \"joins\": only required canonical join objects with left, '
                "right, and join_type.\n\n"
                "Resolve possessives and relational phrases before binding each "
                "attribute. Never use a categorical value as an attribute name. "
                "Do not infer facts absent from the question.\n\n"
                f"Canonical attributes: "
                f"{json.dumps(attribute_vocabulary or {}, sort_keys=True)}\n"
                f"Canonical joins: {json.dumps(list(join_vocabulary))}\n"
                f"Question: {query_text}"
            )
            try:
                ledger_response = llm_client.generate(
                    ledger_prompt,
                    max_tokens=3072,
                    temperature=0.0,
                )
                start = ledger_response.find("{")
                end = ledger_response.rfind("}")
                if start < 0:
                    raise ValueError("clause ledger returned no JSON object")
                rendered = (
                    ledger_response[start : end + 1]
                    if end >= start
                    else ledger_response[start:]
                )
                try:
                    ledger_payload = json.loads(rendered)
                except json.JSONDecodeError:
                    ledger_payload = repair_json(
                        rendered, return_objects=True
                    )
                ledger_plan = _plan_from_clause_ledger(
                    ledger_payload,
                    entity_vocabulary,
                    draft.entities[0] if draft.entities else "",
                    attribute_vocabulary,
                )
                if ledger_plan is not None:
                    candidates.append(requirement_for_plan(ledger_plan))
                    candidate_sources.append("clause_ledger")
            except (RuntimeError, ValueError, TypeError):
                pass

            # Fuse components according to the task each independent path is
            # best constrained to solve: SQL supplies executable output,
            # grouping, and aggregate structure; the semantic audit supplies
            # clause ownership, Boolean restrictions, and relationship intent.
            # This is component-level evidence fusion, not a source-wide vote.
            sql_index = next(
                (
                    index
                    for index, source in enumerate(candidate_sources)
                    if source == "sql_shadow"
                ),
                None,
            )
            semantic_index = next(
                (
                    index
                    for index, source in enumerate(candidate_sources)
                    if source == "json_audit"
                ),
                0,
            )
            if (
                sql_index is not None
                and candidates[sql_index].plan is not None
                and candidates[semantic_index].plan is not None
            ):
                sql_plan = candidates[sql_index].plan
                semantic_plan = candidates[semantic_index].plan
                fused_plan = QueryPlan(
                    projections=sql_plan.projections,
                    group_by=sql_plan.group_by,
                    aggregates=sql_plan.aggregates,
                    predicate=(
                        semantic_plan.predicate
                        if semantic_plan.predicate is not None
                        else sql_plan.predicate
                    ),
                    joins=(
                        semantic_plan.joins
                        if semantic_plan.joins
                        else sql_plan.joins
                    ),
                    having=(
                        semantic_plan.having
                        if semantic_plan.having
                        else sql_plan.having
                    ),
                )
                if fused_plan != sql_plan:
                    candidates.append(requirement_for_plan(fused_plan))
                    candidate_sources.append("component_fusion")

            def normalize_candidate(
                candidate: QueryRequirement,
            ) -> QueryRequirement:
                return replace(
                    candidate,
                    plan=_normalize_plan_with_schema(
                        candidate.plan,
                        query_text,
                        attribute_vocabulary=attribute_vocabulary,
                        join_vocabulary=join_vocabulary,
                        context_references=tuple(
                            AttributeRef(
                                entity,
                                attribute,
                                next(
                                    (
                                        reference.semantic_type
                                        for reference in (
                                            candidate.plan.attributes()
                                            if candidate.plan
                                            else ()
                                        )
                                        if reference.entity == entity
                                        and reference.attribute == attribute
                                    ),
                                    "text",
                                ),
                            )
                            for entity, attribute in (
                                candidate.attribute_bindings
                            )
                        ),
                    ),
                )

            raw_candidate_plans = [
                asdict(candidate.plan)
                if candidate.plan is not None
                else None
                for candidate in candidates
            ]
            normalized_candidates = [
                normalize_candidate(candidate) for candidate in candidates
            ]

            # Contract scores intentionally measure only observable structural
            # requirements. They often tie when candidates differ in Boolean
            # scope, attribute ownership, or join-path meaning. Give the same
            # budgeted model one final, label-free adjudication view containing
            # all independently produced plans and an explicit clause ledger.
            adjudication: Dict[str, Any] = {}
            if len(normalized_candidates) > 1:
                adjudication_prompt = (
                    "Adjudicate alternative query plans using only the analytical "
                    "question and supplied canonical schema. Do not use database "
                    "contents, expected answers, or domain facts.\n\n"
                    "First construct a private clause ledger containing: (1) every "
                    "requested output expression, (2) aggregate and grouping, "
                    "(3) every filter with an exact quote, canonical attribute, "
                    "operator, and literal, (4) the exact AND/OR tree, and (5) only "
                    "the joins required to connect referenced entities. Compare "
                    "every candidate against that ledger. Prefer an unchanged "
                    "candidate only when it is lossless. Otherwise return a corrected "
                    "plan assembled from the canonical schema.\n\n"
                    "Return ONLY one JSON object with keys selected_source, plan, "
                    "and checks. selected_source must be json_draft, json_audit, "
                    "sql_shadow, clause_ledger, component_fusion, or corrected. "
                    "plan must be null when selecting an "
                    "unchanged candidate, and otherwise must be one complete plan "
                    "with projections, group_by, aggregates, predicate, having, "
                    "and joins. "
                    "checks must briefly record output_count, filter_count, "
                    "literal_count, boolean_scope, and join_count.\n\n"
                    f"Canonical attributes: "
                    f"{json.dumps(attribute_vocabulary or {}, sort_keys=True)}\n"
                    f"Canonical joins: {json.dumps(list(join_vocabulary))}\n"
                    f"Question: {query_text}\n"
                    "Candidates:\n"
                    + json.dumps(
                        [
                            {
                                "source": candidate_sources[index],
                                "plan": asdict(candidate.plan),
                            }
                            for index, candidate in enumerate(
                                normalized_candidates
                            )
                            if candidate.plan is not None
                        ],
                        indent=2,
                        default=str,
                    )
                )
                try:
                    adjudication_response = llm_client.generate(
                        adjudication_prompt,
                        max_tokens=4096,
                        temperature=0.0,
                    )
                    start = adjudication_response.find("{")
                    end = adjudication_response.rfind("}")
                    if start < 0:
                        raise ValueError(
                            "semantic adjudicator returned no JSON object"
                        )
                    rendered = (
                        adjudication_response[start : end + 1]
                        if end >= start
                        else adjudication_response[start:]
                    )
                    try:
                        adjudication_payload = json.loads(rendered)
                    except json.JSONDecodeError:
                        adjudication_payload = repair_json(
                            rendered, return_objects=True
                        )
                    if not isinstance(adjudication_payload, Mapping):
                        raise ValueError(
                            "semantic adjudicator payload must be an object"
                        )
                    selected_source = str(
                        adjudication_payload.get("selected_source", "")
                    ).strip()
                    adjudicated_plan = _query_plan(
                        adjudication_payload.get("plan"),
                        entity_vocabulary,
                        (
                            normalized_candidates[0].entities[0]
                            if normalized_candidates[0].entities
                            else ""
                        ),
                        attribute_vocabulary,
                    )
                    if adjudicated_plan is None:
                        if selected_source not in candidate_sources:
                            raise ValueError(
                                "semantic adjudicator selected no valid candidate"
                            )
                        selected_candidate = normalized_candidates[
                            candidate_sources.index(selected_source)
                        ]
                        adjudicated_plan = selected_candidate.plan
                    if adjudicated_plan is None:
                        raise ValueError(
                            "semantic adjudicator produced no usable plan"
                        )
                    adjudicated = requirement_for_plan(adjudicated_plan)
                    raw_candidate_plans.append(asdict(adjudicated_plan))
                    normalized_candidates.append(
                        normalize_candidate(adjudicated)
                    )
                    candidate_sources.append("semantic_adjudicator")
                    adjudication = {
                        "selected_source": selected_source,
                        "checks": adjudication_payload.get("checks"),
                    }
                except (RuntimeError, ValueError, TypeError):
                    # The original independent candidates remain available when
                    # the adjudicator emits malformed or incomplete JSON.
                    pass
            scored_candidates = [
                (
                    _plan_contract_score(candidate.plan, query_text),
                    index,
                    candidate,
                )
                for index, candidate in enumerate(normalized_candidates)
            ]
            base_scored_candidates = [
                item
                for item in scored_candidates
                if candidate_sources[item[1]] != "semantic_adjudicator"
            ]
            _score, selected_index, draft = max(
                base_scored_candidates,
                key=lambda item: (item[0], item[1]),
            )
            adjudicator_item = next(
                (
                    item
                    for item in scored_candidates
                    if candidate_sources[item[1]]
                    == "semantic_adjudicator"
                ),
                None,
            )
            if adjudicator_item is not None:
                adjudicator_score = adjudicator_item[0]
                adjudicated_source = adjudication.get("selected_source")
                if adjudicator_score > _score:
                    _score, selected_index, draft = adjudicator_item
                elif adjudicated_source in candidate_sources:
                    adjudicated_index = candidate_sources.index(
                        adjudicated_source
                    )
                    adjudicated_candidate = normalized_candidates[
                        adjudicated_index
                    ]
                    independently_corroborated = any(
                        index != adjudicated_index
                        and source != "semantic_adjudicator"
                        and candidate.plan == adjudicated_candidate.plan
                        for index, (source, candidate) in enumerate(
                            zip(
                                candidate_sources,
                                normalized_candidates,
                            )
                        )
                    )
                    adjudicated_item = next(
                        item
                        for item in scored_candidates
                        if item[1] == adjudicated_index
                    )
                    if (
                        independently_corroborated
                        and adjudicated_item[0] >= _score
                    ):
                        _score, selected_index, draft = adjudicated_item
            analysis_diagnostics[query_id] = {
                "selected_source": candidate_sources[selected_index],
                "adjudication": adjudication,
                "candidates": [
                    {
                        "source": candidate_sources[index],
                        "contract_score": score,
                        "raw_plan": raw_candidate_plans[index],
                        "plan": (
                            asdict(candidate.plan)
                            if candidate.plan is not None
                            else None
                        ),
                    }
                    for score, index, candidate in scored_candidates
                ],
            }
            return draft

        worker_count = min(intent_max_workers, len(items))
        if worker_count == 1:
            nl_requirements = [_analyze_one(item) for item in items]
        else:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                nl_requirements = list(executor.map(_analyze_one, items))
    else:
        nl_requirements = [
            _heuristic_nl_requirement(query_id, text)
            for query_id, text in nl_queries.items()
        ]

    by_id = {**sql_requirements, **{r.query_id: r for r in nl_requirements}}
    raw_ordered = tuple(by_id[query_id] for query_id, _ in normalized)
    ordered, canonicalization_diagnostics = (
        _canonicalize_workload_requirements(raw_ordered)
    )
    base_diagnostics = (
        dict(analysis_diagnostics)
        if nl_queries and llm_client is not None
        else {}
    )
    contract_diagnostics = {
        requirement.query_id: {
            "valid": not violations,
            "violations": list(violations),
        }
        for requirement in ordered
        if (violations := _plan_contract_diagnostics(requirement))
    }
    base_diagnostics["_workload"] = {
        "canonicalization": canonicalization_diagnostics,
        "plan_contracts": contract_diagnostics,
        "rejected_query_ids": sorted(contract_diagnostics),
    }
    return WorkloadIntent(
        requirements=ordered,
        entity_frequency=dict(Counter(v for r in ordered for v in r.entities)),
        attribute_frequency=dict(Counter(v for r in ordered for v in r.attributes)),
        operator_frequency=dict(Counter(v for r in ordered for v in r.operators)),
        analysis_diagnostics=base_diagnostics,
    )


def make_budgeted_intent_analyzer(
    llm_client: Any,
    *,
    entity_vocabulary: Sequence[str] = (),
    attribute_vocabulary: Optional[Mapping[str, Sequence[str]]] = None,
    join_vocabulary: Sequence[Tuple[str, str, str, str]] = (),
    intent_max_workers: int = 1,
):
    """Adapt a WDIRS-compatible client to the system's analyzer callback."""

    def analyzer(
        queries: Sequence[Mapping[str, Any] | str],
        ledger: GlobalBudgetLedger,
    ) -> WorkloadIntent:
        budgeted = BudgetedLLMClient(
            llm_client, ledger, default_stage="workload_analysis"
        )
        return analyze_workload(
            queries,
            llm_client=budgeted,
            entity_vocabulary=entity_vocabulary,
            attribute_vocabulary=attribute_vocabulary,
            join_vocabulary=join_vocabulary,
            intent_max_workers=intent_max_workers,
        )

    return analyzer
