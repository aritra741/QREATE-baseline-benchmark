"""Why aggregates differ: group size.  For each test query, the number of rows behind each result value in the
correct data (the query's FROM/WHERE/GROUP BY with every aggregate replaced by COUNT(*), run on the gold tables), and
the query's value score (cell F1) at 0% and 20% for our system.  Prediction: an exact COUNT(*), COUNT(column) or SUM
needs every row right, so its 0% score falls as groups grow; AVG at 20% forgives one wrong row in a large group, so
it rises; MIN/MAX depends on one row and moves least.  No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_groupsize
"""

from __future__ import annotations

import json
import statistics as S
from collections import defaultdict

import sqlglot
from sqlglot import exp

from quwarts.eval import drift_live as D
from quwarts.eval.exp_aggtype import agg_class
from quwarts.eval.exp_tau import EXP

CORPORA = ["cspaper", "player", "art", "med", "legal"]
BINS = ((1, 2, "1-2 rows"), (3, 9, "3-9 rows"), (10, 49, "10-49 rows"), (50, 10**9, "50+ rows"))


def group_sizes(sql: str, gold_conn) -> list[int]:
    tree = sqlglot.parse_one(sql, read="sqlite")
    sel = tree.find(exp.Select)
    groups = [g.sql(dialect="sqlite") for g in (sel.args.get("group").expressions if sel.args.get("group") else [])]
    sel.set("expressions", [exp.alias_(exp.Count(this=exp.Star()), "n")] + [sqlglot.parse_one(g, read="sqlite") for g in groups])
    for k in ("order", "limit", "having"):
        sel.set(k, None)
    try:
        return [int(r[0]) for r in gold_conn.execute(sel.sql(dialect="sqlite")).fetchall()]
    except Exception:
        return []


def main() -> int:
    from spp.config_grid import _build_in_memory_db

    rows = []
    for c in CORPORA:
        pq = json.loads((EXP / "WHY" / "tau" / f"{c}_per_query.json").read_text())
        ctx = D.R.context(c)
        gold, _ = D.R.Scorer(c).gold()
        conn = _build_in_memory_db(gold)
        ours = pq["our system"]
        for q in pq["DocETL"]["DocETL"]:
            sizes = group_sizes(ctx.catalog[q], conn)
            if not sizes:
                continue
            cell = lambda t: S.mean(r[q]["cell"].get(str(t), r[q]["cell"].get(t)) for r in ours.values())  # noqa: E731
            rows.append({"corpus": c, "qid": q, "class": agg_class(ctx.catalog[q])["class"], "median_group": S.median(sizes),
                         "groups": len(sizes), "values_0": cell(0.0), "values_20": cell(0.2),
                         "structure": S.mean(r[q]["structure"] for r in ours.values())})
        conn.close()
    out = {}
    for cl in ("COUNT(*)", "COUNT(column)", "SUM", "AVG", "MIN/MAX"):
        sel = [r for r in rows if r["class"] == cl]
        out[cl] = {}
        for lo, hi, lab in BINS:
            b = [r for r in sel if lo <= r["median_group"] <= hi]
            if b:
                out[cl][lab] = {"queries": len(b), "values right at 0%": round(S.mean(r["values_0"] for r in b), 3),
                                "values right at 20%": round(S.mean(r["values_20"] for r in b), 3),
                                "rows and groups right": round(S.mean(r["structure"] for r in b), 3),
                                "corpora": dict(sorted({r["corpus"]: sum(x["corpus"] == r["corpus"] for x in b) for r in b}.items()))}
    dest = EXP / "WHY" / "groupsize"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps({"by_class_and_group_size": out, "queries": rows}, indent=1))
    for cl, bins in out.items():
        print("==", cl)
        for lab, v in bins.items():
            print(f"   {lab:11s} n={v['queries']:3d}  values@0 {v['values right at 0%']:.2f}  values@20 {v['values right at 20%']:.2f}  rows/groups {v['rows and groups right']:.2f}  {v['corpora']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
