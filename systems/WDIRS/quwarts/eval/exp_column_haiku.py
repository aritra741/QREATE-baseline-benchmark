"""Does variation belong to the column, across readers?  The I1 prompts (each column alone, with 2 or 6 other
fields, reworded, with the query's condition), rebuilt exactly (hash-checked) and sent to Claude Haiku with the same
system message; "alone" is sent twice. Per column, for Haiku as for Qwen 7B (I1, and its resend run): how often the
answer changes when only the prompt changes (alone vs each other prompt), how often it changes when the same prompt is
sent twice, accuracy alone, empty answers. Then: do the column kind and Qwen's per-column numbers predict Haiku's?

    ANTHROPIC_API_KEY=... PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        QUWARTS_PARSE_FIRST_OBJECT=1 ~/venvs/quwarts/bin/python -m quwarts.eval.exp_column_haiku run|analyze

Reads: results/experiments/I1-context/haiku/<corpus>/reads.jsonl (resumable). Summary: results/experiments/WHY/column_haiku/.
"""

from __future__ import annotations

import hashlib
import json
import statistics as S
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from quwarts.core.router.comparator import is_null
from quwarts.core.router.context_probe import SYSTEM, render_prompt
from quwarts.core.router.corpus_features import read_document
from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_context import fields_of as specs_of
from quwarts.eval.exp_intervene import OUT, PREDICATE_KIND
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_repeat import change
from quwarts.eval.exp_why import spearman
from quwarts.eval.exp_why_change import fields_of

CORPORA = ["cspaper", "player", "art", "med", "legal"]
KINDS = ("alone", "plus2", "plus6", "paraphrase", PREDICATE_KIND)
MODEL = "claude-haiku-5-5"
_lock = threading.Lock()


def run(workers: int = 48) -> None:
    import anthropic

    client = anthropic.Anthropic(max_retries=2)
    jobs = []
    for c in CORPORA:
        ctx = R.context(c)
        specs = specs_of(c)
        out = OUT / "haiku" / c / "reads.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        done = {json.loads(x)["key"] for x in out.read_text().splitlines() if x.strip()} if out.exists() else set()
        texts = {}
        for line in (OUT / "qwen7b" / c / "reads.jsonl").read_text().splitlines():
            r = json.loads(line)
            if r["kind"] not in KINDS:
                continue
            t = r["table"]
            if (t, r["doc"]) not in texts:
                texts[(t, r["doc"])] = read_document(Path(ctx.docs[t][r["doc"]]))
            fs = []
            for a in r["attributes"]:
                f = specs[f"{t}.{a}"]
                if r["kind"] == "paraphrase" and r.get("description"):
                    f = replace(f, description=r["description"])
                fs.append(f)
            prompt = render_prompt(texts[(t, r["doc"])], fs, r.get("sql") if r["kind"] == PREDICATE_KIND else None)
            if hashlib.sha256(prompt.encode()).hexdigest()[:16] != r["prompt_sha"]:
                raise SystemExit(f"prompt for {t}|{r['doc']}|{r['kind']}|{r['focal']} no longer matches the recorded one")
            for send in ((1, 2) if r["kind"] == "alone" else (1,)):
                key = f"{t}|{r['doc']}|{r['kind']}|{r['focal']}|{send}"
                if key not in done:
                    jobs.append((out, key, send, r, prompt))
    print(f"{len(jobs)} prompts to send to {MODEL}", flush=True)

    def one(job):
        out, key, send, r, prompt = job
        wait = 10.0
        while True:  # a rate limit is waited out, never turned into a missing answer
            try:
                start = time.monotonic()
                m = client.messages.create(model=MODEL, max_tokens=1000, system=SYSTEM, messages=[{"role": "user", "content": prompt}])
                break
            except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError):
                time.sleep(wait)
                wait = min(wait * 1.5, 120.0)
        text = "".join(b.text for b in m.content if b.type == "text").strip()
        row = {"key": key, "send": send, **{k: r[k] for k in ("table", "doc", "kind", "focal", "attributes")},
               "prompt_sha": r["prompt_sha"], "model": MODEL, "response": text, "prompt_tokens": m.usage.input_tokens,
               "output_tokens": m.usage.output_tokens, "stop_reason": m.stop_reason, "seconds": round(time.monotonic() - start, 2)}
        with _lock, out.open("a") as h:
            h.write(json.dumps(row) + "\n")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, _ in enumerate(ex.map(one, jobs), 1):
            if i % 500 == 0:
                print(f"  {i}/{len(jobs)}  {(time.time() - t0) / 60:.1f} min", flush=True)
    print(f"done in {(time.time() - t0) / 60:.1f} min", flush=True)


