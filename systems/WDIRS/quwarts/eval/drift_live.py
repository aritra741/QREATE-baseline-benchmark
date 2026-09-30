"""Real (not replayed) drift runs on the template-paired streams. AUDIT for scores only: reads gold.

    QUWARTS_DRIFT_DESIGN=drift_paired python -m quwarts.eval.drift_live --corpus art --run --deadline 165
    QUWARTS_DRIFT_DESIGN=drift_paired python -m quwarts.eval.drift_live --report

What is real here. The replay (``drift_run``) answered every drifted query from a full read made before the
stream, so drift could not hurt QuWARTS's data. Here nothing is read ahead:

* Build. One shared read of every document with the build workload's (W0's) columns, descriptions and usage
  phrases only (the ``old`` read of ``rebuild_quality``; any missing call is made now and paid).
* Stream. Queries arrive in order and are answered in order. For each query the system
  1. adds the query's literals to the online representation (the query itself, never its answer),
  2. finds the columns it needs that are not yet extracted for every document,
  3. narrows the documents to those that can affect the answer (WHERE conjuncts over complete columns,
     evaluated on the served view),
  4. reads those documents now, with the new column's description and a usage phrase from the queries seen
     so far that use it; a document being read also gets every other known column it still lacks (a read
     costs about the document's length, whatever the number of fields),
  5. answers from the served view. No rebuild: once a column is fetched, it is reused for free.
* Every call's input and output tokens and OpenRouter's reported cost are recorded. Each stream starts from
  the build, so its patch cost is its own; calls whose exact prompt an earlier stream already made are
  reused from the journal and charged to the stream at their recorded usage ("charged"), and "paid" counts
  only calls made for the first time.

Baselines, per position: ``static`` (the build as it is, representation frozen at W0: what a per-build
extractor serves), and the replay's ``reference`` (the same controller on a full read of every column made
before the stream: the accuracy with no drift cost).
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
ORDER = ["attribute/100", "combined/100", "value/100", "attribute/0", "attribute/50", "combined/50",
         "attribute/25", "attribute/75", "combined/0", "combined/25", "combined/75", "value/0", "value/25",
         "value/50", "value/75", "attribute/gradual", "combined/gradual", "value/gradual"]
HEADLINE = ["attribute/100", "value/100", "attribute/0", "combined/0", "value/0"]
WORKERS = 24
PRICE = {"input": 0.10 / 1e6, "output": 0.20 / 1e6}  # OpenRouter list price of qwen/qwen-2.5-7b-instruct
# Ablations of the patch prompt (QUWARTS_LIVE_VARIANT): ``no_literals`` keeps a patched column's usage phrase but
# drops the example constants from the queries; ``no_usage`` gives a patched column no usage phrase. The build is
# the same read in every variant.
VARIANT = os.environ.get("QUWARTS_LIVE_VARIANT", "")
assert VARIANT in ("", "no_literals", "no_usage"), VARIANT
BASE = R.RESULTS / "drift_live"
LIVE = BASE / "variants" / VARIANT if VARIANT else BASE
SCRATCH = Path.home() / "quwarts_scratch" / ("drift_live" + (f"_{VARIANT}" if VARIANT else ""))


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


def values_and_shas(docs: dict[str, Path], table: str, attrs: list[str], fields, by_sha) -> tuple[dict, list[str]]:
    """``read_values`` for one table and field list, also returning the prompt hashes it used."""

    from quwarts.core.retrieve_extract.tokens import count_tokens
    from quwarts.core.router import chunked
    from quwarts.core.router.context_probe import V3, render_prompt, truncate
    from quwarts.core.router.corpus_features import read_document
    from quwarts.core.router.probes import parse_fields

    window = int(V3["window_tokens"])
    specs = [fields[f"{table}.{a}"] for a in attrs]
    values, used = {}, []
    for doc, path in docs.items():
        text = read_document(path)
        if count_tokens(text) <= window:
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


def patch_variant(ctx, seen, fields):
    """The patch prompt's ablation for columns outside the build (the build's own fields are unchanged)."""

    from dataclasses import replace

    from quwarts.core.router.workload_features import usage_phrase, workload_features

    uses = workload_features(ctx.spec, seen)["attributes"] if VARIANT == "no_literals" else {}
    out = {}
    for k, f in fields.items():
        if k in ctx.lean_fields:
            out[k] = f
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


def prepare(corpus: str, caller, deadline: float) -> dict[str, Any] | None:
    """The build read (reusing the recorded W0-description read), the build database and the static view."""

    from quwarts.core.represent import Config, build
    from quwarts.core.router.executor import run_reads
    from quwarts.eval.router_provenance import build as builder

    ctx = R.context(corpus)
    f, s = folder(corpus), scratch(corpus)
    f.mkdir(parents=True, exist_ok=True)
    s.mkdir(parents=True, exist_ok=True)
    done = f / "build.json"
    if done.exists() and (s / "build.db").exists() and (s / "static.db").exists():
        return json.loads(done.read_text())
    j = build_journal(corpus)
    if not j.exists():
        base = BASE / corpus
        shutil.copy2(base / "build_reads.jsonl" if VARIANT and (base / "build_reads.jsonl").exists() else old_read(corpus), j)
        if VARIANT and (base / "usage.jsonl").exists() and not (f / "usage.jsonl").exists():
            shutil.copy2(base / "usage.jsonl", f / "usage.jsonl")  # recorded usage of the shared build calls
    stats = run_reads(ctx.spec, ctx.lean_reads, {}, ctx.lean_fields, caller, j, 12, long_documents="chain", deadline=deadline)
    if stats.get("stopped_at_deadline"):
        return None
    rows = rows_of(j)
    grouped, shas, missing = {}, [], []
    for r in ctx.lean_reads:
        vals, used = values_and_shas(ctx.docs[r.table], r.table, list(r.attributes), ctx.lean_fields, rows)
        shas += used
        missing += [f"{r.table}/{d}" for d in ctx.docs[r.table] if d not in vals]
        for d, v in vals.items():
            grouped.setdefault((r.table, C.SHARED), {})[d] = v
    columns = {f"__schema__:{r.table}": f'SELECT {", ".join(chr(34) + a + chr(34) for a in r.attributes)} FROM "{r.table}"'
               for r in ctx.reads}
    tmp = s / "build.tmp.db"
    builder(ctx.spec, ctx.lean_reads, grouped, all_fields(ctx), {**ctx.catalog, **columns}, tmp)
    keep = {(r.table, a) for r in ctx.lean_reads for a in r.attributes}
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
    shutil.move(str(tmp), s / "build.db")
    build(s / "build.db", s / "static.db", ctx.spec, all_fields(ctx), ctx.w0, Config())
    usage = caller.usage
    cost = charge(shas, usage, rows)
    out = {"corpus": corpus, "calls": cost["calls"], "input": cost["input"], "output": cost["output"],
           "tokens": cost["input"] + cost["output"], "cost": round(cost["cost"], 4),
           "estimated_split_calls": cost["estimated_calls"], "calls_made_now": stats.get("planned_calls", 0) + stats.get("chunk_calls", 0),
           "documents_missing": missing, "w0_columns": sorted(f"{t}.{a}" for t, a in keep)}
    done.write_text(json.dumps(out, indent=1))
    return out


# ------------------------------------------------------------------------------------------ one stream

class Stream:
    """The controller on one stream, from the build, with real reads. Resumable after every query."""

    def __init__(self, corpus: str, key: str, caller):
        self.corpus, self.key, self.caller = corpus, key, caller
        self.ctx = R.context(corpus)
        self.dir = scratch(corpus) / key.replace("/", "_")
        self.state_path = folder(corpus) / "state" / f"{key.replace('/', '_')}.json"
        self.journal = folder(corpus) / "patch_reads.jsonl"
        self.stream = self.ctx.designs[0]["streams"][key]
        self.t0 = set(self.ctx.designs[0]["in_distribution"])
        if self.state_path.exists():
            self.st = json.loads(self.state_path.read_text())
        else:
            self.dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(scratch(corpus) / "build.db", self.dir / "master.db")
            self.st = {"pos": 0, "seen": {}, "records": [], "partial": None,
                       "mat": [[r.table, a, sorted(self.ctx.names[r.table])] for r in self.ctx.lean_reads for a in r.attributes]}
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

        build(self.dir / "master.db", dest, self.ctx.spec, fields, workload, Config())
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
        seen = {**ctx.w0, **self.st["seen"], qid: sql}
        fields_seen, reads_seen = C.design(ctx.spec, seen)  # W0 and the queries so far: descriptions and usage phrases
        if VARIANT:
            fields_seen = patch_variant(ctx, seen, fields_seen)
        F = {**all_fields(ctx), **fields_seen}
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
            cond = C.pushdown_conjuncts(sql, t, known) if len(need) == 1 else None
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
        shas, read_docs, fetched = [], 0, {}
        for t in missing:
            batch = sorted({a for r in reads_seen if r.table == t for a in r.attributes
                            if not self.fully(t, a) and f"{t}.{a}" in fields_seen})
            groups: dict[tuple, list[str]] = {}
            for d in scope[t]:
                attrs = tuple(a for a in batch if d not in self.mat.get((t, a), set()))
                if attrs:
                    groups.setdefault(attrs, []).append(d)
            for attrs, docs in groups.items():
                read = C.Read(t, "patch:" + ",".join(attrs), attrs)
                vspec, root = view_spec(ctx.spec, ctx.docs, t, docs)
                try:
                    left = stop_at - time.monotonic()
                    if left < 10:
                        raise Incomplete()
                    stats = run_reads(vspec, [read], {}, fields_seen, self.caller, self.journal, WORKERS,
                                      long_documents="chain", deadline=left - 8)
                finally:
                    shutil.rmtree(root, ignore_errors=True)
                if stats.get("stopped_at_deadline"):
                    raise Incomplete()
                by = rows_of(self.journal)
                vals, used = values_and_shas({d: ctx.docs[t][d] for d in docs}, t, list(attrs), fields_seen, by)
                shas += used
                read_docs += len(docs)
                conn = sqlite3.connect(self.dir / "master.db")
                with conn:
                    have = {r[1].lower() for r in conn.execute(f'PRAGMA table_info("{t}")')}
                    for a in attrs:
                        if a.lower() not in have:
                            kind = "REAL" if fields_seen[f"{t}.{a}"].value_type in ("int", "float") else "TEXT"
                            conn.execute(f'ALTER TABLE "{t}" ADD COLUMN "{a}" {kind}')
                    ids = {C._doc_name(r[0]): r[0] for r in conn.execute(f'SELECT doc_id FROM "{t}"')}
                    for d in docs:
                        got = vals.get(d)
                        if got is None or d not in ids:
                            continue
                        for a in attrs:
                            conn.execute(f'UPDATE "{t}" SET "{a}" = ? WHERE doc_id = ?',
                                         (commit_value(got.get(a), fields_seen[f"{t}.{a}"]), ids[d]))
                conn.close()
                for a in attrs:
                    self.mat.setdefault((t, a), set()).update(d for d in docs if d in vals)
                    fetched[f"{t}.{a}"] = fetched.get(f"{t}.{a}", 0) + sum(d in vals for d in docs)
        if missing or not built:
            self.view(seen, F, pre)  # the served view after the patch
        seconds = partial["seconds"] + (time.monotonic() - t_start)
        new = self.caller.usage.new[paid_from:]
        paid = {k: partial["paid"][k] + sum(u[k] for u in new) for k in ("input", "output", "cost")}
        paid["calls"] = partial["paid"]["calls"] + len(new)
        charged = charge(shas, self.caller.usage, rows_of(self.journal)) if shas else {"calls": 0, "input": 0, "output": 0, "cost": 0.0}
        self.st["records"].append({
            "pos": pos, "qid": qid, "drift": qid not in self.t0, "action": "patch" if missing else "answer",
            "missing": missing, "scope_docs": sum(len(v) for v in scope.values()), "docs_read": read_docs,
            "fetched": fetched, "runtime_s": round(seconds, 2),
            "calls": charged["calls"], "input_tokens": charged["input"], "output_tokens": charged["output"],
            "cost_usd": round(charged["cost"], 6), "paid": {k: (round(v, 6) if k == "cost" else v) for k, v in paid.items()},
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


def run(corpus: str, deadline: float, which: str = "headline") -> dict[str, Any]:
    t0 = time.monotonic()
    stop_at = t0 + deadline
    stop = lambda: time.monotonic() > stop_at - 12  # noqa: E731
    usage = Usage(folder(corpus) / "usage.jsonl")
    caller = make_caller(usage)
    caller.usage = usage
    b = prepare(corpus, caller, deadline - 20)
    if b is None:
        return {"corpus": corpus, "status": "build read in progress"}
    ctx = R.context(corpus)
    scorer = LiveScorer(corpus)
    streams = [k for k in ORDER if k in ctx.designs[0]["streams"] and (which == "all" or k in HEADLINE)]
    out_dir = folder(corpus) / "streams"
    out_dir.mkdir(parents=True, exist_ok=True)
    static = scratch(corpus) / "static.db"
    lines = []
    for key in streams:
        final = out_dir / f"{key.replace('/', '_')}.jsonl"
        if final.exists():
            continue
        s = Stream(corpus, key, caller)
        n = len(s.stream)
        try:
            while s.st["pos"] < n:
                if time.monotonic() > stop_at - 25:
                    raise Incomplete()
                s.step(stop_at)
        except Incomplete:
            s.save()
            lines.append(f"{corpus:8s} {key:18s} queries {bar(s.st['pos'], n)}")
            break
        items = [(r["qid"], r["digest"], Path(r["view"])) for r in s.st["records"]]
        items += [(q, R.digest(static, ctx.catalog[q]), static) for q in dict.fromkeys(s.stream)]
        if not scorer.run(items, stop):
            lines.append(f"{corpus:8s} {key:18s} queries {bar(n, n)} scoring")
            break
        recs = []
        for r in s.st["records"]:
            sd = R.digest(static, ctx.catalog[r["qid"]])
            recs.append({**{k: v for k, v in r.items() if k not in ("view",)},
                         "benchmark": scorer.get("benchmark", r["qid"], r["digest"]),
                         "tolerant": scorer.get("tolerant", r["qid"], r["digest"]),
                         "static_benchmark": scorer.get("benchmark", r["qid"], sd),
                         "static_tolerant": scorer.get("tolerant", r["qid"], sd)})
        final.write_text("".join(json.dumps(r) + "\n" for r in recs))
        shutil.rmtree(s.dir, ignore_errors=True)
    done = sum((out_dir / f"{k.replace('/', '_')}.jsonl").exists() for k in streams)
    spent = sum(u["cost"] for u in usage.by_sha.values())
    head = f"{corpus:8s} streams {bar(done, len(streams))}  paid so far ${spent:.3f}, {sum(u['input'] for u in usage.by_sha.values())/1e6:.2f}M in / {sum(u['output'] for u in usage.by_sha.values())/1e6:.2f}M out"
    return {"corpus": corpus, "status": "complete" if done == len(streams) else "running", "progress": [head] + lines,
            "elapsed": round(time.monotonic() - t0, 1)}


# ------------------------------------------------------------------------------------------ report

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--deadline", type=float, default=165)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--streams", default="headline", choices=["headline", "all"])
    a = ap.parse_args(argv)
    if a.run:
        out = run(a.corpus, a.deadline, a.streams)
        print("\n".join(out.pop("progress", [])))
        print(json.dumps(out))
    if a.report:
        from quwarts.eval import drift_live_report
        print(drift_live_report.write())
    return 0


if __name__ == "__main__":
    sys.exit(main())
