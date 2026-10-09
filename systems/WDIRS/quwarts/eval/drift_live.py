"""Real (not replayed) drift runs on the template-paired streams. AUDIT for scores only: reads gold.

    QUWARTS_DRIFT_DESIGN=drift_paired python -m quwarts.eval.drift_live --corpus art --run --deadline 165
    QUWARTS_DRIFT_DESIGN=drift_paired python -m quwarts.eval.drift_live --report
    # a local model (e.g. on a CHPC GPU node; see scripts/chpc/README.md), no deadline:
    QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired python -m quwarts.eval.drift_live --corpus art --run \
        --streams fixed --deadline 0 --workers 8

Backends (QUWARTS_LLM): ``openrouter`` (default; results in ``results/drift_live``) or ``ollama`` (a local
server, ``core/llm/ollama.py``; results in ``results/drift_live_ollama``, so answers of the two never mix: the
build is read again with the local model). For Ollama, ``cost_usd`` is what the same tokens would cost at the
OpenRouter list price, for comparison; what the run really spends is GPU time (``runtime_s``).

Fixed-question drift levels (``--streams fixed``). The paired streams change the questions between levels
(each drifted query swaps a column), so a level's score mixes drift with question difficulty. Here the test
questions are the same at every level: the queries of the ``attribute/100`` stream (``--axes`` adds ``value``
and ``combined``; ``attribute_pool`` takes every valid attribute-drift variant instead, 2-4x as many queries). What changes is how much of them the build anticipated. At level p, a seeded, nested p% of
the test queries is withheld; the columns the other (anticipated) test queries need beyond W0's are read at
build time, and the stream then answers every test query in order, reading on arrival whatever the build did
not anticipate. Level 100 is the W0 build; level 0 anticipates all of them. This is the usual design for
workload drift: fixed test queries, a varying share of them represented in the workload the system was built
for (Negi et al., VLDB 2023; CliffGuard).

Levels are defined by columns (design version 4, keys ``fixed4-<axis>/<p>``; see ``fixed_design``): at level p a
nested set of the new columns is left out of the build, and the test queries using them are unanticipated.
Versions 1-3 withheld queries, which left almost every column in the build (many queries share a column).
Only drift may differ between levels (unchanged from version 3):
* W0's columns: every level starts from the same W0 build read, so they hold the same values at every level.
* The anticipated extra columns: one build-time read of all of them (the 0% list) is made once per corpus and
  axis, and each level keeps only the columns its anticipated queries need (the others stay empty until a
  query needs them and they are read on arrival). An anticipated column therefore has the same value at every
  level where it is anticipated. A 7B model's answer for one field depends on which other fields share the
  prompt, so per-level reads (version 2) gave an anticipated column different values at different levels:
  noise, not drift.
* No leak: each extra column's usage phrase comes only from the test queries that use it and are anticipated
  at the highest level where the column is still anticipated; the levels are nested, so those queries are
  anticipated at every level that keeps the column. The shared prompt also lists the columns a level does not
  keep; their values are discarded.
* Version 1 re-read every column per level; version 2 read each level's extra columns separately. Their outputs
  (``fixed-*``, ``fixed2-*``) are kept and never reused or reported.
W0's columns keep W0's usage phrases at every level; ``rebuild_quality`` found that re-phrasing them from a new
workload changes no score beyond noise. What remains between levels is how a drifted column is read: ahead,
in the shared build read, or on arrival, with only the columns its query lacks and a usage phrase from the
queries seen so far. That is the drift effect on accuracy; it can go either way (a short on-arrival prompt
can extract a column better). The cost of drift is the on-arrival reading. A level's build is charged what one
shared read of W0's and its kept columns would cost (W0's read as measured plus the kept fields' prompt lines and
answers per call), not the separate supplement read, which exists only to hold values fixed across levels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any

from quwarts.core.adapt import controller as C
from quwarts.eval import drift_run as R

CORPORA = ["cspaper", "art", "legal", "player", "med"]
ALL_CORPORA = CORPORA + ["finan"]
FIXED_LEVELS = (100, 0, 50, 25, 75)  # 100 first: it is the W0 build, shared with the paired streams
FIXED_SEED = int(os.environ.get("QUWARTS_DRIFT_SEED", 0))  # 0: the recorded design; others: robustness draws (E11)
# Patch budgets (``--streams budget``): % of the patch tokens the unlimited stream spends at 100% drift on that corpus
# and axis; 0% is the static build (recorded on every stream) and the unlimited stream is the fixed level itself.
BUDGETS = (10, 25, 50, 75, 100)
FIXED = "fixed4"  # design version 4 (see the module docstring and fixed_design); earlier outputs are kept, never reused
ORDER = ["attribute/100", "combined/100", "value/100", "attribute/0", "attribute/50", "combined/50",
         "attribute/25", "attribute/75", "combined/0", "combined/25", "combined/75", "value/0", "value/25",
         "value/50", "value/75", "attribute/gradual", "combined/gradual", "value/gradual"]
HEADLINE = ["attribute/100", "value/100", "attribute/0", "combined/0", "value/0"]
WORKERS = int(os.environ.get("QUWARTS_WORKERS", 24))
BACKEND = os.environ.get("QUWARTS_LLM", "openrouter")
assert BACKEND in ("openrouter", "ollama"), BACKEND
PRICE = {"input": 0.10 / 1e6, "output": 0.20 / 1e6}  # OpenRouter list price of qwen/qwen-2.5-7b-instruct
# Ablations of the patch prompt (QUWARTS_LIVE_VARIANT): ``no_literals`` keeps a patched column's usage phrase but
# drops the example constants from the queries; ``no_usage`` gives a patched column no usage phrase. The build is
# the same read in every variant. ``with_known``: a patch prompt also lists every column already known for the table
# (the build's and earlier queries'); a read costs about the document's length whatever the number of fields, and
# the known fields give the model the context the build's prompt had. Only the missing columns are written.
VARIANT = os.environ.get("QUWARTS_LIVE_VARIANT", "")
# Component ablations (E13), one at a time; unset = the system as recorded. Each turns off one part of the stream
# controller (the build is never changed):
#   rawview  serve the master database as stored: no value representation in the view (represent Config t0=False)
#   raw      store patched values as the model returned them (lists joined), without commit-time normalization
#   noscope  patch every document of the table, not only those the query's pushed-down filter can select
#   noreuse  every query starts from the build: no patched column is kept for later queries; a patch then reads only
#            the columns the query lacks (batching columns that are dropped after the query would only add cost), so
#            its contrast is nobatch
#   nobatch  a patch reads only the columns the query lacks, not the other workload columns still missing
#   nodesc   patch prompts drop the field descriptions (the name stands in) for the columns outside the build; types,
#            allowed values and the usage phrase stay
#   nousage  patch prompts drop the workload usage phrase for the columns outside the build
#   head     a long document is read only up to the window (no chained chunks with carried context) by patches
# Prompt factors (E14): how a patch's prompt differs from the build's for the same column. At a fixed level the build
# reads all of a table's new columns in one prompt (supplement_spec's read) with their build-time field specs:
#   bfields  patches use the build's field specs for the new columns (the patch's grouping and scope)
#   bgroup   patches ask for all of the table's new columns together, as the build does (the patch's field specs;
#            the build's for columns no query has used yet), and keep every column they read
#   bprompt  both: a patch's prompt is the build's prompt, read from the build journal (no new calls are needed);
#            with noscope (QUWARTS_ABLATE=bprompt,noscope) the patched cells must equal the 0% build's
# Several may be combined (comma list).
# rawview and raw also change which documents later queries' pushed-down filters select (the scope is evaluated on the
# served view), and raw leaves chained long documents normalized (reduce_chunks commits per chunk).
ABLATE = frozenset(a for a in os.environ.get("QUWARTS_ABLATE", "").split(",") if a)
# I6 (RESEARCH_DEPTH.md): QUWARTS_LABEL_CONTRACT, a JSON file {"table.column": [label, ...]}: a patch prompt lists these
# as the allowed values of a column outside the build (the vocabulary a workload's GROUP BY compares against, which
# the documents do not state and the usage phrase only exemplifies). Unset: the field specs as recorded.
CONTRACT = (json.loads(Path(os.environ["QUWARTS_LABEL_CONTRACT"]).read_text())
            if os.environ.get("QUWARTS_LABEL_CONTRACT") else {})
from dataclasses import replace as replace_field  # noqa: E402
assert ABLATE <= {"rawview", "raw", "noscope", "noreuse", "nobatch", "nodesc", "nousage", "head",
                  "bfields", "bgroup", "bprompt"}, ABLATE
assert VARIANT in ("", "no_literals", "no_usage", "with_known"), VARIANT
BASE = Path(os.environ["QUWARTS_LIVE_ROOT"]) if os.environ.get("QUWARTS_LIVE_ROOT") else \
    R.RESULTS / ("drift_live" if BACKEND == "openrouter" else "drift_live_ollama")  # the override is for tests
LIVE = BASE / "variants" / VARIANT if VARIANT else BASE
SCRATCH = Path(os.environ.get("QUWARTS_SCRATCH") or Path.home() / "quwarts_scratch") / (
    ("drift_live" if BACKEND == "openrouter" else "drift_live_ollama") + (f"_{VARIANT}" if VARIANT else ""))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def folder(corpus: str) -> Path:
    return LIVE / corpus


def scratch(corpus: str) -> Path:
    return SCRATCH / corpus


# ------------------------------------------------------------------------------------------ the caller

class Usage:
    """Input and output tokens and cost of every call, by prompt hash (``usage.jsonl``)."""

    def __init__(self, path: Path):
        self.path, self.lock = path, threading.Lock()
        self.by_sha: dict[str, dict] = {}
        self.new: list[dict] = []
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.by_sha[row["sha"]] = row

    def add(self, row: dict) -> None:
        with self.lock:
            self.by_sha[row["sha"]] = row
            self.new.append(row)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as h:
                h.write(json.dumps(row) + "\n")


def make_caller(usage: Usage, max_tokens: int = 700):
    """The backend's caller, every call's input/output tokens and cost recorded in ``usage``."""

    if os.environ.get("QUWARTS_LIVE_REPLAY"):
        # A replay re-runs streams from the journals only: every read must already be recorded. A call means the
        # replay diverged from the recorded run, so it stops instead of reading (and paying) anew.
        from quwarts.core.ledger import BudgetedCaller, TokenLedger

        def refuse(prompt: str, metadata: dict[str, Any]) -> tuple[str, int]:
            raise RuntimeError(f"replay made a model call (prompt sha {sha(prompt)[:12]}): not in the journal")

        return BudgetedCaller(TokenLedger(theta=10**13), refuse)
    if BACKEND == "ollama":
        return ollama_caller(usage, max_tokens)
    return openrouter_caller(usage, max_tokens)


def ollama_caller(usage: Usage, max_tokens: int):
    from quwarts.core.llm import ollama

    models = ollama.ping()  # fail early when the server is not up
    model = os.environ.get("OLLAMA_MODEL") or ollama.DEFAULT_MODEL
    if not any(m == model or m.split(":latest")[0] == model for m in models):
        raise RuntimeError(f"Ollama at {ollama.base_url()} does not have {model} (has {models}); run `ollama pull {model}`")

    def on_usage(prompt: str, u: dict) -> None:
        usage.add({"sha": sha(prompt), "input": u["input"], "output": u["output"],
                   "cost": u["input"] * PRICE["input"] + u["output"] * PRICE["output"], "reported_cost": False,
                   "seconds": u["seconds"], "backend": "ollama", "model": u["model"], "num_ctx": u["num_ctx"],
                   "ollama_prompt_eval_count": u["ollama_prompt_eval_count"],
                   "maybe_truncated": u["maybe_truncated"], "cut_off": u["cut_off"]})

    return ollama.make_caller(model=model, max_tokens=max_tokens, on_usage=on_usage)


def openrouter_caller(usage: Usage, max_tokens: int):
    """``openrouter.make_caller`` with the prompt/completion split and OpenRouter's cost recorded."""

    from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

    from quwarts.core.ledger import BudgetedCaller, TokenLedger
    from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, openrouter_client
    from quwarts.core.router.registry import PROJECT

    load_env_file(PROJECT / ".env")
    client = openrouter_client()

    def complete(prompt: str, metadata: dict[str, Any]) -> tuple[str, int]:
        delay, response = 5.0, None
        start = time.monotonic()
        for attempt in range(8):
            try:
                response = client.chat.completions.create(
                    model=DEFAULT_MODEL, temperature=0.1, max_tokens=max_tokens,
                    messages=[{"role": "system", "content": metadata.get("system") or "Extract only facts stated in the document. Return JSON."},
                              {"role": "user", "content": prompt}],
                    extra_body={"usage": {"include": True}})
                break
            except (RateLimitError, APIStatusError, APITimeoutError, APIConnectionError) as exc:
                status = getattr(exc, "status_code", None)
                retryable = isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)) or status in {400, 429, 502, 503}
                if status == 400 and "maximum context length" in str(exc):
                    retryable = False
                if not retryable or attempt == 7:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 120)
        text = (response.choices[0].message.content or "").strip()
        u = getattr(response, "usage", None)
        pin = int(getattr(u, "prompt_tokens", 0) or 0) if u else 0
        pout = int(getattr(u, "completion_tokens", 0) or 0) if u else 0
        cost = getattr(u, "cost", None) if u else None
        if cost is None and u is not None and getattr(u, "model_extra", None):
            cost = u.model_extra.get("cost")
        if pin + pout <= 0:
            pin, pout = max(1, len(prompt) // 4), max(1, len(text) // 4)
        usage.add({"sha": sha(prompt), "input": pin, "output": pout,
                   "cost": float(cost) if cost is not None else pin * PRICE["input"] + pout * PRICE["output"],
                   "reported_cost": cost is not None, "seconds": round(time.monotonic() - start, 2)})
        return text, pin + pout

    return BudgetedCaller(TokenLedger(theta=10**13), complete)


def charge(shas: list[str], usage: Usage, journal_rows: dict[str, dict]) -> dict[str, float]:
    """Input/output tokens and cost of the calls behind ``shas`` (exact where recorded; for calls made before
    usage was recorded, output = the response's tokens and input = the rest)."""

    from quwarts.core.retrieve_extract.tokens import count_tokens

    out = {"calls": 0, "input": 0, "output": 0, "cost": 0.0, "estimated_calls": 0}
    for s in shas:
        out["calls"] += 1
        u = usage.by_sha.get(s)
        if u is None:
            row = journal_rows.get(s)
            if row is None:
                continue
            o = count_tokens(row["response"]) + 1
            i = max(0, int(row.get("tokens", 0)) - o)
            u = {"input": i, "output": o, "cost": i * PRICE["input"] + o * PRICE["output"]}
            out["estimated_calls"] += 1
        out["input"] += u["input"]
        out["output"] += u["output"]
        out["cost"] += u["cost"]
    return out


# ------------------------------------------------------------------------------------------ reads

def rows_of(journal: Path) -> dict[str, dict]:
    out = {}
    if journal.exists():
        for line in journal.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                out[row["prompt_sha"]] = row
    return out


def values_and_shas(docs: dict[str, Path], table: str, attrs: list[str], fields, by_sha,
                    head: bool = False) -> tuple[dict, list[str]]:
    """``read_values`` for one table and field list, also returning the prompt hashes it used. ``head``: long
    documents were read only up to the window (``run_reads(long_documents="head")``)."""

    from quwarts.core.retrieve_extract.tokens import count_tokens
    from quwarts.core.router import chunked
    from quwarts.core.router.context_probe import V3, render_prompt, truncate
    from quwarts.core.router.corpus_features import read_document
    from quwarts.core.router.probes import parse_fields

    from quwarts.core.router.executor import cut_to_share

    window = int(V3["window_tokens"])
    specs = [fields[f"{table}.{a}"] for a in attrs]
    values, used = {}, []
    for doc, path in docs.items():
        text = cut_to_share(read_document(path), table, attrs)  # I7: per-column read windows (unset: whole document)
        if head or count_tokens(text) <= window:
            s = sha(render_prompt(truncate(text, window), specs, None))
            row = by_sha.get(s)
            if row is not None:
                parsed = parse_fields(row["response"], attrs)
                values[doc] = {a: parsed.get(a) for a in attrs}
                used.append(s)
            continue
        carry, answers, shas = "", [], []
        pieces = chunked.split_chunks(text, chunked.chunk_tokens(window))
        for i, piece in enumerate(pieces):
            s1 = sha(chunked.render_chunk_prompt(piece, specs, carry, i + 1, len(pieces)))
            s2 = sha(chunked.render_chunk_prompt(chunked.compact(piece), specs, carry, i + 1, len(pieces)))
            s = s1 if s1 in by_sha else s2
            row = by_sha.get(s)
            if row is None:
                break
            parsed = parse_fields(row["response"], attrs)
            answers.append({a: parsed.get(a) for a in attrs})
            shas.append(s)
            carry = chunked.parse_carry(row["response"], carry)
        used += shas
        if len(answers) == len(pieces):
            values[doc] = {a: chunked.reduce_chunks(answers, fields[f"{table}.{a}"])[0] for a in attrs}
    return values, used


def view_spec(spec, docs: dict[str, dict[str, Path]], table: str, names: list[str]):
    import tempfile
    from dataclasses import replace

    root = Path(tempfile.mkdtemp(prefix="quwarts_live_"))
    tables = []
    for t in spec.tables:
        d = root / t.sql_name
        d.mkdir()
        if t.sql_name == table:
            for n in names:
                (d / n).symlink_to(Path(docs[table][n]).resolve())
        tables.append(replace(t, doc_dir=d))
    return replace(spec, tables=tuple(tables)), root


class Incomplete(Exception):
    pass


def left_of(stop_at: float) -> float | None:
    """Seconds left before ``stop_at`` for ``run_reads`` (None: no deadline)."""

    return None if stop_at == float("inf") else stop_at - time.monotonic()


def patch_variant(ctx, seen, fields):
    """The patch prompt's ablation for columns outside the build (the build's own fields are unchanged)."""

    from dataclasses import replace

    from quwarts.core.router.workload_features import usage_phrase, workload_features

    uses = workload_features(ctx.spec, seen)["attributes"] if VARIANT == "no_literals" and not ABLATE else {}
    out = {}
    for k, f in fields.items():
        if k in ctx.lean_fields:
            out[k] = f
        elif "nodesc" in ABLATE:
            out[k] = replace(f, description="")
        elif "nousage" in ABLATE:
            out[k] = replace(f, usage="")
        elif VARIANT == "no_usage":
            out[k] = replace(f, usage="")
        else:
            out[k] = replace(f, usage=usage_phrase(replace(uses[k], literals=()))) if k in uses else f
    return out


# ------------------------------------------------------------------------------------------ build

def build_journal(corpus: str) -> Path:
    return folder(corpus) / "build_reads.jsonl"


def old_read(corpus: str) -> Path:
    base = R.ROOT / corpus
    for p in (base / "rebuild_quality" / "old.jsonl", R.ROOT / "_superseded_med_incumbent" / "rebuild_quality" / "old.jsonl"):
        if p.exists():
            return p
    raise FileNotFoundError(corpus)


def all_fields(ctx) -> dict:
    return {**ctx.fields, **ctx.lean_fields}


class Build:
    """A build: the workload it was made for, its field specs and reads, and where its databases live.
    ``w0`` is the build of the build workload (the paired streams and fixed level 100 start from it)."""

    def __init__(self, corpus: str, name: str, workload: dict[str, str], axis: str | None = None, level: int | None = None):
        ctx = R.context(corpus)
        self.corpus, self.name, self.workload = corpus, name, dict(workload)
        self.supplement: list = []  # the anticipated columns beyond W0's this build keeps (fixed levels)
        self.read_all: list = []    # the shared build-time read they come from (all extra columns of the axis)
        if name == "w0":
            self.fields, self.reads = ctx.lean_fields, ctx.lean_reads
            self.dir, self.meta = scratch(corpus), folder(corpus) / "build.json"
        else:
            spec = supplement_spec(corpus, axis)
            keep = spec["kept"][level]
            self.read_all = spec["reads"]
            # I5 (RESEARCH_DEPTH.md): QUWARTS_BUILD_GROUPS, a JSON file {table: [[column, ...], ...]}, splits a table's
            # build-time read of the anticipated columns into several prompts (the grouping is an accuracy decision:
            # a column's value depends on the columns asked with it). Columns not listed keep one read together.
            groups_file = os.environ.get("QUWARTS_BUILD_GROUPS")
            if groups_file:
                groups = json.loads(Path(groups_file).read_text())
                reads = []
                for r in self.read_all:
                    gs = [tuple(sorted(a for a in g if a in r.attributes)) for g in groups.get(r.table, [])]
                    gs = [g for g in gs if g]
                    rest = tuple(a for a in r.attributes if not any(a in g for g in gs))
                    reads += [C.Read(r.table, "supplement", g) for g in gs]
                    if rest:
                        reads.append(C.Read(r.table, "supplement", rest))
                self.read_all = reads
            self.supplement = [C.Read(r.table, "supplement", tuple(a for a in r.attributes if (r.table, a) in keep))
                               for r in self.read_all]
            self.supplement = [r for r in self.supplement if r.attributes]
            self.fields = {**ctx.lean_fields, **spec["fields"]}
            by_table = {r.table: list(r.attributes) for r in ctx.lean_reads}
            for r in self.supplement:
                by_table.setdefault(r.table, []).extend(r.attributes)
            self.reads = [C.Read(t, C.SHARED, tuple(sorted(a))) for t, a in sorted(by_table.items())]
            self.dir, self.meta = scratch(corpus) / "builds" / name, folder(corpus) / "builds" / f"{name}.json"
        self.db, self.static = self.dir / "build.db", self.dir / "static.db"

    def all_fields(self) -> dict:
        return {**R.context(self.corpus).fields, **self.fields}

    def columns(self) -> list[str]:
        return sorted(f"{r.table}.{a}" for r in self.reads for a in r.attributes)


def w0_build(corpus: str) -> Build:
    return Build(corpus, "w0", R.context(corpus).w0)


def prepare(corpus: str, caller, deadline: float | None, build: Build | None = None) -> dict[str, Any] | None:
    """The build read, the build database and the static view (the build as it is, representation frozen at
    its workload). With OpenRouter the W0 build reuses the recorded W0-description read; any missing call is
    made now and paid. None when stopped by the deadline."""

    from quwarts.core.represent import Config, build as represent
    from quwarts.core.router.executor import run_reads
    from quwarts.eval.router_provenance import build as builder

    ctx = R.context(corpus)
    b = build or w0_build(corpus)
    if b.name != "w0":
        return prepare_supplement(corpus, caller, deadline, b)
    f = folder(corpus)
    f.mkdir(parents=True, exist_ok=True)
    b.dir.mkdir(parents=True, exist_ok=True)
    if b.meta.exists() and b.db.exists() and b.static.exists():
        return json.loads(b.meta.read_text())
    j = build_journal(corpus)
    if not j.exists() and BACKEND == "openrouter":
        base = BASE / corpus
        shutil.copy2(base / "build_reads.jsonl" if VARIANT and (base / "build_reads.jsonl").exists() else old_read(corpus), j)
        if VARIANT and (base / "usage.jsonl").exists() and not (f / "usage.jsonl").exists():
            shutil.copy2(base / "usage.jsonl", f / "usage.jsonl")  # recorded usage of the shared build calls
    t_start, calls_before = time.monotonic(), len(caller.usage.new)
    ticker = Ticker(f"{corpus} build {b.name}", caller.usage)
    try:
        stats = run_reads(ctx.spec, b.reads, {}, b.fields, caller, j, WORKERS, long_documents="chain", deadline=deadline)
    finally:
        ticker.stop()
    if stats.get("stopped_at_deadline"):
        return None
    rows = rows_of(j)
    grouped, shas, missing = {}, [], []
    for r in b.reads:
        vals, used = values_and_shas(ctx.docs[r.table], r.table, list(r.attributes), b.fields, rows)
        shas += used
        missing += [f"{r.table}/{d}" for d in ctx.docs[r.table] if d not in vals]
        for d, v in vals.items():
            grouped.setdefault((r.table, C.SHARED), {})[d] = v
    columns = {f"__schema__:{r.table}": f'SELECT {", ".join(chr(34) + a + chr(34) for a in r.attributes)} FROM "{r.table}"'
               for r in ctx.reads}
    tmp = b.dir / "build.tmp.db"
    builder(ctx.spec, b.reads, grouped, b.all_fields(), {**ctx.catalog, **columns}, tmp)
    keep = {(r.table, a) for r in b.reads for a in r.attributes}
    conn = sqlite3.connect(tmp)
    with conn:
        for r in ctx.reads:
            for a in r.attributes:
                if (r.table, a) not in keep:
                    try:
                        conn.execute(f'UPDATE "{r.table}" SET "{a}" = NULL')
                    except sqlite3.OperationalError:
                        pass
    conn.close()
    R.complete(corpus, tmp)
    shutil.move(str(tmp), b.db)
    represent(b.db, b.static, ctx.spec, b.all_fields(), b.workload, Config())
    cost = charge(shas, caller.usage, rows)
    out = {"corpus": corpus, "build": b.name, "backend": BACKEND, "calls": cost["calls"], "input": cost["input"],
           "output": cost["output"], "tokens": cost["input"] + cost["output"], "cost": round(cost["cost"], 4),
           "estimated_split_calls": cost["estimated_calls"], "calls_made_now": len(caller.usage.new) - calls_before,
           "runtime_s": round(time.monotonic() - t_start, 1), "documents_missing": missing,
           "workload_queries": len(b.workload), "w0_columns" if b.name == "w0" else "columns": b.columns(),
           "maybe_truncated_calls": sum(bool(caller.usage.by_sha.get(x, {}).get("maybe_truncated")) for x in shas),
           "cut_off_calls": sum(bool(caller.usage.by_sha.get(x, {}).get("cut_off")) for x in shas)}
    b.meta.parent.mkdir(parents=True, exist_ok=True)
    b.meta.write_text(json.dumps(out, indent=1))
    return out


def write_values(db: Path, table: str, docs, attrs, vals: dict, fields: dict) -> None:
    """Commit read values of ``attrs`` for ``docs`` into ``db`` (columns added as needed)."""

    from quwarts.core.router.executor import commit_value

    conn = sqlite3.connect(db)
    with conn:
        have = {r[1].lower() for r in conn.execute(f'PRAGMA table_info("{table}")')}
        for a in attrs:
            if a.lower() not in have:
                kind = "REAL" if fields[f"{table}.{a}"].value_type in ("int", "float") else "TEXT"
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{a}" {kind}')
        ids = {C._doc_name(r[0]): r[0] for r in conn.execute(f'SELECT doc_id FROM "{table}"')}
        for d in docs:
            got = vals.get(d)
            if got is None or d not in ids:
                continue
            for a in attrs:
                v = got.get(a)
                if "raw" in ABLATE:  # E13: as returned (a list joined as the commit would), no normalization
                    v = " || ".join(str(x) for x in v if x is not None) if isinstance(v, list) else v
                    v = json.dumps(v) if isinstance(v, dict) else v
                else:
                    v = commit_value(v, fields[f"{table}.{a}"])
                conn.execute(f'UPDATE "{table}" SET "{a}" = ? WHERE doc_id = ?', (v, ids[d]))
    conn.close()


def prepare_supplement(corpus: str, caller, deadline: float | None, b: "Build") -> dict[str, Any] | None:
    """A fixed level's build: the W0 build's database plus one build-time read of the anticipated extra columns."""

    from quwarts.core.represent import Config, build as represent
    from quwarts.core.router.executor import run_reads

    ctx = R.context(corpus)
    if b.meta.exists() and b.db.exists() and b.static.exists():
        meta = json.loads(b.meta.read_text())
        if "measured_tokens" in meta:  # older metadata lacks the one-shared-read cost: recomputed from the journal
            return meta
    w0 = prepare(corpus, caller, deadline)
    if w0 is None:
        return None
    b.dir.mkdir(parents=True, exist_ok=True)
    j = build_journal(corpus)
    t_start, calls_before = time.monotonic(), len(caller.usage.new)
    ticker = Ticker(f"{corpus} build {b.name} (anticipated columns)", caller.usage)
    try:
        stats = run_reads(ctx.spec, b.read_all, {}, b.fields, caller, j, WORKERS, long_documents="chain", deadline=deadline) \
            if b.supplement else {}
    finally:
        ticker.stop()
    if stats.get("stopped_at_deadline"):
        return None
    tmp = b.dir / "build.tmp.db"
    shutil.copy2(w0_build(corpus).db, tmp)
    rows, shas, missing = rows_of(j), [], []
    keep: dict[str, tuple] = {}
    for r in b.supplement:  # a table may have several supplement reads (QUWARTS_BUILD_GROUPS)
        keep[r.table] = tuple(sorted(set(keep.get(r.table, ())) | set(r.attributes)))
    for r in b.read_all if b.supplement else []:
        attrs = [a for a in r.attributes if a in keep.get(r.table, ())]
        if not attrs:
            continue
        vals, used = values_and_shas(ctx.docs[r.table], r.table, list(r.attributes), b.fields, rows)
        shas += used
        missing += [f"{r.table}/{d}" for d in ctx.docs[r.table] if d not in vals]
        write_values(tmp, r.table, list(ctx.docs[r.table]), attrs, vals, b.fields)
    shutil.move(str(tmp), b.db)
    represent(b.db, b.static, ctx.spec, b.all_fields(), b.workload, Config())
    cost = charge(shas, caller.usage, rows)
    # What the build would cost as one shared read of W0's and the kept columns (how a system that anticipated
    # them would read them): W0's read as measured, plus, per W0 call on a table, the kept fields' lines in the
    # prompt and their answers. The separate supplement read exists only to keep values identical across levels.
    from quwarts.core.retrieve_extract.tokens import count_tokens

    extra = 0
    for r in ctx.lean_reads:
        if r.table in keep:
            _v, w0_shas = values_and_shas(ctx.docs[r.table], r.table, list(r.attributes), ctx.lean_fields, rows)
            lines = "\n".join(b.fields[f"{r.table}.{a}"].line() for a in keep[r.table])
            extra += len(w0_shas) * (count_tokens(lines) + 1 + C.Costs.ANSWER_PER_FIELD * len(keep[r.table]))
    out = {"corpus": corpus, "build": b.name, "backend": BACKEND, "design": FIXED,
           "w0_tokens": w0["tokens"], "supplement_calls": cost["calls"], "supplement_input": cost["input"],
           "supplement_output": cost["output"], "supplement_tokens": cost["input"] + cost["output"],
           "tokens": w0["tokens"] + extra, "tokens_as": "one shared read of W0's and the kept columns (estimated)",
           "measured_tokens": w0["tokens"] + cost["input"] + cost["output"],
           "cost": round((w0["tokens"] + extra) / max(1, w0["tokens"]) * w0["cost"], 4),
           "calls_made_now": len(caller.usage.new) - calls_before, "runtime_s": round(time.monotonic() - t_start, 1),
           "documents_missing": missing, "workload_queries": len(b.workload),
           "supplement_columns": sorted(f"{r.table}.{a}" for r in b.supplement for a in r.attributes),
           "shared_read_columns": sorted(f"{r.table}.{a}" for r in b.read_all for a in r.attributes),
           "maybe_truncated_calls": sum(bool(caller.usage.by_sha.get(x, {}).get("maybe_truncated")) for x in shas),
           "cut_off_calls": sum(bool(caller.usage.by_sha.get(x, {}).get("cut_off")) for x in shas)}
    b.meta.parent.mkdir(parents=True, exist_ok=True)
    b.meta.write_text(json.dumps(out, indent=1))
    return out


class Ticker:
    """A progress line every minute while a long read runs (calls made, tokens, seconds)."""

    def __init__(self, label: str, usage: "Usage", every: float = 60.0):
        self.label, self.usage, self.start, self.n0 = label, usage, time.monotonic(), len(usage.new)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(every,), daemon=True)
        self._thread.start()

    def _run(self, every: float) -> None:
        while not self._stop.wait(every):
            new = self.usage.new[self.n0:]
            print(f"  {self.label}: {len(new)} calls, {sum(u['input'] for u in new) / 1e6:.2f}M in / "
                  f"{sum(u['output'] for u in new) / 1e3:.0f}k out, {time.monotonic() - self.start:.0f}s", flush=True)

    def stop(self) -> None:
        self._stop.set()


