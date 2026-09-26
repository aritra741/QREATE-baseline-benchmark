"""Workload needs: one (query, attribute) requirement per use of an attribute by a query.

The unit of sharing in router-v3 is a need, not an attribute. Two needs on the
same attribute can share one extracted column only if they mean the same thing
by it. The SQL role fixes what each need must know (zero tokens):

* ``value``      the query groups, projects, aggregates, joins, or compares the
                 attribute with another column: it needs the full value.
* ``predicate``  the attribute appears only inside single-attribute conditions
                 (WHERE conjuncts or CASE WHEN tests): it needs only the truth of
                 those conditions.

This gives an information order (Halevy's answering-queries-using-views applied
to extracted columns): an extraction that yields a need's full value can serve
its predicate needs, but not the other way round.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

from quwarts.core.router.registry import CorpusSpec
from quwarts.core.router.workload_features import alias_map, resolve_column, table_attribute_names

CANONICAL = "__canonical__"


@dataclass(frozen=True)
class Need:
    query_id: str
    table: str
    attribute: str
    kind: str  # "value" | "predicate"
    conditions: tuple[str, ...] = ()
    weight: float = 1.0

    @property
    def qualified(self) -> str:
        return f"{self.table}.{self.attribute}"

    @property
    def key(self) -> str:
        return f"{self.query_id}|{self.qualified}"

    def to_json(self) -> dict[str, Any]:
        row = asdict(self)
        row.update(qualified=self.qualified, key=self.key)
        return row


def _conjuncts(node: exp.Expression) -> list[exp.Expression]:
    if isinstance(node, exp.And):
        return _conjuncts(node.left) + _conjuncts(node.right)
    if isinstance(node, exp.Paren):
        return _conjuncts(node.this)
    return [node]


def _bare_sql(node: exp.Expression) -> str:
    copy = node.copy()
    for column in copy.find_all(exp.Column):
        column.set("table", None)
    return copy.sql(dialect="sqlite")


@dataclass
class _Occurrences:
    conditions: list[str] = field(default_factory=list)
    covered: set[int] = field(default_factory=set)  # ids of Column nodes inside single-attribute conditions
    total: set[int] = field(default_factory=set)


def query_needs(query_id: str, sql: str, table_attrs: dict[str, set[str]]) -> list[Need]:
    tree = sqlglot.parse_one(sql, read="sqlite")
    aliases = alias_map(tree)
    occ: dict[tuple[str, str], _Occurrences] = {}

    # SELECT aliases (e.g. a CASE bucket) are not physical attributes.
    output_aliases = {node.alias for node in tree.find_all(exp.Alias) if node.alias}

    def resolved(column: exp.Column) -> tuple[str, str] | None:
        # Attributes the SQL references count even when the attribute file omits them
        # (for example Finan total_debt, Med id): the workload, not the file, defines needs.
        if not column.table and column.name in output_aliases:
            return None
        table = resolve_column(column, aliases, table_attrs)
        if table is None:
            return None
        return table, column.name

    for column in tree.find_all(exp.Column):
        key = resolved(column)
        if key:
            occ.setdefault(key, _Occurrences()).total.add(id(column))

    candidates: list[exp.Expression] = []
    for where in tree.find_all(exp.Where):
        candidates.extend(_conjuncts(where.this))
    for case in tree.find_all(exp.Case):
        for branch in case.args.get("ifs") or []:
            candidates.extend(_conjuncts(branch.this))
    for node in candidates:
        if node.find(exp.Select, exp.Subquery):
            continue
        columns = list(node.find_all(exp.Column))
        keys = {resolved(column) for column in columns}
        if len(keys) != 1 or None in keys:
            continue
        key = keys.pop()
        record = occ.setdefault(key, _Occurrences())
        sql_text = _bare_sql(node)
        if sql_text not in record.conditions:
            record.conditions.append(sql_text)
        record.covered.update(id(column) for column in columns)

    needs = []
    for (table, attribute), record in sorted(occ.items()):
        predicate_only = record.total and record.total <= record.covered
        needs.append(
            Need(
                query_id=query_id,
                table=table,
                attribute=attribute,
                kind="predicate" if predicate_only else "value",
                conditions=tuple(record.conditions) if predicate_only else (),
            )
        )
    # Each query carries weight 1, split over its needs: the benchmark averages per query.
    share = 1.0 / len(needs) if needs else 0.0
    return [Need(**{**asdict(need), "weight": share}) for need in needs]


def workload_needs(spec: CorpusSpec, queries: dict[str, str] | None = None) -> list[Need]:
    queries = queries if queries is not None else spec.queries()
    table_attrs = table_attribute_names(spec)
    needs: list[Need] = []
    for query_id in sorted(queries):
        needs.extend(query_needs(query_id, queries[query_id], table_attrs))
    return needs


def can_serve(provider: Need | None, consumer: Need) -> bool:
    """Zero-token information order. ``None`` is a canonical (query-independent) value read."""

    if provider is None:
        return True
    if provider.qualified != consumer.qualified:
        return False
    if provider.kind == "value":
        return True
    # A predicate-only read answers only its own conditions.
    return consumer.kind == "predicate" and set(consumer.conditions) <= set(provider.conditions)
