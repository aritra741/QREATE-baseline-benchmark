"""Stated or inferred, cell by cell, without labels: grounding, a small classifier, a cascade priced in dollars, and a
position model (results/experiments/WHY/grounding/summary.json). No model calls.

    python -m quwarts.eval.exp_grounding

  grounding   For every cell of the recorded 7B run read in two or more contexts: is the *extracted* value stated
              verbatim in the document (a string check, no LLM, no gold)? Against correctness and against disagreement.
  classifier  Logistic regression predicting a wrong cell from label-free features (grounded, disagreement, value
              length, kind, column sensitivity, fill), cross-validated by column and by corpus.
  cascade     On the I2 pool (cells the 32B re-read): which routing rule finds the most fixes per dollar at a budget:
              random, most sensitive first, ungrounded first, disagreeing first, classifier-ranked.
  position    Where in a document a stated value sits, per column: how much of each document a column needs.
"""

from __future__ import annotations

import json
import math
import re
import statistics as S
from collections import defaultdict
from pathlib import Path

from quwarts.core.router.corpus_features import read_document
from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import EXP, gold_by_doc, is_null
from quwarts.eval.exp_context import LIVE, fields_of, load, vnorm
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_transfer import kind_of
from quwarts.eval.exp_workload import found, norm, num_forms

CORPORA = ["cspaper", "player", "art", "med", "legal"]
OUT = EXP / "WHY" / "grounding"
RATES = json.loads((EXP / "COST" / "summary.json").read_text())["rates_usd_per_million"]  # [input, output] per million


def trivial(v) -> bool:
    s = norm(v)
    return s in ("yes", "no", "true", "false") or len(s) < 3


def grounded_flags(text_l: str, value) -> tuple[bool, bool]:
    """(any item stated, every item stated) for the value; numbers in any common form."""
    if is_null(value):
        return False, False
    items = [x.strip() for x in str(value).split("||")] if "||" in str(value) else [str(value)]
    hits = []
    for it in items:
        hit = False
        for form in num_forms(it):
            f = norm(form)
            if len(f) >= 2 and f in text_l:
                hit = True
                break
        hits.append(hit)
    return any(hits), all(hits)


class Docs:
    def __init__(self, c: str):
        self.ctx = R.context(c)
        self.cache: dict[tuple, str] = {}

    def text(self, t: str, d: str) -> str:
        if (t, d) not in self.cache:
            p = self.ctx.docs.get(t, {}).get(d)
            self.cache[(t, d)] = read_document(Path(p)).lower() if p else ""
        return self.cache[(t, d)]


def cells() -> list[dict]:
    """One row per (corpus, column, document) of the recorded 7B run with a gold value and two or more contexts."""
    sens = json.loads((EXP / "WHY" / "context" / "summary.json").read_text())["columns"]
    rows = []
    for c in CORPORA:
        docs = Docs(c)
        gold = gold_by_doc(c)
        fields = fields_of(c)
        stats = {r["column"]: r for r in sens.get(f"qwen7b/{c}", [])}
        per: dict[tuple, dict] = defaultdict(dict)
        for (t, d, a), lst in load(LIVE / c).items():
            for ctx_, v in lst:
                per[(t, d, a)].setdefault(ctx_, v)
        for (t, d, a), ctxs in per.items():
            if len(ctxs) < 2:
                continue
            col = f"{t}.{a}"
            if col not in fields:
                continue
            g = gold.get(t, {}).get(d) or gold.get(t, {}).get(str(d).rsplit(".", 1)[0])
            if g is None or a not in g:
                continue
            narrow = min(ctxs, key=len)
            served = ctxs[narrow]
            text = docs.text(t, d)
            g_any, g_all = grounded_flags(text, served)
            s_any, _ = grounded_flags(text, g[a])
            st = stats.get(col, {})
            fill = None
            if st.get("by_width"):
                n = sum(e["cells"] for e in st["by_width"].values())
                fill = 1 - sum(e["empty"] * e["cells"] for e in st["by_width"].values()) / n if n else None
            rows.append({"corpus": c, "column": col, "doc": d, "kind": kind_of(fields[col]), "served": served,
                         "gold": g[a], "correct": correct(served, g[a]),
                         "disagree": len({vnorm(v) for v in ctxs.values()}) > 1,
                         "empty": is_null(served), "trivial": trivial(served) if not is_null(served) else True,
                         "grounded": g_any, "grounded_all": g_all, "gold_stated": s_any,
                         "value_len": len(str(served)) if not is_null(served) else 0,
                         "sensitivity": st.get("sensitivity"), "fill": fill})
    return rows