def fixed_design(corpus: str, axis: str = "attribute") -> dict[str, Any]:
    """The fixed test queries of an axis and, per level, which new columns the build does not anticipate.

    Drift is in columns, not queries (design v4). The new columns are those the test queries need beyond W0's.
    At level p a nested set of them is left out of the build, and every test query that uses one of them is
    unanticipated (outside the build workload), so nothing pulls the column back in; every other test query is
    anticipated. (Withholding queries instead, as v1-v3 did, left almost every column in the build: a column is
    missing only if all the queries using it are withheld, and many queries share a column, so 25-75% of the
    queries withheld still meant 0-1 of 7 columns missing on player.) The withheld columns are prefixes of one
    order of the new columns, so the levels are nested; among seeded candidate orders (all of them when there are
    at most 7 columns), the one whose prefixes put the share of unanticipated queries closest to 25/50/75% is
    used. Each level records its real shares (columns missing, queries unanticipated): they are the x-axis."""

    import itertools
    import random

    ctx = R.context(corpus)
    path = folder(corpus) / f"{FIXED}_{axis}_design.json"
    if path.exists():
        return json.loads(path.read_text())
    if axis == "attribute_pool":
        # Every valid attribute-drift variant of the paired design (up to 3 per base query), not only the one per
        # base query in the attribute/100 stream: 2-4x the test queries, so one query weighs less. They arrive in a
        # seeded random order.
        test = list(dict.fromkeys(ctx.designs[0]["attribute_pool"]))
        random.Random(FIXED_SEED + 1).shuffle(test)
    else:
        test = ctx.designs[0]["streams"][f"{axis}/100"]
    queries = list(dict.fromkeys(test))
    w0 = {(r.table, a) for r in ctx.lean_reads for a in r.attributes}

    def columns(workload: dict[str, str]) -> set:
        return {(r.table, a) for r in C.design(ctx.spec, {**ctx.w0, **workload})[1] for a in r.attributes} - w0

    uses = {q: columns({q: ctx.catalog[q]}) for q in queries}
    new = sorted(set().union(*uses.values()))

    def unanticipated(withheld: set) -> list[str]:
        return [q for q in queries if uses[q] & withheld]

    targets = [25, 50, 75]
    rng = random.Random(FIXED_SEED)
    if len(new) <= 7:
        orders = [list(o) for o in itertools.permutations(new)]
    else:
        orders = []
        for _ in range(5000):
            o = list(new)
            rng.shuffle(o)
            orders.append(o)
    best = None
    scored = []
    for o in orders:
        share = [100 * len(unanticipated(set(o[:k]))) / len(queries) for k in range(len(o) + 1)]
        ks, k0, cost = [], 0, 0.0
        for t in targets:  # the prefix closest to the target, never shorter than the previous level's
            k = min(range(k0, len(o) + 1), key=lambda j: (abs(share[j] - t), j))
            ks.append(k)
            k0 = k
            cost += abs(share[k] - t)
        scored.append((cost, o, ks))
        if best is None or cost < best[0] - 1e-9:
            best = (cost, o, ks)
    if FIXED_SEED:
        # Robustness draws: a seeded choice among the orders whose level shares are within 10 percentage points
        # (summed over the three levels) of the best, so the withheld columns differ at about the same drift.
        near = [x for x in scored if x[0] <= best[0] + 10]
        best = random.Random(f"order:{FIXED_SEED}").choice(near)
    _cost, order, ks = best
    prefix = {0: 0, **dict(zip(targets, ks)), 100: len(order)}
    levels = {}
    for p in sorted(FIXED_LEVELS):
        withheld_cols = set(order[:prefix[p]])
        out_q = unanticipated(withheld_cols)
        anticipated = [q for q in queries if q not in out_q]
        missing = set(new) - columns({q: ctx.catalog[q] for q in anticipated})  # the columns the build really lacks
        levels[str(p)] = {"withheld_columns": sorted(f"{t}.{a}" for t, a in withheld_cols),
                          "missing_columns": sorted(f"{t}.{a}" for t, a in missing),
                          "columns_missing_share": round(len(missing) / len(new), 3) if new else 0.0,
                          "queries_unanticipated_share": round(len(out_q) / len(queries), 3),
                          "withheld": out_q, "anticipated": anticipated}
    out = {"corpus": corpus, "axis": axis, "design": FIXED, "seed": FIXED_SEED, "test": test,
           "new_columns": [f"{t}.{a}" for t, a in order], "levels": levels,
           "note": "level p: a nested set of the new columns is left out of the build; test queries using one of "
                   "them are unanticipated. The shares are the real drift of each level."}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    return out


