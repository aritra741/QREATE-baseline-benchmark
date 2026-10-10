"""Analyses of the interventions I3 (frozen DocETL) and I4 (forecast policy, frozen contexts); results/experiments/WHY/i3, i4.

    python -m quwarts.eval.exp_interventions i3
    python -m quwarts.eval.exp_interventions i4
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import statistics as S
from collections import defaultdict
from pathlib import Path

from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import EXP, REPO, gold_by_doc, is_null
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_transfer import kind_of
from quwarts.eval.exp_why import norm, save, spearman

CORPORA = ["cspaper", "player", "art", "med", "legal"]
ORIG = REPO / "results" / "docetl_drift_ollama"
VARIANTS = {"frozen": REPO / "results" / "docetl_frozen_ollama", "frozen2": REPO / "results" / "docetl_frozen2_ollama",
            "frozen4": REPO / "results" / "docetl_frozen4_ollama", "frozen2_rep": REPO / "results" / "docetl_frozen2_ollama_rep"}


def nonempty_disagreement(tries: list[dict]) -> float | None:
    """Disagreement between the first two contexts over the documents both answered (empties excluded)."""
    if len(tries) < 2:
        return None
    t1, t2 = tries[0]["values"], tries[1]["values"]
    both = [d for d in t1 if d in t2 and not is_null(t1[d]) and not is_null(t2[d])
            and t1[d] not in (-1, "Not found") and t2[d] not in (-1, "Not found")]
    if len(both) < 10:
        return None
    return round(sum(norm(t1[d]) != norm(t2[d]) for d in both) / len(both), 3)


def keys_db(db: Path, t: str, c: str) -> list:
    conn = sqlite3.connect(db)
    try:
        return [v for (v,) in conn.execute(f'SELECT "{c}" FROM "{t}"')]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def rate(left_vals, right_vals):
    right = {norm(v) for v in right_vals if norm(v)}
    left = [norm(v) for v in left_vals if norm(v)]
    return (sum(v in right for v in left) / len(left)) if left else None


def i3() -> dict:
    out = {}
    for name, root in VARIANTS.items():
        if root.exists():
            out[name] = i3_variant(root)
    return save("i3", out)


def i3_variant(FROZEN: Path) -> dict:
    """Frozen vs original DocETL: per query (join / no join), join-key match rates, and per-column accuracy change
    against the column's 7B context sensitivity."""
    sens = json.loads((EXP / "WHY" / "context" / "summary.json").read_text())["columns"]
    out = {"corpora": {}, "join_keys": {}, "columns": []}
    for c in CORPORA:
        po, pf = ORIG / c / "per_query.json", FROZEN / c / "per_query.json"
        if not (po.exists() and pf.exists()):
            continue
        o, f = json.loads(po.read_text()), json.loads(pf.read_text())
        ctx = R.context(c)
        common = [q for q in f if q in o and q in ctx.catalog]
        if not common:
            continue
        joins = [q for q in common if re.search(r"\bJOIN\b", ctx.catalog[q], re.I)]
        plain = [q for q in common if q not in joins]
        m = lambda d, qs: round(S.mean(d[q]["benchmark"] for q in qs), 4) if qs else None  # noqa: E731
        out["corpora"][c] = {"queries": len(common), "complete": (FROZEN / c / "complete.json").exists(),
                             "original": m(o, common), "frozen": m(f, common),
                             "join_queries": len(joins), "original_join": m(o, joins), "frozen_join": m(f, joins),
                             "original_nojoin": m(o, plain), "frozen_nojoin": m(f, plain),
                             "queries_better": sum(f[q]["benchmark"] > o[q]["benchmark"] + 1e-9 for q in common),
                             "queries_worse": sum(f[q]["benchmark"] < o[q]["benchmark"] - 1e-9 for q in common),
                             "calls_original": sum(o[q]["calls"] for q in common), "calls_frozen": sum(f[q]["calls"] for q in common),
                             "tokens_original": sum(o[q]["prompt_tokens"] + o[q]["completion_tokens"] for q in common),
                             "tokens_frozen": sum(f[q]["prompt_tokens"] + f[q]["completion_tokens"] for q in common)}
        # join keys (player): share of left rows whose key appears in the right table, per run
        if joins:
            per = defaultdict(lambda: {"original": [], "frozen": [], "gold": []})
            gold = R.Scorer(c).gold()[0]
            for q in joins:
                name = re.sub(r"[:/#]", "_", q)
                for lt, lc, rt, rc in re.findall(r"ON\s+(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)", ctx.catalog[q], re.I):
                    j = f"{lt}.{lc} = {rt}.{rc}"
                    for tag, root in (("original", ORIG), ("frozen", FROZEN)):
                        db = root / c / "db" / f"{name}.db"
                        if db.exists():
                            v = rate(keys_db(db, lt, lc), keys_db(db, rt, rc))
                            if v is not None:
                                per[j][tag].append(v)
                    g = rate([x.get(lc) for x in gold.get(lt, [])], [x.get(rc) for x in gold.get(rt, [])])
                    if g is not None:
                        per[j]["gold"].append(g)
            out["join_keys"][c] = {j: {k: round(S.mean(v), 3) if v else None for k, v in d.items()} for j, d in per.items()}
        # per column: accuracy of the frozen values (one extraction) vs the original's pooled values
        from quwarts.eval.exp_transfer import docetl_values
        from quwarts.eval.exp_context import fields_of

        fields = fields_of(c)
        gold_docs = gold_by_doc(c)
        orig_vals = docetl_values(c)
        by_col = {r["column"]: r["sensitivity"] for r in sens.get(f"qwen7b/{c}", [])}
        for cache in (FROZEN / c / "cache").glob("*.json"):
            t = cache.stem
            for a, e in json.loads(cache.read_text()).items():
                col = f"{t}.{a}"
                if col not in fields:
                    continue
                g = gold_docs.get(t, {})
                fr = [(v, (g.get(d) or g.get(str(d).rsplit(".", 1)[0]))) for d, v in e["values"].items()]
                fr = [(v, gd[a]) for v, gd in fr if gd and a in gd]
                ov = [(v, (g.get(d) or g.get(str(d).rsplit(".", 1)[0]))) for d, vs in orig_vals.get(col, {}).items() for v in vs]
                ov = [(v, gd[a]) for v, gd in ov if gd and a in gd and not is_null(v)]
                if len(fr) >= 10 and len(ov) >= 10:
                    out["columns"].append({"corpus": c, "column": col, "kind": kind_of(fields[col]),
                                           "sensitivity_7b": by_col.get(col), "docetl_sensitivity": e.get("sensitivity"),
                                           "docetl_sensitivity_nonempty": nonempty_disagreement(e.get("tries", [])),
                                           "tries": len(e.get("tries", [])), "filled": e.get("filled"),
                                           "accuracy_original": round(S.mean(correct(v, gg) for v, gg in ov), 3),
                                           "accuracy_frozen": round(S.mean(correct(v, gg) for v, gg in fr), 3),
                                           "empty_frozen": round(S.mean(is_null(v) for v, _ in fr), 3)})
    cols = [r for r in out["columns"] if r["sensitivity_7b"] is not None]
    if len(cols) > 4:
        out["spearman_sensitivity_vs_accuracy_change"] = round(spearman(
            [r["sensitivity_7b"] for r in cols], [r["accuracy_frozen"] - r["accuracy_original"] for r in cols]), 3)
        out["spearman_sensitivity_vs_frozen_accuracy"] = round(spearman(
            [r["sensitivity_7b"] for r in cols], [r["accuracy_frozen"] for r in cols]), 3)
    dn = [r for r in out["columns"] if r.get("docetl_sensitivity_nonempty") is not None and r["sensitivity_7b"] is not None]
    if len(dn) > 4:
        out["spearman_docetl_nonempty_disagreement_vs_7b_sensitivity"] = round(spearman(
            [r["docetl_sensitivity_nonempty"] for r in dn], [r["sensitivity_7b"] for r in dn]), 3)
        out["spearman_docetl_nonempty_disagreement_vs_frozen_accuracy"] = round(spearman(
            [r["docetl_sensitivity_nonempty"] for r in dn], [r["accuracy_frozen"] for r in dn]), 3)
        out["columns_with_nonempty_disagreement"] = len(dn)
    ds = [r for r in out["columns"] if r.get("docetl_sensitivity") is not None]
    if len(ds) > 4:  # DocETL's own two-context disagreement as a trust signal, inside DocETL
        out["spearman_docetl_sensitivity_vs_frozen_accuracy"] = round(spearman(
            [r["docetl_sensitivity"] for r in ds], [r["accuracy_frozen"] for r in ds]), 3)
        both = [r for r in ds if r["sensitivity_7b"] is not None]
        if len(both) > 4:
            out["spearman_docetl_sensitivity_vs_7b_sensitivity"] = round(spearman(
                [r["docetl_sensitivity"] for r in both], [r["sensitivity_7b"] for r in both]), 3)
    return out


