"""The query-side findings re-checked on the realistic workload (WHY/realistic/<corpus>.json from exp_realistic_eval).

  1. scores at 0/5/10/20% per collection and system, and by query shape (one number, or a grouped table);
  2. exactness by aggregate and group size (rows behind each result value in the correct data);
  3. which column decides: a query's score against the exact accuracy of its weakest grouping and aggregated column
     (our system's final table of the first replicate), within collections;
  4. joins: scores of join queries against the share of rows whose join key finds a match.
No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_realistic_why
"""

from __future__ import annotations

import json
import sqlite3
import statistics as S
from collections import defaultdict

import sqlglot
from sqlglot import exp

from quwarts.core.router.comparator import is_null
from quwarts.eval import drift_live as D
from quwarts.eval.exp_aggtype import agg_class
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_groupsize import group_sizes
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_profile import roles
from quwarts.eval.exp_realistic_eval import KEY, QVIEWS
from quwarts.eval.exp_tau import EXP
from quwarts.eval.exp_why import spearman
from quwarts.eval.realistic_queries import register

CORPORA = ["cspaper", "player", "art", "med", "legal"]
TK = ("0.0", "0.05", "0.1", "0.2")


def mean_over_runs(runs: dict, q: str, key: str) -> float | None:
    vals = [o[q][key] if key in o[q] else o[q]["cell"][key] for o in runs.values() if q in o]
    return S.mean(vals) if vals else None


def main() -> int:
    from spp.config_grid import _build_in_memory_db

    out = {"scores": {}, "by_shape": {}, "groupsize": defaultdict(list), "roles": {}, "joins": {}}
    rows_gs = []
    for c in CORPORA:
        f = EXP / "WHY" / "realistic" / f"{c}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text())
        ctx = D.R.context(c)
        register(ctx, c)
        pq = d["per_query"]
        systems = {k: v for k, v in pq.items() if v}
        common = set.intersection(*[set.intersection(*[set(o) for o in runs.values()]) for runs in systems.values()]) if systems else set()
        out["scores"][c] = {"queries": len(common), **{name: {t: round(S.mean(mean_over_runs(runs, q, t) for q in common), 4) for t in TK}
                                                       for name, runs in systems.items()}}
        gold, _ = D.R.Scorer(c).gold()
        gconn = _build_in_memory_db(gold)
        shape = defaultdict(lambda: defaultdict(list))
        ours_name = "our system" if "our system" in systems else "our system (no re-reads)"
        for q in common:
            sql = ctx.catalog[q]
            sizes = group_sizes(sql, gconn)
            one = len(sizes) <= 1 and sqlglot.parse_one(sql, read="sqlite").find(exp.Group) is None
            for name, runs in systems.items():
                shape["one number" if one else "grouped table"][name].append(mean_over_runs(runs, q, "0.2"))
            if sizes and ours_name in systems:
                rows_gs.append({"corpus": c, "qid": q, "class": agg_class(sql)["class"], "median_group": S.median(sizes),
                                "values_0": mean_over_runs(systems[ours_name], q, "0.0") if False else S.mean(o[q]["cell"]["0.0"] for o in systems[ours_name].values() if q in o),
                                "score_20": mean_over_runs(systems[ours_name], q, "0.2"), "one_number": one})
        out["by_shape"][c] = {s: {name: {"queries": len(v), "score_20": round(S.mean(v), 3)} for name, v in m.items()} for s, m in shape.items()}
        # column accuracy on the first replicate's final view
        runs = systems.get(ours_name, {})
        if runs:
            run = sorted(runs)[0]
            views = sorted((QVIEWS / run / c / KEY).glob("*.db"))
            if views:
                con = sqlite3.connect(views[-1])
                gdoc = gold_by_doc(c)
                acc = {}

                def col_acc(col):
                    if col in acc:
                        return acc[col]
                    t, a = col.split(".", 1)
                    ok = []
                    try:
                        for dd, v in con.execute(f'SELECT doc_id, "{a}" FROM "{t}"'):
                            g = gdoc.get(t, {}).get(str(dd)) or gdoc.get(t, {}).get(str(dd).rsplit(".", 1)[0])
                            if g is None or a not in g:
                                continue
                            gv = g[a]
                            ok.append((is_null(v) and is_null(gv)) or (not is_null(v) and not is_null(gv) and correct(v, gv, 0.0)))
                    except sqlite3.Error:
                        pass
                    acc[col] = sum(ok) / len(ok) if ok else None
                    return acc[col]

                res = {}
                for role in ("grouped by", "aggregated", "filtered on"):
                    xs, ys = [], []
                    for q in common:
                        cols = roles(ctx.catalog[q])[role]
                        a = [col_acc(x) for x in cols]
                        a = [x for x in a if x is not None]
                        if a:
                            xs.append(min(a)); ys.append(mean_over_runs(runs, q, "0.2"))
                    res[role] = {"queries": len(xs), "rank_correlation": round(spearman(xs, ys), 3) if len(xs) >= 6 and len(set(xs)) > 2 else None}
                out["roles"][c] = res
                joins = [q for q in common if roles(ctx.catalog[q])["join key"]]
                if joins:
                    out["joins"][c] = {"queries": len(joins), **{name: round(S.mean(mean_over_runs(rr, q, "0.2") for q in joins), 3) for name, rr in systems.items()},
                                       "non_join_queries": {name: round(S.mean(mean_over_runs(rr, q, "0.2") for q in common - set(joins)), 3) for name, rr in systems.items()}}
        gconn.close()
    bins = ((1, 2, "1-2"), (3, 9, "3-9"), (10, 49, "10-49"), (50, 10**9, "50+"))
    for fam, cls in (("COUNT, SUM or AVG", ("COUNT(*)", "COUNT(column)", "SUM", "AVG")), ("MIN or MAX", ("MIN/MAX",))):
        for lo, hi, lab in bins:
            b = [r["values_0"] for r in rows_gs if r["class"] in cls and lo <= r["median_group"] <= hi]
            if b:
                out["groupsize"][fam].append({"rows": lab, "queries": len(b), "values_exact": round(S.mean(b), 3)})
    dest = EXP / "WHY" / "realistic"
    (dest / "why_summary.json").write_text(json.dumps({**out, "groupsize": dict(out["groupsize"]), "queries": rows_gs}, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "queries"}, indent=1, default=dict))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
