"""Score under workload drift (fixed4 levels, attribute_pool), one panel per corpus: QuWARTS with on-arrival
patching, and the same build without adaptation (static). Score = structure F2 x cell F1, per query, averaged.

    ~/venvs/quwarts/bin/python systems/WDIRS/quwarts/scripts/plot_drift_curves.py [corpora] [out.png]
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
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else LIVE / "drift_curves.png"
LEVELS = (0, 25, 50, 75, 100)

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = [("benchmark", "Adaptive (patch on arrival)", "#2a78d6", "-"),
          ("static_benchmark", "No adaptation (static build)", "#eb6834", (0, (4, 2.5)))]


def curve(corpus: str, key: str) -> tuple[list[float], int]:
    ys, n = [], 0
    for p in LEVELS:
        rows = [json.loads(line) for line in open(LIVE / corpus / "streams" / f"fixed4-attribute_pool_{p}.jsonl")]
        ys.append(sum(r[key] for r in rows) / len(rows))
        n = len(rows)
    return ys, n


plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK})
cols = 3 if len(CORPORA) > 4 else 2
nrows = -(-len(CORPORA) // cols)
fig, axes = plt.subplots(nrows, cols, figsize=(5 * cols, 3.6 * nrows + 0.9), facecolor=SURFACE, squeeze=False)
for ax in axes.flat[len(CORPORA):]:
    ax.set_visible(False)
for ax, corpus in zip(axes.flat, CORPORA):
    ax.set_facecolor(SURFACE)
    top = 0.0
    for key, _label, color, style in SERIES:
        ys, n = curve(corpus, key)
        top = max(top, max(ys))
        ax.plot(LEVELS, ys, color=color, linestyle=style, linewidth=2, marker="o", markersize=7,
                markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
        ax.annotate(f"{ys[-1]:.3f}", (100, ys[-1]), textcoords="offset points", xytext=(0, 9), ha="center",
                    fontsize=9, color=INK)
    ax.annotate(f"{ys[0]:.3f}", (0, ys[0]), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=9, color=INK)
    ax.set_ylim(0, top * 1.35)
    ax.set_xlim(-6, 106)
    ax.set_xticks(list(LEVELS), [f"{p}%" for p in LEVELS])
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_title(f"{corpus}  ({n} queries)", loc="left", fontsize=11, fontweight="bold", color=INK)
    ax.set_xlabel("Drift")
    ax.set_ylabel("Score")
fig.suptitle("Score under workload drift", x=0.02, ha="left", fontsize=13, fontweight="bold", color=INK)
fig.text(0.02, 1 - 0.55 / fig.get_figheight(), "y-axes start at 0; scales differ per corpus.", fontsize=9, color=INK2)
handles = [Line2D([], [], color=c, linestyle=s, linewidth=2, marker="o", markersize=6, markeredgecolor=SURFACE)
           for _k, _l, c, s in SERIES]
fig.legend(handles, [l for _k, l, _c, _s in SERIES], loc="upper right", ncol=2, frameon=False, fontsize=10,
           bbox_to_anchor=(0.99, 1 - 0.18 / fig.get_figheight()))
fig.tight_layout(rect=(0, 0, 1, 1 - 0.8 / fig.get_figheight()))
fig.savefig(OUT, dpi=200, facecolor=SURFACE)
print(OUT)