def stream_stats(f: Path) -> dict | None:
    if not f.exists():
        return None
    rs = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    return {"score": round(S.mean(r["benchmark"] for r in rs), 4),
            "tokens": sum(r["input_tokens"] + r["output_tokens"] for r in rs),
            "patches": sum(r["action"] == "patch" for r in rs), "queries": len(rs)}


def i4() -> dict:
    """Budget policies at 100% drift, budgets 25% and 50%: frozen contexts (bgroup) under fcfs / pace / forecast, and
    forecast without freezing against the recorded fcfs and pace."""
    out = {"streams": {}, "summary": {}}
    runs = {"frozen_fcfs": EXP / "I4-bgroup-fcfs" / "live", "frozen_pace": EXP / "I4-bgroup-pace" / "live",
            "frozen_forecast": EXP / "I4-bgroup-forecast" / "live", "plain_forecast": EXP / "I4-plain-forecast" / "live",
            "recorded_fcfs": REPO / "results" / "drift_live_ollama", "recorded_pace": EXP / "E3.2-pace" / "live"}
    deltas = defaultdict(list)
    for c in CORPORA:
        for b in (25, 50):
            row = {}
            for name, root in runs.items():
                s = stream_stats(root / c / "streams" / f"fixed4b{b:03d}-attribute_pool_100.jsonl")
                if s:
                    row[name] = s
            if row:
                out["streams"][f"{c}/b{b}"] = row
                for a, base in (("frozen_forecast", "frozen_fcfs"), ("frozen_pace", "frozen_fcfs"),
                                ("plain_forecast", "recorded_fcfs"), ("frozen_fcfs", "recorded_fcfs"),
                                ("frozen_forecast", "recorded_fcfs")):
                    if a in row and base in row:
                        deltas[f"{a}_minus_{base}"].append((c, b, round(row[a]["score"] - row[base]["score"], 4),
                                                           round(row[a]["tokens"] / max(1, row[base]["tokens"]), 3)))
    for k, v in deltas.items():
        out["summary"][k] = {"streams": len(v), "mean_delta": round(S.mean(x[2] for x in v), 4),
                             "wins": sum(x[2] > 0.002 for x in v), "losses": sum(x[2] < -0.002 for x in v),
                             "mean_token_ratio": round(S.mean(x[3] for x in v), 3), "per_stream": v}
    # Budgets are shares of each family's own unlimited spend, and frozen (grouped) patches are several times cheaper,
    # so frozen and recorded streams are also compared on absolute tokens: score against tokens at level 100.
    out["score_vs_tokens"] = {}
    for c in CORPORA:
        curve = {}
        for fam, root in (("recorded", REPO / "results" / "drift_live_ollama"), ("frozen_fcfs", EXP / "I4-bgroup-fcfs" / "live"),
                          ("frozen_forecast", EXP / "I4-bgroup-forecast" / "live"), ("frozen_pace", EXP / "I4-bgroup-pace" / "live"),
                          ("plain_forecast", EXP / "I4-plain-forecast" / "live"), ("recorded_pace", EXP / "E3.2-pace" / "live"),
                          ("frozen_unlimited", EXP / "E14-bgroup" / "live")):
            pts = []
            for b in (10, 25, 50, 75, 100):
                st = stream_stats(root / c / "streams" / f"fixed4b{b:03d}-attribute_pool_100.jsonl")
                if st:
                    pts.append({"budget": b, "tokens": st["tokens"], "score": st["score"]})
            st = stream_stats(root / c / "streams" / "fixed4-attribute_pool_100.jsonl")
            if st and fam in ("recorded", "frozen_unlimited"):
                pts.append({"budget": "unlimited", "tokens": st["tokens"], "score": st["score"]})
            if pts:
                curve[fam] = pts
        if curve:
            out["score_vs_tokens"][c] = curve
    return save("i4", out)


