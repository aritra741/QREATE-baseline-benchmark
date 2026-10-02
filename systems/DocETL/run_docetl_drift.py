"""DocETL on the drift experiment's queries, on the local Ollama model, scored like QuWARTS's drift run.

Every query a corpus's drift experiment uses: the W0 workload, the ``attribute_pool`` fixed-level test
queries (``fixed4`` design) and the paired headline streams. DocETL is query-at-a-time: one map per
(query, table) over every document of the table, with the recorded fair prompt (``run_fair_docetl.py``:
the query's SQL, the fields with their descriptions, numeric types, -1 / empty-string sentinels). The
fields, value types and descriptions are those QuWARTS's design gives the query on its own
(``C.design(spec, {query})``), so neither system gets more description than the other. A document is cut
with Qwen's tokenizer so the prompt and answer fit the server's context. Each query's tables go into one
SQLite database, completed to the physical schema, and scored by the drift run's scorer
(``drift_run.Scorer``: the official SQL path, structure F2 x cell F1), so a DocETL score and a QuWARTS
score of the same query are comparable. DocETL has no build, so its score does not depend on the drift
level; per level it is the mean over that level's test queries (the same queries at every level).

Resumable: a finished (query, table) map and a scored query are skipped.

    QUWARTS_DRIFT_DESIGN=drift_paired QUWARTS_LLM=ollama OLLAMA_HOST=127.0.0.1:11434 \\
        python run_docetl_drift.py --corpus player --threads 8
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "systems" / "WDIRS"))
os.environ.setdefault("QUWARTS_DRIFT_DESIGN", "drift_paired")
os.environ.setdefault("QUWARTS_LLM", "ollama")
# DocETL writes every call to a SQLite (diskcache) cache, even with bypass_cache; on the network home
# directory its lock costs seconds per call and leaves the map's threads idle. The job's local disk, one per corpus.
_corpus = sys.argv[sys.argv.index("--corpus") + 1] if "--corpus" in sys.argv else "probe"
os.environ.setdefault("DOCETL_HOME_DIR", f"{os.environ.get('TMPDIR', '/tmp')}/docetl_home/{_corpus}")

from docetl.api import Dataset, MapOp, Pipeline, PipelineOutput, PipelineStep  # noqa: E402
from docetl.operations.utils.api import APIWrapper  # noqa: E402

from quwarts.core.retrieve_extract.tokens import count_tokens, encode_offsets  # noqa: E402
from quwarts.eval import drift_live as D  # noqa: E402
from quwarts.eval.docetl_rescore import _frame  # noqa: E402

R, C = D.R, D.C
MODEL = "ollama_chat/" + os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
API_BASE = "http://" + os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").removeprefix("http://")
NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "32768"))
ANSWER_ROOM = 512
MARGIN = 256  # chat template and DocETL's own wrapping around the prompt
OUT = ROOT / "results" / "docetl_drift_ollama"
HEADLINE = ("attribute/100", "value/100", "attribute/0", "value/0", "combined/0")
TOKENS = {"prompt": 0, "completion": 0, "calls": 0}
_lock = threading.Lock()


def track_tokens() -> None:
    original = APIWrapper._call_llm_with_cache

    def wrapped(self, *args, **kwargs):
        response = original(self, *args, **kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            with _lock:
                TOKENS["prompt"] += int(getattr(usage, "prompt_tokens", 0) or 0)
                TOKENS["completion"] += int(getattr(usage, "completion_tokens", 0) or 0)
                TOKENS["calls"] += 1
        return response

    APIWrapper._call_llm_with_cache = wrapped


def prompt_template(table: str, fields: list[str], numeric: set[str], sql: str, descriptions: dict[str, str]) -> str:
    """The fair runner's prompt (``run_fair_docetl.prompt_template``), unchanged."""

    field_list = "\n".join(f"- {c}: {descriptions[c]}" if descriptions.get(c) else f"- {c}" for c in fields)
    numeric_here = ", ".join(c for c in fields if c in numeric) or "none"
    return (
        f"You are building a structured {table} table for this natural-language query:\n{sql}\n\n"
        f"From this {table} document, extract exactly one record with these fields:\n{field_list}\n\n"
        "For numeric fields, return numbers (not quoted strings). "
        f"Numeric fields in this extraction: {numeric_here}.\n"
        "If a numeric field is unknown, return -1. If a text field is unknown, return empty string. "
        "Keep names concise and normalized.\n\nDocument:\n{{ input.text }}"
    )