def _answers(path: Path, model_key: str | None = None) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                out[(r["table"], r["doc"], r["kind"], r["focal"], r.get("send", 1))] = fields_of(r).get(r["focal"])
    return out


def per_column(answers: dict, resend: dict | None, c: str) -> dict:
    gold = gold_by_doc(c)
    cols = defaultdict(lambda: {"prompt_change": [], "resend_change": [], "right": [], "empty": []})
    by = defaultdict(dict)
    for (t, d, k, a, s), v in answers.items():
        by[(t, d, a)][(k, s)] = v
    for (t, d, a), m in by.items():
        if ("alone", 1) not in m:
            continue
        x = cols[f"{t}.{a}"]
        v0 = m[("alone", 1)]
        g = (gold.get(t, {}).get(d) or gold.get(t, {}).get(str(d).rsplit(".", 1)[0]) or {}).get(a)
        x["right"].append(correct(v0, g) if not is_null(g) else is_null(v0))
        if not is_null(g):
            x["empty"].append(is_null(v0))
        for k in ("plus2", "plus6", "paraphrase"):
            if (k, 1) in m:
                x["prompt_change"].append(change(v0, m[(k, 1)]) is not None)
        second = m.get(("alone", 2)) if resend is None else resend.get((t, d, "alone", a, 1), "<none>")
        if second != "<none>" and (("alone", 2) in m or resend is not None):
            x["resend_change"].append(change(v0, second) is not None)
    mean = lambda xs: round(S.mean(xs), 3) if xs else None  # noqa: E731
    return {col: {k: mean(v) for k, v in x.items()} | {"docs": len(x["right"])} for col, x in cols.items()}


def analyze() -> dict:
    kinds = {x["column"]: x["kind"] for x in json.loads((OUT / "summary.json").read_text())["columns"]["qwen7b"]}
    rows = []
    for c in CORPORA:
        q = per_column(_answers(OUT / "qwen7b" / c / "reads.jsonl"), _answers(OUT / "qwen7b-repeat-t01" / c / "reads.jsonl"), c)
        h = per_column(_answers(OUT / "haiku" / c / "reads.jsonl"), None, c)
        for col in sorted(set(q) & set(h)):
            rows.append({"corpus": c, "column": col, "kind": kinds.get(col, "other"), "qwen": q[col], "haiku": h[col]})
    out = {"columns": rows, "rank_correlation_qwen_vs_haiku": {}, "by_kind": {}}
    for m in ("prompt_change", "resend_change", "right", "empty"):
        pairs = [(r["qwen"][m], r["haiku"][m]) for r in rows if r["qwen"][m] is not None and r["haiku"][m] is not None]
        out["rank_correlation_qwen_vs_haiku"][m] = {"columns": len(pairs), "rho": round(spearman([a for a, _ in pairs], [b for _, b in pairs]), 3) if len(pairs) >= 6 else None}
    for kd in sorted({r["kind"] for r in rows}):
        sel = [r for r in rows if r["kind"] == kd]
        out["by_kind"][kd] = {"columns": len(sel), **{f"{who} {m}": round(S.mean(r[who][m] for r in sel if r[who][m] is not None), 3)
                                                     for who in ("qwen", "haiku") for m in ("prompt_change", "resend_change", "right", "empty")
                                                     if any(r[who][m] is not None for r in sel)}}
    dest = OUT.parent / "WHY" / "column_haiku"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "columns"}, indent=1))
    return out


if __name__ == "__main__":
    (run if sys.argv[1] == "run" else analyze)()