SCRATCH = Path("/scratch/general/vast/u1592362/quwarts_exp")


def master_db(root_scratch: Path, c: str) -> Path:
    return root_scratch / c / "fixed4-attribute_pool_100" / "master.db"


def recorded_master(c: str) -> Path:
    from quwarts.eval.exp_analysis import REPLAY_SCRATCH
    from quwarts.eval.exp_open import HOME_SCRATCH

    p = HOME_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
    return p if p.exists() else REPLAY_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"


def journal_shas(root: Path, c: str) -> set:
    out = set()
    for name in ("build_reads.jsonl", "patch_reads.jsonl"):
        f = root / c / name
        if f.exists():
            out |= {json.loads(l).get("prompt_sha") for l in f.read_text().splitlines() if l.strip()}
    return out


def served_from_journals(root: Path, c: str, exclude: set) -> dict:
    """A cloned stream's own reads (its journal starts with a copy of the recorded one): (table, doc, attr) -> the
    first value this run read. The stream's database is removed when it completes, so values come from here."""
    from quwarts.eval.exp_context import load

    out = {}
    for (t, d, a), lst in load(root / c, exclude).items():
        v = lst[0][1]
        out[(t, d, a)] = " || ".join(str(x) for x in v) if isinstance(v, list) else v
    return out


