"""Score under workload drift at patch budgets (fixed4 levels, attribute_pool), one panel per corpus. Budget = % of
the patch tokens the unlimited stream spends at 100% drift on that corpus; 0% is the static build, and the
unlimited stream is the adaptive run itself. Corpora whose budgeted streams are not all finished are skipped.

    ~/venvs/quwarts/bin/python systems/WDIRS/quwarts/scripts/plot_drift_budget.py [corpora] [out.png]
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[4]
LIVE = ROOT / "results" / "drift_live_ollama"
CORPORA = (sys.argv[1] if len(sys.argv) > 1 else "player,cspaper,art,med,legal").split(",")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else LIVE / "drift_budget.png"
LEVELS = (0, 25, 50, 75, 100)
BUDGETS = (10, 25, 50, 75, 100)
RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]  # validated ordinal blue ramp
SURFACE, INK, INK2, GRID, STATIC, FULL = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#eb6834", "#0b0b0b"


def mean(path: Path, key: str = "benchmark") -> float:
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    return sum(r[key] for r in rows) / len(rows)


def curve(corpus: str, budget: int | None, key: str = "benchmark") -> list[float] | None:
    s = LIVE / corpus / "streams"
    paths = [s / (f"fixed4-attribute_pool_{p}.jsonl" if budget is None else f"fixed4b{budget:03d}-attribute_pool_{p}.jsonl")
             for p in LEVELS]
    return [mean(p, key) for p in paths] if all(p.exists() for p in paths) else None


done = [c for c in CORPORA if all(curve(c, b) for b in BUDGETS)]
if not done:
    sys.exit("no corpus has every budgeted stream yet")
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK})
cols = 3 if len(done) > 4 else min(2, len(done))
nrows = -(-len(done) // cols)
fig, axes = plt.subplots(nrows, cols, figsize=(max(5 * cols, 11), 3.6 * nrows + 0.9), facecolor=SURFACE, squeeze=False)
for ax in axes.flat[len(done):]:
    ax.set_visible(False)
for ax, corpus in zip(axes.flat, done):
    ax.set_facecolor(SURFACE)
    static = curve(corpus, None, "static_benchmark")
    full = curve(corpus, None)
    ax.plot(LEVELS, static, color=STATIC, linestyle=(0, (4, 2.5)), linewidth=2, marker="o", markersize=6,
            markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3)
    for b, color in zip(BUDGETS, RAMP):
        ax.plot(LEVELS, curve(corpus, b), color=color, linewidth=2, marker="o", markersize=6, markeredgecolor=SURFACE,
                markeredgewidth=1.5, zorder=4)
    ax.plot(LEVELS, full, color=FULL, linewidth=1, linestyle=(0, (1, 1.5)), zorder=5)
    top = max(max(full), max(max(curve(corpus, b)) for b in BUDGETS))
    ax.set_ylim(0, top * 1.25)
    ax.set_xlim(-6, 106)
    ax.set_xticks(list(LEVELS), [f"{p}%" for p in LEVELS])
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_title(corpus, loc="left", fontsize=11, fontweight="bold", color=INK)
    ax.set_xlabel("Drift")
    ax.set_ylabel("Score")
fig.suptitle("Score under workload drift at patch budgets", x=0.02, ha="left", fontsize=13, fontweight="bold", color=INK)
fig.text(0.02, 1 - 0.55 / fig.get_figheight(),
         "Budget = % of the patch tokens unlimited adaptive spends at 100% drift on that corpus. y-axes start at 0.",
         fontsize=9, color=INK2)
handles = ([Line2D([], [], color=STATIC, linestyle=(0, (4, 2.5)), linewidth=2, marker="o", markersize=5)]
           + [Line2D([], [], color=c, linewidth=2, marker="o", markersize=5) for c in RAMP]
           + [Line2D([], [], color=FULL, linewidth=1, linestyle=(0, (1, 1.5)))])
labels = ["Static (0%)"] + [f"{b}%" for b in BUDGETS] + ["Unlimited"]
fig.legend(handles, labels, loc="upper right", ncol=len(labels), frameon=False, fontsize=9,
           bbox_to_anchor=(0.99, 1 - 0.95 / fig.get_figheight()))
fig.tight_layout(rect=(0, 0, 1, 1 - 1.15 / fig.get_figheight()))
fig.savefig(OUT, dpi=200, facecolor=SURFACE)
print(OUT, "corpora:", ",".join(done))
