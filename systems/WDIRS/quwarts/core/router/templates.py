"""Query templates and drift splits from the SQL workload (system-side: uses only the SQL).

Three template levels, finest to coarsest:
  L1  literal template: the query with every literal replaced by a typed placeholder (strings $s,
      numbers $n), IN-lists collapsed to one placeholder, output aliases resolved. Queries sharing an
      L1 template differ only in constants (the QueryBot 5000 notion of a template).
  L2  role signature: the set of (column, role) pairs, role in {select, group, case, agg:<fn>,
      filter:<op>}.
  L3  column set.

Constants are template parameters: they change with every use, so a new constant is not drift and
the system must work for any constant by design. In case80 Legal every query is its own L1 and L2
template, so holding out templates equals the random split. The drift that matters is structural: a
known column used in a new role (an AVG column now under MIN; a grouped column now filtered).
``drift_split`` hides (column, role) pairs so every held-out query uses at least one known column in
a role no input query uses, while every column it uses is still used by some input query (so the
system still extracts it). ``include_constants=True`` reproduces the first definition, which also hid
(column, constant) pairs; that was a category error, kept only to reproduce the earlier run.
"""

from __future__ import annotations

import random
from typing import Any

import sqlglot
from sqlglot import exp

AGGREGATES = (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)
COMPARISONS = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.In, exp.Between, exp.Is, exp.Like)


def _parse(sql: str) -> exp.Expression:
    return sqlglot.parse_one(sql, read="sqlite")


def _aliases(tree: exp.Expression) -> dict[str, exp.Expression]:
    return {a.alias: a.this for a in tree.expressions if isinstance(a, exp.Alias)}


def _resolve_aliases(tree: exp.Expression) -> exp.Expression:
    """Replace references to output aliases (GROUP BY case_family, ORDER BY n) by their expressions."""
    aliases = _aliases(tree)
    for clause in ("group", "having", "order"):
        part = tree.args.get(clause)
        if not part:
            continue
        for col in list(part.find_all(exp.Column)):
            if not col.table and col.name in aliases:
                col.replace(aliases[col.name].copy())
    return tree


def literal_template(sql: str) -> str:
    def placeholder(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Literal):
            return exp.var("$s" if node.is_string else "$n")
        return node

    tree = _resolve_aliases(_parse(sql)).transform(placeholder)
    for node in list(tree.find_all(exp.In)):
        values = node.args.get("expressions") or []
        if values and all(isinstance(v, exp.Var) for v in values):
            node.set("expressions", [exp.var(values[0].name + "_list")])
    for alias in list(tree.find_all(exp.Alias)):
        alias.replace(alias.this)
    return tree.sql(dialect="sqlite")


def _columns(node: exp.Expression) -> set[str]:
    return {c.name for c in node.find_all(exp.Column)}


def role_signature(sql: str) -> frozenset[tuple[str, str]]:
    tree = _resolve_aliases(_parse(sql))
    roles: set[tuple[str, str]] = set()
    group = tree.args.get("group")
    if group:
        roles |= {(c, "group") for c in _columns(group)}
    for clause in ("where", "having"):
        part = tree.args.get(clause)
        if part:
            for cmp in part.find_all(*COMPARISONS):
                roles |= {(c, f"filter:{type(cmp).__name__.lower()}") for c in _columns(cmp)}
    for select in tree.expressions:
        aggs = list(select.find_all(*AGGREGATES))
        cases = list(select.find_all(exp.Case))
        for agg in aggs:
            roles |= {(c, f"agg:{type(agg).__name__.lower()}") for c in _columns(agg)}
        for case in cases:
            roles |= {(c, "case") for c in _columns(case)}
        if not aggs and not cases:
            roles |= {(c, "select") for c in _columns(select)}
    return frozenset(roles)


def column_set(sql: str) -> frozenset[str]:
    tree = _resolve_aliases(_parse(sql))
    return frozenset(_columns(tree) - set(_aliases(tree)))


def literals(sql: str) -> set[tuple[str, str]]:
    """(column, constant) pairs a query compares a column against (WHERE / HAVING / CASE conditions)."""
    out: set[tuple[str, str]] = set()
    for cmp in _resolve_aliases(_parse(sql)).find_all(*COMPARISONS):
        cols = _columns(cmp)
        for lit in cmp.find_all(exp.Literal):
            out |= {(c, lit.this) for c in cols}
    return out