class Served:
    """Values of a run: its own journal reads where it read, the recorded committed value elsewhere."""

    def __init__(self, c: str, root: Path | None):
        self.c = c
        self.rec = recorded_master(c)
        self.new = served_from_journals(root, c, journal_shas(REPO / "results" / "drift_live_ollama", c)) if root else {}
        self.cache: dict = {}

    def column(self, t: str, a: str) -> dict | None:
        from quwarts.eval.exp_open import column_values

        if (t, a) not in self.cache:
            pv = column_values(self.rec, t, a) if self.rec.exists() else None
            if pv is not None and self.new:
                pv = dict(pv)
                for (tt, d, aa), v in self.new.items():
                    if tt == t and aa == a:
                        pv[str(d)] = v
            self.cache[(t, a)] = pv
        return self.cache[(t, a)]


def label_fate_values(pv: dict | None, a: str, gold_t: dict) -> dict | None:
    """exp_groups.fate for one column given its values per document."""
    from collections import Counter

    from quwarts.eval.exp_groups import num
    from quwarts.eval.exp_open import lookup

    if pv is None:
        return None

    def vn(v):
        v = norm(v)
        return v if v is None or num(v) is None else repr(round(num(v), 6))

    pairs = [(vn(g[a]), vn(lookup(pv, d))) for d, g in gold_t.items() if a in g and not is_null(g[a])]
    by = defaultdict(Counter)
    for g, pr in pairs:
        if pr is not None:
            by[pr][g] += 1
    owner = {pr: cnt.most_common(1)[0][0] for pr, cnt in by.items()}
    cnt = Counter("empty" if pr is None else "exact" if pr == g else "other_form" if owner[pr] == g else "merged" for g, pr in pairs)
    n = max(1, len(pairs))
    return {"rows": len(pairs), **{k: round(cnt[k] / n, 3) for k in ("exact", "other_form", "merged", "empty")},
            "labels_served": len(by)}


def label_fate(db: Path, t: str, a: str, gold_t: dict) -> dict | None:
    """exp_groups.fate for one column on one database: where each gold row's label ends up (exact, its own label in
    another form, merged into a label that mostly holds another gold group, empty)."""
    from collections import Counter

    from quwarts.eval.exp_groups import num
    from quwarts.eval.exp_open import column_values, lookup

    pv = column_values(db, t, a) if db.exists() else None
    if pv is None:
        return None

    def vn(v):
        v = norm(v)
        return v if v is None or num(v) is None else repr(round(num(v), 6))

    pairs = [(vn(g[a]), vn(lookup(pv, d))) for d, g in gold_t.items() if a in g and not is_null(g[a])]
    by = defaultdict(Counter)
    for g, pr in pairs:
        if pr is not None:
            by[pr][g] += 1
    owner = {pr: cnt.most_common(1)[0][0] for pr, cnt in by.items()}
    cnt = Counter("empty" if pr is None else "exact" if pr == g else "other_form" if owner[pr] == g else "merged" for g, pr in pairs)
    n = max(1, len(pairs))
    return {"rows": len(pairs), **{k: round(cnt[k] / n, 3) for k in ("exact", "other_form", "merged", "empty")},
            "labels_served": len(by)}


