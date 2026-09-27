"""A fair DocETL baseline: the recorded runner's map, with its input defects fixed.

Same DocETL map operator, model (Qwen 2.5 7B via OpenRouter), one pipeline per (query, table),
and the recorded prompt, with four changes (see results/docetl_diagnostics/docetl_input_format_audit.md):

1. Field descriptions: each field is listed with the same workload-generated description the
   QuWARTS shared read used (``--descriptions``); fields without one get the name alone. No
   benchmark attribute file is read.
2. Truncation by Qwen's tokenizer: each document is cut, before DocETL sees it, so the whole
   prompt stays under the endpoint's 32,768-token limit with room for the answer. DocETL's own
   truncation (which undercounts Qwen tokens) is never triggered.
3. Failures are logged: DocETL keeps ``skip_on_error=True``, and every document missing from
   a pipeline's output is written to ``failures.json``.
4. Explicit ``max_tokens``: the model's only OpenRouter provider rejects prompts over about
   21k tokens (HTTP 400) when no ``max_tokens`` is sent, because it reserves a large default
   for the answer. Setting it (512) and keeping prompt + answer within the measured 25k admits every case.
5. Sentinels: the prompt keeps DocETL's "-1 / empty string when unknown" instruction; scoring
   maps those markers to NULL (``quwarts.eval.docetl_rescore --null-sentinels``).

Resumable: queries with a finished output are skipped.

    python run_fair_docetl.py --corpus legal --held-out --descriptions <json> --threads 32
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (HERE, ROOT / "systems" / "WDIRS", ROOT):
    sys.path.insert(0, str(p))
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import test_player_query_awareness_trend_docetl as runner  # noqa: E402
from docetl.api import Dataset, MapOp, Pipeline, PipelineOutput, PipelineStep  # noqa: E402
from docetl.operations.utils.api import APIWrapper  # noqa: E402
from quwarts.core.retrieve_extract.tokens import count_tokens, encode_offsets  # noqa: E402

# Advertised context is 32,768, but the model's only OpenRouter provider rejected a 23k-token
# prompt with max_tokens=8000 and accepted it with 2000: prompt + answer <= 25,000 is the measured
# safe total.
CONTEXT = 25_000
ANSWER_ROOM = 512
MARGIN = 0
DATASET = {"legal": "Legal", "finan": "Finan", "med": "Med", "art": "Art", "cspaper": "CSPaper", "player": "Player"}
TOKENS = {"prompt": 0, "completion": 0, "calls": 0}


def track_tokens() -> None:
    original = APIWrapper._call_llm_with_cache

    def wrapped(self, *args, **kwargs):
        response = original(self, *args, **kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            TOKENS["prompt"] += int(getattr(usage, "prompt_tokens", 0) or 0)
            TOKENS["completion"] += int(getattr(usage, "completion_tokens", 0) or 0)
            TOKENS["calls"] += 1
        return response

    APIWrapper._call_llm_with_cache = wrapped


def prompt_template(table: str, fields: list[str], numeric: set[str], sql: str, descriptions: dict[str, str]) -> str:
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


# The endpoint checks the context with its own token estimate, which runs up to ~35% above Qwen's
# exact count on number-heavy filings. A document it rejects (or loses to a transport error) is
# retried with a smaller cut; each document's final cut is recorded.
RETRY_SCALES = (1.0, 0.8, 0.64)  # 1.0 first: a transport or rate-limit failure is retried at the same cut


def fit(text: str, template: str, context: int = CONTEXT) -> str:
    budget = context - count_tokens(template) - ANSWER_ROOM - MARGIN
    # Only the first `budget` tokens matter: tokenize a prefix, which gives the same cut point as
    # tokenizing the whole document whenever the prefix holds comfortably more than `budget` tokens.
    prefix = text[: 16 * budget]
    _ids, offsets = encode_offsets(prefix)
    if len(offsets) <= budget + 50 and len(prefix) < len(text):
        _ids, offsets = encode_offsets(text)
    if len(offsets) <= budget:
        return text
    return text[: offsets[budget - 1][1]]


BATCH = 34  # documents per resumable batch (each device call is capped at ~3 minutes)
DEADLINE = 110.0  # seconds after which no new batch starts in this process


def run_batch(template: str, schema: dict[str, str], data: list[dict[str, Any]], out: Path, threads: int) -> list[dict]:
    op = MapOp(name="extract_fields", type="map", prompt=template, output={"schema": schema},
               model="openrouter/qwen/qwen-2.5-7b-instruct", skip_on_error=True, timeout=420,
               max_retries_per_timeout=2,
               # Without max_tokens the only OpenRouter provider for this model reserves a large
               # default for the answer and rejects prompts over ~21k tokens (HTTP 400).
               litellm_completion_kwargs={"max_tokens": ANSWER_ROOM})
    out.mkdir(parents=True, exist_ok=True)
    pipeline = Pipeline(
        name="extract",
        datasets={"raw": Dataset(type="memory", path=data, source="local")},
        operations=[op],
        steps=[PipelineStep(name="extract_step", input="raw", operations=["extract_fields"])],
        output=PipelineOutput(type="file", path=str(out / "pipeline_output.json"), intermediate_dir=str(out / "intermediate")),
        default_model="openrouter/qwen/qwen-2.5-7b-instruct",
        bypass_cache=True,
    )
    cwd = os.getcwd()
    try:
        os.chdir(out)
        pipeline.run(max_threads=threads)
    finally:
        os.chdir(cwd)
    return json.loads((out / "pipeline_output.json").read_text())


def run_query(qid: str, sql: str, table: str, fields: list[str], numeric: set[str], descriptions: dict[str, str],
              records: list[dict[str, Any]], out: Path, threads: int, t0: float) -> dict[str, Any] | None:
    """One DocETL map over the table's documents, run as fixed batches so an interrupted query resumes.

    Each finished batch stores its rows and its own token usage; the query's pipeline_output.json and
    stats.json are written only when every batch is done. Returns None while batches remain.
    """
    template = prompt_template(table, fields, numeric, sql, descriptions)
    # The largest context the endpoint accepted for each document in an earlier query is reused, so
    # every query gives a document the same cut and rejected attempts are not repeated.
    cache_path = out.parent.parent / "accepted_context.json"
    accepted = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    data = [{"doc_id": r["doc_id"], "text": fit(r["text"], template, accepted.get(r["doc_id"], CONTEXT))} for r in records]
    schema = {c: ("number" if c in numeric else "str") for c in fields}
    batches = out / "batches"
    batches.mkdir(parents=True, exist_ok=True)
    chunks = [data[i:i + BATCH] for i in range(0, len(data), BATCH)]
    for i, chunk in enumerate(chunks):
        done_path = batches / f"{i:03d}.json"
        if done_path.exists():
            continue
        if time.time() - t0 > DEADLINE:
            return None
        before, started = dict(TOKENS), time.time()
        rows = run_batch(template, schema, chunk, batches / f"{i:03d}", threads)
        cut = {d["doc_id"]: accepted.get(d["doc_id"], CONTEXT) for d in chunk}
        by_id = {r["doc_id"]: r for r in records}
        for j, scale in enumerate(RETRY_SCALES):
            missing = [d["doc_id"] for d in chunk if d["doc_id"] not in {r.get("doc_id") for r in rows}]
            if not missing:
                break
            context = min(int(CONTEXT * scale), min(cut[m] for m in missing)) if scale == 1.0 else int(CONTEXT * scale)
            if scale == 1.0:  # same cut as the first attempt, per document
                retry = [{"doc_id": m, "text": fit(by_id[m]["text"], template, cut[m])} for m in missing]
                rows += run_batch(template, schema, retry, batches / f"{i:03d}_retry{j}", threads)
                continue
            missing = [m for m in missing if cut[m] > context]  # a document is never retried at a larger cut
            if not missing:
                break
            retry = [{"doc_id": m, "text": fit(by_id[m]["text"], template, context)} for m in missing]
            rows += run_batch(template, schema, retry, batches / f"{i:03d}_retry{j}", threads)
            cut.update({m: context for m in missing})
        done_path.write_text(json.dumps({
            "rows": rows, "prompt_tokens": TOKENS["prompt"] - before["prompt"],
            "completion_tokens": TOKENS["completion"] - before["completion"],
            "calls": TOKENS["calls"] - before["calls"], "seconds": round(time.time() - started, 1),
            "context_per_doc": {d: c for d, c in cut.items() if d in {r.get("doc_id") for r in rows}}}))
        produced = {r.get("doc_id") for r in rows}
        for d, c in cut.items():  # keep the largest cut the endpoint accepted; never shrink it
            if d in produced:
                accepted[d] = max(accepted.get(d, 0), c)
        cache_path.write_text(json.dumps(accepted, indent=1, sort_keys=True))
        print(json.dumps({"query_id": qid, "batch": i, "of": len(chunks), "rows": len(rows),
                          "calls": TOKENS["calls"] - before["calls"]}), flush=True)
    parts = [json.loads((batches / f"{i:03d}.json").read_text()) for i in range(len(chunks))]
    produced = [r for part in parts for r in part["rows"]]
    (out / "pipeline_output.json").write_text(json.dumps(produced, indent=2))
    missing = sorted({r["doc_id"] for r in data} - {r.get("doc_id") for r in produced})
    stats = {"query_id": qid, "documents": len(data), "rows": len(produced), "failed": missing,
             "truncated": sum(1 for r, d in zip(records, data) if len(d["text"]) < len(r["text"])),
             "prompt_tokens": sum(p["prompt_tokens"] for p in parts),
             "completion_tokens": sum(p["completion_tokens"] for p in parts),
             "calls": sum(p["calls"] for p in parts), "seconds": round(sum(p["seconds"] for p in parts), 1),
             "batches": len(chunks),
             "docs_at_reduced_context": sum(1 for p in parts for c in p.get("context_per_doc", {}).values() if c < CONTEXT)}
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--held-out", action="store_true", help="only the 16 held-out queries DocETL was scored on")
    parser.add_argument("--descriptions", type=Path, help="{table.column: {description}} JSON (e.g. generated)")
    parser.add_argument("--protocol", action="store_true",
                        help="the benchmark's published input: attribute descriptions and value types")
    parser.add_argument("--tag", default="", help="results go to results/docetl_fair_<corpus>_<tag>")
    parser.add_argument("--batch", type=int, default=None, help="documents per resumable batch (layout only)")
    parser.add_argument("--threads", type=int, default=32)
    parser.add_argument("--max-queries", type=int, default=1)
    args = parser.parse_args()
    corpus = args.corpus
    if args.batch:
        global BATCH
        BATCH = args.batch
    runner.DOCETL_MODEL = "openrouter/qwen/qwen-2.5-7b-instruct"
    runner.OLLAMA_BASE_URL = None
    runner.configure_dataset(DATASET[corpus])
    track_tokens()
    # Numeric types from the SQL workload (as QuWARTS derives them), not from the benchmark files.
    from quwarts.core.router.registry import get_corpus
    from quwarts.core.router.workload_features import workload_features
    from quwarts.eval.router_shared_read_run import workload

    spec = get_corpus(corpus)
    root = ROOT / "results" / (f"docetl_fair_{corpus}" + (f"_{args.tag}" if args.tag else ""))
    root.mkdir(parents=True, exist_ok=True)
    if args.protocol:
        # As UDA-Bench runs every system: descriptions and value types from the attribute files.
        attrs = spec.benchmark_attribute_descriptions(purpose="protocol")
        descriptions_all = {f"{t.sql_name}.{a}": {"description": r.get("description")}
                            for t in spec.tables for a, r in attrs.get(t.attributes_key, {}).items()}
        from quwarts.core.router.context_probe import declared_choices

        def labels(r):  # a declared label set outranks the value type (Finan's Yes/No major_equity_changes is typed int)
            choices, _ = declared_choices(str(r.get("description") or ""))
            return choices and not all(c.replace(".", "", 1).lstrip("-").isdigit() for c in choices)

        numeric_sql = {a for t in spec.tables for a, r in attrs.get(t.attributes_key, {}).items()
                       if str(r.get("value_type")) in ("int", "float") and not labels(r)}
    else:
        train, _test = workload(corpus)
        wf = workload_features(spec, {r["query_id"]: r["sql"] for r in train})
        numeric_sql = {u.name for u in wf["attributes"].values() if u.numeric}
        descriptions_all = json.loads(args.descriptions.read_text()) if args.descriptions else {}
    (root / "numeric_fields.json").write_text(json.dumps(sorted(numeric_sql)))
    (root / "descriptions.json").write_text(json.dumps(descriptions_all, indent=2))
    manifest = json.loads((ROOT / "results" / f"docetl_{corpus}_case80" / "query_manifest.json").read_text())
    done = 0
    t0 = time.time()
    for q in manifest:
        qid, sql = q["query_id"], q["sql"]
        need = runner.columns_per_table_from_sql(sql)
        for table, cols in need.items():
            out = root / qid / f"table_{table}"
            if (out / "stats.json").exists():
                continue
            descriptions = {c: descriptions_all.get(f"{table}.{c}", {}).get("description") for c in cols}
            records = runner._raw_doc_records_for_table(table)
            stats = run_query(qid, sql, table, cols, numeric_sql, descriptions, records, out, args.threads, t0)
            if stats is None:
                print(json.dumps({"query_id": qid, "status": "paused; rerun to resume"}), flush=True)
                return 0
            print(json.dumps({k: (len(v) if k == "failed" else v) for k, v in stats.items()}), flush=True)
            done += 1
            if done >= args.max_queries:
                return 0
    print(json.dumps({"status": "all queries done"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
