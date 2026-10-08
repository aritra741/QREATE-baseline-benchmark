"""Where queries fail and why: per-query results broken down by query features, at every drift level.

    ~/venvs/quwarts/bin/python results/experiments/why/breakdown.py

Sources: per-query query features (E9-query-types/per_query.csv), per-query structure F2, cell F1 and row counts for
the unlimited on-demand runs at each drift level (E2.4-errors/<corpus>/per_query.csv), static-build scores per level
(drift_live_ollama streams). Writes results/experiments/why/breakdown.json and figures/b*.png.
"""

import csv
import json
import statistics as S
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
RES = EXP.parent
CORPORA = ["cspaper", "player", "art", "med", "legal"]
LEVELS = (0, 25, 50, 75, 100)
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "savefig.facecolor": SURFACE})

feat = {r["qid"]: r for r in csv.DictReader(open(EXP / "E9-query-types" / "per_query.csv"))}
comp = defaultdict(dict)  # (qid) -> level -> row
for c in CORPORA:
    for r in csv.DictReader(open(EXP / "E2.4-errors" / c / "per_query.csv")):
        if r["system"].startswith("unlimited@"):
            comp[r["qid"]][int(r["system"].split("@")[1])] = r
static = defaultdict(dict)
for c in CORPORA:
    for p in LEVELS:
        for line in open(RES / "drift_live_ollama" / c / "streams" / f"fixed4-attribute_pool_{p}.jsonl"):
            x = json.loads(line)
            static[x["qid"]][p] = x["static_benchmark"]


def agg_kind(r):
    a = json.loads(r["aggs"])
    if not a:
        return "none"
    if len(set(a)) > 1:
        return "several"
    k = a[0]
    return {"min_text": "MIN/MAX (text-stored numbers)", "max_text": "MIN/MAX (text-stored numbers)"}.get(k, k.upper().replace("_NUM", ""))


DIMS = {
    "Aggregate": agg_kind,
    "Filter conditions": lambda r: {0: "0", 1: "1", 2: "2"}.get(int(r["n_predicates"]), "3+"),
    "Joins": lambda r: {0: "0", 1: "1"}.get(int(r["joins"]), "2+"),
    "Tables": lambda r: r["n_tables"] if int(r["n_tables"]) < 3 else "3+",
}

rows = []
for q, f in feat.items():
    if q not in comp or 100 not in comp[q]:
        continue
    row = {"qid": q, "corpus": f["corpus"]}
    for d, fn in DIMS.items():
        row[d] = fn(f)
    for p in LEVELS:
        cp = comp[q].get(p)
        if cp is None:
            continue
        row[f"patched_{p}"] = float(cp["product"])
        row[f"structure_{p}"] = float(cp["structure_f2"])
        row[f"cell_{p}"] = float(cp["cell_f1_20"])
        row[f"label_{p}"] = cp["label"]
        pr, gr = int(cp["pred_rows"] or 0), int(cp["gold_rows"] or 0)
        row[f"rows_{p}"] = "no rows" if pr == 0 else "too few" if pr < gr else "too many" if pr > gr else "same"
        row[f"static_{p}"] = static[q].get(p)
    rows.append(row)

out = {"queries": len(rows), "by": {}}
for d in DIMS:
    groups = defaultdict(list)
    for r in rows:
        groups[r[d]].append(r)
    res = {}
    for g, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        e = {"queries": len(rs), "corpora": sorted({r["corpus"] for r in rs})}
        for p in LEVELS:
            vals = [r for r in rs if f"patched_{p}" in r]
            if not vals:
                continue
            e[f"patched_{p}"] = round(S.mean(r[f"patched_{p}"] for r in vals), 3)
            e[f"static_{p}"] = round(S.mean(r[f"static_{p}"] for r in vals if r[f"static_{p}"] is not None), 3)
        h = [r for r in rs if "structure_100" in r]
        e["structure_100"] = round(S.mean(r["structure_100"] for r in h), 3)
        e["cell_100"] = round(S.mean(r["cell_100"] for r in h), 3)
        lab = defaultdict(int)
        rws = defaultdict(int)
        for r in h:
            lab[r["label_100"]] += 1
            rws[r["rows_100"]] += 1
        e["labels_100"] = dict(lab)
        e["rows_100"] = dict(rws)
        res[g] = e
    out["by"][d] = res
