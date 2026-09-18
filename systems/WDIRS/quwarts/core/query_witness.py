"""Query-correct support grain. Not always the primary entity id."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable

from sqlglot import exp

from quwarts.core.query_support import QueryShape, SupportRow, _freeze, grain_sql, query_shape
from quwarts.core.signature import table_aliases
from quwarts.core.workload import _default_entity, parse_sql

_AGGS = (exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)
_TOKEN_MARKERS = ("||", " like ", "like '%|'")


@dataclass(frozen=True)
class JoinSpec:
    join_id: str
    left_table: str
    right_table: str
    left_alias: str
    right_alias: str
    on_sql: str
    entity_edge: bool


@dataclass(frozen=True)
class WitnessSpec:
    query_id: str
    sql: str
    kinds: tuple[str, ...]
    primary: str
    primary_alias: str
    tables: tuple[str, ...]
    alias_to_table: tuple[tuple[str, str], ...]
    count_column: str | None
    distinct_sql: str | None
    group_aliases: tuple[str, ...]
    group_sql: tuple[str, ...]
    joins: tuple[JoinSpec, ...]

    @property
    def kind(self) -> str:
        return "+".join(self.kinds) if self.kinds else "row"

    def table_for(self, alias: str) -> str:
        mapping = dict(self.alias_to_table)
        return mapping.get(alias.lower(), alias.lower())


def _norm_sql(sql: str) -> str:
    return " ".join((sql or "").lower().split())


def join_signature_id(left_table: str, right_table: str, on_sql: str) -> str:
    a, b = sorted((left_table.lower(), right_table.lower()))
    digest = hashlib.sha256(f"{a}|{b}|{_norm_sql(on_sql)}".encode()).hexdigest()[:16]
    return digest


def group_digest(expr_sql: str) -> str:
    return hashlib.sha256(_norm_sql(expr_sql).encode()).hexdigest()[:12]


def group_sig_names(expr_sql: str) -> tuple[str, str]:
    digest = group_digest(expr_sql)
    return f"sig_group_{digest}", f"sig_group_{digest}_r"


def normalize_group(value: Any) -> str:
    if value in (None, "", "unknown"):
        return "unknown"
    if isinstance(value, dict):
        import json

        value = json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, (list, tuple)):
        import json

        value = json.dumps(list(value), default=str)
    return " ".join(str(value).casefold().split())


def compile_witness_spec(query_id: str, sql: str, shape: QueryShape | None = None) -> WitnessSpec:
    shape = shape or query_shape(query_id, sql)
    tree = parse_sql(sql)
    aliases = table_aliases(tree)
    default = _default_entity(tree) or shape.primary
    kinds: list[str] = []
    count_column = None
    distinct_sql = None
    for proj in getattr(tree, "expressions", []) or []:
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        count = expr if isinstance(expr, exp.Count) else expr.find(exp.Count)
        if count is None:
            continue
        inner = count.this
        starred = (
            bool(count.args.get("star"))
            or isinstance(inner, exp.Star)
            or inner is None
        )
        if count.args.get("distinct") or isinstance(count.this, exp.Distinct):
            kinds.append("distinct")
            inner = count.this
            if isinstance(inner, exp.Distinct) and inner.expressions:
                inner = inner.expressions[0]
            if isinstance(inner, exp.Tuple) and inner.expressions:
                inner = inner.expressions[0]
            distinct_sql = inner.sql(dialect="sqlite") if inner is not None else None
            if isinstance(inner, exp.Column) and inner.name:
                count_column = inner.name.lower()
        elif starred or count.this is None:
            kinds.append("row")
        else:
            kinds.append("counted_value")
            col = count.find(exp.Column)
            count_column = col.name.lower() if col is not None and col.name else None
    if not kinds:
        kinds.append("row")
    joins = tuple(_join_specs(tree, aliases))
    if joins:
        kinds.append("join_tuple")
        if any(item.entity_edge for item in joins):
            kinds.append("entity_edge")
    if shape.group_aliases:
        kinds.append("grouped")
    seen: list[str] = []
    for item in kinds:
        if item not in seen:
            seen.append(item)
    alias_pairs = tuple(sorted((alias, table) for alias, table in aliases.items()))
    if not alias_pairs and shape.primary:
        alias_pairs = ((shape.primary_alias, shape.primary),)
    return WitnessSpec(
        query_id=query_id,
        sql=sql,
        kinds=tuple(seen),
        primary=shape.primary,
        primary_alias=shape.primary_alias,
        tables=shape.tables,
        alias_to_table=alias_pairs,
        count_column=count_column,
        distinct_sql=distinct_sql,
        group_aliases=shape.group_aliases,
        group_sql=shape.group_sql,
        joins=joins,
    )


def _join_specs(tree: exp.Expression, aliases: dict[str, str]) -> list[JoinSpec]:
    found: list[JoinSpec] = []
    seen: set[str] = set()
    prior: exp.Table | None = None
    for table in tree.find_all(exp.Table):
        if prior is None:
            prior = table
            continue
        on = None
        parent = table.parent
        while parent is not None and not isinstance(parent, exp.Join):
            parent = parent.parent
        if isinstance(parent, exp.Join):
            on = parent.args.get("on")
        if on is None or prior is None:
            prior = table
            continue
        left_alias = (prior.alias or prior.name or "").lower()
        right_alias = (table.alias or table.name or "").lower()
        left_table = aliases.get(left_alias, (prior.name or "").lower())
        right_table = aliases.get(right_alias, (table.name or "").lower())
        on_sql = on.sql(dialect="sqlite")
        join_id = join_signature_id(left_table, right_table, on_sql)
        if join_id in seen:
            prior = table
            continue
        seen.add(join_id)
        low = _norm_sql(on_sql)
        entity_edge = any(marker in low for marker in _TOKEN_MARKERS)
        a_table, b_table = (left_table, right_table)
        a_alias, b_alias = (left_alias, right_alias)
        if left_table > right_table:
            a_table, b_table = right_table, left_table
            a_alias, b_alias = right_alias, left_alias
        found.append(
            JoinSpec(
                join_id=join_id,
                left_table=a_table,
                right_table=b_table,
                left_alias=a_alias,
                right_alias=b_alias,
                on_sql=on_sql,
                entity_edge=entity_edge,
            )
        )
        prior = table
    return found


def occupancy_key(rowids: dict[str, int], distinct_value: Any = None, entity_id: Any = None) -> Any:
    return _freeze(
        (
            tuple(sorted((str(table), int(rid)) for table, rid in rowids.items())),
            str(distinct_value or entity_id or ""),
        )
    )


def witness_key_of(row: SupportRow | dict[str, Any]) -> Any:
    if isinstance(row, dict):
        if row.get("witness_key") not in (None, (), ""):
            return _freeze(row["witness_key"])
        return row.get("entity_id")
    if getattr(row, "witness_key", None) not in (None, (), ""):
        return _freeze(row.witness_key)
    return row.entity_id


def make_witness_key(
    spec: WitnessSpec,
    rowids: dict[str, int],
    *,
    distinct_value: Any = None,
    group_key: dict[str, Any] | None = None,
    counted_present: bool | None = None,
) -> tuple:
    parts: list[Any] = []
    if "distinct" in spec.kinds:
        parts.append(("d", None if distinct_value in (None, "") else str(distinct_value)))
    elif "counted_value" in spec.kinds:
        parts.append(("c", int(rowids.get(spec.primary) or 0), bool(counted_present)))
    else:
        parts.append(("r", int(rowids.get(spec.primary) or 0)))
    if "join_tuple" in spec.kinds or "entity_edge" in spec.kinds:
        parts.append(("j", tuple(sorted((str(table), int(rid)) for table, rid in rowids.items()))))
    if "grouped" in spec.kinds:
        groups = group_key or {}
        parts.append(
            ("g", tuple(normalize_group(groups.get(name)) for name in spec.group_aliases))
        )
    return _freeze(parts)


def grain_sql_for(spec: WitnessSpec) -> str:
    sql = grain_sql(spec.sql)
    tree = parse_sql(sql)
    if not isinstance(tree, exp.Select):
        return sql
    kept = list(tree.expressions)
    if spec.distinct_sql:
        kept.append(exp.alias_(parse_sql(spec.distinct_sql), "distinct_value"))
    if spec.count_column and "counted_value" in spec.kinds:
        kept.append(
            exp.alias_(
                exp.Column(
                    this=exp.to_identifier(spec.count_column),
                    table=exp.to_identifier(spec.primary_alias),
                ),
                "counted_value",
            )
        )
    tree.set("expressions", kept)
    return tree.sql(dialect="sqlite")


def support_from_grain(
    spec: WitnessSpec,
    rows: Iterable[dict[str, Any]],
    rid_to_entity: dict[int, str] | None = None,
) -> list[SupportRow]:
    mapping = rid_to_entity or {}
    out: list[SupportRow] = []
    for row in rows:
        rowids: dict[str, int] = {}
        for alias, table in spec.alias_to_table:
            raw = row.get(f"{alias}__rid")
            if raw in (None, ""):
                continue
            rowids[table] = int(raw)
        if spec.primary not in rowids:
            raw = row.get(f"{spec.primary_alias}__rid")
            if raw not in (None, ""):
                rowids[spec.primary] = int(raw)
        primary_rid = int(rowids.get(spec.primary) or 0)
        groups = {name: row.get(name) for name in spec.group_aliases}
        distinct = row.get("distinct_value")
        counted = row.get("counted_value")
        key = make_witness_key(
            spec,
            rowids,
            distinct_value=distinct,
            group_key=groups,
            counted_present=counted not in (None, ""),
        )
        partners = tuple(
            str(rowids[table])
            for table in spec.tables
            if table != spec.primary and table in rowids
        )
        out.append(
            SupportRow(
                entity_id=str(mapping.get(primary_rid) or primary_rid),
                rowid=primary_rid,
                included="true",
                group_key=groups,
                join_partner_ids=partners,
                witness_key=key,
                rowids=rowids,
                distinct_value=None if distinct in (None, "") else str(distinct),
                source="aprime",
            )
        )
    return out


def group_token(row: SupportRow, spec: WitnessSpec) -> str:
    if not spec.group_aliases:
        return ""
    if len(spec.group_aliases) == 1:
        return normalize_group(row.group_key.get(spec.group_aliases[0]))
    return normalize_group([row.group_key.get(name) for name in spec.group_aliases])
