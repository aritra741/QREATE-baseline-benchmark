"""Patch policies under per-query column descriptions, cost model only (no calls).
P0 scoped: read the query's scope documents, only the query's missing columns (the breakdown's policy)
P1 scoped + batch: same documents, but each read also fetches every column the system already knows that
   the document lacks (descriptions seen so far)
P2 eager: at a column's first appearance, read it for every document (with every known missing column)
Clairvoyant: one read per document with every column the stream will ever need, for the documents any query needs.
Also: how often a new column appears again later in the stream, and the same statistic in W0 (the build workload)."""
import json, sys, logging
from collections import Counter
logging.disable(logging.INFO)
from quwarts.eval import drift_run as R
from quwarts.core.adapt import controller as C

corpus = sys.argv[1]
ctx = R.context(corpus)
robust_db = R.fixed_db(corpus, "robust_raw")
lean = {(r.table, a) for r in ctx.lean_reads for a in r.attributes}
spec = lambda t, a: ctx.fields[f"{t}.{a}"]

def cols(q):
    return {(t, a) for t, attrs in ctx.records[q]["attributes"].items() for a in attrs if f"{t}.{a}" in ctx.fields}

def scope_of(q, t, known):
    need = ctx.records[q]["attributes"]
    cond = C.pushdown_conjuncts(ctx.catalog[q], t, known) if len(need) == 1 else None
    s = C.evaluate_scope(robust_db, t, cond) if cond else None
    return set(ctx.names[t]) if s is None else s

def run(stream, policy):
    mat = {k: set(ctx.names[k[0]]) for k in lean}
    known = set(lean)
    tok = 0
    reads = 0
    for q in stream:
        need = cols(q)
        new = need - known
        known |= need
        for t in {t for t, _ in need}:
            lacking = [a for (tt, a) in need if tt == t and not mat.get((tt, a), set()) >= set(ctx.names[t])]
            if not lacking:
                continue
            complete = {a for (tt, a) in known if tt == t and mat.get((tt, a), set()) >= set(ctx.names[t])}
            docs = set(ctx.names[t]) if (policy == "P2" and any(k[0] == t for k in new)) else scope_of(q, t, complete)
            for d in sorted(docs):
                want = [a for a in lacking if d not in mat.get((t, a), set())]
                if not want:
                    continue
                if policy in ("P1", "P2"):
                    want = sorted({a for (tt, a) in known if tt == t and d not in mat.get((tt, a), set())})
                tok += ctx.costs.read(t, d, [spec(t, a) for a in want])
                reads += 1
                for a in want:
                    mat.setdefault((t, a), set()).add(d)
    return tok, reads

def clairvoyant(stream):
    allc = set().union(*(cols(q) for q in stream)) - lean
    tok = 0
    for t in {t for t, _ in allc}:
        docs = set()
        for q in stream:
            if any(tt == t and (tt, a) not in lean for tt, a in cols(q)):
                docs |= scope_of(q, t, {a for (tt, a) in lean if tt == t})
        extra = [a for (tt, a) in allc if tt == t]
        tok += sum(ctx.costs.read(t, d, [spec(t, a) for a in extra]) for d in docs)
    return tok

def recurrence(queries):
    seen, first, again = Counter(), set(), set()
    for q in queries:
        for c in cols(q):
            if seen[c] == 0:
                first.add(c)
            else:
                again.add(c)
            seen[c] += 1
    return round(len(again & first) / max(1, len(first)), 2), round(sum(seen.values()) / max(1, len(seen)), 1)

out = {"corpus": corpus, "lean_build": R.read_cost(ctx, ctx.lean_fields, ctx.lean_reads),
       "w0_recurrence": recurrence(list(ctx.w0)), "groups": {}}
for key in ("attribute/100", "combined/100", "attribute/gradual"):
    acc = Counter()
    rec = []
    for s in R.SEEDS:
        st = ctx.designs[s]["streams"][key]
        for p in ("P0", "P1", "P2"):
            tk, n = run(st, p)
            acc[p] += tk / 3
            acc[p + "_reads"] += n / 3
        acc["clairvoyant"] += clairvoyant(st) / 3
        newcols = [q for q in st]
        # recurrence of drift columns inside the stream
        seen = Counter(); firsts = []; 
        for q in st:
            for c in cols(q) - lean:
                seen[c] += 1
        rec.append(sum(v > 1 for v in seen.values()) / max(1, len(seen)))
    out["groups"][key] = {k: round(v) for k, v in acc.items()} | {"drift_cols_recurring": round(sum(rec) / 3, 2)}
print(json.dumps(out))
