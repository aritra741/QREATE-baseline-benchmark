"""Player budget sweep (router-v3, Ollama Qwen 2.5 7B): score and tokens spent against the budget theta, as a share
of DocETL's recorded Player tokens (12,829,901). Score = mean per-query structure F2 x cell F1@0.20 on the 20
held-out queries; DocETL's recorded product on the same queries is the reference.

    ~/venvs/quwarts/bin/python systems/WDIRS/quwarts/scripts/plot_budget_sweep.py [out.png]
"""

import json
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[4]
SWEEP = ROOT / "results" / "quwarts_player_budget_sweep_ollama"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else SWEEP / "budget_sweep.png"
DOCETL_TOKENS, DOCETL_SCORE = 12_829_901, 0.2017
# One shared read of every input-workload column, no planner or probes, on the same server.
SHARED = json.loads((ROOT / "results" / "quwarts_router_v3" / "player_ollama" / "shared_read_protocol" /
                     "score_blank.json").read_text())
SHARED_TOKENS, SHARED_SCORE = SHARED["read_tokens"], SHARED["read_first"]["held_out_split"]["product"]

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
QUWARTS, DOCETL = "#2a78d6", "#eb6834"

pts = []
for d in sorted(SWEEP.glob("f*/execute/score.json")):
    s = json.loads(d.read_text())
    pct = int(d.parts[-3][1:])
    pts.append((pct, s["mean_per_query_product"], s["total_tokens"] / 1e6, s["probe_tokens"] / 1e6))
xs, score, spent, probe = zip(*pts)

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK})
fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.4), facecolor=SURFACE)
for ax in (a, b):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_xlim(-4, 106)
    ax.set_xticks([5, 25, 50, 75, 100], ["5%", "25%", "50%", "75%", "100%"])
    ax.set_xlabel("Budget (share of DocETL's tokens)")

a.plot(xs, score, color=QUWARTS, linewidth=2, marker="o", markersize=7, markeredgecolor=SURFACE, markeredgewidth=2,
       zorder=3, label="QuWARTS")
a.plot([100], [DOCETL_SCORE], linestyle="none", marker="D", markersize=8, color=DOCETL, markeredgecolor=SURFACE,
       markeredgewidth=2, zorder=4, label="DocETL (its full 12.8M tokens)")
for x, y in zip(xs, score):
    if x in (5, 25, 100):
        a.annotate(f"{y:.3f}", (x, y), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=9, color=INK)
a.plot([100 * SHARED_TOKENS / DOCETL_TOKENS], [SHARED_SCORE], linestyle="none", marker="s", markersize=8, color=INK,
       markeredgecolor=SURFACE, markeredgewidth=2, zorder=4, label=f"Shared read, no planner ({SHARED_TOKENS / 1e6:.1f}M tokens)")
a.annotate(f"{SHARED_SCORE:.3f}", (100 * SHARED_TOKENS / DOCETL_TOKENS, SHARED_SCORE), textcoords="offset points",
           xytext=(9, -3), ha="left", fontsize=9, color=INK)
a.annotate(f"{DOCETL_SCORE:.3f}", (100, DOCETL_SCORE), textcoords="offset points", xytext=(0, -16), ha="center",
           fontsize=9, color=INK)
a.set_ylim(0, max(max(score), SHARED_SCORE) * 1.3)
a.set_ylabel("Score")
a.set_title("Score", loc="left", fontsize=11, fontweight="bold")
a.legend(frameon=False, loc="lower right", fontsize=9)

b.plot([0, 100], [0, DOCETL_TOKENS / 1e6], color=INK2, linewidth=1, linestyle=(0, (4, 3)), zorder=2)
b.annotate("budget θ", (60, 0.6 * DOCETL_TOKENS / 1e6), textcoords="offset points", xytext=(-6, 6), ha="right",
           fontsize=9, color=INK2)
b.plot(xs, spent, color=QUWARTS, linewidth=2, marker="o", markersize=7, markeredgecolor=SURFACE, markeredgewidth=2,
       zorder=3)
for x, y in zip(xs, spent):
    if x in (5, 50, 100):
        b.annotate(f"{y:.1f}M", (x, y), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=9, color=INK)
b.set_ylim(0, DOCETL_TOKENS / 1e6 * 1.1)
b.set_ylabel("Tokens spent (millions)")
b.set_title("Tokens spent (probes + reads)", loc="left", fontsize=11, fontweight="bold")

fig.suptitle("Player: QuWARTS at different budgets", x=0.02, ha="left", fontsize=13, fontweight="bold")
fig.text(0.02, 0.885, "100% = DocETL's recorded 12.8M tokens on the same queries.",
         fontsize=9, color=INK2)
fig.tight_layout(rect=(0, 0, 1, 0.86))
fig.savefig(OUT, dpi=200, facecolor=SURFACE)
print(OUT)