(HERE / "breakdown.json").write_text(json.dumps(out, indent=1))


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


# Figure: patched and static score across drift levels, per group, for each dimension
def curves(dim, name, keep=None):
    res = out["by"][dim]
    groups = [g for g in res if (keep is None or g in keep) and res[g]["queries"] >= 12][:5]
    cols = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(11, 3.9), sharey=True)
    for i, g in enumerate(groups):
        e = res[g]
        ax.plot(LEVELS, [e[f"patched_{p}"] for p in LEVELS], marker="o", color=cols[i % 6], label=f"{g} ({e['queries']})",
                markeredgecolor=SURFACE)
        bx.plot(LEVELS, [e[f"static_{p}"] for p in LEVELS], marker="o", color=cols[i % 6], linestyle=(0, (4, 2.5)),
                markeredgecolor=SURFACE)
    for a, t in ((ax, "(a) With on-demand extraction"), (bx, "(b) Static build")):
        a.set_xticks(LEVELS, [f"{p}%" for p in LEVELS])
        a.set_xlabel("Drift")
        a.set_title(t, fontsize=10.5, loc="left", color=INK)
        style(a)
    ax.set_ylabel("Mean score")
    ax.set_ylim(0, None)
    fig.legend(*ax.get_legend_handles_labels(), fontsize=8.5, frameon=False, loc="upper center", ncol=len(groups),
               title=f"{dim} (queries)", title_fontsize=8.5, bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(HERE / "figures" / name, dpi=180)
    plt.close(fig)


curves("Aggregate", "b1_aggregate_drift.png")
curves("Filter conditions", "b2_filters_drift.png")
curves("Joins", "b3_joins_drift.png")


# Figure: failure composition at 100% drift for each group of a dimension
def failures(dim, name):
    res = out["by"][dim]
    groups = [g for g in res if res[g]["queries"] >= 8]
    kinds = [("no rows", "No rows returned", MUTED), ("structure", "Wrong rows or groups", ORANGE),
             ("values", "Right rows, wrong values", YELLOW), ("ok", "Fully right", AQUA)]
    fig, ax = plt.subplots(figsize=(9.5, 0.55 * len(groups) + 1.4))
    for i, g in enumerate(groups):
        n = res[g]["queries"]
        left = 0
        for k, lab, col in kinds:
            v = res[g]["labels_100"].get(k, 0) / n
            ax.barh(i, v, left=left, color=col, height=0.6, label=lab if i == 0 else None)
            if v >= 0.08:
                ax.text(left + v / 2, i, f"{v:.0%}", ha="center", va="center", fontsize=8.5, color="white" if col != YELLOW else INK)
            left += v
    ax.set_yticks(range(len(groups)), [f"{g} ({res[g]['queries']})" for g in groups])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4, fontsize=8.5, frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(HERE / "figures" / name, dpi=180)
    plt.close(fig)


failures("Aggregate", "b4_aggregate_failures.png")
failures("Filter conditions", "b5_filter_failures.png")
print(json.dumps({d: {g: {k: v for k, v in e.items() if k in ("queries", "patched_0", "patched_100", "static_100",
                                                              "structure_100", "cell_100", "labels_100", "rows_100")}
                      for g, e in out["by"][d].items()} for d in DIMS}, indent=1))


# Figures from the group and aggregate analysis (groups.json, quwarts.eval.exp_groups)
gj = json.loads((HERE / "groups.json").read_text())["summary"]


def aggregate_direction():
    d = gj["aggregate_direction"]
    order = ["MIN", "SUM", "MAX", "AVG", "COUNT"]
    fig, ax = plt.subplots(figsize=(9.5, 3.4))
    for i, k in enumerate(order):
        e = d[k]
        left = 0
        for key, lab, col in (("below", "Too low", BLUE), ("within", "Within 20% of gold", AQUA), ("above", "Too high", ORANGE)):
            ax.barh(i, e[key], left=left, color=col, height=0.6, label=lab if i == 0 else None)
            if e[key] >= 0.06:
                ax.text(left + e[key] / 2, i, f"{e[key]:.0%}", ha="center", va="center", fontsize=8.5, color="white")
            left += e[key]
    ax.set_yticks(range(len(order)), [f"{k} ({d[k]['groups']} groups)" for k in order])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, fontsize=8.5, frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "b6_aggregate_direction.png", dpi=180)
    plt.close(fig)


