"""Analyses that settle the open questions without model calls (results/experiments/A-open/<name>/).

    python -m quwarts.eval.exp_open cells       # A3: patch vs build prompt, cell by cell, per new column (7B)
    python -m quwarts.eval.exp_open power       # A15: smallest paired effect each corpus's test set can detect
    python -m quwarts.eval.exp_open shares      # A6: 0%-level cells per train share (E12), with each column's prompt size
    python -m quwarts.eval.exp_open goldinject  # A12: views with gold injected (MIN/MAX-over-text vs other queries)
    python -m quwarts.eval.exp_open nevernull   # A14: views with gold-empty cells of never-null text columns emptied
    python -m quwarts.eval.exp_open ablcells    # A7/A8: per column, what each E13/E14 ablation changed (needs the A0 replays)

A cell is correct if gold is empty and the prediction is empty, or both have values that agree (same_value: equal
after normalization, numbers within 20%). Paired comparisons of two databases use McNemar's exact test on the cells
one gets right and the other wrong.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import (EXP, REPLAY, REPLAY_SCRATCH, REPO, bootstrap, gold_by_doc, is_null, same_value,
                                       score_components, view)

OUT = EXP / "A-open"
SCRATCH = Path("/scratch/general/vast/u1592362/quwarts_exp")
HOME_SCRATCH = Path.home() / "quwarts_scratch" / "drift_live_ollama"
CORPORA = ["cspaper", "player", "art", "med", "legal"]


def correct(pred, gold) -> bool:
    return is_null(pred) if is_null(gold) else (not is_null(pred) and same_value(pred, gold))


def column_values(db: Path, table: str, col: str) -> dict[str, object] | None:
    conn = sqlite3.connect(db)
    try:
        have = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
        if col not in have:
            return None
        return {str(d): v for d, v in conn.execute(f'SELECT doc_id, "{col}" FROM "{table}"')}
    finally:
        conn.close()


def lookup(vals: dict, doc: str):
    if doc in vals:
        return vals[doc]
    stem = doc.rsplit(".", 1)[0]
    return vals.get(stem, vals.get(doc + ".txt"))


def mcnemar_p(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value for b vs c discordant pairs."""

    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def compare(corpus: str, a_db: Path, b_db: Path, cols: list[str], docs_of: dict[str, set] | None = None) -> list[dict]:
    """Per column: cells right in a and in b (against gold), filled shares, discordant pairs and McNemar p."""

    gold = gold_by_doc(corpus)
    rows = []
    for col in cols:
        t, c = col.split(".", 1)
        a, b = column_values(a_db, t, c), column_values(b_db, t, c)
        if a is None or b is None:
            continue
        n = ra = rb = fa = fb = ge = ab = ba = 0
        for d, g in gold.get(t, {}).items():
            if c not in g or (docs_of is not None and d not in docs_of.get(col, set())):
                continue
            pa, pb = lookup(a, d), lookup(b, d)
            ca, cb = correct(pa, g[c]), correct(pb, g[c])
            n += 1
            ra += ca
            rb += cb
            fa += not is_null(pa)
            fb += not is_null(pb)
            ge += is_null(g[c])
            ab += ca and not cb
            ba += cb and not ca
        if n:
            rows.append({"column": col, "cells": n, "correct_a": round(ra / n, 3), "correct_b": round(rb / n, 3),
                         "filled_a": round(fa / n, 3), "filled_b": round(fb / n, 3), "gold_empty": round(ge / n, 3),
                         "a_right_b_wrong": ab, "b_right_a_wrong": ba, "p": round(mcnemar_p(ab, ba), 5)})
    return rows


def holm(rows: list[dict]) -> None:
    """Holm-adjusted significance at 0.05 over the rows' p-values (``sig``)."""

    order = sorted(range(len(rows)), key=lambda i: rows[i]["p"])
    m, stop = len(rows), False
    for k, i in enumerate(order):
        if stop or rows[i]["p"] > 0.05 / (m - k):
            stop = True
            rows[i]["sig"] = False
        else:
            rows[i]["sig"] = True


