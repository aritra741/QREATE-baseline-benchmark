"""Three free checks. (1) cost law: patch tokens per stream vs unseen feature mass; (2) shape transfer: share of
drifted equality literals whose Potter's-Wheel shape is among W0's literal shapes for that column; (3) scope
soundness: documents pruned by pushdown on raw values vs on the online representation, and wrongly pruned ones."""
import json, sys, logging, sqlite3
from collections import Counter, defaultdict
logging.disable(logging.INFO)
from quwarts.eval import drift_run as R
from quwarts.core.adapt import controller as C
from quwarts.core.represent.grammar import shape, grammar
from quwarts.eval.tolerant_score import cell

corpus = sys.argv[1]
ctx = R.context(corpus)
lean = {(r.table, a) for r in ctx.lean_reads for a in r.attributes}
out = {"corpus": corpus}

# (1) cost law: per stream (all axes, levels, seeds), P1 patch tokens and characterization
sys.argv = [sys.argv[0], corpus]
pol = open(__file__.replace("checks.py", "policies.py")).read().split("out = {")[0]
exec(pol)
law = []
for s in R.SEEDS:
    d = ctx.designs[s]
    for key, st in d["streams"].items():
        ch = d["characterization"][key]
        tok, _ = run(st, "P1")
        law.append({"stream": f"s{s}/{key}", "tokens": tok, "unseen_feature_mass": ch["unseen_feature_mass"],
                    "attribute_novel": ch["attribute_novel"], "constant_novel": ch["constant_novel"], "n": len(st)})
out["law"] = law

# (2) shape transfer, value-drift literals vs W0 literals per column
uses0 = grammar(ctx.spec, ctx.w0)
shapes0 = {k: set(u.shapes) for k, u in uses0.items()}
hit = tot = 0; per = defaultdict(lambda: [0, 0]); novel_hit = novel_tot = 0
for q in ctx.designs[0]["value_pool"]:
    lits = ctx.records[q]["literals"]
    for col, vals in lits.items():
        t, a = col.split(".", 1) if "." in col else (None, col)
        key = next((k for k in shapes0 if k[1] == a and (t is None or k[0] == t)), None)
        for v in vals:
            if key is None or not (shapes0.get(key) or uses0[key].like):
                continue
            fam = shapes0[key] | {shape(c) for c in uses0[key].like}  # LIKE cores are literals too
            like = str(v).startswith("~")  # a LIKE core under LOWER(): case-folded, so compare case-folded shapes
            fold = lambda s: s.replace("Aa", "a").replace("A", "a") if like else s
            for part in [x.strip().lstrip("~") for x in str(v).split("||") if x.strip()]:  # list literals: one shape per part
                tot += 1; per[col][1] += 1
                ok = fold(shape(part)) in {fold(s) for s in fam}
                hit += ok; per[col][0] += ok
                if part not in uses0[key].equality:  # a constant W0 never used
                    novel_tot += 1; novel_hit += ok
out["shape_transfer"] = {"literals": tot, "in_w0_shape_family": round(hit / max(1, tot), 3),
                         "novel_literals": novel_tot, "novel_in_family": round(novel_hit / max(1, novel_tot), 3),
                         "per_column": {c: f"{h}/{n}" for c, (h, n) in per.items()}}

# (3) scope soundness: pushdown on raw values vs represented values, on value-drift queries with a new column
from quwarts.core.represent import Config, build
raw = R.fixed_db(corpus, "robust_raw")
view = ctx.scratch / "checks_view.db"
w1 = {q: ctx.catalog[q] for q in ctx.designs[0]["value_pool"]}
build(raw, view, ctx.spec, ctx.fields, {**ctx.w0, **w1}, Config())
gold_scope = None
res = {"queries": 0, "raw_pruned": 0, "rep_pruned": 0, "raw_prunes_everything": 0, "rep_prunes_everything": 0,
       "raw_pruned_docs_kept_by_rep": 0, "rep_pruned_docs_kept_by_raw": 0}
for q in w1:
    need = ctx.records[q]["attributes"]
    if len(need) != 1:
        continue
    t = next(iter(need))
    known = {a for (tt, a) in lean if tt == t}
    cond = C.pushdown_conjuncts(ctx.catalog[q], t, known)
    if not cond:
        continue
    sr = C.evaluate_scope(raw, t, cond); sv = C.evaluate_scope(view, t, cond)
    if sr is None or sv is None:
        continue
    n = len(ctx.names[t])
    res["queries"] += 1
    res["raw_pruned"] += n - len(sr); res["rep_pruned"] += n - len(sv)
    res["raw_prunes_everything"] += len(sr) == 0; res["rep_prunes_everything"] += len(sv) == 0
    res["raw_pruned_docs_kept_by_rep"] += len(sv - sr); res["rep_pruned_docs_kept_by_raw"] += len(sr - sv)
res["docs_per_table"] = {t: len(v) for t, v in ctx.names.items()}
out["scope"] = res
print(json.dumps(out))
