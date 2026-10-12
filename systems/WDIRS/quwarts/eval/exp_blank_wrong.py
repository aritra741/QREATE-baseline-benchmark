"""Blank against wrong, controlled: take a run's final table, pick 20% of the correct answers in every column the
test queries use, and make two copies of the table: in one those answers are blanked, in the other they are replaced
by a wrong value taken from another row of the same column.  Every test query is scored on the clean table and on
both damaged copies; the score losses are compared by what the query does with the column.  No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_blank_wrong cspaper V3-ablate-itemfilter <scratch dir>
"""

from __future__ import annotations

import json
import random
import re
import shutil
import sqlite3
import statistics as S
import sys
from collections import defaultdict
from pathlib import Path

from quwarts.core.adapt import catalogue as K
from quwarts.core.represent import Config, build
from quwarts.core.router.comparator import is_null
from quwarts.core.router.context_probe import FieldSpec
from quwarts.eval import drift_live as D
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_cause import CauseScorer, fields_of, final_view, write_column
from quwarts.eval.exp_open import correct

RATE = 0.2
EXP = Path(__file__).resolve().parents[4] / "results" / "experiments"


def features(sql: str) -> list[str]:
    """What a query does, in the terms the comparison is reported in."""
    u = " ".join(sql.upper().split())
    f = []
    if " JOIN " in u:
        f.append("join")
    if "GROUP BY" in u:
        f.append("group by")
    if re.search(r"\bCOUNT\s*\(\s*\*\s*\)", u):
        f.append("count rows")
    if re.search(r"\bCOUNT\s*\(\s*(DISTINCT\s+)?[A-Z_\.\"]+\s*\)", u):
        f.append("count a column's values")
    if re.search(r"\b(AVG|SUM|MAX|MIN)\s*\(", u):
        f.append("sum, average, min or max")
    where = u.split(" WHERE ", 1)[1] if " WHERE " in u else ""
    where = where.split(" GROUP BY ")[0]
    if where:
        if re.search(r"<>|!=|\bNOT\b", where):
            f.append("filter: not equal")
        if re.search(r"(?<![<>!])=|\bIN\s*\(|\bLIKE\b", where):
            f.append("filter: equal or contains")
        if re.search(r"(?<![<>])[<>](?![>=])|<=|>=", where.replace("<>", "")):
            f.append("filter: greater or less")
    return f or ["plain select"]