def fit(text: str, template: str) -> str:
    budget = NUM_CTX - count_tokens(template) - ANSWER_ROOM - MARGIN
    prefix = text[: 16 * budget]
    _ids, offsets = encode_offsets(prefix)
    if len(offsets) <= budget + 50 and len(prefix) < len(text):
        _ids, offsets = encode_offsets(text)
    if len(offsets) <= budget:
        return text
    return text[: offsets[budget - 1][1]]


def queries(corpus: str) -> list[str]:
    """Run order: the drift test queries first (the charts need them), then W0, then the headline streams."""

    ctx = R.context(corpus)
    design = json.loads((D.folder(corpus) / "fixed4_attribute_pool_design.json").read_text())
    streams = ctx.designs[0]["streams"]
    order = list(dict.fromkeys(design["test"]))
    order += [q for q in ctx.w0 if q not in order]
    for key in HEADLINE:
        order += [q for q in dict.fromkeys(streams.get(key, [])) if q not in order]
    return order


def sql_of(corpus: str, qid: str) -> str:
    ctx = R.context(corpus)
    return ctx.catalog.get(qid) or ctx.w0[qid]


def safe(qid: str) -> str:
    return qid.replace("/", "_").replace(":", "_").replace("#", "_")


def run_map(table: str, fields: list[str], template: str, schema: dict[str, str], data: list[dict], out: Path,
            threads: int) -> list[dict]:
    op = MapOp(name="extract_fields", type="map", prompt=template, output={"schema": schema}, model=MODEL,
               skip_on_error=True, timeout=900, max_retries_per_timeout=2,
               litellm_completion_kwargs={"max_tokens": ANSWER_ROOM, "num_ctx": NUM_CTX, "api_base": API_BASE})
    out.mkdir(parents=True, exist_ok=True)
    pipeline = Pipeline(
        name="extract",
        datasets={"raw": Dataset(type="memory", path=data, source="local")},
        operations=[op],
        steps=[PipelineStep(name="extract_step", input="raw", operations=["extract_fields"])],
        output=PipelineOutput(type="file", path=str(out / "pipeline_output.json"), intermediate_dir=str(out / "intermediate")),
        default_model=MODEL, default_lm_api_base=API_BASE, bypass_cache=True,
    )
    cwd = os.getcwd()
    try:
        os.chdir(out)
        pipeline.run(max_threads=threads)
    finally:
        os.chdir(cwd)
    path = out / "pipeline_output.json"
    return json.loads(path.read_text()) if path.exists() else []


def run_table(corpus: str, qid: str, sql: str, table: str, attrs: list[str], fields: dict, out: Path, threads: int) -> dict:
    ctx = R.context(corpus)
    stats_path = out / "stats.json"
    if stats_path.exists():
        return json.loads(stats_path.read_text())
    numeric = {a for a in attrs if getattr(fields.get(f"{table}.{a}"), "value_type", "str") in ("int", "float")}
    descriptions = {a: getattr(fields.get(f"{table}.{a}"), "description", None) for a in attrs}
    template = prompt_template(table, attrs, numeric, sql, descriptions)
    texts = {d: Path(p).read_text(errors="ignore") for d, p in ctx.docs[table].items()}
    data = [{"doc_id": d, "text": fit(texts[d], template)} for d in ctx.names[table]]
    schema = {a: ("number" if a in numeric else "str") for a in attrs}
    before, started = dict(TOKENS), time.time()
    rows = run_map(table, attrs, template, schema, data, out / "run", threads)
    got = {r.get("doc_id") for r in rows}
    missing = [d for d in data if d["doc_id"] not in got]
    if missing:  # one retry of the documents DocETL skipped on error
        rows += run_map(table, attrs, template, schema, missing, out / "retry", threads)
        got = {r.get("doc_id") for r in rows}
    rows = clean(rows, attrs)
    (out / "pipeline_output.json").write_text(json.dumps(rows))
    stats = {"query_id": qid, "table": table, "fields": attrs, "numeric": sorted(numeric), "documents": len(data),
             "rows": len(rows), "failed": sorted(d["doc_id"] for d in data if d["doc_id"] not in got),
             "truncated": sum(len(d["text"]) < len(texts[d["doc_id"]]) for d in data),
             "prompt_tokens": TOKENS["prompt"] - before["prompt"], "completion_tokens": TOKENS["completion"] - before["completion"],
             "calls": TOKENS["calls"] - before["calls"], "seconds": round(time.time() - started, 1)}
    stats_path.write_text(json.dumps(stats, indent=1))
    return stats