def i6(exp: str = "I6-contract") -> dict:
    """The label contract (I6): the contracted columns' label fate and the stream score against the recorded run.
    ``exp``: the run's folder (a replicate, I6rep-contract, uses the same contract files)."""
    from quwarts.eval.exp_context import fields_of

    root = EXP / exp / "live"
    out = {"corpora": {}, "exp": exp}
    distinct = json.loads((EXP / "why" / "groups.json").read_text())["distinct"]
    for c in CORPORA:
        cf = EXP / "I6-contract" / f"{c}.json"
        if not cf.exists() or not json.loads(cf.read_text()):
            continue
        contract = json.loads(cf.read_text())
        rec = stream_stats(REPO / "results" / "drift_live_ollama" / c / "streams" / "fixed4-attribute_pool_100.jsonl")
        new = stream_stats(root / c / "streams" / "fixed4-attribute_pool_100.jsonl")
        gold = gold_by_doc(c)
        fields = fields_of(c)
        cols = {}
        s_rec, s_new = Served(c, None), Served(c, root if new else None)
        for col, labels in contract.items():
            t, a = col.split(".", 1)
            from quwarts.eval.exp_open import lookup

            docs = [d for d, g in gold.get(t, {}).items() if a in g]
            pv0, pv1 = s_rec.column(t, a), s_new.column(t, a)
            cols[col] = {"labels_declared": len(labels), "kind": kind_of(fields[col]) if col in fields else None,
                         "cells_reread": sum(1 for (tt, d, aa) in s_new.new if tt == t and aa == a),
                         "accuracy_recorded": round(S.mean(correct(lookup(pv0, d), gold[t][d][a]) for d in docs), 3) if docs and pv0 else None,
                         "accuracy_contract": round(S.mean(correct(lookup(pv1, d), gold[t][d][a]) for d in docs), 3) if docs and pv1 and new else None,
                         "recorded": label_fate_values(pv0, a, gold.get(t, {})),
                         "contract": label_fate_values(pv1, a, gold.get(t, {})) if new else None}
        # the test queries that group by a contracted column, paired
        qids = sorted({r["qid"] for r in distinct if r["corpus"] == c and r["column"] in contract})
        paired = None
        f_rec = REPO / "results" / "drift_live_ollama" / c / "streams" / "fixed4-attribute_pool_100.jsonl"
        f_new = root / c / "streams" / "fixed4-attribute_pool_100.jsonl"
        if f_rec.exists() and f_new.exists():
            r0 = {r["qid"]: r["benchmark"] for r in map(json.loads, f_rec.read_text().splitlines()) if r.get("qid")}
            r1 = {r["qid"]: r["benchmark"] for r in map(json.loads, f_new.read_text().splitlines()) if r.get("qid")}
            common = [q for q in qids if q in r0 and q in r1]
            if common:
                paired = {"queries": len(common), "recorded": round(S.mean(r0[q] for q in common), 4),
                          "contract": round(S.mean(r1[q] for q in common), 4),
                          "up": sum(r1[q] > r0[q] + 1e-9 for q in common), "down": sum(r1[q] < r0[q] - 1e-9 for q in common)}
        out["corpora"][c] = {"recorded": rec, "contract": new, "complete": new is not None and rec is not None and new["queries"] == rec["queries"],
                             "columns": cols, "grouping_queries": paired}
    return save("i6" if exp == "I6-contract" else exp.lower().replace("-", "_"), out)


