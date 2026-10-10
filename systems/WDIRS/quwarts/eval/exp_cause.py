"""What exactly causes a query's score to change between two runs: counterfactual tables scored on the real queries.

    python -m quwarts.eval.exp_cause --corpus cspaper --run V2            # the planner's run at 100% drift
    python -m quwarts.eval.exp_cause --corpus cspaper --run I5-alone --level 0

The two served tables (the recorded run's and the other run's) differ in some cells. Each differing cell is one of:
  form      the same fact rendered otherwise (normalized text equal, same number, same date in another form)
  empty     a value appears or disappears
  items     a list gains or loses items
  fact      different content
Counterfactual tables apply the differences of one category only, on top of the recorded table; each is turned into
a served view with the system's own representation and scored on every test query with the benchmark scorer. The
score change attributable to a category is score(counterfactual) - score(recorded); "all" applies every difference
and should reproduce the other run's score. Query deltas are reported by category and by the query's operators.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import statistics as S
from collections import Counter, defaultdict
from pathlib import Path

from quwarts.core.router.comparator import is_null
from quwarts.core.router.probes import parse_fields
from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import EXP, REPLAY_SCRATCH, gold_by_doc
from quwarts.eval.exp_context import fields_of
from quwarts.eval.exp_interventions import Served, recorded_master
from quwarts.eval.exp_open import HOME_SCRATCH, column_values, correct, lookup
from quwarts.eval.exp_transfer import kind_of

SCRATCH = Path("/scratch/general/vast/u1592362/quwarts_exp/cause")


def ntext(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def category(old, new, kind: str) -> str | None:
    """How the new value differs from the old one, or None when they are the same."""
    if is_null(old) and is_null(new):
        return None
    if is_null(old) or is_null(new):
        return "empty"
    if ntext(old) == ntext(new):
        return None
    if kind == "list" or "||" in str(old) or "||" in str(new):
        a = {ntext(x) for x in str(old).split("||") if ntext(x)}
        b = {ntext(x) for x in str(new).split("||") if ntext(x)}
        return None if a == b else "items"
    na, nb = num(old), num(new)
    if na is not None and nb is not None:
        return "form" if abs(na - nb) <= 0.01 * max(1.0, abs(nb)) else "fact"
    ya, yb = re.findall(r"\b(1[5-9]\d\d|20\d\d)\b", str(old)), re.findall(r"\b(1[5-9]\d\d|20\d\d)\b", str(new))
    if ya and yb and ya[0] == yb[0]:
        return "form"
    a, b = ntext(old), ntext(new)
    if a and b and (a in b or b in a):
        return "form"
    return "fact"


def operators(sql: str) -> list[str]:
    u = sql.upper()
    ops = []
    if " JOIN " in u:
        ops.append("join")
    if "GROUP BY" in u:
        ops.append("group by")
    if re.search(r"\b(AVG|SUM|MAX|MIN)\s*\(", u):
        ops.append("numeric aggregate")
    elif re.search(r"\bCOUNT\s*\(", u):
        ops.append("count")
    if " WHERE " in u:
        ops.append("filter")
    return ops or ["select"]


def new_values(corpus: str, root: Path, level: int, table: str, attr: str) -> dict | None:
    """The other run's served values for a column: at level 0 its build database; at 100 the journal reads with the
    stronger reader's replacements applied."""
    if level == 0:
        db = root.parent.parent / "live" / corpus / "builds" / "fixed4_attribute_pool_0" / "build.db"
        scratch = Path(str(root).replace("results/experiments", "/scratch/general/vast/u1592362/quwarts_exp").replace("/live", "")) / "drift_live_ollama" / corpus / "builds" / "fixed4_attribute_pool_0" / "build.db"
        for p in (scratch, db):
            if p.exists():
                return column_values(p, table, attr)
        return None
    from quwarts.eval.exp_context import load
    from quwarts.eval.exp_interventions import journal_shas

    # the run's own reads; where a document was read alone by the probe and in its frozen group, the group's value is
    # the one the stream committed
    reads = load(root / corpus, journal_shas(EXP.parent / "drift_live_ollama", corpus))
    pv = {}
    for (t, d, a), lst in reads.items():
        if t != table or a != attr:
            continue
        grp = [v for ctx_, v in lst if len(ctx_) > 1]
        v = grp[0] if grp else lst[0][1]
        pv[str(d)] = " || ".join(str(x) for x in v) if isinstance(v, list) else v
    if not pv:
        return None
    rep = root / corpus / "repair_reads.jsonl"
    if rep.exists():
        for line in rep.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("purpose") == "second_look" and r["table"] == table and r["attribute"] == attr:
                pv[str(r["doc"])] = parse_fields(r["response"], [attr]).get(attr)
    return pv