def rate(sel, key="correct") -> float | None:
    return round(S.mean(r[key] for r in sel), 3) if sel else None


def grounding(rows: list[dict]) -> dict:
    out = {}
    nontriv = [r for r in rows if not r["empty"] and not r["trivial"]]
    out["cells"] = {"all": len(rows), "non_empty_non_trivial": len(nontriv)}
    for name, sel in (("all", nontriv), *((k, [r for r in nontriv if r["kind"] == k]) for k in ("number", "category", "list", "free text"))):
        g, ng = [r for r in sel if r["grounded"]], [r for r in sel if not r["grounded"]]
        if g and ng:
            out[name] = {"cells": len(sel), "share_grounded": round(len(g) / len(sel), 3),
                         "accuracy_grounded": rate(g), "accuracy_ungrounded": rate(ng),
                         "disagreement_grounded": rate(g, "disagree"), "disagreement_ungrounded": rate(ng, "disagree"),
                         "share_of_wrong_cells_ungrounded": round(sum(not r["correct"] for r in ng) / max(1, sum(not r["correct"] for r in sel)), 3)}
    # lists: all items stated vs some
    lists = [r for r in nontriv if r["kind"] == "list" and r["grounded"]]
    if lists:
        out["list_all_items_stated"] = {"cells": len(lists), "share_all_stated": round(S.mean(r["grounded_all"] for r in lists), 3),
                                        "accuracy_all_stated": rate([r for r in lists if r["grounded_all"]]),
                                        "accuracy_some_stated": rate([r for r in lists if not r["grounded_all"]])}
    # the 2x2: grounded x disagree
    for gflag in (True, False):
        for dflag in (True, False):
            sel = [r for r in nontriv if r["grounded"] == gflag and r["disagree"] == dflag]
            out[f"grounded={gflag},disagree={dflag}"] = {"cells": len(sel), "accuracy": rate(sel)}
    # gold stated vs not: is under-determination the absence of a statement?
    gs, gn = [r for r in rows if r["gold_stated"] and not trivial(r["gold"])], [r for r in rows if not r["gold_stated"] and not is_null(r["gold"]) and not trivial(r["gold"])]
    out["gold_stated"] = {"cells_stated": len(gs), "cells_not_stated": len(gn),
                          "disagreement_when_stated": rate(gs, "disagree"), "disagreement_when_not_stated": rate(gn, "disagree"),
                          "accuracy_when_stated": rate(gs), "accuracy_when_not_stated": rate(gn)}
    empty = [r for r in rows if r["empty"]]
    out["empty_cells"] = {"cells": len(empty), "accuracy": rate(empty), "gold_also_empty": round(S.mean(is_null(r["gold"]) for r in empty), 3) if empty else None}
    return out


def features(r: dict, which: str) -> list[float]:
    kinds = ("number", "yes/no", "category", "list", "free text")
    base = [1.0 if r["grounded"] else 0.0]
    if which == "grounded":
        return base
    if which == "grounded+disagree":
        return base + [1.0 if r["disagree"] else 0.0]
    return (base + [1.0 if r["grounded_all"] else 0.0, 1.0 if r["disagree"] else 0.0, 1.0 if r["empty"] else 0.0,
                    math.log1p(r["value_len"]), r["sensitivity"] if r["sensitivity"] is not None else 0.5,
                    r["fill"] if r["fill"] is not None else 0.7] + [1.0 if r["kind"] == k else 0.0 for k in kinds])