_SUPPLEMENT: dict = {}


def supplement_spec(corpus: str, axis: str) -> dict[str, Any]:
    """The shared build-time read of an axis's extra columns: its reads, each column's field spec, and the
    columns each level keeps (``{level: {(table, attr)}}``)."""

    key = (corpus, axis)
    if key in _SUPPLEMENT:
        return _SUPPLEMENT[key]
    ctx = R.context(corpus)
    d = fixed_design(corpus, axis)
    w0 = {(r.table, a) for r in ctx.lean_reads for a in r.attributes}
    kept = {}
    for p, lvl in d["levels"].items():
        _f, reads = C.design(ctx.spec, {**ctx.w0, **{q: ctx.catalog[q] for q in lvl["anticipated"]}})
        kept[int(p)] = {(r.table, a) for r in reads for a in r.attributes} - w0
    every = set().union(*kept.values())
    fields = {}
    for t, a in sorted(every):
        top = max(p for p, cols in kept.items() if (t, a) in cols)  # anticipated at every level up to here
        anticipated = d["levels"][str(top)]["anticipated"]
        users = {q: ctx.catalog[q] for q in anticipated
                 if a in C.query_attributes(ctx.spec, q, ctx.catalog[q], {**ctx.w0, q: ctx.catalog[q]}).get(t, set())}
        wf, _r = C.design(ctx.spec, {**ctx.w0, **(users or {q: ctx.catalog[q] for q in anticipated})})
        fields[f"{t}.{a}"] = wf[f"{t}.{a}"]
    reads = [C.Read(t, "supplement", tuple(sorted(a for tt, a in every if tt == t))) for t in sorted({t for t, _a in every})]
    _SUPPLEMENT[key] = {"reads": reads, "fields": fields, "kept": kept}
    return _SUPPLEMENT[key]


