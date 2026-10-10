"""Figures for the catalogue planner's evaluation (results/experiments/why/figures/w13_system.png).

    ~/venvs/quwarts/bin/python results/experiments/why/v2_figures.py
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
NAMES = {"cspaper": "Research papers", "player": "Basketball players", "art": "Artists", "med": "Medical", "legal": "Court judgments"}
DOCETL = json.loads((EXP / "WHY" / "transfer_docetl_predict" / "summary.json").read_text())["mean_score"]


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def docetl_tokens() -> dict:
    """DocETL's tokens on the test queries of the current catalogue (its per-query extraction, results/docetl_drift_ollama)."""
    out = {}
    for c in NAMES:
        f = EXP.parent / "docetl_drift_ollama" / c / "per_query.json"
        if f.exists():
            d = json.loads(f.read_text())
            test = set(json.loads((EXP.parent / "drift_live_ollama" / c / "fixed4_attribute_pool_design.json").read_text())["test"])
            rows = [v for q, v in d.items() if q in test] or list(d.values())
            out[c] = sum(v.get("prompt_tokens", 0) + v.get("completion_tokens", 0) for v in rows)
    return out


def system_figure():
    d = json.loads((EXP / "V2" / "summary.json").read_text())["runs"]
    dt = docetl_tokens()
    fig, axes = plt.subplots(1, 5, figsize=(14.5, 3.6))
    for ax, c in zip(axes, ["cspaper", "player", "art", "med", "legal"]):
        runs = d.get(c, {})
        rec = runs.get("recorded", {})
        pts = sorted([(v["tokens"], v["score"]) for k, v in rec.items() if "attribute_pool_100" in k and v["tokens"] > 0])
        if pts:
            ax.plot([p[0] / 1e6 for p in pts], [p[1] for p in pts], marker="o", color=MUTED, label="Recorded system, budgets 25%, 50% and unlimited")
        fam = "V3" if "V3" in runs else ("v2" if "v2" in runs else "V2a")
        v2 = (runs.get(fam) or {}).get("fixed4-attribute_pool_100")
        if v2:
            ax.plot([(v2["tokens"] + v2["repair_tokens"]) / 1e6], [v2["score"]], marker="*", markersize=14, linestyle="none", color=BLUE, label="Catalogue planner (7B + 32B tokens)")
        pre = "V3-" if fam == "V3" else ("" if fam == "v2" else "V2a-")
        for key, mk, col, lab in (("ablate-unit", "s", ORANGE, "without the unit decision"), ("ablate-windows", "^", AQUA, "without windows"),
                                  ("ablate-repair", "D", YELLOW, "without second looks"), ("ablate-itemfilter", "v", INK2, "without the item filter")):
            r = (runs.get(pre + key) or {}).get("fixed4-attribute_pool_100")
            if r:
                ax.plot([(r["tokens"] + r["repair_tokens"]) / 1e6], [r["score"]], marker=mk, linestyle="none", color=col, markerfacecolor="none", markersize=8, label=f"Planner {lab}")
        if c in DOCETL and c in dt:
            ax.plot([dt[c] / 1e6], [DOCETL[c]], marker="x", markersize=9, linestyle="none", color=MAGENTA, label="DocETL (per-query extraction)")
        ax.set_xscale("log")
        ax.xaxis.set_major_locator(matplotlib.ticker.LogLocator(base=10, numticks=5))
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_title(NAMES[c], fontsize=10, loc="left", color=INK)
        if c == "cspaper":
            ax.set_ylabel("Mean query score")
        style(ax)
    fig.supxlabel("Tokens spent on extraction, millions (log scale)", fontsize=10, color=INK2, y=0.13)
    handles, labels = axes[0].get_legend_handles_labels()
    seen = {}
    for h, l in zip(handles, labels):
        seen.setdefault(l, h)
    fig.legend(list(seen.values()), list(seen.keys()), loc="lower center", ncol=3, fontsize=8.5, frameon=False, bbox_to_anchor=(0.5, -0.03))
    fig.tight_layout(rect=(0, 0.14, 1, 1))
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / "w13_system.png", dpi=180)
    plt.close(fig)
    print(OUT / "w13_system.png")


if __name__ == "__main__":
    system_figure()
