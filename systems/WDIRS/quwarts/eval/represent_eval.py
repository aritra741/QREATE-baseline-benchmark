"""Representation layer on the frozen protocol runs (AUDIT for scores and cell accuracy: reads gold).

The raw database is each corpus's frozen protocol run (``shared_read_protocol/read_first_blank.db``, the
chained run where it exists); no document is re-read. A view is built by ``core.represent.build`` from the
workload's train queries only (``frozen``) or from train and test queries as they arrive (``online``: an
arriving query's literals are part of the workload; its answer is not). Each view is scored with the
benchmark metric and the tolerant metric on all queries and on the held-out (DocETL) queries, and its
cells are compared with gold for the targeted columns.

    python -m quwarts.eval.represent_eval --corpus art --configs base
    python -m quwarts.eval.represent_eval --corpus art --configs model --deadline 150
    python -m quwarts.eval.represent_eval --report
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from quwarts.core.represent import Config, build
from quwarts.core.represent.llm import Journal
from quwarts.core.router.registry import RESULTS

CORPORA = ["med", "finan", "legal", "art", "cspaper", "player"]
ROOT = RESULTS / "representation"
SCRATCH = Path.home() / "quwarts_scratch" / "representation"
GOLD_KEY = {"player": "id", "art": "id", "legal": "id", "cspaper": "pdf_filename", "med": "id"}
CONFIGS = {
    "base": [Config(t0=False), Config(t1=False, er=False, group=False), Config(er=False, group=False), Config()],
    "model": [Config(t2="all"), Config(t2="cascade"), Config(t1=False, t2="all")],
}


def context(corpus: str):
    from quwarts.eval import router_shared_read_run as rs
    from quwarts.eval.tolerant_rescore import quwarts_run

    spec, train, test, fields, reads = rs.setup(corpus, "protocol")
    return spec, train, test, fields, quwarts_run(corpus) / "read_first_blank.db"


def held_out(corpus: str) -> list[str]:
    from quwarts.eval.docetl_rescore import recorded_tables

    manifest, _ = recorded_tables(context(corpus)[0].name)
    return sorted(manifest)


def caller():
    from quwarts.core.ledger import TokenLedger
    from quwarts.core.llm.openrouter import load_env_file, make_caller
    from quwarts.core.router.registry import PROJECT

    load_env_file(PROJECT / ".env")
    return make_caller(TokenLedger(theta=10**12), temperature=0.0, max_tokens=1500)


def gold_cells(corpus: str, spec) -> dict[tuple[str, str], dict[str, Any]]:
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.eval.router_execute_v3 import DATASET
    from quwarts.experiments.synthesize_case80 import gold_name

    key = GOLD_KEY.get(corpus)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    if key is None:
        return out
    for table, rows in load_ground_truth(gold_name(DATASET[spec.name])).items():
        for r in rows:
            raw = str(r.get(key, "")).strip()
            if not raw:
                continue
            try:
                doc = Path(raw).stem + ".txt" if corpus == "cspaper" else f"{int(float(raw))}.txt"
            except ValueError:
                continue
            out[(table, doc)] = r
    return out


def cell_accuracy(db: Path, gold: dict, columns: list[str]) -> dict[str, dict[str, Any]]:
    from quwarts.eval.tolerant_score import cell

    conn = sqlite3.connect(db)
    out = {}
    for qualified in columns:
        table, col = qualified.split(".", 1)
        exact = tol = n = 0
        for doc_id, v in conn.execute(f'SELECT doc_id, "{col}" FROM "{table}"'):
            g = gold.get((table, Path(str(doc_id)).name), {}).get(col.lower())
            if g is None or cell(g) is None:
                continue
            n += 1
            if v is not None:
                exact += str(v).strip() == str(g).strip()
                tol += cell(v) == cell(g)
        out[qualified] = {"n": n, "exact": round(exact / n, 3) if n else None, "tolerant": round(tol / n, 3) if n else None}
    conn.close()
    return out


def targeted_columns(spec, fields, workload: dict[str, str]) -> list[str]:
    from quwarts.core.represent.grammar import grammar
    from quwarts.core.represent.normalize import targets

    return sorted(f"{t}.{c}" for (t, c), tg in targets(grammar(spec, workload), fields).items() if not tg.numeric and tg.uses > 0)


def run(corpus: str, group: str, mode: str, deadline: float | None, force: bool = False) -> dict[str, Any]:
    from quwarts.eval.router_execute_v3 import DATASET, score
    from quwarts.eval.tolerant_score import score_tolerant

    stop = time.monotonic() + deadline if deadline else None
    spec, train, test, fields, raw = context(corpus)
    train_q = {r["query_id"]: r["sql"] for r in train}
    all_q = {**train_q, **{r["query_id"]: r["sql"] for r in test}}
    workload = train_q if mode == "frozen" else all_q
    folder = ROOT / corpus / mode
    folder.mkdir(parents=True, exist_ok=True)
    journal = Journal(ROOT / corpus / "llm.jsonl")
    gold = gold_cells(corpus, spec)
    call = caller() if group == "model" else None
    done = {}
    for config in CONFIGS[group]:
        path = folder / f"{config.name}.json"
        if path.exists() and not force:
            done[config.name] = "cached"
            continue
        if stop and time.monotonic() > stop:
            break
        db = SCRATCH / corpus / mode / f"{config.name}.db"
        manifest = build(raw, db, spec, fields, workload, config, call, journal)
        bench = score(DATASET[spec.name], all_q, {q: str(db) for q in all_q}, db)
        tol = score_tolerant(DATASET[spec.name], all_q, {q: str(db) for q in all_q}, db, SCRATCH / corpus / mode / f"tol_{config.name}")
        columns = targeted_columns(spec, fields, workload)
        result = {"corpus": corpus, "mode": mode, "config": config.name, "manifest": manifest,
                  "benchmark": {p["query_id"]: round(float(p["product"]), 4) for p in bench["per_query"]},
                  "tolerant": {p["query_id"]: round(float(p["product"]), 4) for p in tol["per_query"]},
                  "cells": cell_accuracy(db, gold, columns) if gold else {}}
        path.write_text(json.dumps(result, indent=1))
        done[config.name] = "built"
    return done


def paired_ci(diffs: list[float], reps: int = 10_000, seed: int = 20260927) -> list[float]:
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(reps))
    return [round(means[int(0.025 * reps)], 3), round(means[int(0.975 * reps) - 1], 3)]


def report() -> str:
    lines = []
    for mode in ("frozen", "online"):
        lines += [f"## {mode}", "", "| Corpus | Config | held-out bench | held-out tolerant | all bench | all tolerant | Δ all bench vs raw (CI) | "
                  "cells changed | model tokens | mean cell exact / tolerant |", "|---|---|---:|---:|---:|---:|---|---|---:|---|"]
        for corpus in CORPORA:
            folder = ROOT / corpus / mode
            if not folder.exists():
                continue
            held = held_out(corpus)
            results = {json.loads(p.read_text())["config"]: json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))}
            raw = results.get("raw")
            for name, r in sorted(results.items(), key=lambda x: (x[0] != "raw", len(x[0]), x[0])):
                m = lambda metric, ids: sum(r[metric].get(q, 0.0) for q in ids) / len(ids)  # noqa: E731
                allq = list(r["benchmark"])
                delta = ""
                if raw and name != "raw":
                    diffs = [r["benchmark"][q] - raw["benchmark"][q] for q in allq]
                    delta = f"{sum(diffs) / len(diffs):+.3f} {paired_ci(diffs)}"
                cells = [c for c in r["cells"].values() if c["exact"] is not None]
                acc = (f"{sum(c['exact'] for c in cells) / len(cells):.3f} / {sum(c['tolerant'] for c in cells) / len(cells):.3f}"
                       if cells else "–")
                tokens = (r["manifest"].get("t2") or {}).get("spent", 0)
                lines.append(f"| {corpus} | {name} | {m('benchmark', held):.3f} | {m('tolerant', held):.3f} | {m('benchmark', allq):.3f} | "
                             f"{m('tolerant', allq):.3f} | {delta} | {r['manifest'].get('cells_changed', {})} | {tokens:,} | {acc} |")
        lines.append("")
    text = "\n".join(lines)
    (ROOT / "REPORT.md").write_text(text + "\n")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", choices=CORPORA)
    parser.add_argument("--configs", choices=sorted(CONFIGS), default="base")
    parser.add_argument("--mode", choices=["frozen", "online"], default="frozen")
    parser.add_argument("--deadline", type=float, default=None)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--force", action="store_true", help="rebuild views that already have results")
    args = parser.parse_args(argv)
    if args.corpus:
        print(json.dumps(run(args.corpus, args.configs, args.mode, args.deadline, args.force)))
    if args.report:
        print(report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
