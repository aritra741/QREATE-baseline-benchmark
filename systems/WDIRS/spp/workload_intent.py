"""Ground-truth-free workload intent analysis.

Natural-language queries are converted into a schema-independent requirement
IR. SQL input remains supported for diagnostics and migration experiments.
The analyzer never reads UDA-Bench tables or attributes metadata.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, replace
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from json_repair import repair_json

from spp.budget_ledger import GlobalBudgetLedger
from spp.budgeted_llm import BudgetedLLMClient
from spp.spec import (
    AggregateSpec,
    AttributeRef,
    JoinSpec,
    PredicateSpec,
    QueryPlan,
    QueryRequirement,
)

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
    )
    return plan if plan.attributes() or plan.aggregates else None


def _expected_aggregate(text: str) -> Optional[str]:
    lowered = text.lower()
    if re.search(r"\b(average|mean)\b", lowered):
        return "avg"
    if re.search(r"\b(fewest|lowest|smallest|minimum)\b", lowered):
        return "min"
    if re.search(r"\b(largest|highest|greatest|maximum)\b", lowered):
        return "max"
    if re.search(r"\b(total|combined|altogether|sum)\b", lowered):
        return "sum"
    if re.search(r"\b(how many|count)\b", lowered):
        return "count"
    return None


def _repair_plan_aggregate(
    plan: Optional[QueryPlan], text: str
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
            for reference in projections
            if reference not in grouped
        ]
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
                    for reference in projections
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


def _normalize_plan_with_schema(
    plan: Optional[QueryPlan],
    text: str,
    *,
    attribute_vocabulary: Optional[Mapping[str, Sequence[str]]] = None,
    join_vocabulary: Sequence[Tuple[str, str, str, str]] = (),
) -> Optional[QueryPlan]:
    if plan is None:
        return None
    lowered = text.lower()
    core_entities = {
        reference.entity
        for reference in (*plan.projections, *plan.group_by)
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
            if (
                kind == "and"
                and " or " in lowered
                and "either" not in lowered
            ):
                kind = "or"
            return replace(predicate, kind=kind, children=children)
        value = predicate.value
        if isinstance(value, Mapping):
            return None
        if isinstance(value, (list, tuple)) and len(value) == 1:
            value = value[0]
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
        operator = predicate.operator
        rendered = str(value).lower()
        position = lowered.find(rendered)
        context = ""
        if position >= 0:
            prefix = lowered[:position]
            boundary = max(
                prefix.rfind(" or "),
                prefix.rfind(" and "),
                prefix.rfind(","),
                prefix.rfind(";"),
            )
            context = prefix[boundary + 1 :]
        if re.search(r"\b(not|other than|different from)\b", context):
            operator = "!="
        elif re.search(r"\b(more than|greater than|above|after)\b", context):
            operator = ">"
        elif re.search(r"\b(at least|no fewer than)\b", context):
            operator = ">="
        elif re.search(r"\b(less than|fewer than|below|before)\b", context):
            operator = "<"
        elif re.search(r"\b(at most|no more than|or earlier)\b", context):
            operator = "<="
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

    predicate = clean_predicate(plan.predicate)
    aggregates = list(plan.aggregates)
    if (
        aggregates
        and aggregates[0].function == "count"
        and aggregates[0].attribute is None
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
        predicate_attributes: set[Tuple[str, str]] = set()

        def collect_predicates(value: Optional[PredicateSpec]) -> None:
            if value is None:
                return
            if (
                value.attribute is not None
                and value.operator != "is_not_null"
            ):
                predicate_attributes.add(
                    (value.attribute.entity, value.attribute.attribute)
                )
            for child in value.children:
                collect_predicates(child)

        collect_predicates(predicate)
        candidates = [
            candidate
            for candidate in candidates
            if (candidate.entity, candidate.attribute)
            not in predicate_attributes
        ]
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

    group_by = list(plan.group_by)
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
    if group_clause and attribute_vocabulary:
        excluded = {
            (aggregate.attribute.entity, aggregate.attribute.attribute)
            for aggregate in aggregates
            if aggregate.attribute is not None
        }

        def collect_excluded(value: Optional[PredicateSpec]) -> None:
            if value is None:
                return
            if value.attribute is not None:
                excluded.add(
                    (value.attribute.entity, value.attribute.attribute)
                )
            for child in value.children:
                collect_excluded(child)

        collect_excluded(predicate)
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
    if (
        not group_by
        and aggregates
        and aggregates[0].function == "count"
        and predicate is not None
        and predicate.kind == "predicate"
        and predicate.operator == "="
        and isinstance(predicate.value, str)
    ):
        group_by = [predicate.attribute]

    if aggregates and attribute_vocabulary:
        grouped_keys = {
            (reference.entity, reference.attribute) for reference in group_by
        }
        existing_refs = {
            (reference.entity, reference.attribute): reference
            for reference in plan.attributes()
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
            positions = [lowered.find(token) for token in tokens]
            return min(positions) if positions and all(pos >= 0 for pos in positions) else -1

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
            target = max(
                candidates,
                key=lambda reference: (
                    reference.entity in mentioned_entities,
                    reference.entity in core_entities,
                    -abs(phrase_position(reference.attribute) - cue_position),
                    len(reference.attribute.split("_")),
                ),
            )
            aggregates[0] = replace(
                aggregates[0],
                attribute=target,
                alias=f"{aggregates[0].function}_{target.attribute}",
            )

    # In an aggregate query every non-aggregate output must be a grouping
    # dimension. Discard leaked projections from the LLM audit; otherwise
    # SQLite accepts them permissively and returns arbitrary values.
    projections = tuple(group_by) if aggregates else plan.projections

    required_entities = {
        reference.entity
        for reference in QueryPlan(
            projections=projections,
            group_by=tuple(group_by),
            aggregates=tuple(aggregates),
            predicate=predicate,
            joins=(),
        ).attributes()
    }
    normalized_joins: List[JoinSpec] = []
    if len(required_entities) > 1 and join_vocabulary:
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
    expected = _expected_aggregate(text)
    if expected is not None:
        score += 8 if any(
            aggregate.function == expected for aggregate in plan.aggregates
        ) else -8
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
    for number in re.findall(r"\b\d+(?:\.\d+)?\b", lowered):
        score += 3 if any(number in value for value in predicate_values) else -3
    for match in re.finditer(
        r"\b[A-Z][a-z]+(?:[- ][A-Z][a-z]+)*\b", text
    ):
        if match.start() == 0:
            continue
        literal = match.group(0).lower()
        score += 2 if any(
            literal in value for value in predicate_values
        ) else -2
    if re.search(
        r"\b(?:each|every|group(?:ed)?\s+by|break\b.+\bdown by)\b",
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
    return score


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
        plan = _repair_plan_aggregate(plan, queries_by_id[query_id])
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
            list(dict.fromkeys(reference.attribute for reference in plan_references))
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
            for reference in plan_references
        )
        if not plan:
            for value in list_field("attribute_bindings"):
                if not isinstance(value, Mapping):
                    continue
                reference = _attribute_ref(
                    value,
                    entity_vocabulary,
                    default_entity,
                    attribute_vocabulary,
                )
                if reference is not None:
                    bindings.append(
                        (reference.entity, reference.attribute)
                    )
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
            review_prompt = (
                "Audit and correct one schema-independent analytical query plan. "
                "Return ONLY a JSON array containing one complete corrected item "
                "in the same shape as the draft. Re-read the question rather than "
                "trusting the draft.\n\n"
                "Checklist:\n"
                "1. Preserve the exact requested aggregate and its numeric measure; "
                "COUNT(*) is only entity cardinality, while COUNT(attribute) counts "
                "known values.\n"
                "2. Include exactly the dimensions requested by phrases such as "
                "'for each', 'for every', 'by', or 'group'. Do not group by a "
                "constant used only as a filter.\n"
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
            except (RuntimeError, ValueError, TypeError):
                # The independently budgeted draft remains usable and auditable
                # when the semantic reviewer emits malformed output.
                pass
            normalized_candidates = [
                replace(
                    candidate,
                    plan=_normalize_plan_with_schema(
                        candidate.plan,
                        query_text,
                        attribute_vocabulary=attribute_vocabulary,
                        join_vocabulary=join_vocabulary,
                    ),
                )
                for candidate in candidates
            ]
            draft = max(
                enumerate(normalized_candidates),
                key=lambda item: (
                    _plan_contract_score(
                        item[1].plan,
                        query_text,
                    ),
                    item[0],
                ),
            )[1]
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
    ordered = tuple(by_id[query_id] for query_id, _ in normalized)
    return WorkloadIntent(
        requirements=ordered,
        entity_frequency=dict(Counter(v for r in ordered for v in r.entities)),
        attribute_frequency=dict(Counter(v for r in ordered for v in r.attributes)),
        operator_frequency=dict(Counter(v for r in ordered for v in r.operators)),
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
