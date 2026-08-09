"""Deterministic validation of compiled SQL against a typed query plan."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from spp.query_plan_compiler import compile_query_plan
from spp.spec import (
    AttributeRef,
    ExpressionSpec,
    PredicateSpec,
    QueryRequirement,
    SynthesisConfig,
)


PhysicalColumn = Tuple[str, str]


@dataclass(frozen=True)
class SQLValidationResult:
    errors: Tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors

    def require_valid(self) -> None:
        if self.errors:
            raise ValueError("SQL plan validation failed: " + "; ".join(self.errors))


def _readonly_error(sql: str) -> Optional[str]:
    normalized = sql.strip().rstrip(";").strip()
    first = normalized.split(None, 1)[0].lower() if normalized else ""
    if first not in {"select", "with"}:
        return "query must begin with SELECT or WITH"
    forbidden = (
        " insert ", " update ", " delete ", " drop ", " alter ", " create ",
        " attach ", " detach ", " pragma ", " vacuum ",
    )
    if any(token in f" {normalized.lower()} " for token in forbidden):
        return "query contains a forbidden mutating statement"
    return None


def _live_schema(database_path: Path) -> Dict[str, set[str]]:
    uri = f"file:{Path(database_path).resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
            )
        ]
        schema: Dict[str, set[str]] = {}
        for table in tables:
            quoted = table.replace('"', '""')
            schema[table.lower()] = {
                str(row[1]).lower()
                for row in connection.execute(
                    f'PRAGMA table_info("{quoted}")'
                )
            }
    return schema


def _select(expression: exp.Expression) -> Optional[exp.Select]:
    if isinstance(expression, exp.Select):
        return expression
    return expression.find(exp.Select)


def _has_ancestor(
    expression: exp.Expression,
    kinds: type[exp.Expression] | tuple[type[exp.Expression], ...],
    *,
    stop: Optional[exp.Expression] = None,
) -> bool:
    parent = expression.parent
    while parent is not None and parent is not stop:
        if isinstance(parent, kinds):
            return True
        parent = parent.parent
    return False


def _literal_value(expression: exp.Expression) -> object:
    if isinstance(expression, exp.Null):
        return None
    if isinstance(expression, exp.Boolean):
        return bool(expression.this)
    if isinstance(expression, exp.Literal):
        if expression.is_string:
            return str(expression.this)
        rendered = str(expression.this)
        try:
            number = float(rendered)
            return int(number) if number.is_integer() else number
        except ValueError:
            return rendered
    return expression.sql(dialect="sqlite")


def _hashable(value: object) -> object:
    try:
        hash(value)
        return value
    except TypeError:
        return json.dumps(value, sort_keys=True, default=str)


def _predicate_leaves(predicate: Optional[PredicateSpec]) -> Iterable[PredicateSpec]:
    if predicate is None:
        return ()
    if predicate.kind in {"and", "or"}:
        return tuple(
            leaf
            for child in predicate.children
            for leaf in _predicate_leaves(child)
        )
    return (predicate,)


def validate_sql(
    requirement: QueryRequirement,
    config: SynthesisConfig,
    database_path: Path,
    sql: str,
) -> SQLValidationResult:
    """Validate SQL syntax, live bindings, and the complete typed-plan contract."""
    errors: list[str] = []
    readonly_error = _readonly_error(sql)
    if readonly_error:
        return SQLValidationResult((readonly_error,))
    try:
        expression = parse_one(sql, read="sqlite")
    except ParseError as exc:
        return SQLValidationResult((f"SQL parse error: {exc}",))
    select = _select(expression)
    if select is None:
        return SQLValidationResult(("query has no SELECT expression",))

    try:
        live_schema = _live_schema(database_path)
    except sqlite3.Error as exc:
        return SQLValidationResult((f"database introspection failed: {exc}",))

    cte_names = {
        cte.alias_or_name.lower() for cte in expression.find_all(exp.CTE)
    }
    aliases: Dict[str, str] = {}
    referenced_tables: set[str] = set()
    for table in select.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_names:
            continue
        if name not in live_schema:
            errors.append(f"unknown table {table.name}")
            continue
        referenced_tables.add(name)
        aliases[table.alias_or_name.lower()] = name
        aliases[name] = name

    select_aliases = {
        item.alias.lower()
        for item in select.expressions
        if item.alias
    }

    def resolve_column(column: exp.Column) -> Optional[PhysicalColumn]:
        name = column.name.lower()
        if column.table:
            table = aliases.get(column.table.lower())
            if table is None:
                errors.append(f"unknown table or alias {column.table}")
                return None
            if name not in live_schema.get(table, set()):
                errors.append(f"unknown column {column.sql()}")
                return None
            return table, name
        matches = [
            table
            for table in referenced_tables
            if name in live_schema.get(table, set())
        ]
        if len(matches) == 1:
            return matches[0], name
        if not matches and name in select_aliases:
            return None
        if not matches:
            errors.append(f"unknown column {column.name}")
        else:
            errors.append(f"ambiguous column {column.name}")
        return None

    resolved: Dict[int, PhysicalColumn] = {}
    for column in select.find_all(exp.Column):
        location = resolve_column(column)
        if location is not None:
            resolved[id(column)] = location

    uri = f"file:{Path(database_path).resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
    except sqlite3.Error as exc:
        errors.append(f"SQLite rejected query: {exc}")

    plan = requirement.plan
    if plan is None:
        return SQLValidationResult(tuple(dict.fromkeys(errors)))

    # SQL-contract input is itself authoritative. Accept only an AST-identical
    # copy after the read-only, live-binding, and SQLite checks above. Likewise,
    # the deterministic expression-aware compiler is trusted only when the
    # candidate is structurally identical to its output. Non-equivalent rewrites
    # continue through the detailed plan validator below.
    authoritative = str(requirement.text or "").strip().rstrip(";")
    if authoritative and _readonly_error(authoritative) is None:
        try:
            if expression == parse_one(authoritative, read="sqlite"):
                return SQLValidationResult(tuple(dict.fromkeys(errors)))
        except ParseError:
            pass
    deterministic = compile_query_plan(plan, config)
    if deterministic:
        try:
            if expression == parse_one(deterministic, read="sqlite"):
                return SQLValidationResult(tuple(dict.fromkeys(errors)))
        except ParseError:
            pass
    has_derived_expressions = (
        any(
            isinstance(item, ExpressionSpec)
            for item in (*plan.projections, *plan.group_by)
        )
        or any(item.expression is not None for item in plan.aggregates)
        or any(
            item.aggregate.expression is not None for item in plan.having
        )
        or any(
            item.left_expression is not None
            or item.right_expression is not None
            for item in plan.joins
        )
    )
    if has_derived_expressions:
        errors.append(
            "candidate SQL expression tree does not match typed query plan"
        )
        return SQLValidationResult(tuple(dict.fromkeys(errors)))

    relation_columns = {
        relation.name.lower(): {
            attribute.lower() for attribute in relation.attributes
        }
        & live_schema.get(relation.name.lower(), set())
        for relation in config.schema.relations
        if relation.name.lower() in live_schema
    }

    def bind(reference: AttributeRef) -> Optional[PhysicalColumn]:
        entity = reference.entity.lower()
        attribute = reference.attribute.lower()
        if attribute in relation_columns.get(entity, set()):
            return entity, attribute
        matches = [
            (table, attribute)
            for table, columns in relation_columns.items()
            if attribute in columns
        ]
        if len(matches) == 1:
            return matches[0]
        if config.schema.pattern == "denormalized" and relation_columns:
            first = next(iter(relation_columns))
            if attribute in relation_columns[first]:
                return first, attribute
        errors.append(
            f"plan attribute is not uniquely materialized: "
            f"{reference.entity}.{reference.attribute}"
        )
        return None

    bound = {
        reference: bind(reference)
        for reference in plan.attributes()
    }
    expected_tables = {
        location[0] for location in bound.values() if location is not None
    }
    if expected_tables:
        for table in sorted(expected_tables - referenced_tables):
            errors.append(f"missing planned table {table}")
        for table in sorted(referenced_tables - expected_tables):
            errors.append(f"unexpected table {table}")

    equivalent: Dict[PhysicalColumn, set[PhysicalColumn]] = {}
    for location in (value for value in bound.values() if value is not None):
        equivalent.setdefault(location, {location})
    for join in plan.joins:
        left, right = bound.get(join.left), bound.get(join.right)
        if left is None or right is None or join.join_type != "inner":
            continue
        merged = equivalent.get(left, {left}) | equivalent.get(right, {right})
        for location in merged:
            equivalent[location] = merged

    def same(
        actual: Optional[PhysicalColumn],
        expected: Optional[PhysicalColumn],
    ) -> bool:
        if actual is None or expected is None:
            return False
        return actual in equivalent.get(expected, {expected})

    aggregates = [
        aggregate
        for item in select.expressions
        for aggregate in item.find_all(exp.AggFunc)
    ]
    if len(aggregates) != len(plan.aggregates):
        errors.append(
            f"expected {len(plan.aggregates)} aggregate(s), found {len(aggregates)}"
        )
    for index, expected in enumerate(plan.aggregates):
        if index >= len(aggregates):
            break
        actual = aggregates[index]
        function = actual.key.lower()
        if function != expected.function:
            errors.append(
                f"aggregate {index + 1} must be {expected.function.upper()}, "
                f"found {function.upper()}"
            )
        argument = actual.this
        actual_distinct = isinstance(argument, exp.Distinct)
        if isinstance(argument, exp.Distinct):
            argument = argument.expressions[0] if argument.expressions else argument
        if actual_distinct != expected.distinct:
            errors.append(
                f"aggregate {index + 1} DISTINCT modifier does not match plan"
            )
        if isinstance(argument, exp.Null):
            errors.append(f"{function.upper()}(NULL) is not a valid aggregate target")
        if expected.attribute is None:
            if expected.function == "count" and not isinstance(argument, exp.Star):
                errors.append("COUNT aggregate must target *")
        elif not (
            isinstance(argument, exp.Column)
            and same(resolved.get(id(argument)), bound.get(expected.attribute))
        ):
            errors.append(
                "aggregate target must be "
                f"{expected.attribute.entity}.{expected.attribute.attribute}"
            )

    expected_selected_refs = (
        plan.group_by
        if plan.aggregates
        else tuple(dict.fromkeys((*plan.group_by, *plan.projections)))
    )
    actual_bare: list[PhysicalColumn] = []
    for item in select.expressions:
        target = item.this if isinstance(item, exp.Alias) else item
        if target.find(exp.AggFunc):
            continue
        if isinstance(target, exp.Column):
            location = resolved.get(id(target))
            if location is not None:
                actual_bare.append(location)
        else:
            errors.append(f"unexpected selected expression {target.sql()}")
    unmatched_bare = list(actual_bare)
    for reference in expected_selected_refs:
        expected = bound.get(reference)
        match_index = next(
            (
                index
                for index, actual in enumerate(unmatched_bare)
                if same(actual, expected)
            ),
            None,
        )
        if match_index is None:
            errors.append(
                f"missing selected column {reference.entity}.{reference.attribute}"
            )
        else:
            unmatched_bare.pop(match_index)
    for table, column in unmatched_bare:
        errors.append(f"unexpected selected bare column {table}.{column}")

    group = select.args.get("group")
    actual_groups = [
        resolved[id(column)]
        for column in (group.find_all(exp.Column) if group is not None else ())
        if id(column) in resolved
    ]
    unmatched_groups = list(actual_groups)
    for reference in plan.group_by:
        expected = bound.get(reference)
        match_index = next(
            (
                index
                for index, actual in enumerate(unmatched_groups)
                if same(actual, expected)
            ),
            None,
        )
        if match_index is None:
            errors.append(
                f"missing GROUP BY dimension "
                f"{reference.entity}.{reference.attribute}"
            )
        else:
            unmatched_groups.pop(match_index)
    for table, column in unmatched_groups:
        errors.append(f"unexpected GROUP BY column {table}.{column}")

    expected_having: Counter[
        tuple[str, Optional[PhysicalColumn], bool, str, object]
    ] = Counter(
        (
            condition.aggregate.function,
            (
                bound.get(condition.aggregate.attribute)
                if condition.aggregate.attribute is not None
                else None
            ),
            condition.aggregate.distinct,
            condition.operator,
            _hashable(condition.value),
        )
        for condition in plan.having
    )
    actual_having: Counter[
        tuple[str, Optional[PhysicalColumn], bool, str, object]
    ] = Counter()
    having_clause = select.args.get("having")
    comparison_operators = {
        exp.EQ: "=",
        exp.NEQ: "!=",
        exp.GT: ">",
        exp.GTE: ">=",
        exp.LT: "<",
        exp.LTE: "<=",
    }
    if having_clause is not None:
        for comparison in having_clause.find_all(
            tuple(comparison_operators)
        ):
            aggregate = comparison.this
            if not isinstance(aggregate, exp.AggFunc):
                errors.append(
                    f"unsupported HAVING expression {comparison.sql()}"
                )
                continue
            argument = aggregate.this
            distinct = isinstance(argument, exp.Distinct)
            if distinct:
                argument = (
                    argument.expressions[0]
                    if argument.expressions
                    else argument
                )
            location = (
                resolved.get(id(argument))
                if isinstance(argument, exp.Column)
                else None
            )
            actual_having[
                (
                    aggregate.key.lower(),
                    location,
                    distinct,
                    comparison_operators[type(comparison)],
                    _hashable(_literal_value(comparison.expression)),
                )
            ] += 1
    if actual_having != expected_having:
        for condition, count in (expected_having - actual_having).items():
            errors.append(f"missing HAVING condition {condition!r}")
        for condition, count in (actual_having - expected_having).items():
            errors.append(f"unexpected HAVING condition {condition!r}")

    expected_edges: Counter[
        tuple[frozenset[PhysicalColumn], str]
    ] = Counter()
    for join in plan.joins:
        left, right = bound.get(join.left), bound.get(join.right)
        if left is not None and right is not None and left[0] != right[0]:
            expected_edges[(frozenset((left, right)), join.join_type)] += 1
    actual_edges: Counter[
        tuple[frozenset[PhysicalColumn], str]
    ] = Counter()
    for join in select.args.get("joins") or ():
        on = join.args.get("on")
        join_type = (
            "left"
            if str(join.args.get("side", "")).lower() == "left"
            else "inner"
        )
        for equality in on.find_all(exp.EQ) if on is not None else ():
            if not isinstance(equality.this, exp.Column) or not isinstance(
                equality.expression, exp.Column
            ):
                continue
            left = resolved.get(id(equality.this))
            right = resolved.get(id(equality.expression))
            if left is not None and right is not None and left[0] != right[0]:
                actual_edges[(frozenset((left, right)), join_type)] += 1
    for (edge, join_type), count in expected_edges.items():
        if actual_edges[(edge, join_type)] < count:
            rendered = "=".join(
                f"{table}.{column}" for table, column in sorted(edge)
            )
            errors.append(
                f"missing declared join edge {rendered} ({join_type})"
            )
    for (edge, join_type), count in actual_edges.items():
        if expected_edges[(edge, join_type)] < count:
            rendered = "=".join(
                f"{table}.{column}" for table, column in sorted(edge)
            )
            errors.append(
                f"undeclared or wrong join edge {rendered} ({join_type})"
            )

    expected_predicates: Counter[
        tuple[Optional[PhysicalColumn], str, object]
    ] = Counter(
        (
            bound.get(leaf.attribute),
            leaf.operator,
            _hashable(
                f"%{leaf.value}%"
                if leaf.operator == "contains"
                else leaf.value
            ),
        )
        for leaf in _predicate_leaves(plan.predicate)
        if leaf.attribute is not None
    )
    actual_predicates: Counter[
        tuple[Optional[PhysicalColumn], str, object]
    ] = Counter()
    where = select.args.get("where")
    if where is not None:
        comparison_types = (
            exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
            exp.Like, exp.Is,
        )
        operator_by_type = {
            exp.EQ: "=",
            exp.NEQ: "!=",
            exp.GT: ">",
            exp.GTE: ">=",
            exp.LT: "<",
            exp.LTE: "<=",
            exp.Like: "contains",
        }
        for comparison in where.find_all(comparison_types):
            if _has_ancestor(comparison, comparison_types, stop=where):
                continue
            left, right = comparison.this, comparison.expression
            if isinstance(left, exp.Column):
                if isinstance(comparison, exp.Is):
                    operator = (
                        "is_not_null"
                        if isinstance(comparison.parent, exp.Not)
                        else "is_null"
                    )
                else:
                    operator = operator_by_type[type(comparison)]
                actual_predicates[
                    (
                        resolved.get(id(left)),
                        operator,
                        _hashable(_literal_value(right)),
                    )
                ] += 1
    if actual_predicates != expected_predicates:
        for (location, operator, value), count in (
            expected_predicates - actual_predicates
        ).items():
            rendered = (
                f"{location[0]}.{location[1]}" if location is not None else "unknown"
            )
            errors.append(
                f"missing predicate {rendered} {operator} {value!r}"
            )
        for (location, operator, value), count in (
            actual_predicates - expected_predicates
        ).items():
            rendered = (
                f"{location[0]}.{location[1]}" if location is not None else "unknown"
            )
            errors.append(
                f"unexpected predicate {rendered} {operator} {value!r}"
            )

    def normalized_boolean(kind: str, children: Iterable[object]) -> object:
        flattened: list[object] = []
        for child in children:
            if (
                isinstance(child, tuple)
                and len(child) == 2
                and child[0] == kind
                and isinstance(child[1], tuple)
            ):
                flattened.extend(child[1])
            else:
                flattened.append(child)
        return kind, tuple(sorted(flattened, key=repr))

    def expected_predicate_signature(
        predicate: Optional[PredicateSpec],
    ) -> object:
        if predicate is None:
            return None
        if predicate.kind in {"and", "or"}:
            return normalized_boolean(
                predicate.kind,
                (
                    expected_predicate_signature(child)
                    for child in predicate.children
                ),
            )
        assert predicate.attribute is not None
        value = (
            f"%{predicate.value}%"
            if predicate.operator == "contains"
            else predicate.value
        )
        return (
            "leaf",
            bound.get(predicate.attribute),
            predicate.operator,
            _hashable(value),
        )

    def actual_predicate_signature(node: Optional[exp.Expression]) -> object:
        if node is None:
            return None
        if isinstance(node, exp.Paren):
            return actual_predicate_signature(node.this)
        if isinstance(node, (exp.And, exp.Or)):
            return normalized_boolean(
                "and" if isinstance(node, exp.And) else "or",
                (
                    actual_predicate_signature(node.this),
                    actual_predicate_signature(node.expression),
                ),
            )
        if isinstance(node, exp.Not) and isinstance(node.this, exp.Is):
            comparison = node.this
            if isinstance(comparison.this, exp.Column):
                return (
                    "leaf",
                    resolved.get(id(comparison.this)),
                    "is_not_null",
                    None,
                )
        for comparison_type, operator in operator_by_type.items():
            if isinstance(node, comparison_type) and isinstance(
                node.this, exp.Column
            ):
                return (
                    "leaf",
                    resolved.get(id(node.this)),
                    operator,
                    _hashable(_literal_value(node.expression)),
                )
        if isinstance(node, exp.Is) and isinstance(node.this, exp.Column):
            return (
                "leaf",
                resolved.get(id(node.this)),
                "is_null",
                None,
            )
        return ("unsupported", node.sql(dialect="sqlite"))

    expected_signature = expected_predicate_signature(plan.predicate)
    actual_signature = actual_predicate_signature(
        where.this if where is not None else None
    )
    if actual_signature != expected_signature:
        errors.append("predicate boolean structure does not match plan")

    return SQLValidationResult(tuple(dict.fromkeys(errors)))


def require_valid_sql(
    requirement: QueryRequirement,
    config: SynthesisConfig,
    database_path: Path,
    sql: str,
) -> None:
    validate_sql(requirement, config, database_path, sql).require_valid()
