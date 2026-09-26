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


def fit(text: str, template: str) -> str:
    budget = CONTEXT - count_tokens(template) - ANSWER_ROOM - MARGIN
    if count_tokens(text) <= budget:
        return text
    _ids, offsets = encode_offsets(text)
    return text[: offsets[budget - 1][1]]


def run_query(qid: str, sql: str, table: str, fields: list[str], numeric: set[str], descriptions: dict[str, str],
              records: list[dict[str, Any]], out: Path, threads: int) -> dict[str, Any]:
    template = prompt_template(table, fields, numeric, sql, descriptions)
    data = [{"doc_id": r["doc_id"], "text": fit(r["text"], template)} for r in records]
    out.mkdir(parents=True, exist_ok=True)
    schema = {c: ("number" if c in numeric else "str") for c in fields}
    op = MapOp(name="extract_fields", type="map", prompt=template, output={"schema": schema},
               model="openrouter/qwen/qwen-2.5-7b-instruct", skip_on_error=True, timeout=420,
               max_retries_per_timeout=2,
               # Without max_tokens the only OpenRouter provider for this model reserves a large
               # default for the answer and rejects prompts over ~21k tokens (HTTP 400).
               litellm_completion_kwargs={"max_tokens": ANSWER_ROOM})
    pipeline = Pipeline(
        name="extract",
        datasets={"raw": Dataset(type="memory", path=data, source="local")},
        operations=[op],
        steps=[PipelineStep(name="extract_step", input="raw", operations=["extract_fields"])],
        output=PipelineOutput(type="file", path=str(out / "pipeline_output.json"), intermediate_dir=str(out / "intermediate")),
        default_model="openrouter/qwen/qwen-2.5-7b-instruct",
        bypass_cache=True,
    )
    before = dict(TOKENS)
    started = time.time()
    cwd = os.getcwd()
    try:
        os.chdir(out)
        pipeline.run(max_threads=threads)
    finally:
        os.chdir(cwd)
    produced = json.loads((out / "pipeline_output.json").read_text())
    missing = sorted({r["doc_id"] for r in data} - {r.get("doc_id") for r in produced})
    stats = {"query_id": qid, "documents": len(data), "rows": len(produced), "failed": missing,
             "truncated": sum(1 for r, d in zip(records, data) if len(d["text"]) < len(r["text"])),
             "prompt_tokens": TOKENS["prompt"] - before["prompt"], "completion_tokens": TOKENS["completion"] - before["completion"],
             "calls": TOKENS["calls"] - before["calls"], "seconds": round(time.time() - started, 1)}
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--held-out", action="store_true", help="only the 16 held-out queries DocETL was scored on")
    parser.add_argument("--descriptions", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=32)
    parser.add_argument("--max-queries", type=int, default=1)
    args = parser.parse_args()
    corpus = args.corpus
    runner.DOCETL_MODEL = "openrouter/qwen/qwen-2.5-7b-instruct"
    runner.OLLAMA_BASE_URL = None
    runner.configure_dataset(DATASET[corpus])
    track_tokens()
    # Numeric types from the SQL workload (as QuWARTS derives them), not from the benchmark files.
    from quwarts.core.router.registry import get_corpus
    from quwarts.core.router.workload_features import workload_features
    from quwarts.eval.router_shared_read_run import workload

    train, _test = workload(corpus)
    wf = workload_features(get_corpus(corpus), {r["query_id"]: r["sql"] for r in train})
    numeric_sql = {u.name for u in wf["attributes"].values() if u.numeric}
    (ROOT / "results" / f"docetl_fair_{corpus}").mkdir(parents=True, exist_ok=True)
    (ROOT / "results" / f"docetl_fair_{corpus}" / "numeric_fields.json").write_text(json.dumps(sorted(numeric_sql)))
    manifest = json.loads((ROOT / "results" / f"docetl_{corpus}_case80" / "query_manifest.json").read_text())
    descriptions_all = json.loads(args.descriptions.read_text())
    root = ROOT / "results" / f"docetl_fair_{corpus}"
    done = 0
    for q in manifest:
        qid, sql = q["query_id"], q["sql"]
        need = runner.columns_per_table_from_sql(sql)
        for table, cols in need.items():
            out = root / qid / f"table_{table}"
            if (out / "stats.json").exists():
                continue
            descriptions = {c: descriptions_all.get(f"{table}.{c}", {}).get("description") for c in cols}
            records = runner._raw_doc_records_for_table(table)
            stats = run_query(qid, sql, table, cols, numeric_sql, descriptions, records, out, args.threads)
            print(json.dumps({k: (len(v) if k == "failed" else v) for k, v in stats.items()}), flush=True)
            done += 1
            if done >= args.max_queries:
                return 0
    print(json.dumps({"status": "all queries done"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
