"""I2: determinacy-guided second looks (results/experiments/I2-secondlook/).

    python -m quwarts.eval.exp_secondlook run [--budget 1000] [--workers 4]
    python -m quwarts.eval.exp_secondlook analyze

The cells of the new columns at 100% drift, with the 7B's served values. A fixed budget of second looks by the 32B
(the column asked alone, the same field spec, the document's head window) is allocated three ways: to the columns with
the highest 7B context sensitivity first, uniformly across columns, and at random. A second look *catches* an error
when the served value is wrong and the 32B's is right, and *introduces* one in the opposite case. Prediction
(RESEARCH_DEPTH.md, I2): allocation by sensitivity catches 1.4 to 2 times more errors per cell than random, except on
categories, where it should not beat random. Resumable: a (column, document) in reads.jsonl is not asked again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics as S
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from quwarts.core.router.context_probe import V3, render_prompt, truncate
from quwarts.core.router.corpus_features import read_document
from quwarts.core.router.probes import parse_fields
from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import EXP, REPLAY_SCRATCH, gold_by_doc
from quwarts.eval.exp_context import fields_of
from quwarts.eval.exp_intervene import LIVE, chat, server
from quwarts.eval.exp_open import HOME_SCRATCH, column_values, correct, lookup, patched_docs
from quwarts.eval.exp_transfer import kind_of

OUT = EXP / "I2-secondlook"
CORPORA = ["cspaper", "player", "art", "med", "legal"]
ALLOCATIONS = ("by_sensitivity", "uniform", "random")
_lock = threading.Lock()


def cells() -> list[dict]:
    """Every (new column, patched document) with a gold value: the served 7B value, the column's sensitivity, kind."""
    sens = json.loads((EXP / "WHY" / "context" / "summary.json").read_text())["columns"]
    out = []
    for c in CORPORA:
        fields = fields_of(c)
        gold = gold_by_doc(c)
        new = json.loads((LIVE / c / "fixed4_attribute_pool_design.json").read_text())["new_columns"]
        docs = patched_docs(LIVE / c / "state" / "fixed4-attribute_pool_100.json")
        P = HOME_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
        if not P.exists():
            P = REPLAY_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
        by_col = {r["column"]: r["sensitivity"] for r in sens.get(f"qwen7b/{c}", [])}
        kinds = {col: kind_of(fields[col]) for col in new if col in fields}
        kind_mean = defaultdict(list)
        for col, s in by_col.items():
            if col in kinds:
                kind_mean[kinds[col]].append(s)
        for col in new:
            if col not in fields:
                continue
            t, a = col.split(".", 1)
            pv = column_values(P, t, a)
            if pv is None:
                continue
            s = by_col.get(col)
            if s is None:
                s = S.mean(kind_mean[kinds[col]]) if kind_mean.get(kinds[col]) else 0.5
            for d, g in gold.get(t, {}).items():
                if a not in g or d not in docs.get(col, set()):
                    continue
                out.append({"corpus": c, "column": col, "kind": kinds[col], "doc": d, "sensitivity": s,
                            "served": lookup(pv, d), "gold": g[a]})
    return out


def allocate(rows: list[dict], budget: int) -> dict[str, list[dict]]:
    rng = random.Random("I2")
    by_col = defaultdict(list)
    for r in rows:
        by_col[r["column"]].append(r)
    for v in by_col.values():
        rng.shuffle(v)
    # by sensitivity: whole columns, most sensitive first
    order = sorted(by_col, key=lambda k: (-by_col[k][0]["sensitivity"], k))
    bys = [r for k in order for r in by_col[k]][:budget]
    # uniform: round-robin over columns
    uni, i = [], 0
    while len(uni) < budget and any(i < len(v) for v in by_col.values()):
        for k in sorted(by_col):
            if i < len(by_col[k]) and len(uni) < budget:
                uni.append(by_col[k][i])
        i += 1
    rnd = list(rows)
    rng.shuffle(rnd)
    return {"by_sensitivity": bys, "uniform": uni, "random": rnd[:budget]}


def key_of(r: dict) -> str:
    return f"{r['corpus']}|{r['column']}|{r['doc']}"


