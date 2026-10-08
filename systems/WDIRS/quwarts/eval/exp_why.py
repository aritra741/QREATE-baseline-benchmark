"""Analyses behind the WHY claims (results/experiments/WHY/<name>/summary.json); no model calls.

    python -m quwarts.eval.exp_why cost        # why anticipating is cheap: document tokens dominate extraction cost
    python -m quwarts.eval.exp_why value       # why budget policies cannot win: value comes later and cost depends on order
    python -m quwarts.eval.exp_why determinacy # why some columns are prompt-sensitive: how far documents fix the value
    python -m quwarts.eval.exp_why joinkeys    # why DocETL collapses on joins: do its join keys match?
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
import statistics as S
from pathlib import Path

from quwarts.eval import drift_live as D
from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import EXP, REPO, gold_by_doc, is_null, streams, view
from quwarts.eval.exp_open import HOME_SCRATCH, column_values, correct, lookup, patched_docs

OUT = EXP / "WHY"
LIVE = REPO / "results" / "drift_live_ollama"
CORPORA = ["cspaper", "player", "art", "med", "legal"]


def save(name: str, out) -> dict:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    return out


def spearman(x: list[float], y: list[float]) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks(x), ranks(y)
    mx, my = S.mean(rx), S.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


# ------------------------------------------------------------------ cost

def cost() -> dict:
    """Measured break-even (extra build tokens to anticipate every new column ÷ tokens to patch them all later) against
    a document-token model: anticipating a column adds its field line and answer to each build prompt a document gets;
    patching it pays a prompt with the document, the instructions and the field. Per (column, document), averaged."""

    from quwarts.core.retrieve_extract.tokens import count_tokens
    from quwarts.core.router import chunked
    from quwarts.core.router.context_probe import V3, render_prompt
    from quwarts.core.router.corpus_features import read_document

    window = int(V3["window_tokens"])
    rows = {r["corpus"] + str(r["level"]): r for r in csv.DictReader(open(LIVE / "fixed_levels.csv"))
            if r["axis"] == "attribute_pool" and r["backend"] == "ollama"}
    out = {}
    for c in CORPORA:
        ctx = R.context(c)
        supp = D.supplement_spec(c, "attribute_pool")
        w0 = json.loads((LIVE / c / "build.json").read_text())["tokens"]
        anticipate = int(rows[c + "0"]["build_tokens"]) - w0
        patch = int(rows[c + "100"]["patch_input"]) + int(rows[c + "100"]["patch_output"])
        add, pay, doc_tokens = [], [], []
        for r in supp["reads"]:
            docs = list(ctx.docs[r.table].items())[:60]
            for a in r.attributes:
                f = supp["fields"][f"{r.table}.{a}"]
                line = count_tokens(f.line()) + 1 + 12  # the field's line, a newline, and its answer
                for _d, path in docs:
                    text = read_document(path)
                    n = count_tokens(text)
                    chunks = 1 if n <= window else len(chunked.split_chunks(text, chunked.chunk_tokens(window)))
                    add.append(line * chunks)
                    alone = count_tokens(render_prompt(text, [f], None)) if n <= window else \
                        n + chunks * (count_tokens(render_prompt("", [f], None)))
                    pay.append(alone + 12 * chunks)
                    doc_tokens.append(n)
        out[c] = {"measured_break_even": round(anticipate / patch, 4), "anticipate_tokens": anticipate,
                  "patch_tokens": patch, "model_break_even": round(sum(add) / sum(pay), 4),
                  "median_document_tokens": int(S.median(doc_tokens)), "new_columns": sum(len(r.attributes) for r in supp["reads"])}
    return save("cost", out)


# ------------------------------------------------------------------ value

def value() -> dict:
    """Where an extraction's value goes (its own query vs later queries that reuse the column), and how much the same
    query's extraction cost varies between streams (unlimited vs budgeted, same drift level)."""

    out = {}
    for c in CORPORA:
        rows = list(csv.DictReader(open(EXP / "E2.2-patches" / c / "patches.csv")))
        unl = [r for r in rows if r["budget"] == ""]
        own = sum(float(r["gain_on_query"]) for r in unl)
        later = sum(float(r["later_gain_sum"]) for r in unl)
        base = {(r["level"], r["qid"]): int(r["tokens"]) for r in unl}
        ratios = []
        for r in rows:
            if r["budget"] == "":
                continue
            k = (r["level"], r["qid"])
            if k in base and base[k] > 0 and int(r["tokens"]) > 0:
                ratios.append(int(r["tokens"]) / base[k])
        out[c] = {"patches": len(unl), "value_on_own_query": round(own, 3), "value_on_later_queries": round(later, 3),
                  "later_share": round(later / (own + later), 3) if own + later else None,
                  "patches_with_no_own_gain_but_later_gain": sum(float(r["gain_on_query"]) <= 1e-9 < float(r["later_gain_sum"]) for r in unl),
                  "same_query_cost_ratios": len(ratios),
                  "cost_ratio_median": round(S.median(ratios), 3) if ratios else None,
                  "cost_ratio_share_over_1_5x": round(sum(x > 1.5 for x in ratios) / len(ratios), 3) if ratios else None,
                  "cost_ratio_share_under_0_67x": round(sum(x < 1 / 1.5 for x in ratios) / len(ratios), 3) if ratios else None,
                  "ratios": [round(x, 3) for x in ratios]}
    return save("value", out)


# ------------------------------------------------------------------ determinacy