def fixed_build(corpus: str, axis: str, p: int) -> Build:
    ctx = R.context(corpus)
    lvl = fixed_design(corpus, axis)["levels"][str(p)]
    if not lvl["anticipated"]:
        return w0_build(corpus)  # nothing anticipated: the W0 build itself
    return Build(corpus, f"{FIXED}_{axis}_{p}", {**ctx.w0, **{q: ctx.catalog[q] for q in lvl["anticipated"]}}, axis, p)


# ------------------------------------------------------------------------------------------ budget policies

# QUWARTS_BUDGET_POLICY (budgeted streams only; the budget itself is never exceeded):
#   fcfs    any patch that fits the remaining budget (the default)
#   cap     also skip a patch estimated above QUWARTS_BUDGET_CAP (default 0.25) of the whole budget
#   pace    spend no faster than the stream advances: after query k of n, at most budget * (k / n + 0.25)
#   fragile skip a query whose answer is MIN/MAX over a text column (one extreme string per group: across the five
#           corpora these 45 queries score 0.03 on average yet take a third of the patch tokens); a later query that
#           needs the same columns patches them itself
#   oracle  hindsight reference, not a policy: skip a query whose patch bought nothing in the unlimited stream at the
#           same level (QUWARTS_BUDGET_ORACLE: the E2.2 patches.csv), so the budget goes to patches that paid off
#   knapsack offline best set (E3.1), not a policy: only the patches the knapsack over the whole unlimited stream chose
#           for this budget and level (QUWARTS_BUDGET_ALLOW: exp_analysis knapsack's allow.json)
#   forecast extract now only what the known workload (W0 and the queries seen so far in the stream) asks for again, or
#           what is cheap: a patch whose columns no other known query uses is skipped when it costs more than
#           QUWARTS_FORECAST_SMALL (default 0.10) of the remaining budget. From the finding that a patch's value is
#           deferred and shared (RESEARCH_DEPTH.md, P4): it forecasts reuse instead of judging a patch by its own query.
POLICY = os.environ.get("QUWARTS_BUDGET_POLICY", "fcfs")
assert POLICY in ("fcfs", "cap", "pace", "oracle", "fragile", "knapsack", "forecast"), POLICY
_ORACLE: dict[str, set] = {}
_DEMAND: dict[str, dict[str, set]] = {}  # corpus -> known query -> the columns it uses


