"""Zero-token workload features per (table, attribute)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

from quwarts.core.router.registry import CorpusSpec
from quwarts.core.workload import analyze_workload

SENSITIVE_ROLES = {"key", "join", "group", "predicate", "agg_additive", "agg_distinct", "agg_extremal"}


@dataclass
class AttributeUse:
    table: str
    name: str
    dtype: str
    roles: list[str]
    query_ids: list[str]
    description: str = ""
    value_type: str = ""
    closed_label: bool = False
    literals: list[str] = field(default_factory=list)

    @property
    def qualified(self) -> str:
        return f"{self.table}.{self.name}"

    @property
    def n_queries(self) -> int:
        return len(self.query_ids)

    @property
    def sensitive(self) -> bool:
        return bool(SENSITIVE_ROLES & set(self.roles))

    @property
    def numeric(self) -> bool:
        return self.dtype == "numeric" or self.value_type in {"int", "float", "number"}

    def to_json(self) -> dict[str, Any]:
        row = asdict(self)
        row.update(qualified=self.qualified, n_queries=self.n_queries, sensitive=self.sensitive, numeric=self.numeric)
        return row


def alias_map(tree: exp.Expression) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for table in tree.find_all(exp.Table):
        aliases[table.name] = table.name
        if table.alias:
            aliases[table.alias] = table.name
    return aliases


def resolve_column(column: exp.Column, aliases: dict[str, str], table_attrs: dict[str, set[str]]) -> str | None:
    """Base table of a column reference, or None if it is not a physical attribute."""

    name = column.name
    if column.table:
        table = aliases.get(column.table)
        return table if table else None
    tables = sorted(set(aliases.values()))
    owners = [table for table in tables if name in table_attrs.get(table, set())]
    if len(owners) == 1:
        return owners[0]
    if len(tables) == 1:
        return tables[0]
    return None


def _string_literals(node: exp.Expression) -> list[str]:
    out: list[str] = []
    for literal in node.find_all(exp.Literal):
        if literal.is_string:
            value = literal.this.strip().strip("%").replace("%", " ").strip()
            if value:
                out.append(value)
    return out


def comparison_literals(sql: str, table_attrs: dict[str, set[str]]) -> dict[str, set[str]]:
    """String literals compared against each qualified attribute."""

    tree = sqlglot.parse_one(sql, read="sqlite")
    aliases = alias_map(tree)
    found: dict[str, set[str]] = {}
    kinds = (exp.EQ, exp.NEQ, exp.In, exp.Like, exp.ILike)
    for node in tree.find_all(*kinds):
        columns = list(node.find_all(exp.Column))
        literals = _string_literals(node)
        if len(columns) != 1 or not literals:
            continue
        table = resolve_column(columns[0], aliases, table_attrs)
        if table is None:
            continue
        found.setdefault(f"{table}.{columns[0].name}", set()).update(literals)
    return found


def sql_table_attributes(queries: dict[str, str], tables: list[str]) -> dict[str, set[str]]:
    """Physical attributes per table, from the SQL workload alone.

    Qualified references (``t.col`` via aliases) and columns of single-table statements
    resolve directly. An unqualified column in a multi-table statement goes to the one
    table the workload elsewhere qualifies it with; if none or several, it is left out.
    SELECT aliases are never attributes.
    """

    out: dict[str, set[str]] = {t: set() for t in tables}
    for sql in queries.values():
        tree = sqlglot.parse_one(sql, read="sqlite")
        aliases = alias_map(tree)
        names = set(aliases.values())
        output_aliases = {n.alias for n in tree.find_all(exp.Alias) if n.alias}
        for column in tree.find_all(exp.Column):
            if not column.name or (not column.table and column.name in output_aliases):
                continue
            if column.table:
                table = aliases.get(column.table)
                if table:
                    out.setdefault(table, set()).add(column.name)
            elif len(names) == 1:
                out.setdefault(next(iter(names)), set()).add(column.name)
            # An unqualified column in a multi-table statement is recorded only through
            # its qualified uses elsewhere in the workload.
    return out


def table_attribute_names(spec: CorpusSpec, queries: dict[str, str] | None = None) -> dict[str, set[str]]:
    queries = queries if queries is not None else spec.queries()
    return sql_table_attributes(queries, [t.sql_name for t in spec.tables])


def workload_features(spec: CorpusSpec, queries: dict[str, str] | None = None) -> dict[str, Any]:
    queries = queries if queries is not None else spec.queries()
    _logical, workload = analyze_workload(queries)
    template_statements = {template.id: list(template.statement_ids) for template in workload.templates}
    table_attrs = table_attribute_names(spec, queries)

    literals: dict[str, set[str]] = {}
    table_queries: dict[str, set[str]] = {table.sql_name: set() for table in spec.tables}
    for query_id, sql in queries.items():
        tree = sqlglot.parse_one(sql, read="sqlite")
        for table in set(alias_map(tree).values()):
            table_queries.setdefault(table, set()).add(query_id)
        for key, values in comparison_literals(sql, table_attrs).items():
            literals.setdefault(key, set()).update(values)

    attributes: dict[str, AttributeUse] = {}
    for qualified, requirement in workload.requirements.items():
        if "." not in qualified:
            continue
        table, name = qualified.split(".", 1)
        query_ids = sorted({sid for tid in requirement.templates for sid in template_statements.get(tid, [])})
        attributes[qualified] = AttributeUse(
            table=table,
            name=name,
            dtype=str(requirement.dtype),
            roles=sorted(role.value for role in requirement.roles),
            query_ids=query_ids,
            # SQL-only: no benchmark description, type or label flag (RULES.md: T, Q, theta).
            description="",
            value_type="float" if str(requirement.dtype) == "numeric" else "",
            closed_label=False,
            literals=sorted(literals.get(qualified, set())),
        )

    tables = {}
    for table, ids in table_queries.items():
        attrs = [use for use in attributes.values() if use.table == table]
        uses = sum(use.n_queries for use in attrs)
        tables[table] = {
            "queries": sorted(ids),
            "n_queries": len(ids),
            "n_attributes": len(attrs),
            # Mean number of queries that need each attribute: cross-query redundancy.
            "attribute_reuse": (uses / len(attrs)) if attrs else 0.0,
        }
    return {
        "n_queries": len(queries),
        "binding_failures": list(workload.binding_failures),
        "tables": tables,
        "attributes": attributes,
    }


def usage_phrase(use: "AttributeUse") -> str:
    """How the whole reference workload uses an attribute, without any single query's SQL.

    This is what the workload knows about a column that a query-independent read lacks:
    whether it is aggregated as a number, grouped by value, or compared with specific values.
    """

    roles = set(use.roles)
    parts = []
    # A non-numeric column inside an aggregate is aggregated through a CASE/predicate
    # (e.g. SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END)): not a numeric use.
    if roles & {"agg_additive", "agg_extremal"} and use.numeric:
        parts.append("aggregated as a number (sum, average, max or min)")
    if "agg_distinct" in roles:
        parts.append("counted by distinct value")
    if "group" in roles:
        parts.append("grouped by its value")
    if "predicate" in roles:
        if use.literals:
            parts.append("compared with " + ", ".join(repr(v) for v in use.literals[:12]))
        elif use.numeric:
            parts.append("compared numerically")
        else:
            parts.append("filtered on")
    if roles & {"join", "key"}:
        parts.append("used to join with another table")
    if "project" in roles and not parts:
        parts.append("reported as is")
    return "; ".join(parts)
