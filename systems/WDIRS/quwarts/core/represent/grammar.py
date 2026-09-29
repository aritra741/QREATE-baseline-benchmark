"""What the workload says about how each column's values must be written (no gold, no corpus names).

A SQL workload states representation in its literals and operators, not only which columns it needs:

* ``col = 'x'``, ``col != 'x'``, ``col IN ('x', 'y')``: exact equality. A stored value that names ``x`` in
  any other form is invisible to the query.
* ``col LIKE '%x%'`` (SQLite: case-insensitive): the stored value must contain ``x``.
* ``LOWER(col)``, ``UPPER(col)``, ``TRIM(col)``: the query itself tolerates case or edge spaces.
* numeric comparison, arithmetic, ``SUM``/``AVG``, ``CAST(... AS INTEGER)``: the value must be a number.
* ``a.col = b.col``: the two columns must share one domain (the same entity written the same way).
* ``GROUP BY col``: every distinct spelling becomes its own group, so spellings of one value must agree.

``grammar(spec, queries)`` collects these per column. ``shape(value)`` abstracts a value into a token
signature in the style of Potter's Wheel (Raman & Hellerstein, VLDB 2001): runs of digits, words by case,
and punctuation kept literally, so ``20th-21st`` is ``9a-9a``, ``Frontcourt`` is ``Aa``,
``clinical_evaluation`` is ``a_a``. A column's literal shapes and case convention are the representation
the workload expects for values it has not named yet: constants change, their form does not.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

WRAPPERS = {"LOWER": "case", "UPPER": "case", "TRIM": "space", "LTRIM": "space", "RTRIM": "space"}


@dataclass
class ColumnUse:
    table: str
    column: str
    equality: Counter = field(default_factory=Counter)  # literal -> occurrences (=, !=, IN)
    like: Counter = field(default_factory=Counter)  # pattern core -> occurrences
    numeric: int = 0  # numeric comparisons, arithmetic, numeric aggregates, casts
    grouped: int = 0  # raw GROUP BY
    grouped_via_case: int = 0  # GROUP BY an expression (CASE) over the column
    projected: int = 0
    filtered: int = 0
    tolerated: set[str] = field(default_factory=set)  # "case" and/or "space" (wrapper functions)
    joins: Counter = field(default_factory=Counter)  # (table, column) -> occurrences
    queries: set[str] = field(default_factory=set)

    @property
    def key(self) -> tuple[str, str]:
        return (self.table, self.column)

    @property
    def literals(self) -> list[str]:
        return sorted(x for x in set(self.equality) | set(self.like) if x)

    @property
    def exact_uses(self) -> int:
        """Uses in which the stored spelling decides the answer: equality, raw grouping, joins."""

        return sum(self.equality.values()) + self.grouped + sum(self.joins.values())

    @property
    def shapes(self) -> Counter:
        return Counter(shape(x) for x in self.literals)

    @property
    def case_convention(self) -> str | None:
        """``title``, ``lower`` or ``upper`` when every alphabetic word of the literals agrees."""

        kinds = Counter()
        if len(self.literals) < 2:  # one literal ('USA') is an example, not a convention
            return None
        for lit in self.literals:
            for word in re.findall(r"[A-Za-z]+", lit):
                if len(word) < 2:
                    continue
                kinds["upper" if word.isupper() else "lower" if word.islower() else "title" if word[0].isupper() else "mixed"] += 1
        if len(kinds) == 1:
            kind = next(iter(kinds))
            if kind == "upper" and len(self.literals) < 3:  # acronyms are not a case convention
                return None
            return kind
        return None

    @property
    def separator(self) -> str | None:
        """Within-value word separator of the literals (``_`` or space) when they agree."""

        seps = Counter("_" if "_" in lit else " " for lit in self.literals if re.search(r"[A-Za-z][ _][A-Za-z]", lit))
        return next(iter(seps)) if len(seps) == 1 else None


def shape(value: Any) -> str:
    text = str(value)
    out = []
    for token in re.findall(r"\d+|[A-Za-z]+|\s+|[^\w\s]|_", text):
        if token.isdigit():
            out.append("9")
        elif token.isalpha():
            out.append("A" if token.isupper() and len(token) > 1 else "Aa" if token[0].isupper() else "a")
        elif token.isspace():
            out.append(" ")
        else:
            out.append(token)
    return "".join(out)


def _unwrap(node: exp.Expression, tolerated: set[str]) -> exp.Expression:
    while isinstance(node, (exp.Lower, exp.Upper, exp.Trim)) or (isinstance(node, exp.Anonymous) and node.name.upper() in WRAPPERS):
        name = node.key.upper() if not isinstance(node, exp.Anonymous) else node.name.upper()
        tolerated.add(WRAPPERS.get(name, "case"))
        node = node.this
    return node


def _like_core(pattern: str) -> str:
    return pattern.strip("%_").replace("%", " ").strip()


def grammar(spec, queries: dict[str, str]) -> dict[tuple[str, str], ColumnUse]:
    from quwarts.core.router.workload_features import alias_map, resolve_column, table_attribute_names

    table_attrs = table_attribute_names(spec, queries)
    uses: dict[tuple[str, str], ColumnUse] = {}

    def use(col: exp.Column, aliases) -> ColumnUse | None:
        table = resolve_column(col, aliases, table_attrs)
        if table is None or not col.name:
            return None
        key = (table, col.name)
        if key not in uses:
            uses[key] = ColumnUse(table, col.name)
        return uses[key]

    for qid, sql in queries.items():
        try:
            tree = sqlglot.parse_one(sql, read="sqlite")
        except sqlglot.errors.ParseError:
            continue
        aliases = alias_map(tree)
        output_aliases = {n.alias for n in tree.find_all(exp.Alias) if n.alias}

        def column_of(node: exp.Expression, tolerated: set[str]) -> exp.Column | None:
            inner = _unwrap(node, tolerated)
            if isinstance(inner, exp.Column) and not (not inner.table and inner.name in output_aliases):
                return inner
            return None

        for node in tree.find_all(exp.EQ, exp.NEQ):
            tol: set[str] = set()
            left, right = column_of(node.left, tol), column_of(node.right, tol)
            if left is not None and right is not None:
                a, b = use(left, aliases), use(right, aliases)
                if a and b and a.table != b.table:
                    a.joins[b.key] += 1
                    b.joins[a.key] += 1
                    a.tolerated |= tol
                    b.tolerated |= tol
                    a.queries.add(qid)
                    b.queries.add(qid)
                continue
            col = left if left is not None else right
            other = node.right if left is not None else node.left
            if col is not None and isinstance(other, exp.Literal):
                u = use(col, aliases)
                if u:
                    u.tolerated |= tol
                    u.queries.add(qid)
                    u.filtered += 1
                    if other.is_string:
                        u.equality[other.this] += 1
                    else:
                        u.numeric += 1
        for node in tree.find_all(exp.In):
            tol = set()
            col = column_of(node.this, tol)
            if col is None:
                continue
            u = use(col, aliases)
            if u:
                u.tolerated |= tol
                u.queries.add(qid)
                u.filtered += 1
                for item in node.expressions:
                    if isinstance(item, exp.Literal):
                        if item.is_string:
                            u.equality[item.this] += 1
                        else:
                            u.numeric += 1
        for node in tree.find_all(exp.Like, exp.ILike):
            tol = {"case"}  # SQLite LIKE ignores ASCII case
            col = column_of(node.this, tol)
            if col is None or not isinstance(node.expression, exp.Literal):
                continue
            u = use(col, aliases)
            if u:
                u.tolerated |= tol
                u.queries.add(qid)
                u.filtered += 1
                core = _like_core(node.expression.this)
                if core:
                    u.like[core] += 1
        def direct(node: exp.Expression) -> exp.Column | None:
            """A column operand, possibly under a numeric CAST (``CAST(col AS INTEGER)``)."""

            while isinstance(node, exp.Cast):
                node = node.this
            return node if isinstance(node, exp.Column) and not (not node.table and node.name in output_aliases) else None

        numeric_nodes = []
        for node in tree.find_all(exp.GT, exp.GTE, exp.LT, exp.LTE):
            if any(isinstance(x, exp.Literal) and not x.is_string for x in (node.left, node.right)):
                numeric_nodes += [node.left, node.right]
        for node in tree.find_all(exp.Between):
            numeric_nodes.append(node.this)
        for node in tree.find_all(exp.Sum, exp.Avg):
            numeric_nodes.append(node.this)
        for node in tree.find_all(exp.Div, exp.Mul, exp.Add, exp.Sub):
            numeric_nodes += [node.left, node.right]
        for node in tree.find_all(exp.Cast):
            if node.to.this in (exp.DataType.Type.INT, exp.DataType.Type.BIGINT, exp.DataType.Type.FLOAT,
                                exp.DataType.Type.DOUBLE, exp.DataType.Type.DECIMAL):
                numeric_nodes.append(node.this)
        for target in numeric_nodes:
            col = direct(target) if target is not None else None
            if col is not None:
                u = use(col, aliases)
                if u:
                    u.numeric += 1
                    u.queries.add(qid)
        select = tree.find(exp.Select)
        if select is not None:
            projected = {}
            for item in select.expressions:
                target = item.this if isinstance(item, exp.Alias) else item
                tol = set()
                col = column_of(target, tol)
                if col is not None:
                    u = use(col, aliases)
                    if u:
                        u.projected += 1
                        u.queries.add(qid)
                        if isinstance(item, exp.Alias):
                            projected[item.alias] = u
                elif isinstance(item, exp.Alias):
                    projected[item.alias] = [use(c, aliases) for c in target.find_all(exp.Column)]
            group = select.args.get("group")
            if group is not None:
                for g in group.expressions:
                    tol = set()
                    col = column_of(g, tol)
                    if col is not None and col.name not in projected:
                        u = use(col, aliases)
                        if u:
                            u.grouped += 1
                            u.queries.add(qid)
                        continue
                    name = g.name if isinstance(g, exp.Column) else None
                    target = projected.get(name) if name else None
                    if isinstance(target, ColumnUse):
                        target.grouped += 1
                    elif isinstance(target, list):
                        for u in target:
                            if u:
                                u.grouped_via_case += 1
                    else:
                        for c in g.find_all(exp.Column):
                            u = use(c, aliases)
                            if u:
                                u.grouped_via_case += 1
    return uses


def join_pairs(uses: dict[tuple[str, str], ColumnUse]) -> list[tuple[tuple[str, str], tuple[str, str], int]]:
    seen, out = set(), []
    for key, u in uses.items():
        for other, n in u.joins.items():
            pair = tuple(sorted([key, other]))
            if pair not in seen:
                seen.add(pair)
                out.append((pair[0], pair[1], n))
    return out