def base_db(corpus: str, level: int) -> Path:
    if level == 0:
        p = HOME_SCRATCH / corpus / "builds" / "fixed4_attribute_pool_0" / "build.db"
        return p if p.exists() else REPLAY_SCRATCH / corpus / "builds" / "fixed4_attribute_pool_0" / "build.db"
    return recorded_master(corpus)


def doc_ids(db: Path, table: str) -> list:
    con = sqlite3.connect(db)
    try:
        return [r[0] for r in con.execute(f'SELECT doc_id FROM "{table}"')]
    finally:
        con.close()


def write_column(db: Path, table: str, attr: str, values: dict) -> None:
    con = sqlite3.connect(db)
    try:
        have = {r[1].lower() for r in con.execute(f'PRAGMA table_info("{table}")')}
        if attr.lower() not in have:
            con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{attr}" TEXT')
        for d, v in values.items():
            con.execute(f'UPDATE "{table}" SET "{attr}" = ? WHERE doc_id = ?', (None if is_null(v) else (" || ".join(map(str, v)) if isinstance(v, list) else v), d))
        con.commit()
    finally:
        con.close()


class CauseScorer(R.Scorer):
    def __init__(self, corpus: str, path: Path):
        super().__init__(corpus)
        self.path = path
        self.cache = json.loads(path.read_text()) if path.exists() else {"benchmark": {}, "tolerant": {}}


def final_view(corpus: str, run: str, level: int, out_dir: Path, key: str | None = None) -> Path:
    """The run's final served table as a view: the recorded table with every cell the run read (and the stronger
    reader replaced) applied, committed with the run's field specs and represented with the full catalogue. Returns
    the view path (``<out_dir>/all.view.db``), building it when absent."""
    from quwarts.core.represent import Config, build
    from quwarts.core.router.executor import commit_value

    view = out_dir / "all.view.db"
    if view.exists():
        return view
    out_dir.mkdir(parents=True, exist_ok=True)
    root = EXP / run / "live"
    ctx = R.context(corpus)
    fields = fields_of(corpus)
    state = root / corpus / "state" / (f"{key.replace('/', '_')}.json" if key else f"fixed4-attribute_pool_{level}.json")
    if state.exists():
        from quwarts.core.router.context_probe import FieldSpec

        for t, plan in json.loads(state.read_text()).get("frozen", {}).items():
            fields = {**fields, **{k: FieldSpec(**{**v, "choices": tuple(v["choices"])}) for k, v in plan["fields"].items()}}
    db = out_dir / "all.db"
    shutil.copy2(base_db(corpus, level), db)
    design = json.loads((EXP.parent / "drift_live_ollama" / corpus / "fixed4_attribute_pool_design.json").read_text())
    columns = set(design["new_columns"])
    if run != "recorded":
        for t, plan in (json.loads(state.read_text()).get("frozen", {}) if state.exists() else {}).items():
            columns |= {f"{t}.{a}" for a in plan["columns"]}  # the planner also read the other schema columns
    for col in sorted(columns):
        if col not in fields or run == "recorded":
            continue
        t, attr = col.split(".", 1)
        new = new_values(corpus, root, level, t, attr)
        if not new:
            continue
        if level == 100:
            new = {d: commit_value(v, fields[col]) for d, v in new.items()}
        write_column(db, t, attr, {str(d): lookup(new, str(d)) for d in doc_ids(db, t) if lookup(new, str(d)) is not None or str(d) in new})
    build(db, view, ctx.spec, fields, dict(ctx.catalog), Config(t0=True))
    return view