def clean(rows: list[dict], attrs: list[str]) -> list[dict]:
    """``doc_id`` and the query's fields only. When the model wrote DocETL's tool call as text
    (``{"name": "send_output", "arguments": {...}}``), DocETL fills every field with "Not found";
    the values are those arguments. A nested value left over is NULL. Column names are lowercased, as in
    QuWARTS's databases (SQLite names are case-insensitive, so the physical-schema completion would
    otherwise add a duplicate)."""

    out = []
    for r in rows:
        if isinstance(r.get("arguments"), dict) and r.get("name") == "send_output":
            r = {**r, **r["arguments"]}
        out.append({"doc_id": r.get("doc_id"),
                    **{a.lower(): (None if isinstance(r.get(a), (dict, list)) else r.get(a)) for a in attrs}})
    return out


def build_db(corpus: str, sql: str, tables: dict[str, list[dict]], numeric: dict[str, set[str]], dest: Path) -> Path:
    ctx = R.context(corpus)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    conn = sqlite3.connect(dest)
    for t in R.referenced(sql)[0]:
        if t in tables or t not in ctx.names:
            continue
        tables[t] = [{"doc_id": d} for d in ctx.names[t]]  # a table the query reads no column of: its rows only
    for t, records in tables.items():
        _frame(records or [{"doc_id": None}], numeric.get(t, set()), True).to_sql(t, conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()
    R.complete(corpus, dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--threads", type=int, default=8, help="concurrent documents within a map")
    ap.add_argument("--limit", type=int, help="only the first N queries (a smoke test)")
    a = ap.parse_args(argv)
    corpus = a.corpus
    ctx = R.context(corpus)
    track_tokens()
    root = OUT / corpus
    root.mkdir(parents=True, exist_ok=True)
    scorer = R.Scorer(corpus)
    scorer.path = root / "scores.json"
    scorer.cache = json.loads(scorer.path.read_text()) if scorer.path.exists() else {"benchmark": {}, "tolerant": {}}
    per_path = root / "per_query.json"
    per = json.loads(per_path.read_text()) if per_path.exists() else {}
    order = queries(corpus)[: a.limit]
    t0 = time.time()
    for i, qid in enumerate(order):
        if qid in per:
            continue
        sql = sql_of(corpus, qid)
        fields, reads = C.design(ctx.spec, {qid: sql})
        tables, numeric, stats = {}, {}, []
        for r in reads:
            if r.table not in ctx.names or not r.attributes:
                continue
            s = run_table(corpus, qid, sql, r.table, list(r.attributes), fields, root / safe(qid) / f"table_{r.table}", a.threads)
            stats.append(s)
            tables[r.table] = clean(json.loads((root / safe(qid) / f"table_{r.table}" / "pipeline_output.json").read_text()),
                                    list(r.attributes))
            numeric[r.table] = {x.lower() for x in s["numeric"]}
        db = build_db(corpus, sql, tables, numeric, root / "db" / f"{safe(qid)}.db")
        dig = R.digest(db, sql)
        scorer.run([(qid, dig, db)], lambda: False)
        per[qid] = {"benchmark": scorer.get("benchmark", qid, dig), "tolerant": scorer.get("tolerant", qid, dig),
                    "digest": dig, "tables": [s["table"] for s in stats],
                    "prompt_tokens": sum(s["prompt_tokens"] for s in stats),
                    "completion_tokens": sum(s["completion_tokens"] for s in stats),
                    "calls": sum(s["calls"] for s in stats), "failed_docs": sum(len(s["failed"]) for s in stats),
                    "truncated_docs": sum(s["truncated"] for s in stats), "seconds": round(sum(s["seconds"] for s in stats), 1)}
        per_path.write_text(json.dumps(per, indent=1))
        p = per[qid]
        print(f"{corpus:8s} docetl {i + 1:3d}/{len(order)}  {p['benchmark']:.3f}  {qid[:48]:48s}  "
              f"{(p['prompt_tokens'] + p['completion_tokens']) / 1e6:5.2f}M tok  {p['seconds']:6.0f}s  "
              f"failed {p['failed_docs']}  | {(time.time() - t0) / 60:.0f} min", flush=True)
    done = [q for q in order if q in per]
    print(json.dumps({"corpus": corpus, "status": "complete" if len(done) == len(order) else "running",
                      "queries": len(done), "of": len(order),
                      "mean_benchmark": round(sum(per[q]["benchmark"] for q in done) / max(len(done), 1), 4)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
