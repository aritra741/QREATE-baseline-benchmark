"""Figures for results/experiments/RESULTS_PAPER.md, one or two per research question, read from the result files.

    ~/venvs/quwarts/bin/python systems/WDIRS/quwarts/scripts/plot_results_paper.py

Writes results/experiments/figures/*.png. Palette: the validated default categorical order (blue, orange, aqua,
yellow, magenta; validated light, contrast WARN on slots 3-5, so those series are direct-labeled and every value is
also in the document's tables).
"""

import csv
import json
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
RES = ROOT / "results"
EXP = RES / "experiments"
OUT = EXP / "figures"
OUT.mkdir(parents=True, exist_ok=True)

SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
CORPORA = ["player", "art", "cspaper", "legal", "med"]
CORPUS_COLOR = dict(zip(CORPORA, [BLUE, ORANGE, AQUA, YELLOW, MAGENTA]))
LEVELS = (0, 25, 50, 75, 100)

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 2, "lines.markersize": 7,
    "legend.frameon": False,
})


def style(ax, ygrid=True):
    if ygrid:
        ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def save(fig, name, title, subtitle=None, bottom=0.0):
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    if subtitle:
        fig.text(0.01, 1 - 0.5 / fig.get_figheight(), subtitle, fontsize=9, color=INK2, ha="left")
    fig.tight_layout(rect=(0, bottom, 1, 1 - (0.6 if subtitle else 0.4) / fig.get_figheight()))
    fig.savefig(OUT / name, dpi=180)
    plt.close(fig)
    print(OUT / name)


def spread(values: list[float], gap: float) -> list[float]:
    """Label positions near ``values`` with at least ``gap`` between neighbours (order kept)."""

    order = sorted(range(len(values)), key=lambda i: values[i])
    pos = [values[i] for i in order]
    for k in range(1, len(pos)):
        pos[k] = max(pos[k], pos[k - 1] + gap)
    out = [0.0] * len(values)
    for k, i in enumerate(order):
        out[i] = pos[k]
    return out


def stream(corpus: str, name: str, root: Path = RES / "drift_live_ollama") -> list[dict]:
    return [json.loads(line) for line in (root / corpus / "streams" / f"{name}.jsonl").read_text().splitlines()]


def mean(xs):
    return sum(xs) / len(xs)


# ------------------------------------------------------------------ RQ1

def rq1_drift():
    fig, axes = plt.subplots(1, 5, figsize=(15, 3.6), sharey=False)
    for ax, c in zip(axes, CORPORA):
        rows = {p: stream(c, f"fixed4-attribute_pool_{p}") for p in LEVELS}
        ad = [mean([r["benchmark"] for r in rows[p]]) for p in LEVELS]
        st = [mean([r["static_benchmark"] for r in rows[p]]) for p in LEVELS]
        ax.plot(LEVELS, ad, color=BLUE, marker="o", markeredgecolor=SURFACE, markeredgewidth=1.5, label="On-demand patching")
        ax.plot(LEVELS, st, color=ORANGE, marker="o", linestyle=(0, (4, 2.5)), markeredgecolor=SURFACE, markeredgewidth=1.5,
                label="Static build")
        ax.annotate(f"{ad[-1]:.3f}", (100, ad[-1]), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=8.5, color=INK)
        ax.annotate(f"{st[-1]:.3f}", (100, st[-1]), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=8.5, color=INK)
        ax.set_ylim(0, max(ad + st) * 1.3)
        ax.set_xticks(LEVELS, [f"{p}%" for p in LEVELS])
        ax.set_xlabel("Drift (new columns not anticipated)")
        ax.set_title(f"{c}  ({len(rows[100])} queries)")
        style(ax)
    axes[0].set_ylabel("Score")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper right", ncol=2, bbox_to_anchor=(0.995, 1.0))
    save(fig, "rq1_drift.png", "On-demand patching keeps accuracy under drift; a static build collapses",
         "Score per query (structure F2 × cell F1), averaged. y-axes start at 0; scales differ per corpus.")


