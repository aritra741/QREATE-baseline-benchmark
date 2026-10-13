"""Our reader on a query's own field set, with long documents read in chunks (as run) or whole in one call.

The decisive test of the call-size cause (WHY/edge/REPORT.md 2.1): the same field specs, prompt and parser,
temperature 0.1; only the window changes. ``chunk``: documents longer than the window (10,108 tokens) are read
as ordered chunks with a carried note; ``whole``: the window is 31,000 tokens, so a document up to that length
is one call (num_ctx 32768, as DocETL's). Values are committed as in our system (absence values) and put through
DocETL's table building (run_docetl_drift.build_db) so that both systems' tables take the same path to the
scorer. Output: results/reader_arms/<arm>/<corpus>/ (journal, usage, db, per_query.json at 0/5/10/20%).

    OLLAMA_HOST=... OLLAMA_NUM_CTX=32768 PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_reader_arms --arm whole --corpus player --qids real:player#QJ14
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quwarts.core.router import context_probe as CP
from quwarts.core.router.executor import commit_value, load_values, run_reads
from quwarts.eval import drift_live as D
from quwarts.eval.exp_docetl_variation import catalogs, safe
from quwarts.eval.exp_tau import EXP, TAUS, score_multi


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["chunk", "whole"])
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--qids", nargs="+", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model", help="an Anthropic model id (official SDK, key in ANTHROPIC_API_KEY) instead of the local Ollama model")
    a = ap.parse_args(argv)
    if a.arm == "whole":
        CP.V3["window_tokens"] = 31_000
    repo = EXP.parents[1]
    sys.path.insert(0, str(repo / "systems" / "DocETL"))
    import run_docetl_drift as RD

    c = a.corpus
    ctx = D.R.context(c)
    cat = catalogs(c)
    root = repo / "results" / "reader_arms" / (f"{a.arm}-{a.model}" if a.model else a.arm) / c
    root.mkdir(parents=True, exist_ok=True)
    usage = D.Usage(root / "usage.jsonl")
    caller = anthropic_caller(usage, a.model) if a.model else D.make_caller(usage)
    per_path = root / "per_query.json"
    per = json.loads(per_path.read_text()) if per_path.exists() else {}
    for qid in a.qids:
        if qid in per:
            continue
        sql = cat[qid]
        ctx.catalog.setdefault(qid, sql)
        fields, reads = D.C.design(ctx.spec, {qid: sql})
        reads = [r for r in reads if r.table in ctx.names and r.attributes]
        journal = root / f"{safe(qid)}.journal.jsonl"
        n0 = len(usage.new)
        stats = run_reads(ctx.spec, reads, {}, fields, caller, journal, workers=a.workers, long_documents="chain")
        values = load_values(journal, fields)
        tables, numeric = {}, {}
        for r in reads:
            got = values.get((r.table, r.context), {})
            tables[r.table] = [{"doc_id": d, **{x.lower(): commit_value(got.get(d, {}).get(x), fields[f"{r.table}.{x}"]) for x in r.attributes}}
                               for d in ctx.names[r.table]]
            numeric[r.table] = {x.lower() for x in r.attributes if getattr(fields.get(f"{r.table}.{x}"), "value_type", "str") in ("int", "float")}
            (root / f"{safe(qid)}.table_{r.table}.json").write_text(json.dumps(tables[r.table], default=str))
        db = RD.build_db(c, sql, tables, numeric, root / "db" / f"{safe(qid)}.db")
        sc = score_multi(c, [(qid, db)])[qid]
        new = usage.new[n0:]
        per[qid] = {"score": {f"{t:.0%}": sc.get(t) for t in TAUS}, "tables": [r.table for r in reads],
                    "fields": {r.table: list(r.attributes) for r in reads}, "read_stats": stats,
                    "calls": len(new), "input_tokens": sum(x["input"] for x in new), "output_tokens": sum(x["output"] for x in new),
                    "max_call_input": max((x["input"] for x in new), default=0)}
        import fcntl  # several processes may write the same collection's file: merge under a lock
        with open(str(per_path) + ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            disk = json.loads(per_path.read_text()) if per_path.exists() else {}
            disk[qid] = per[qid]
            per_path.write_text(json.dumps(disk, indent=1, default=str))
        p = per[qid]
        print(f"ours-{a.arm:5s} {c:8s} {qid:32s} score@20 {p['score']['20%']:.3f} @0 {p['score']['0%']:.3f}  calls {p['calls']}  "
              f"{(p['input_tokens'] + p['output_tokens']) / 1e6:.2f}M tok  max call {p['max_call_input']}", flush=True)
    return 0


def anthropic_caller(usage, model: str, max_tokens: int = 2000):
    """Our reader's calls through the Anthropic SDK: same prompt and system text; the model's default sampling."""

    import time

    import anthropic

    from quwarts.core.ledger import BudgetedCaller, TokenLedger

    client = anthropic.Anthropic(max_retries=2)

    def complete(prompt: str, metadata: dict) -> tuple[str, int]:
        start = time.monotonic()
        wait = 10.0
        while True:  # a rate limit or overload is waited out, never turned into a missing answer
            try:
                r = client.messages.create(model=model, max_tokens=max_tokens,
                                           system=metadata.get("system") or "Extract only facts stated in the document. Return JSON.",
                                           messages=[{"role": "user", "content": prompt}])
                break
            except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError):
                time.sleep(wait)
                wait = min(wait * 1.5, 120.0)
        text = "".join(b.text for b in r.content if b.type == "text").strip()
        usage.add({"sha": D.sha(prompt), "input": r.usage.input_tokens, "output": r.usage.output_tokens, "cost": 0.0,
                   "reported_cost": False, "seconds": round(time.monotonic() - start, 2), "backend": "anthropic", "model": model,
                   "stop_reason": r.stop_reason})
        return text, r.usage.input_tokens + r.usage.output_tokens

    return BudgetedCaller(TokenLedger(theta=10**13), complete)


if __name__ == "__main__":
    raise SystemExit(main())