def forecast_allows(corpus: str, qid: str, missing: dict, seen: list[str], est: int, spent: int, budget: int) -> bool:
    ctx = R.context(corpus)
    dem = _DEMAND.setdefault(corpus, {})
    for q, sql in list(ctx.w0.items()) + [(s, ctx.catalog[s]) for s in seen if s in ctx.catalog]:
        if q not in dem:
            need = C.query_attributes(ctx.spec, q, sql, {q: sql})
            dem[q] = {f"{t}.{a}" for t, attrs in need.items() for a in attrs}
    cols = {f"{t}.{a}" for t, attrs in missing.items() for a in attrs}
    known = set(ctx.w0) | set(seen)
    reuse = sum(1 for q, cs in dem.items() if q != qid and q in known and cs & cols)
    small = float(os.environ.get("QUWARTS_FORECAST_SMALL", 0.10))
    return reuse >= 1 or est <= small * max(budget - spent, 0)
_ALLOW: dict[str, list] = {}  # E3.1 knapsack choices, "b<budget>/<level>" -> allowed qids


def fragile_query(corpus: str, qid: str) -> bool:
    """MIN or MAX over a text column (by the field's SQL-derived type)."""

    import sqlglot
    from sqlglot import exp

    ctx = R.context(corpus)
    try:
        tree = sqlglot.parse_one(ctx.catalog[qid], read="sqlite")
    except Exception:  # noqa: BLE001
        return False
    for f in tree.find_all(exp.Min, exp.Max):
        for col in f.find_all(exp.Column):
            q = [k for k in ctx.fields if k.split(".", 1)[1] == col.name]
            if q and ctx.fields[q[0]].value_type not in ("int", "float"):
                return True
    return False


