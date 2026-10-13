"""How much of I1's prompt instability is the prompt?  Every single-column I1 read (alone, plus 2, plus 6, reworded,
with the condition) is sent again with exactly the same prompt (checked by its hash) and the same request settings.
A column's answer can then be compared two ways on the same document: same prompt sent twice (resampling), and
alone against another prompt (the I1 comparison).  If the second is no larger than the first, the prompt did not
cause the change.

    python -m quwarts.eval.exp_repeat run --tag t01 --hosts 127.0.0.1:P1,127.0.0.1:P2 [--temperature 0.1] [--workers 8]
    python -m quwarts.eval.exp_repeat analyze

Reads go to results/experiments/I1-context/qwen7b-repeat-<tag>/<corpus>/reads.jsonl (resumable).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from itertools import combinations
from pathlib import Path

from quwarts.core.adapt import catalogue as K
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.router.comparator import is_null
from quwarts.core.router.context_probe import render_prompt
from quwarts.core.router.corpus_features import read_document
from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_context import fields_of as specs_of
from quwarts.eval.exp_intervene import OUT, PREDICATE_KIND, chat
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_why_change import fields_of

CORPORA = ["cspaper", "player", "art", "med", "legal"]
KINDS = ("alone", "plus2", "plus6", "paraphrase", PREDICATE_KIND)
NUM_CTX = 32768  # the main server's context when I1 ran (servers/main.json), sent with every I1 request
_lock = threading.Lock()


def run(tag: str, hosts: list[str], temperature: float, workers: int) -> None:
    jobs = []
    for c in CORPORA:
        ctx = R.context(c)
        specs = specs_of(c)
        out = OUT / f"qwen7b-repeat-{tag}" / c / "reads.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        done = {json.loads(x)["key"] for x in out.read_text().splitlines() if x.strip()} if out.exists() else set()
        texts = {}
        for line in (OUT / "qwen7b" / c / "reads.jsonl").read_text().splitlines():
            r = json.loads(line)
            if r["kind"] not in KINDS:
                continue
            key = f"{r['table']}|{r['doc']}|{r['kind']}|{r['focal']}"
            if key in done:
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
            sha = hashlib.sha256(prompt.encode()).hexdigest()[:16]
            if sha != r["prompt_sha"]:
                raise SystemExit(f"prompt for {key} no longer matches the recorded one ({sha} vs {r['prompt_sha']})")
            jobs.append((out, key, r, prompt))
    print(f"{len(jobs)} prompts to send at temperature {temperature} over {len(hosts)} servers", flush=True)

    def one(i_job):
        i, (out, key, r, prompt) = i_job
        res = chat(hosts[i % len(hosts)], r["model"], prompt, NUM_CTX, temperature=temperature)
        row = {"key": key, **{k: r[k] for k in ("table", "doc", "kind", "focal", "attributes")},
               "prompt_sha": r["prompt_sha"], "temperature": temperature, **res}
        with _lock:
            with out.open("a") as h:
                h.write(json.dumps(row) + "\n")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers * len(hosts)) as ex:
        for i, _ in enumerate(ex.map(one, enumerate(jobs)), 1):
            if i % 250 == 0:
                print(f"  {i}/{len(jobs)}  {(time.time() - t0) / 60:.1f} min", flush=True)
    print(f"done in {(time.time() - t0) / 60:.1f} min", flush=True)


def _reads(d: Path) -> dict:
    out = {}
    if d.exists():
        for line in d.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                out[(r["table"], r["doc"], r["kind"], r["focal"])] = fields_of(r).get(r["focal"])
    return out


def change(a, b) -> str | None:
    """None if the same answer; otherwise how it changed."""
    if K.norm(a) == K.norm(b):
        return None
    if is_null(a) != is_null(b):
        return "blank vs filled"
    if correct(a, b) or correct(b, a):
        return "same value, other wording"
    return "different value"


def analyze() -> dict:
    tags = sorted(p.name.split("qwen7b-repeat-", 1)[1] for p in OUT.glob("qwen7b-repeat-*"))
    kinds_list = json.loads((OUT / "summary.json").read_text())["columns"]["qwen7b"]
    is_list = {x["column"]: x["kind"] == "list" for x in kinds_list}
    out = {}
    for tag in tags:
        rows = []
        for c in CORPORA:
            orig = _reads(OUT / "qwen7b" / c / "reads.jsonl")
            rep = _reads(OUT / f"qwen7b-repeat-{tag}" / c / "reads.jsonl")
            gold = gold_by_doc(c)
            cells = defaultdict(dict)
            for (t, d, k, a), v in orig.items():
                if k in KINDS and (t, d, k, a) in rep:
                    cells[(t, d, a)][k] = (v, rep[(t, d, k, a)])
            for (t, d, a), by in cells.items():
                if "alone" not in by:
                    continue
                g = (gold.get(t, {}).get(d) or {}).get(a)
                kind = "list" if is_list.get(f"{t}.{a}") else "single value"
                for k, (v, v2) in by.items():
                    rows.append({"corpus": c, "column": f"{t}.{a}", "kind": kind, "prompt": k, "compare": "same prompt twice",
                                 "change": change(v, v2), "right": (correct(v, g) if not is_null(g) else is_null(v)),
                                 "right2": (correct(v2, g) if not is_null(g) else is_null(v2))})
                a0, a1 = by["alone"]
                for k, (v, v2) in by.items():
                    if k == "alone":
                        continue
                    # alone vs other prompt, original reads; and the same with both repeats (two estimates)
                    for x, y, which in ((a0, v, "first"), (a1, v2, "second")):
                        rows.append({"corpus": c, "column": f"{t}.{a}", "kind": kind, "prompt": k,
                                     "compare": "alone vs this prompt", "which": which, "change": change(x, y)})
                    # stable prompt effect: both sends of each prompt agree with each other but not across prompts
                    rows.append({"corpus": c, "column": f"{t}.{a}", "kind": kind, "prompt": k, "compare": "stable effect",
                                 "change": change(a0, v) if change(a0, a1) is None and change(v, v2) is None else None,
                                 "both_stable": change(a0, a1) is None and change(v, v2) is None})

        def rate(sel):
            n = len(sel)
            cnt = Counter(r["change"] for r in sel if r["change"])
            return {"pairs": n, "changed": round(sum(cnt.values()) / n, 3) if n else None,
                    **{k: round(v / n, 3) for k, v in cnt.most_common()}}

        res = {}
        for grp in ("all", "list", "single value"):
            sel = [r for r in rows if grp == "all" or r["kind"] == grp]
            res[grp] = {
                "same prompt twice": {k: rate([r for r in sel if r["compare"] == "same prompt twice" and r["prompt"] == k]) for k in KINDS},
                "alone vs this prompt": {k: rate([r for r in sel if r["compare"] == "alone vs this prompt" and r["prompt"] == k]) for k in KINDS if k != "alone"},
                "stable effect": {k: rate([r for r in sel if r["compare"] == "stable effect" and r["prompt"] == k]) for k in KINDS if k != "alone"},
                "both sends of both prompts agree": {k: round(sum(r["both_stable"] for r in sel if r["compare"] == "stable effect" and r["prompt"] == k) / max(1, sum(1 for r in sel if r["compare"] == "stable effect" and r["prompt"] == k)), 3) for k in KINDS if k != "alone"},
            }
        same = [r for r in rows if r["compare"] == "same prompt twice"]
        res["accuracy first vs second send"] = {"first": round(sum(r["right"] for r in same) / len(same), 3),
                                                "second": round(sum(r["right2"] for r in same) / len(same), 3)}
        by_col = defaultdict(list)
        for r in same:
            by_col[r["column"]].append(r["change"] is not None)
        res["same prompt twice, by column"] = {k: round(sum(v) / len(v), 3) for k, v in sorted(by_col.items(), key=lambda x: -sum(x[1]) / len(x[1]))}
        out[tag] = res
    dest = OUT.parent / "WHY" / "repeat"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({t: {g: v for g, v in r.items() if g != "same prompt twice, by column"} for t, r in out.items()}, indent=1))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["run", "analyze"])
    p.add_argument("--tag", default="t01")
    p.add_argument("--hosts", default="")
    p.add_argument("--temperature", type=float, default=0.1)
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args(argv)
    if a.cmd == "run":
        run(a.tag, [h for h in a.hosts.split(",") if h], a.temperature, a.workers)
    else:
        analyze()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
