"""Our reader, one shared read per table for a collection's realistic queries: what helps with a small model, and
whether knowing the query workload helps.

One read of each table with the union of the columns the realistic queries use (our reader: long documents read as
chained chunks, plain JSON, one row per document), then every query answered from that one table with no representation
layer. From the same read two stores are scored: values as read (lists and stated text kept) and values committed as our
system commits them (absence values, allowed labels). Variants change only the read:
  base     the field lines carry the workload's use of each column ("Workload use: compared with specific values, for
           example 'surgery'"), as our system's build does
  nousage  the same read with no workload use lines (no example constants, no grouping/join/number hints)
  allcols  every schema column of each table the queries touch is read (not only the workload's); the workload's columns
           keep their use lines, the others have none
Tables go through DocETL's table building (run_docetl_drift.build_db) like every other arm. Queries: the realistic test
queries scored in WHY/swap/realistic_<corpus>.json. Output: results/shared_reader/<variant>/<corpus>/.

    OLLAMA_HOST=... OLLAMA_NUM_CTX=32768 PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_shared_reader --corpus med --variant base
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace

from quwarts.core.router.executor import Read, commit_value, load_values, run_reads
from quwarts.eval import drift_live as D
from quwarts.eval.exp_docetl_variation import catalogs, safe
from quwarts.eval.exp_tau import EXP, TAUS, score_multi


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--variant", choices=["base", "nousage", "allcols"], default="base")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    repo = EXP.parents[1]
    sys.path.insert(0, str(repo / "systems" / "DocETL"))
    import run_docetl_drift as RD

    c = a.corpus
    ctx = D.R.context(c)
    cat = catalogs(c)
    qids = sorted(json.loads((EXP / "WHY" / "swap" / f"realistic_{c}.json").read_text())[c]["per_query"])
    queries = {q: cat[q] for q in qids}
    for q, s in queries.items():
        ctx.catalog.setdefault(q, s)
    root = repo / "results" / "shared_reader" / a.variant / c
    root.mkdir(parents=True, exist_ok=True)
    usage = D.Usage(root / "usage.jsonl")
    caller = D.make_caller(usage)
    fields, reads = D.C.design(ctx.spec, queries)  # the union of the workload's columns per table, with use lines
    reads = [r for r in reads if r.table in ctx.names and r.attributes]
    if a.variant == "nousage":
        fields = {k: replace(f, usage="") for k, f in fields.items()}
    elif a.variant == "allcols":
        from quwarts.eval.exp_context import fields_of

        schema = {}
        for k in fields_of(c):
            t, x = k.split(".", 1)
            schema.setdefault(t, []).append(x)
        extra = {f"_all_{r.table}": f"SELECT {', '.join(schema.get(r.table, r.attributes))} FROM {r.table}" for r in reads}
        fields_all, _ = D.C.design(ctx.spec, extra)
        fields = {**{k: replace(f, usage="") for k, f in fields_all.items()}, **fields}  # workload columns keep their lines
        reads = [Read(r.table, r.context, tuple(x for x in sorted({*r.attributes, *schema.get(r.table, [])}) if f"{r.table}.{x}" in fields))
                 for r in reads]
    journal = root / "journal.jsonl"
    n0 = len(usage.new)
    stats = run_reads(ctx.spec, reads, {}, fields, caller, journal, workers=a.workers, long_documents="chain")
    values = load_values(journal, fields)
    out = {"queries": len(queries), "variant": a.variant, "reads": {r.table: list(r.attributes) for r in reads}, "read_stats": stats}
    sc = {}
    for store in ("asread", "committed"):
        keep = (lambda v, f: commit_value(v, f)) if store == "committed" else \
            (lambda v, f: None if v is None else (" || ".join(map(str, v)) if isinstance(v, list) else v))
        tables, numeric = {}, {}
        for r in reads:
            got = values.get((r.table, r.context), {})
            tables[r.table] = [{"doc_id": d, **{x.lower(): keep(got.get(d, {}).get(x), fields[f"{r.table}.{x}"]) for x in r.attributes}}
                               for d in ctx.names[r.table]]
            numeric[r.table] = {x.lower() for x in r.attributes if getattr(fields.get(f"{r.table}.{x}"), "value_type", "str") in ("int", "float")}
        items = [(q, RD.build_db(c, queries[q], {t: [dict(x) for x in v] for t, v in tables.items()}, numeric,
                                 root / store / "db" / f"{safe(q)}.db")) for q in queries]
        sc[store] = score_multi(c, items)
    new = usage.new[n0:]
    out.update({"calls": len(new), "input_tokens": sum(x["input"] for x in new), "output_tokens": sum(x["output"] for x in new),
                "mean": {s: {f"{t:.0%}": round(sum(sc[s][q].get(t) or 0 for q in queries) / len(queries), 4) for t in TAUS} for s in sc},
                "per_query": {q: {s: {f"{t:.0%}": sc[s][q].get(t) for t in TAUS} for s in sc} for q in queries}})
    (root / "per_query.json").write_text(json.dumps(out, indent=1, default=str))
    for s in sc:
        print(f"shared-reader {a.variant:8s} {s:9s} {c:8s} mean " + " ".join(f"{k}:{v:.3f}" for k, v in out["mean"][s].items()), flush=True)
    print(f"shared-reader {a.variant} {c}: {len(new)} calls, {(out['input_tokens'] + out['output_tokens']) / 1e6:.2f}M tokens", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