def rq1_seeds():
    roots = [RES / "drift_live_ollama"] + [EXP / f"E11-seed{k}" / "live" for k in (1, 2, 3)]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.9))
    for ax, c in zip(axes, ["cspaper", "player"]):
        top = 0.0
        for k, root in enumerate(roots):
            rows = {p: stream(c, f"fixed4-attribute_pool_{p}", root) for p in LEVELS}
            ad = [mean([r["benchmark"] for r in rows[p]]) for p in LEVELS]
            st = [mean([r["static_benchmark"] for r in rows[p]]) for p in LEVELS]
            top = max(top, max(ad))
            ax.plot(LEVELS, ad, color=BLUE, linewidth=1.6, alpha=0.9, marker="o", markersize=5,
                    markeredgecolor=SURFACE, label="On-demand patching" if k == 0 else None)
            ax.plot(LEVELS, st, color=ORANGE, linewidth=1.6, alpha=0.9, linestyle=(0, (4, 2.5)), marker="o", markersize=5,
                    markeredgecolor=SURFACE, label="Static build" if k == 0 else None)
        ax.set_ylim(0, top * 1.3)
        ax.set_xticks(LEVELS, [f"{p}%" for p in LEVELS])
        ax.set_xlabel("Drift (new columns not anticipated)")
        ax.set_title(c)
        style(ax)
    axes[0].set_ylabel("Score")
    axes[0].legend(loc="lower left")
    save(fig, "rq1_seeds.png", "The drift result holds across four draws of the withheld columns",
         "One line per draw (seed 0 = the recorded design). Patched curves stay flat; static collapses on every draw.")


def rq1_train():
    shares = {"cspaper": [(10, "E12-w0f010"), (25, "E12-w0f025"), (100, None)],
              "player": [(10, "E12-w0f010"), (25, "E12-w0f025"), (100, None)],
              "art": [(10, "E12-w0f010"), (25, "E12-w0f025"), (50, "E12-w0f050"), (100, None)],
              "med": [(10, "E12-w0f010"), (25, "E12-w0f025"), (50, "E12-w0f050"), (100, None)],
              "legal": [(10, "E12-w0f010"), (25, "E12-w0f025"), (50, "E12-w0f050"), (100, None)]}
    ramp = {10: "#86b6ef", 25: "#5598e7", 50: "#2a78d6", 100: "#104281"}
    oramp = {10: "#f5b597", 25: "#ef8d63", 50: "#eb6834", 100: "#b44a1f"}
    fig, grid = plt.subplots(2, 3, figsize=(15, 8.2))
    axes = list(grid.flat)
    for ax, (c, runs) in zip(axes, shares.items()):
        top = 0.0
        for share, d in runs:
            root = RES / "drift_live_ollama" if d is None else EXP / d / "live"
            rows = {p: stream(c, f"fixed4-attribute_pool_{p}", root) for p in LEVELS}
            ad = [mean([r["benchmark"] for r in rows[p]]) for p in LEVELS]
            st = [mean([r["static_benchmark"] for r in rows[p]]) for p in LEVELS]
            top = max(top, max(ad))
            ax.plot(LEVELS, ad, color=ramp[share], marker="o", markersize=5, markeredgecolor=SURFACE,
                    label=f"patched, train {share}%")
            ax.plot(LEVELS, st, color=oramp[share], linestyle=(0, (4, 2.5)), marker="o", markersize=5,
                    markeredgecolor=SURFACE, label=f"static, train {share}%")
        ax.set_ylim(0, top * 1.3)
        ax.set_xticks(LEVELS, [f"{p}%" for p in LEVELS])
        ax.set_xlabel("Drift (new columns not anticipated)")
        ax.set_title(c)
        style(ax)
    axes[0].set_ylabel("Score")
    axes[3].set_ylabel("Score")
    h, l = axes[2].get_legend_handles_labels()
    order = [0, 2, 4, 6, 1, 3, 5, 7]
    axes[5].axis("off")
    axes[5].legend([h[i] for i in order], [l[i] for i in order], fontsize=9.5, ncol=2, loc="center", frameon=False)
    save(fig, "rq1_train.png", "The drift result holds for every train share",
         "Build workload cut to 10–50% of its queries (same test queries). Darker = larger train share; blue patched, "
         "orange dashed static.")


