"""Deterministic SQLite compilation from the schema-independent query-plan IR."""

from __future__ import annotations

from typing import Dict, Optional, Set, Tuple

from spp.spec import (
    AggregateSpec,
    AttributeRef,
    ExpressionSpec,
    PlanExpression,
    PredicateSpec,
    QueryPlan,
    SynthesisConfig,
)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def compile_query_plan(
    plan: QueryPlan, config: SynthesisConfig
) -> Optional[str]:
    """Compile a complete plan, returning ``None`` when binding is ambiguous."""
    relations = config.schema.relations
    if not relations:
        return None
    aliases = {
        relation.name: f"t{index}" for index, relation in enumerate(relations)
    }

    def locate(reference: AttributeRef) -> Optional[Tuple[str, str]]:
        entity_matches = [
            relation
            for relation in relations
            if relation.name == reference.entity
            and reference.attribute in relation.attributes
        ]
        if len(entity_matches) == 1:
            return entity_matches[0].name, reference.attribute
        attribute_matches = [
            relation
            for relation in relations
            if reference.attribute in relation.attributes
        ]
        if len(attribute_matches) == 1:
            return attribute_matches[0].name, reference.attribute
        if config.schema.pattern == "denormalized" and (
            reference.attribute in relations[0].attributes
        ):
            return relations[0].name, reference.attribute
        return None

    locations: Dict[AttributeRef, Tuple[str, str]] = {}
    for reference in plan.attributes():
        location = locate(reference)
        if location is None:
            return None
        locations[reference] = location

    def column(reference: AttributeRef) -> str:
        table, name = locations[reference]
        return f"{_quote(aliases[table])}.{_quote(name)}"

    def expression_sql(expression: PlanExpression) -> str:
        if isinstance(expression, AttributeRef):
            return column(expression)
        if expression.kind == "column":
            assert expression.attribute is not None
            return column(expression.attribute)
        if expression.kind == "literal":
            return _literal(expression.value)
        if expression.kind == "binary":
            arguments = [
                expression_sql(argument) for argument in expression.arguments
            ]
            if expression.operator in {"and", "or"}:
                separator = f" {expression.operator.upper()} "
                return "(" + separator.join(arguments) + ")"
            if expression.operator == "between":
                return (
                    f"({arguments[0]} BETWEEN {arguments[1]} "
                    f"AND {arguments[2]})"
                )
            if expression.operator == "in":
                return f"({arguments[0]} IN ({', '.join(arguments[1:])}))"
            return (
                f"({arguments[0]} {expression.operator.upper()} "
                f"{arguments[1]})"
            )
        if expression.kind == "unary":
            argument = expression_sql(expression.arguments[0])
            if expression.operator == "not":
                return f"(NOT {argument})"
            if expression.operator == "neg":
                return f"(-{argument})"
            if expression.operator == "is_null":
                return f"({argument} IS NULL)"
            if expression.operator == "is_not_null":
                return f"({argument} IS NOT NULL)"
        if expression.kind == "cast":
            argument = expression_sql(expression.arguments[0])
            return f"CAST({argument} AS {expression.operator.upper()})"
        if expression.kind == "case":
            parts = ["CASE"]
            for condition, result in expression.branches:
                parts.extend(
                    [
                        "WHEN",
                        expression_sql(condition),
                        "THEN",
                        expression_sql(result),
                    ]
                )
            if expression.default is not None:
                parts.extend(["ELSE", expression_sql(expression.default)])
            parts.append("END")
            return " ".join(parts)
        if expression.kind == "function":
            arguments = ", ".join(
                expression_sql(argument) for argument in expression.arguments
            )
            return f"{expression.operator.upper()}({arguments})"
        raise ValueError(f"unsupported expression kind: {expression.kind}")

    def selected_sql(expression: PlanExpression) -> str:
        rendered = expression_sql(expression)
        if isinstance(expression, ExpressionSpec) and expression.alias:
            return f"{rendered} AS {_quote(expression.alias)}"
        return rendered

    # SQLite permits bare, non-grouped columns in aggregate SELECT lists and
    # returns an arbitrary row's value. Treat the IR strictly instead: aggregate
    # outputs contain only grouping dimensions plus aggregates.
    selected_refs = list(
        dict.fromkeys(
            plan.group_by
            if plan.aggregates
            else (*plan.group_by, *plan.projections)
        )
    )
    select_parts = [selected_sql(expression) for expression in selected_refs]

    def aggregate_sql(aggregate: AggregateSpec) -> str:
        argument = "*"
        if aggregate.expression is not None:
            argument = expression_sql(aggregate.expression)
        elif aggregate.attribute is not None:
            argument = column(aggregate.attribute)
        if aggregate.distinct:
            argument = f"DISTINCT {argument}"
        return f"{aggregate.function.upper()}({argument})"

    for aggregate in plan.aggregates:
        expression = aggregate_sql(aggregate)
        alias = aggregate.alias or (
            f"{aggregate.function}_{aggregate.attribute.attribute}"
            if aggregate.attribute is not None
            else "count_all"
        )
        select_parts.append(f"{expression} AS {_quote(alias)}")
    if not select_parts:
        return None

    required_tables: Set[str] = {
        table for table, _column in locations.values()
    }
    first_reference = next(iter(plan.attributes()), None)
    root = locations[first_reference][0] if first_reference else relations[0].name
    included = {root}
    from_sql = f"{_quote(root)} AS {_quote(aliases[root])}"
    join_sql = []
    pending = list(plan.joins)
    while required_tables - included:
        progress = False
        for join in list(pending):
            left_table, _ = locations[join.left]
            right_table, _ = locations[join.right]
            if left_table == right_table:
                pending.remove(join)
                progress = True
                continue
            if left_table in included and right_table not in included:
                target = right_table
            elif right_table in included and left_table not in included:
                target = left_table
            else:
                continue
            keyword = "LEFT JOIN" if join.join_type == "left" else "JOIN"
            left = join.left_expression or join.left
            right = join.right_expression or join.right
            join_sql.append(
                f"{keyword} {_quote(target)} AS {_quote(aliases[target])} "
                f"ON {expression_sql(left)} = {expression_sql(right)}"
            )
            included.add(target)
            pending.remove(join)
            progress = True
        if not progress:
            return None

    def predicate_sql(predicate: PredicateSpec) -> str:
        if predicate.kind in {"and", "or"}:
            operator = f" {predicate.kind.upper()} "
            return "(" + operator.join(
                predicate_sql(child) for child in predicate.children
            ) + ")"
        assert predicate.attribute is not None
        target = column(predicate.attribute)
        if predicate.operator == "is_null":
            return f"{target} IS NULL"
        if predicate.operator == "is_not_null":
            return f"{target} IS NOT NULL"
        if predicate.operator == "contains":
            return f"{target} LIKE {_literal('%' + str(predicate.value) + '%')}"
        return f"{target} {predicate.operator} {_literal(predicate.value)}"

    sql = "SELECT " + ", ".join(select_parts)
    sql += "\nFROM " + from_sql
    if join_sql:
        sql += "\n" + "\n".join(join_sql)
    if plan.predicate is not None:
        sql += "\nWHERE " + predicate_sql(plan.predicate)
    if plan.group_by:
        sql += "\nGROUP BY " + ", ".join(
            expression_sql(expression) for expression in plan.group_by
        )
    if plan.having:
        sql += "\nHAVING " + " AND ".join(
            f"{aggregate_sql(condition.aggregate)} "
            f"{condition.operator} {_literal(condition.value)}"
            for condition in plan.having
        )
    return sql
