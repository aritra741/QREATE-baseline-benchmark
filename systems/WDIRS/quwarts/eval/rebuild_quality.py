"""Does re-extracting with prompts built from the new workload give better answers? (AUDIT: gold for scores)

Three reads of every document, all with the build's field list (W0's columns), differing only in the usage
phrases of the prompt:
* ``old``     phrases from W0 (the build workload): the build read under the per-query-description protocol
* ``retest``  the same prompts as ``old``, read again: the noise floor
* ``new``     phrases from the drifted workload W1 (seed 0's 100% value-drift stream) for every column W1 uses
Scored on W1's queries and on the rest of the value-drift pool, raw and with online representation.

    python -m quwarts.eval.rebuild_quality --corpus art --read --deadline 120
    python -m quwarts.eval.rebuild_quality --corpus art --score --deadline 150
    python -m quwarts.eval.rebuild_quality --report
"""
from __future__ import annotations

import argparse, json, shutil, sys, time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from quwarts.core.adapt import controller as C
from quwarts.eval import drift_run as R

CONDITIONS = ("old", "retest", "new")
CORPORA = ["cspaper", "art", "legal", "player", "med", "finan"]


def setup(corpus: str):
    from quwarts.core.router.workload_features import usage_phrase, workload_features

    ctx = R.context(corpus)
    d = ctx.designs[0]
    w1 = {q: ctx.catalog[q] for q in d["streams"]["value/100"]}
    old = dict(ctx.lean_fields)
    f1 = workload_features(ctx.spec, w1)["attributes"]
    new = {k: (replace(f, usage=usage_phrase(f1[k])) if k in f1 else f) for k, f in old.items()}
    fields = {"old": old, "retest": old, "new": new}
    rest = [q for q in d["value_pool"] if q not in w1]
    return ctx, w1, rest, fields


def folder(corpus: str) -> Path:
    return R.ROOT / corpus / "rebuild_quality"


def read(corpus: str, deadline: float, workers: int) -> dict:
    from quwarts.core.ledger import TokenLedger
    from quwarts.core.llm.openrouter import load_env_file, make_caller
    from quwarts.core.router.executor import run_reads
    from quwarts.core.router.registry import PROJECT

    ctx, _w1, _rest, fields = setup(corpus)
    load_env_file(PROJECT / ".env")
    folder(corpus).mkdir(parents=True, exist_ok=True)

    def one(cond):
        caller = make_caller(TokenLedger(theta=10**12), max_tokens=700)
        st = run_reads(ctx.spec, ctx.lean_reads, {}, fields[cond], caller, folder(corpus) / f"{cond}.jsonl", workers,
                       long_documents="chain", deadline=deadline)
        return cond, {k: st.get(k) for k in ("planned_calls", "done_before", "chunk_calls", "stopped_at_deadline", "exhausted")} | {"spent": caller.ledger.spent}

    with ThreadPoolExecutor(3) as pool:  # the three conditions in parallel
        return dict(pool.map(one, CONDITIONS))


def rows(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines() if path.exists() else []:
        if line.strip():
            r = json.loads(line)
            out[r["prompt_sha"]] = r
    return out


def databases(corpus: str) -> dict[str, Path]:
    from quwarts.core.represent import Config, build
    from quwarts.eval.router_provenance import build as builder

    ctx, w1, _rest, fields = setup(corpus)
    out = {}
    for cond in CONDITIONS:
        raw = ctx.scratch / "rebuild_quality" / f"{cond}_raw.db"
        view = raw.with_name(f"{cond}_online.db")
        out[f"{cond}/raw"], out[f"{cond}/online"] = raw, view
        if view.exists():
            continue
        values = C.read_values(ctx.docs, ctx.lean_reads, fields[cond], rows(folder(corpus) / f"{cond}.jsonl"))
        grouped = {}
        for (t, d), v in values.items():
            grouped.setdefault((t, C.SHARED), {})[d] = v
        raw.parent.mkdir(parents=True, exist_ok=True)
        columns = {f"__schema__:{r.table}": f'SELECT {", ".join(chr(34) + a + chr(34) for a in r.attributes)} FROM "{r.table}"'
                   for r in ctx.lean_reads}
        tmp = raw.with_suffix(".tmp.db")
        builder(ctx.spec, ctx.lean_reads, grouped, fields[cond], {**ctx.catalog, **columns}, tmp)
        R.complete(corpus, tmp)
        shutil.move(str(tmp), raw)
        build(raw, view, ctx.spec, fields[cond], {**ctx.w0, **w1}, Config())
    return out


def score(corpus: str, deadline: float | None) -> dict:
    start = time.monotonic()
    stop = (lambda: False) if deadline is None else (lambda: time.monotonic() - start > deadline)
    ctx, w1, rest, _fields = setup(corpus)
    dbs = databases(corpus)
    scorer = R.Scorer(corpus)
    table = {}
    items = []
    for name, db in dbs.items():
        for q in list(w1) + rest:
            dig = R.digest(db, ctx.catalog[q])
            table.setdefault(name, {})[q] = dig
            items.append((q, dig, db))
    done = scorer.run(items, stop)
    (folder(corpus) / "digests.json").write_text(json.dumps(table))
    return {"corpus": corpus, "complete": done}


def report() -> str:
    from quwarts.eval.represent_eval import paired_ci

    lines = ["# Re-extraction with the new workload's prompts (seed 0, 100% value drift)", "",
             "Each cell: mean benchmark score of old / retest / new prompts. W1: the drifted stream's queries (the workload that shaped the new prompts); rest: the other value-drift queries.", "",
             "| Corpus | Queries | Raw: old / retest / new | new - old [95% CI] | retest - old | Online representation: old / retest / new | new - old [95% CI] |",
             "|---|---|---|---|---|---|---|"]
    for c in CORPORA:
        p = folder(c) / "digests.json"
        if not p.exists():
            continue
        dig = json.loads(p.read_text())
        sc = json.loads((R.context(c).folder / "scores.json").read_text())["benchmark"]
        _ctx, w1, rest, _f = setup(c)
        for label, qs in (("W1", list(w1)), ("rest", rest)):
            cells = []
            for kind in ("raw", "online"):
                v = {cond: [sc.get(f"{q}|{dig[f'{cond}/{kind}'][q]}") for q in qs] for cond in CONDITIONS}
                if any(x is None for xs in v.values() for x in xs):
                    cells += ["(scoring)", "", ""] if kind == "raw" else ["(scoring)", ""]
                    continue
                m = {cond: sum(xs) / len(xs) for cond, xs in v.items()}
                diff = [a - b for a, b in zip(v["new"], v["old"])]
                ci = paired_ci(diff)
                cells.append(" / ".join(f"{m[x]:.3f}" for x in CONDITIONS))
                cells.append(f"{m['new'] - m['old']:+.3f} [{ci[0]:+.3f}, {ci[1]:+.3f}]")
                if kind == "raw":
                    cells.append(f"{m['retest'] - m['old']:+.3f}")
            lines.append(f"| {c} | {label} ({len(qs)}) | " + " | ".join(cells) + " |")
    text = "\n".join(lines)
    (R.ROOT / "REBUILD_QUALITY.md").write_text(text + "\n")
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", choices=CORPORA)
    ap.add_argument("--read", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--deadline", type=float, default=None)
    ap.add_argument("--workers", type=int, default=48)
    a = ap.parse_args(argv)
    if a.read:
        print(json.dumps(read(a.corpus, a.deadline or 120, a.workers)))
    if a.score:
        print(json.dumps(score(a.corpus, a.deadline)))
    if a.report:
        print(report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