def rq1_anticipation():
    rows = {(r["corpus"], int(r["level"])): r for r in csv.DictReader(open(RES / "drift_live_ollama" / "fixed_levels.csv"))
            if r["axis"] == "attribute_pool"}
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ends = {}
    for c in CORPORA:
        tot = [int(rows[(c, p)]["build_tokens"]) + int(rows[(c, p)]["patch_input"]) + int(rows[(c, p)]["patch_output"])
               for p in LEVELS]
        rel = [t / tot[0] for t in tot]
        ax.plot(LEVELS, rel, color=CORPUS_COLOR[c], marker="o", markeredgecolor=SURFACE, markeredgewidth=1.5)
        ends[c] = rel[-1]
    for c, y in zip(ends, spread(list(ends.values()), 0.5)):
        ax.annotate(f"{c} ×{ends[c]:.1f}", (103, y), va="center", fontsize=9, color=INK)
    ax.axhline(1, color=AXIS, linewidth=1)
    ax.set_xticks(LEVELS, [f"{p}%" for p in LEVELS])
    ax.set_xlim(-5, 128)
    ax.set_ylim(0, None)
    ax.set_xlabel("New columns not anticipated by the build (drift)")
    ax.set_ylabel("Total tokens ÷ fully anticipated")
    style(ax)
    save(fig, "rq1_anticipation.png", "Patching a column later costs far more than reading it up front",
         "Build + patch tokens relative to a build that anticipated every column; scores stay within 0.014 (see table).")


# ------------------------------------------------------------------ RQ2

def rq2_width():
    widths = [1, 3, 6, 12]
    ends = {}
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for c in CORPORA:
        f = EXP / "E2.1b-width" / c / "summary.json"
        if not f.exists():
            continue
        s = json.loads(f.read_text())["by_width"]
        ys = [s[str(w)]["exact_agree"] for w in widths]
        ax.plot(widths, ys, color=CORPUS_COLOR[c], marker="o", markeredgecolor=SURFACE, markeredgewidth=1.5)
        ends[c] = ys[-1]
    for c, y in zip(ends, spread(list(ends.values()), 0.045)):
        ax.annotate(c, (13.5, y), va="center", fontsize=9, color=INK)
    ax.set_xscale("log", base=2)
    ax.set_xticks(widths, [str(w) for w in widths])
    ax.set_xlim(0.85, 22)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Columns asked per prompt (log scale)")
    ax.set_ylabel("Agreement with gold (both have a value)")
    style(ax)
    save(fig, "rq2_width.png", "Asking for fewer columns per prompt does not help in general",
         "Same 12 columns and documents per corpus; one column per prompt costs 6–10× the tokens.")


# ------------------------------------------------------------------ RQ3

def policy_summary(corpus):
    return json.loads((EXP / "E3-policies" / corpus / "summary.json").read_text())


def rq3_legal():
    d = policy_summary("legal")
    budgets = [10, 25, 50, 75, 100]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    for name, color, label, ls in (("fcfs", ORANGE, "First-come-first-served", (0, (4, 2.5))),
                                   ("fragile", BLUE, "Skip MIN/MAX-over-text queries", "-")):
        ys = [d[name]["cells"][f"{b}@100"][0] for b in budgets]
        ax.plot(budgets, ys, color=color, linestyle=ls, marker="o", markeredgecolor=SURFACE, markeredgewidth=1.5, label=label)
    ax.axhline(d["unlimited"]["100"], color=MUTED, linewidth=1, linestyle=(0, (1, 1.5)))
    ax.annotate("unlimited budget", (100, d["unlimited"]["100"]), xytext=(0, 6), textcoords="offset points", ha="right",
                fontsize=8.5, color=INK2)
    ax.annotate("collapse: two early patches\nexhaust the budget", (50, d["fcfs"]["cells"]["50@100"][0]), xytext=(12, -6),
                textcoords="offset points", fontsize=8.5, color=INK2)
    ax.set_xticks(budgets, [f"{b}%" for b in budgets])
    ax.set_ylim(0, 0.15)
    ax.set_xlabel("Patch budget (% of the unlimited stream's patch tokens)")
    ax.set_ylabel("Score")
    ax.legend(loc="lower right")
    style(ax)
    save(fig, "rq3_legal_budget.png", "Skipping unwinnable queries removes the budget collapse",
         "Legal, 100% drift: a larger budget scores less first-come-first-served. Overlapping lines: same choices.")


