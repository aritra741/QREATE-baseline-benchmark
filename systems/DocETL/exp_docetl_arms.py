"""DocETL under controlled changes, one at a time, on chosen queries (the decisive tests of WHY/edge/REPORT.md).

Arms (all but ``asis`` with DOCETL_STR_COERCE=1, the fix for DocETL's Ollama path turning a string "2008"
into 2008 and then rejecting it against a declared string type):
  asis     the harness as run before (no fix)
  strfix   the fix only
  masked   strfix; the SQL in the prompt has every string constant replaced by '<value>'
  nosql    strfix; no SQL in the prompt (fields and descriptions only)
  chunked  strfix; each document split into our reader's chunks (same chunk size), one DocETL item per
           chunk, fields combined per document as ours are (most frequent non-blank value, ties to the
           earliest chunk); a document has a row if any chunk returned one
  temp01   strfix; temperature 0.1 (our reader's) instead of Ollama's default (0.8)
Everything else is run_docetl_drift's (prompt, fit to the window, one retry of skipped documents, table
building, scoring). Output: results/docetl_arms/<arm>/<corpus>/..., per_query.json with scores at 0/5/10/20%.

    OLLAMA_HOST=... PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python systems/DocETL/exp_docetl_arms.py --arm strfix --corpus legal --qids real:legal#Q5 ...
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ARMS = ("asis", "strfix", "masked", "nosql", "chunked", "temp01")


def mask(sql: str) -> str:
    return re.sub(r"'[^']*'", "'<value>'", sql)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--qids", nargs="+", required=True)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--model", help="a litellm model id instead of the local Ollama model, e.g. anthropic/claude-haiku-5-5; "
                                    "documents are still fitted to the same 32k window, so both models see the same text")
    a = ap.parse_args(argv)
    if a.arm != "asis":
        os.environ["DOCETL_STR_COERCE"] = "1"

    import run_docetl_drift as RD
    from quwarts.core.router import chunked
    from quwarts.core.router.context_probe import V3
    from quwarts.eval import drift_live as D
    from quwarts.eval.exp_docetl_variation import catalogs
    from quwarts.eval.exp_tau import TAUS, score_multi

    c = a.corpus
    ctx = D.R.context(c)
    cat = catalogs(c)
    for q in a.qids:
        ctx.catalog.setdefault(q, cat[q])
    RD.track_tokens()
    tag = a.arm
    if a.model:
        RD.MODEL, RD.API_BASE = a.model, None
        orig_op = RD.MapOp

        def hosted(*args, **kw):  # no Ollama options (num_ctx, api_base) for a hosted model
            kw["litellm_completion_kwargs"] = {k: v for k, v in kw.get("litellm_completion_kwargs", {}).items() if k in ("max_tokens", "temperature")}
            return orig_op(*args, **kw)

        RD.MapOp = hosted
        tag = f"{a.arm}-{a.model.split('/')[-1]}"
    root = RD.ROOT / "results" / "docetl_arms" / tag / c
    root.mkdir(parents=True, exist_ok=True)
    per_path = root / "per_query.json"
    per = json.loads(per_path.read_text()) if per_path.exists() else {}

    base_run_map = RD.run_map

    def run_map(table, fields, template, schema, data, out, threads):
        if a.arm != "temp01":
            return base_run_map(table, fields, template, schema, data, out, threads)
        orig = RD.MapOp

        def make(*args, **kw):
            kw["litellm_completion_kwargs"] = {**kw.get("litellm_completion_kwargs", {}), "temperature": 0.1}
            return orig(*args, **kw)

        RD.MapOp = make
        try:
            return base_run_map(table, fields, template, schema, data, out, threads)
        finally:
            RD.MapOp = orig

    def run_table(qid, sql, table, attrs, fields, out):
        stats_path = out / "stats.json"
        if stats_path.exists():
            return json.loads(stats_path.read_text())
        numeric = {x for x in attrs if getattr(fields.get(f"{table}.{x}"), "value_type", "str") in ("int", "float")}
        descriptions = {x: getattr(fields.get(f"{table}.{x}"), "description", None) for x in attrs}
        shown = mask(sql) if a.arm == "masked" else sql
        template = RD.prompt_template(table, attrs, numeric, shown, descriptions)
        if a.arm == "nosql":
            template = template.replace(f"for this natural-language query:\n{sql}\n\n", ".\n\n")
            assert sql not in template
        texts = {d: Path(p).read_text(errors="ignore") for d, p in ctx.docs[table].items()}
        if a.arm == "chunked":
            size = chunked.chunk_tokens(int(V3["window_tokens"]))
            data = [{"doc_id": f"{d}#{i}", "text": RD.fit(ch, template)}
                    for d in ctx.names[table] for i, ch in enumerate(chunked.split_chunks(texts[d], size))]
        else:
            data = [{"doc_id": d, "text": RD.fit(texts[d], template)} for d in ctx.names[table]]
        schema = {x: ("number" if x in numeric else "str") for x in attrs}
        before, started = dict(RD.TOKENS), time.time()
        rows = run_map(table, attrs, template, schema, data, out / "run", a.threads)
        got = {r.get("doc_id") for r in rows}
        missing = [d for d in data if d["doc_id"] not in got]
        if missing:
            rows += run_map(table, attrs, template, schema, missing, out / "retry", a.threads)
        rows = RD.clean(rows, attrs)
        items = len(data)
        if a.arm == "chunked":  # combine chunk rows per document
            by_doc: dict[str, list[dict]] = {}
            for r in rows:
                d, _, i = str(r["doc_id"]).rpartition("#")
                by_doc.setdefault(d, []).append({**r, "_i": int(i)})
            merged = []
            for d, rs in by_doc.items():
                rs.sort(key=lambda r: r["_i"])
                row = {"doc_id": d}
                for x in attrs:
                    vals = [r.get(x.lower()) for r in rs if not _blank(r.get(x.lower()))]
                    if vals:
                        counts = Counter(json.dumps(v, sort_keys=True, default=str) for v in vals)
                        top = max(counts.values())
                        row[x.lower()] = next(v for v in vals if counts[json.dumps(v, sort_keys=True, default=str)] == top)
                    else:
                        row[x.lower()] = rs[0].get(x.lower())
                merged.append(row)
            rows = merged
        (out / "pipeline_output.json").write_text(json.dumps(rows))
        docs = list(ctx.names[table])
        have = {str(r["doc_id"]) for r in rows}
        stats = {"query_id": qid, "arm": a.arm, "table": table, "fields": attrs, "numeric": sorted(numeric),
                 "documents": len(docs), "items": items, "rows": len(rows), "failed": sorted(d for d in docs if d not in have),
                 "prompt_tokens": RD.TOKENS["prompt"] - before["prompt"], "completion_tokens": RD.TOKENS["completion"] - before["completion"],
                 "calls": RD.TOKENS["calls"] - before["calls"], "seconds": round(time.time() - started, 1)}
        stats_path.write_text(json.dumps(stats, indent=1))
        return stats

    for qid in a.qids:
        if qid in per:
            continue
        sql = cat[qid]
        fields, reads = D.C.design(ctx.spec, {qid: sql})
        tables, numeric, stats = {}, {}, []
        for r in reads:
            if r.table not in ctx.names or not r.attributes:
                continue
            out = root / RD.safe(qid) / f"table_{r.table}"
            out.mkdir(parents=True, exist_ok=True)
            s = run_table(qid, sql, r.table, list(r.attributes), fields, out)
            stats.append(s)
            tables[r.table] = json.loads((out / "pipeline_output.json").read_text())
            numeric[r.table] = {x.lower() for x in s["numeric"]}
        db = RD.build_db(c, sql, tables, numeric, root / "db" / f"{RD.safe(qid)}.db")
        sc = score_multi(c, [(qid, db)])[qid]
        per[qid] = {"score": {f"{t:.0%}": sc.get(t) for t in TAUS}, "tables": [s["table"] for s in stats],
                    "prompt_tokens": sum(s["prompt_tokens"] for s in stats), "completion_tokens": sum(s["completion_tokens"] for s in stats),
                    "calls": sum(s["calls"] for s in stats), "failed_docs": sum(len(s["failed"]) for s in stats),
                    "seconds": round(sum(s["seconds"] for s in stats), 1)}
        import fcntl  # several processes may write the same collection's file: merge under a lock
        with open(str(per_path) + ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            disk = json.loads(per_path.read_text()) if per_path.exists() else {}
            disk[qid] = per[qid]
            per_path.write_text(json.dumps(disk, indent=1))
        p = per[qid]
        print(f"{a.arm:8s} {c:8s} {qid:40s} score@20 {p['score']['20%']:.3f} @0 {p['score']['0%']:.3f}  "
              f"failed {p['failed_docs']}  {(p['prompt_tokens'] + p['completion_tokens']) / 1e6:.2f}M tok  {p['seconds']:.0f}s", flush=True)
    return 0


def _blank(v) -> bool:
    return v is None or v == -1 or (isinstance(v, str) and v.strip() in ("", "-1", "Not found", "not found"))


if __name__ == "__main__":
    raise SystemExit(main())
