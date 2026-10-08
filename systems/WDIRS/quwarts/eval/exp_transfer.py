"""Can the WHY findings be used to derive a policy, and do they hold outside QuWARTS? (results/experiments/WHY/<name>/)
No model calls.

    python -m quwarts.eval.exp_transfer need      # how likely a column is to be needed, against the break-even
    python -m quwarts.eval.exp_transfer check     # prompt disagreement as a signal of which cells / columns are wrong
    python -m quwarts.eval.exp_transfer predict   # predict which queries come out right from column kind and aggregate
    python -m quwarts.eval.exp_transfer docetl    # do column kind and prompt disagreement predict DocETL's accuracy?
    python -m quwarts.eval.exp_transfer docetl_predict  # do our failure explanations predict DocETL's failures?
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sqlite3
import statistics as S
from collections import defaultdict

import sqlglot
from sqlglot import exp

from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import EXP, REPO, gold_by_doc, is_null, streams
from quwarts.eval.exp_open import HOME_SCRATCH, column_values, correct, lookup, patched_docs
from quwarts.eval.exp_why import CORPORA, LIVE, norm, save, spearman

DOCETL = REPO / "results" / "docetl_drift_ollama"


def needed(ctx, q: str) -> set[str]:
    from quwarts.core.adapt import controller as C

    nd = C.query_attributes(ctx.spec, q, ctx.catalog[q], {q: ctx.catalog[q]})
    return {f"{t}.{a}" for t, xs in nd.items() for a in xs}


def vnorm(v) -> str:
    try:
        return repr(round(float(str(v).replace(",", "")), 6))
    except ValueError:
        return norm(v)


def kind_of(f) -> str:
    if f.value_type in ("int", "float"):
        return "number"
    if {x.lower() for x in f.choices} == {"yes", "no"}:
        return "yes/no"
    if f.value_type.startswith("multi") or f.multi_choice:
        return "list"
    return "category" if f.choices else "free text"


# ------------------------------------------------------------------ need

def need() -> dict:
    """Probability that a column is needed, three ways, against the measured break-even of anticipating it:
    base rate (share of schema columns any benchmark query uses), reuse (a column asked by one test query is asked by
    another), and short-range locality (asked again within the next 10 queries of the 100% stream)."""
    cost = json.loads((EXP / "WHY" / "cost" / "summary.json").read_text())
    out = {}
    for c in CORPORA:
        ctx = R.context(c)
        schema = {f"{t}.{a}" for t, rows in gold_by_doc(c).items() for g in rows.values() for a in g}
        uses = defaultdict(int)
        for q in ctx.catalog:
            for col in needed(ctx, q) & schema:
                uses[col] += 1
        st = streams(c)["fixed4-attribute_pool/100"]
        seq = [needed(ctx, r["qid"]) for r in st]
        new = set(json.loads((LIVE / c / "fixed4_attribute_pool_design.json").read_text())["new_columns"])
        first, again, again10 = 0, 0, 0
        for col in new:
            pos = [i for i, s in enumerate(seq) if col in s]
            if not pos:
                continue
            first += 1
            again += len(pos) > 1
            again10 += len(pos) > 1 and pos[1] - pos[0] <= 10
        out[c] = {"schema_columns": len(schema), "used_by_any_query": len(uses),
                  "base_rate": round(len(uses) / len(schema), 3),
                  "new_columns_asked": first, "reuse_rate": round(again / first, 3) if first else None,
                  "reuse_within_10_queries": round(again10 / first, 3) if first else None,
                  "median_uses_per_used_column": S.median(uses.values()) if uses else 0,
                  "break_even": cost[c]["measured_break_even"],
                  "anticipate_all_schema_pays": len(uses) / len(schema) > cost[c]["measured_break_even"]}
    return save("transfer_need", out)


# ------------------------------------------------------------------ check

def check() -> dict:
    """Per cell of every new column (documents read by both the build's prompt and an on-demand prompt): is the cell
    wrong when the two prompts disagree vs agree? And per column: how many wrong cells does checking the most
    disagreeing columns first catch, against a random order."""
    cells, cols = [], []
    for c in CORPORA:
        ctx = R.context(c)
        gold = gold_by_doc(c)
        new = json.loads((LIVE / c / "fixed4_attribute_pool_design.json").read_text())["new_columns"]
        docs = patched_docs(LIVE / c / "state" / "fixed4-attribute_pool_100.json")
        P = HOME_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
        if not P.exists():
            from quwarts.eval.exp_analysis import REPLAY_SCRATCH
            P = REPLAY_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
        B = HOME_SCRATCH / c / "builds" / "fixed4_attribute_pool_0" / "build.db"
        fields = {**ctx.fields, **ctx.lean_fields}
        for col in new:
            t, a = col.split(".", 1)
            pv, bv = column_values(P, t, a), column_values(B, t, a)
            if pv is None or bv is None or col not in fields:
                continue
            n = wrong = dis = 0
            for d, g in gold.get(t, {}).items():
                if a not in g or d not in docs.get(col, set()):
                    continue
                p, b = lookup(pv, d), lookup(bv, d)
                w = not correct(p, g[a])  # the served (on-demand) value
                x = norm(p) != norm(b)
                cells.append({"corpus": c, "kind": kind_of(fields[col]), "disagree": x, "wrong": w})
                n += 1
                wrong += w
                dis += x
            if n >= 10:
                cols.append({"corpus": c, "column": col, "cells": n, "wrong": wrong, "disagreement": dis / n})
    out = {}
    for name, sel in (("all", cells), *((k, [x for x in cells if x["kind"] == k]) for k in
                                         ("number", "yes/no", "category", "list", "free text"))):
        dg = [x for x in sel if x["disagree"]]
        ag = [x for x in sel if not x["disagree"]]
        if dg and ag:
            out[name] = {"cells": len(sel), "share_disagree": round(len(dg) / len(sel), 3),
                         "wrong_when_disagree": round(sum(x["wrong"] for x in dg) / len(dg), 3),
                         "wrong_when_agree": round(sum(x["wrong"] for x in ag) / len(ag), 3),
                         "share_of_wrong_cells_in_disagreement": round(sum(x["wrong"] for x in dg) /
                                                                       max(1, sum(x["wrong"] for x in sel)), 3)}
    # checking columns in order of disagreement: share of all wrong cells covered after checking k% of cells
    total_cells, total_wrong = sum(x["cells"] for x in cols), sum(x["wrong"] for x in cols)
    curve = {}
    for name, order in (("by_disagreement", sorted(cols, key=lambda x: -x["disagreement"])),
                        ("oracle", sorted(cols, key=lambda x: -x["wrong"] / x["cells"]))):
        pts, cc, cw = [], 0, 0
        for x in order:
            cc += x["cells"]
            cw += x["wrong"]
            pts.append((round(cc / total_cells, 3), round(cw / total_wrong, 3)))
        curve[name] = pts
    out["column_order"] = {"columns": len(cols), "cells": total_cells, "wrong_cells": total_wrong,
                           "base_error": round(total_wrong / total_cells, 3), "curves": curve}
    return save("transfer_check", out)


# ------------------------------------------------------------------ predict

def predict() -> dict:
    """Rule derived from the label and aggregate findings: a query is 'safe' if every GROUP BY column holds numbers
    (or it has no GROUP BY) and every aggregate is MIN, AVG or SUM; 'fragile' if it groups by a list or yes/no column or
    uses COUNT or MAX. Score at every drift level by class."""
    rows = []
    for c in CORPORA:
        ctx = R.context(c)
        fields = {**ctx.fields, **ctx.lean_fields}
        from quwarts.eval.drift_live import supplement_spec

        fields.update(supplement_spec(c, "attribute_pool")["fields"])
        ss = streams(c)
        for p in (0, 25, 50, 75, 100):
            for r in ss[f"fixed4-attribute_pool/{p}"]:
                sql = ctx.catalog[r["qid"]]
                try:
                    tree = sqlglot.parse_one(re.sub(r"/\*.*?\*/", "", sql, flags=re.S), read="sqlite")
                except Exception:  # noqa: BLE001
                    continue
                alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
                tables = set(alias.values())
                grp = tree.find(exp.Group)
                kinds = []
                for col in (grp.find_all(exp.Column) if grp else []):
                    ts = [alias.get(col.table)] if col.table else [t for t in tables if f"{t}.{col.name}" in fields]
                    f = next((fields[f"{t}.{col.name}"] for t in ts if f"{t}.{col.name}" in fields), None)
                    kinds.append(kind_of(f) if f else "derived")
                aggs = {a.key.upper() for a in tree.find_all(exp.AggFunc)}
                fragile = bool({"list", "yes/no"} & set(kinds)) or bool({"COUNT", "MAX"} & aggs)
                safe = all(k == "number" for k in kinds) and aggs and aggs <= {"MIN", "AVG", "SUM"}
                cls = "safe" if safe else "fragile" if fragile else "middle"
                order = ["list", "free text", "category", "yes/no", "derived", "number"]
                worst = min(kinds, key=order.index) if kinds else "no GROUP BY"
                rows.append({"corpus": c, "level": p, "qid": r["qid"], "class": cls, "score": r["benchmark"],
                             "group_kind": worst, "aggs": sorted(aggs)})
    out = {}
    for p in (0, 25, 50, 75, 100):
        out[p] = {}
        for cls in ("safe", "middle", "fragile"):
            rs = [r for r in rows if r["level"] == p and r["class"] == cls]
            if rs:
                out[p][cls] = {"queries": len(rs), "mean_score": round(S.mean(r["score"] for r in rs), 3),
                               "share_above_0_5": round(sum(r["score"] > 0.5 for r in rs) / len(rs), 3),
                               "corpora": sorted({r["corpus"] for r in rs})}
    per = {}
    for c in CORPORA:
        per[c] = {cls: round(S.mean(r["score"] for r in rows if r["corpus"] == c and r["level"] == 100 and r["class"] == cls), 3)
                  for cls in ("safe", "middle", "fragile")
                  if any(r["corpus"] == c and r["level"] == 100 and r["class"] == cls for r in rows)}
    # within-corpus effects: score minus the corpus mean at the same drift level, averaged over drift levels
    mean = {(c, p): S.mean(r["score"] for r in rows if r["corpus"] == c and r["level"] == p)
            for c in CORPORA for p in (0, 25, 50, 75, 100)}
    for r in rows:
        r["resid"] = r["score"] - mean[(r["corpus"], r["level"])]

    def eff(key):
        rs = [r for r in rows if key(r)]
        qs = {(r["corpus"], r["qid"]) for r in rs}
        return {"queries": len(qs), "corpora": len({r["corpus"] for r in rs}),
                "score_vs_corpus_mean": round(S.mean(r["resid"] for r in rs), 3),
                "corpora_where_below_mean": sum(S.mean(r["resid"] for r in rs if r["corpus"] == c) < 0
                                                for c in CORPORA if any(r["corpus"] == c for r in rs))}
    within = {"group_by_kind": {k: eff(lambda r, k=k: r["group_kind"] == k) for k in
                                ("no GROUP BY", "number", "derived", "yes/no", "category", "free text", "list")
                                if any(r["group_kind"] == k for r in rows)},
              "aggregate": {a: eff(lambda r, a=a: a in r["aggs"]) for a in ("MIN", "AVG", "SUM", "MAX", "COUNT")}}
    return save("transfer_predict", {"by_level": out, "per_corpus_100": per, "within_corpus": within})


# ------------------------------------------------------------------ docetl

def docetl() -> dict:
    """DocETL (another system, its own prompts) on the same drifted workloads: per column, accuracy over every
    non-empty (query, document) extraction, and its own disagreement between queries that extracted the same column for the same
    document. Compared with column kind and with QuWARTS's prompt disagreement on the same column."""
    det = {r["column"]: r for r in json.loads((EXP / "WHY" / "determinacy" / "summary.json").read_text())["columns"]}
    rows = []
    for c in CORPORA:
        ctx = R.context(c)
        gold = gold_by_doc(c)
        from quwarts.eval.drift_live import supplement_spec

        fields = {**ctx.fields, **ctx.lean_fields, **supplement_spec(c, "attribute_pool")["fields"]}
        vals = defaultdict(lambda: defaultdict(list))  # col -> doc -> [values per query db]
        for f in glob.glob(str(DOCETL / c / "db" / "*.db")):
            con = sqlite3.connect(f)
            for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                info = [x[1] for x in con.execute(f'PRAGMA table_info("{t}")')]
                if "doc_id" not in info:
                    continue
                data = con.execute(f'SELECT * FROM "{t}"').fetchall()
                for j, a in enumerate(info):
                    if a == "doc_id" or all(row[j] is None for row in data):
                        continue  # this query did not extract the column
                    for row in data:
                        vals[f"{t}.{a}"][row[info.index("doc_id")]].append(row[j])
            con.close()
        for col, per_doc in vals.items():
            t, a = col.split(".", 1)
            if col not in fields:
                continue
            g = gold.get(t, {})
            n = ok = pairs = dis = 0
            for d, vs in per_doc.items():
                gd = g.get(d) or g.get(str(d).rsplit(".", 1)[0])
                if not gd or a not in gd:
                    continue
                vs = [v for v in vs if not is_null(v)]  # a query that did not process the document leaves it empty
                for v in vs:
                    n += 1
                    ok += correct(v, gd[a])
                if len(vs) > 1:
                    pairs += 1
                    dis += len({vnorm(v) for v in vs}) > 1
            if n >= 10:
                rows.append({"corpus": c, "column": col, "kind": kind_of(fields[col]), "extractions": n,
                             "accuracy": round(ok / n, 3),
                             "own_disagreement": round(dis / pairs, 3) if pairs >= 10 else None,
                             "quwarts_disagreement": det[col]["disagreement"] if col in det else None,
                             "quwarts_accuracy": det[col]["accuracy"] if col in det else None})
    by_kind = {}
    for k in ("number", "yes/no", "category", "list", "free text"):
        rs = [r for r in rows if r["kind"] == k]
        if rs:
            by_kind[k] = {"columns": len(rs), "mean_accuracy": round(S.mean(r["accuracy"] for r in rs), 3)}
    a = [r for r in rows if r["own_disagreement"] is not None]
    b = [r for r in rows if r["quwarts_disagreement"] is not None]
    out = {"columns": rows, "by_kind": by_kind,
           "spearman_own_disagreement_vs_accuracy": round(spearman([r["own_disagreement"] for r in a],
                                                                   [r["accuracy"] for r in a]), 3) if len(a) > 4 else None,
           "columns_with_own_disagreement": len(a),
           "spearman_quwarts_disagreement_vs_docetl_accuracy": round(spearman([r["quwarts_disagreement"] for r in b],
                                                                              [r["accuracy"] for r in b]), 3) if len(b) > 4 else None,
           "spearman_quwarts_accuracy_vs_docetl_accuracy": round(spearman([r["quwarts_accuracy"] for r in b],
                                                                          [r["accuracy"] for r in b]), 3) if len(b) > 4 else None,
           "columns_shared_with_quwarts": len(b)}
    return save("transfer_docetl", out)


def docetl_values(c: str) -> dict:
    """DocETL's non-empty values per column and document, pooled over its per-query outputs."""
    vals = defaultdict(lambda: defaultdict(list))
    for f in glob.glob(str(DOCETL / c / "db" / "*.db")):
        con = sqlite3.connect(f)
        for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            info = [x[1] for x in con.execute(f'PRAGMA table_info("{t}")')]
            if "doc_id" not in info:
                continue
            i = info.index("doc_id")
            for row in con.execute(f'SELECT * FROM "{t}"'):
                for j, a in enumerate(info):
                    if j != i and not is_null(row[j]):
                        vals[f"{t}.{a}"][row[i]].append(row[j])
        con.close()
    return vals


def gold_for(g: dict, d):
    return g.get(d) or g.get(str(d).rsplit(".", 1)[0])


def docetl_predict() -> dict:
    """Do our explanations predict DocETL's failures? On DocETL's own outputs: (1) where gold rows of GROUP BY columns
    end up, by kind of column; (2) within-corpus score by aggregate and by GROUP BY kind, and aggregate direction in
    matched groups; (3) per cell of the 41 new columns, DocETL's error rate where our two prompts agree vs disagree."""
    from collections import Counter

    from quwarts.eval.drift_live import supplement_spec
    from quwarts.eval.exp_groups import gold_conn, num
    from quwarts.eval.exp_groups import norm as gnorm

    order = ["list", "free text", "category", "yes/no", "derived", "number"]
    qrows, fate, direction = [], defaultdict(Counter), defaultdict(Counter)
    for c in CORPORA:
        ctx = R.context(c)
        fields = {**ctx.fields, **ctx.lean_fields, **supplement_spec(c, "attribute_pool")["fields"]}
        gold = gold_by_doc(c)
        gconn = gold_conn(c)
        per = json.loads((DOCETL / c / "per_query.json").read_text())
        for q, r in per.items():
            if q not in ctx.catalog:
                continue  # a query from before the med/legal regeneration
            sql = re.sub(r"/\*.*?\*/", "", ctx.catalog[q], flags=re.S)
            db = DOCETL / c / "db" / (re.sub(r"[:/#]", "_", q) + ".db")
            try:
                tree = sqlglot.parse_one(sql, read="sqlite")
            except Exception:  # noqa: BLE001
                continue
            alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
            tables = set(alias.values())
            grp = tree.find(exp.Group)
            kinds, gcols = [], []
            for col in (grp.find_all(exp.Column) if grp else []):
                ts = [alias.get(col.table)] if col.table else [t for t in tables if f"{t}.{col.name}" in fields]
                key = next((f"{t}.{col.name}" for t in ts if f"{t}.{col.name}" in fields), None)
                kinds.append(kind_of(fields[key]) if key else "derived")
                if key:
                    gcols.append((key, kinds[-1]))
            aggs = {a.key.upper() for a in tree.find_all(exp.AggFunc)}
            qrows.append({"corpus": c, "qid": q, "score": r["benchmark"], "aggs": sorted(aggs),
                          "group_kind": min(kinds, key=order.index) if kinds else "no GROUP BY"})
            if not db.exists():
                continue
            con = sqlite3.connect(db)
            # (1) label fate in this query's output
            for key, kind in gcols:
                t, a = key.split(".", 1)
                try:
                    pv = dict(con.execute(f'SELECT doc_id,"{a}" FROM "{t}"').fetchall())
                except sqlite3.Error:
                    continue
                pairs = []
                for d, p in pv.items():
                    g = gold_for(gold.get(t, {}), d)
                    if g and a in g and not is_null(g[a]):
                        # numbers as numbers (DocETL stores 45.0 where gold has 45)
                        pairs.append((vnorm(g[a]), None if is_null(p) else vnorm(p)))
                by = defaultdict(Counter)
                for g, p in pairs:
                    if p is not None:
                        by[p][g] += 1
                owner = {p: cnt.most_common(1)[0][0] for p, cnt in by.items()}
                for g, p in pairs:
                    fate[kind]["empty" if p is None else "exact" if p == g else
                               "other_form" if owner[p] == g else "merged"] += 1
            # (2b) aggregate direction over groups matched by key
            sel = tree.find(exp.Select)
            exprs = sel.expressions if sel else []
            nk = sum(1 for e in exprs if not e.find(exp.AggFunc))
            ak = [e.find(exp.AggFunc).key.upper() for e in exprs if e.find(exp.AggFunc) is not None]
            if ak and nk:
                try:
                    gm = {tuple(gnorm(x) for x in row[:nk]): row[nk:] for row in gconn.execute(sql).fetchall()}
                    for row in con.execute(sql).fetchall():
                        k = tuple(gnorm(x) for x in row[:nk])
                        if k not in gm:
                            continue
                        for i, kind in enumerate(ak[:len(row) - nk]):
                            pv_, gv = num(row[nk + i]), num(gm[k][i])
                            if pv_ is None or gv is None:
                                continue
                            span = max(abs(gv), 1e-9)
                            direction[kind]["within" if abs(pv_ - gv) <= 0.2 * span else
                                            "above" if pv_ > gv else "below"] += 1
                except sqlite3.Error:
                    pass
            con.close()
    share = lambda cn: {"rows": sum(cn.values()), **{k: round(v / sum(cn.values()), 3) for k, v in cn.most_common()}}  # noqa: E731
    # DocETL fills a column only for the documents a query's filters keep, so "empty" mostly means "not read";
    # compare the non-empty rows
    nonempty = {k: share(Counter({x: n for x, n in v.items() if x != "empty"})) for k, v in fate.items()}
    out = {"queries": len(qrows), "label_fate_by_kind": {k: share(v) for k, v in fate.items()},
           "label_fate_by_kind_nonempty": nonempty,
           "aggregate_direction": {k: share(v) for k, v in direction.items()}}
    # (2a) within-corpus effects on DocETL's scores
    mean = {c: S.mean(r["score"] for r in qrows if r["corpus"] == c) for c in CORPORA if any(r["corpus"] == c for r in qrows)}
    for r in qrows:
        r["resid"] = r["score"] - mean[r["corpus"]]

    def eff(rs):
        return {"queries": len(rs), "score_vs_corpus_mean": round(S.mean(r["resid"] for r in rs), 3),
                "corpora_below_mean": sum(S.mean(r["resid"] for r in rs if r["corpus"] == c) < 0
                                          for c in CORPORA if any(r["corpus"] == c for r in rs)),
                "corpora": len({r["corpus"] for r in rs})} if rs else None
    out["within_corpus"] = {
        "aggregate": {a: eff([r for r in qrows if a in r["aggs"]]) for a in ("MIN", "AVG", "SUM", "MAX", "COUNT")},
        "group_by_kind": {k: eff([r for r in qrows if r["group_kind"] == k]) for k in
                          ("no GROUP BY", "number", "derived", "yes/no", "category", "free text", "list")}}
    out["mean_score"] = {c: round(m, 3) for c, m in mean.items()}
    # (3) per cell: DocETL error where our two prompts agree vs disagree
    cells = []
    for c in CORPORA:
        ctx = R.context(c)
        gold = gold_by_doc(c)
        dv = docetl_values(c)
        new = json.loads((LIVE / c / "fixed4_attribute_pool_design.json").read_text())["new_columns"]
        docs = patched_docs(LIVE / c / "state" / "fixed4-attribute_pool_100.json")
        P = HOME_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
        if not P.exists():
            from quwarts.eval.exp_analysis import REPLAY_SCRATCH
            P = REPLAY_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
        B = HOME_SCRATCH / c / "builds" / "fixed4_attribute_pool_0" / "build.db"
        fields = {**ctx.fields, **ctx.lean_fields}
        for col in new:
            t, a = col.split(".", 1)
            pv, bv = column_values(P, t, a), column_values(B, t, a)
            if pv is None or bv is None or col not in fields or col not in dv:
                continue
            ddoc = {str(k).rsplit(".", 1)[0]: v for k, v in dv[col].items()}
            for d, g in gold.get(t, {}).items():
                if a not in g or d not in docs.get(col, set()):
                    continue
                vs = dv[col].get(d) or ddoc.get(str(d).rsplit(".", 1)[0])
                if not vs:
                    continue
                x = norm(lookup(pv, d)) != norm(lookup(bv, d))
                for v in vs:
                    cells.append({"kind": kind_of(fields[col]), "disagree": x, "wrong": not correct(v, g[a])})
    cc = {}
    for name, sel in (("all", cells), *((k, [x for x in cells if x["kind"] == k]) for k in
                                         ("number", "yes/no", "category", "list", "free text"))):
        dg, ag = [x for x in sel if x["disagree"]], [x for x in sel if not x["disagree"]]
        if dg and ag:
            cc[name] = {"docetl_values": len(sel), "docetl_wrong_when_ours_disagree": round(S.mean(x["wrong"] for x in dg), 3),
                        "docetl_wrong_when_ours_agree": round(S.mean(x["wrong"] for x in ag), 3)}
    out["cells"] = cc
    return save("transfer_docetl_predict", out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["need", "check", "predict", "docetl", "docetl_predict"])
    a = ap.parse_args(argv)
    out = {"need": need, "check": check, "predict": predict, "docetl": docetl, "docetl_predict": docetl_predict}[a.what]()
    print(json.dumps({k: v for k, v in out.items() if k not in ("columns",)}, indent=1, default=str)[:5000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