def run(budget: int, workers: int, limit: int | None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = cells()
    alloc = allocate(rows, budget)
    (OUT / "allocation.json").write_text(json.dumps({k: [key_of(r) for r in v] for k, v in alloc.items()}, indent=0))
    wanted = {key_of(r): r for v in alloc.values() for r in v}
    journal = OUT / "reads.jsonl"
    done = set()
    if journal.exists():
        for line in journal.read_text().splitlines():
            if line.strip():
                done.add(key_of(json.loads(line)))
    todo = [r for k, r in wanted.items() if k not in done]
    if limit:
        todo = todo[:limit]
    srv = server("qwen32b")
    window = int(V3["window_tokens"])
    print(f"I2: {len(rows)} cells, {len(wanted)} chosen, {len(todo)} to ask ({len(done)} done)", flush=True)
    ctxs = {c: R.context(c) for c in CORPORA}
    fields = {c: fields_of(c) for c in CORPORA}

    def one(r: dict) -> None:
        t, a = r["column"].split(".", 1)
        text = truncate(read_document(Path(ctxs[r["corpus"]].docs[t][r["doc"]])), window)
        prompt = render_prompt(text, [fields[r["corpus"]][r["column"]]], None)
        res = chat(srv["host"], "qwen2.5:32b-instruct", prompt, srv["context"])
        value = parse_fields(res["response"], [a]).get(a)
        row = {"corpus": r["corpus"], "column": r["column"], "doc": r["doc"], "kind": r["kind"],
               "sensitivity": r["sensitivity"], "served": r["served"], "gold": r["gold"], "second": value,
               "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:16], **res}
        with _lock:
            with journal.open("a") as h:
                h.write(json.dumps(row, default=str) + "\n")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, _ in enumerate(ex.map(one, todo), 1):
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}  {(time.time() - t0) / 60:.1f} min", flush=True)
    print(f"I2: done in {(time.time() - t0) / 60:.1f} min", flush=True)


def analyze() -> dict:
    alloc = json.loads((OUT / "allocation.json").read_text())
    reads = {}
    for line in (OUT / "reads.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            reads[f"{r['corpus']}|{r['column']}|{r['doc']}"] = r
    out = {"allocations": {}, "by_kind": {}}
    for name, keys in alloc.items():
        rs = [reads[k] for k in keys if k in reads]
        if not rs:
            continue

        def summary(sel):
            caught = sum((not correct(r["served"], r["gold"])) and correct(r["second"], r["gold"]) for r in sel)
            introduced = sum(correct(r["served"], r["gold"]) and not correct(r["second"], r["gold"]) for r in sel)
            tokens = sum(r["prompt_tokens"] + r["output_tokens"] for r in sel)
            return {"cells": len(sel), "served_wrong": sum(not correct(r["served"], r["gold"]) for r in sel),
                    "caught": caught, "introduced": introduced, "net": caught - introduced,
                    "caught_per_1000_cells": round(1000 * caught / len(sel), 1),
                    "net_per_1000_cells": round(1000 * (caught - introduced) / len(sel), 1),
                    "net_per_million_tokens": round(1e6 * (caught - introduced) / tokens, 1) if tokens else None,
                    "columns": len({r["column"] for r in sel})}

        out["allocations"][name] = summary(rs)
        out["allocations"][name + "_without_categories"] = summary([r for r in rs if r["kind"] != "category"])
        out["by_kind"][name] = {k: summary([r for r in rs if r["kind"] == k])
                                for k in ("number", "yes/no", "category", "list", "free text") if any(r["kind"] == k for r in rs)}
    # the relationship itself, over every asked cell: does sensitivity predict that a second look pays?
    allr = list(reads.values())
    bins = [(0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
    out["by_sensitivity_bin"] = {}
    for lo, hi in bins:
        sel = [r for r in allr if lo <= r["sensitivity"] < hi]
        if len(sel) >= 20:
            caught = sum((not correct(r["served"], r["gold"])) and correct(r["second"], r["gold"]) for r in sel)
            intro = sum(correct(r["served"], r["gold"]) and not correct(r["second"], r["gold"]) for r in sel)
            out["by_sensitivity_bin"][f"{lo:.1f}-{hi:.1f}"] = {"cells": len(sel), "served_accuracy": round(S.mean(correct(r["served"], r["gold"]) for r in sel), 3),
                                                              "second_accuracy": round(S.mean(correct(r["second"], r["gold"]) for r in sel), 3),
                                                              "net_per_1000_cells": round(1000 * (caught - intro) / len(sel), 1)}
    (OUT / "summary.json").write_text(json.dumps(out, indent=1))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["run", "analyze"])
    ap.add_argument("--budget", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    if a.what == "run":
        run(a.budget, a.workers, a.limit)
    else:
        print(json.dumps(analyze(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
