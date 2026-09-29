"""Representation layer on the frozen protocol runs (AUDIT for scores and cell accuracy: reads gold).

The raw database is each corpus's frozen protocol run (``shared_read_protocol/read_first_blank.db``, the
chained run where it exists); no document is re-read. A view is built by ``core.represent.build`` from the
workload's train queries only (``frozen``) or from train and test queries as they arrive (``online``: an
arriving query's literals are part of the workload; its answer is not). Each view is scored with the
benchmark metric and the tolerant metric on all queries and on the held-out (DocETL) queries, and its
cells are compared with gold for the targeted columns.

    python -m quwarts.eval.represent_eval --corpus art --configs base
    python -m quwarts.eval.represent_eval --corpus art --configs model --deadline 150
    python -m quwarts.eval.represent_eval --corpus art --configs budget --deadline 150   # the router's frontier
    python -m quwarts.eval.represent_eval --corpus art --drift --deadline 150            # drift levels
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
    "model": [Config(t2="all"), Config(t2="cascade"), Config(t1=False, t2="all"), Config(t1=False, t2="all", demos=False)],
    # the router's frontier: model-tier token budgets, columns chosen by benefit per token
    "budget": [Config(t2=m, budget=b) for m in ("all", "cascade") for b in (250, 500, 1000, 2000, 4000, 8000, 16000)],
    "cardinality": [Config(cardinality=False)],
}
DRIFT = ["art", "cspaper", "player"]  # corpora with a full-schema read (every column of every document)
LEVELS = ["drift_25", "drift_50", "drift_75", "drift_100"]
DRIFT_CONFIGS = [Config(t0=False), Config(), Config(t2="cascade"), Config(t2="all"), Config(cardinality=False)]


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
    call = caller() if group in ("model", "budget") else None
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


def full_raw(corpus: str) -> tuple[Path, Any, dict[str, str], dict[str, dict[str, str]], dict]:
    """The raw database of the full-schema read (``extraction_plan/<corpus>/reads.jsonl``: every schema
    column of every document, the robust design), built once through the shared-read builder."""

    from quwarts.core.adapt import controller as C
    from quwarts.core.schema_columns import complete_physical_schema
    from quwarts.core.signature import audit_workload, enumerate_predicates
    from quwarts.core.signature_realize import live_predicates
    from quwarts.eval import materialize_stream as MS
    from quwarts.eval.router_provenance import build as builder

    spec, train, _test, _run, docs = MS.context(corpus)
    train_q = {r["query_id"]: r["sql"] for r in train}
    fields, reads = C.design(spec, train_q, robust=True)
    sets = {level: {r["query_id"]: r["sql"] for r in json.loads((RESULTS / "drift_eval" / corpus / f"{level}.json").read_text())["rows"]}
            for level in LEVELS}
    union = dict(train_q)
    for qs in sets.values():
        union.update(qs)
    db = SCRATCH / corpus / "drift" / "full_raw.db"
    if not db.exists():
        by_sha = {}
        for line in (RESULTS / "extraction_plan" / corpus / "reads.jsonl").read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                by_sha[row["prompt_sha"]] = row
        values = C.read_values(docs, reads, fields, by_sha)
        grouped = {}
        for (t, d), v in values.items():
            grouped.setdefault((t, C.SHARED), {})[d] = v
        columns = {f"__schema__:{r.table}": f'SELECT {", ".join(chr(34) + a + chr(34) for a in r.attributes)} FROM "{r.table}"' for r in reads}
        builder(spec, reads, grouped, fields, {**union, **columns}, db)
        audit = audit_workload([{"query_id": q, "sql": x} for q, x in union.items()])
        conn = sqlite3.connect(db)
        complete_physical_schema(conn, union, live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible)))
        conn.commit()
        conn.close()
    return db, spec, train_q, sets, fields


def score_chunk(dataset: str, chunk: dict[str, str], db: Path, context: dict[str, str]) -> dict[str, float]:
    """``router_execute_v3.score`` on a chunk of queries, with the scorer's signature predicates computed
    over the whole query set (``context``) as a single call would. The predicates' eligibility depends
    on the set; computed over a chunk alone, a rewrite can name a signature column the database does not
    have, and the query then scores zero."""

    from quwarts.core.pipeline import official_sql
    from quwarts.core.signature import audit_workload, enumerate_predicates
    from quwarts.core.signature_realize import live_predicates
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.experiments.synthesize_case80 import gold_name, score_with_rewrites

    audit = audit_workload([{"query_id": q, "sql": s} for q, s in context.items()])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    rows = [{"query_id": q, "sql": s, "pack": q.split(":", 1)[0]} for q, s in chunk.items()]
    rewrites = {q: {"sql": official_sql(s, str(db), predicates, query_id=q), "sqlite_path": str(db)} for q, s in chunk.items()}
    report = score_with_rewrites(rows, rewrites, db, load_ground_truth(gold_name(dataset)), dataset)
    return {r["query_id"]: round(float(r.get("structure_f2") or 0.0) * float(r.get("cell_f1_20") or 0.0), 4)
            for r in report.get("per_query") or []}


def drift(corpus: str, deadline: float | None, force: bool = False, levels: list[str] | None = None,
          modes: list[str] | None = None) -> dict[str, Any]:
    """Representation under workload drift: views from the train literals only (``frozen``) against views
    that also take each drift level's arriving queries into the workload (``online``); scored on the
    level's queries."""

    from quwarts.eval.router_execute_v3 import DATASET, score
    from quwarts.eval.tolerant_score import score_tolerant

    stop = time.monotonic() + deadline if deadline else None
    raw, spec, train_q, sets, fields = full_raw(corpus)
    journal = Journal(ROOT / corpus / "llm.jsonl")
    call = caller()
    folder = ROOT / corpus / "drift"
    folder.mkdir(parents=True, exist_ok=True)
    done = {}
    for level in levels or LEVELS:
        queries = sets[level]
        for mode in modes or ("frozen", "online"):
            workload = train_q if mode == "frozen" else {**train_q, **queries}
            for config in DRIFT_CONFIGS:
                if mode == "online" and not config.t0:
                    continue  # the raw database has no representation to adapt
                key = f"{level}/{mode}/{config.name}"
                path = folder / f"{level}__{mode}__{config.name}.json"
                if path.exists() and not force and (json.loads(path.read_text()).get("scored_whole")
                                                     or json.loads(path.read_text()).get("predicates_over_level")):
                    done[key] = "cached"
                    continue
                if stop and time.monotonic() > stop:
                    return done
                db = SCRATCH / corpus / "drift" / f"{level}__{mode}__{config.name}.db"
                partial_path = folder / f"{level}__{mode}__{config.name}.partial.json"
                partial = json.loads(partial_path.read_text()) if partial_path.exists() and not force else {}
                if "manifest" not in partial or not db.exists():
                    manifest = build(raw, db, spec, fields, workload, config, call, journal)
                    partial = {"manifest": {"t2": manifest.get("t2"), "cells_changed": manifest.get("cells_changed")},
                               "benchmark": {}, "tolerant": {}}
                    partial_path.write_text(json.dumps(partial))
                # Scored in chunks with a resumable partial result: a drifted query that groups by a
                # high-cardinality column makes the metric's row alignment slow.
                if not partial.get("predicates_over_level"):  # chunks scored before the fix: redo the benchmark metric
                    partial["benchmark"], partial["predicates_over_level"] = {}, True
                for metric in ("benchmark", "tolerant"):
                    left = [q for q in queries if q not in partial[metric]]
                    for start in range(0, len(left), 8):
                        if stop and time.monotonic() > stop:
                            partial_path.write_text(json.dumps(partial))
                            done[key] = "partial"
                            return done
                        chunk = {q: queries[q] for q in left[start:start + 8]}
                        dbs = {q: str(db) for q in chunk}
                        if metric == "benchmark":
                            partial[metric].update(score_chunk(DATASET[spec.name], chunk, db, queries))
                        else:
                            rep = score_tolerant(DATASET[spec.name], chunk, dbs, db, SCRATCH / corpus / "drift" / f"tol_{level}__{mode}__{config.name}")
                            partial[metric].update({p["query_id"]: round(float(p["product"]), 4) for p in rep["per_query"]})
                        partial_path.write_text(json.dumps(partial))
                path.write_text(json.dumps({"corpus": corpus, "level": level, "mode": mode, "config": config.name,
                                            "t2": partial["manifest"].get("t2"), "cells_changed": partial["manifest"].get("cells_changed"),
                                            "predicates_over_level": True,
                                            "benchmark": partial["benchmark"], "tolerant": partial["tolerant"]}, indent=1))
                done[key] = "built"
    return done