def main(argv=None) -> int:
    from quwarts.core.represent import Config, build

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--run", required=True, help="results/experiments/<run>/live")
    ap.add_argument("--level", type=int, default=100)
    a = ap.parse_args(argv)
    c, root = a.corpus, EXP / a.run / "live"
    ctx = R.context(c)
    fields = fields_of(c)
    gold = gold_by_doc(c)
    design = json.loads((EXP.parent / "drift_live_ollama" / c / "fixed4_attribute_pool_design.json").read_text())
    tests = list(dict.fromkeys(design["test"]))
    base = base_db(c, a.level)
    state = root / c / "state" / f"fixed4-attribute_pool_{a.level}.json"
    if state.exists():  # the planner's frozen specs (choices, usage phrases): the view and the commit use them
        from quwarts.core.router.context_probe import FieldSpec

        for t, plan in json.loads(state.read_text()).get("frozen", {}).items():
            fields = {**fields, **{k: FieldSpec(**{**v, "choices": tuple(v["choices"])}) for k, v in plan["fields"].items()}}
    out_dir = SCRATCH / a.run / c / str(a.level)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    # the differences, per cell, by category
    diffs = defaultdict(dict)  # category -> (table, attr) -> {doc: new value}
    counts = Counter()
    cell_acc = defaultdict(lambda: [0, 0, 0])  # category -> [cells, old correct, new correct]
    for col in design["new_columns"]:
        if col not in fields:
            continue
        t, attr = col.split(".", 1)
        old = column_values(base, t, attr)
        new = new_values(c, root, a.level, t, attr)
        if old is None or new is None:
            continue
        if a.level == 100:  # the stream commits normalized values (executor.commit_value with the field's spec)
            from quwarts.core.router.executor import commit_value

            new = {d: commit_value(v, fields[col]) for d, v in new.items()}
        for d in doc_ids(base, t):
            o = old.get(str(d))
            read = lookup(new, str(d)) is not None or str(d) in new or str(d).rsplit(".", 1)[0] in new
            n = lookup(new, str(d)) if read else None
            k = category(o, n, kind_of(fields[col])) if read else ("coverage" if not is_null(o) else None)
            if k is None:
                continue
            diffs[k][(t, attr)] = {**diffs[k].get((t, attr), {}), str(d): n}
            counts[k] += 1
            g = gold.get(t, {}).get(str(d)) or gold.get(t, {}).get(str(d).rsplit(".", 1)[0])
            if g and attr in g:
                e = cell_acc[k]
                e[0] += 1
                e[1] += correct(o, g[attr])
                e[2] += correct(n, g[attr])
                # the gold-aware split: did the change make the cell right, wrong, or leave it wrong either way?
                kk = k + ("->right" if correct(n, g[attr]) else ("->wrong (was right)" if correct(o, g[attr]) else "->wrong (was wrong)"))
                diffs[kk][(t, attr)] = {**diffs[kk].get((t, attr), {}), str(d): n}
    print(f"{c} {a.run} level {a.level}: differing cells by category {dict(counts)}")
    for k, e in cell_acc.items():
        print(f"   {k:6s} cells with gold {e[0]:5d}: accuracy {e[1] / max(1, e[0]):.3f} -> {e[2] / max(1, e[0]):.3f}")
    # the counterfactual tables and their views
    tables = {"recorded": {}}
    for k in diffs:
        tables[k] = {k: diffs[k]}
    tables["all"] = {k: v for k, v in diffs.items() if "->" not in k}
    scorer = CauseScorer(c, out_dir / "scores.json")
    workload = dict(ctx.catalog)
    results = {}
    for name, parts in tables.items():
        db = out_dir / f"{name}.db"
        shutil.copy2(base, db)
        for k, cols in parts.items():
            for (t, attr), vals in cols.items():
                write_column(db, t, attr, vals)
        view = out_dir / f"{name}.view.db"
        build(db, view, ctx.spec, fields, workload, Config(t0=True))
        items = [(q, R.digest(view, ctx.catalog[q]), view) for q in tests]
        scorer.run(items, lambda: False)
        scorer.save()
        results[name] = {q: scorer.get("benchmark", q, dig) for q, dig, _ in items}
    summary = {"corpus": c, "run": a.run, "level": a.level, "cells": dict(counts),
               "cell_accuracy": {k: {"cells": e[0], "recorded": round(e[1] / max(1, e[0]), 3), "run": round(e[2] / max(1, e[0]), 3)} for k, e in cell_acc.items()},
               "mean_score": {name: round(S.mean(v for v in r.values() if v is not None), 4) for name, r in results.items()},
               "by_category_and_operator": {}, "queries": {}}
    rec = results["recorded"]
    for name, r in results.items():
        if name == "recorded":
            continue
        deltas = {q: (r[q] or 0) - (rec[q] or 0) for q in tests}
        summary["queries"][name] = {q: round(d, 4) for q, d in deltas.items() if abs(d) > 1e-9}
        byop = defaultdict(list)
        for q, d in deltas.items():
            for op in operators(ctx.catalog[q]):
                byop[op].append(d)
        summary["by_category_and_operator"][name] = {op: {"queries": len(v), "mean_delta": round(S.mean(v), 4), "moved": sum(abs(x) > 0.02 for x in v)} for op, v in byop.items()}
    stream = root / c / "streams" / f"fixed4-attribute_pool_{a.level}.jsonl"
    if stream.exists():
        recs = {r["qid"]: r for r in map(json.loads, stream.read_text().splitlines()) if r.strip() if False} if False else {}
        for line in stream.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                recs[r["qid"]] = r
        view = out_dir / "all.view.db"
        same = sum(R.digest(view, ctx.catalog[q]) == recs[q]["digest"] for q in tests if q in recs)
        summary["sanity"] = {"stream_mean_score": round(S.mean(recs[q]["benchmark"] for q in tests if q in recs), 4),
                             "queries_with_identical_result_to_the_stream": f"{same}/{len(tests)}"}
        print("sanity against the run's own stream:", summary["sanity"])
    print("mean score by table:", summary["mean_score"])
    for name, ops in summary["by_category_and_operator"].items():
        print(f"   {name:8s}", {op: f"{v['mean_delta']:+.3f} ({v['moved']}/{v['queries']} moved)" for op, v in ops.items()})
    out = EXP / "WHY" / "cause"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{c}_{a.run}_L{a.level}.json").write_text(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def second_look_columns(corpus: str, min_cells: int = 20) -> dict:
    """Which columns' second looks pay at the query level, and whether that is predicted by the per-cell repair rate
    or by how much the stronger reader's label distribution moves toward gold's. For every column with enough
    second looks in the I2 pool, the recorded table with that column's cells replaced by the 32B's values is scored
    on every test query; the gain is compared with the column's net repair rate and its distributional gain."""
    from collections import Counter

    from quwarts.core.represent import Config, build
    from quwarts.core.router.executor import commit_value

    ctx = R.context(corpus)
    fields = fields_of(corpus)
    gold = gold_by_doc(corpus)
    design = json.loads((EXP.parent / "drift_live_ollama" / corpus / "fixed4_attribute_pool_design.json").read_text())
    tests = list(dict.fromkeys(design["test"]))
    pool = defaultdict(dict)
    for line in (EXP / "I2-secondlook" / "reads.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["corpus"] == corpus and r["doc"] not in pool[r["column"]]:
            pool[r["column"]][r["doc"]] = r
    out_dir = SCRATCH / "secondlooks" / corpus
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_db(corpus, 100)
    scorer = CauseScorer(corpus, out_dir / "scores.json")
    workload = dict(ctx.catalog)

    def score(db: Path, name: str) -> float:
        view = out_dir / f"{name}.view.db"
        build(db, view, ctx.spec, fields, workload, Config(t0=True))
        items = [(q, R.digest(view, ctx.catalog[q]), view) for q in tests]
        scorer.run(items, lambda: False)
        scorer.save()
        return S.mean(scorer.get("benchmark", q, dig) or 0 for q, dig, _ in items)

    rec_db = out_dir / "recorded.db"
    shutil.copy2(base, rec_db)
    rec = score(rec_db, "recorded")
    rows = []
    for col, cells in sorted(pool.items()):
        if len(cells) < min_cells or col not in fields:
            continue
        t, attr = col.split(".", 1)
        new = {str(d): commit_value(r["second"], fields[col]) for d, r in cells.items()}
        db = out_dir / f"{attr}.db"
        shutil.copy2(base, db)
        write_column(db, t, attr, new)
        sc = score(db, attr)
        fixes = sum((not correct(r["served"], r["gold"])) and correct(r["second"], r["gold"]) for r in cells.values())
        breaks = sum(correct(r["served"], r["gold"]) and not correct(r["second"], r["gold"]) for r in cells.values())
        # distributional gain: total-variation distance to gold's label histogram, served against second, on the pool
        def tv(vals):
            n = len(vals)
            a, g = Counter(ntext(v) for v in vals), Counter(ntext(r["gold"]) for r in cells.values())
            return sum(abs(a[k] / n - g[k] / n) for k in set(a) | set(g)) / 2
        rows.append({"column": col, "kind": kind_of(fields[col]), "cells": len(cells), "query_gain": round(sc - rec, 4),
                     "net_repair_rate": round((fixes - breaks) / len(cells), 3), "fixes": fixes, "breaks": breaks,
                     "tv_served": round(tv([r["served"] for r in cells.values()]), 3), "tv_second": round(tv([r["second"] for r in cells.values()]), 3)})
        rows[-1]["distributional_gain"] = round(rows[-1]["tv_served"] - rows[-1]["tv_second"], 3)
        print(f"  {col:34s} cells={len(cells):4d} gain={sc - rec:+.4f} net_rate={rows[-1]['net_repair_rate']:+.3f} tv {rows[-1]['tv_served']:.2f}->{rows[-1]['tv_second']:.2f}", flush=True)
    from quwarts.eval.exp_why import spearman

    summ = {"corpus": corpus, "recorded_score": round(rec, 4), "columns": rows}
    if len(rows) >= 4:
        summ["spearman_gain_vs_net_repair_rate"] = round(spearman([r["net_repair_rate"] for r in rows], [r["query_gain"] for r in rows]), 3)
        summ["spearman_gain_vs_distributional_gain"] = round(spearman([r["distributional_gain"] for r in rows], [r["query_gain"] for r in rows]), 3)
    (EXP / "WHY" / "cause").mkdir(parents=True, exist_ok=True)
    (EXP / "WHY" / "cause" / f"secondlooks_{corpus}.json").write_text(json.dumps(summ, indent=1))
    print(summ.get("spearman_gain_vs_net_repair_rate"), summ.get("spearman_gain_vs_distributional_gain"))
    return summ