def norm(v) -> str:
    return re.sub(r"\s+", " ", str(v).strip().lower()) if not is_null(v) else ""


def determinacy() -> dict:
    """Per new column: how often two prompts (the build's and the patch's) give different values for the same document
    (the less the document fixes the value, the more they disagree), against accuracy (gold) of either prompt."""

    out = []
    for c in CORPORA:
        ctx = R.context(c)
        gold = gold_by_doc(c)
        new = json.loads((LIVE / c / "fixed4_attribute_pool_design.json").read_text())["new_columns"]
        docs = patched_docs(LIVE / c / "state" / "fixed4-attribute_pool_100.json")
        P = HOME_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
        if not P.exists():  # the re-run kept no master; its replay (identical) did
            from quwarts.eval.exp_analysis import REPLAY_SCRATCH
            P = REPLAY_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
        B = HOME_SCRATCH / c / "builds" / "fixed4_attribute_pool_0" / "build.db"
        fields = {**ctx.fields, **ctx.lean_fields}
        for col in new:
            t, a = col.split(".", 1)
            pv, bv = column_values(P, t, a), column_values(B, t, a)
            if pv is None or bv is None:
                continue
            n = dis = cp = cb = ge = 0
            for d, g in gold.get(t, {}).items():
                if a not in g or d not in docs.get(col, set()):
                    continue
                p, b = lookup(pv, d), lookup(bv, d)
                n += 1
                dis += norm(p) != norm(b)
                cp += correct(p, g[a])
                cb += correct(b, g[a])
                ge += is_null(g[a])
            if n < 10:
                continue
            f = fields[col]
            kind = ("number" if f.value_type in ("int", "float") else "yes/no" if {x.lower() for x in f.choices} == {"yes", "no"}
                    else "category" if f.choices else "free text")
            out.append({"corpus": c, "column": col, "documents": n, "disagreement": round(dis / n, 3),
                        "accuracy": round((cp + cb) / (2 * n), 3), "gold_empty": round(ge / n, 3), "kind": kind,
                        "multi_valued": f.value_type.startswith("multi") or f.multi_choice})
    x = [r["disagreement"] for r in out]
    summary = {"columns": out, "spearman_disagreement_vs_accuracy": round(spearman(x, [r["accuracy"] for r in out]), 3),
               "spearman_disagreement_vs_gold_empty": round(spearman(x, [r["gold_empty"] for r in out]), 3)}
    for k in ("number", "yes/no", "category", "free text"):
        v = [r["disagreement"] for r in out if r["kind"] == k]
        if v:
            summary[f"mean_disagreement_{k}"] = round(S.mean(v), 3)
    return save("determinacy", summary)


# ------------------------------------------------------------------ join keys

def joinkeys() -> dict:
    """Player join queries: share of rows whose join key finds a partner in the joined table, in DocETL's per-query
    tables, in our served view, and in gold."""

    ctx = R.context("player")
    dd = json.loads((REPO / "results" / "docetl_drift_ollama" / "player" / "per_query.json").read_text())
    gold = R.Scorer("player").gold()[0]
    key = "fixed4-attribute_pool/100"

    def rate(conn_rows_left, conn_rows_right):
        right = {norm(v) for v in conn_rows_right if norm(v)}
        left = [norm(v) for v in conn_rows_left if norm(v)]
        return (sum(v in right for v in left) / len(left)) if left else None

    def keys_db(db: Path, t: str, c: str) -> list:
        conn = sqlite3.connect(db)
        try:
            return [v for (v,) in conn.execute(f'SELECT "{c}" FROM "{t}"')]
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    per = []
    for r in streams("player")[key]:
        q = r["qid"]
        sql = ctx.catalog[q]
        conds = re.findall(r"ON\s+(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)", sql, re.I)
        if not conds or q not in dd:
            continue
        name = re.sub(r"[:/#]", "_", q)
        ddb = REPO / "results" / "docetl_drift_ollama" / "player" / "db" / f"{name}.db"
        ours = view("player", key, r["pos"])
        for lt, lc, rt, rc in conds:
            g = rate([x.get(lc) for x in gold.get(lt, [])], [x.get(rc) for x in gold.get(rt, [])])
            d = rate(keys_db(ddb, lt, lc), keys_db(ddb, rt, rc)) if ddb.exists() else None
            o = rate(keys_db(ours, lt, lc), keys_db(ours, rt, rc)) if ours.exists() else None
            per.append({"qid": q, "join": f"{lt}.{lc} = {rt}.{rc}", "gold": g, "docetl": d, "ours": o,
                        "docetl_score": dd[q]["benchmark"], "our_score": r["benchmark"]})
    by = {}
    for j in sorted({p["join"] for p in per}):
        ps = [p for p in per if p["join"] == j]
        m = lambda k: round(S.mean([p[k] for p in ps if p[k] is not None]), 3) if any(p[k] is not None for p in ps) else None
        by[j] = {"queries": len(ps), "gold": m("gold"), "docetl": m("docetl"), "ours": m("ours"),
                 "docetl_found": sum(p["docetl"] is not None for p in ps)}
    return save("joinkeys", {"by_join": by, "per_query": per})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["cost", "value", "determinacy", "joinkeys"])
    a = ap.parse_args(argv)
    out = {"cost": cost, "value": value, "determinacy": determinacy, "joinkeys": joinkeys}[a.what]()
    s = json.dumps(out, indent=1, default=str)
    print(s[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
