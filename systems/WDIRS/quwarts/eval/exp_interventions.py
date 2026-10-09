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
                          ("frozen_forecast", EXP / "I4-bgroup-forecast" / "live"), ("frozen_unlimited", EXP / "E14-bgroup" / "live")):
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=["i3", "i4"])
    a = ap.parse_args(argv)
    o = {"i3": i3, "i4": i4}[a.what]()
    print(json.dumps({k: v for k, v in o.items() if k not in ("columns", "streams")}, indent=1, default=str)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
