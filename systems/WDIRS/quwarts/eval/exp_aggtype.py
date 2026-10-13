"""Query scores by aggregation type, per collection and tolerance (from WHY/tau/<corpus>_per_query.json).

Each test query is classed by the aggregates it computes: COUNT(*) (rows), COUNT(column) or COUNT(DISTINCT column)
(values present), SUM, AVG, MIN/MAX, or "several kinds". For each class: number of queries, the score at 0/5/10/20%,
and its two factors, structure F2 (the right groups and rows) and cell F1 (the right numbers in them), for our system
(mean of runs), our system without re-reads, and DocETL. No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_aggtype
"""

from __future__ import annotations

import json
import statistics as S
from collections import defaultdict

import sqlglot
from sqlglot import exp

from quwarts.eval import drift_live as D
from quwarts.eval.exp_tau import EXP, TAUS

CORPORA = ["cspaper", "player", "art", "med", "legal"]


def agg_class(sql: str) -> dict:
    tree = sqlglot.parse_one(sql, read="sqlite")
    kinds = set()
    for node in tree.find_all(exp.AggFunc):
        if isinstance(node, exp.Count):
            arg = node.this
            kinds.add("COUNT(*)" if arg is None or isinstance(arg, exp.Star) else "COUNT(column)")
        elif isinstance(node, exp.Sum):
            kinds.add("SUM")
        elif isinstance(node, exp.Avg):
            kinds.add("AVG")
        elif isinstance(node, (exp.Min, exp.Max)):
            kinds.add("MIN/MAX")
        else:
            kinds.add(type(node).__name__.upper())
    return {"class": next(iter(kinds)) if len(kinds) == 1 else ("several kinds" if kinds else "no aggregate"),
            "grouped": tree.find(exp.Group) is not None, "joins": len(list(tree.find_all(exp.Join)))}


def main() -> int:
    out = {}
    for c in CORPORA:
        f = EXP / "WHY" / "tau" / f"{c}_per_query.json"
        if not f.exists():
            continue
        pq = json.loads(f.read_text())
        ctx = D.R.context(c)
        docetl = pq["DocETL"]["DocETL"]
        common = set(docetl)
        systems = {"our system": pq.get("our system", {}), "our system without re-reads": pq.get("our system without re-reads", {}),
                   "DocETL": {"DocETL": docetl}}
        classes = defaultdict(list)
        for q in common:
            classes[agg_class(ctx.catalog[q])["class"]].append(q)
        res = {}
        for cl, qs in sorted(classes.items(), key=lambda x: -len(x[1])):
            row = {"queries": len(qs)}
            for name, runs in systems.items():
                def m(get):
                    return round(S.mean(S.mean(get(r[q]) for q in qs) for r in runs.values()), 3)
                row[name] = {**{f"{t:.0%}": m(lambda x, t=t: x[str(t)] if str(t) in x else x[t]) for t in TAUS},
                             "rows and groups right (structure)": m(lambda x: x["structure"]),
                             **{f"values right at {t:.0%} (cell)": m(lambda x, t=t: x["cell"][str(t)] if str(t) in x["cell"] else x["cell"][t]) for t in (0.0, 0.2)}}
            res[cl] = row
        out[c] = res
    dest = EXP / "WHY" / "aggtype"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1))
    for c, res in out.items():
        print("==", c)
        for cl, row in res.items():
            o, d = row["our system"], row["DocETL"]
            print(f"  {cl:15s} n={row['queries']:3d}  ours 0/5/10/20: {o['0%']:.3f} {o['5%']:.3f} {o['10%']:.3f} {o['20%']:.3f}"
                  f"  struct {o['rows and groups right (structure)']:.2f} cell0 {o['values right at 0% (cell)']:.2f} cell20 {o['values right at 20% (cell)']:.2f}"
                  f"  | DocETL 20%: {d['20%']:.3f} struct {d['rows and groups right (structure)']:.2f} cell20 {d['values right at 20% (cell)']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
