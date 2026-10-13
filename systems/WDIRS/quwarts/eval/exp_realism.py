"""Realism audit of the test queries: would a real user ask this?  Explicit rules, each tied to the column's meaning.

  R1 sum or average of a non-additive number: SUM of an age, a draft pick, a year; AVG of a year
     (AVG of an age or a draft pick is kept: "average age per team" is a real question)
  R2 SUM or AVG of a column that is not a number (MIN or MAX of a year or an amount stored as text is a real question)
  R3 a joined table that the query does not use beyond the join condition (no selected, grouped or filtered column)
  R4 grouping by an identifier-like column (90% or more of its correct values distinct per row, e.g. a name or a
     one-off free-text status) whose groups hold one row in the correct data: the aggregate aggregates nothing
  R6 a filter that compares one column with both = and <> (e.g. nationality = 'Serbian' OR nationality <> 'Greek'):
     redundant or nearly always true, the trace of random predicate generation
  R5 an equality or IN filter on a long free-text or list literal (over 40 characters or containing '||'): a value no
     one types
Also reported, not counted as unrealistic: a result label that contradicts its expression (AVG(draft_pick) AS
avg_age), the trace of attribute substitution in the query generator; and joins without aggregation.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_realism
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

import sqlglot
from sqlglot import exp

from quwarts.eval import drift_live as D
from quwarts.eval.exp_context import fields_of
from quwarts.eval.exp_tau import EXP
from quwarts.eval.exp_transfer import kind_of

CORPORA = ["cspaper", "player", "art", "med", "legal"]
NO_SUM = {"age", "draft_pick", "draft_year", "founded_year"}
NO_AVG = {"draft_year", "founded_year"}


def audit(sql: str, fields: dict, distinct: dict, median_group: float | None = None) -> dict:
    tree = sqlglot.parse_one(sql, read="sqlite")
    alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
    tables = set(alias.values())
    single = next(iter(tables)) if len(tables) == 1 else None

    def full(c):
        return f"{alias.get(c.table, c.table) if c.table else single}.{c.name}"

    flags = []
    for agg in tree.find_all(exp.AggFunc):
        cols = list(agg.find_all(exp.Column))
        if isinstance(agg, exp.Count) or not cols or agg.find(exp.Case):
            continue
        for c in cols:
            f = fields.get(full(c))
            if isinstance(agg, exp.Sum) and c.name in NO_SUM:
                flags.append(f"R1 SUM({c.name})")
            if isinstance(agg, exp.Avg) and c.name in NO_AVG:
                flags.append(f"R1 AVG({c.name})")
            if f is not None and kind_of(f) != "number" and isinstance(agg, (exp.Sum, exp.Avg)):
                flags.append(f"R2 {type(agg).__name__.upper()}({c.name}) of {kind_of(f)}")
    if len(tables) > 1:
        used = defaultdict(int)
        join_cols = set()
        for j in tree.find_all(exp.Join):
            if j.args.get("on") is not None:
                join_cols |= {id(c) for c in j.args["on"].find_all(exp.Column)}
        for c in tree.find_all(exp.Column):
            if id(c) not in join_cols:
                used[alias.get(c.table, c.table) if c.table else single] += 1
        for t in tables:
            if not used.get(t):
                flags.append(f"R3 table {t} joined but unused")
    g = tree.find(exp.Group)
    if g is not None:
        for c in g.find_all(exp.Column):
            if distinct.get(full(c), 0) >= 0.9 and (median_group is None or median_group <= 1):
                flags.append(f"R4 grouped by identifier-like {c.name}")
    if w_ := tree.find(exp.Where):
        ops = defaultdict(set)
        for node in w_.find_all(exp.EQ, exp.NEQ):
            col = node.find(exp.Column)
            if col is not None:
                ops[full(col)].add(type(node).__name__)
        if any(len(v) == 2 for v in ops.values()):
            flags.append("R6 one column compared with both = and <>")
    w = tree.find(exp.Where)
    if w is not None:
        for node in list(w.find_all(exp.EQ)) + list(w.find_all(exp.In)):
            for lit in node.find_all(exp.Literal):
                if lit.is_string and (len(lit.this) > 40 or "||" in lit.this):
                    flags.append("R5 filter on a long literal")
                    break
    notes = []
    for a in tree.find_all(exp.Alias):
        inner = a.this
        if isinstance(inner, exp.AggFunc) and not isinstance(inner, exp.Count):
            cols = [c.name for c in inner.find_all(exp.Column)]
            if cols and not any(c.lower() in a.alias.lower() for c in cols):
                notes.append(f"label {a.alias} for {inner.sql()}")
    agg = tree.find(exp.AggFunc) is not None
    return {"unrealistic": sorted(set(flags)), "label_mismatch": notes, "joins": len(tables) - 1, "aggregates": agg}


def main() -> int:
    from quwarts.core.adapt import catalogue as K
    from quwarts.core.router.comparator import is_null
    from quwarts.eval.exp_analysis import gold_by_doc

    gs = {(r["corpus"], r["qid"]): r for r in json.loads((EXP / "WHY" / "groupsize" / "summary.json").read_text())["queries"]}
    out = {}
    for c in CORPORA:
        ctx = D.R.context(c)
        fields = fields_of(c)
        distinct = {}
        for t, rows_ in gold_by_doc(c).items():
            cols = {k for r in rows_.values() for k in r}
            for a in cols:
                vals = [K.norm(r.get(a)) for r in rows_.values() if not is_null(r.get(a))]
                if len(vals) >= 10:
                    distinct[f"{t}.{a}"] = len(set(vals)) / len(vals)
        tests = list(dict.fromkeys(json.loads((EXP.parent / "drift_live_ollama" / c / "fixed4_attribute_pool_design.json").read_text())["test"]))
        rows = []
        for q in tests:
            a = audit(ctx.catalog[q], fields, distinct, gs.get((c, q), {}).get("median_group"))
            rows.append({"qid": q, "generated_by_substitution": q.startswith("attr:"), **a, "sql": " ".join(ctx.catalog[q].split())})
        rules = Counter(f.split(" ")[0] for r in rows for f in r["unrealistic"])
        out[c] = {"queries": len(rows), "unrealistic": sum(bool(r["unrealistic"]) for r in rows),
                  "by_rule": dict(sorted(rules.items())),
                  "label_mismatch": sum(bool(r["label_mismatch"]) for r in rows),
                  "generated_by_substitution": sum(r["generated_by_substitution"] for r in rows),
                  "unrealistic_among_substituted": sum(bool(r["unrealistic"]) for r in rows if r["generated_by_substitution"]),
                  "unrealistic_among_original": sum(bool(r["unrealistic"]) for r in rows if not r["generated_by_substitution"]),
                  "joins_without_aggregation": sum(r["joins"] > 0 and not r["aggregates"] for r in rows),
                  "realistic_queries": [r["qid"] for r in rows if not r["unrealistic"]],
                  "rows": rows}
    dest = EXP / "WHY" / "realism"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1))
    for c, v in out.items():
        print(c, {k: v[k] for k in ("queries", "unrealistic", "by_rule", "label_mismatch", "generated_by_substitution",
                                    "unrealistic_among_substituted", "unrealistic_among_original", "joins_without_aggregation")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
