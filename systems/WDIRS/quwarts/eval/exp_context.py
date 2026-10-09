"""Extraction context as a hidden argument of a cell's value (results/experiments/WHY/context/summary.json).

    python -m quwarts.eval.exp_context

From the logged reads of every run (build and on-demand prompts; 7B, 32B and Llama), each (document, column) value
is tagged with the *context* it was asked in: the set of columns in the same prompt. Per column and run:
  - context sensitivity: share of documents whose value differs between two contexts;
  - accuracy per context width (number of columns asked together), and the empty-answer rate per width;
  - whether sensitivity is a property of the column: rank correlation across models, and 7B sensitivity vs
    32B / Llama accuracy.
No model calls.
"""

from __future__ import annotations

import json
import statistics as S
from collections import defaultdict
from pathlib import Path

from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import EXP, REPO, gold_by_doc, is_null, parse
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_transfer import kind_of
from quwarts.eval.exp_why import norm, spearman

LIVE = REPO / "results" / "drift_live_ollama"
CORPORA = ["cspaper", "player", "art", "med", "legal"]
RUNS = {  # model -> corpus -> directory with build_reads.jsonl and patch_reads.jsonl
    "qwen7b": {c: LIVE / c for c in CORPORA},
    "qwen32b": {"cspaper": EXP / "E6.2-stream-qwen32b-cspaper" / "live" / "cspaper",
                "player": EXP / "E6.2-stream-qwen32b-player" / "live" / "player",
                "art": EXP / "E6.3-qwen32b-art" / "live" / "art",
                "med": EXP / "E6.3-qwen32b-med" / "live" / "med",
                "legal": EXP / "E6.3-qwen32b-legal" / "live" / "legal"},
    "llama8b": {"cspaper": EXP / "E6.2-stream-llama8b-cspaper" / "live" / "cspaper",
                "player": EXP / "E6.2-stream-llama8b-player" / "live" / "player",
                "art": EXP / "E6.3-llama8b-art" / "live" / "art",
                "med": EXP / "E6.3-llama8b-med" / "live" / "med"},
}
WIDTH_BINS = ((1, 1), (2, 3), (4, 7), (8, 10**6))


def vnorm(v):
    if is_null(v):
        return None
    try:
        return repr(round(float(str(v).replace(",", "")), 6))
    except ValueError:
        return norm(v)


def width_bin(w: int) -> str:
    for lo, hi in WIDTH_BINS:
        if lo <= w <= hi:
            return f"{lo}" if lo == hi else (f"{lo}-{hi}" if hi < 10**6 else f"{lo}+")
    return "?"


def load(d: Path, exclude_shas: set | None = None) -> dict:
    """(table, doc, attr) -> list of (context, value); context = tuple of columns asked in the same prompt.
    ``exclude_shas``: prompts to leave out (an ablation's journal starts with a copy of the recorded run's reads)."""
    vals = defaultdict(list)
    for name in ("build_reads.jsonl", "patch_reads.jsonl"):
        f = d / name
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if exclude_shas and r.get("prompt_sha") in exclude_shas:
                continue
            ctx = tuple(sorted(r["attributes"]))
            got = parse(r["response"])
            for a in r["attributes"]:
                vals[(r["table"], r["doc"], a)].append((ctx, got.get(a)))
    return vals


def fields_of(c: str) -> dict:
    from quwarts.eval.drift_live import supplement_spec

    ctx = R.context(c)
    return {**ctx.fields, **ctx.lean_fields, **supplement_spec(c, "attribute_pool")["fields"]}


