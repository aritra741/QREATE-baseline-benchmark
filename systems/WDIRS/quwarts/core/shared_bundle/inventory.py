"""Compile the union of base attributes referenced by a SQL workload."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlglot import exp

from quwarts.core.schema_columns import referenced_columns
from quwarts.core.signature import resolve_attribute, select_aliases, table_aliases
from quwarts.core.workload import _default_entity, parse_sql

_ROLE_WHERE = "WHERE"
_ROLE_JOIN = "JOIN"
_ROLE_CASE = "CASE"
_ROLE_GROUP = "GROUP BY"
_ROLE_HAVING = "HAVING"
_ROLE_AGG = "aggregate input"
_ROLE_PROJ = "projection"

_CMP = (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between)
_EQ = (exp.EQ, exp.NEQ, exp.In)
_LIKE = tuple(cls for name in ("Like", "ILike", "ILIKE") if (cls := getattr(exp, name, None)) is not None)
_AGG = (exp.Sum, exp.Avg, exp.Count, exp.Max, exp.Min)
_FILTER_ROLES = {_ROLE_WHERE, _ROLE_JOIN, _ROLE_HAVING}
_EXPR_ROLES = {_ROLE_WHERE, _ROLE_JOIN, _ROLE_CASE, _ROLE_GROUP, _ROLE_HAVING, _ROLE_AGG, _ROLE_PROJ}


@dataclass
class AttributeRecord:
    name: str
    sql_type: str
    occurrence_count: int
    queries: list[str]
    roles: dict[str, int]
    predicate_literals: list[str]
    numeric_comparisons: list[dict[str, str]]
    categorical_literals: list[str]
    cooccurring: list[str]
    expressions: list[str]
    plumbing_null_count: int = 0
    expression_change_entities: int = 0

    @property
    def dtype(self) -> str:
        return "numeric" if self.sql_type == "REAL" else "string"

    @property
    def n_queries(self) -> int:
        return len(self.queries)

    @property
    def semantic(self) -> bool:
        closed = bool(self.categorical_literals) and all(
            "%" not in item and len(item) <= 24 for item in self.categorical_literals
        )
        return closed

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sql_type": self.sql_type,
            "dtype": self.dtype,
            "occurrence_count": self.occurrence_count,
            "n_queries": self.n_queries,
            "queries": list(self.queries),
            "roles": dict(self.roles),
            "predicate_literals": list(self.predicate_literals),
            "numeric_comparisons": list(self.numeric_comparisons),
            "categorical_literals": list(self.categorical_literals),
            "cooccurring": list(self.cooccurring),
            "expressions": list(self.expressions),
            "plumbing_null_count": self.plumbing_null_count,
            "expression_change_entities": self.expression_change_entities,
            "impact_unit": self.occurrence_count * self.n_queries,
        }


def _numeric_literal(text: str) -> bool:
    body = str(text).strip().replace(",", "")
    if body.startswith("-"):
        body = body[1:]
    return body.replace(".", "", 1).isdigit()


def _sql(node: exp.Expression | None) -> str:
    if node is None:
        return ""
    return node.sql(dialect="sqlite")


def _literals(node: exp.Expression | None) -> list[str]:
    if node is None:
        return []
    out: list[str] = []
    for literal in node.find_all(exp.Literal):
        text = str(literal.this) if literal.this is not None else ""
        if text != "":
            out.append(text)
    return out


def _op_name(node: exp.Expression) -> str:
    if isinstance(node, (exp.Like, exp.ILike)):
        return "LIKE"
    mapping = {
        exp.EQ: "=",
        exp.NEQ: "!=",
        exp.GT: ">",
        exp.GTE: ">=",
        exp.LT: "<",
        exp.LTE: "<=",
        exp.In: "IN",
        exp.Between: "BETWEEN",
        exp.Is: "IS",
    }
    for cls, name in mapping.items():
        if isinstance(node, cls):
            return name
    return node.key.upper()


def _ancestor(node: exp.Expression, types: tuple[type, ...]) -> exp.Expression | None:
    current = node.parent
    while current is not None:
        if isinstance(current, types):
            return current
        current = current.parent
    return None


def _roles_for(column: exp.Column) -> list[tuple[str, exp.Expression]]:
    found: list[tuple[str, exp.Expression]] = []
    if _ancestor(column, (exp.Where,)):
        pred = _ancestor(column, _EQ + _CMP + _LIKE + (exp.Is,)) or _ancestor(column, (exp.Where,))
        found.append((_ROLE_WHERE, pred or column))
    join = _ancestor(column, (exp.Join,))
    if join is not None:
        found.append((_ROLE_JOIN, join.args.get("on") or join))
    case = _ancestor(column, (exp.Case,))
    if case is not None:
        found.append((_ROLE_CASE, case))
    group = _ancestor(column, (exp.Group,))
    if group is not None:
        found.append((_ROLE_GROUP, group))
    having = _ancestor(column, (exp.Having,))
    if having is not None:
        found.append((_ROLE_HAVING, having))
    agg = _ancestor(column, _AGG)
    if agg is not None:
        found.append((_ROLE_AGG, agg))
    if not found:
        select = _ancestor(column, (exp.Select,))
        if select is not None:
            found.append((_ROLE_PROJ, column.parent if isinstance(column.parent, exp.Expression) else column))
    return found


def compile_attribute_inventory(statements: dict[str, str]) -> dict[str, AttributeRecord]:
    physical = {item.column.lower(): item for item in referenced_columns(statements)}
    occ: dict[str, int] = defaultdict(int)
    roles: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    queries: dict[str, set[str]] = defaultdict(set)
    literals: dict[str, list[str]] = defaultdict(list)
    numeric_cmp: dict[str, list[dict[str, str]]] = defaultdict(list)
    categorical: dict[str, list[str]] = defaultdict(list)
    expressions: dict[str, set[str]] = defaultdict(set)
    per_query_attrs: dict[str, set[str]] = defaultdict(set)

    for query_id, sql in statements.items():
        tree = parse_sql(sql)
        aliases = table_aliases(tree)
        default = _default_entity(tree)
        skip = select_aliases(tree)
        used: set[str] = set()
        for column in tree.find_all(exp.Column):
            resolved = resolve_attribute(column, aliases, default)
            if resolved is None:
                continue
            _qualified, _table, name = resolved
            if name in skip or name == "rowid":
                continue
            occ[name] += 1
            queries[name].add(query_id)
            used.add(name)
            for role, expr in _roles_for(column):
                roles[name][role] += 1
                text = _sql(expr)
                if text:
                    expressions[name].add(text)
        per_query_attrs[query_id] = used

        like_types = _LIKE
        for node in tree.find_all(_EQ + _CMP + like_types + (exp.Is,)):
            cols = list(node.find_all(exp.Column))
            if not cols:
                continue
            resolved = resolve_attribute(cols[0], aliases, default)
            if resolved is None:
                continue
            name = resolved[2]
            if name in skip:
                continue
            values = _literals(node)
            literals[name].extend(values)
            if isinstance(node, _CMP):
                numeric_cmp[name].append({"operator": _op_name(node), "literals": "|".join(values)})
            if isinstance(node, like_types):
                categorical[name].extend(values)
            elif isinstance(node, (exp.In, exp.EQ, exp.NEQ)) and values:
                if all(not _numeric_literal(item) for item in values):
                    categorical[name].extend(values)

    cooccur: dict[str, set[str]] = defaultdict(set)
    for attrs in per_query_attrs.values():
        for left in attrs:
            for right in attrs:
                if left != right:
                    cooccur[left].add(right)

    records: dict[str, AttributeRecord] = {}
    for name in sorted(set(physical) | set(occ)):
        info = physical.get(name)
        records[name] = AttributeRecord(
            name=name,
            sql_type="REAL" if info and info.sql_type == "REAL" else "TEXT",
            occurrence_count=int(occ.get(name) or 0),
            queries=sorted(queries.get(name) or []),
            roles={key: int(roles[name][key]) for key in sorted(roles[name])},
            predicate_literals=sorted(dict.fromkeys(literals.get(name) or [])),
            numeric_comparisons=[
                dict(item) for item in
                sorted({json.dumps(row, sort_keys=True): row for row in numeric_cmp.get(name) or []}.values(), key=lambda r: json.dumps(r, sort_keys=True))
            ],
            categorical_literals=sorted(dict.fromkeys(categorical.get(name) or [])),
            cooccurring=sorted(cooccur.get(name) or []),
            expressions=sorted(expressions.get(name) or []),
        )
    required = {item.column.lower() for item in referenced_columns(statements)}
    missing = required - set(records)
    if missing:
        raise SystemExit(f"attribute inventory missing {sorted(missing)}")
    return records


def attach_plumbing_nulls(
    records: dict[str, AttributeRecord],
    null_counts: dict[str, int],
) -> dict[str, AttributeRecord]:
    for name, record in records.items():
        n_null = int(null_counts.get(name) or 0)
        record.plumbing_null_count = n_null
        uses_expr = any(role in _EXPR_ROLES for role in record.roles)
        record.expression_change_entities = n_null if uses_expr else 0
    return records


def inventory_hash(records: dict[str, AttributeRecord]) -> str:
    payload = {name: records[name].as_dict() for name in sorted(records)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def ast_names(statements: dict[str, str]) -> set[str]:
    return {item.column.lower() for item in referenced_columns(statements)}