def rq3_policies():
    pols = [("fragile", "Skip MIN/MAX over text", BLUE), ("oracle", "Hindsight oracle", ORANGE),
            ("cap", "Per-patch cap", AQUA), ("pace", "Pacing", YELLOW)]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    w = 0.19
    for i, (key, label, color) in enumerate(pols):
        vals = []
        for c in CORPORA:
            d = policy_summary(c)
            vals.append(d[key]["mean_score"] - d["fcfs"]["mean_score"] if key in d else 0.0)
        xs = [j + (i - 1.5) * w for j in range(len(CORPORA))]
        ax.bar(xs, vals, width=w - 0.02, color=color, label=label, edgecolor=SURFACE, linewidth=1)
    ax.axhline(0, color=AXIS, linewidth=1)
    ax.set_xticks(range(len(CORPORA)), CORPORA)
    ax.set_ylabel("Score minus first-come-first-served")
    ax.legend(ncol=4, loc="lower left", bbox_to_anchor=(0, 1.0))
    style(ax)
    save(fig, "rq3_policies.png", "Only skipping unwinnable queries never hurts",
         "Mean over 25 budget × drift settings per corpus. Skip and oracle are no-ops where no query matches.")


# ------------------------------------------------------------------ RQ4

def rq4_signals():
    import sys

    sys.path.insert(0, str(ROOT / "systems" / "WDIRS"))
    import os

    os.environ.setdefault("QUWARTS_DRIFT_DESIGN", "drift_paired")
    from quwarts.eval import drift_run as R
    from quwarts.eval.exp_analysis import query_features

    rows = []
    for c in CORPORA:
        ctx = R.context(c)
        for r in csv.DictReader(open(EXP / "E2.2-patches" / c / "patches.csv")):
            if r["budget"] != "":
                continue
            f = query_features(ctx.catalog[r["qid"]], ctx.fields)
            aggs = f.get("aggs", [])
            rows.append({"tokens": int(r["tokens"]), "waste": r["no_value"] == "True",
                         "minmax_text": any(a.endswith("_text") for a in aggs),
                         "avg_sum": any(a in ("avg", "sum") for a in aggs) and not any(a.endswith("_text") for a in aggs),
                         "filtered": bool(f.get("filter_kinds"))})
    total_waste = sum(r["tokens"] for r in rows if r["waste"])
    sigs = [("MIN/MAX over a text column", lambda r: r["minmax_text"]), ("No filter (whole corpus)", lambda r: not r["filtered"]),
            ("Filtered (scoped)", lambda r: r["filtered"]), ("AVG / SUM", lambda r: r["avg_sum"])]
    share, cover = [], []
    for _n, pred in sigs:
        sel = [r for r in rows if pred(r)]
        t = sum(r["tokens"] for r in sel)
        wst = sum(r["tokens"] for r in sel if r["waste"])
        share.append(wst / t)
        cover.append(wst / total_waste)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.4), sharey=True)
    names = [n for n, _ in sigs]
    for ax, vals, title in ((axes[0], share, "Share of the signal's patch tokens wasted"),
                            (axes[1], cover, "Share of all wasted tokens it covers")):
        ax.barh(range(len(names)), vals, color=BLUE, height=0.55)
        for i, v in enumerate(vals):
            ax.annotate(f"{v:.0%}", (v, i), xytext=(4, 0), textcoords="offset points", va="center", fontsize=9, color=INK)
        ax.set_xlim(0, 1.08)
        ax.set_title(title)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    axes[0].set_yticks(range(len(names)), names)
    axes[0].invert_yaxis()
    save(fig, "rq4_signals.png", "Two SQL-visible signals locate most wasted extraction tokens",
         f"138 patches over five corpora, 152M tokens, {total_waste / sum(r['tokens'] for r in rows):.0%} wasted "
         "(improved no query).")


# ------------------------------------------------------------------ RQ5