def column_stats(vals: dict, gold: dict, fields: dict, c: str) -> list[dict]:
    per = defaultdict(lambda: defaultdict(list))  # col -> doc -> [(ctx, v)]
    for (t, d, a), lst in vals.items():
        per[f"{t}.{a}"][d].extend(lst)
    out = []
    for col, docs in per.items():
        t, a = col.split(".", 1)
        if col not in fields:
            continue
        g = gold.get(t, {})
        n_multi = dis = 0
        by_width = defaultdict(lambda: [0, 0, 0])  # bin -> [cells, correct, empty]
        narrow_wide = [0, 0, 0, 0, 0]  # docs with a narrow (<=3) and a wide (>=4) context: [n, differ, wide_empty_narrow_filled, narrow_correct, wide_correct]
        for d, lst in docs.items():
            gd = g.get(d) or g.get(str(d).rsplit(".", 1)[0])
            ctxs = {}
            for ctx, v in lst:
                ctxs.setdefault(ctx, v)  # first answer per context (repeated reads are identical by construction)
            if len(ctxs) >= 2:
                n_multi += 1
                dis += len({vnorm(v) for v in ctxs.values()}) > 1
                narrow = [v for ctx, v in ctxs.items() if len(ctx) <= 3]
                wide = [v for ctx, v in ctxs.items() if len(ctx) >= 4]
                if narrow and wide and gd is not None and a in gd:
                    narrow_wide[0] += 1
                    narrow_wide[1] += vnorm(narrow[0]) != vnorm(wide[0])
                    narrow_wide[2] += is_null(wide[0]) and not is_null(narrow[0])
                    narrow_wide[3] += correct(narrow[0], gd[a])
                    narrow_wide[4] += correct(wide[0], gd[a])
            if gd is None or a not in gd:
                continue
            for ctx, v in ctxs.items():
                b = by_width[width_bin(len(ctx))]
                b[0] += 1
                b[1] += correct(v, gd[a])
                b[2] += is_null(v)
        if n_multi < 10:
            continue
        acc_all = [correct(v, (g.get(d) or g.get(str(d).rsplit(".", 1)[0]))[a]) for d, lst in docs.items()
                   for _, v in lst[:1] if (g.get(d) or g.get(str(d).rsplit(".", 1)[0])) and a in (g.get(d) or g.get(str(d).rsplit(".", 1)[0]))]
        out.append({"corpus": c, "column": col, "kind": kind_of(fields[col]), "docs_with_two_contexts": n_multi,
                    "sensitivity": round(dis / n_multi, 3),
                    "accuracy": round(S.mean(acc_all), 3) if acc_all else None,
                    "narrow_vs_wide": {"docs": narrow_wide[0], "differ": round(narrow_wide[1] / narrow_wide[0], 3),
                                       "wide_empty_narrow_filled": round(narrow_wide[2] / narrow_wide[0], 3),
                                       "accuracy_narrow": round(narrow_wide[3] / narrow_wide[0], 3),
                                       "accuracy_wide": round(narrow_wide[4] / narrow_wide[0], 3)} if narrow_wide[0] >= 10 else None,
                    "by_width": {b: {"cells": v[0], "accuracy": round(v[1] / v[0], 3), "empty": round(v[2] / v[0], 3)}
                                 for b, v in sorted(by_width.items()) if v[0] >= 10}})
    return out