def _items(sql: str, include_constants: bool = False) -> set[tuple[str, ...]]:
    roles = {("role", c, r) for c, r in role_signature(sql) if c != "*"}
    return roles | ({("literal", c, v) for c, v in literals(sql)} if include_constants else set())


def drift_split(rows: list[dict[str, str]], seed: int, held_out_fraction: float = 0.2,
                slack: float = 0.25, max_per_column: int | None = 1,
                max_item_share: float = 0.25, include_constants: bool = False) -> tuple[list[dict], list[dict], list[tuple[str, ...]]]:
    """Hide (column, role) and (column, constant) items; hold out every query that uses a hidden item.

    Items are tried in seeded random order. An item is hidden only if the held-out set stays within
    ``held_out_fraction * (1 + slack)`` of the workload, every column of every held-out query is
    still used by some input query, and (``max_per_column``) no column has more hidden items than
    allowed, and no single item pulls in more than ``max_item_share`` of the target, so the drift is
    spread over several columns and items instead of one. Stops once the held-out
    set reaches ``held_out_fraction``.
    """
    items_of = {r["query_id"]: _items(r["sql"], include_constants) for r in rows}
    cols_of = {r["query_id"]: column_set(r["sql"]) for r in rows}
    candidates = sorted(set().union(*items_of.values()))
    random.Random(seed).shuffle(candidates)
    target = int(round(held_out_fraction * len(rows)))
    cap = int(round(target * (1 + slack)))
    item_cap = max(1, int(round(target * max_item_share)))
    hidden: list[tuple[str, ...]] = []
    held: set[str] = set()
    per_column: dict[str, int] = {}
    for item in candidates:
        if len(held) >= target:
            break
        if max_per_column is not None and per_column.get(item[1], 0) >= max_per_column:
            continue
        new_held = held | {q for q, its in items_of.items() if item in its}
        if new_held == held or len(new_held) > cap or len(new_held - held) > item_cap:
            continue
        train_cols = set().union(*(cols_of[q] for q in items_of if q not in new_held))
        if any(not cols_of[q] <= train_cols for q in new_held):
            continue
        hidden.append(item)
        per_column[item[1]] = per_column.get(item[1], 0) + 1
        held = new_held
    train = [r for r in rows if r["query_id"] not in held]
    test = [r for r in rows if r["query_id"] in held]
    return train, test, hidden


def exposure(train: list[dict], held: list[dict]) -> dict[str, Any]:
    """How structurally new the held-out queries are to a system built from ``train``."""
    t1 = {literal_template(r["sql"]) for r in train}
    t2 = {role_signature(r["sql"]) for r in train}
    t3 = {column_set(r["sql"]) for r in train}
    pairs = set().union(*(role_signature(r["sql"]) for r in train))
    cols = set().union(*(column_set(r["sql"]) for r in train))
    lits = set().union(*(literals(r["sql"]) for r in train))
    per_query = {}
    for r in held:
        sig = role_signature(r["sql"])
        per_query[r["query_id"]] = {
            "L1_seen": literal_template(r["sql"]) in t1,
            "L2_seen": sig in t2,
            "L3_seen": column_set(r["sql"]) in t3,
            "unseen_roles": sorted(f"{c}:{role}" for c, role in sig - pairs),
            "unseen_columns": sorted(column_set(r["sql"]) - cols),
            "unseen_literals": sorted(f"{c}={v}" for c, v in literals(r["sql"]) - lits),
        }
    n = len(held)
    frac = lambda k: sum(v[k] for v in per_query.values()) / n  # noqa: E731
    has = lambda k: sum(bool(v[k]) for v in per_query.values()) / n  # noqa: E731
    return {"n_train": len(train), "n_held_out": n,
            "L1_seen": frac("L1_seen"), "L2_seen": frac("L2_seen"), "L3_seen": frac("L3_seen"),
            "with_unseen_role": has("unseen_roles"), "with_unseen_column": has("unseen_columns"),
            "with_unseen_literal": has("unseen_literals"),
            # Structural drift only: new constants are the normal use of a template, not drift.
            "with_any_drift": sum(bool(v["unseen_roles"] or v["unseen_columns"]) for v in per_query.values()) / n,
            "per_query": per_query}
