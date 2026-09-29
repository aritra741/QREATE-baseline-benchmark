"""Where the patch tokens go under the per-query-description protocol (cost model only, no calls).

Protocol: the build reads W0's columns. A query that needs a column the system lacks gets that column's
description and patches it: the documents in the query's scope (pushdown of its WHERE conjuncts over
complete columns) that lack it are read again, with only the query's missing columns in the prompt.
Nothing is rebuilt. Costs are the controller's estimates (Costs.read)."""
import json, sys, logging, re
from collections import defaultdict, Counter
from pathlib import Path
logging.disable(logging.INFO)
from quwarts.eval import drift_run as R
from quwarts.core.adapt import controller as C
from quwarts.eval.tolerant_score import cell
from quwarts.core.router.corpus_features import read_document

corpus = sys.argv[1]
ctx = R.context(corpus)
robust_db = R.fixed_db(corpus, "robust_raw")
lean = {(r.table, a) for r in ctx.lean_reads for a in r.attributes}
window = ctx.costs.window

# --- derivability of every read column from build columns, on the model's own values (gold-free)
values = C.read_values(ctx.docs, ctx.reads, ctx.fields, R.journal_rows(corpus))
cols = defaultdict(dict)
for (t, d), v in values.items():
    for a, x in v.items():
        cols[(t, a)][d] = cell(x)
def derivable(target):
    t, a = target
    best = (0.0, None, None)
    tv = {d: x for d, x in cols[target].items() if x is not None}
    if len(tv) < 10:
        return best
    for src in [k for k in lean if k[0] == t]:
        sv = cols[src]
        both = [d for d in tv if sv.get(d) is not None]
        if len(both) < 10:
            continue
        # substring program: the target value is written inside the source value
        sub = sum(str(tv[d]) in str(sv[d]) for d in both) / len(both)
        # lookup (functional dependency), leave-one-out: predict from other documents with the same source value
        groups = defaultdict(Counter)
        for d in both:
            groups[sv[d]][tv[d]] += 1
        hit = 0
        for d in both:
            g = groups[sv[d]].copy(); g[tv[d]] -= 1
            g = +g
            hit += bool(g) and g.most_common(1)[0][0] == tv[d]
        loo = hit / len(both)
        base = Counter(tv[d] for d in both).most_common(1)[0][1] / len(both)  # always guess the commonest value
        if loo < base + 0.05:
            loo = 0.0
        cover = len(both) / len(tv)
        for score, kind in ((sub * cover, "substring"), (loo * cover, "lookup")):
            if score > best[0]:
                best = (round(score, 3), f"{src[1]}", kind)
    return best
drift_cols = {(t, a) for q, r in ctx.records.items() if q not in ctx.w0 for t, attrs in r["attributes"].items() for a in attrs if (t, a) not in lean}
deriv = {k: derivable(k) for k in drift_cols}

# --- verbatim locatability of the model's value (for 'locate, then read a window')
texts = {}
def locatable(t, d, a):
    v = cols[(t, a)].get(d)
    if v is None:
        return False
    s = str(v)
    if len(s) < 5 or re.fullmatch(r"[\d.\-]+", s):
        return False
    if (t, d) not in texts:
        texts[(t, d)] = read_document(ctx.docs[t][d]).lower()
    return all(p.strip().lower() in texts[(t, d)] for p in s.split("||") if p.strip())

# --- replay the protocol on every stream
def run(stream):
    mat = {k: set(ctx.names[k[0]]) for k in lean}
    reads_of = Counter()
    later_need = [set() for _ in stream]
    acc = set()
    for i in range(len(stream) - 1, -1, -1):
        later_need[i] = set(acc)
        for t, attrs in ctx.records[stream[i]]["attributes"].items():
            acc |= {(t, a) for a in attrs}
    out = Counter()
    for i, q in enumerate(stream):
        need = ctx.records[q]["attributes"]
        sql = ctx.catalog[q]
        for t, attrs in need.items():
            if t not in ctx.names:
                continue
            lacking = [a for a in attrs if (t, a) in ctx.fields and not mat.get((t, a), set()) >= set(ctx.names[t])] if False else \
                      [a for a in attrs if f"{t}.{a}" in ctx.fields and not (mat.get((t, a), set()) >= set(ctx.names[t]))]
            if not lacking:
                continue
            known = {a for (tt, a), ds in mat.items() if tt == t and ds >= set(ctx.names[t])}
            cond = C.pushdown_conjuncts(sql, t, known) if len(need) == 1 else None
            scope = C.evaluate_scope(robust_db, t, cond) if cond else None
            scope = set(ctx.names[t]) if scope is None else scope
            for d in ctx.names[t]:
                miss = [a for a in lacking if d not in mat.get((t, a), set())]
                if not miss:
                    continue
                cost = ctx.costs.read(t, d, [ctx.fields[f"{t}.{a}"] for a in miss])
                out["all_docs_counterfactual"] += cost
                if d not in scope:
                    out["saved_by_scope"] += cost
                    continue
                out["patch"] += cost
                long_doc = ctx.costs.doc_tokens[(t, d)] > window
                out["patch_long_docs"] += cost * long_doc
                out["patch_repeat_read"] += cost * (reads_of[(t, d)] > 0)
                if all(deriv.get((t, a), (0,))[0] >= 0.95 for a in miss):
                    out["patch_derivable"] += cost
                if all((t, a) in later_need[i] for a in miss):
                    out["patch_reused_later"] += cost
                if all(locatable(t, d, a) for a in miss):
                    out["patch_locatable"] += cost
                reads_of[(t, d)] += 1
                for a in miss:
                    mat.setdefault((t, a), set()).add(d)
            out["patch_events"] += 1
    return out

groups = {"attribute/100": [], "combined/100": [], "attribute/gradual": [], "value/100": []}
for s in R.SEEDS:
    for key in groups:
        groups[key].append(run(ctx.designs[s]["streams"][key]))
lean_build = R.read_cost(ctx, ctx.lean_fields, ctx.lean_reads)
res = {"corpus": corpus, "lean_build": lean_build, "window": window,
       "long_doc_share_of_corpus": round(sum(v for (t, d), v in ctx.costs.doc_tokens.items() if v > window) / sum(ctx.costs.doc_tokens.values()), 3),
       "derivable": {f"{t}.{a}": v for (t, a), v in sorted(deriv.items())}, "groups": {}}
for key, runs in groups.items():
    m = {k: sum(r[k] for r in runs) / len(runs) for k in set().union(*runs)}
    res["groups"][key] = {k: round(v) for k, v in m.items()}
print(json.dumps(res))