def drift_report() -> str:
    lines = ["| Corpus | Level | raw | frozen: free tiers | frozen: + model (cascade) | frozen: + model (all) | online: free tiers | "
             "online: + model (cascade) | online: + model (all) | frozen: declared cardinality | online: declared cardinality | "
             "model tokens frozen / online (cascade, all) |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for corpus in DRIFT:
        folder = ROOT / corpus / "drift"
        if not folder.exists():
            continue
        for level in LEVELS:
            cells, tokens = [], []
            get = lambda mode, name: folder / f"{level}__{mode}__{name}.json"  # noqa: E731
            names = [("frozen", "raw"), ("frozen", "t0+t1+er+group"), ("frozen", "t0+t1+er+group+t2_cascade"), ("frozen", "t0+t1+er+group+t2_all"),
                     ("online", "t0+t1+er+group"), ("online", "t0+t1+er+group+t2_cascade"), ("online", "t0+t1+er+group+t2_all"),
                     ("frozen", "t0+t1+er+group+declared_cardinality"), ("online", "t0+t1+er+group+declared_cardinality")]
            for mode, name in names:
                p = get(mode, name)
                if p.exists():
                    r = json.loads(p.read_text())
                    b, t = (sum(r[m].values()) / len(r[m]) for m in ("benchmark", "tolerant"))
                    cells.append(f"{b:.3f} / {t:.3f}")
                    if "t2" in name:
                        tokens.append((r.get("t2") or {}).get("spent", 0))
                else:
                    cells.append("–")
            lines.append(f"| {corpus} | {level.split('_')[1]}% | " + " | ".join(cells) + f" | {', '.join(f'{x:,}' for x in tokens)} |")
    text = "Benchmark / tolerant mean per query on each drift level's queries.\n\n" + "\n".join(lines)
    (ROOT / "DRIFT.md").write_text(text + "\n")
    return text


def columns_report() -> str:
    """Per column: the residual after T0, its structure, and what each tier does to cell accuracy (gold)."""

    names = {"t0": "t0", "t1": "t0+t1", "model": "t0+er+group+t2_all", "model_nodemo": "t0+er+group+t2_all+nodemo",
             "t1+model": "t0+t1+er+group+t2_all", "cascade": "t0+t1+er+group+t2_cascade"}
    lines = ["| Column | rows | residual distinct after T0 | pattern classes | values per class | program coverage | "
             "T0 | +programs | +model (no demos) | +model | programs+model | cascade | model tokens: all / cascade |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    rows = []
    for corpus in CORPORA:
        folder = ROOT / corpus / "frozen"
        rs = {k: json.loads((folder / f"{v}.json").read_text()) for k, v in names.items() if (folder / f"{v}.json").exists()}
        if "t1" not in rs:
            continue
        for col, m in rs["t1"]["manifest"]["columns"].items():
            if not m["residual_after_t0"]:
                continue
            acc = {k: (r["cells"].get(col) or {}).get("exact") for k, r in rs.items()}
            tok = lambda k: ((rs.get(k) or {}).get("manifest", {}).get("columns", {}).get(col, {}).get("t2") or {}).get("tokens", 0)  # noqa: E731
            cov = m["coverage"]
            rows.append({"column": f"{corpus}.{col}", "rows": m["rows"], "residual": m["residual_after_t0"], "classes": cov["classes"],
                         "redundancy": cov["redundancy"], "coverage": cov["covered_share"], **acc,
                         "tokens_all": tok("model"), "tokens_cascade": tok("cascade")})
    f = lambda x: "–" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))  # noqa: E731
    for r in sorted(rows, key=lambda r: -r["redundancy"]):
        lines.append(f"| {r['column']} | {r['rows']} | {r['residual']} | {r['classes']} | {r['redundancy']} | {r['coverage']} | "
                     f"{f(r.get('t0'))} | {f(r.get('t1'))} | {f(r.get('model_nodemo'))} | {f(r.get('model'))} | {f(r.get('t1+model'))} | "
                     f"{f(r.get('cascade'))} | {r['tokens_all']:,} / {r['tokens_cascade']:,} |")
    text = "\n".join(lines)
    (ROOT / "COLUMNS.md").write_text(text + "\n")
    (ROOT / "columns.json").write_text(json.dumps(rows, indent=1))
    return text