def main() -> dict:
    cols = {}
    for model, dirs in RUNS.items():
        for c, d in dirs.items():
            if not (d / "build_reads.jsonl").exists():
                continue
            cols[(model, c)] = column_stats(load(d), gold_by_doc(c), fields_of(c), c)
    out = {"columns": {f"{m}/{c}": v for (m, c), v in cols.items()}}
    # sensitivity by kind, per model
    out["sensitivity_by_kind"] = {}
    for model in RUNS:
        rows = [r for (m, _), v in cols.items() if m == model for r in v]
        out["sensitivity_by_kind"][model] = {
            k: {"columns": len(rs), "mean_sensitivity": round(S.mean(r["sensitivity"] for r in rs), 3),
                "mean_accuracy": round(S.mean(r["accuracy"] for r in rs if r["accuracy"] is not None), 3)}
            for k in ("number", "yes/no", "category", "list", "free text")
            if (rs := [r for r in rows if r["kind"] == k])}
        if len(rows) > 4:
            out["sensitivity_by_kind"][model]["spearman_sensitivity_vs_accuracy"] = round(spearman(
                [r["sensitivity"] for r in rows if r["accuracy"] is not None],
                [r["accuracy"] for r in rows if r["accuracy"] is not None]), 3)
            out["sensitivity_by_kind"][model]["columns"] = len(rows)
    # is sensitivity a property of the column? compare models on shared columns
    by = {m: {(r["corpus"], r["column"]): r for (mm, _), v in cols.items() if mm == m for r in v} for m in RUNS}
    out["across_models"] = {}
    for a, b in (("qwen7b", "qwen32b"), ("qwen7b", "llama8b"), ("qwen32b", "llama8b")):
        shared = sorted(k for k in set(by[a]) & set(by[b]) if by[a][k]["accuracy"] is not None and by[b][k]["accuracy"] is not None)
        if len(shared) < 5:
            continue
        out["across_models"][f"{a}_vs_{b}"] = {
            "shared_columns": len(shared),
            "spearman_sensitivity": round(spearman([by[a][k]["sensitivity"] for k in shared],
                                                   [by[b][k]["sensitivity"] for k in shared]), 3),
            "spearman_accuracy": round(spearman([by[a][k]["accuracy"] for k in shared],
                                                [by[b][k]["accuracy"] for k in shared]), 3),
            f"spearman_{a}_sensitivity_vs_{b}_accuracy": round(spearman(
                [by[a][k]["sensitivity"] for k in shared], [by[b][k]["accuracy"] for k in shared]), 3),
            f"mean_sensitivity_{a}": round(S.mean(by[a][k]["sensitivity"] for k in shared), 3),
            f"mean_sensitivity_{b}": round(S.mean(by[b][k]["sensitivity"] for k in shared), 3)}
    # width effect: pooled over columns, per model and kind
    out["width_effect"] = {}
    for model in RUNS:
        rows = [r for (m, _), v in cols.items() if m == model for r in v]
        agg = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
        for r in rows:
            for b, e in r["by_width"].items():
                x = agg[r["kind"]][b]
                x[0] += e["cells"]
                x[1] += round(e["accuracy"] * e["cells"])
                x[2] += round(e["empty"] * e["cells"])
        out["width_effect"][model] = {k: {b: {"cells": v[0], "accuracy": round(v[1] / v[0], 3), "empty": round(v[2] / v[0], 3)}
                                          for b, v in sorted(bs.items())} for k, bs in agg.items()}
        # paired, within column: the same documents asked in a narrow (<= 3 columns) and a wide (>= 4) prompt
        paired = {}
        for k in ("all", "number", "yes/no", "category", "list", "free text"):
            nw = [r for r in rows if r["narrow_vs_wide"] and (k == "all" or r["kind"] == k)]
            if nw:
                paired[k] = {"columns": len(nw), "docs": sum(r["narrow_vs_wide"]["docs"] for r in nw),
                             "share_differ": round(S.mean(r["narrow_vs_wide"]["differ"] for r in nw), 3),
                             "accuracy_narrow": round(S.mean(r["narrow_vs_wide"]["accuracy_narrow"] for r in nw), 3),
                             "accuracy_wide": round(S.mean(r["narrow_vs_wide"]["accuracy_wide"] for r in nw), 3),
                             "columns_better_narrow": sum(r["narrow_vs_wide"]["accuracy_narrow"] > r["narrow_vs_wide"]["accuracy_wide"] + 0.02 for r in nw),
                             "columns_better_wide": sum(r["narrow_vs_wide"]["accuracy_wide"] > r["narrow_vs_wide"]["accuracy_narrow"] + 0.02 for r in nw),
                             "wide_empty_narrow_filled": round(S.mean(r["narrow_vs_wide"]["wide_empty_narrow_filled"] for r in nw), 3)}
        out["width_effect"][model]["paired_within_column"] = paired
    d = EXP / "WHY" / "context"
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    return out

# ------------------------------------------------------------------ items 4 and 5 of the plan (no GPU)

ABLATIONS = {  # kind of context change -> run whose patches differ from the recorded run in that one respect
    "description": EXP / "E13-nodesc" / "live",   # field descriptions removed from on-demand prompts
    "usage": EXP / "E13-nousage" / "live",        # the workload-use phrase removed
    "grouping": EXP / "E14-bgroup" / "live",      # every patch asks the table's whole new-column set
    "window": EXP / "E13-head" / "live",          # long documents read up to the window only
}


