"""Our system on the representation-conflict queries: one shared extraction, then three ways to answer.

One read of each table (our reader, chunked long documents, the union of the columns every conflict query of the
collection needs; the shared read of our build), committed as our system commits values. From that one raw table:
  raw       the queries run on the values as extracted (no representation)
  shared    one view for all the collection's queries (core.represent.build with the whole workload): one form per column
  perquery  one view per query (represent.build with that query alone): each query gets the form its own SQL implies
Tables go through DocETL's table building (run_docetl_drift.build_db) so every arm reaches the scorer the same way;
correct answers come from the queries' answer keys. Output: results/conflict_ours/<model or qwen>/<corpus>/.

    ANTHROPIC_API_KEY=... PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        QUWARTS_PARSE_FIRST_OBJECT=1 ~/venvs/quwarts/bin/python -m quwarts.eval.exp_conflict_ours --corpus art --model claude-haiku-5-5
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys

from quwarts.core.represent import Config, build
from quwarts.core.router.executor import commit_value, load_values, run_reads
from quwarts.eval import drift_live as D
from quwarts.eval.exp_docetl_variation import safe
from quwarts.eval.exp_reader_arms import anthropic_caller
from quwarts.eval.exp_tau import EXP, TAUS, score_multi
from quwarts.eval.validate_conflicts import load


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--model", help="Anthropic model id; default: the local Ollama model")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--gold", action="store_true", help="perfect extraction: the correct values instead of model reads (no calls)")
    ap.add_argument("--store", choices=["committed", "asread"], default="committed",
                    help="committed: values conformed to the field specs at commit, as our system stores them; asread: the values "
                         "as read (lists and stated text kept), so every form is left to the views")
    a = ap.parse_args(argv)
    repo = EXP.parents[1]
    sys.path.insert(0, str(repo / "systems" / "DocETL"))
    import run_docetl_drift as RD

    c = a.corpus
    ctx = D.R.context(c)
    queries = load(c)
    for q, s in queries.items():
        ctx.catalog[q] = s
    root = repo / "results" / "conflict_ours" / ("gold" if a.gold else (a.model or "qwen")) / c
    out_dir = root if a.store == "committed" else root / "asread"
    out_dir.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    usage = D.Usage(root / "usage.jsonl")
    caller = None if a.gold else (anthropic_caller(usage, a.model) if a.model else D.make_caller(usage))
    fields, reads = D.C.design(ctx.spec, queries)  # the shared read: the union of the workload's columns per table
    reads = [r for r in reads if r.table in ctx.names and r.attributes]
    journal = root / "journal.jsonl"
    n0 = len(usage.new)
    if a.gold:
        from quwarts.eval.exp_analysis import gold_by_doc

        gdoc = gold_by_doc(c)
        stats = {"gold": True}
        values = {}
        for r in reads:
            gt = {str(d).rsplit(".", 1)[0]: row for d, row in gdoc.get(r.table, {}).items()}
            values[(r.table, r.context)] = {d: {x: (gt.get(str(d).rsplit(".", 1)[0]) or {}).get(x) for x in r.attributes} for d in ctx.names[r.table]}
    else:
        stats = run_reads(ctx.spec, reads, {}, fields, caller, journal, workers=a.workers, long_documents="chain")
        values = load_values(journal, fields)
    tables, numeric = {}, {}
    for r in reads:
        got = values.get((r.table, r.context), {})
        keep = (lambda v, f: commit_value(v, f)) if a.store == "committed" else (lambda v, f: None if v is None else (" || ".join(map(str, v)) if isinstance(v, list) else v))
        tables[r.table] = [{"doc_id": d, **{x.lower(): keep(got.get(d, {}).get(x), fields[f"{r.table}.{x}"]) for x in r.attributes}}
                           for d in ctx.names[r.table]]
        numeric[r.table] = {x.lower() for x in r.attributes if getattr(fields.get(f"{r.table}.{x}"), "value_type", "str") in ("int", "float")}
    # the raw table, NOT completed: the predicate signature columns are added to each version after its values are final
    from quwarts.eval.docetl_rescore import _frame

    referenced = set().union(*(set(D.R.referenced(s)[0]) for s in queries.values()))
    for t in referenced:
        if t in ctx.names and t not in tables:
            tables[t] = [{"doc_id": d} for d in ctx.names[t]]
    master = out_dir / "master.db"
    if master.exists():
        master.unlink()
    con = sqlite3.connect(master)
    for t, records in tables.items():
        _frame([dict(x) for x in records] or [{"doc_id": None}], numeric.get(t, set()), True).to_sql(t, con, if_exists="replace", index=False)
    con.commit()
    con.close()
    raw = out_dir / "views" / "raw.db"
    raw.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(master, raw)
    D.R.complete(c, raw)
    items = {"raw": [], "shared": [], "perquery": []}
    shared = out_dir / "views" / "shared.db"
    build(master, shared, ctx.spec, fields, queries, Config())
    D.R.complete(c, shared)
    for q in queries:
        items["raw"].append((q, raw))
        items["shared"].append((q, shared))
        own = out_dir / "views" / f"{safe(q)}.db"
        build(master, own, ctx.spec, fields, {q: queries[q]}, Config())
        D.R.complete(c, own)
        items["perquery"].append((q, own))
    sc = {k: score_multi(c, v) for k, v in items.items()}
    new = usage.new[n0:]
    out = {"queries": len(queries), "reads": {r.table: list(r.attributes) for r in reads}, "read_stats": stats,
           "calls": len(new), "input_tokens": sum(x["input"] for x in new), "output_tokens": sum(x["output"] for x in new),
           "per_query": {q: {k: {f"{t:.0%}": sc[k][q].get(t) for t in TAUS} for k in sc} for q in queries}}
    (out_dir / "per_query.json").write_text(json.dumps(out, indent=1, default=str))
    for k in sc:
        print(f"ours-{a.store}-{k:9s} {c:8s} mean@20 {sum(sc[k][q][0.2] for q in queries) / len(queries):.3f} @0 {sum(sc[k][q][0.0] for q in queries) / len(queries):.3f}", flush=True)
    print(f"ours {c}: {len(new)} calls, {(out['input_tokens'] + out['output_tokens']) / 1e6:.2f}M tokens", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