def policy_allows(corpus: str, key: str, qid: str, pos: int, n: int, est: int, spent: int, budget: int,
                  missing: dict | None = None, seen: list[str] | None = None) -> bool:
    if POLICY == "forecast":
        return forecast_allows(corpus, qid, missing or {}, seen or [], est, spent, budget)
    if POLICY == "cap":
        return est <= float(os.environ.get("QUWARTS_BUDGET_CAP", 0.25)) * budget
    if POLICY == "pace":
        return spent + est <= budget * ((pos + 1) / n + 0.25)
    if POLICY == "fragile":
        return not fragile_query(corpus, qid)
    if POLICY == "oracle":
        level = key.split("/")[1]
        if level not in _ORACLE:
            import csv

            rows = csv.DictReader(open(os.environ["QUWARTS_BUDGET_ORACLE"]))
            _ORACLE[level] = {r["qid"] for r in rows
                              if r["budget"] == "" and r["level"] == level and r["no_value"] == "True"}
        return qid not in _ORACLE[level]
    if POLICY == "knapsack":  # E3.1: only the patches the offline knapsack chose for this budget and level
        if not _ALLOW:
            _ALLOW.update(json.load(open(os.environ["QUWARTS_BUDGET_ALLOW"])))
        head, level = key.split("/")
        return qid in _ALLOW.get(f"{head.split('-')[0][len(FIXED):]}/{level}", ())
    return True


# ------------------------------------------------------------------------------------------ one stream