def i7(exp: str = "I7-windows") -> dict:
    """Per-column read windows (I7): the stream's score and tokens against the recorded run and the first-window
    ablation (E13-head), and per-column accuracy against the window share. ``exp``: the run's folder, which also
    holds the share files (I7b-windows: the rule with its exemptions)."""
    from quwarts.eval.exp_context import fields_of
    from quwarts.eval.exp_open import column_values, lookup

    root = EXP / exp / "live"
    out = {"corpora": {}, "exp": exp}
    for c in CORPORA:
        wf = EXP / exp / f"{c}.json"
        if not wf.exists() or not json.loads(wf.read_text()):
            continue
        shares = json.loads(wf.read_text())
        rec = stream_stats(REPO / "results" / "drift_live_ollama" / c / "streams" / "fixed4-attribute_pool_100.jsonl")
        head = stream_stats(EXP / "E13-head" / "live" / c / "streams" / "fixed4-attribute_pool_100.jsonl")
        new = stream_stats(root / c / "streams" / "fixed4-attribute_pool_100.jsonl")
        gold = gold_by_doc(c)
        fields = fields_of(c)
        design = json.loads((REPO / "results" / "drift_live_ollama" / c / "fixed4_attribute_pool_design.json").read_text())
        cols = []
        s_rec, s_new = Served(c, None), Served(c, root if new else None)
        for col in design["new_columns"]:
            if col not in fields:
                continue
            t, a = col.split(".", 1)
            pv0 = s_rec.column(t, a)
            pv1 = s_new.column(t, a) if new else None
            if pv0 is None:
                continue
            docs = [d for d, g in gold.get(t, {}).items() if a in g]
            acc0 = round(S.mean(correct(lookup(pv0, d), gold[t][d][a]) for d in docs), 3) if docs else None
            acc1 = round(S.mean(correct(lookup(pv1, d), gold[t][d][a]) for d in docs), 3) if docs and pv1 is not None else None
            cols.append({"column": col, "kind": kind_of(fields[col]), "share": shares.get(col, 1.0), "cells": len(docs),
                         "accuracy_recorded": acc0, "accuracy_windows": acc1,
                         "delta": round(acc1 - acc0, 3) if acc0 is not None and acc1 is not None else None})
        summary = {}
        if new and rec:
            summary = {"score_delta_vs_recorded": round(new["score"] - rec["score"], 4),
                       "token_ratio_vs_recorded": round(new["tokens"] / max(1, rec["tokens"]), 3),
                       "token_ratio_vs_head": round(new["tokens"] / max(1, head["tokens"]), 3) if head else None,
                       "score_delta_vs_head": round(new["score"] - head["score"], 4) if head else None}
            done = [x for x in cols if x["delta"] is not None]
            if done:
                summary["mean_accuracy_delta_windowed"] = round(S.mean(x["delta"] for x in done if x["share"] < 1.0), 4) if any(x["share"] < 1.0 for x in done) else None
                summary["mean_accuracy_delta_whole"] = round(S.mean(x["delta"] for x in done if x["share"] >= 1.0), 4) if any(x["share"] >= 1.0 for x in done) else None
                summary["spearman_share_vs_delta"] = round(spearman([x["share"] for x in done], [x["delta"] for x in done]), 3) if len(done) > 4 else None
        out["corpora"][c] = {"recorded": rec, "head": head, "windows": new, "complete": new is not None and rec is not None and new["queries"] == rec["queries"],
                             "summary": summary, "columns": cols}
    return save("i7" if exp == "I7-windows" else exp.lower().replace("-", "_"), out)


