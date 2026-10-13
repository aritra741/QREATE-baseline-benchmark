"""Charts for the findings deck (results/experiments/why/figures/deck/*.png), one per evidence slide.

    ~/venvs/quwarts/bin/python results/experiments/why/deck_figures.py

Palette (validated with the dataviz validator on the slide surface): blue #2A6FB0, orange #C2551F, teal #1F8A70 for
series; gray #6F7883 only for labelled reference marks (DocETL, the version without the planner, zero lines).
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
OUT = HERE / "figures" / "deck"
BLUE, ORANGE, TEAL, GRAY = "#2A6FB0", "#C2551F", "#1F8A70", "#6F7883"
SURF, INK, INK2, GRID = "#F7F5F0", "#1B2430", "#3E4957", "#DDE1E5"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 16, "axes.titlesize": 17, "axes.labelsize": 16,
                     "xtick.labelsize": 15, "ytick.labelsize": 15, "legend.fontsize": 14, "axes.edgecolor": "#B9BEC4",
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
                     "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})
W, H = 8.6, 5.6  # inches at 200 dpi: 1720 x 1120, shown at 860 x 560 on the slide


def fig(w=W, h=H, **kw):
    f, ax = plt.subplots(figsize=(w, h), **kw)
    return f, ax


def style(ax, grid="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def save(f, name):
    OUT.mkdir(parents=True, exist_ok=True)
    f.tight_layout()
    f.savefig(OUT / f"{name}.png", dpi=200)
    plt.close(f)
    print(OUT / f"{name}.png")


def j(p):
    return json.loads((EXP / p).read_text())


I1 = j("I1-context/summary.json")
M7 = I1["per_model"]["qwen7b"]
C7 = {c["column"]: c for c in I1["columns"]["qwen7b"]}
C32 = {c["column"]: c for c in I1["columns"]["qwen32b"]}


def h01():
    pairs = M7["sensitivity_rank_across_kinds_of_change"]
    names = {"plus2_vs_plus6": "add 2 questions vs add 6", "natural_vs_plus2": "usual set vs add 2",
             "natural_vs_plus6": "usual set vs add 6", "natural_vs_paraphrase": "usual set vs reworded",
             "paraphrase_vs_plus2": "reworded vs add 2", "paraphrase_vs_plus6": "reworded vs add 6"}
    items = sorted(((names[k], v["spearman"]) for k, v in pairs.items()), key=lambda x: x[1])
    f, ax = fig()
    ax.barh([n for n, _ in items], [v for _, v in items], color=BLUE, height=0.6)
    for i, (_, v) in enumerate(items):
        ax.text(v + 0.01, i, f"{v:.2f}", va="center", fontsize=15, color=INK)
    # reference levels measured from the data (WHY/references): chance with the columns shuffled, and the agreement of
    # one kind of change with itself when every prompt is sent again
    ref = j("WHY/references/summary.json")["H1"]
    chance = max(v["chance_95"] for k, v in ref.items() if "chance_95" in v)
    rep = ref["repeat level (same change, measured twice)"].values()
    ax.axvspan(0, chance, color=GRAY, alpha=0.15, linewidth=0)
    top = len(items) - 0.62
    ax.text(0.01, top, f"chance: below {chance:.2f}", color=INK2, fontsize=13, ha="left", va="bottom")
    ax.axvspan(min(rep), max(rep), color=TEAL, alpha=0.25, linewidth=0)
    ax.text(max(rep), -0.45, f"same change measured twice: {min(rep):.2f} to {max(rep):.2f}", color=TEAL, fontsize=13, ha="right", va="top")
    ax.set_xlim(0, 1.05)
    ax.set_ylim(-0.85, len(items) - 0.1)
    ax.set_xlabel("Do both changes pick the same unstable columns?\n(1 = same order, 0 = unrelated)")
    style(ax, "x")
    save(f, "h01")


def h02():
    d = j("WHY/context/sample_curve.json")
    ns = [5, 10, 20]
    mean = [-d[f"n={n}"]["spearman_mean"] for n in ns]
    lo = [-d[f"n={n}"]["spearman_max"] for n in ns]
    hi = [-d[f"n={n}"]["spearman_min"] for n in ns]
    f, ax = fig()
    ax.fill_between(ns, lo, hi, color=BLUE, alpha=0.15, linewidth=0, label="range over 30 draws")
    ax.plot(ns, mean, marker="o", markersize=9, color=BLUE, linewidth=2.5, label="mean over 30 draws")
    ax.axhline(-d["full"]["spearman"], color=GRAY, linestyle=":", linewidth=2)
    ax.text(4.8, -d["full"]["spearman"] + 0.008, "using all documents: 0.72", color=GRAY, fontsize=14, ha="left", va="bottom")
    chance = 1.96 / (d["columns"] - 1) ** 0.5  # 95% of shuffles of 101 columns fall below this
    ax.axhspan(0, chance, color=GRAY, alpha=0.15, linewidth=0)
    ax.text(4.8, chance - 0.01, f"chance: below {chance:.2f}", color=INK2, fontsize=14, ha="left", va="top")
    for n, m in zip(ns, mean):
        ax.text(n, m + 0.012 if n < 20 else m - 0.035, f"{m:.2f}", ha="center", fontsize=15)
    ax.set_xticks(ns)
    ax.set_xlabel("Documents tested per column (no correct answers needed)")
    ax.set_ylabel("How well instability picks out\nthe less accurate columns\n(rank correlation, sign flipped)")
    ax.set_ylim(0, 0.8)
    ax.legend(loc="center right", frameon=False, bbox_to_anchor=(1, 0.45))
    style(ax)
    save(f, "h02")


def h03():
    import numpy as np
    ctxs = [("plus2", "with 2 extra\nquestions"), ("plus6", "with 6 extra\nquestions"), ("natural", "with its usual\nquestion set")]
    alone_b, ctx_b, means = [], [], []
    for k, name in ctxs:
        rows = [c for c in C7.values() if k in c["accuracy"] and "alone" in c["accuracy"]]
        alone_b.append(sum(c["accuracy"]["alone"] > c["accuracy"][k] + 0.05 for c in rows))
        ctx_b.append(sum(c["accuracy"][k] > c["accuracy"]["alone"] + 0.05 for c in rows))
        means.append((len(rows), sum(c["accuracy"]["alone"] for c in rows) / len(rows), sum(c["accuracy"][k] for c in rows) / len(rows)))
    x = np.arange(3)
    f, ax = fig()
    ax.bar(x - 0.19, alone_b, 0.36, color=BLUE, label="more accurate asked alone (by 5+ points)")
    ax.bar(x + 0.19, ctx_b, 0.36, color=ORANGE, label="more accurate asked with others (by 5+ points)")
    for i in range(3):
        ax.text(x[i] - 0.19, alone_b[i] + 0.2, str(alone_b[i]), ha="center", fontsize=16)
        ax.text(x[i] + 0.19, ctx_b[i] + 0.2, str(ctx_b[i]), ha="center", fontsize=16)
        n, a, c = means[i]
        ax.text(x[i], -3.4, f"{n} columns; average\naccuracy {a:.2f} vs {c:.2f}", ha="center", fontsize=13, color=INK2)
    ax.set_xticks(x); ax.set_xticklabels([n for _, n in ctxs])
    ax.set_ylabel("Number of columns")
    ax.set_ylim(0, 14)
    ax.legend(frameon=False, loc="upper left")
    style(ax)
    f.subplots_adjust(bottom=0.3)
    save(f, "h03")


def h04():
    xs, ys, names = [], [], []
    for k, c in C7.items():
        if k in C32 and c.get("mean_sensitivity") is not None and C32[k].get("mean_sensitivity") is not None:
            xs.append(c["mean_sensitivity"]); ys.append(C32[k]["mean_sensitivity"]); names.append(k)
    f, ax = fig()
    ax.plot([0, 1], [0, 1], color=GRAY, linestyle="--", linewidth=1.5)
    up = [(x, y) for x, y in zip(xs, ys) if y - x >= 0.05]
    rest = [(x, y) for x, y in zip(xs, ys) if y - x < 0.05]
    ax.scatter(*zip(*rest), s=90, color=BLUE, edgecolor=SURF, linewidth=1.5, label=f"large model steadier or equal ({len(rest)})")
    ax.scatter(*zip(*up), s=90, color=ORANGE, edgecolor=SURF, linewidth=1.5, label=f"large model less steady ({len(up)})")
    ax.text(0.97, 0.05, "Same columns are unstable\nfor both (agreement 0.77)", ha="right", fontsize=15, color=INK2)
    ax.set_xlabel("How often answers change, small model (7B)")
    ax.set_ylabel("How often answers change, large model (32B)")
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
    ax.legend(loc="upper left", frameon=False)
    style(ax, None)
    save(f, "h04")
    return len(xs), len(up)


def h05():
    labels = ["only earlier\nanswers\nchanged", "only later\nanswers\nchanged", "other answers\nin the document\nchanged", "nothing else\nchanged"]
    vals = [0.402, 0.365, 0.476, 0.115]
    cols = [BLUE, BLUE, ORANGE, ORANGE]
    f, ax = fig()
    bars = ax.bar(range(4), vals, color=cols, width=0.62)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.012, f"{v:.2f}", ha="center", fontsize=16)
    ax.set_xticks(range(4)); ax.set_xticklabels(labels, fontsize=14)
    ax.set_ylabel("How often this answer also changed")
    ax.set_ylim(0, 0.58)
    ax.text(0.5, 0.535, "earlier answers:\nsmall effect", ha="center", fontsize=14, color=BLUE)
    ax.text(2.5, 0.535, "same document:\nfour times higher", ha="center", fontsize=14, color=ORANGE)
    style(ax)
    save(f, "h05")


def h06():
    xs, ys, lab = [], [], []
    for k, c in C7.items():
        a = c["accuracy"]
        if "natural_first" in a and "natural_last" in a and c.get("gold_empty") is not None:
            xs.append(c["gold_empty"]); ys.append(a["natural_last"] - a["natural_first"]); lab.append(k)
    f, ax = fig()
    ax.axhline(0, color=GRAY, linewidth=1.5)
    ax.scatter(xs, ys, s=90, color=BLUE, edgecolor=SURF, linewidth=1.5)
    for x, y, k in zip(xs, ys, lab):
        short = k.split(".")[1]
        if short in ("agent_framework", "awards", "nba_championships"):
            ax.annotate(short, (x, y), xytext=(8, 4), textcoords="offset points", fontsize=14, color=INK2)
    ax.text(0.98, 0.5, "No pattern (correlation -0.22)", ha="right", fontsize=15, color=INK2, transform=ax.transAxes)
    ax.set_xlabel("Share of documents where the true answer is blank")
    ax.set_ylabel("Accuracy gain from asking it\nlast instead of first")
    style(ax)
    save(f, "h06")


def h07():
    a = M7["agreement_vs_correctness"]
    kinds = [("all", "all columns"), ("number", "numbers"), ("list", "lists"), ("free text", "free text"), ("category", "fixed choices")]
    kinds = [(k, n) for k, n in kinds if k in a]
    agree = [a[k]["accuracy_when_agree"] for k, _ in kinds]
    differ = [a[k]["accuracy_when_differ"] for k, _ in kinds]
    import numpy as np
    x = np.arange(len(kinds))
    f, ax = fig()
    ax.bar(x - 0.19, agree, 0.36, color=BLUE, label="two prompts give the same answer")
    ax.bar(x + 0.19, differ, 0.36, color=ORANGE, label="two prompts give different answers")
    for i in range(len(kinds)):
        ax.text(x[i] - 0.19, agree[i] + 0.012, f"{agree[i]:.2f}", ha="center", fontsize=13)
        ax.text(x[i] + 0.19, differ[i] + 0.012, f"{differ[i]:.2f}", ha="center", fontsize=13)
    ax.set_xticks(x); ax.set_xticklabels([n for _, n in kinds])
    ax.set_ylabel("Share of answers that are correct")
    ax.set_ylim(0, 0.8)
    ax.legend(frameon=False, loc="upper right")
    style(ax)
    save(f, "h07")


def h08():
    xs, ys, lists = [], [], []
    for c in C7.values():
        p = c.get("predicate") or {}
        if p.get("changed") is not None and c.get("mean_sensitivity") is not None and p.get("docs"):
            xs.append(c["mean_sensitivity"]); ys.append(p["changed"]); lists.append(c["kind"] == "list")
    f, ax = fig()
    lx = [(x, y) for x, y, l in zip(xs, ys, lists) if l]
    ox = [(x, y) for x, y, l in zip(xs, ys, lists) if not l]
    if ox:
        ax.scatter(*zip(*ox), s=100, color=BLUE, edgecolor=SURF, linewidth=1.5, label="other columns")
    if lx:
        ax.scatter(*zip(*lx), s=100, color=ORANGE, edgecolor=SURF, linewidth=1.5, label="list columns")
    ax.text(0.98, 0.04, "correlation 0.78\nyes/no: 3% change, lists: 72%", ha="right", fontsize=15, color=INK2, transform=ax.transAxes)
    ax.set_xlabel("How often the column's answers change with prompt wording")
    ax.set_ylabel("Share of answers changed by\nshowing the query's condition")
    ax.set_ylim(-0.03, 1.03)
    ax.legend(frameon=False, loc="upper left")
    style(ax, None)
    save(f, "h08")
    return len(xs)


def bars(name, labels, vals, colors, ylabel, fmt="{:.0f}", ylim=None, note=None, horizontal=False, w=W, h=H):
    f, ax = fig(w, h)
    if horizontal:
        ax.barh(range(len(vals)), vals, color=colors, height=0.6)
        ax.set_yticks(range(len(vals))); ax.set_yticklabels(labels)
        for i, v in enumerate(vals):
            ax.text(v + (max(vals) * 0.015), i, fmt.format(v), va="center", fontsize=15)
        ax.set_xlabel(ylabel)
        if ylim:
            ax.set_xlim(*ylim)
        style(ax, "x")
    else:
        ax.bar(range(len(vals)), vals, color=colors, width=0.6)
        ax.set_xticks(range(len(vals))); ax.set_xticklabels(labels)
        for i, v in enumerate(vals):
            ax.text(i, v + (max(vals) * 0.02 if v >= 0 else -max(vals) * 0.06), fmt.format(v), ha="center", fontsize=15)
        ax.set_ylabel(ylabel)
        if ylim:
            ax.set_ylim(*ylim)
        style(ax)
    if note:
        ax.text(0.98, 0.95, note, transform=ax.transAxes, ha="right", va="top", fontsize=14, color=INK2)
    save(f, name)


def h09():
    a = j("I2-secondlook/summary.json")["allocations"]
    bars("h09", ["least stable\ncolumns first\n(our guess)", "spread evenly\nover columns", "random\nanswers"],
         [a["by_sensitivity"]["net_per_1000_cells"], a["uniform"]["net_per_1000_cells"], a["random"]["net_per_1000_cells"]],
         [BLUE, GRAY, GRAY], "Answers fixed minus answers broken,\nper 1,000 re-reads by the large model", ylim=(0, 175))


def h10():
    import numpy as np
    f, axes = plt.subplots(1, 2, figsize=(W, H))
    groups = [("checker's\npicks", 592 / 600, 75 / 592, BLUE), ("random\npicks", 360 / 600, 114 / 360, GRAY)]
    for ax, (title, idx) in zip(axes, (("Picked answers that were wrong", 1), ("Wrong answers the large\nmodel then fixed", 2))):
        vals = [g[idx] for g in groups]
        ax.bar(range(2), vals, color=[g[3] for g in groups], width=0.6)
        for i, v in enumerate(vals):
            ax.text(i, v + 0.02, f"{v:.0%}", ha="center", fontsize=16)
        ax.set_xticks(range(2)); ax.set_xticklabels([g[0] for g in groups])
        ax.set_title(title, fontsize=16, color=INK, loc="left")
        ax.set_ylim(0, 1.12)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
        style(ax)
    save(f, "h10")


def h11():
    labels = ["removed list items\nnot in the text", "gave the full date,\nnot just the year", "found a different fact", "same answer,\nbetter wording", "filled a blank", "other"]
    vals = [38, 21, 20, 10, 7, 4]
    bars("h11", labels[::-1], vals[::-1], [GRAY, GRAY, GRAY, GRAY, BLUE, BLUE], "Share of the large model's 388 fixes (%)",
         fmt="{:.0f}%", horizontal=True, ylim=(0, 46))


def h12():
    import numpy as np
    labels = ["research papers", "basketball players"]
    per_query = [0.122, 0.108]
    first = [0.059, 0.054]
    det = [0.113, 0.1545]
    x = np.arange(2)
    f, ax = fig()
    ax.bar(x - 0.27, per_query, 0.25, color=GRAY, label="DocETL as published: new prompt for every query")
    ax.bar(x, first, 0.25, color=ORANGE, label="one fixed prompt per column: the first one used")
    ax.bar(x + 0.27, det, 0.25, color=BLUE, label="one fixed prompt per column: one that answers most documents")
    ax.errorbar([1 + 0.27], [0.1545], yerr=[[0.0095], [0.0095]], color=INK, capsize=6, linewidth=1.5)
    for xs, vs in ((x - 0.27, per_query), (x, first), (x + 0.27, det)):
        for xi, v in zip(xs, vs):
            top = v + (0.0095 if abs(xi - 1.27) < 1e-6 else 0)
            label = "0.145–0.164" if abs(xi - 1.27) < 1e-6 else f"{v:.3f}"
            ax.text(xi, top + 0.005, label, ha="center", fontsize=13)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("Average query score")
    ax.set_ylim(0, 0.24)
    ax.legend(frameon=False, loc="upper left", fontsize=13)
    style(ax)
    save(f, "h12")


def h13():
    s = j("WHY/i4/summary.json")["streams"]
    rows = []
    for k, v in s.items():
        if "frozen_fcfs" in v and "frozen_forecast" in v:
            c, b = k.split("/")
            rows.append((f"{ {'cspaper': 'papers', 'player': 'players', 'art': 'artists', 'med': 'medical', 'legal': 'court'}[c]} {b[1:]}%",
                         v["frozen_forecast"]["score"] - v["frozen_fcfs"]["score"]))
    rows.sort(key=lambda r: r[1])
    f, ax = fig()
    ax.axvline(0, color=GRAY, linewidth=1.5)
    for i, (n, d) in enumerate(rows):
        ax.plot([0, d], [i, i], color=ORANGE if d < -0.002 else GRAY, linewidth=2.5)
        ax.plot(d, i, "o", markersize=11, color=ORANGE if d < -0.002 else GRAY, markeredgecolor=SURF, markeredgewidth=1.5)
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlabel("Score with forecasting minus score when reading\na column the first time a query asks for it")
    ax.text(0.03, 0.97, "never better; worse in 6 of 10 runs", transform=ax.transAxes, fontsize=15, color=INK2, va="top")
    style(ax, "x")
    save(f, "h13")


def h14():
    f, axes = plt.subplots(1, 2, figsize=(W, H), gridspec_kw={"width_ratios": [1, 2.2]})
    ax = axes[0]
    ax.bar([0], [0.138], color=BLUE, width=0.5)
    ax.text(0, 0.143, "+0.138", ha="center", fontsize=16)
    ax.set_xticks([0]); ax.set_xticklabels(["the 5\nchosen\ncolumns"])
    ax.set_ylim(-0.02, 0.17); ax.set_title("Answer accuracy", loc="left", fontsize=16)
    style(ax)
    ax = axes[1]
    d = {"papers": -0.0004, "players": -0.0011, "artists": -0.0095, "medical": -0.0039, "court": -0.0046}
    ax.axhline(0, color=GRAY, linewidth=1.5)
    ax.bar(range(5), list(d.values()), color=ORANGE, width=0.6)
    for i, v in enumerate(d.values()):
        ax.text(i, v - 0.0012, f"{v:+.3f}", ha="center", va="top", fontsize=13)
    ax.set_xticks(range(5)); ax.set_xticklabels(list(d.keys()), fontsize=14)
    ax.set_ylim(-0.017, 0.006); ax.set_title("Query score change by collection", loc="left", fontsize=16)
    style(ax)
    save(f, "h14")


def h15():
    cats = [("exact label", BLUE), ("right century, other wording", TEAL), ("merged into a wider range", ORANGE)]
    before = [27, 50, 23]
    after = [52, 6, 43]
    f, ax = fig(W, 5.0)
    for row, vals in ((1, before), (0, after)):
        left = 0
        for (name, col), v in zip(cats, vals):
            ax.barh(row, v, left=left, color=col, height=0.55, edgecolor=SURF, linewidth=2, label=name if row == 1 else None)
            if v >= 10:
                ax.text(left + v / 2, row, f"{v}%", ha="center", va="center", color="#FFFFFF", fontsize=16, fontweight="bold")
            else:
                ax.text(left + v / 2, row + 0.36, f"{v}%", ha="center", va="bottom", color=INK, fontsize=15)
            left += v
    ax.set_yticks([1, 0]); ax.set_yticklabels(["no list of\nallowed labels", "list of allowed\nlabels given"])
    ax.set_xlim(0, 101); ax.set_xlabel("Artists' century: what happened to 709 answers (%)")
    style(ax, None)
    h, l = ax.get_legend_handles_labels()
    f.legend(h, l, frameon=False, loc="lower center", ncol=2, fontsize=13)
    f.tight_layout(rect=(0, 0.14, 1, 1))
    OUT.mkdir(parents=True, exist_ok=True)
    f.savefig(OUT / "h15.png", dpi=200); plt.close(f); print(OUT / "h15.png")


def h16():
    rows = [("birth date", 0.38, 0.79), ("death date", 0.31, 0.56), ("birth city (list)", 0.39, 0.28),
            ("field (list)", 0.13, 0.03), ("FIBA cups (0 if none)", 0.86, 0.25), ("NBA titles (0 if none)", 0.95, 0.40)]
    f, ax = fig()
    for i, (n, a, b) in enumerate(rows[::-1]):
        col = BLUE if b > a else ORANGE
        ax.plot([a, b], [i, i], color=col, linewidth=3)
        ax.plot(a, i, "o", color=GRAY, markersize=10, markeredgecolor=SURF, markeredgewidth=1.5)
        ax.plot(b, i, "o", color=col, markersize=12, markeredgecolor=SURF, markeredgewidth=1.5)
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows[::-1]], fontsize=14)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Accuracy: reading the whole document (gray) vs\nonly the part where answers usually sit (color)")
    style(ax, "x")
    save(f, "h16")


def asym():
    rows = [("papers: answers that became right", 0.009), ("papers: answers that became wrong", -0.032), ("players: became right (grouping)", 0.004),
            ("players: became wrong (grouping)", -0.011), ("players: became wrong (filters)", -0.019),
            ("players: became wrong (joins)", -0.024), ("players: wording only (499 answers)", 0.001)]
    f, ax = fig()
    ax.axvline(0, color=GRAY, linewidth=1.5)
    for i, (n, v) in enumerate(rows[::-1]):
        col = BLUE if v > 0.002 else (ORANGE if v < 0 else GRAY)
        ax.barh(i, v, color=col, height=0.6)
        ax.text(v + (0.001 if v >= 0 else -0.001), i, f"{v:+.3f}", va="center", ha="left" if v >= 0 else "right", fontsize=14)
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows[::-1]], fontsize=14)
    ax.set_xlim(-0.042, 0.018)
    ax.set_xlabel("Effect on the average query score")
    style(ax, "x")
    save(f, "asymmetry")


CORP = [("cspaper", "papers"), ("player", "players"), ("art", "artists"), ("med", "medical"), ("legal", "court cases")]
REC = {"cspaper": 0.153, "player": 0.387, "art": 0.256, "med": 0.115, "legal": 0.170}
RUNS = {"cspaper": [0.138, 0.136, 0.144], "player": [0.377, 0.374, 0.369], "art": [0.255, 0.250, 0.260],
        "med": [0.107, 0.098, 0.095], "legal": [0.178, 0.168]}


def h17():
    row = {"cspaper": 0.150, "player": 0.373, "art": 0.257, "med": 0.092}
    f, axes = plt.subplots(1, 4, figsize=(W, H))
    for ax, (c, n) in zip(axes, CORP[:4]):
        r = RUNS[c]
        ax.plot([0] * len(r), r, "o", color=BLUE, markersize=11, markeredgecolor=SURF, markeredgewidth=1.5, label="our system, repeat runs")
        ax.plot([1], [row[c]], "D", color=ORANGE, markersize=12, markeredgecolor=SURF, markeredgewidth=1.5, label="re-reads aimed at filtered rows")
        lo, hi = min(r + [row[c]]), max(r + [row[c]])
        pad = max(0.01, (hi - lo) * 0.6)
        ax.set_ylim(lo - pad, hi + pad)
        ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(5))
        ax.set_xlim(-0.6, 1.6); ax.set_xticks([])
        ax.set_title(n, fontsize=16, loc="left")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.3f}"))
        style(ax)
    axes[0].set_ylabel("Average query score")
    h, l = axes[0].get_legend_handles_labels()
    f.legend(h, l, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.01))
    f.tight_layout(rect=(0, 0.08, 1, 1))
    OUT.mkdir(parents=True, exist_ok=True)
    f.savefig(OUT / "h17.png", dpi=200); plt.close(f); print(OUT / "h17.png")


def h18():
    import numpy as np
    d = {"artists": (0.2625, 0.2576, 0.2618), "medical": (0.1205, 0.0868, 0.1231)}
    x = np.arange(2)
    f, ax = fig()
    for k, (lab, col) in enumerate((("no list cleanup", GRAY), ("cleanup that can blank a cell", ORANGE), ("cleanup that never blanks a cell", BLUE))):
        vals = [d[c][k] for c in d]
        ax.bar(x + (k - 1) * 0.27, vals, 0.25, color=col, label=lab)
        for xi, v in zip(x + (k - 1) * 0.27, vals):
            ax.text(xi, v + 0.004, f"{v:.3f}", ha="center", fontsize=13)
    ax.set_xticks(x); ax.set_xticklabels(list(d.keys()))
    ax.set_ylabel("Average query score (same table)")
    ax.set_ylim(0, 0.34)
    ax.legend(frameon=False, loc="upper right", fontsize=13)
    ax.text(0.02, 0.97, "papers, players, court cases: no change", transform=ax.transAxes, fontsize=14, color=INK2, va="top")
    style(ax)
    save(f, "h18")


# DocETL, the external baseline, scored on exactly our test queries (court cases: the 21 of 27 it answered; our
# system is scored on the same 21 there). Tokens: DocETL's on those queries; ours = the initial build + on-demand
# reads by both models (raw tokens, the 32B's counted like the 7B's).
DOCETL_TEST = {"cspaper": 0.105, "player": 0.081, "art": 0.167, "med": 0.072, "legal": 0.057}
OURS_TEST = {"cspaper": [0.138, 0.136, 0.144], "player": [0.377, 0.374, 0.369], "art": [0.255, 0.250, 0.260],
             "med": [0.107, 0.098, 0.095], "legal": [0.155, 0.142]}
NOREREAD_TEST = {"cspaper": [0.129], "player": [0.366], "art": [0.257], "med": [0.078, 0.092], "legal": [0.140]}
DOCETL_TOK = {"cspaper": 20.7, "player": 190.6, "art": 57.9, "med": 88.8, "legal": 333.0}
BUILD_TOK = {"cspaper": 0.40, "player": 2.04, "art": 2.43, "med": 2.55, "legal": 4.56}
ONDEMAND_TOK = {"cspaper": 0.52 + 0.20, "player": 5.02 + 1.25, "art": 2.33 + 0.21, "med": 7.11 + 2.91, "legal": 5.33 + 0.52}


def baseline_scores():
    import numpy as np
    x = np.arange(5)
    f, ax = fig(W + 1.4, H)
    d = [DOCETL_TEST[c] for c, _ in CORP]
    o = [S_mean(OURS_TEST[c]) for c, _ in CORP]
    n = [S_mean(NOREREAD_TEST[c]) for c, _ in CORP]
    ax.bar(x - 0.27, d, 0.25, color=GRAY, label="DocETL (baseline)")
    ax.bar(x, o, 0.25, color=BLUE, label="our system")
    ax.bar(x + 0.27, n, 0.25, color=TEAL, label="our system without re-reads (no correct answers used)")
    for c_i, (c, _) in enumerate(CORP):
        for v in OURS_TEST[c]:
            ax.plot(c_i, v, "o", color=INK, markersize=5)
    for xs, vs in ((x - 0.27, d), (x, o), (x + 0.27, n)):
        for xi, v in zip(xs, vs):
            ax.text(xi, v + 0.008, f"{v:.2f}", ha="center", fontsize=12)
    ax.set_xticks(x); ax.set_xticklabels([nm for _, nm in CORP])
    ax.set_ylabel("Average query score, test queries")
    ax.set_ylim(0, 0.42)
    style(ax)
    h, l = ax.get_legend_handles_labels()
    f.legend(h, l, frameon=False, loc="lower center", ncol=3, fontsize=13)
    f.tight_layout(rect=(0, 0.08, 1, 1))
    OUT.mkdir(parents=True, exist_ok=True)
    f.savefig(OUT / "baseline_scores.png", dpi=200); plt.close(f); print(OUT / "baseline_scores.png")


def baseline_tokens():
    import numpy as np
    f, ax = fig(W, H)
    y = np.arange(5)[::-1]
    ours = [BUILD_TOK[c] + ONDEMAND_TOK[c] for c, _ in CORP]
    doc = [DOCETL_TOK[c] for c, _ in CORP]
    ax.barh(y + 0.2, doc, 0.38, color=GRAY, label="DocETL")
    ax.barh(y - 0.2, ours, 0.38, color=BLUE, label="our system (initial build included)")
    for yi, a, b in zip(y, ours, doc):
        ax.text(b * 1.15, yi + 0.2, f"{b:.0f}M", va="center", fontsize=13)
        ax.text(a * 1.15, yi - 0.2, f"{a:.1f}M  ({b / a:.0f} times fewer)", va="center", fontsize=13)
    ax.set_xscale("log")
    ax.set_xlim(0.5, 3000)
    ax.set_yticks(y); ax.set_yticklabels([nm for _, nm in CORP])
    ax.set_xlabel("Tokens read by the models, millions (log scale)")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    style(ax, "x")
    h, l = ax.get_legend_handles_labels()
    f.legend(h, l, frameon=False, loc="lower center", ncol=2, fontsize=13)
    f.tight_layout(rect=(0, 0.07, 1, 1))
    OUT.mkdir(parents=True, exist_ok=True)
    f.savefig(OUT / "baseline_tokens.png", dpi=200); plt.close(f); print(OUT / "baseline_tokens.png")


def noplanner():
    f, axes = plt.subplots(1, 5, figsize=(W, H))
    for ax, (c, n) in zip(axes, CORP):
        ax.axhline(REC[c], color=GRAY, linestyle="--", linewidth=2, label="without the planner (one prompt per query)")
        ax.plot([0] * len(RUNS[c]), RUNS[c], "o", color=BLUE, markersize=11, markeredgecolor=SURF, markeredgewidth=1.5, label="our system (repeat runs)")
        vals = RUNS[c] + [REC[c]]
        ax.set_ylim(min(vals) - 0.02, max(vals) + 0.02)
        ax.set_xlim(-0.7, 0.7); ax.set_xticks([])
        ax.set_title(n, fontsize=14, loc="center")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.2f}"))
        ax.tick_params(axis="y", labelsize=13)
        style(ax)
    axes[0].set_ylabel("Average query score")
    hs = {}
    for ax in axes:
        for h, l in zip(*ax.get_legend_handles_labels()):
            hs.setdefault(l, h)
    f.legend(list(hs.values()), list(hs.keys()), loc="lower center", ncol=1, frameon=False, fontsize=13, bbox_to_anchor=(0.5, -0.01))
    f.tight_layout(rect=(0, 0.14, 1, 1))
    OUT.mkdir(parents=True, exist_ok=True)
    f.savefig(OUT / "noplanner.png", dpi=200); plt.close(f); print(OUT / "noplanner.png")


def tokens():
    plan = {"cspaper": 0.52, "player": 5.02, "art": 2.33, "med": 7.11, "legal": 5.33}
    rec = {"cspaper": 1.16, "player": 5.67, "art": 6.08, "med": 14.08, "legal": 19.77}
    rows = [(n, plan[c] / rec[c]) for c, n in CORP]
    bars("tokens", [r[0] for r in rows][::-1], [r[1] * 100 for r in rows][::-1], BLUE,
         "Small-model tokens while queries arrive, as a share of\nthe version without the planner (%)", fmt="{:.0f}%", horizontal=True, ylim=(0, 105), w=W, h=H)


def budget():
    import numpy as np
    b25 = {"cspaper": (0.150, 0.137), "player": (0.344, 0.176), "art": (0.202, 0.179), "med": (0.075, 0.079), "legal": (0.160, 0.098)}
    b50 = {"cspaper": (0.138, 0.147), "player": (0.366, 0.293), "art": (0.254, 0.191), "med": (0.085, 0.104), "legal": (0.160, 0.146)}
    f, axes = plt.subplots(1, 2, figsize=(W + 2.2, H), sharey=True)
    x = np.arange(5)
    for ax, (title, d) in zip(axes, (("budget 25%", b25), ("budget 50%", b50))):
        p = [d[c][0] for c, _ in CORP]; r = [d[c][1] for c, _ in CORP]
        ax.bar(x - 0.2, p, 0.38, color=BLUE, label="our system")
        ax.bar(x + 0.2, r, 0.38, color=GRAY, label="without the planner")
        ax.set_xticks(x); ax.set_xticklabels([n for _, n in CORP], fontsize=14)
        ax.set_title(title, loc="left", fontsize=16)
        for xi, v in zip(x - 0.2, p):
            ax.text(xi, v + 0.006, f"{v:.2f}", ha="center", fontsize=12)
        for xi, v in zip(x + 0.2, r):
            ax.text(xi, v + 0.006, f"{v:.2f}", ha="center", fontsize=12, color=INK2)
        style(ax)
    axes[0].set_ylabel("Average query score")
    h, l = axes[0].get_legend_handles_labels()
    f.legend(h, l, frameon=False, loc="lower center", ncol=2)
    f.tight_layout(rect=(0, 0.08, 1, 1))
    OUT.mkdir(parents=True, exist_ok=True)
    f.savefig(OUT / "budget.png", dpi=200); plt.close(f); print(OUT / "budget.png")


def S_mean(v):
    return sum(v) / len(v)


def ablations():
    import numpy as np
    f, axes = plt.subplots(1, 2, figsize=(W + 2.2, H), gridspec_kw={"width_ratios": [1, 1.4]})
    ratio = {"cspaper": 1.49 / 0.52, "player": 7.57 / 5.02, "art": 6.90 / 2.33, "med": 17.20 / 7.11, "legal": 20.45 / 5.33}
    ax = axes[0]
    ax.barh(range(5), [ratio[c] for c, _ in CORP][::-1], color=BLUE, height=0.6)
    ax.set_yticks(range(5)); ax.set_yticklabels([n for _, n in CORP][::-1])
    for i, v in enumerate([ratio[c] for c, _ in CORP][::-1]):
        ax.text(v + 0.05, i, f"{v:.1f}×", va="center", fontsize=14)
    ax.set_xlim(0, 4.4)
    ax.set_title("Reading all columns at once: token saving", loc="left", fontsize=15)
    style(ax, "x")
    ax = axes[1]
    looks = {"cspaper": 0.138 - 0.129, "player": 0.377 - 0.366, "art": 0.255 - 0.257,
             "med": (0.107 + 0.098 + 0.095) / 3 - (0.078 + 0.092) / 2, "legal": 0.178 - 0.167}
    filt = {"cspaper": 0.0, "player": 0.0, "art": 0.2576 - 0.2625, "med": 0.0868 - 0.1205, "legal": 0.0}
    x = np.arange(5)
    ax.axhline(0, color=GRAY, linewidth=1.5)
    ax.bar(x - 0.2, [looks[c] for c, _ in CORP], 0.38, color=BLUE, label="re-reads by the large model")
    ax.bar(x + 0.2, [filt[c] for c, _ in CORP], 0.38, color=ORANGE, label="list cleanup, old version")
    ax.set_xticks(x); ax.set_xticklabels([n for _, n in CORP], fontsize=14)
    ax.set_title("Score added by each part", loc="left", fontsize=15)
    style(ax)
    h, l = ax.get_legend_handles_labels()
    f.legend(h, l, frameon=False, loc="lower center", ncol=2, fontsize=14)
    f.tight_layout(rect=(0, 0.08, 1, 1))
    OUT.mkdir(parents=True, exist_ok=True)
    f.savefig(OUT / "ablations.png", dpi=200); plt.close(f); print(OUT / "ablations.png")


def resend():
    """Same prompt sent twice against a different prompt (WHY/repeat): share of answers that change."""
    d = j("WHY/repeat/summary.json")["t01"]["all"]
    kinds = [("plus2", "add 2\nquestions"), ("plus6", "add 6\nquestions"), ("paraphrase", "reworded"),
             ("with_predicate", "query's condition\nshown")]
    series = [("same prompt sent twice", BLUE, lambda k: d["same prompt twice"][k]["changed"]),
              ("alone vs this prompt", ORANGE, lambda k: d["alone vs this prompt"][k]["changed"]),
              ("change caused by the prompt\n(holds when both are resent)", TEAL, lambda k: d["stable effect"][k]["changed"])]
    f, ax = fig()
    w = 0.26
    for i, (lab, col, get) in enumerate(series):
        xs = [x + (i - 1) * w for x in range(len(kinds))]
        vs = [get(k) for k, _ in kinds]
        ax.bar(xs, vs, width=w - 0.03, color=col, label=lab)
        for x, v in zip(xs, vs):
            ax.text(x, v + 0.01, f"{v * 100:.0f}%", ha="center", fontsize=13, color=INK)
    ax.set_xticks(range(len(kinds)))
    ax.set_xticklabels([n for _, n in kinds])
    ax.set_ylim(0, 0.62)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * 100:.0f}%"))
    ax.set_ylabel("Share of answers that change")
    ax.legend(frameon=False, loc="upper left", fontsize=13)
    style(ax)
    save(f, "resend")


def blank_wrong():
    """Controlled damage (WHY/blank_wrong): the same 20% of correct answers blanked or replaced by a wrong value."""
    names = [("cspaper", "papers"), ("player", "players"), ("art", "artists"), ("med", "medical"), ("legal", "court\ncases")]
    ms = {c: j(f"WHY/blank_wrong/{c}.json")["mean_score"] for c, _ in names}
    series = [("all answers correct", GRAY, "clean"), ("20% replaced by a wrong value", BLUE, "wrong"),
              ("the same 20% left blank", ORANGE, "blank")]
    f, ax = fig()
    w = 0.26
    for i, (lab, col, key) in enumerate(series):
        xs = [x + (i - 1) * w for x in range(len(names))]
        vs = [ms[c][key] for c, _ in names]
        ax.bar(xs, vs, width=w - 0.03, color=col, label=lab)
        for x, v in zip(xs, vs):
            ax.text(x, v + 0.01, f"{v:.2f}", ha="center", fontsize=12, color=INK)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([n for _, n in names])
    ax.set_ylim(0, 0.78)
    ax.set_ylabel("Average query score")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), fontsize=13, ncol=3, handlelength=1.2, columnspacing=1.0)
    style(ax)
    save(f, "blank_wrong")



def groupsize():
    """Exactness by group size (WHY/groupsize) and the p^n check (WHY/pn)."""
    import statistics as St
    rows = j("WHY/groupsize/summary.json")["queries"]
    bins = [(1, 2, "1-2"), (3, 9, "3-9"), (10, 49, "10-49"), (50, 10**9, "50+")]
    fams = [("COUNT, SUM or AVG", BLUE, ("COUNT(*)", "COUNT(column)", "SUM", "AVG")), ("MIN or MAX", ORANGE, ("MIN/MAX",))]
    f, (a1, a2) = plt.subplots(1, 2, figsize=(W, H), gridspec_kw={"width_ratios": [1.25, 1]})
    for lab, col, cls in fams:
        xs, ys, ns = [], [], []
        for i, (lo, hi, _) in enumerate(bins):
            b = [r["values_0"] for r in rows if r["class"] in cls and lo <= r["median_group"] <= hi]
            if b:
                xs.append(i); ys.append(St.mean(b)); ns.append(len(b))
        a1.plot(xs, ys, marker="o", markersize=8, linewidth=2.5, color=col, label=lab)
        for x, y, n in zip(xs, ys, ns):
            dy = 0.03 if col == ORANGE else -0.07
            a1.text(x + (0.12 if x == 0 else 0), y + dy, f"{y:.2f} ({n})", ha="left" if x == 0 else "center", fontsize=11, color=INK)
    a1.set_xticks(range(len(bins))); a1.set_xticklabels([b[2] for b in bins])
    a1.set_xlabel("Rows behind each result value")
    a1.set_ylabel("Share of result values exactly right")
    a1.set_ylim(-0.08, 0.92)
    a1.set_xlim(-0.3, 3.4)
    a1.legend(frameon=False, loc="upper right", fontsize=12)
    style(a1)
    pn = j("WHY/pn/summary.json")["bins"]["COUNT, SUM, AVG"]
    labs = [k for k in ("below 0.05", "0.05-0.2", "0.2-0.5", "0.5-1") if k in pn]
    x = range(len(labs))
    a2.bar([i - 0.2 for i in x], [pn[k]["predicted"] for k in labs], 0.38, color=GRAY, label="predicted: p to the power n")
    a2.bar([i + 0.2 for i in x], [pn[k]["observed"] for k in labs], 0.38, color=BLUE, label="observed")
    a2.set_xticks(list(x)); a2.set_xticklabels(["<.05", ".05-.2", ".2-.5", ".5-1"])
    a2.set_xlabel("Predicted share exactly right")
    a2.set_ylim(0, 0.85)
    a2.legend(frameon=False, loc="upper left", fontsize=11)
    a2.set_title("COUNT, SUM, AVG", fontsize=14, color=INK2)
    style(a2)
    save(f, "groupsize")


def roles_chart():
    """Within-collection rank correlation of a query's score with the accuracy of its weakest column per role."""
    d = j("WHY/profile/summary.json")["by_role_accuracy"]
    names = [("player", "players"), ("art", "artists"), ("legal", "court\ncases"), ("med", "medical"), ("cspaper", "papers")]
    series = [("grouped by", "grouping column", BLUE), ("aggregated", "aggregated column", ORANGE)]
    f, ax = fig()
    w = 0.36
    for i, (role, lab, col) in enumerate(series):
        xs = [x + (i - 0.5) * w for x in range(len(names))]
        vs = [d[role].get(c, {}).get("rank_correlation", 0.0) for c, _ in names]
        ax.bar(xs, vs, width=w - 0.03, color=col, label=lab)
        for x, v in zip(xs, vs):
            ax.text(x, v + (0.02 if v >= 0 else -0.06), f"{v:.2f}", ha="center", fontsize=12, color=INK)
    ax.axhline(0, color=GRAY, linewidth=1)
    ax.set_xticks(range(len(names))); ax.set_xticklabels([n for _, n in names])
    ax.set_ylim(-0.6, 0.85)
    ax.set_ylabel("Link between a column's accuracy\nand the query's score (rank correlation)")
    ax.legend(frameon=False, loc="upper right", fontsize=13)
    style(ax)
    save(f, "roles")

if __name__ == "__main__":
    h01(); h02(); h03(); print("h04", h04()); h05(); h06(); h07(); print("h08 columns", h08())
    h09(); h10(); h11(); h12(); h13(); h14(); h15(); h16(); asym(); h17(); h18()
    baseline_scores(); baseline_tokens(); noplanner(); tokens(); budget(); ablations(); resend(); blank_wrong(); groupsize(); roles_chart()
