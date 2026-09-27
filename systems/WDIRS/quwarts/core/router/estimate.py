"""Aggregate answers from a proxy table plus an oracle sample, with confidence intervals (system-side).

The proxy table holds a cheap read of every document; the oracle holds a careful read of a uniform
random sample S of n of the N documents. For a query, every document contributes to each output cell
a value computed by the query's own SQL expressions (WHERE, grouping expressions such as CASE
buckets, aggregate arguments) on its proxy row (P_i) or oracle row (O_i). The difference estimator

    T_hat = sum_{i in all} P_i + (N / n) * sum_{i in S} (O_i - P_i)

is unbiased for sum_i O_i (the answer on an all-oracle table) under simple random sampling without
replacement, with Var = N^2 (1 - n/N) s_d^2 / n (SampleClean; prediction-powered inference). AVG is the
ratio of two such totals, with a linearized (delta-method) variance. MIN/MAX are not estimable from
a sample; they are computed on the proxy and marked uncertified. COUNT(DISTINCT), LIMIT and nested
aggregates are unsupported (the caller falls back to the proxy answer).
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

Z95 = 1.959964
KINDS = {exp.Count: "count", exp.Sum: "sum", exp.Avg: "avg", exp.Min: "min", exp.Max: "max"}
OPS = {exp.GT: lambda a, b: a > b, exp.GTE: lambda a, b: a >= b, exp.LT: lambda a, b: a < b,
       exp.LTE: lambda a, b: a <= b, exp.EQ: lambda a, b: a == b, exp.NEQ: lambda a, b: a != b}


@dataclass
class Plan:
    table: str
    keys: list[tuple[str, str]] = field(default_factory=list)   # (output name, SQL expression)
    aggs: list[dict[str, Any]] = field(default_factory=list)    # name, kind, num, den, hidden
    where: str | None = None
    having: list[tuple[str, Any, float]] = field(default_factory=list)  # (agg name, op, number)
    order: list[str] = field(default_factory=list)              # output column names, in column order
    supported: bool = True
    reason: str = ""


def _agg_parts(node: exp.Expression) -> tuple[str, str, str | None] | None:
    kind = KINDS.get(type(node))
    if kind is None:
        return None
    arg = node.this
    if isinstance(arg, exp.Distinct):
        return None
    if kind == "count":
        if arg is None or isinstance(arg, exp.Star):
            return kind, "1", None
        return kind, f"CASE WHEN ({arg.sql('sqlite')}) IS NOT NULL THEN 1 ELSE 0 END", None
    a = arg.sql("sqlite")
    if kind == "avg":
        return kind, f"COALESCE(({a}), 0)", f"CASE WHEN ({a}) IS NOT NULL THEN 1 ELSE 0 END"
    if kind == "sum":
        return kind, f"COALESCE(({a}), 0)", None
    return kind, a, None


def plan_query(sql: str) -> Plan:
    tree = sqlglot.parse_one(sql, read="sqlite")
    tables = [t.name for t in tree.find_all(exp.Table)]
    plan = Plan(table=tables[0] if tables else "")
    if len(set(tables)) != 1 or tree.args.get("limit") or tree.find(exp.Join):
        plan.supported, plan.reason = False, "join or limit"
        return plan
    for select in tree.expressions:
        name = select.alias_or_name if isinstance(select, exp.Alias) else select.sql("sqlite")
        body = select.this if isinstance(select, exp.Alias) else select
        aggs = list(body.find_all(*KINDS))
        if not aggs:
            plan.keys.append((name, body.sql("sqlite")))
        elif len(aggs) == 1 and aggs[0] is body and _agg_parts(body):
            kind, num, den = _agg_parts(body)
            plan.aggs.append({"name": name, "kind": kind, "num": num, "den": den, "hidden": False,
                              "sql": body.sql("sqlite")})
        else:
            plan.supported, plan.reason = False, f"unsupported select {name}"
            return plan
        plan.order.append(name)
    plan.aggs.append({"name": "__rows", "kind": "count", "num": "1", "den": None, "hidden": True, "sql": "COUNT(*)"})
    where = tree.args.get("where")
    plan.where = where.this.sql("sqlite") if where else None
    having = tree.args.get("having")
    if having:
        for cmp in [having.this] if isinstance(having.this, tuple(OPS)) else list(having.this.find_all(*OPS)):
            agg = next((a for a in cmp.find_all(*KINDS)), None)
            num = next((n for n in cmp.find_all(exp.Literal) if not n.is_string), None)
            parts = _agg_parts(agg) if agg else None
            if parts is None or num is None or not isinstance(cmp.left, tuple(KINDS)):
                plan.supported, plan.reason = False, "unsupported HAVING"
                return plan
            match = next((a for a in plan.aggs if a["sql"] == agg.sql("sqlite")), None)
            if match is None:
                kind, n_, d_ = parts
                match = {"name": f"__having{len(plan.aggs)}", "kind": kind, "num": n_, "den": d_, "hidden": True,
                         "sql": agg.sql("sqlite")}
                plan.aggs.append(match)
            plan.having.append((match["name"], OPS[type(cmp)], float(num.this)))
    return plan


def project(conn: sqlite3.Connection, plan: Plan) -> dict[str, dict[str, Any]]:
    """Per document: group key, WHERE flag, and each aggregate's numerator/denominator."""
    cols = [f"({k}) AS k{i}" for i, (_n, k) in enumerate(plan.keys)]
    for j, a in enumerate(plan.aggs):
        cols.append(f"({a['num']}) AS n{j}")
        cols.append(f"({a['den'] or 'NULL'}) AS d{j}")
    w = f"CASE WHEN ({plan.where}) THEN 1 ELSE 0 END" if plan.where else "1"
    sql = f'SELECT doc_id, {w} AS w, {", ".join(cols)} FROM "{plan.table}"'
    out = {}
    for row in conn.execute(sql):
        doc, flag, rest = row[0], row[1], row[2:]
        key = tuple(rest[: len(plan.keys)])
        vals = rest[len(plan.keys):]
        out[str(doc)] = {"w": int(flag or 0), "key": key,
                         "num": [vals[2 * j] for j in range(len(plan.aggs))],
                         "den": [vals[2 * j + 1] for j in range(len(plan.aggs))]}
    return out