def classifier(rows: list[dict]) -> dict:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold

    y = np.array([0 if r["correct"] else 1 for r in rows])
    out = {"cells": len(rows), "share_wrong": round(float(y.mean()), 3)}
    for which in ("grounded", "grounded+disagree", "all"):
        X = np.array([features(r, which) for r in rows])
        # by column: a column's cells are never split between train and test
        groups = np.array([hash((r["corpus"], r["column"])) % 10**9 for r in rows])
        aucs, preds = [], np.zeros(len(rows))
        for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
            m = LogisticRegression(max_iter=2000).fit(X[tr], y[tr])
            p = m.predict_proba(X[te])[:, 1]
            preds[te] = p
            if len(set(y[te])) > 1:
                aucs.append(roc_auc_score(y[te], p))
        # by corpus: train on four, test on the fifth
        corp = {}
        for c in CORPORA:
            tr = np.array([r["corpus"] != c for r in rows])
            te = ~tr
            if te.sum() > 20 and len(set(y[te])) > 1:
                m = LogisticRegression(max_iter=2000).fit(X[tr], y[tr])
                corp[c] = round(float(roc_auc_score(y[te], m.predict_proba(X[te])[:, 1])), 3)
        m = LogisticRegression(max_iter=2000).fit(X, y)
        out[which] = {"auroc_by_column_cv": round(float(S.mean(aucs)), 3), "auroc_leave_one_corpus_out": corp,
                      "coefficients": [round(float(x), 2) for x in m.coef_[0]]}
        for r, p in zip(rows, preds):
            r[f"p_wrong_{which}"] = float(p)
    out["feature_order_all"] = ["grounded", "grounded_all", "disagree", "empty", "log_value_len", "sensitivity", "fill",
                                "number", "yes/no", "category", "list", "free text"]
    return out


def cascade(rows: list[dict]) -> dict:
    """The I2 pool: each cell has the 7B's served value, the 32B's second look and its tokens. Route a budget of cells
    to the 32B by several rules; count net fixes and dollars."""
    pool = []
    i2 = [json.loads(l) for l in (EXP / "I2-secondlook" / "reads.jsonl").read_text().splitlines() if l.strip()]
    by_key = {(r["corpus"], r["column"], r["doc"]): r for r in rows}
    docs = {c: Docs(c) for c in CORPORA}
    for r in i2:
        t = r["column"].split(".", 1)[0]
        text = docs[r["corpus"]].text(t, r["doc"])
        g_any, _ = grounded_flags(text, r["served"])
        k = (r["corpus"], r["column"], r["doc"])
        base = by_key.get(k, {})
        pool.append({**r, "grounded": g_any, "disagree": base.get("disagree"), "p_wrong": base.get("p_wrong_all"),
                     "fix": (not correct(r["served"], r["gold"])) and correct(r["second"], r["gold"]),
                     "break": correct(r["served"], r["gold"]) and not correct(r["second"], r["gold"]),
                     "tokens32": r["prompt_tokens"] + r["output_tokens"]})
    import random

    rng = random.Random("cascade")
    budget = 600
    rules = {
        "random": lambda ps: sorted(ps, key=lambda _: rng.random()),
        "most_sensitive_first": lambda ps: sorted(ps, key=lambda r: -r["sensitivity"]),
        "ungrounded_first": lambda ps: sorted(ps, key=lambda r: (r["grounded"] or is_null(r["served"]), rng.random())),
        "disagreeing_first": lambda ps: sorted(ps, key=lambda r: (not r["disagree"], rng.random())),
        "classifier_p_wrong_first": lambda ps: sorted(ps, key=lambda r: -(r["p_wrong"] if r["p_wrong"] is not None else 0)),
        "ungrounded_and_not_empty_first": lambda ps: sorted(ps, key=lambda r: (is_null(r["served"]) or r["grounded"], rng.random())),
    }
    out = {"pool_cells": len(pool), "budget": budget, "rules": {}}
    lo, hi = RATES["qwen2.5-32b (low: qwen3-32b)"], RATES["qwen2.5-32b (high: qwen-2.5-coder-32b)"]
    for name, f in rules.items():
        sel = f(list(pool))[:budget]
        fixes, breaks = sum(r["fix"] for r in sel), sum(r["break"] for r in sel)
        pin, pout = sum(r["prompt_tokens"] for r in sel), sum(r["output_tokens"] for r in sel)
        usd_lo, usd_hi = (pin * lo[0] + pout * lo[1]) / 1e6, (pin * hi[0] + pout * hi[1]) / 1e6
        out["rules"][name] = {"net_fixes": fixes - breaks, "fixes": fixes, "breaks": breaks,
                              "tokens_32b": pin + pout, "usd_low": round(usd_lo, 3), "usd_high": round(usd_hi, 3),
                              "net_fixes_per_usd_high": round((fixes - breaks) / usd_hi, 1) if usd_hi else None,
                              "share_served_wrong_in_selection": round(S.mean(not correct(r["served"], r["gold"]) for r in sel), 3)}
    # the grounding split itself on the pool
    for gflag in (True, False):
        sel = [r for r in pool if r["grounded"] == gflag and not is_null(r["served"])]
        if sel:
            out[f"pool_grounded={gflag}"] = {"cells": len(sel), "served_accuracy": round(S.mean(correct(r["served"], r["gold"]) for r in sel), 3),
                                             "fix_rate_of_wrong": round(sum(r["fix"] for r in sel) / max(1, sum(not correct(r["served"], r["gold"]) for r in sel)), 3),
                                             "break_rate_of_right": round(sum(r["break"] for r in sel) / max(1, sum(correct(r["served"], r["gold"]) for r in sel)), 3)}
    return out