def main(argv=None) -> int:
    c, run, sp = (argv or sys.argv[1:])[:3]
    sp = Path(sp)
    R = D.R
    ctx = R.context(c)
    fields = fields_of(c)
    st = json.loads((EXP / run / "live" / c / "state" / "fixed4-attribute_pool_100.json").read_text())
    for t, plan in st.get("frozen", {}).items():
        fields = {**fields, **{k: FieldSpec(**{**v, "choices": tuple(v["choices"])}) for k, v in plan["fields"].items()}}
    src = final_view(c, run, 100, sp / "fv" / f"{c}_{run}").with_name("all.db")
    out = sp / "bw" / c
    out.mkdir(parents=True, exist_ok=True)
    tests = list(dict.fromkeys(json.loads((EXP.parent / "drift_live_ollama" / c / "fixed4_attribute_pool_design.json").read_text())["test"]))
    used = defaultdict(set)  # table -> columns the test queries mention
    con = sqlite3.connect(src)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for q in tests:
        sql = ctx.catalog[q]
        for t in tables:
            if re.search(rf"\b{re.escape(t)}\b", sql):
                for col in [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]:
                    if col != "doc_id" and re.search(rf"\b{re.escape(col)}\b", sql):
                        used[t].add(col)
    gold = gold_by_doc(c)
    rng = random.Random(7)
    # start from a table holding the gold answers in every column the test queries use, so every damaged cell was
    # truly right (the run's own table mixes forms the query scorer counts as wrong)
    gsrc = out / "gold.db"
    shutil.copy2(src, gsrc)
    for t, cols in used.items():
        docs = [r[0] for r in con.execute(f'SELECT doc_id FROM "{t}"')]
        for col in cols:
            vals = {}
            for d in docs:
                g = (gold.get(t, {}).get(d) or gold.get(t, {}).get(str(d).rsplit(".", 1)[0]) or {})
                if col in g:
                    vals[d] = None if is_null(g[col]) else g[col]
            if vals:
                write_column(gsrc, t, col, vals)
    con.close()
    src = gsrc
    con = sqlite3.connect(src)
    blank_db, wrong_db = out / "blank.db", out / "wrong.db"
    shutil.copy2(src, blank_db)
    shutil.copy2(src, wrong_db)
    n_cells = 0
    for t, cols in used.items():
        rows = con.execute(f'SELECT doc_id, {", ".join(chr(34) + x + chr(34) for x in sorted(cols))} FROM "{t}"').fetchall()
        for i, col in enumerate(sorted(cols), start=1):
            right = []
            for r in rows:
                d, v = r[0], r[i]
                g = (gold.get(t, {}).get(d) or gold.get(t, {}).get(str(d).rsplit(".", 1)[0]) or {}).get(col)
                if not is_null(v) and not is_null(g) and correct(v, g):
                    right.append((d, v, g))
            pool = [r[i] for r in rows if not is_null(r[i])]
            chosen = rng.sample(right, int(len(right) * RATE)) if len(right) >= 5 else []
            blanks, wrongs = {}, {}
            for d, v, g in chosen:
                alts = [x for x in pool if K.norm(x) != K.norm(v) and not correct(x, g)]
                if not alts:
                    continue
                blanks[d] = None
                wrongs[d] = rng.choice(alts)
            if blanks:
                write_column(blank_db, t, col, blanks)
                write_column(wrong_db, t, col, wrongs)
                n_cells += len(blanks)
    scorer = CauseScorer(c, out / "scores.json")
    res = {}
    for name, db in (("clean", src), ("blank", blank_db), ("wrong", wrong_db)):
        view = out / f"{name}.view.db"
        if view.exists():
            view.unlink()
        build(db, view, ctx.spec, fields, dict(ctx.catalog), Config(t0=True))
        items = [(q, R.digest(view, ctx.catalog[q]), view) for q in tests]
        scorer.run(items, lambda: False)
        scorer.save()
        res[name] = {q: scorer.get("benchmark", q, dg) or 0.0 for q, dg, _ in items}
    per_query = {q: {"features": features(ctx.catalog[q]), "clean": res["clean"][q],
                     "blank_loss": round(res["clean"][q] - res["blank"][q], 4),
                     "wrong_loss": round(res["clean"][q] - res["wrong"][q], 4)} for q in tests}
    summary = {"corpus": c, "run": run, "rate": RATE, "cells_damaged": n_cells, "queries": len(tests),
               "mean_score": {k: round(S.mean(v.values()), 4) for k, v in res.items()}, "by_feature": {}}
    byf = defaultdict(list)
    for q, v in per_query.items():
        for f in v["features"]:
            byf[f].append(v)
    for f, vs in sorted(byf.items()):
        summary["by_feature"][f] = {"queries": len(vs), "blank_loss": round(S.mean(v["blank_loss"] for v in vs), 4),
                                    "wrong_loss": round(S.mean(v["wrong_loss"] for v in vs), 4),
                                    "blank_hurts_more": sum(v["blank_loss"] > v["wrong_loss"] + 1e-9 for v in vs),
                                    "wrong_hurts_more": sum(v["wrong_loss"] > v["blank_loss"] + 1e-9 for v in vs)}
    dest = EXP / "WHY" / "blank_wrong"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{c}.json").write_text(json.dumps({**summary, "per_query": per_query}, indent=1))
    print(c, "RESULT", json.dumps({k: summary[k] for k in ("cells_damaged", "mean_score")}))
    for f, v in summary["by_feature"].items():
        print(f"  {f:28s} n={v['queries']:3d} blank loss {v['blank_loss']:+.3f}  wrong loss {v['wrong_loss']:+.3f}  blank worse in {v['blank_hurts_more']}, wrong worse in {v['wrong_hurts_more']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