def rq5_planner():
    def sr(path):
        d = json.loads((RES / "quwarts_router_v3" / path / "score_blank.json").read_text())
        return d["read_first"]["held_out_split"]["product"], d["read_tokens"]

    def pl(path):
        s = json.loads(path.read_text())
        return s["mean_per_query_product"], s["total_tokens"]

    pts = []
    sweep = RES / "quwarts_player_budget_sweep_ollama"
    for f in ("f025", "f075"):
        pts.append(("Planner, names and types", *pl(sweep / f / "execute" / "score.json"), BLUE, f[1:].lstrip("0") + "%"))
    for f in ("f025", "f075"):
        pts.append(("Planner, with descriptions", *pl(EXP / "E5.2-planner-protocol" / f / "execute" / "score.json"), ORANGE,
                    f[1:].lstrip("0") + "%"))
    pts.append(("Planner, descriptions + join weight", *pl(EXP / "E5.3-planner-joinweight" / "f075" / "execute" / "score.json"),
                AQUA, "75%"))
    s_plain, t_plain = sr("player_ollama_plain/shared_read")
    s_prot, t_prot = sr("player_ollama/shared_read_protocol")
    for t, label in (("t025", "25%"), ("t075", "75%")):
        s, tok = pl(EXP / "E5.4-planner-on-shared" / t / "execute" / "score.json")
        pts.append(("Shared pass + planner on top", s, tok + t_prot, MAGENTA, label))
    fig, ax = plt.subplots(figsize=(9, 4.6))
    seen = set()
    for name, s, tok, color, lab in pts:
        ax.scatter(tok / 1e6, s, s=70, color=color, edgecolor=SURFACE, linewidth=1.5, zorder=3,
                   label=None if name in seen else name)
        seen.add(name)
        dy = 6 if (color == ORANGE and lab == "25%") else (-10 if (color == BLUE and lab == "25%") else -3)
        ax.annotate(lab, (tok / 1e6, s), xytext=(6, dy), textcoords="offset points", fontsize=8.5, color=INK2)
    ax.scatter([t_plain / 1e6], [s_plain], s=110, marker="D", color=INK2, edgecolor=SURFACE, linewidth=1.5, zorder=4,
               label="One shared pass, names and types")
    ax.scatter([t_prot / 1e6], [s_prot], s=110, marker="D", color=YELLOW, edgecolor=INK2, linewidth=1, zorder=4,
               label="One shared pass, with descriptions")
    ax.annotate(f"{s_prot:.3f}", (t_prot / 1e6, s_prot), xytext=(8, 4), textcoords="offset points", fontsize=9, color=INK)
    ax.set_xlim(0, None)
    ax.set_ylim(0, 0.65)
    ax.set_xlabel("Tokens (millions)")
    ax.set_ylabel("Score, 20 held-out player queries")
    ax.legend(loc="lower right", fontsize=8.5)
    style(ax)
    save(fig, "rq5_planner.png", "No planner configuration reaches one shared pass with good field descriptions",
         "Player, Qwen 2.5 7B (4-bit). Point labels: planner budget as a share of DocETL's player tokens.")


# ------------------------------------------------------------------ RQ6

def rq6_cells():
    one, both, better = [], [], []
    for c in CORPORA:
        d = json.loads((EXP / "E2.3-order" / c / "summary.json").read_text())
        one.append(d["cells_read_in_one_only"])
        both.append(d["cells_read_in_both_differ"])
        better.append(d["budget_scores_higher"])
    fig, ax = plt.subplots(figsize=(9, 3.8))
    w = 0.36
    xs = range(len(CORPORA))
    ax.bar([x - w / 2 for x in xs], one, width=w - 0.03, color=BLUE, label="Filled in one stream, empty in the other")
    ax.bar([x + w / 2 for x in xs], [b if b > 0 else float("nan") for b in both], width=w - 0.03, color=ORANGE,
           label="Filled in both, different values")
    ax.set_yscale("log")
    ax.set_ylim(0.7, 3e5)
    for x, b in zip(xs, both):
        ax.annotate(f"{b:,}", (x + w / 2, b if b > 0 else 0.7), xytext=(0, 3), textcoords="offset points", ha="center",
                    fontsize=8.5)
    ax.set_xticks(list(xs), CORPORA)
    ax.set_ylabel("Differing cells (log scale)")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2)
    style(ax)
    save(fig, "rq6_cells.png", "Order changes which documents are extracted, not the values extracted",
         "Cells that differ between a budgeted and the unlimited stream at the same drift level, all budgets and levels.")


# ------------------------------------------------------------------ RQ7