def kinds_of_change() -> dict:
    """Per column, the share of documents whose value changes under each kind of context change, from the ablation
    logs; then whether the column ranking is the same across kinds (Spearman) and how each kind relates to accuracy."""
    rows = []
    for c in CORPORA:
        main = load(LIVE / c)
        mctx: dict[tuple, dict[tuple, object]] = {}
        for k, lst in main.items():
            d = {}
            for ctx, v in lst:
                d.setdefault(ctx, v)
            mctx[k] = d
        fields = fields_of(c)
        gold = gold_by_doc(c)
        stats = {r["column"]: r for r in column_stats(main, gold, fields, c)}
        per: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for name, d in ABLATIONS.items():
            if not (d / c / "patch_reads.jsonl").exists():
                continue
            main_shas = {json.loads(line)["prompt_sha"] for name in ("build_reads.jsonl", "patch_reads.jsonl")
                         for line in (LIVE / c / name).read_text().splitlines() if line.strip()}
            abl = load(d / c, exclude_shas=main_shas)  # the ablation's own reads only
            seen = set()
            for (t, dd, a), lst in abl.items():
                if (t, dd, a) not in mctx or (t, dd, a) in seen:
                    continue
                m = mctx[(t, dd, a)]
                for ctx, v in lst:
                    if name == "grouping":
                        narrow = min(m, key=len)  # the recorded run's narrowest context for this cell
                        mv = m[narrow]
                    elif ctx in m:
                        mv = m[ctx]
                    else:
                        continue
                    per[f"{t}.{a}"][name].append(vnorm(mv) != vnorm(v))
                    seen.add((t, dd, a))
                    break
        for col, kinds in per.items():
            e = {"corpus": c, "column": col, "kind": kind_of(fields[col]) if col in fields else "?",
                 "accuracy": stats.get(col, {}).get("accuracy"), "sensitivity": stats.get(col, {}).get("sensitivity")}
            for name, flags in kinds.items():
                if len(flags) >= 10:
                    e[name] = round(S.mean(flags), 3)
                    e[name + "_docs"] = len(flags)
            if any(k in e for k in ABLATIONS):
                rows.append(e)
    out = {"columns": rows, "spearman_between_kinds": {}, "spearman_vs_accuracy": {}, "mean_by_kind_of_column": {}}
    names = list(ABLATIONS) + ["sensitivity"]
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            rs = [r for r in rows if r.get(x) is not None and r.get(y) is not None]
            if len(rs) >= 8:
                out["spearman_between_kinds"][f"{x}_vs_{y}"] = {"columns": len(rs),
                                                                "spearman": round(spearman([r[x] for r in rs], [r[y] for r in rs]), 3)}
        rs = [r for r in rows if r.get(x) is not None and r.get("accuracy") is not None]
        if len(rs) >= 8:
            out["spearman_vs_accuracy"][x] = {"columns": len(rs), "spearman": round(spearman([r[x] for r in rs], [r["accuracy"] for r in rs]), 3),
                                              "mean": round(S.mean(r[x] for r in rs), 3)}
    for k in ("number", "yes/no", "category", "list", "free text"):
        rs = [r for r in rows if r["kind"] == k]
        if rs:
            out["mean_by_kind_of_column"][k] = {x: round(S.mean(r[x] for r in rs if r.get(x) is not None), 3)
                                                for x in names if any(r.get(x) is not None for r in rs)}
            out["mean_by_kind_of_column"][k]["columns"] = len(rs)
    d = EXP / "WHY" / "context"
    (d / "kinds_of_change.json").write_text(json.dumps(out, indent=1))
    return out


def sample_curve(reps: int = 30) -> dict:
    """How many documents the signal needs: per 7B column, sensitivity estimated from n sampled documents against the
    column's full-corpus accuracy, Spearman over columns, averaged over random draws."""
    import random

    flags_by_col: dict[tuple, list[int]] = {}
    acc: dict[tuple, float] = {}
    for c in CORPORA:
        main = load(LIVE / c)
        fields = fields_of(c)
        gold = gold_by_doc(c)
        for r in column_stats(main, gold, fields, c):
            if r["accuracy"] is not None:
                acc[(c, r["column"])] = r["accuracy"]
        per: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(dict))
        for (t, d, a), lst in main.items():
            for ctx, v in lst:
                per[f"{t}.{a}"][d].setdefault(ctx, v)
        for col, docs in per.items():
            fl = [int(len({vnorm(v) for v in ctxs.values()}) > 1) for ctxs in docs.values() if len(ctxs) >= 2]
            if (c, col) in acc and len(fl) >= 10:
                flags_by_col[(c, col)] = fl
    out = {"columns": len(flags_by_col)}
    full = {k: S.mean(v) for k, v in flags_by_col.items()}
    keys = sorted(flags_by_col)
    out["full"] = {"columns": len(keys), "spearman": round(spearman([full[k] for k in keys], [acc[k] for k in keys]), 3)}
    for n in (5, 10, 20, 40):
        ks = [k for k in keys if len(flags_by_col[k]) >= n]
        if len(ks) < 8:
            continue
        rhos = []
        for rep in range(reps):
            rng = random.Random(f"{n}:{rep}")
            est = [S.mean(rng.sample(flags_by_col[k], n)) for k in ks]
            rhos.append(spearman(est, [acc[k] for k in ks]))
        out[f"n={n}"] = {"columns": len(ks), "spearman_mean": round(S.mean(rhos), 3),
                         "spearman_min": round(min(rhos), 3), "spearman_max": round(max(rhos), 3),
                         "spearman_full_on_same_columns": round(spearman([full[k] for k in ks], [acc[k] for k in ks]), 3)}
    (EXP / "WHY" / "context" / "sample_curve.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    import sys

    if "--kinds" in sys.argv:
        o = kinds_of_change()
        print(json.dumps({k: v for k, v in o.items() if k != "columns"}, indent=1))
    elif "--sample" in sys.argv:
        print(json.dumps(sample_curve(), indent=1))
    else:
        o = main()
        print(json.dumps({k: v for k, v in o.items() if k != "columns"}, indent=1))