def position(rows: list[dict]) -> dict:
    """Per column, where stated gold values sit; the share of a document a column needs (90th percentile) and the
    token share that reading only that far would save, per corpus."""
    out = {}
    for c in CORPORA:
        docs = Docs(c)
        gold = gold_by_doc(c)
        fields = fields_of(c)
        ctx = docs.ctx
        cols = {}
        for t, rows_t in gold.items():
            if t not in ctx.docs:
                continue
            per = defaultdict(list)
            for d, g in rows_t.items():
                if d not in ctx.docs[t]:
                    continue
                text = docs.text(t, d)
                for a, v in g.items():
                    if is_null(v) or trivial(v) or f"{t}.{a}" not in fields:
                        continue
                    ok, pos = found(text, v)
                    if ok:
                        per[f"{t}.{a}"].append(pos)
            for col, ps in per.items():
                if len(ps) >= 10:
                    ps.sort()
                    cols[col] = {"stated_values": len(ps), "median": round(ps[len(ps) // 2], 3), "p90": round(ps[int(0.9 * len(ps))], 3),
                                 "kind": kind_of(fields[col])}
        if cols:
            p90s = [v["p90"] for v in cols.values()]
            out[c] = {"columns": len(cols), "mean_p90": round(S.mean(p90s), 3),
                      "columns_needing_first_half_only": sum(v["p90"] <= 0.5 for v in cols.values()),
                      "columns_needing_first_quarter_only": sum(v["p90"] <= 0.25 for v in cols.values()),
                      "token_share_saved_reading_to_p90_per_column": round(1 - S.mean(p90s), 3),
                      "by_kind": {k: round(S.mean(v["p90"] for v in cols.values() if v["kind"] == k), 3)
                                  for k in ("number", "category", "list", "free text") if any(v["kind"] == k for v in cols.values())},
                      "columns_detail": cols}
    return out


def main() -> dict:
    rows = cells()
    out = {"grounding": grounding(rows), "classifier": classifier(rows), "cascade": cascade(rows), "position": position(rows)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    # the per-cell verifier scores (out-of-fold by column), for the routed second looks (I2b, exp_secondlook)
    with (OUT / "cells.jsonl").open("w") as h:
        for r in rows:
            h.write(json.dumps({"corpus": r["corpus"], "column": r["column"], "doc": r["doc"],
                                "p_wrong": round(r.get("p_wrong_all", 0.0), 4), "disagree": r["disagree"],
                                "grounded": r["grounded"], "grounded_all": r["grounded_all"], "empty": r["empty"]}) + "\n")
    return out


if __name__ == "__main__":
    o = main()
    print(json.dumps({k: ({kk: vv for kk, vv in v.items() if kk != "columns_detail"} if k != "position" else
                          {c: {kk: vv for kk, vv in x.items() if kk != "columns_detail"} for c, x in v.items()})
                      for k, v in o.items()}, indent=1)[:9000])
