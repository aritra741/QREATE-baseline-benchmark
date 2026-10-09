"""DocETL with frozen extraction contexts (I3 in results/experiments/why/RESEARCH_DEPTH.md).

Each column is extracted once, by the first query that needs it, in that query's prompt; every later query reuses
those values instead of extracting the column again in its own prompt. Everything else is ``run_docetl_drift.py``:
the same fair prompt (listing only the columns still to extract), the same documents, model, scoring and query order.
Results go to ``results/docetl_frozen_ollama/<corpus>/`` with the same files as the original run, plus
``cache/<table>.json`` (each column's values and the query whose prompt produced them).

Predictions: join keys become consistent across tables (match rate from 18% toward 70% or more), join queries recover
most of their loss, non-join queries change little, and the columns that change most are the high-sensitivity ones.

    QUWARTS_DRIFT_DESIGN=drift_paired QUWARTS_LLM=ollama OLLAMA_HOST=127.0.0.1:PORT \\
        python run_docetl_frozen.py --corpus player --threads 8
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import run_docetl_drift as base

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "results" / "docetl_frozen_ollama"
ORIGINAL_RUN_TABLE = base.run_table  # kept before main() replaces base.run_table with the frozen one
_lock = threading.Lock()


def cache_path(corpus: str, table: str) -> Path:
    p = OUT / corpus / "cache" / f"{table}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_cache(corpus: str, table: str) -> dict:
    p = cache_path(corpus, table)
    return json.loads(p.read_text()) if p.exists() else {}


def run_table_frozen(corpus: str, qid: str, sql: str, table: str, attrs: list[str], fields: dict, out: Path,
                     threads: int) -> dict:
    ctx = base.R.context(corpus)
    stats_path = out / "stats.json"
    if stats_path.exists():
        return json.loads(stats_path.read_text())
    numeric = {a for a in attrs if getattr(fields.get(f"{table}.{a}"), "value_type", "str") in ("int", "float")}
    with _lock:
        cache = load_cache(corpus, table)
        new = [a for a in attrs if a.lower() not in cache]
    if new:
        # Only the columns no earlier query extracted: this query's prompt lists them (and its own SQL), and their
        # values are frozen for every later query.
        s = ORIGINAL_RUN_TABLE(corpus, qid, sql, table, new, fields, out / "new", threads)
        rows = json.loads((out / "new" / "pipeline_output.json").read_text())
        with _lock:
            cache = load_cache(corpus, table)
            for a in new:
                cache[a.lower()] = {"from_query": qid, "asked_with": sorted(x.lower() for x in new),
                                    "numeric": a in numeric, "values": {r["doc_id"]: r.get(a.lower()) for r in rows}}
            cache_path(corpus, table).write_text(json.dumps(cache))
    else:
        s = {"documents": len(ctx.names[table]), "rows": len(ctx.names[table]), "failed": [], "truncated": 0,
             "prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "seconds": 0.0}
    rows = [{"doc_id": d, **{a.lower(): cache[a.lower()]["values"].get(d) for a in attrs}} for d in ctx.names[table]]
    out.mkdir(parents=True, exist_ok=True)
    (out / "pipeline_output.json").write_text(json.dumps(rows))
    stats = {"query_id": qid, "table": table, "fields": attrs, "new_fields": new, "numeric": sorted(numeric),
             "documents": s["documents"], "rows": len(rows), "failed": s["failed"], "truncated": s["truncated"],
             "prompt_tokens": s["prompt_tokens"], "completion_tokens": s["completion_tokens"], "calls": s["calls"],
             "seconds": s["seconds"]}
    stats_path.write_text(json.dumps(stats, indent=1))
    return stats


if __name__ == "__main__":
    base.OUT = OUT
    base.run_table = run_table_frozen
    rc = base.main()
    corpus = sys.argv[sys.argv.index("--corpus") + 1]
    per = json.loads((OUT / corpus / "per_query.json").read_text()) if (OUT / corpus / "per_query.json").exists() else {}
    if "--limit" not in sys.argv and all(q in per for q in base.queries(corpus)):
        (OUT / corpus / "complete.json").write_text(json.dumps({"queries": len(per)}))
    sys.exit(rc)
