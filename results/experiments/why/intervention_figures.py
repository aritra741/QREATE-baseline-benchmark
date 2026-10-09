"""Figures for the interventions I1-I3 (results/experiments/why/figures/w9-w11).

    ~/venvs/quwarts/bin/python results/experiments/why/intervention_figures.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
OUT = HERE / "figures"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "savefig.facecolor": SURFACE})
pct = matplotlib.ticker.PercentFormatter(1.0)


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=180)
    plt.close(fig)
    print(OUT / name)


def context_intervention():
    d = json.loads((EXP / "I1-context" / "summary.json").read_text())
    m = d["per_model"]["qwen7b"]
    cols = d["columns"]["qwen7b"]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(10.5, 4.0), gridspec_kw={"width_ratios": [1.1, 1]})
    kinds = [("alone", "Alone"), ("plus2", "+2 random"), ("plus6", "+6 random"), ("natural", "Natural group"),
             ("paraphrase", "Paraphrased\ndescription")]
    acc = [m["mean_accuracy_by_context"][k] for k, _ in kinds]
    emp = [m["mean_empty_by_context"][k] for k, _ in kinds]
    w = 0.38
    b1 = ax.bar([i - w / 2 for i in range(5)], acc, width=w - 0.03, color=BLUE, label="Accuracy")
    b2 = ax.bar([i + w / 2 for i in range(5)], emp, width=w - 0.03, color=MUTED, label="Left empty")
    for b, v in list(zip(b1, acc)) + list(zip(b2, emp)):
        ax.annotate(f"{v:.0%}", (b.get_x() + b.get_width() / 2, v), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8.5)
    ax.set_xticks(range(5), [n for _, n in kinds], fontsize=9)
    ax.set_ylim(0, 0.6)
    ax.yaxis.set_major_formatter(pct)
    ax.set_title("(a) Mean over 39 columns: the context does not move the average", fontsize=10, loc="left", color=INK)
    ax.legend(loc="upper right", fontsize=8.5, frameon=False)
    style(ax)
    xs = [r["accuracy"].get("alone") for r in cols if "alone" in r["accuracy"] and "natural" in r["accuracy"]]
    ys = [r["accuracy"].get("natural") for r in cols if "alone" in r["accuracy"] and "natural" in r["accuracy"]]
    ks = [r["kind"] for r in cols if "alone" in r["accuracy"] and "natural" in r["accuracy"]]
    colors = {"number": BLUE, "yes/no": AQUA, "category": YELLOW, "list": ORANGE, "free text": MAGENTA}
    for k, c in colors.items():
        pts = [(x, y) for x, y, kk in zip(xs, ys, ks) if kk == k]
        if pts:
            bx.scatter([p[0] for p in pts], [p[1] for p in pts], s=44, color=c, edgecolor=SURFACE, linewidth=1.2, label=f"{k} ({len(pts)})", zorder=3)
    bx.plot([0, 1], [0, 1], color=AXIS, linestyle="--", linewidth=1)
    bx.set_xlim(-0.02, 1.02)
    bx.set_ylim(-0.02, 1.02)
    bx.xaxis.set_major_formatter(pct)
    bx.yaxis.set_major_formatter(pct)
    bx.set_xlabel("Accuracy when asked alone")
    bx.set_ylabel("Accuracy in the natural group")
    bx.set_title("(b) Per column: the direction is the column's own", fontsize=10, loc="left", color=INK)
    bx.legend(loc="lower right", fontsize=8, frameon=False)
    style(bx)
    save(fig, "w9_context_intervention.png")


def second_looks():
    d = json.loads((EXP / "I2-secondlook" / "summary.json").read_text())
    bins = list(d["by_sensitivity_bin"].items())
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(10.5, 3.9), gridspec_kw={"width_ratios": [1.2, 1]})
    w = 0.38
    s1 = [v["served_accuracy"] for _, v in bins]
    s2 = [v["second_accuracy"] for _, v in bins]
    b1 = ax.bar([i - w / 2 for i in range(len(bins))], s1, width=w - 0.03, color=BLUE, label="7B value as served")
    b2 = ax.bar([i + w / 2 for i in range(len(bins))], s2, width=w - 0.03, color=ORANGE, label="32B second look")
    for b, v in list(zip(b1, s1)) + list(zip(b2, s2)):
        ax.annotate(f"{v:.0%}", (b.get_x() + b.get_width() / 2, v), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8.5)
    ax.set_xticks(range(len(bins)), [f"{k}\n({v['cells']} cells)" for k, v in bins], fontsize=9)
    ax.set_xlabel("Context sensitivity of the column")
    ax.set_ylim(0, 1.0)
    ax.yaxis.set_major_formatter(pct)
    ax.set_title("(a) Accuracy before and after a second look", fontsize=10, loc="left", color=INK)
    ax.legend(loc="upper right", fontsize=8.5, frameon=False)
    style(ax)
    names = [("random", "Random"), ("uniform", "Uniform across\ncolumns"), ("by_sensitivity", "Most sensitive\nfirst"),
             ("lowest_sensitivity_first_hindsight", "Least sensitive\nfirst (hindsight)")]
    vals = [d["allocations"][k]["net_per_1000_cells"] for k, _ in names]
    bars = bx.bar(range(len(names)), vals, color=[MUTED, BLUE, ORANGE, AQUA], width=0.6)
    for b, v in zip(bars, vals):
        bx.annotate(f"{v:.0f}", (b.get_x() + b.get_width() / 2, v), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=9)
    bx.set_xticks(range(len(names)), [n for _, n in names], fontsize=8.5)
    bx.set_ylabel("Net errors fixed per 1,000 second looks")
    bx.set_title("(b) Where to spend 600 second looks", fontsize=10, loc="left", color=INK)
    style(bx)
    save(fig, "w10_second_looks.png")


def frozen_docetl():
    d = json.loads((EXP / "WHY" / "i3" / "summary.json").read_text())
    variants = [("original", None, "Per-query (original)"), ("frozen", "frozen", "Frozen on the first context"),
                ("frozen2", "frozen2", "Frozen on the better of two"), ("frozen2_rep", "frozen2_rep", "Same, second run"),
                ("frozen4", "frozen4", "Frozen on a determined context")]
    corpora = [("cspaper", "Research papers"), ("player", "Basketball players")]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.9))
    colors = [MUTED, ORANGE, BLUE, BLUE, AQUA]
    for ax, (c, label) in zip(axes, corpora):
        vals, calls, names, cols = [], [], [], []
        for i, (key, var, name) in enumerate(variants):
            if var is None:
                src = d.get("frozen", {}).get("corpora", {}).get(c)
                if not src:
                    continue
                vals.append(src["original"])
                calls.append(src["calls_original"])
            else:
                src = d.get(var, {}).get("corpora", {}).get(c)
                if not src or not src.get("complete"):
                    continue
                vals.append(src["frozen"])
                calls.append(src["calls_frozen"])
            names.append(name)
            cols.append(colors[i])
        bars = ax.bar(range(len(vals)), vals, color=cols, width=0.6)
        for b, v, k in zip(bars, vals, calls):
            ax.annotate(f"{v:.3f}\n{k / 1000:.1f}k calls", (b.get_x() + b.get_width() / 2, v), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8.5)
        ax.set_xticks(range(len(names)), [n.replace(" on ", "\non ").replace("(original)", "\n(original)").replace("Same, ", "Same,\n") for n in names], fontsize=8)
        ax.set_ylim(0, max(vals) * 1.35)
        ax.set_ylabel("Mean query score")
        ax.set_title(f"{label}", fontsize=10, loc="left", color=INK)
        style(ax)
    save(fig, "w11_frozen_docetl.png")


def budget_curves():
    d = json.loads((EXP / "WHY" / "i4" / "summary.json").read_text())["score_vs_tokens"]
    names = {"cspaper": "Research papers", "player": "Basketball players", "art": "Artists", "med": "Medical", "legal": "Court judgments"}
    fig, axes = plt.subplots(1, 5, figsize=(14, 3.4))
    for ax, c in zip(axes, ["cspaper", "player", "art", "med", "legal"]):
        cur = d.get(c, {})
        rec = sorted(cur.get("recorded", []), key=lambda p: p["tokens"])
        if rec:
            ax.plot([p["tokens"] / 1e6 for p in rec], [p["score"] for p in rec], marker="o", color=MUTED, label="Recorded: one prompt per query's missing columns")
        fr = sorted(cur.get("frozen_fcfs", []) + cur.get("frozen_unlimited", []), key=lambda p: p["tokens"])
        if fr:
            ax.plot([p["tokens"] / 1e6 for p in fr], [p["score"] for p in fr], marker="o", color=BLUE, label="Frozen context: a table's new columns in one prompt")
        fo = sorted(cur.get("frozen_forecast", []), key=lambda p: p["tokens"])
        if fo:
            ax.plot([p["tokens"] / 1e6 for p in fo], [p["score"] for p in fo], marker="s", linestyle="none", color=ORANGE, label="Frozen context, forecast policy")
        ax.set_xscale("log")
        ax.set_title(names[c], fontsize=10, loc="left", color=INK)
        ax.set_xlabel("Tokens spent on extraction (millions, log)")
        if c == "cspaper":
            ax.set_ylabel("Mean query score")
        style(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=8.5, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(OUT / "w12_budget_curves.png", dpi=180)
    plt.close(fig)
    print(OUT / "w12_budget_curves.png")


for fn in (context_intervention, second_looks, frozen_docetl, budget_curves):
    fn()
