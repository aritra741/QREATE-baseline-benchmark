"""Tokens spent under workload drift (fixed4 levels, attribute_pool), one panel per corpus: the build's read and the
on-arrival patch reads, stacked per level (input + output tokens, from fixed_levels.csv). The static build's cost
is the build bar alone.

    ~/venvs/quwarts/bin/python systems/WDIRS/quwarts/scripts/plot_drift_cost.py [corpora] [out.png]
"""

import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[4]
LIVE = ROOT / "results" / "drift_live_ollama"
CORPORA = (sys.argv[1] if len(sys.argv) > 1 else "player,cspaper,art,med,legal").split(",")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else LIVE / "drift_cost.png"
LEVELS = (0, 25, 50, 75, 100)

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BUILD, PATCH = "#2a78d6", "#eb6834"

rows = {(r["corpus"], int(r["level"])): r for r in csv.DictReader(open(LIVE / "fixed_levels.csv"))
        if r["axis"] == "attribute_pool"}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK})
cols = 3 if len(CORPORA) > 4 else 2
nrows = -(-len(CORPORA) // cols)
fig, axes = plt.subplots(nrows, cols, figsize=(5 * cols, 3.6 * nrows + 0.9), facecolor=SURFACE, squeeze=False)
for ax in axes.flat[len(CORPORA):]:
    ax.set_visible(False)
for ax, corpus in zip(axes.flat, CORPORA):
    build = [int(rows[(corpus, p)]["build_tokens"]) / 1e6 for p in LEVELS]
    patch = [(int(rows[(corpus, p)]["patch_input"]) + int(rows[(corpus, p)]["patch_output"])) / 1e6 for p in LEVELS]
    ax.set_facecolor(SURFACE)
    x = range(len(LEVELS))
    ax.bar(x, build, width=0.62, color=BUILD, edgecolor=SURFACE, linewidth=2, zorder=3)
    ax.bar(x, patch, width=0.62, bottom=build, color=PATCH, edgecolor=SURFACE, linewidth=2, zorder=3)
    for i in (0, len(LEVELS) - 1):
        total = build[i] + patch[i]
        ax.annotate(f"{total:.1f}M", (i, total), textcoords="offset points", xytext=(0, 4), ha="center",
                    fontsize=9, color=INK)
    ax.set_ylim(0, max(b + p for b, p in zip(build, patch)) * 1.18)
    ax.set_xticks(list(x), [f"{p}%" for p in LEVELS])
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_title(corpus, loc="left", fontsize=11, fontweight="bold", color=INK)
    ax.set_xlabel("Drift")
    ax.set_ylabel("Tokens (millions)")
fig.suptitle("Token cost under workload drift", x=0.02, ha="left", fontsize=13, fontweight="bold", color=INK)
fig.text(0.02, 1 - 0.55 / fig.get_figheight(),
         "Input + output tokens per level. y-axes start at 0; scales differ per corpus. "
         "No adaptation costs the build bar alone.", fontsize=9, color=INK2)
fig.legend([Patch(color=BUILD), Patch(color=PATCH)], ["Build read", "On-arrival patches"], loc="upper right", ncol=2,
           frameon=False, fontsize=10, bbox_to_anchor=(0.99, 1 - 0.18 / fig.get_figheight()))
fig.tight_layout(rect=(0, 0, 1, 1 - 0.8 / fig.get_figheight()))
fig.savefig(OUT, dpi=200, facecolor=SURFACE)
print(OUT)
