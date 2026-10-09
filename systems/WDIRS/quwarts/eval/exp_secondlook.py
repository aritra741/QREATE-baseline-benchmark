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
RATE_HIGH = json.loads((EXP / "COST" / "summary.json").read_text())["rates_usd_per_million"]["qwen2.5-32b (high: qwen-2.5-coder-32b)"]
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


def verifier_scores() -> dict[str, dict]:
    """The label-free verifier's score per cell (exp_grounding, out-of-fold by column) and its disagreement flag."""
    p = EXP / "WHY" / "grounding" / "cells.jsonl"
    if not p.exists():
        return {}
    return {f"{r['corpus']}|{r['column']}|{r['doc']}": r for r in (json.loads(l) for l in p.read_text().splitlines() if l.strip())}


def allocate(rows: list[dict], budget: int, lengths: dict | None = None) -> dict[str, list[dict]]:
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
    out = {"by_sensitivity": bys, "uniform": uni, "random": rnd[:budget]}
    # I2b: the same budget routed by the verifier (classifier score; disagreement alone; score per token of the
    # document, the cost-aware router). Cells the verifier has no row for (one context only) go last.
    ver = verifier_scores()
    if ver:
        rng2 = random.Random("I2b")
        tie = {key_of(r): rng2.random() for r in rows}
        p = lambda r: ver[key_of(r)]["p_wrong"] if key_of(r) in ver else -1.0  # noqa: E731
        dis = lambda r: key_of(r) in ver and bool(ver[key_of(r)]["disagree"])  # noqa: E731
        out["classifier"] = sorted(rows, key=lambda r: (-p(r), tie[key_of(r)]))[:budget]
        out["disagreeing"] = sorted(rows, key=lambda r: (not dis(r), tie[key_of(r)]))[:budget]
        if lengths:
            toks = lambda r: lengths.get((r["corpus"], r["column"].split(".", 1)[0], r["doc"]), 6000) + 400  # noqa: E731
            out["classifier_per_token"] = sorted(rows, key=lambda r: (-(max(p(r), 0.0) / toks(r)), tie[key_of(r)]))[:budget]
    return out


def key_of(r: dict) -> str:
    return f"{r['corpus']}|{r['column']}|{r['doc']}"