def design(root: Path, corpus: str) -> dict:
    return json.loads((root / corpus / "fixed4_attribute_pool_design.json").read_text())


def patched_docs(state: Path) -> dict[str, set]:
    st = json.loads(state.read_text())
    out: dict[str, set] = {}
    for t, a, docs in st["mat"]:
        out[f"{t}.{a}"] = set(docs)
    return out


def save(name: str, out) -> None:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text(json.dumps(out, indent=1, default=str))


# ------------------------------------------------------------------------------------------ A3 / A15

def cells() -> dict:
    """A3: the recorded 100%-drift stream (columns read by patches) vs the 0% build (read by the build prompt), cell by
    cell, on the documents the patches read. 7B."""

    out = {}
    rec = REPO / "results" / "drift_live_ollama"
    for c in CORPORA:
        new = design(rec, c)["new_columns"]
        patched = HOME_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
        build0 = HOME_SCRATCH / c / "builds" / "fixed4_attribute_pool_0" / "build.db"
        docs = patched_docs(rec / c / "state" / "fixed4-attribute_pool_100.json")
        rows = compare(c, patched, build0, new, {k: v for k, v in docs.items() if k in new})
        holm(rows)
        out[c] = rows
    save("A3-cells", out)
    return out


def power() -> dict:
    """A15: the smallest mean paired difference (80% power, two-sided 0.05) each corpus's test set can detect, from the
    spread of per-query differences in the recorded 0% vs 100% comparison: 2.8 * sd / sqrt(n)."""

    out = {}
    rec = REPO / "results" / "drift_live_ollama"
    for c in CORPORA:
        load = lambda p: {json.loads(l)["qid"]: json.loads(l)["benchmark"] for l in (rec / c / "streams" / p).read_text().splitlines()}
        a, b = load("fixed4-attribute_pool_0.jsonl"), load("fixed4-attribute_pool_100.jsonl")
        d = [b[q] - a[q] for q in a]
        n = len(d)
        m = sum(d) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1))
        out[c] = {"queries": n, "sd_of_paired_difference": round(sd, 4), "min_detectable": round(2.8 * sd / math.sqrt(n), 4),
                  "queries_changed": sum(abs(x) > 1e-9 for x in d)}
    save("A15-power", out)
    return out


# ------------------------------------------------------------------------------------------ A6

def share_groups(corpus: str, frac: float | None) -> dict[str, int]:
    """Each new column's prompt size (number of columns asked together) in the 0% build of a train share."""

    code = ("import json,os; from quwarts.eval import drift_live as D, drift_run as R\n"
            f"ctx=R.context('{corpus}'); s=D.supplement_spec('{corpus}','attribute_pool'); out={{}}\n"
            "for r in ctx.lean_reads:\n  [out.__setitem__(f'{r.table}.{a}', len(r.attributes)) for a in r.attributes]\n"
            "for r in s['reads']:\n  [out.__setitem__(f'{r.table}.{a}', len(r.attributes)) for a in r.attributes]\n"
            "print(json.dumps(out))")
    env = {**os.environ}
    if frac is not None:
        env["QUWARTS_W0_FRACTION"] = str(frac)
        env["QUWARTS_LIVE_ROOT"] = str(EXP / f"E12-w0f{round(frac * 100):03d}" / "live")
    else:
        env.pop("QUWARTS_W0_FRACTION", None)
        env.pop("QUWARTS_LIVE_ROOT", None)
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=str(REPO / "systems" / "WDIRS"))
    return json.loads(r.stdout.strip().splitlines()[-1])


