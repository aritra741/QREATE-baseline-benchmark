"""Ground-truth-free workload intent analysis.

Natural-language queries are converted into a schema-independent requirement
IR. SQL input remains supported for diagnostics and migration experiments.
The analyzer never reads UDA-Bench tables or attributes metadata.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
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


def _is_sql(text: str) -> bool:
    return bool(re.match(r"^\s*(select|with)\b", text, re.IGNORECASE))


def _attribute_ref(payload: object) -> Optional[AttributeRef]:
    if not isinstance(payload, Mapping):
        return None
    entity = str(payload.get("entity", "")).strip().lower()
    attribute = str(payload.get("attribute", "")).strip().lower()
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


def _predicate_spec(payload: object) -> Optional[PredicateSpec]:
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
                _predicate_spec(value)
                for value in raw_children
            )
            if child is not None
        )
        return PredicateSpec(kind=kind, children=children) if children else None
    reference = _attribute_ref(
        payload.get("attribute")
        if isinstance(payload.get("attribute"), Mapping)
        else payload
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


def _query_plan(payload: object) -> Optional[QueryPlan]:
    if not isinstance(payload, Mapping):
        return None

    def refs(name: str) -> Tuple[AttributeRef, ...]:
        values = payload.get(name, [])
        if not isinstance(values, (list, tuple)):
            return ()
        return tuple(
            reference
            for reference in (_attribute_ref(value) for value in values)
            if reference is not None
        )

    aggregates: List[AggregateSpec] = []
    values = payload.get("aggregates", [])
    if isinstance(values, (list, tuple)):
        for value in values:
            if not isinstance(value, Mapping):
                continue
            function = str(value.get("function", "")).strip().lower()
            reference = _attribute_ref(value.get("attribute"))
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
            left = _attribute_ref(value.get("left"))
            right = _attribute_ref(value.get("right"))
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
        predicate=_predicate_spec(payload.get("predicate")),
        joins=tuple(joins),
    )
    return plan if plan.attributes() or plan.aggregates else None


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
    payload: str, queries_by_id: Mapping[str, str]
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

        relationships = []
        for rel in list_field("relationships"):
            if isinstance(rel, Mapping):
                parsed = (
                    str(rel.get("left", "")).lower(),
                    str(rel.get("relation", "")).lower(),
                    str(rel.get("right", "")).lower(),
                )
                if all(parsed):
                    relationships.append(parsed)
            elif isinstance(rel, (list, tuple)) and len(rel) == 3:
                parsed = tuple(str(v).lower() for v in rel)
                if all(parsed):
                    relationships.append(parsed)
        plan = _query_plan(row.get("plan"))
        plan_references = plan.attributes() if plan else ()
        entities = list(
            dict.fromkeys(
                [
                    *(str(v).lower() for v in list_field("entities")),
                    *(reference.entity for reference in plan_references),
                ]
            )
        )
        attributes = list(
            dict.fromkeys(
                [
                    *(str(v).lower() for v in list_field("attributes")),
                    *(reference.attribute for reference in plan_references),
                ]
            )
        )
        bindings = [
            (str(v.get("entity", "")).lower(), str(v.get("attribute", "")).lower())
            for v in list_field("attribute_bindings")
            if isinstance(v, Mapping) and v.get("entity") and v.get("attribute")
        ]
        bindings.extend(
            (reference.entity, reference.attribute)
            for reference in plan_references
            if (reference.entity, reference.attribute) not in bindings
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
) -> WorkloadIntent:
    """Analyze SQL or NL workload without reading any ground-truth artifact."""
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
        nl_requirements = []
        items = list(nl_queries.items())
        batch_size = 4
        for start in range(0, len(items), batch_size):
            batch = dict(items[start : start + batch_size])
            prompt = instructions + json.dumps(
                [
                    {"query_id": query_id, "query": text}
                    for query_id, text in batch.items()
                ],
                indent=2,
            )
            response = llm_client.generate(
                prompt, max_tokens=4096, temperature=0.0
            )
            nl_requirements.extend(_parse_llm_payload(response, batch))
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


def make_budgeted_intent_analyzer(llm_client: Any):
    """Adapt a WDIRS-compatible client to the system's analyzer callback."""

    def analyzer(
        queries: Sequence[Mapping[str, Any] | str],
        ledger: GlobalBudgetLedger,
    ) -> WorkloadIntent:
        budgeted = BudgetedLLMClient(
            llm_client, ledger, default_stage="workload_analysis"
        )
        return analyze_workload(queries, llm_client=budgeted)

    return analyzer
