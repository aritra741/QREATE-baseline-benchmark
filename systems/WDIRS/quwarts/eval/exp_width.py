"""E2.1b prompt width (RQ2): is a column extracted more accurately when a read asks for fewer columns?

For one table per corpus, a fixed set of up to 12 workload columns (the protocol field specs, with the build
workload's usage phrases) is read on a fixed document sample in reads of 1, 3, 6 and 12 columns (columns assigned
to reads in one fixed shuffled order, so each width partitions the same set). Every document is read from its first
window (no chaining), the same at every width. Each column's values are then compared with gold on the sampled
documents: exact and lenient agreement where both have a value, false fills (a value where gold has none) and misses.

Resumable: reads go to a journal (``results/experiments/E2.1b-width/<corpus>/reads.jsonl``) and are not repeated.

    QUWARTS_LLM=ollama python -m quwarts.eval.exp_width --corpus player --docs 141
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

from quwarts.core.ledger import TokenLedger
from quwarts.core.router.executor import Read, load_values, run_reads
from quwarts.eval import drift_run as R
from quwarts.eval import exp_analysis as A
from quwarts.eval.drift_live import view_spec
from quwarts.eval.router_plan_v3 import llm_caller

WIDTHS = (1, 3, 6, 12)
TABLE = {"player": "player", "cspaper": "cspaper", "art": "art", "legal": "legal", "med": "disease"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--docs", type=int, default=60)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    corpus, table = a.corpus, TABLE[a.corpus]
    out = A.EXP / "E2.1b-width" / corpus
    out.mkdir(parents=True, exist_ok=True)
    ctx = R.context(corpus)
    gold = A.gold_by_doc(corpus)[table]
    fields = {q: f for q, f in ctx.fields.items() if q.startswith(table + ".")}
    cols = sorted(q.split(".", 1)[1] for q in fields if any(q.split(".", 1)[1] in g for g in list(gold.values())[:1]))
    random.Random(f"width:{corpus}").shuffle(cols)
    cols = cols[:12]
    docs = sorted(d for d in ctx.names[table] if d in gold)
    docs = sorted(random.Random(f"width-docs:{corpus}").sample(docs, min(a.docs, len(docs))))
    reads = [Read(table, f"width{w}:{i}", tuple(sorted(cols[i:i + w]))) for w in WIDTHS for i in range(0, len(cols), w)]
    journal = out / "reads.jsonl"
    vspec, root = view_spec(ctx.spec, ctx.docs, table, docs)
    ledger = TokenLedger(theta=10**13)
    try:
        stats = run_reads(vspec, reads, {}, fields, llm_caller(ledger, max_tokens=700), journal, a.workers,
                          long_documents="head")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    values = load_values(journal, fields)
    rows_by_ctx: dict[str, int] = {}
    for line in journal.read_text().splitlines():
        r = json.loads(line)
        if r["doc"] in docs:
            rows_by_ctx[r["context"].split(":")[0]] = rows_by_ctx.get(r["context"].split(":")[0], 0) + int(r["tokens"])
    res = []
    for w in WIDTHS:
        for i in range(0, len(cols), w):
            ctxname = f"width{w}:{i}"
            got = values.get((table, ctxname), {})
            for c in cols[i:i + w]:
                n = gn = ff = miss = both = exact = loose = 0
                for d in docs:
                    if d not in got:
                        continue
                    g, v = gold[d].get(c), got[d].get(c)
                    n += 1
                    gnull, pnull = A.is_null(g), A.is_null(v)
                    gn += gnull
                    ff += gnull and not pnull
                    miss += pnull and not gnull
                    if not gnull and not pnull:
                        both += 1
                        exact += A.same_value(v, g)
                        loose += A.lenient(v, g)
                res.append({"width": w, "column": c, "docs": n, "gold_null": gn, "false_fills": ff, "misses": miss,
                            "both": both, "exact": exact, "lenient": loose})
    summary = {"corpus": corpus, "table": table, "columns": cols, "docs": len(docs), "read_stats": stats,
               "tokens_by_width": rows_by_ctx, "by_width": {}}
    for w in WIDTHS:
        rs = [r for r in res if r["width"] == w]
        tot = lambda k: sum(r[k] for r in rs)  # noqa: E731
        summary["by_width"][w] = {
            "exact_agree": round(tot("exact") / max(1, tot("both")), 3),
            "lenient_agree": round(tot("lenient") / max(1, tot("both")), 3),
            "false_fill_rate": round(tot("false_fills") / max(1, tot("gold_null")), 3),
            "miss_rate": round(tot("misses") / max(1, tot("docs") - tot("gold_null")), 3),
            "cells": tot("docs"), "tokens": rows_by_ctx.get(f"width{w}", 0)}
    (out / "per_column.json").write_text(json.dumps(res, indent=1))
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary["by_width"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