def shares() -> dict:
    """A6: 0%-drift build cells of each train share against the full train set's, per column (all documents), with the
    prompt size each column was read in."""

    out = {}
    for c in ("med", "legal", "art", "cspaper", "player"):
        full = HOME_SCRATCH / c / "builds" / "fixed4_attribute_pool_0" / "build.db"
        gfull = share_groups(c, None)
        out[c] = {}
        for f in (0.1, 0.25, 0.5):
            db = SCRATCH / f"E12-w0f{round(f * 100):03d}" / "drift_live_ollama" / c / "builds" / "fixed4_attribute_pool_0" / "build.db"
            if not db.exists():
                continue
            g = share_groups(c, f)
            cols = sorted(set(g) & set(gfull))
            rows = compare(c, db, full, cols)
            for r in rows:
                r["prompt_size_share"], r["prompt_size_full"] = g.get(r["column"]), gfull.get(r["column"])
            holm(rows)
            out[c][str(f)] = [r for r in rows if r["a_right_b_wrong"] + r["b_right_a_wrong"]]
    save("A6-shares", out)
    return out


# ------------------------------------------------------------------------------------------ A12 / A14

def target_columns(corpus: str, sql: str, fragile_only: bool) -> list[tuple[str, str]]:
    """(table, column) pairs: the MIN/MAX-over-text arguments (fragile_only) or every referenced column."""

    import sqlglot
    from sqlglot import exp

    ctx = R.context(corpus)
    tree = sqlglot.parse_one(sql, read="sqlite")
    alias = {}
    for t in tree.find_all(exp.Table):
        alias[t.alias_or_name] = t.name
    tables = set(alias.values())

    def owner(col: exp.Column) -> str | None:
        if col.table and col.table in alias:
            return alias[col.table]
        hits = [t for t in tables if f"{t}.{col.name}" in ctx.fields]
        return hits[0] if hits else None

    cols = []
    nodes = [c for f in tree.find_all(exp.Min, exp.Max) for c in f.find_all(exp.Column)] if fragile_only else list(tree.find_all(exp.Column))
    for col in nodes:
        t = owner(col)
        if t and f"{t}.{col.name}" in ctx.fields:
            if fragile_only and ctx.fields[f"{t}.{col.name}"].value_type in ("int", "float"):
                continue
            cols.append((t, col.name))
    return sorted(set(cols))


