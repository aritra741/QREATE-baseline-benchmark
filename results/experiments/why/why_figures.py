"""Figures for the "Key findings and why" document (results/experiments/why/figures/).

    ~/venvs/quwarts/bin/python results/experiments/why/why_figures.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
WHY = EXP / "WHY"
OUT = HERE / "figures"
OUT.mkdir(parents=True, exist_ok=True)

BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
CORP = {"cspaper": "Research papers", "player": "Basketball players", "art": "Artists", "med": "Medical",
        "legal": "Court judgments"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "savefig.facecolor": SURFACE})


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def save(fig, name, title, subtitle=None):
    # Titles and subtitles live in the document's captions; the image itself carries none.
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=180)
    plt.close(fig)
    print(OUT / name)


def box(ax, x, y, w, h, text, color, tcolor="white", size=10.5, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02", fc=color, ec="none"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color=tcolor, fontsize=size, wrap=True,
            fontweight="bold" if bold else "normal")


# ------------------------------------------------------------------ 0 knowledge map (infographic)
def knowledge_map():
    fig, ax = plt.subplots(figsize=(11, 6.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.06)
    ax.axis("off")
    claims = [
        ("When a value is extracted does not matter;\nhow it is asked does", BLUE),
        ("Extraction cost is document tokens:\nanticipating a column is nearly free", AQUA),
        ("An extraction's value arrives later:\nbudgeting at query time cannot see it", ORANGE),
        ("Accuracy is bounded by the specification\nand by how far documents fix the value", MAGENTA),
        ("Independent extractions break joins:\nkeys must be extracted consistently", YELLOW),
    ]
    evidence = [
        "Patches given the build's prompt\nreproduce the up-front scores exactly",
        "A per-document token model predicts the\nbreak-even probability within ~30%",
        "54–97% of extraction value is realized\nby later queries that reuse the column",
        "Prompt disagreement predicts error\n(rank correlation −0.76, 41 columns)",
        "DocETL's join keys match 18–19% of the\ntime; ours 75–97% (gold 63–93%)",
    ]
    for i, ((c, col), e) in enumerate(zip(claims, evidence)):
        y = 0.83 - i * 0.185
        box(ax, 0.02, y, 0.47, 0.145, c, col, size=11, bold=True)
        box(ax, 0.54, y, 0.44, 0.145, e, "#f1f0ec", tcolor=INK, size=10)
        ax.annotate("", xy=(0.538, y + 0.0725), xytext=(0.492, y + 0.0725),
                    arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.4))
    ax.text(0.02, 1.05, "Knowledge", fontsize=11, color=INK2, fontweight="bold", va="top")
    ax.text(0.54, 1.05, "Evidence that explains why", fontsize=11, color=INK2, fontweight="bold", va="top")
    save(fig, "w0_knowledge_map.png", "Five things we now know about LLM-built databases under workload drift")


# ------------------------------------------------------------------ 1 when vs how
def when_vs_how():
    groups = ["Papers\n(7B)", "Players\n(7B)", "Artists\n(7B)", "Papers\n(32B)", "Players\n(32B)"]
    up = [0.134, 0.379, 0.270, 0.162, 0.401]
    patch = [0.153, 0.387, 0.256, 0.224, 0.421]
    build_prompt = [0.134, 0.379, 0.270, 0.162, 0.401]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    w = 0.26
    xs = range(len(groups))
    for k, (vals, col, lab) in enumerate(((up, BLUE, "Extracted up front (0% drift)"),
                                          (patch, ORANGE, "Extracted on demand, patch prompt (100% drift)"),
                                          (build_prompt, AQUA, "Extracted on demand with the build's prompt (100% drift)"))):
        bars = ax.bar([x + (k - 1) * w for x in xs], vals, width=w - 0.03, color=col, label=lab)
        for b, v in zip(bars, vals):
            ax.annotate(f"{v:.3f}", (b.get_x() + b.get_width() / 2, v), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=8.5, color=INK)
    ax.set_xticks(list(xs), groups)
    ax.set_ylabel("Score")
    ax.set_ylim(0, 0.5)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, fontsize=8.5, frameon=False)
    style(ax)
    save(fig, "w1_when_vs_how.png", "Same prompt, same answers: timing does not change extracted values",
         "On-demand extraction with the build's exact prompt reproduces the up-front score query for query.")


# ------------------------------------------------------------------ 2 cost
def cost():
    d = json.loads((WHY / "cost" / "summary.json").read_text())
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(11, 4.3), gridspec_kw={"width_ratios": [1.05, 1]})
    # left: prompt composition, one patch prompt vs the extra lines of anticipation (illustrative, measured medians)
    comps = [("Research papers", d["cspaper"]["median_document_tokens"]), ("Court judgments", d["legal"]["median_document_tokens"]),
             ("Medical", d["med"]["median_document_tokens"])]
    instr, field = 66, 84  # measured medians over all new columns: instructions, one field line + answer
    for i, (name, doc) in enumerate(comps):
        ax.barh(i, doc, color=BLUE, height=0.55, label="Document text" if i == 0 else None)
        ax.barh(i, instr, left=doc, color=MUTED, height=0.55, label="Instructions" if i == 0 else None)
        ax.barh(i, field, left=doc + instr, color=ORANGE, height=0.55, label="One field line + answer" if i == 0 else None)
        ax.annotate(f"field = {field / (doc + instr + field):.1%} of the prompt", (doc + instr + field, i), xytext=(5, 0),
                    textcoords="offset points", va="center", fontsize=9, color=INK)
    ax.set_yticks(range(len(comps)), [c for c, _ in comps])
    ax.set_xlabel("Tokens in one extraction prompt (median document)")
    ax.set_xlim(0, max(doc for _, doc in comps) * 1.55)
    ax.legend(loc="lower right", fontsize=8.5, frameon=False)
    ax.set_title("(a) Tokens in one extraction prompt", fontsize=10.5, loc="left", color=INK)
    style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID)
    # right: model vs measured break-even
    cols = {"cspaper": BLUE, "player": ORANGE, "art": AQUA, "med": MAGENTA, "legal": YELLOW}
    lo, hi = 0.008, 0.25
    bx.plot([lo, hi], [lo, hi], color=AXIS, linewidth=1, linestyle="--")
    offs = {"cspaper": (6, 4), "art": (6, -10), "player": (6, -10), "med": (-50, -14), "legal": (6, 4)}
    for c, v in d.items():
        bx.scatter(v["model_break_even"], v["measured_break_even"], s=70, color=cols[c], edgecolor=SURFACE, zorder=3)
        bx.annotate(CORP[c], (v["model_break_even"], v["measured_break_even"]), xytext=offs[c], textcoords="offset points",
                    fontsize=9, color=INK)
    bx.set_xscale("log")
    bx.set_yscale("log")
    bx.set_xlim(lo, hi)
    bx.set_ylim(lo, hi)
    bx.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    bx.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    bx.set_xlabel("Predicted by the document-token model")
    bx.set_ylabel("Measured break-even probability")
    bx.set_title("(b) Break-even probability", fontsize=10.5, loc="left", color=INK)
    style(bx)
    save(fig, "w2_cost_mechanism.png", "Why anticipating a column is so cheap",
         "Left: prompt composition at each corpus's median document length (measured medians). Right: break-even "
         "probability, predicted vs measured (dashed: equal).")


# ------------------------------------------------------------------ 3 value timing
def value_timing():
    d = json.loads((WHY / "value" / "summary.json").read_text())
    order = ["cspaper", "art", "player", "med", "legal"]
    later = [d[c]["later_share"] for c in order]
    fig, ax = plt.subplots(figsize=(9.5, 3.6))
    ys = range(len(order))
    ax.barh(list(ys), [1 - x for x in later], color=BLUE, height=0.55, label="Value to the query that triggered it")
    ax.barh(list(ys), later, left=[1 - x for x in later], color=ORANGE, height=0.55,
            label="Value to later queries that reuse the column")
    for y, x in zip(ys, later):
        ax.annotate(f"{x:.0%} later", (1, y), xytext=(6, 0), textcoords="offset points", va="center", fontsize=9.5)
    ax.set_yticks(list(ys), [CORP[c] for c in order])
    ax.set_xlim(0, 1.15)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.invert_yaxis()
    ax.legend(loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=2, fontsize=9, frameon=False)
    style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID)
    save(fig, "w3_value_timing.png", "Why budgeting at query time cannot win: the value comes later",
         "Share of each extraction's score gain realized by its own query vs later queries (unlimited budget, all "
         "drift levels).")


# ------------------------------------------------------------------ 4 determinacy
def determinacy():
    d = json.loads((WHY / "determinacy" / "summary.json").read_text())
    cols = {"number": BLUE, "yes/no": AQUA, "category": YELLOW, "free text": ORANGE}
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    for k, c in cols.items():
        pts = [r for r in d["columns"] if r["kind"] == k]
        ax.scatter([r["disagreement"] for r in pts], [r["accuracy"] for r in pts], s=55, color=c, edgecolor=SURFACE,
                   label=f"{k} ({len(pts)})", zorder=3)
    ax.set_xlabel("Disagreement between two prompts on the same document (share of cells)")
    ax.set_ylabel("Accuracy against gold")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.legend(title="Column type (columns)", fontsize=9, title_fontsize=9, frameon=False, loc="upper right")
    ax.text(0.02, 0.06, f"Rank correlation {d['spearman_disagreement_vs_accuracy']:.2f}", fontsize=10, color=INK,
            transform=ax.transAxes)
    style(ax)
    save(fig, "w4_determinacy.png", "Why some columns are hard: the document does not fix the value",
         "Each point is a column the test queries need (five corpora). Where two prompts disagree, both are usually "
         "wrong.")


# ------------------------------------------------------------------ 5 join keys
def joinkeys():
    d = json.loads((WHY / "joinkeys" / "summary.json").read_text())["by_join"]
    labels = {"player.team = team.team_name": "Player's team → team table", "team.location = city.city_name": "Team's city → city table"}
    fig, ax = plt.subplots(figsize=(9, 3.9))
    w = 0.26
    keys = list(d)
    for k, (field, col, lab) in enumerate((("gold", MUTED, "Gold data"), ("ours", BLUE, "Our build"), ("docetl", ORANGE, "DocETL"))):
        vals = [d[j][field] for j in keys]
        bars = ax.bar([x + (k - 1) * w for x in range(len(keys))], vals, width=w - 0.03, color=col, label=lab)
        for b, v in zip(bars, vals):
            ax.annotate(f"{v:.0%}", (b.get_x() + b.get_width() / 2, v), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=9)
    ax.set_xticks(range(len(keys)), [f"{labels.get(j, j)}\n({d[j]['queries']} queries)" for j in keys])
    ax.set_ylim(0, 1.12)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_ylabel("Rows whose join key finds a partner")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, fontsize=9, frameon=False)
    style(ax)
    save(fig, "w5_join_keys.png", "Why DocETL fails on joins: its join keys rarely match",
         "Basketball players, every test query that joins tables. DocETL extracts each table separately per query.")


# ------------------------------------------------------------------ 6 specification
def specification():
    cols = ["Player: FIBA World Cup\nappearances (count)", "Player: NBA\nchampionships (count)", "Artist: awards\n(count)",
            "Artist: birth date"]
    full = [0.86, 0.95, 0.74, 0.38]
    nodesc = [0.01, 0.23, 0.06, 0.00]
    fig, ax = plt.subplots(figsize=(9.5, 3.9))
    w = 0.36
    for k, (vals, col, lab) in enumerate(((full, BLUE, "With field descriptions"), (nodesc, ORANGE, "Names and types only"))):
        bars = ax.bar([x + (k - 0.5) * w for x in range(len(cols))], vals, width=w - 0.03, color=col, label=lab)
        for b, v in zip(bars, vals):
            ax.annotate(f"{v:.2f}", (b.get_x() + b.get_width() / 2, v), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=9)
    ax.set_xticks(range(len(cols)), cols, fontsize=9.5)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Share of cells correct")
    ax.legend(loc="upper right", fontsize=9, frameon=False)
    style(ax)
    save(fig, "w6_specification.png", "Why descriptions matter most: the model reads correctly when told what to write",
         "Without a description the model leaves counts empty or writes dates in another form (100% drift, same "
         "documents).")


# ------------------------------------------------------------------ 7 transfer
def transfer():
    ck = json.loads((WHY / "transfer_check" / "summary.json").read_text())
    dt = json.loads((WHY / "transfer_docetl" / "summary.json").read_text())
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(10.5, 4.0), gridspec_kw={"width_ratios": [1.15, 1]})
    kinds = [("number", "Numbers"), ("yes/no", "Yes/no"), ("list", "Lists"), ("free text", "Free text"),
             ("category", "Categories")]
    w = 0.38
    for k, (key, col, lab) in enumerate((("wrong_when_agree", BLUE, "The two prompts agree"),
                                         ("wrong_when_disagree", ORANGE, "The two prompts disagree"))):
        vals = [ck[x][key] for x, _ in kinds]
        bars = ax.bar([i + (k - 0.5) * w for i in range(len(kinds))], vals, width=w - 0.03, color=col, label=lab)
        for b, v in zip(bars, vals):
            ax.annotate(f"{v:.0%}", (b.get_x() + b.get_width() / 2, v), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=8.5)
    ax.set_xticks(range(len(kinds)), [f"{n}\n({ck[x]['cells']:,} cells)" for x, n in kinds], fontsize=9)
    ax.set_ylim(0, 1.0)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_ylabel("Share of cells wrong")
    ax.set_title("(a) Our system: cells where two prompts agree or disagree", fontsize=10, loc="left", color=INK)
    ax.legend(loc="upper left", fontsize=8.5, frameon=False)
    style(ax)
    rs = [r for r in dt["columns"] if r["quwarts_disagreement"] is not None]
    cols = {"cspaper": BLUE, "player": AQUA, "art": ORANGE, "med": MAGENTA, "legal": YELLOW}
    for c, col in cols.items():
        pts = [r for r in rs if r["corpus"] == c]
        if pts:
            bx.scatter([r["quwarts_disagreement"] for r in pts], [r["accuracy"] for r in pts], s=46, color=col,
                       edgecolor=SURFACE, linewidth=1.5, label=CORP[c], zorder=3)
    bx.set_xlim(-0.03, 1)
    bx.set_ylim(-0.03, 1.03)
    bx.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    bx.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    bx.set_xlabel("Disagreement between our two prompts")
    bx.set_ylabel("DocETL's accuracy on the same column")
    bx.set_title(f"(b) Carries over to DocETL (rank correlation {dt['spearman_quwarts_disagreement_vs_docetl_accuracy']:.2f})",
                 fontsize=10, loc="left", color=INK)
    bx.legend(loc="upper right", fontsize=8, frameon=False)
    style(bx)
    save(fig, "w7_transfer.png", "", None)


for fn in (knowledge_map, when_vs_how, cost, value_timing, determinacy, joinkeys, specification):
    fn()
transfer()
