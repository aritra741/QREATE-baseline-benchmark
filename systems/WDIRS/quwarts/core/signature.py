"""Workload-observable signatures. AST only. No gold, no corpus names."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlglot import exp

from quwarts.core.logical import qualify
from quwarts.core.workload import _default_entity, _literal_value, parse_sql

ELIGIBLE_USAGES = frozenset(
    {
        "like_literal",
        "eq_literal",
        "is_null",
        "cmp_literal",
        "case_condition",
    }
)
FULL_VALUE_USAGES = frozenset(
    {
        "raw_projection",
        "raw_group_by",
        "equijoin",
        "count_distinct",
        "order_minmax",
        "var_compare",
        "unclassified",
    }
)

_CMP = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)
_LIKE = (exp.Like, exp.ILike)
_CMP_ALL = _CMP + _LIKE + (exp.Is, exp.In, exp.Between)


@dataclass(frozen=True)
class Occurrence:
    query_id: str
    attribute: str
    usage: str
    operator: str | None = None
    literal: str | None = None
    transforms: tuple[str, ...] = ()
    condition_sql: str | None = None
    bare_condition_sql: str | None = None
    table: str | None = None
    column: str | None = None
    qualifier: str | None = None


@dataclass(frozen=True)
class AtomicPredicate:
    pred_id: str
    attribute: str
    table: str
    column: str
    operator: str
    literal: str | None
    transforms: tuple[str, ...]
    condition_sql: str
    bare_condition_sql: str
    query_ids: tuple[str, ...]
    raw_occurrences: int

    @property
    def sig_name(self) -> str:
        return f"sig_{self.pred_id}"

    @property
    def resolved_name(self) -> str:
        return f"sig_{self.pred_id}_r"


@dataclass
class ObservabilityReport:
    signature_eligible: list[str] = field(default_factory=list)
    full_value_required: list[str] = field(default_factory=list)
    usages: dict[str, list[str]] = field(default_factory=dict)
    occurrences: list[Occurrence] = field(default_factory=list)
    gate_vocab: dict[str, str] = field(default_factory=dict)
    gate_pass: bool = False


def table_aliases(tree: exp.Expression) -> dict[str, str]:
    return {
        (node.alias or node.name).lower(): node.name.lower()
        for node in tree.find_all(exp.Table)
        if node.name
    }


def select_aliases(tree: exp.Expression) -> set[str]:
    found: set[str] = set()
    if not isinstance(tree, exp.Select):
        return found
    for projection in tree.expressions:
        if isinstance(projection, exp.Alias) and projection.alias:
            found.add(projection.alias.lower())
    return found


def resolve_attribute(
    column: exp.Column,
    aliases: dict[str, str],
    default: str | None,
) -> tuple[str, str, str] | None:
    name = column.name.lower() if column.name else None
    if not name:
        return None
    raw_table = column.table.lower() if column.table else None
    table = aliases.get(raw_table, raw_table) if raw_table else default
    if not table:
        return None
    return qualify(table, name), table, name


def _is_constant(node: exp.Expression | None) -> bool:
    return node is not None and node.find(exp.Column) is None


def _transforms_until(column: exp.Column, stop: exp.Expression) -> tuple[str, ...]:
    found: list[str] = []
    current: exp.Expression | None = column.parent
    while current is not None and current is not stop:
        if isinstance(current, exp.Lower):
            found.append("lower")
        elif isinstance(current, exp.Upper):
            found.append("upper")
        elif isinstance(current, exp.Trim):
            found.append("trim")
        current = current.parent
    return tuple(found)


def _in_join_on(node: exp.Expression) -> bool:
    current: exp.Expression | None = node
    while current is not None:
        if isinstance(current, exp.Join):
            return True
        current = current.parent
    return False


def _ancestor(node: exp.Expression, types: tuple[type, ...]) -> exp.Expression | None:
    current: exp.Expression | None = node.parent
    while current is not None:
        if isinstance(current, types):
            return current
        current = current.parent
    return None


def _between(node: exp.Expression, stop: exp.Expression, types: tuple[type, ...]) -> bool:
    current: exp.Expression | None = node.parent
    while current is not None and current is not stop:
        if isinstance(current, types):
            return True
        current = current.parent
    return False


def _in_case_when(column: exp.Column) -> bool:
    case = _ancestor(column, (exp.Case,))
    if case is None:
        return False
    for when in case.args.get("ifs") or []:
        this = when.this if isinstance(when, exp.If) else None
        if this is not None and (column is this or column.find_ancestor(exp.If) is when):
            if column in this.walk() or any(item is column for item in this.find_all(exp.Column)):
                return True
    return False


def _column_in(expr: exp.Expression | None, column: exp.Column) -> bool:
    if expr is None:
        return False
    return any(item is column for item in expr.find_all(exp.Column))


def _in_when_condition(column: exp.Column) -> bool:
    current: exp.Expression | None = column
    while current is not None:
        parent = current.parent
        if isinstance(parent, exp.If) and parent.this is current:
            return _ancestor(parent, (exp.Case,)) is not None
        current = parent
    return False


def _op_name(node: exp.Expression) -> str:
    if isinstance(node, (exp.Like, exp.ILike)):
        return "LIKE"
    if isinstance(node, exp.EQ):
        return "="
    if isinstance(node, exp.NEQ):
        return "!="
    if isinstance(node, exp.GT):
        return ">"
    if isinstance(node, exp.GTE):
        return ">="
    if isinstance(node, exp.LT):
        return "<"
    if isinstance(node, exp.LTE):
        return "<="
    if isinstance(node, exp.Is):
        return "IS NOT NULL" if node.args.get("not") else "IS NULL"
    if isinstance(node, exp.In):
        return "IN"
    if isinstance(node, exp.Between):
        return "BETWEEN"
    return node.key.upper()


def _literal_key(node: exp.Expression | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, exp.Null):
        return None
    if isinstance(node, exp.Literal):
        return str(_literal_value(node))
    if isinstance(node, exp.Boolean):
        return "1" if node.this else "0"
    literals = [str(_literal_value(item)) for item in node.find_all(exp.Literal)]
    if literals and node.find(exp.Column) is None:
        return "|".join(literals) if len(literals) > 1 else literals[0]
    if node.find(exp.Column) is None:
        return node.sql(dialect="sqlite")
    return None


def _other_operand(node: exp.Expression, column: exp.Column) -> exp.Expression | None:
    if isinstance(node, exp.Between):
        return None
    if isinstance(node, exp.In):
        return None
    left = node.this
    right = node.expression
    if _column_in(left, column) and not _column_in(right, column):
        return right
    if _column_in(right, column) and not _column_in(left, column):
        return left
    return None


def _classify_comparison(node: exp.Expression, column: exp.Column) -> str:
    if isinstance(node, exp.Is):
        return "is_null"
    if isinstance(node, _LIKE):
        other = _other_operand(node, column)
        if other is not None and _is_constant(other):
            return "like_literal"
        return "var_compare"
    if isinstance(node, exp.In):
        if all(_is_constant(item) for item in node.expressions):
            return "eq_literal"
        return "var_compare"
    if isinstance(node, exp.Between):
        low, high = node.args.get("low"), node.args.get("high")
        if _is_constant(low) and _is_constant(high):
            return "cmp_literal"
        return "var_compare"
    if isinstance(node, _CMP):
        other = _other_operand(node, column)
        if other is not None and _is_constant(other):
            return "eq_literal" if isinstance(node, (exp.EQ, exp.NEQ)) else "cmp_literal"
        if _in_join_on(node) and isinstance(node, exp.EQ):
            return "equijoin"
        return "var_compare"
    return "unclassified"


def _raw_group(column: exp.Column) -> bool:
    group = _ancestor(column, (exp.Group,))
    if group is None:
        return False
    if _between(column, group, (exp.Case, *_CMP_ALL, exp.AggFunc)):
        return False
    return True


def _raw_order(column: exp.Column) -> bool:
    order = _ancestor(column, (exp.Order,))
    if order is None:
        return False
    if _between(column, order, (exp.Case, *_CMP_ALL, exp.AggFunc)):
        return False
    return True


def _raw_projection(column: exp.Column, tree: exp.Expression) -> bool:
    if not isinstance(tree, exp.Select):
        return False
    if _in_when_condition(column):
        return False
    if _ancestor(column, _CMP_ALL + (exp.AggFunc,)):
        return False
    for projection in tree.expressions:
        if any(item is column for item in projection.find_all(exp.Column)):
            return True
    return False


def classify_column(
    column: exp.Column,
    tree: exp.Expression,
    aliases: dict[str, str],
    default: str | None,
    alias_names: set[str],
    query_id: str,
) -> Occurrence | None:
    if not column.name:
        return None
    if not column.table and column.name.lower() in alias_names:
        return None
    resolved = resolve_attribute(column, aliases, default)
    if resolved is None:
        return None
    attribute, table, name = resolved
    cmp_node = _ancestor(column, _CMP_ALL)
    usage = None
    operator = None
    literal = None
    transforms: tuple[str, ...] = ()
    condition_sql = None
    bare_condition_sql = None
    if cmp_node is not None:
        usage = _classify_comparison(cmp_node, column)
        if usage in ELIGIBLE_USAGES and _in_when_condition(column):
            usage = "case_condition"
        operator = _op_name(cmp_node)
        transforms = _transforms_until(column, cmp_node)
        if isinstance(cmp_node, exp.In):
            literal = "|".join(
                str(_literal_key(item) or "") for item in cmp_node.expressions
            )
        elif isinstance(cmp_node, exp.Between):
            literal = f"{_literal_key(cmp_node.args.get('low'))}|{_literal_key(cmp_node.args.get('high'))}"
        elif isinstance(cmp_node, exp.Is):
            literal = None
        else:
            other = _other_operand(cmp_node, column)
            literal = _literal_key(other)
        if usage in ELIGIBLE_USAGES or usage == "case_condition":
            condition_sql = cmp_node.sql(dialect="sqlite")
            bare = cmp_node.copy()
            for col in bare.find_all(exp.Column):
                col.set("table", None)
            bare_condition_sql = bare.sql(dialect="sqlite")
    elif _ancestor(column, (exp.Count,)) is not None:
        count = _ancestor(column, (exp.Count,))
        usage = "count_distinct" if count is not None and count.args.get("distinct") else "unclassified"
    elif _ancestor(column, (exp.Max, exp.Min)):
        usage = "order_minmax"
    elif _raw_group(column):
        usage = "raw_group_by"
    elif _raw_order(column):
        usage = "order_minmax"
    elif _raw_projection(column, tree):
        usage = "raw_projection"
    else:
        usage = "unclassified"
    return Occurrence(
        query_id=query_id,
        attribute=attribute,
        usage=usage,
        operator=operator,
        literal=literal,
        transforms=transforms,
        condition_sql=condition_sql,
        bare_condition_sql=bare_condition_sql,
        table=table,
        column=name,
        qualifier=column.table.lower() if column.table else None,
    )


def audit_sql(query_id: str, sql: str) -> list[Occurrence]:
    tree = parse_sql(sql)
    aliases = table_aliases(tree)
    default = _default_entity(tree)
    alias_names = select_aliases(tree)
    found: list[Occurrence] = []
    for column in tree.find_all(exp.Column):
        item = classify_column(column, tree, aliases, default, alias_names, query_id)
        if item is not None:
            found.append(item)
    return found


def audit_workload(queries: Iterable[dict[str, str]]) -> ObservabilityReport:
    occurrences: list[Occurrence] = []
    for row in queries:
        occurrences.extend(audit_sql(row["query_id"], row["sql"]))
    by_attr: dict[str, set[str]] = defaultdict(set)
    for item in occurrences:
        by_attr[item.attribute].add(item.usage)
    eligible: list[str] = []
    required: list[str] = []
    usages = {name: sorted(kinds) for name, kinds in sorted(by_attr.items())}
    for name, kinds_list in usages.items():
        kinds = set(kinds_list)
        if kinds & FULL_VALUE_USAGES:
            required.append(name)
        elif kinds and kinds <= (ELIGIBLE_USAGES | {"case_condition"}):
            eligible.append(name)
        else:
            required.append(name)
    gate = {
        name: ("full_value_required" if name in required else "signature_eligible")
        for name in usages
    }
    return ObservabilityReport(
        signature_eligible=eligible,
        full_value_required=required,
        usages=usages,
        occurrences=occurrences,
        gate_vocab=gate,
        gate_pass=bool(eligible) or not usages,
    )


def _pred_key(item: Occurrence) -> tuple[Any, ...]:
    return (item.attribute, item.operator, item.literal, item.transforms)


def _pred_id(key: tuple[Any, ...]) -> str:
    payload = "|".join("" if part is None else str(part) for part in key)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def enumerate_predicates(
    occurrences: Iterable[Occurrence],
    eligible: Iterable[str],
) -> list[AtomicPredicate]:
    allowed = set(eligible)
    grouped: dict[tuple[Any, ...], list[Occurrence]] = defaultdict(list)
    for item in occurrences:
        if item.attribute not in allowed:
            continue
        if item.usage not in ELIGIBLE_USAGES and item.usage != "case_condition":
            continue
        if not item.operator or not item.bare_condition_sql:
            continue
        grouped[_pred_key(item)].append(item)
    predicates: list[AtomicPredicate] = []
    for key, items in grouped.items():
        sample = items[0]
        predicates.append(
            AtomicPredicate(
                pred_id=_pred_id(key),
                attribute=sample.attribute,
                table=sample.table or sample.attribute.split(".")[0],
                column=sample.column or sample.attribute.split(".")[-1],
                operator=sample.operator or "",
                literal=sample.literal,
                transforms=sample.transforms,
                condition_sql=sample.condition_sql or "",
                bare_condition_sql=sample.bare_condition_sql or "",
                query_ids=tuple(sorted({item.query_id for item in items})),
                raw_occurrences=len(items),
            )
        )
    predicates.sort(key=lambda item: (item.attribute, item.operator, item.literal or ""))
    return predicates


def predicate_index(predicates: Iterable[AtomicPredicate]) -> dict[tuple[Any, ...], AtomicPredicate]:
    return {
        (item.attribute, item.operator, item.literal, item.transforms): item
        for item in predicates
    }


def _match_node(
    node: exp.Expression,
    tree: exp.Expression,
    aliases: dict[str, str],
    default: str | None,
    index: dict[tuple[Any, ...], AtomicPredicate],
) -> AtomicPredicate | None:
    columns = list(node.find_all(exp.Column))
    if not columns:
        return None
    for column in columns:
        resolved = resolve_attribute(column, aliases, default)
        if resolved is None:
            continue
        attribute, _, _ = resolved
        operator = _op_name(node)
        transforms = _transforms_until(column, node)
        if isinstance(node, exp.In):
            literal = "|".join(str(_literal_key(item) or "") for item in node.expressions)
        elif isinstance(node, exp.Between):
            literal = f"{_literal_key(node.args.get('low'))}|{_literal_key(node.args.get('high'))}"
        elif isinstance(node, exp.Is):
            literal = None
        else:
            other = _other_operand(node, column)
            if other is None or not _is_constant(other):
                continue
            literal = _literal_key(other)
        found = index.get((attribute, operator, literal, transforms))
        if found is not None:
            return found
    return None


def statements_as_queries(statements: dict[str, str]) -> list[dict[str, str]]:
    return [{"query_id": key, "sql": value} for key, value in statements.items()]


def rewrite_sql(sql: str, predicates: Iterable[AtomicPredicate]) -> str:
    tree = parse_sql(sql)
    aliases = table_aliases(tree)
    default = _default_entity(tree)
    index = predicate_index(predicates)
    replacements: list[tuple[exp.Expression, AtomicPredicate, str | None]] = []
    for node in list(tree.walk()):
        if not isinstance(node, _CMP_ALL):
            continue
        matched = _match_node(node, tree, aliases, default, index)
        if matched is None:
            continue
        column = next((col for col in node.find_all(exp.Column) if resolve_attribute(col, aliases, default)), None)
        qualifier = column.table if column is not None and column.table else None
        replacements.append((node, matched, qualifier))
    if not replacements:
        return sql
    for node, pred, qualifier in replacements:
        original = node.copy()
        truth = exp.Column(
            this=exp.to_identifier(pred.sig_name),
            table=exp.to_identifier(qualifier) if qualifier else None,
        )
        resolved = exp.Column(
            this=exp.to_identifier(pred.resolved_name),
            table=exp.to_identifier(qualifier) if qualifier else None,
        )
        case = exp.Case()
        case.set(
            "ifs",
            [
                exp.If(
                    this=exp.EQ(this=resolved, expression=exp.Literal.number(1)),
                    true=truth,
                )
            ],
        )
        case.set("default", original)
        node.replace(case)
    return tree.sql(dialect="sqlite")


def gold_signature_sql(pred: AtomicPredicate) -> str:
    col = f'"{pred.column}"'
    return (
        f"CASE WHEN {col} IS NULL THEN NULL "
        f"WHEN {pred.bare_condition_sql} THEN 1 ELSE 0 END"
    )


def materialize_signatures(conn: Any, predicates: Iterable[AtomicPredicate]) -> None:
    by_table: dict[str, list[AtomicPredicate]] = defaultdict(list)
    for pred in predicates:
        by_table[pred.table].append(pred)
    for table, items in by_table.items():
        existing = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
        for pred in items:
            if pred.sig_name not in existing:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{pred.sig_name}" INTEGER')
                existing.add(pred.sig_name)
            if pred.resolved_name not in existing:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{pred.resolved_name}" INTEGER')
                existing.add(pred.resolved_name)
            conn.execute(
                f'UPDATE "{table}" SET "{pred.sig_name}" = {gold_signature_sql(pred)}, '
                f'"{pred.resolved_name}" = 1'
            )
    conn.commit()