def budget_report() -> str:
    """The router's frontier: benchmark score on all queries against model-tier tokens."""

    lines = ["| Corpus | Mode | budget | tokens planned | tokens spent | columns chosen | all bench | all tolerant | held-out bench |",
             "|---|---|---:|---:|---:|---|---:|---:|---:|"]
    for corpus in CORPORA:
        folder = ROOT / corpus / "frozen"
        if not folder.exists():
            continue
        held = held_out(corpus)
        pts = []
        for p in folder.glob("*.json"):
            r = json.loads(p.read_text())
            name = r["config"]
            if "@" not in name and name not in ("t0+t1+er+group", "t0+t1+er+group+t2_all", "t0+t1+er+group+t2_cascade"):
                continue
            t2 = r["manifest"].get("t2") or {}
            mode = "cascade" if "cascade" in name else ("all" if "t2_all" in name else "free")
            budget = int(name.split("@")[1]) if "@" in name else (0 if mode == "free" else -1)
            allq = list(r["benchmark"])
            m = lambda metric, ids: sum(r[metric].get(q, 0.0) for q in ids) / len(ids)  # noqa: E731
            pts.append((mode, budget, t2.get("planned_tokens", 0), t2.get("spent", 0), len(t2.get("chosen", [])),
                        m("benchmark", allq), m("tolerant", allq), m("benchmark", held)))
        for mode, budget, planned, spent, chosen, b, t, h in sorted(pts, key=lambda x: (x[0], x[1] if x[1] >= 0 else 10**9)):
            lines.append(f"| {corpus} | {mode} | {'∞' if budget < 0 else budget} | {planned:,} | {spent:,} | {chosen} | {b:.3f} | {t:.3f} | {h:.3f} |")
    text = "\n".join(lines)
    (ROOT / "BUDGET.md").write_text(text + "\n")
    return text


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
            results = {json.loads(p.read_text())["config"]: json.loads(p.read_text()) for p in sorted(folder.glob("*.json")) if "@" not in p.name}
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
    parser.add_argument("--drift", action="store_true", help="drift levels on the full-schema read (Art, CSPaper, Player)")
    parser.add_argument("--level", choices=LEVELS, action="append", help="restrict --drift to these levels")
    parser.add_argument("--drift-mode", choices=["frozen", "online"], action="append", help="restrict --drift to these modes")
    args = parser.parse_args(argv)
    if args.corpus and args.drift:
        print(json.dumps(drift(args.corpus, args.deadline, args.force, args.level, args.drift_mode)))
    elif args.corpus:
        print(json.dumps(run(args.corpus, args.configs, args.mode, args.deadline, args.force)))
    if args.report:
        print(report())
        print(columns_report())
        print(budget_report())
        print(drift_report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
