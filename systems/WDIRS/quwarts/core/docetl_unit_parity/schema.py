"""Compile one query-local extraction schema from the original SQL AST."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from sqlglot import exp

from quwarts.core.schema_columns import referenced_columns
from quwarts.core.signature import resolve_attribute, select_aliases, table_aliases
from quwarts.core.workload import _default_entity, parse_sql

_NUMERIC = (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between, exp.Sum, exp.Avg)
_SEMANTIC_TOKENS = {"yes", "no", "true", "false", "y", "n"}


@dataclass
class FieldSpec:
    name: str
    dtype: str
    sql_type: str
    description: str
    literals: list[str] = field(default_factory=list)
    semantic: bool = False
    usages: list[str] = field(default_factory=list)


@dataclass
class QuerySchema:
    query_id: str
    sql: str
    fields: list[FieldSpec]

    @property
    def names(self) -> list[str]:
        return [item.name for item in self.fields]

    @property
    def dtypes(self) -> dict[str, str]:
        return {item.name: item.dtype for item in self.fields}

    @property
    def sql_types(self) -> dict[str, str]:
        return {item.name: item.sql_type for item in self.fields}

    @property
    def descriptions(self) -> dict[str, str]:
        return {item.name: item.description for item in self.fields}

    @property
    def semantic_fields(self) -> set[str]:
        return {item.name for item in self.fields if item.semantic}

    def as_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "fields": [
                {
                    "name": item.name,
                    "dtype": item.dtype,
                    "sql_type": item.sql_type,
                    "description": item.description,
                    "literals": item.literals,
                    "semantic": item.semantic,
                    "usages": item.usages,
                }
                for item in self.fields
            ],
        }


def _bare(name: str) -> str:
    return name.split(".")[-1].lower()


def _literals(node: exp.Expression) -> list[str]:
    out = []
    for literal in node.find_all(exp.Literal):
        text = str(literal.this) if literal.this is not None else ""
        if text != "":
            out.append(text)
    return out


def _column_name(column: exp.Column, aliases: dict[str, str], default: str | None) -> str | None:
    resolved = resolve_attribute(column, aliases, default)
    if resolved is None:
        return None
    return resolved[2]


def compile_query_schema(query_id: str, sql: str) -> QuerySchema:
    tree = parse_sql(sql)
    aliases = table_aliases(tree)
    default = _default_entity(tree)
    skip = select_aliases(tree)
    physical = {item.column.lower(): item for item in referenced_columns({query_id: sql})}
    usages: dict[str, list[str]] = {name: [] for name in physical}
    literals: dict[str, list[str]] = {name: [] for name in physical}
    semantic: dict[str, bool] = {name: False for name in physical}

    def mark(column: exp.Column | None, label: str, extra: list[str] | None = None) -> None:
        if column is None:
            return
        name = _column_name(column, aliases, default)
        if name is None or name in skip or name == "rowid":
            return
        key = name.lower()
        if key not in usages:
            usages[key] = []
            literals[key] = []
            semantic[key] = False
        if label not in usages[key]:
            usages[key].append(label)
        if extra:
            literals[key].extend(extra)

    for predicate in tree.find_all(exp.Where):
        for column in predicate.find_all(exp.Column):
            mark(column, "WHERE", _literals(predicate))
    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        if on is not None:
            for column in on.find_all(exp.Column):
                mark(column, "JOIN ON", _literals(on))
    for node in tree.find_all(exp.Case):
        for column in node.find_all(exp.Column):
            mark(column, "CASE", _literals(node))
    group = tree.args.get("group")
    if group is not None:
        for column in group.find_all(exp.Column):
            mark(column, "GROUP BY")
    having = tree.args.get("having")
    if having is not None:
        for column in having.find_all(exp.Column):
            mark(column, "HAVING", _literals(having))
    for agg in tree.find_all((exp.Sum, exp.Avg, exp.Count, exp.Max, exp.Min)):
        for column in agg.find_all(exp.Column):
            mark(column, f"aggregate {agg.key.upper()}")
    for proj in tree.expressions:
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        if expr.find((exp.Sum, exp.Avg, exp.Count, exp.Max, exp.Min)):
            continue
        for column in expr.find_all(exp.Column):
            mark(column, "projected non-aggregate")

    like_types = tuple(
        cls
        for name in ("Like", "ILike", "ILIKE")
        if (cls := getattr(exp, name, None)) is not None
    )
    for node in tree.find_all((exp.In, exp.EQ, exp.NEQ) + like_types):
        columns = list(node.find_all(exp.Column))
        if not columns:
            continue
        name = _column_name(columns[0], aliases, default)
        if name is None:
            continue
        key = name.lower()
        values = _literals(node)
        if key in literals:
            literals[key].extend(values)
        if isinstance(node, exp.In) and values and all(str(item).strip().lower() in _SEMANTIC_TOKENS or len(str(item)) <= 8 for item in values):
            if key in semantic:
                semantic[key] = True

    fields: list[FieldSpec] = []
    missing = sorted(set(physical) - set(usages))
    for name in missing:
        usages[name] = ["referenced"]
        literals.setdefault(name, [])
        semantic.setdefault(name, False)
    for name in sorted(set(usages) | set(physical)):
        info = physical.get(name)
        numeric = bool(info and info.sql_type == "REAL")
        uses = usages.get(name) or ["referenced"]
        lits = list(dict.fromkeys(literals.get(name) or []))
        desc_parts = [", ".join(uses)]
        if lits:
            desc_parts.append("predicate literals: " + ", ".join(lits[:8]))
        fields.append(
            FieldSpec(
                name=name,
                dtype="numeric" if numeric else "string",
                sql_type="REAL" if numeric else "TEXT",
                description="; ".join(desc_parts),
                literals=lits,
                semantic=bool(semantic.get(name)),
                usages=uses,
            )
        )
    if not fields:
        raise SystemExit(f"{query_id}: compiled empty schema")
    required = {item.column.lower() for item in referenced_columns({query_id: sql})}
    have = {item.name.lower() for item in fields}
    if required - have:
        raise SystemExit(f"{query_id}: schema missing {sorted(required - have)}")
    return QuerySchema(query_id=query_id, sql=sql, fields=fields)


def schema_hash(schemas: dict[str, QuerySchema]) -> str:
    payload = {qid: schemas[qid].as_dict() for qid in sorted(schemas)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