def run(budget: int, workers: int, limit: int | None, dry: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((OUT / "config.json").read_text()) if (OUT / "config.json").exists() else {}
    budget = int(cfg.get("budget", budget))
    rows = cells()
    max_doc = cfg.get("max_doc_tokens")
    lengths: dict[tuple, int] = {}
    if max_doc:  # size the experiment to the hardware: skip the longest documents (stated in the write-up)
        from quwarts.core.retrieve_extract.tokens import count_tokens

        ctxs0 = {c: R.context(c) for c in CORPORA}
        keep = []
        for r in rows:
            t = r["column"].split(".", 1)[0]
            k = (r["corpus"], t, r["doc"])
            if k not in lengths:
                lengths[k] = count_tokens(read_document(Path(ctxs0[r["corpus"]].docs[t][r["doc"]])))
            if lengths[k] <= int(max_doc):
                keep.append(r)
        print(f"I2: document cap {max_doc} tokens keeps {len(keep)} of {len(rows)} cells", flush=True)
        rows = keep
    alloc = allocate(rows, budget, lengths)
    (OUT / "allocation.json").write_text(json.dumps({k: [key_of(r) for r in v] for k, v in alloc.items()}, indent=0))
    wanted = {key_of(r): r for v in alloc.values() for r in v}
    if dry:
        done0 = set()
        if (OUT / "reads.jsonl").exists():
            done0 = {key_of(json.loads(l)) for l in (OUT / "reads.jsonl").read_text().splitlines() if l.strip()}
        for k, v in alloc.items():
            print(f"  {k}: {len(v)} cells, {sum(key_of(r) in done0 for r in v)} already read")
        return
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
            pin, pout = sum(r["prompt_tokens"] for r in sel), sum(r["output_tokens"] for r in sel)
            usd = (pin * RATE_HIGH[0] + pout * RATE_HIGH[1]) / 1e6  # the 32B at its higher OpenRouter price
            return {"cells": len(sel), "served_wrong": sum(not correct(r["served"], r["gold"]) for r in sel),
                    "caught": caught, "introduced": introduced, "net": caught - introduced,
                    "tokens": tokens, "usd_high": round(usd, 3),
                    "net_per_usd_high": round((caught - introduced) / usd, 1) if usd else None,
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
    # per column: is a wrong cell fixable by a stronger reader, and does sensitivity predict that?
    by_col = defaultdict(list)
    for r in allr:
        by_col[(r["corpus"], r["column"])].append(r)
    cols = []
    for (c, col), rs in by_col.items():
        if len(rs) < 10:
            continue
        wrong = [r for r in rs if not correct(r["served"], r["gold"])]
        fixed = sum(correct(r["second"], r["gold"]) for r in wrong)
        intro = sum(correct(r["served"], r["gold"]) and not correct(r["second"], r["gold"]) for r in rs)
        cols.append({"corpus": c, "column": col, "kind": rs[0]["kind"], "sensitivity": rs[0]["sensitivity"], "cells": len(rs),
                     "served_accuracy": round(S.mean(correct(r["served"], r["gold"]) for r in rs), 3),
                     "second_accuracy": round(S.mean(correct(r["second"], r["gold"]) for r in rs), 3),
                     "wrong": len(wrong), "fix_rate": round(fixed / len(wrong), 3) if wrong else None,
                     "net_per_1000_cells": round(1000 * (fixed - intro) / len(rs), 1)})
    from quwarts.eval.exp_why import spearman

    fx = [x for x in cols if x["fix_rate"] is not None and x["wrong"] >= 5]
    out["per_column"] = {"columns": len(cols),
                         "spearman_sensitivity_vs_second_accuracy": round(spearman([x["sensitivity"] for x in cols], [x["second_accuracy"] for x in cols]), 3),
                         "spearman_sensitivity_vs_fix_rate": round(spearman([x["sensitivity"] for x in fx], [x["fix_rate"] for x in fx]), 3) if len(fx) > 4 else None,
                         "spearman_sensitivity_vs_net": round(spearman([x["sensitivity"] for x in cols], [x["net_per_1000_cells"] for x in cols]), 3),
                         "by_sensitivity_band": {}, "rows": cols}
    for lo, hi in ((0, 0.3), (0.3, 0.6), (0.6, 1.01)):
        sel = [x for x in fx if lo <= x["sensitivity"] < hi]
        if sel:
            out["per_column"]["by_sensitivity_band"][f"{lo}-{min(hi, 1.0)}"] = {
                "columns": len(sel), "mean_fix_rate_of_wrong_cells": round(S.mean(x["fix_rate"] for x in sel), 3),
                "served_accuracy": round(S.mean(x["served_accuracy"] for x in sel), 3),
                "second_accuracy": round(S.mean(x["second_accuracy"] for x in sel), 3)}
    # hindsight re-allocations over the asked cells, same budget: lowest-sensitivity first and highest first
    budget = min(len(alloc["random"]), len(allr))
    asked = sorted(allr, key=lambda r: r["sensitivity"])
    for name, sel in (("lowest_sensitivity_first", asked[:budget]), ("highest_sensitivity_first", asked[-budget:])):
        caught = sum((not correct(r["served"], r["gold"])) and correct(r["second"], r["gold"]) for r in sel)
        intro = sum(correct(r["served"], r["gold"]) and not correct(r["second"], r["gold"]) for r in sel)
        out["allocations"][name + "_hindsight"] = {"cells": len(sel), "caught": caught, "introduced": intro,
                                                   "net_per_1000_cells": round(1000 * (caught - intro) / len(sel), 1),
                                                   "columns": len({r["column"] for r in sel})}
    (OUT / "summary.json").write_text(json.dumps(out, indent=1))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["run", "analyze"])
    ap.add_argument("--budget", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry", action="store_true", help="write the allocation and report overlap; ask nothing")
    a = ap.parse_args(argv)
    if a.what == "run":
        run(a.budget, a.workers, a.limit, a.dry)
    else:
        print(json.dumps(analyze(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
