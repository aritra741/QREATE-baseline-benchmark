"""Augment vs rebuild under per-query column descriptions, cost model only.
Patch-only (P1: each read fetches every known column the document lacks) against the same policy with one
rebuild before query t (every document read once with every column seen so far), for the best t in
hindsight (an upper bound on what any rebuild rule could gain), and OnlinePT's rule (rebuild once the patch
rent since the build reaches the rebuild's cost)."""
import json, sys, logging
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
def rebuild_cost(mat, known):
    tok = 0
    for t in ctx.names:
        ks = [a for (tt, a) in known if tt == t]
        for d in ctx.names[t]:
            miss = [a for a in ks if d not in mat.get((t, a), set())]
            if miss:
                tok += ctx.costs.read(t, d, [ctx.fields[f"{t}.{a}"] for a in ks])  # a rebuild reads the document for its whole design
    return tok
def run(stream, rebuild_at=None, onlinept=False):
    mat = {k: set(ctx.names[k[0]]) for k in lean}
    known = set(lean); tok = 0; rent = 0; rebuilt = None
    for i, q in enumerate(stream):
        known |= cols(q)
        if i == rebuild_at or (onlinept and rebuilt is None and rent >= rebuild_cost(mat, known) > 0):
            tok += rebuild_cost(mat, known)
            for c in known:
                mat[c] = set(ctx.names[c[0]])
            rebuilt = i; rent = 0
        need = cols(q)
        for t in {t for t, _ in need}:
            lacking = [a for (tt, a) in need if tt == t and not mat.get((tt, a), set()) >= set(ctx.names[t])]
            if not lacking:
                continue
            complete = {a for (tt, a) in known if tt == t and mat.get((tt, a), set()) >= set(ctx.names[t])}
            for d in scope_of(q, t, complete):
                if any(d not in mat.get((t, a), set()) for a in lacking):
                    miss = sorted({a for (tt, a) in known if tt == t and d not in mat.get((tt, a), set())})
                    c = ctx.costs.read(t, d, [ctx.fields[f"{t}.{a}"] for a in miss])
                    tok += c; rent += c
                    for a in miss:
                        mat.setdefault((t, a), set()).add(d)
    return tok, rebuilt
L = R.read_cost(ctx, ctx.lean_fields, ctx.lean_reads)
out = {"corpus": corpus, "groups": {}}
for key in ("attribute/100", "attribute/gradual", "combined/100"):
    r = {"patch_only": 0, "best_single_rebuild": 0, "onlinept": 0, "best_t": []}
    for s in R.SEEDS:
        st = ctx.designs[s]["streams"][key]
        p, _ = run(st)
        best = min((run(st, rebuild_at=t)[0], t) for t in range(0, len(st), 2))
        o, when = run(st, onlinept=True)
        r["patch_only"] += p / 3 / L; r["best_single_rebuild"] += min(best[0], p) / 3 / L; r["onlinept"] += o / 3 / L
        r["best_t"].append(best[1] if best[0] < p else None)
    out["groups"][key] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()}
print(json.dumps(out))