def rewrite(src: Path, dest: Path, corpus: str, cols: list[tuple[str, str]], gold, mode: str) -> int:
    """Copy a view and set ``cols`` from gold: mode "inject" (every cell) or "empty" (only cells gold leaves empty)."""

    from quwarts.core.adapt import controller as C

    shutil.copy2(src, dest)
    conn = sqlite3.connect(dest)
    n = 0
    with conn:
        for t, c in cols:
            have = {r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')}
            targets = [x for x in (c, f"{c}__canonical") if x in have]
            if not targets:
                continue
            g = gold.get(t, {})
            for rowid, d in conn.execute(f'SELECT rowid, doc_id FROM "{t}"').fetchall():
                name = C._doc_name(d)
                gr = g.get(name) or g.get(str(name).rsplit(".", 1)[0])
                if gr is None or c not in gr:
                    continue
                if mode == "empty" and not is_null(gr[c]):
                    continue
                v = None if is_null(gr[c]) else gr[c]
                for x in targets:
                    conn.execute(f'UPDATE "{t}" SET "{x}" = ? WHERE rowid = ?', (v, rowid))
                n += 1
    conn.close()
    return n


def rescore(name: str, variants: dict) -> dict:
    """Score original and rewritten views of the recorded unlimited 100%-drift stream (E2 replay views).
    ``variants``: label -> function(corpus, qid, sql, gold) -> (cols, mode) or None (query not in this variant)."""

    from quwarts.eval.exp_analysis import streams

    out = {}
    for c in CORPORA:
        ctx = R.context(c)
        gold = gold_by_doc(c)
        key = "fixed4-attribute_pool/100"
        tmp = SCRATCH / "A-open" / name / c
        tmp.mkdir(parents=True, exist_ok=True)
        cache_path = OUT / name / f"cache_{c}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        res = {}
        for label, fn in variants.items():
            pairs = []
            for r in streams(c)[key]:
                spec = fn(c, r["qid"], ctx.catalog[r["qid"]], gold)
                src = view(c, key, r["pos"])
                if spec is None or not src.exists():
                    continue
                cols, mode = spec
                dest = tmp / f"{label}_{r['pos']:03d}.db"
                if not dest.exists():
                    rewrite(src, dest, c, cols, gold, mode)
                pairs.append((r["qid"], src, dest))
            score_components(c, [(q, s) for q, s, _d in pairs] + [(q, d) for q, _s, d in pairs], cache)
            cache_path.write_text(json.dumps(cache))
            sc = lambda q, db: (lambda x: x["structure_f2"] * x["cell_f1_20"])(cache[f"{q}|{R.digest(db, ctx.catalog[q])}"])
            before = [sc(q, s) for q, s, _d in pairs]
            after = [sc(q, d) for q, _s, d in pairs]
            diff = [y - x for x, y in zip(before, after)]
            res[label] = {"queries": len(pairs), "before": round(sum(before) / max(1, len(before)), 4),
                          "after": round(sum(after) / max(1, len(after)), 4),
                          "diff_ci": bootstrap(diff) if diff else None,
                          "after_zero": sum(a < 1e-9 for a in after), "after_one": sum(a > 1 - 1e-9 for a in after)}
        out[c] = res
    save(name, out)
    return out


def goldinject() -> dict:
    """A12: inject gold into the MIN/MAX-over-text argument column, and into every referenced column, of each query's
    view; MIN/MAX-over-text queries vs the rest. If perfect values still score low, the loss is the benchmark's."""

    from quwarts.eval.drift_live import fragile_query

    def arg(c, q, sql, gold):
        return (target_columns(c, sql, True), "inject") if fragile_query(c, q) else None

    def all_fragile(c, q, sql, gold):
        return (target_columns(c, sql, False), "inject") if fragile_query(c, q) else None

    def all_other(c, q, sql, gold):
        return (target_columns(c, sql, False), "inject") if not fragile_query(c, q) else None

    return rescore("A12-goldinject", {"minmax_text_argument": arg, "minmax_text_all_columns": all_fragile,
                                      "other_queries_all_columns": all_other})


def nevernull() -> dict:
    """A14: empty every cell that gold leaves empty in the never-null text columns a query references; the score
    gained is what the contradiction between the schema ('never null') and gold costs."""

    def fn(c, q, sql, gold):
        ctx = R.context(c)
        cols = [(t, a) for t, a in target_columns(c, sql, False)
                if not ctx.fields[f"{t}.{a}"].nullable and ctx.fields[f"{t}.{a}"].value_type not in ("int", "float")]
        return (cols, "empty") if cols else None

    return rescore("A14-nevernull", {"never_null_text_gold_empty": fn})


# ------------------------------------------------------------------------------------------ A12b

def text_extrema_fix() -> None:
    """Sensitivity metric: the benchmark types every aggregate output as numeric (spp.aggregation_metrics.schema_from_sql),
    so a MIN/MAX over a text column can never match (float('other') fails). Here a MIN/MAX output whose gold values are
    not numeric is typed as a string (compared like a key cell); everything else is unchanged."""

    from spp import aggregation_metrics as M

    if getattr(M, "_text_extrema_fixed", False):
        return
    orig = M.gold_table_from_sql

    def fixed(rows, sql):
        t = orig(rows, sql)
        schema = M.schema_from_sql(sql)
        types = {c.name: c.type for c in t.columns}
        for c in t.columns:
            op = schema["operators"].get(c.name, "")
            if c.role == "measure" and op in ("MIN", "MAX") and not M._column_values_look_numeric(rows, c.name):
                types[c.name] = "string"
        if types == {c.name: c.type for c in t.columns}:
            return t
        return M.table_from_rows(rows, key_columns=[c.name for c in t.columns if c.role == "key"],
                                 measure_columns=[c.name for c in t.columns if c.role == "measure"],
                                 column_types=types, operators=schema["operators"])

    M.gold_table_from_sql = fixed
    import quwarts.experiments.player_case80 as P
    if hasattr(P, "gold_table_from_sql"):
        P.gold_table_from_sql = fixed
    M._text_extrema_fixed = True


def metricfix() -> dict:
    """A12b: the recorded unlimited streams at 0% and 100% drift, and the static build at 100%, re-scored with
    text-typed MIN/MAX outputs (E2 replay views; no model calls). Per query type: MIN/MAX-over-text vs the rest."""

    from quwarts.eval.drift_live import fragile_query
    from quwarts.eval.exp_analysis import streams

    text_extrema_fix()
    out = {}
    for c in CORPORA:
        ctx = R.context(c)
        cache_path = OUT / "A12b-metricfix" / f"cache_{c}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        res = {}
        for key in ("fixed4-attribute_pool/0", "fixed4-attribute_pool/100"):
            st = streams(c)[key]
            items = [(r["qid"], view(c, key, r["pos"])) for r in st if view(c, key, r["pos"]).exists()]
            score_components(c, items, cache)
            cache_path.write_text(json.dumps(cache))
            new = {q: (lambda x: x["structure_f2"] * x["cell_f1_20"])(cache[f"{q}|{R.digest(db, ctx.catalog[q])}"]) for q, db in items}
            old = {r["qid"]: r["benchmark"] for r in st}
            frag = {q for q in new if fragile_query(c, q)}
            m = lambda d, qs: round(sum(d[q] for q in qs) / len(qs), 4) if qs else None
            res[key] = {"all_old": m(old, list(new)), "all_new": m(new, list(new)),
                        "minmax_text_queries": len(frag), "minmax_text_old": m(old, frag), "minmax_text_new": m(new, frag),
                        "others_unchanged": all(abs(new[q] - old[q]) < 1e-9 for q in new if q not in frag)}
        out[c] = res
    save("A12b-metricfix", out)
    return out


# ------------------------------------------------------------------------------------------ A7 / A8

ABLATIONS = [("E13", n) for n in ("nodesc", "raw", "rawview", "noscope", "nobatch", "head", "noreuse", "nousage")] + \
            [("E14", n) for n in ("bgroup", "bfields")]


def ablcells() -> dict:
    """A7/A8: per ablation and corpus, which new columns' cells changed against the full system's 100%-drift master
    (on documents both read), and whether the ablation's per-query scores reproduce its run."""

    out = {}
    rec = REPO / "results" / "drift_live_ollama"
    for e, n in ABLATIONS:
        for c in ("cspaper", "player", "art"):  # med and legal: re-run on regenerated queries, ablations not yet run
            root = EXP / f"A0-{e}-{n}" / "live" / c
            master = SCRATCH / f"A0-{e}-{n}" / "drift_live_ollama" / c / "fixed4-attribute_pool_100" / "master.db"
            if not master.exists():
                continue
            new = design(rec, c)["new_columns"]
            full = HOME_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
            da = patched_docs(root / "state" / "fixed4-attribute_pool_100.json")
            db = patched_docs(rec / c / "state" / "fixed4-attribute_pool_100.json")
            both = {k: da.get(k, set()) & db.get(k, set()) for k in new}
            rows = compare(c, master, full, new, both)
            holm(rows)
            orig = {json.loads(l)["qid"]: json.loads(l)["benchmark"] for l in
                    (EXP / f"{e}-{n}" / "live" / c / "streams" / "fixed4-attribute_pool_100.jsonl").read_text().splitlines()}
            rep = {json.loads(l)["qid"]: json.loads(l)["benchmark"] for l in
                   (root / "streams" / "fixed4-attribute_pool_100.jsonl").read_text().splitlines()}
            out[f"{e}-{n}/{c}"] = {"reproduced": all(abs(orig[q] - rep[q]) < 1e-9 for q in orig),
                                   "columns": [r for r in rows if r["a_right_b_wrong"] + r["b_right_a_wrong"]]}
    save("A7-ablcells", out)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["cells", "power", "shares", "goldinject", "nevernull", "ablcells", "metricfix"])
    a = ap.parse_args(argv)
    out = {"cells": cells, "power": power, "shares": shares, "goldinject": goldinject, "nevernull": nevernull,
           "ablcells": ablcells, "metricfix": metricfix}[a.what]()
    print(json.dumps(out, indent=1, default=str)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
