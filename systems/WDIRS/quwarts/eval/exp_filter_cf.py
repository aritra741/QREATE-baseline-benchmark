"""Counterfactual for the item filter on one corpus: the no-filter run's final table, the same table with the
filter as shipped (empties a cell when no item is stated), and with a never-empty variant; every test query scored."""
import json, shutil, sqlite3, statistics as S, sys
from pathlib import Path
from collections import defaultdict
from quwarts.eval import drift_live as D
from quwarts.eval.exp_cause import CauseScorer, write_column, fields_of, operators, final_view
from quwarts.core.adapt import catalogue as K
from quwarts.core.represent import Config, build
from quwarts.core.router.context_probe import FieldSpec
from quwarts.core.router.corpus_features import read_document
from quwarts.core.router.comparator import is_null

c, run, sp = sys.argv[1], sys.argv[2], Path(sys.argv[3])
R = D.R; ctx = R.context(c); EXP = Path("../../results/experiments")
st = json.load(open(EXP / run / "live" / c / "state/fixed4-attribute_pool_100.json"))
fields = fields_of(c)
for t, plan in st["frozen"].items():
    fields = {**fields, **{k: FieldSpec(**{**v, "choices": tuple(v["choices"])}) for k, v in plan["fields"].items()}}
src = final_view(c, run, 100, sp / "fv" / f"{c}_{run}").with_name("all.db")
out = sp / "fv" / f"{c}_cf"; out.mkdir(parents=True, exist_ok=True)
con = sqlite3.connect(src)
dbs = {"nofilter": src}
for variant in ("filter", "keep"):
    db = out / f"{variant}.db"; shutil.copy2(src, db); n = e = 0
    for t, plan in st["frozen"].items():
        for col, s in plan["stats"].items():
            a = col.split(".", 1)[1]
            if s.get("kind") != "list" or not s.get("item_filter"):
                continue
            new = {}
            for d, v in con.execute(f'SELECT doc_id, "{a}" FROM "{t}"').fetchall():
                if is_null(v) or d not in ctx.docs[t]:
                    continue
                nv = K.filter_list_items(v, read_document(Path(ctx.docs[t][d])).lower())
                if nv is None and variant == "keep":
                    continue
                if K.norm(nv) != K.norm(v):
                    new[d] = nv; n += 1; e += nv is None
            if new:
                write_column(db, t, a, new)
    print(c, variant, "cells changed", n, "emptied", e)
    dbs[variant] = db
tests = list(dict.fromkeys(json.load(open(EXP.parent / "drift_live_ollama" / c / "fixed4_attribute_pool_design.json"))["test"]))
scorer = CauseScorer(c, out / "scores.json"); res = {}
for name, db in dbs.items():
    view = out / f"{name}.view.db"
    if view.exists():
        view.unlink()
    build(db, view, ctx.spec, fields, dict(ctx.catalog), Config(t0=True))
    items = [(q, R.digest(view, ctx.catalog[q]), view) for q in tests]
    scorer.run(items, lambda: False); scorer.save()
    res[name] = {q: scorer.get("benchmark", q, dg) or 0 for q, dg, _ in items}
print(c, "RESULT", {k: round(S.mean(v.values()), 4) for k, v in res.items()})