class Stream:
    """The controller on one stream, from the build, with real reads. Resumable after every query."""

    def __init__(self, corpus: str, key: str, caller, build: Build | None = None, stream: list[str] | None = None,
                 budget: int | None = None):
        self.corpus, self.key, self.caller = corpus, key, caller
        self.budget = budget  # patch tokens the stream may spend (None: unlimited)
        self.ctx = R.context(corpus)
        self.build = build or w0_build(corpus)
        self.dir = scratch(corpus) / key.replace("/", "_")
        self.state_path = folder(corpus) / "state" / f"{key.replace('/', '_')}.json"
        # bprompt: a patch's prompts are the build's, so it reads (and journals) where the build did
        self.journal = build_journal(corpus) if "bprompt" in ABLATE else folder(corpus) / "patch_reads.jsonl"
        self.stream = stream or self.ctx.designs[0]["streams"][key]
        self.t0 = set(self.ctx.designs[0]["in_distribution"])
        if self.state_path.exists():
            self.st = json.loads(self.state_path.read_text())
        else:
            self.dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.build.db, self.dir / "master.db")
            self.st = {"pos": 0, "seen": {}, "records": [], "partial": None,
                       "mat": [[r.table, a, sorted(self.ctx.names[r.table])] for r in self.build.reads for a in r.attributes]}
        self.mat = {(t, a): set(d) for t, a, d in self.st["mat"]}

    def save(self) -> None:
        self.st["mat"] = [[t, a, sorted(d)] for (t, a), d in self.mat.items()]
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.st))
        tmp.replace(self.state_path)

    def fully(self, t: str, a: str) -> bool:
        return self.mat.get((t, a), set()) >= set(self.ctx.names[t])

    def view(self, workload, fields, dest: Path) -> Path:
        from quwarts.core.represent import Config, build

        build(self.dir / "master.db", dest, self.ctx.spec, fields, workload, Config(t0="rawview" not in ABLATE))
        return dest

    def step(self, stop_at: float) -> None:
        """The next query. Stopped by the deadline (``Incomplete``), it is redone from the journal next time,
        its time and paid calls so far carried over."""

        qid = self.stream[self.st["pos"]]
        partial = self.st["partial"] or {"qid": qid, "seconds": 0.0, "paid": {"calls": 0, "input": 0, "output": 0, "cost": 0.0}}
        t_start = time.monotonic()
        paid_from = len(self.caller.usage.new)
        try:
            self._step(stop_at, partial, t_start, paid_from)
        except Incomplete:
            new = self.caller.usage.new[paid_from:]
            paid = {k: partial["paid"][k] + sum(u[k] for u in new) for k in ("input", "output", "cost")}
            paid["calls"] = partial["paid"]["calls"] + len(new)
            self.st["partial"] = {"qid": qid, "seconds": partial["seconds"] + time.monotonic() - t_start, "paid": paid}
            self.save()
            raise

    def _step(self, stop_at: float, partial: dict, t_start: float, paid_from: int) -> None:
        from quwarts.core.router.executor import commit_value, run_reads

        ctx, pos = self.ctx, self.st["pos"]
        qid = self.stream[pos]
        sql = ctx.catalog[qid]
        if "noreuse" in ABLATE:  # E13: back to the build before every query (earlier patches are not kept)
            shutil.copy2(self.build.db, self.dir / "master.db")
            self.mat = {(r.table, a): set(ctx.names[r.table]) for r in self.build.reads for a in r.attributes}
        seen = {**self.build.workload, **self.st["seen"], qid: sql}
        fields_seen, reads_seen = C.design(ctx.spec, seen)  # the build's workload and the queries so far
        if VARIANT in ("no_literals", "no_usage") or ABLATE & {"nodesc", "nousage"}:
            fields_seen = patch_variant(ctx, seen, fields_seen)
        if CONTRACT:  # I6: the workload declares the label vocabulary of the columns it groups by
            fields_seen = {k: (replace_field(f, choices=tuple(CONTRACT[k])) if k in CONTRACT and k not in ctx.lean_fields else f)
                           for k, f in fields_seen.items()}
        F = {**self.build.all_fields(), **fields_seen}
        need = C.query_attributes(ctx.spec, qid, sql, seen)
        views = self.dir / "views"
        pre = views / f"{pos:03d}.db"
        built = False
        missing, scope = {}, {}
        for t, attrs in need.items():
            if t not in ctx.names:
                continue
            lacking = {a for a in attrs if not self.fully(t, a)}
            if not lacking:
                continue
            known = {a for (tt, a) in self.mat if tt == t and self.fully(t, a)}
            cond = C.pushdown_conjuncts(sql, t, known) if len(need) == 1 and "noscope" not in ABLATE else None
            rows = None
            if cond:
                if not built:
                    self.view(seen, F, pre)
                    built = True
                rows = C.evaluate_scope(pre, t, cond)
            docs = list(ctx.names[t]) if rows is None else [d for d in ctx.names[t] if d in rows]
            todo = [d for d in docs if any(d not in self.mat.get((t, a), set()) for a in lacking)]
            if todo:
                missing[t], scope[t] = sorted(lacking), todo
        skipped = {}
        # The patch's estimated cost (the controller's per-document read estimate, the columns it would ask for),
        # recorded on every patch so estimates can be checked against the tokens charged.
        est = 0
        for t in missing:
            batch = sorted({a for r in reads_seen if r.table == t for a in r.attributes
                            if not self.fully(t, a) and f"{t}.{a}" in fields_seen
                            and (not ABLATE & {"nobatch", "noreuse"} or a in missing[t])})
            for d in scope[t]:
                attrs = [a for a in batch if d not in self.mat.get((t, a), set())]
                if attrs:
                    est += ctx.costs.read(t, d, [fields_seen[f"{t}.{a}"] for a in attrs])
        if missing and self.budget is not None:
            # Over the remaining budget the patch is skipped: the query is answered from what is extracted, and
            # later (cheaper) patches may still fit.
            spent = sum(r["input_tokens"] + r["output_tokens"] for r in self.st["records"])
            if spent + est > self.budget or not policy_allows(self.corpus, self.key, qid, pos, len(self.stream),
                                                              est, spent, self.budget, missing=missing,
                                                              seen=[r["qid"] for r in self.st["records"]]):
                skipped, missing = missing, {}
        shas, read_docs, fetched = [], 0, {}
        for t in missing:
            batch = sorted({a for r in reads_seen if r.table == t for a in r.attributes
                            if not self.fully(t, a) and f"{t}.{a}" in fields_seen
                            and (not ABLATE & {"nobatch", "noreuse"} or a in missing[t])})
            groups: dict[tuple, list[str]] = {}
            for d in scope[t]:
                attrs = tuple(a for a in batch if d not in self.mat.get((t, a), set()))
                if attrs:
                    groups.setdefault(attrs, []).append(d)
            known_t = sorted(a for r in reads_seen if r.table == t for a in r.attributes
                             if self.fully(t, a) and f"{t}.{a}" in fields_seen) if VARIANT == "with_known" else []
            FR, together = fields_seen, ()  # E14: the read's field specs, and the build's co-read columns
            if ABLATE & {"bfields", "bgroup", "bprompt"}:
                supp = supplement_spec(self.corpus, self.key.split("/")[0].split("-", 1)[1])
                build_first = ABLATE & {"bfields", "bprompt"}
                FR = {**fields_seen, **supp["fields"]} if build_first else {**supp["fields"], **fields_seen}
                if ABLATE & {"bgroup", "bprompt"}:
                    together = next((r.attributes for r in supp["reads"] if r.table == t), ())
            for attrs, docs in groups.items():
                asked = tuple(sorted(set(attrs) | set(known_t) | set(together)))
                read = C.Read(t, "patch:" + ",".join(asked), asked)
                vspec, root = view_spec(ctx.spec, ctx.docs, t, docs)
                try:
                    left = left_of(stop_at)
                    if left is not None and left < 10:
                        raise Incomplete()
                    stats = run_reads(vspec, [read], {}, FR, self.caller, self.journal, WORKERS,
                                      long_documents="head" if "head" in ABLATE else "chain",
                                      deadline=None if left is None else left - 8)
                finally:
                    shutil.rmtree(root, ignore_errors=True)
                if stats.get("stopped_at_deadline"):
                    raise Incomplete()
                by = rows_of(self.journal)
                vals, used = values_and_shas({d: ctx.docs[t][d] for d in docs}, t, list(asked), FR, by,
                                             head="head" in ABLATE)
                shas += used
                read_docs += len(docs)
                write_values(self.dir / "master.db", t, docs, attrs, vals, FR)
                for a in attrs:
                    self.mat.setdefault((t, a), set()).update(d for d in docs if d in vals)
                    fetched[f"{t}.{a}"] = fetched.get(f"{t}.{a}", 0) + sum(d in vals for d in docs)
                for a in together:  # E14 bgroup / bprompt: the other columns read with them are kept, as the build's are
                    fresh = [d for d in docs if d in vals and d not in self.mat.get((t, a), set())]
                    if a in attrs or not fresh:
                        continue
                    write_values(self.dir / "master.db", t, fresh, [a], vals, FR)
                    self.mat.setdefault((t, a), set()).update(fresh)
                    fetched[f"{t}.{a}"] = fetched.get(f"{t}.{a}", 0) + len(fresh)
        if missing or not built:
            self.view(seen, F, pre)  # the served view after the patch
        seconds = partial["seconds"] + (time.monotonic() - t_start)
        new = self.caller.usage.new[paid_from:]
        paid = {k: partial["paid"][k] + sum(u[k] for u in new) for k in ("input", "output", "cost")}
        paid["calls"] = partial["paid"]["calls"] + len(new)
        charged = charge(shas, self.caller.usage, rows_of(self.journal)) if shas else {"calls": 0, "input": 0, "output": 0, "cost": 0.0}
        self.st["records"].append({
            "pos": pos, "qid": qid, "drift": qid not in self.t0, "anticipated": qid in self.build.workload,
            "action": "patch" if missing else ("skipped" if skipped else "answer"),
            "missing": missing or skipped, "est_tokens": est, "scope_docs": sum(len(v) for v in scope.values()), "docs_read": read_docs,
            "fetched": fetched, "runtime_s": round(seconds, 2),
            "calls": charged["calls"], "input_tokens": charged["input"], "output_tokens": charged["output"],
            "cost_usd": round(charged["cost"], 6), "paid": {k: (round(v, 6) if k == "cost" else v) for k, v in paid.items()},
            "maybe_truncated_calls": sum(bool(self.caller.usage.by_sha.get(x, {}).get("maybe_truncated")) for x in shas),
            "cut_off_calls": sum(bool(self.caller.usage.by_sha.get(x, {}).get("cut_off")) for x in shas),
            "view": str(pre), "digest": R.digest(pre, sql)})
        self.st["seen"][qid] = sql
        self.st["pos"] = pos + 1
        self.st["partial"] = None
        self.save()


# ------------------------------------------------------------------------------------------ scores

