"""Long streams with skewed frequencies and a shift: 500 queries, the first 250 mostly in-distribution
(10% drift), the next 250 mostly drift (90%), each query drawn with Zipf(1) weights inside its pool.
Augment-only (P1) against a single rebuild at every 25th position, cost model only."""
import json, sys, random, logging
logging.disable(logging.INFO)
sys.argv = [sys.argv[0], sys.argv[1]]
import importlib.util
spec = importlib.util.spec_from_file_location("rb", __file__.replace("long.py", "rebuild.py"))
src = open(__file__.replace("long.py", "rebuild.py")).read().split("L = R.read_cost")[0]
exec(src)
L = R.read_cost(ctx, ctx.lean_fields, ctx.lean_reads)
out = {"corpus": corpus, "seeds": []}
for seed in (0, 1, 2):
    d = ctx.designs[0]
    rng = random.Random(seed)
    t0, pool = list(d["in_distribution"]), list(d["attribute_pool"])
    w = lambda n: [1 / (i + 1) for i in range(n)]
    rng.shuffle(t0); rng.shuffle(pool)
    def draw(p):
        return rng.choices(pool, w(len(pool)))[0] if rng.random() < p else rng.choices(t0, w(len(t0)))[0]
    stream = [draw(0.1) for _ in range(250)] + [draw(0.9) for _ in range(250)]
    base, _ = run(stream)
    best = min((run(stream, rebuild_at=t)[0], t) for t in range(0, 500, 25))
    o, when = run(stream, onlinept=True)
    out["seeds"].append({"augment_only": round(base / L, 2), "best_rebuild": round(best[0] / L, 2), "best_at": best[1],
                         "onlinept": round(o / L, 2), "onlinept_at": when,
                         "distinct_new_columns": len(set().union(*(cols(q) for q in stream)) - lean)})
print(json.dumps(out))
