"""Quantitative check of the group-size mechanism: an exact COUNT, SUM or AVG needs every row behind the value right.

For each single-table test query of our system (run V3's final served table): p = share of the table's rows whose
values in every column the query uses equal the correct ones exactly (case ignored; numbers exactly); n = rows behind
each result value in the correct data (exp_groupsize); predicted exact share = mean over result values of p^n. Compared
with the observed value score at 0% (cell F1@0), binned by the prediction. MIN/MAX is reported apart (only the extreme
row must be right). No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_pn <served tables dir>
"""

from __future__ import annotations

import json
import sqlite3
import statistics as S
import sys
from pathlib import Path

import sqlglot
from sqlglot import exp

from quwarts.core.router.comparator import is_null
from quwarts.eval import drift_live as D
from quwarts.eval.exp_aggtype import agg_class
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_groupsize import group_sizes
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_tau import EXP

CORPORA = ["cspaper", "player", "art", "med", "legal"]
BINS = ((0.0, 0.05, "below 0.05"), (0.05, 0.2, "0.05-0.2"), (0.2, 0.5, "0.2-0.5"), (0.5, 1.01, "0.5-1"))


def main(argv=None) -> int:
    from spp.config_grid import _build_in_memory_db

    fv = Path((argv or sys.argv[1:])[0])
    rows = []
    for c in CORPORA:
        pq = json.loads((EXP / "WHY" / "tau" / f"{c}_per_query.json").read_text())["our system"]["V3"]
        ctx = D.R.context(c)
        gold, _ = D.R.Scorer(c).gold()
        gconn = _build_in_memory_db(gold)
        gdoc = gold_by_doc(c)
        con = sqlite3.connect(fv / f"{c}_V3" / "served.db")
        for q, sc in pq.items():
            sql = ctx.catalog[q]
            tree = sqlglot.parse_one(sql, read="sqlite")
            tables = {t.name for t in tree.find_all(exp.Table)}
            if len(tables) != 1:
                continue
            t = next(iter(tables))
            cols = sorted({x.name for x in tree.find_all(exp.Column)} - {"doc_id"})
            have = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
            cols = [x for x in cols if x in have]
            if not cols:
                continue
            ok = []
            for row in con.execute(f'SELECT doc_id, {", ".join(chr(34) + x + chr(34) for x in cols)} FROM "{t}"'):
                g = gdoc.get(t, {}).get(str(row[0])) or gdoc.get(t, {}).get(str(row[0]).rsplit(".", 1)[0])
                if g is None:
                    continue
                ok.append(all((is_null(v) and is_null(g.get(a))) or (not is_null(v) and not is_null(g.get(a)) and correct(v, g.get(a), 0.0))
                              for a, v in zip(cols, row[1:])))
            sizes = group_sizes(sql, gconn)
            if not ok or not sizes:
                continue
            p = sum(ok) / len(ok)
            rows.append({"corpus": c, "qid": q, "class": agg_class(sql)["class"], "p": round(p, 3),
                         "median_group": S.median(sizes), "predicted": round(S.mean(p ** n for n in sizes), 4),
                         "observed": sc["cell"].get("0.0", sc["cell"].get(0.0))})
        con.close()
        gconn.close()
    out = {}
    for name, sel in (("COUNT, SUM, AVG", [r for r in rows if r["class"] in ("COUNT(*)", "COUNT(column)", "SUM", "AVG")]),
                      ("MIN/MAX", [r for r in rows if r["class"] == "MIN/MAX"])):
        out[name] = {"queries": len(sel)}
        if len(sel) > 3:
            xs, ys = [r["predicted"] for r in sel], [r["observed"] for r in sel]
            from quwarts.eval.exp_why import spearman
            out[name]["rank_correlation_predicted_observed"] = round(spearman(xs, ys), 3)
        for lo, hi, lab in BINS:
            b = [r for r in sel if lo <= r["predicted"] < hi]
            if b:
                out[name][lab] = {"queries": len(b), "predicted": round(S.mean(r["predicted"] for r in b), 3),
                                  "observed": round(S.mean(r["observed"] for r in b), 3)}
    dest = EXP / "WHY" / "pn"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps({"bins": out, "queries": rows}, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
