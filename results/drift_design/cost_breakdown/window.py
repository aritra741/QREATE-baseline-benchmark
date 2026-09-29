"""Shared reads over a window of queries (micro-batching / cooperative scans), cost model only.
Queries are answered in batches of W consecutive arrivals. For a batch, each document that any batch query
needs is read once, with every known column it lacks (P1 batching inside the batch). W=1 is P1."""
import json, sys, logging
from collections import Counter
logging.disable(logging.INFO)
from quwarts.eval import drift_run as R
from quwarts.core.adapt import controller as C
corpus = sys.argv[1]
ctx = R.context(corpus)
robust_db = R.fixed_db(corpus, "robust_raw")
lean = {(r.table, a) for r in ctx.lean_reads for a in r.attributes}
cache = {}
def cols(q):
    return {(t, a) for t, attrs in ctx.records[q]["attributes"].items() for a in attrs if f"{t}.{a}" in ctx.fields}
def scope_of(q, t, known):
    k = (q, t, frozenset(known))
    if k not in cache:
        need = ctx.records[q]["attributes"]
        cond = C.pushdown_conjuncts(ctx.catalog[q], t, known) if len(need) == 1 else None
        s = C.evaluate_scope(robust_db, t, cond) if cond else None
        cache[k] = set(ctx.names[t]) if s is None else s
    return cache[k]
def run(stream, W):
    mat = {k: set(ctx.names[k[0]]) for k in lean}
    known = set(lean); tok = 0
    for b in range(0, len(stream), W):
        batch = stream[b:b + W]
        for q in batch:
            known |= cols(q)
        want = {}
        for q in batch:
            need = cols(q)
            for t in {t for t, _ in need}:
                lacking = [a for (tt, a) in need if tt == t and not mat.get((tt, a), set()) >= set(ctx.names[t])]
                if not lacking:
                    continue
                complete = {a for (tt, a) in known if tt == t and mat.get((tt, a), set()) >= set(ctx.names[t])}
                for d in scope_of(q, t, complete):
                    if any(d not in mat.get((t, a), set()) for a in lacking):
                        want[(t, d)] = True
        for (t, d) in want:
            miss = sorted({a for (tt, a) in known if tt == t and d not in mat.get((tt, a), set())})
            tok += ctx.costs.read(t, d, [ctx.fields[f"{t}.{a}"] for a in miss])
            for a in miss:
                mat.setdefault((t, a), set()).add(d)
    return tok
L = R.read_cost(ctx, ctx.lean_fields, ctx.lean_reads)
out = {"corpus": corpus, "lean_build": L, "groups": {}}
for key in ("attribute/100", "attribute/gradual"):
    res = {}
    for W in (1, 2, 4, 8, 14, 28, 56):
        if W > len(ctx.designs[0]["streams"][key]):
            continue
        res[W] = round(sum(run(ctx.designs[s]["streams"][key], W) for s in R.SEEDS) / 3 / L, 2)
    out["groups"][key] = res
print(json.dumps(out))