def rq7_models():
    models = [("Llama 3.1 8B", ORANGE), ("Qwen 2.5 7B", BLUE), ("Qwen 2.5 32B", AQUA)]

    def sr(tag):
        d = json.loads((RES / "quwarts_router_v3" / tag / "shared_read_protocol" / "score_blank.json").read_text())
        return d["read_first"]["held_out_split"]["product"]

    def st(root, c, p):
        rs = stream(c, f"fixed4-attribute_pool_{p}", root)
        return mean([r["benchmark"] for r in rs]), mean([r["static_benchmark"] for r in rs])

    roots = {"Llama 3.1 8B": "llama8b", "Qwen 2.5 32B": "qwen32b"}
    shared = [sr("player_ollama_llama8b"), sr("player_ollama"), sr("player_ollama_qwen32b")]
    player, cspaper = [], []
    for name, _c in models:
        if name == "Qwen 2.5 7B":
            player.append(st(RES / "drift_live_ollama", "player", 100))
            cspaper.append(st(RES / "drift_live_ollama", "cspaper", 100))
        else:
            player.append(st(EXP / f"E6.2-stream-{roots[name]}-player" / "live", "player", 100))
            cspaper.append(st(EXP / f"E6.2-stream-{roots[name]}-cspaper" / "live", "cspaper", 100))
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    panels = [("Player, one shared pass (20 held-out)", shared, None),
              ("Player at 100% drift", [p[0] for p in player], [p[1] for p in player]),
              ("cspaper at 100% drift", [p[0] for p in cspaper], [p[1] for p in cspaper])]
    for ax, (title, vals, static) in zip(axes, panels):
        for i, ((name, color), v) in enumerate(zip(models, vals)):
            ax.bar(i, v, width=0.6, color=color)
            ax.annotate(f"{v:.3f}", (i, v), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=9)
            if static:
                ax.hlines(static[i], i - 0.3, i + 0.3, color=INK, linewidth=2, linestyle=(0, (2, 1.5)))
        ax.set_xticks(range(3), [m for m, _ in models], fontsize=9)
        ax.set_ylim(0, max(vals) * 1.25)
        ax.set_title(title)
        style(ax)
    axes[0].set_ylabel("Score")
    axes[1].annotate("dashed: static build", (0.02, 0.95), xycoords="axes fraction", fontsize=8.5, color=INK2, va="top")
    save(fig, "rq7_models.png", "The drift result holds across models; capacity raises every number",
         "Patched (bars) vs static (dashed) at 100% drift, same patch cost for every model.")


# ------------------------------------------------------------------ RQ8

def rq8_bottleneck():
    sf, cf = [], []
    order = ["player", "legal", "cspaper", "art", "med"]
    for c in order:
        d = json.loads((EXP / "E2.4-errors" / c / "summary.json").read_text())["unlimited@100"]
        sf.append(d["structure_f2"])
        cf.append(d["cell_f1_20"])
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    w = 0.36
    xs = range(len(order))
    ax.bar([x - w / 2 for x in xs], sf, width=w - 0.03, color=BLUE, label="Structure F2 (right rows and groups)")
    ax.bar([x + w / 2 for x in xs], cf, width=w - 0.03, color=ORANGE, label="Cell F1 (right values)")
    for x, a, b in zip(xs, sf, cf):
        ax.annotate(f"{a:.2f}", (x - w / 2, a), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8.5)
        ax.annotate(f"{b:.2f}", (x + w / 2, b), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8.5)
    ax.set_xticks(list(xs), order)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Mean over queries")
    ax.legend(loc="upper right", ncol=2, bbox_to_anchor=(1, 1.12))
    style(ax)
    save(fig, "rq8_bottleneck.png", "Values limit most corpora; structure limits med",
         "With on-demand patching at 100% drift.")


