"""Two small read experiments for the open questions (results/experiments/A-open/<name>/).

    python -m quwarts.eval.exp_reads alone --corpus art   # A4: each new column read alone vs in the build's group
    python -m quwarts.eval.exp_reads t2 --corpus art      # A13: the representation's model tier on the served views

A4. The 0%-drift build reads all of a table's new columns in one prompt (supplement_spec's read) with build-time field
specs. Here each new column is read alone, with the same field spec, on a document sample, so only the grouping
differs; correctness against gold per column (as exp_open), then which column features go with the direction.

A13. Values right in substance but wrong in form (RQ8): the served views of the recorded unlimited 100%-drift stream
are re-represented with the model tier on (represent Config t2="cascade": residual values the deterministic tiers
cannot map to the column's workload vocabulary go to the model), then re-scored against the views as served.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
from pathlib import Path

from quwarts.eval import drift_live as D
from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import bootstrap, score_components, streams, view
from quwarts.eval.exp_open import (HOME_SCRATCH, OUT, REPO, SCRATCH, column_values, correct, gold_by_doc, holm, is_null,
                                   lookup, mcnemar_p)

SAMPLE = 150  # documents per table


def alone(corpus: str) -> dict:
    from quwarts.core.adapt import controller as C
    from quwarts.core.router.executor import run_reads

    ctx = R.context(corpus)
    supp = D.supplement_spec(corpus, "attribute_pool")
    fields = {**ctx.lean_fields, **supp["fields"]}
    d = OUT / "A4-alone" / corpus
    d.mkdir(parents=True, exist_ok=True)
    journal = d / "reads.jsonl"
    usage = D.Usage(d / "usage.jsonl")
    caller = D.make_caller(usage)
    gold = gold_by_doc(corpus)
    build0 = HOME_SCRATCH / corpus / "builds" / "fixed4_attribute_pool_0" / "build.db"
    rows = []
    for r in supp["reads"]:
        t = r.table
        docs = sorted(d_ for d_ in ctx.docs[t] if d_ in gold.get(t, {}))
        random.Random(f"alone:{corpus}:{t}").shuffle(docs)
        docs = sorted(docs[:SAMPLE])
        vspec, root = D.view_spec(ctx.spec, ctx.docs, t, docs)
        try:
            run_reads(vspec, [C.Read(t, "alone:" + a, (a,)) for a in r.attributes], {}, fields, caller, journal,
                      D.WORKERS, long_documents="chain")
        finally:
            shutil.rmtree(root, ignore_errors=True)
        by = D.rows_of(journal)
        for a in r.attributes:
            vals, _ = D.values_and_shas({x: ctx.docs[t][x] for x in docs}, t, [a], fields, by)
            grouped = column_values(build0, t, a) or {}
            n = ra = rb = fa = fb = ab = ba = ge = 0
            for x in docs:
                g = gold[t][x].get(a) if a in gold[t][x] else None
                if a not in gold[t][x]:
                    continue
                pa = (vals.get(x) or {}).get(a)
                from quwarts.core.router.executor import commit_value
                pa = commit_value(pa, fields[f"{t}.{a}"])
                pb = lookup(grouped, x)
                ca, cb = correct(pa, g), correct(pb, g)
                n += 1; ra += ca; rb += cb; fa += not is_null(pa); fb += not is_null(pb); ge += is_null(g)
                ab += ca and not cb; ba += cb and not ca
            f = fields[f"{t}.{a}"]
            kind = ("numeric" if f.value_type in ("int", "float") else "yes/no" if {c.lower() for c in f.choices} == {"yes", "no"}
                    else "categorical" if f.choices else "free text")
            if n:
                rows.append({"column": f"{t}.{a}", "cells": n, "alone": round(ra / n, 3), "grouped": round(rb / n, 3),
                             "filled_alone": round(fa / n, 3), "filled_grouped": round(fb / n, 3),
                             "gold_empty": round(ge / n, 3), "group_size": len(r.attributes), "kind": kind,
                             "multi": f.value_type.startswith("multi") or f.multi_choice, "never_null": not f.nullable,
                             "choices": len(f.choices), "description_words": len((f.description or "").split()),
                             "alone_right_grouped_wrong": ab, "grouped_right_alone_wrong": ba, "p": round(mcnemar_p(ab, ba), 5)})
    holm(rows)
    (d / "summary.json").write_text(json.dumps(rows, indent=1))
    return {"corpus": corpus, "columns": rows}


def t2(corpus: str) -> dict:
    from quwarts.core.represent import Config, build
    from quwarts.core.represent.llm import Journal

    ctx = R.context(corpus)
    key = "fixed4-attribute_pool/100"
    d = OUT / "A13-t2" / corpus
    d.mkdir(parents=True, exist_ok=True)
    tmp = SCRATCH / "A-open" / "A13-t2" / corpus
    tmp.mkdir(parents=True, exist_ok=True)
    usage = D.Usage(d / "usage.jsonl")
    caller = D.make_caller(usage)
    journal = Journal(d / "t2.jsonl")
    fields = {**ctx.fields, **ctx.lean_fields}
    seen = dict(ctx.w0)
    items, stats = [], []
    for r in streams(corpus)[key]:
        seen[r["qid"]] = ctx.catalog[r["qid"]]
        src = view(corpus, key, r["pos"])
        if not src.exists():
            continue
        dest = tmp / f"{r['pos']:03d}.db"
        if not dest.exists():
            m = build(src, dest, ctx.spec, fields, dict(seen), Config(t2="cascade"), caller, journal)
            stats.append({"pos": r["pos"], **(m.get("t2") or {})})
        items.append((r["qid"], src, dest))
    cache_path = d / "cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    score_components(corpus, [(q, s) for q, s, _ in items] + [(q, x) for q, _, x in items], cache)
    cache_path.write_text(json.dumps(cache))
    sc = lambda q, db: (lambda c: c["structure_f2"] * c["cell_f1_20"])(cache[f"{q}|{R.digest(db, ctx.catalog[q])}"])
    before = [sc(q, s) for q, s, _ in items]
    after = [sc(q, x) for q, _, x in items]
    diff = [b - a for a, b in zip(before, after)]
    out = {"corpus": corpus, "queries": len(items), "before": round(sum(before) / len(before), 4),
           "after": round(sum(after) / len(after), 4), "diff_ci": bootstrap(diff),
           "queries_up": sum(x > 1e-9 for x in diff), "queries_down": sum(x < -1e-9 for x in diff),
           "t2_tokens": sum(s.get("spent", 0) for s in stats), "t2_calls": sum(s.get("calls", 0) for s in stats)}
    (d / "summary.json").write_text(json.dumps(out, indent=1))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["alone", "t2"])
    ap.add_argument("--corpus", required=True)
    a = ap.parse_args(argv)
    out = {"alone": alone, "t2": t2}[a.what](a.corpus)
    print(json.dumps(out, indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