class LiveScorer(R.Scorer):
    def __init__(self, corpus: str):
        super().__init__(corpus)
        self.path = folder(corpus) / "scores.json"
        self.cache = json.loads(self.path.read_text()) if self.path.exists() else {"benchmark": {}, "tolerant": {}}


def bar(done: int, total: int, width: int = 20) -> str:
    k = int(width * done / total) if total else width
    return "[" + "#" * k + "-" * (width - k) + f"] {done}/{total}"


def plan(corpus: str, which: str, axes: list[str]) -> list[tuple[str, Build | None, list[str] | None]]:
    """(stream key, build, stream) in run order. Paired streams start from the W0 build; fixed levels from
    their own build (built when first reached)."""

    ctx = R.context(corpus)
    out = []
    if which in ("fixed", "fixed+headline", "everything"):
        for axis in axes:
            if axis not in ("attribute", "attribute_pool"):
                # Levels are sets of new columns left out of the build; value drift adds no column (new constants on
                # known columns) and the combined streams mix in such queries, so neither has column levels.
                print(f"{corpus}: no fixed levels for the {axis} axis (drift in constants, not columns); skipped", flush=True)
                continue
            test = fixed_design(corpus, axis)["test"]
            out += [(f"{FIXED}-{axis}/{p}", None, test) for p in FIXED_LEVELS]
    if which == "budget":
        for axis in axes:
            if axis in ("attribute", "attribute_pool"):
                test = fixed_design(corpus, axis)["test"]
                out += [(f"{FIXED}b{b:03d}-{axis}/{p}", None, test) for b in BUDGETS for p in FIXED_LEVELS]
    if which in ("headline", "all", "fixed+headline", "everything"):
        keys = HEADLINE if which in ("headline", "fixed+headline") else ORDER
        out += [(k, None, None) for k in ORDER if k in keys and k in ctx.designs[0]["streams"]]
    only = [k for k in os.environ.get("QUWARTS_LIVE_ONLY", "").split(",") if k]  # e.g. fixed4-attribute_pool/100
    if only:
        out = [o for o in out if o[0] in only]
    return out


def run(corpus: str, deadline: float, which: str = "headline", axes: list[str] | None = None) -> dict[str, Any]:
    """Every planned stream of a corpus; resumable. ``deadline`` <= 0: no deadline (a batch job)."""

    t0 = time.monotonic()
    stop_at = float("inf") if deadline <= 0 else t0 + deadline
    stop = lambda: time.monotonic() > stop_at - 12  # noqa: E731
    usage = Usage(folder(corpus) / "usage.jsonl")
    caller = make_caller(usage)
    caller.usage = usage
    if prepare(corpus, caller, left_of(stop_at) if stop_at == float("inf") else max(5.0, stop_at - time.monotonic() - 20)) is None:
        return {"corpus": corpus, "status": "build read in progress"}
    ctx = R.context(corpus)
    scorer = LiveScorer(corpus)
    streams = plan(corpus, which, axes or ["attribute"])
    out_dir = folder(corpus) / "streams"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for key, _b, stream in streams:
        final = out_dir / f"{key.replace('/', '_')}.jsonl"
        if final.exists():
            continue
        budget = None
        if key.startswith(FIXED + "-") or key.startswith(FIXED + "b"):
            head, p = key.split("/")
            name, axis = head.split("-", 1)
            build = fixed_build(corpus, axis, int(p))
            if prepare(corpus, caller, left_of(stop_at), build) is None:
                lines.append(f"{corpus:8s} {key:22s} build read in progress")
                break
            if name != FIXED:  # a budgeted stream: % of the unlimited stream's patch tokens at 100% drift
                full = out_dir / f"{FIXED}-{axis}_100.jsonl"
                if not full.exists():
                    lines.append(f"{corpus:8s} {key:22s} needs {full.name} (run --streams fixed first)")
                    break
                spend = sum(r["input_tokens"] + r["output_tokens"] for r in map(json.loads, full.read_text().splitlines()))
                budget = round(int(name[len(FIXED) + 1:]) / 100 * spend)
        else:
            build = w0_build(corpus)
        s = Stream(corpus, key, caller, build, stream, budget)
        n = len(s.stream)
        try:
            while s.st["pos"] < n:
                if time.monotonic() > stop_at - 25:
                    raise Incomplete()
                s.step(stop_at)
                r = s.st["records"][-1]
                tot = s.st["records"]
                print(f"{corpus:8s} {key:22s} {bar(len(tot), n)}  {r['action']:6s} docs {r['docs_read']:4d}  "
                      f"{(r['input_tokens'] + r['output_tokens']) / 1e3:7.1f}k tok  {r['runtime_s']:6.1f}s  | stream "
                      f"{sum(x['input_tokens'] + x['output_tokens'] for x in tot) / 1e6:.2f}M tok ${sum(x['cost_usd'] for x in tot):.3f}",
                      flush=True)
        except Incomplete:
            s.save()
            lines.append(f"{corpus:8s} {key:22s} queries {bar(s.st['pos'], n)}")
            break
        static = build.static
        items = [(r["qid"], r["digest"], Path(r["view"])) for r in s.st["records"]]
        items += [(q, R.digest(static, ctx.catalog[q]), static) for q in dict.fromkeys(s.stream)]
        if not scorer.run(items, stop):
            lines.append(f"{corpus:8s} {key:22s} queries {bar(n, n)} scoring")
            break
        recs = []
        for r in s.st["records"]:
            sd = R.digest(static, ctx.catalog[r["qid"]])
            recs.append({**{k: v for k, v in r.items() if k not in ("view",)}, "build": build.name, "backend": BACKEND,
                         "benchmark": scorer.get("benchmark", r["qid"], r["digest"]),
                         "tolerant": scorer.get("tolerant", r["qid"], r["digest"]),
                         "static_benchmark": scorer.get("benchmark", r["qid"], sd),
                         "static_tolerant": scorer.get("tolerant", r["qid"], sd)})
        final.write_text("".join(json.dumps(r) + "\n" for r in recs))
        if not os.environ.get("QUWARTS_KEEP_VIEWS"):  # kept for audits
            shutil.rmtree(s.dir, ignore_errors=True)
        m = sum(r["benchmark"] for r in recs) / len(recs)
        print(f"{corpus:8s} {key:22s} done: accuracy {m:.3f}, patches {sum(r['action'] == 'patch' for r in recs)}", flush=True)
    done = sum((out_dir / f"{k.replace('/', '_')}.jsonl").exists() for k, _b, _s in streams)
    spent = sum(u["cost"] for u in usage.by_sha.values())
    head = (f"{corpus:8s} streams {bar(done, len(streams))}  {BACKEND}: {'list-price equivalent ' if BACKEND == 'ollama' else 'paid '}"
            f"${spent:.3f}, {sum(u['input'] for u in usage.by_sha.values())/1e6:.2f}M in / {sum(u['output'] for u in usage.by_sha.values())/1e6:.2f}M out")
    return {"corpus": corpus, "status": "complete" if done == len(streams) else "running", "progress": [head] + lines,
            "elapsed": round(time.monotonic() - t0, 1)}


# ------------------------------------------------------------------------------------------ report

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--deadline", type=float, default=165)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--streams", default="headline", choices=["headline", "all", "fixed", "fixed+headline", "everything", "budget"])
    ap.add_argument("--axes", default="attribute", help="fixed levels: comma list of attribute, value, combined")
    ap.add_argument("--workers", type=int, help="concurrent model calls (default QUWARTS_WORKERS or 24)")
    a = ap.parse_args(argv)
    if a.workers:
        global WORKERS
        WORKERS = a.workers
    if a.run:
        corpora = (ALL_CORPORA if BACKEND == "ollama" else CORPORA) if a.corpus == "all" else a.corpus.split(",")
        for corpus in corpora:
            out = run(corpus, a.deadline, a.streams, a.axes.split(","))
            print("\n".join(out.pop("progress", [])))
            print(json.dumps(out), flush=True)
    if a.report:
        from quwarts.eval import drift_live_report
        print(drift_live_report.write())
    return 0


if __name__ == "__main__":
    sys.exit(main())