def rq8_form():
    rows = []
    for c in CORPORA:
        for r in csv.DictReader(open(EXP / "E2.1-columns" / c / "columns.csv")):
            if r.get("agree_when_both") and r.get("lenient_agree_when_both"):
                e, l = float(r["agree_when_both"]), float(r["lenient_agree_when_both"])
                rows.append((l - e, r["column"], e, l))
    rows = sorted(rows, reverse=True)[:10][::-1]
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    for i, (_g, name, e, l) in enumerate(rows):
        ax.plot([e, l], [i, i], color=AXIS, linewidth=2, zorder=1)
        ax.scatter([e], [i], s=60, color=ORANGE, zorder=2, edgecolor=SURFACE, linewidth=1.5, label="Exact" if i == 0 else None)
        ax.scatter([l], [i], s=60, color=BLUE, zorder=2, edgecolor=SURFACE, linewidth=1.5,
                   label="Lenient (shared list item; case, dashes ignored)" if i == 0 else None)
    ax.set_yticks(range(len(rows)), [r[1] for r in rows], fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Agreement with gold where both have a value")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=8.5)
    save(fig, "rq8_form.png", "Many values are right in substance but not in the exact form a query groups by",
         "The ten columns with the largest gap between lenient and exact agreement, on the documents read.")


# ------------------------------------------------------------------ DocETL

def docetl():
    def ci(d):
        rng = random.Random(0)
        ms = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(4000))
        return ms[100], ms[3900]

    ours_m, doc_m, ratio, labels = [], [], [], []
    for c in CORPORA:
        dd = json.loads((RES / "docetl_drift_ollama" / c / "per_query.json").read_text())
        ours = {r["qid"]: r for r in stream(c, "fixed4-attribute_pool_100")}
        q = [k for k in dd if k in ours]
        ours_m.append(mean([ours[k]["benchmark"] for k in q]))
        doc_m.append(mean([dd[k]["benchmark"] for k in q]))
        dt = sum(dd[k]["prompt_tokens"] + dd[k]["completion_tokens"] for k in q)
        ot = sum(ours[k]["input_tokens"] + ours[k]["output_tokens"] for k in q)
        ot += json.loads((RES / "drift_live_ollama" / c / "build.json").read_text())["tokens"]
        ratio.append(dt / ot)
        labels.append(f"{c}\n({len(q)} of {len(ours)} queries)" if len(q) < len(ours) else f"{c}\n({len(q)} queries)")
    joins = json.loads((EXP / "E9-query-types" / "summary.json").read_text())["player"]["joins"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2), gridspec_kw={"width_ratios": [1.6, 1]})
    ax = axes[0]
    w = 0.36
    xs = range(len(CORPORA))
    ax.bar([x - w / 2 for x in xs], ours_m, width=w - 0.03, color=BLUE, label="Ours (build + on-demand patches)")
    ax.bar([x + w / 2 for x in xs], doc_m, width=w - 0.03, color=ORANGE, label="DocETL")
    for x, r, o in zip(xs, ratio, ours_m):
        ax.annotate(f"{r:.0f}× fewer tokens", (x - w / 2, o), xytext=(0, 3), textcoords="offset points", ha="center",
                    fontsize=8, color=INK2)
    ax.set_xticks(list(xs), labels, fontsize=9)
    ax.set_ylim(0, max(ours_m) * 1.25)
    ax.set_ylabel("Score at 100% drift")
    ax.legend(loc="upper right")
    ax.set_title("All corpora")
    style(ax)
    ax = axes[1]
    groups = ["0 joins", "1 join", "2+ joins"]
    a = [joins[g]["adaptive_100"] for g in groups]
    b = [joins[g].get("docetl", 0) for g in groups]
    ax.bar([x - w / 2 for x in range(3)], a, width=w - 0.03, color=BLUE)
    ax.bar([x + w / 2 for x in range(3)], b, width=w - 0.03, color=ORANGE)
    for x, v in enumerate(b):
        ax.annotate(f"{v:.3f}", (x + w / 2, v), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8.5)
    ax.set_xticks(range(3), [f"{g}\n(n={joins[g]['n']})" for g in groups], fontsize=9)
    ax.set_ylim(0, max(a) * 1.25)
    ax.set_title("Player by number of joins")
    style(ax)
    save(fig, "docetl.png", "Ours is more accurate than DocETL on every corpus at 7–25× fewer tokens",
         "Same model and drift queries. DocETL's accuracy collapses on joins.")


if __name__ == "__main__":
    for fn in (rq1_drift, rq1_seeds, rq1_train, rq1_anticipation, rq2_width, rq3_legal, rq3_policies, rq4_signals, rq5_planner, rq6_cells,
               rq7_models, rq8_bottleneck, rq8_form, docetl):
        fn()