def _f(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _var(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def estimate(plan: Plan, proxy: dict[str, dict], oracle: dict[str, dict], n_total: int) -> list[dict[str, Any]]:
    """Estimated result rows: {output name: value} plus '__ci' {name: (lo, hi)} and '__certified'."""
    sample = sorted(oracle)
    n, N = len(sample), n_total
    fpc = 1 - n / N
    groups = {r["key"] for r in proxy.values() if r["w"]} | {oracle[d]["key"] for d in sample if oracle[d]["w"]}

    def contrib(r: dict, g: tuple, j: int, part: str) -> float:
        if not r["w"] or r["key"] != g:
            return 0.0
        return _f(r[part][j]) if r[part][j] is not None else 0.0

    rows = []
    for g in sorted(groups, key=lambda t: tuple(str(x) for x in t)):
        cells, ci, certified = {}, {}, {}
        for j, a in enumerate(plan.aggs):
            if a["kind"] in ("min", "max"):
                vals = [_f(r["num"][j]) for r in proxy.values() if r["w"] and r["key"] == g and r["num"][j] is not None]
                cells[a["name"]] = (min(vals) if a["kind"] == "min" else max(vals)) if vals else None
                certified[a["name"]] = False
                continue
            tot = {}
            diffs = {}
            for part in ("num", "den") if a["kind"] == "avg" else ("num",):
                base = sum(contrib(r, g, j, part) for r in proxy.values())
                d = [contrib(oracle[s], g, j, part) - contrib(proxy[s], g, j, part) for s in sample if s in proxy]
                tot[part] = base + (N / n) * sum(d) if n else base
                diffs[part] = d
            if a["kind"] == "avg":
                if tot["den"] <= 0:
                    cells[a["name"]] = None
                    continue
                r_hat = tot["num"] / tot["den"]
                e = [dn - r_hat * dd for dn, dd in zip(diffs["num"], diffs["den"])]
                se = N * math.sqrt(max(0.0, fpc * _var(e) / n)) / tot["den"] if n else 0.0
                cells[a["name"]] = r_hat
            else:
                se = N * math.sqrt(max(0.0, fpc * _var(diffs["num"]) / n)) if n else 0.0
                cells[a["name"]] = max(0.0, tot["num"]) if a["kind"] == "count" else tot["num"]
            ci[a["name"]] = (cells[a["name"]] - Z95 * se, cells[a["name"]] + Z95 * se)
            certified[a["name"]] = True
        if (cells.get("__rows") or 0) < 0.5:
            continue
        if any(cells.get(name) is None or not op(cells[name], value) for name, op, value in plan.having):
            continue
        row = {name: v for (name, _), v in zip(plan.keys, g)}
        for a in plan.aggs:
            if not a["hidden"]:
                v = cells.get(a["name"])
                row[a["name"]] = int(round(v)) if a["kind"] == "count" and v is not None else v
        row["__ci"] = {k: v for k, v in ci.items() if not k.startswith("__")}
        row["__certified"] = {k: v for k, v in certified.items() if not k.startswith("__")}
        rows.append(row)
    return rows