def i5() -> dict:
    """The build's prompt groups (I5): the level-0 build re-made with every new column read alone, or grouped by the
    I1 rule (columns more accurate alone get their own prompt); the 0% stream's score and the per-column accuracy
    against the recorded build, with the I1 prediction per column (alone better / group better / no difference)."""
    from quwarts.eval.exp_analysis import REPLAY_SCRATCH
    from quwarts.eval.exp_context import fields_of
    from quwarts.eval.exp_open import HOME_SCRATCH, column_values, lookup

    i1 = json.loads((EXP / "I1-context" / "summary.json").read_text())["columns"]["qwen7b"]
    direction = {}
    for r in i1:
        a, n = r["accuracy"].get("alone"), r["accuracy"].get("natural")
        if a is not None and n is not None:
            direction[(r["corpus"], r["column"])] = "alone_better" if a - n >= 0.05 else "group_better" if n - a >= 0.05 else "same"
    out = {"kinds": {}}
    for kind in ("alone", "chosen"):
        root = EXP / f"I5-{kind}" / "live"
        res = {}
        for c in CORPORA:
            gf = EXP / "I5-groups" / f"{c}_{kind}.json"
            if not gf.exists():
                continue
            groups = json.loads(gf.read_text())
            rec = stream_stats(REPO / "results" / "drift_live_ollama" / c / "streams" / "fixed4-attribute_pool_0.jsonl")
            new = stream_stats(root / c / "streams" / "fixed4-attribute_pool_0.jsonl")
            gold = gold_by_doc(c)
            fields = fields_of(c)
            p0 = HOME_SCRATCH / c / "builds" / "fixed4_attribute_pool_0" / "build.db"  # the level-0 build's values
            if not p0.exists():
                p0 = REPLAY_SCRATCH / c / "builds" / "fixed4_attribute_pool_0" / "build.db"
            p1 = SCRATCH / f"I5-{kind}" / "drift_live_ollama" / c / "builds" / "fixed4_attribute_pool_0" / "build.db"
            alone_cols = {f"{t}.{g[0]}" for t, gs in groups.items() for g in gs if len(g) == 1}
            cols = []
            for t, gs in groups.items():
                for g in gs:
                    for a in g:
                        col = f"{t}.{a}"
                        if col not in fields:
                            continue
                        v0 = column_values(p0, t, a) if p0.exists() else None
                        v1 = column_values(p1, t, a) if p1.exists() else None
                        docs = [d for d, gg in gold.get(t, {}).items() if a in gg]
                        acc0 = round(S.mean(correct(lookup(v0, d), gold[t][d][a]) for d in docs), 3) if docs and v0 is not None else None
                        acc1 = round(S.mean(correct(lookup(v1, d), gold[t][d][a]) for d in docs), 3) if docs and v1 is not None else None
                        cols.append({"column": col, "kind": kind_of(fields[col]), "read_alone": col in alone_cols, "group_size": len(g),
                                     "i1_direction": direction.get((c, col)), "cells": len(docs),
                                     "accuracy_recorded": acc0, "accuracy_new": acc1,
                                     "delta": round(acc1 - acc0, 3) if acc0 is not None and acc1 is not None else None})
            done = [x for x in cols if x["delta"] is not None]
            summ = {}
            if new and rec:
                summ["score_delta_vs_recorded"] = round(new["score"] - rec["score"], 4)
            if done:
                for key in ("alone_better", "group_better", "same", None):
                    sel = [x for x in done if x["i1_direction"] == key and x["read_alone"]]
                    if sel:
                        summ[f"read_alone_and_i1_{key or 'unmeasured'}"] = {"columns": len(sel), "mean_delta": round(S.mean(x["delta"] for x in sel), 4),
                                                                           "up": sum(x["delta"] > 0.02 for x in sel), "down": sum(x["delta"] < -0.02 for x in sel)}
                grouped = [x for x in done if not x["read_alone"]]
                if grouped:
                    summ["still_grouped"] = {"columns": len(grouped), "mean_delta": round(S.mean(x["delta"] for x in grouped), 4)}
            builds = {}
            for name, broot in (("recorded", REPO / "results" / "drift_live_ollama"), ("new", root)):
                bf = broot / c / "builds" / "fixed4_attribute_pool_0.json"
                if bf.exists():
                    b = json.loads(bf.read_text())
                    builds[name] = {"measured_tokens": b.get("measured_tokens"), "supplement_calls": b.get("supplement_calls"),
                                    "supplement_tokens": b.get("supplement_tokens")}
            if "recorded" in builds and "new" in builds and builds["new"]["supplement_tokens"] and builds["recorded"]["supplement_tokens"]:
                summ["supplement_token_ratio"] = round(builds["new"]["supplement_tokens"] / builds["recorded"]["supplement_tokens"], 3)
            res[c] = {"recorded": rec, "new": new, "complete": new is not None and rec is not None and new["queries"] == rec["queries"],
                      "summary": summ, "builds": builds, "columns": cols}
        out["kinds"][kind] = res
    return save("i5", out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=["i3", "i4", "i5", "i6", "i7"])
    ap.add_argument("--exp", help="i6/i7: the run's folder under results/experiments (a replicate or variant)")
    a = ap.parse_args(argv)
    if a.what in ("i6", "i7") and a.exp:
        o = {"i6": i6, "i7": i7}[a.what](a.exp)
    else:
        o = {"i3": i3, "i4": i4, "i5": i5, "i6": i6, "i7": i7}[a.what]()
    print(json.dumps({k: v for k, v in o.items() if k not in ("columns", "streams")}, indent=1, default=str)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