def distinct_labels():
    names = {"cspaper": "Research papers", "med": "Medical", "art": "Artists", "player": "Basketball players",
             "legal": "Court judgments"}
    pc = gj["per_corpus_distinct"]
    order = sorted(pc, key=lambda c: pc[c]["median_ratio"])
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(11, 3.6))
    ax.barh(range(len(order)), [pc[c]["median_ratio"] for c in order], color=BLUE, height=0.55)
    for i, c in enumerate(order):
        ax.annotate(f"{pc[c]['median_ratio']:.2f}", (pc[c]["median_ratio"], i), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=9)
    ax.axvline(1, color=AXIS, linestyle="--", linewidth=1)
    ax.set_yticks(range(len(order)), [names[c] for c in order])
    ax.set_xlim(0, 1.2)
    ax.set_xlabel("Distinct values in the extracted GROUP BY column ÷ in gold (median)")
    ax.set_title("(a) Extracted labels collapse", fontsize=10.5, loc="left", color=INK)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    sg = gj["score_by_gold_groups"]
    ks = list(sg)
    bx.bar(range(len(ks)), [sg[k]["share_too_few_groups"] for k in ks], color=ORANGE, width=0.55)
    for i, k in enumerate(ks):
        bx.annotate(f"{sg[k]['share_too_few_groups']:.0%}", (i, sg[k]["share_too_few_groups"]), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=9)
    bx.set_xticks(range(len(ks)), [f"{k}\n({sg[k]['queries']})" for k in ks])
    bx.set_xlabel("Groups in the gold answer (queries)")
    bx.set_ylabel("Queries returning too few groups")
    bx.set_ylim(0, 1)
    bx.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    bx.set_title("(b) More groups, more of them missed", fontsize=10.5, loc="left", color=INK)
    style(bx)
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "b7_label_collapse.png", dpi=180)
    plt.close(fig)


def label_fate():
    d = gj["label_fate"]
    NAMES = {"cspaper": "Research papers", "player": "Basketball players", "art": "Artists", "med": "Medical",
             "legal": "Court judgments", "numeric": "Numbers", "categorical": "Free categories",
             "two-valued": "Two values (yes/no, 0/1)", "multi-valued": "Lists of values"}
    parts = (("exact", "Exact gold label", AQUA), ("other_form", "Own label, other form", BLUE),
             ("merged", "Merged into another group", ORANGE), ("empty", "Left empty", MUTED))
    fig, (ax, bx) = plt.subplots(2, 1, figsize=(9.5, 5.4), gridspec_kw={"height_ratios": [4, 5]})
    for a, rows, title in ((ax, [(k, d["per_column_kind"][k]) for k in ("numeric", "categorical", "two-valued", "multi-valued")],
                            "(a) By kind of GROUP BY column"),
                           (bx, [(c, d["per_corpus"][c]) for c in CORPORA], "(b) By corpus")):
        for i, (k, e) in enumerate(rows):
            left = 0
            for key, lab, col in parts:
                v = e.get(key, 0)
                a.barh(i, v, left=left, color=col, height=0.6, label=lab if (i == 0 and a is ax) else None)
                if v >= 0.06:
                    a.text(left + v / 2, i, f"{v:.0%}", ha="center", va="center", fontsize=8.5, color="white")
                left += v
        a.set_yticks(range(len(rows)), [NAMES[k] + (f" ({e['rows']:,} rows)" if "rows" in e else "") for k, e in rows])
        a.invert_yaxis()
        a.set_xlim(0, 1)
        a.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        a.set_title(title, fontsize=10.5, loc="left", color=INK)
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
    fig.legend(loc="upper center", ncol=4, fontsize=8.5, frameon=False, bbox_to_anchor=(0.55, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(HERE / "figures" / "b8_label_fate.png", dpi=180)
    plt.close(fig)


aggregate_direction()
distinct_labels()
label_fate()
