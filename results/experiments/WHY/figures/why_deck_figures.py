"""Charts for the why-story deck (2026-10-14). One message per chart; bars at 20% tolerance, a black tick at 0% (exact).

Numbers come from: WHY/swap/realistic_<c>.json (by_tau), WHY/arms/results.json, WHY/arms/cost_passes.json,
WHY/docetl_optimizer/comparison.json + full_system_haiku.json, WHY/conflict/summary.json, results/conflict_agent/*
(three agent runs), and the DocETL players run stats (drop rate by length; droplen.json, made by droplen.py).

    ~/venvs/quwarts/bin/python results/experiments/WHY/figures/why_deck_figures.py <out_dir> <font_dir> <droplen.json>
"""

from __future__ import annotations

import json
import statistics as S
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

WHY = Path(__file__).resolve().parents[1]
REPO = WHY.parents[2]
OUT, FONTS, DROPLEN = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)
for f in FONTS.glob("*.ttf"):
    font_manager.fontManager.addfont(str(f))
plt.rcParams.update({"font.family": "IBM Plex Sans", "font.size": 20, "axes.edgecolor": "#8A96A3", "axes.labelcolor": "#3E4957",
                     "xtick.color": "#3E4957", "ytick.color": "#3E4957", "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": "#F7F5F0", "axes.facecolor": "#F7F5F0", "savefig.facecolor": "#F7F5F0"})
OURS, DOC, GREY, INK, LIGHT = "#2A6FB0", "#D9822B", "#A3ADB8", "#1B2430", "#9CC0E3"
T = ["0%", "5%", "10%", "20%"]


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=200, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def label_bars(ax, bars, fmt="{:.2f}", color=INK, inside=False, size=20):
    for b in bars:
        v = b.get_width() if b.get_width() > 0 and b.get_height() < 1.5 and ax.name == "rectilinear" and getattr(ax, "_horiz", False) else b.get_height()
        ax.annotate(fmt.format(v), (b.get_x() + b.get_width() / 2, v), xytext=(0, 6), textcoords="offset points", ha="center",
                    va="bottom", fontsize=size, color=color, fontweight="semibold")


def tick0(ax, xs, vals, width):
    for x, v in zip(xs, vals):
        ax.plot([x - width / 2, x + width / 2], [v, v], color=INK, lw=3, solid_capstyle="butt")


# 1. headline: score and tokens per collection ------------------------------------------------------------------
cols = [("player", "Players"), ("med", "Medical"), ("legal", "Court\ncases"), ("art", "Artists"), ("cspaper", "Papers")]
sw = {c: json.loads((WHY / "swap" / f"realistic_{c}.json").read_text())[c]["by_tau"] for c, _ in cols}
cost = {r["corpus"]: r for r in json.loads((WHY / "arms" / "cost_passes.json").read_text())}
fig, (a1, a2) = plt.subplots(1, 2, figsize=(16, 6.2), gridspec_kw={"wspace": 0.28})
x = range(len(cols))
w = 0.38
b1 = a1.bar([i - w / 2 for i in x], [sw[c]["20%"]["docetl"] for c, _ in cols], w, color=DOC, label="DocETL")
b2 = a1.bar([i + w / 2 for i in x], [sw[c]["20%"]["ours"] for c, _ in cols], w, color=OURS, label="Our system")
tick0(a1, [i - w / 2 for i in x], [sw[c]["0%"]["docetl"] for c, _ in cols], w)
tick0(a1, [i + w / 2 for i in x], [sw[c]["0%"]["ours"] for c, _ in cols], w)
label_bars(a1, b2)
a1.set_xticks(list(x), [n for _, n in cols], fontsize=19)
a1.set_ylim(0, 0.7)
a1.set_title("Query score (higher is better)", fontsize=22, color=INK, loc="left", pad=14)
a1.legend(frameon=False, fontsize=19, loc="upper right")
b3 = a2.bar([i - w / 2 for i in x], [cost[c]["docetl_tokens"] / 1e6 for c, _ in cols], w, color=DOC)
b4 = a2.bar([i + w / 2 for i in x], [cost[c]["ours_tokens"] / 1e6 for c, _ in cols], w, color=OURS)
for b in b4:
    a2.annotate(f"{b.get_height():.0f}M" if b.get_height() >= 1 else f"{b.get_height():.1f}M", (b.get_x() + b.get_width() / 2, b.get_height()),
                xytext=(0, 6), textcoords="offset points", ha="center", fontsize=17, color=OURS, fontweight="semibold")
for b in b3:
    a2.annotate(f"{b.get_height():.0f}M", (b.get_x() + b.get_width() / 2, b.get_height()), xytext=(0, 6), textcoords="offset points",
                ha="center", fontsize=19, color=INK, fontweight="semibold")
a2.set_xticks(list(x), [n for _, n in cols], fontsize=19)
a2.set_title("Tokens used (lower is better)", fontsize=22, color=INK, loc="left", pad=14)
a2.set_ylim(0, 112)
save(fig, "headline")

# 2. waterfall for players ----------------------------------------------------------------------------------------
p = sw["player"]["20%"]
steps = [("DocETL", 0, p["docetl"], DOC), ("+ lost\ndocuments", p["docetl"], p["rows"], OURS), ("+ empty\ncells", p["rows"], p["empty"], OURS),
         ("+ wrong\nvalues", p["empty"], p["values"], OURS), ("= our system", 0, p["ours"], INK)]
fig, ax = plt.subplots(figsize=(13, 6.2))
for i, (n, lo, hi, c) in enumerate(steps):
    ax.bar(i, hi - lo, 0.62, bottom=lo, color=c)
    lab = f"{hi:.2f}" if lo == 0 else f"+{hi - lo:.2f}\n({sw['player']['20%']['share_of_gap'][('rows', 'empty', 'values')[i - 1]]:.0%} of gap)"
    ax.annotate(lab, (i, hi), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=21, color=INK, fontweight="semibold")
    if 0 < i < 4:
        ax.plot([i - 1 + 0.31, i - 0.31], [lo, lo], color=GREY, lw=1.5, ls=":")
ax.set_xticks(range(5), [s[0] for s in steps], fontsize=20)
ax.set_ylim(0, 0.72)
ax.set_ylabel("Mean query score, players", fontsize=20)
save(fig, "waterfall")

# 3. drop rate by document length -----------------------------------------------------------------------------------
dl = {int(k): v for k, v in json.loads(DROPLEN.read_text()).items()}
ks = sorted(dl)
fig, ax = plt.subplots(figsize=(14, 6.2))
rates = [dl[k][1] / dl[k][0] for k in ks]
bars = ax.bar(range(len(ks)), rates, 0.75, color=[GREY if k < 14 else DOC for k in ks])
for i, (b, k) in enumerate(zip(bars, ks)):
    ax.annotate(f"{rates[i]:.0%}", (b.get_x() + b.get_width() / 2, rates[i]), xytext=(0, 5), textcoords="offset points", ha="center",
                fontsize=17, color=INK)
ax.set_xticks(range(len(ks)), [f"{k}k" if k < 24 else "24k+" for k in ks], fontsize=18)
ax.set_xlabel("Document length in tokens (start of each 2,000-token band)", fontsize=20)
ax.set_ylabel("Documents lost", fontsize=20)
ax.set_ylim(0, 1)
ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
ax.axvline(6.5, color=INK, lw=2, ls="--")
ax.annotate("14,000 tokens", (6.55, 0.93), fontsize=19, color=INK, fontweight="semibold")
save(fig, "droplen")

# 4. QJ14 under five settings --------------------------------------------------------------------------------------------
arms = json.loads((WHY / "arms" / "results.json").read_text())
get = lambda sysn, arm, q: next(r for r in arms if r["system"] == sysn and r["arm"] == arm and r["query"] == q)  # noqa: E731
sets = [("DocETL\nas is", "docetl", "strfix", DOC), ("DocETL, less\nrandomness", "docetl", "temp01", DOC),
        ("DocETL,\ndocuments split", "docetl", "chunked", OURS), ("Our reader,\nwhole documents", "ours", "whole", OURS),
        ("DocETL,\nstronger model", "docetl", "strfix-claude-haiku-5-5", OURS)]
fig, ax = plt.subplots(figsize=(14, 6.2))
for i, (n, s, a, c) in enumerate(sets):
    r = get(s, a, "real:player#QJ14")
    ax.bar(i, r["score"]["20%"], 0.62, color=c)
    lost = r["dropped"] if r["dropped"] is not None else 0
    ax.annotate(f"{r['score']['20%']:.2f}", (i, r["score"]["20%"]), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=22,
                color=INK, fontweight="semibold")
    ax.annotate(f"{lost} of 59 lost", (i, 1.13), ha="center", fontsize=18, color=DOC if lost else "#3E4957", annotation_clip=False)
ax.set_xticks(range(5), [s[0] for s in sets], fontsize=19)
ax.set_ylim(0, 1.08)
ax.set_ylabel("Query score", fontsize=20)
save(fig, "qj14")

# 5. constant shown or hidden: false and true matches, medical Q12 ----------------------------------------------------
def fm(arm, key):
    r = get("docetl", arm, "real:med#Q12")
    a, b = r["constants"]["disease.treatments like %surgery%"][key].split("/")
    return int(a) / int(b)


fig, axes = plt.subplots(1, 2, figsize=(15, 6.2), sharey=True, gridspec_kw={"wspace": 0.12})
for ax, (title, sfx) in zip(axes, (("Small model (Qwen 7B)", ""), ("Strong model (Haiku)", "-claude-haiku-5-5"))):
    xs = range(3)
    labs = ["word shown", "word hidden", "no query"]
    f = [fm(a + sfx, "false_match") for a in ("strfix", "masked", "nosql")]
    t = [fm(a + sfx, "true_match") for a in ("strfix", "masked", "nosql")]
    bf = ax.bar([i - 0.2 for i in xs], f, 0.38, color=DOC, label="wrongly counted (of 68)")
    bt = ax.bar([i + 0.2 for i in xs], t, 0.38, color=OURS, label="rightly counted (of 21)")
    for bars in (bf, bt):
        for b in bars:
            ax.annotate(f"{b.get_height():.0%}", (b.get_x() + b.get_width() / 2, b.get_height()), xytext=(0, 5), textcoords="offset points",
                        ha="center", fontsize=18, color=INK, fontweight="semibold")
    ax.set_xticks(list(xs), labs, fontsize=19)
    ax.set_title(title, fontsize=22, color=INK, loc="left", pad=12)
    ax.set_ylim(0, 1.05)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
axes[0].legend(frameon=False, fontsize=18, loc="upper right")
save(fig, "constant")

# 6. passes over the documents per collection ---------------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(14, 6.2))
for i, (c, n) in enumerate(cols):
    d, o = cost[c]["docetl_passes"], cost[c]["ours_passes"]
    ax.bar(i - 0.2, d, 0.38, color=DOC, label="DocETL" if i == 0 else None)
    ax.bar(i + 0.2, o, 0.38, color=OURS, label="Our system" if i == 0 else None)
    ax.annotate(str(d), (i - 0.2, d), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=20, color=INK, fontweight="semibold")
    ax.annotate(str(int(o)), (i + 0.2, o), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=20, color=INK, fontweight="semibold")
    ax.annotate(f"{cost[c]['docetl_tokens'] / cost[c]['ours_tokens']:.1f}x fewer tokens", (i, -11), ha="center", fontsize=17, color=OURS,
                annotation_clip=False)
ax.set_xticks(range(len(cols)), [n for _, n in cols], fontsize=20)
ax.set_ylabel("Times every document was read", fontsize=20)
ax.set_ylim(0, 60)
ax.legend(frameon=False, fontsize=19)
save(fig, "passes")

# 7. queries with no model call under three plans ------------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(12, 5.6))
plans = [("Read a column when\na query first needs it", 32), ("+ read the expected\ncolumns first", 71), ("+ read all missing columns\nof a table together", 99)]
bars = ax.barh(range(3), [v for _, v in plans], 0.6, color=[LIGHT, OURS, INK])
for i, (_, v) in enumerate(plans):
    ax.annotate(f"{v} of 107", (v, i), xytext=(8, 0), textcoords="offset points", va="center", fontsize=22, color=INK, fontweight="semibold")
ax.set_yticks(range(3), [p[0] for p in plans], fontsize=19)
ax.invert_yaxis()
ax.set_xlim(0, 125)
ax.set_xlabel("Queries answered with no model call", fontsize=20)
save(fig, "ladder")

# 8. stronger model: 8 queries ------------------------------------------------------------------------------------------------------------
comp = json.loads((WHY / "docetl_optimizer" / "comparison.json").read_text())
full = json.loads((WHY / "docetl_optimizer" / "full_system_haiku.json").read_text())
def mean(k, t):
    return S.mean((r[k].get("score") or r[k])[t] for r in comp)
fullq = [full[r["query"].split(":")[1].split("#")[0]]["RW-haiku"]["per_query"][r["query"]] for r in comp]
rows = [("DocETL", mean("DocETL (Haiku)", "20%"), mean("DocETL (Haiku)", "0%"), "13M", DOC),
        ("DocETL + its optimizer\n(MOAR, with labels)", mean("DocETL + MOAR (Haiku)", "20%"), mean("DocETL + MOAR (Haiku)", "0%"), "34M+", DOC),
        ("DocETL + its optimizer\n(v1, no labels)", mean("DocETL + v1 (Haiku)", "20%"), mean("DocETL + v1 (Haiku)", "0%"), "281M", DOC),
        ("DocETL with our\nprompt wording", None, None, "13M", LIGHT),
        ("Our full system", S.mean(q["20%"] for q in fullq), S.mean(q["0%"] for q in fullq), "about 4M", OURS)]
ow = {}
for c_ in ("player", "med"):
    ow.update(json.loads((REPO / "results" / "docetl_arms" / "ourwords-claude-haiku-5-5" / c_ / "per_query.json").read_text()))
owq = [ow[r["query"]]["score"] for r in comp]
rows[3] = (rows[3][0], S.mean(x["20%"] for x in owq), S.mean(x["0%"] for x in owq), rows[3][3], rows[3][4])
fig, ax = plt.subplots(figsize=(14, 7))
for i, (n, v20, v0, tok, c) in enumerate(rows):
    ax.barh(i, v20, 0.6, color=c)
    ax.plot([v0, v0], [i - 0.3, i + 0.3], color=INK, lw=3)
    ax.annotate(f"{v20:.2f}   ({tok} tokens)", (v20, i), xytext=(10, 0), textcoords="offset points", va="center", fontsize=20, color=INK,
                fontweight="semibold")
ax.set_yticks(range(len(rows)), [r[0] for r in rows], fontsize=19)
ax.invert_yaxis()
ax.set_xlim(0, 1)
ax.set_xlabel("Mean query score on the 8 hardest queries, all on Haiku", fontsize=20)
save(fig, "strong")

# 9. conflict ladder on perfect values ------------------------------------------------------------------------------------------------
conf = json.loads((WHY / "conflict" / "summary.json").read_text())
cs = list(conf)
def cm(arm, t):
    return S.mean(conf[c]["arms"][arm]["mean"][t] for c in cs)
def groups(arm):
    return sum(int(conf[c]["arms"][arm]["groups_resolved_at_20"].split("/")[0]) for c in cs)
base = "ours on perfect values, stored as read, "
agent = [base + "view agent per query" + s for s in ("", " (replicate 2)", " (replicate 3)")]
lad = [("Values as stated,\nno rewriting", [base + "no view"], GREY), ("One shared form\nfor all queries", [base + "one shared view"], GREY),
       ("A form per query,\nfixed rules", [base + "one view per query"], LIGHT), ("A form per query,\nchosen by an agent", agent, OURS)]
fig, ax = plt.subplots(figsize=(14, 6.2))
for i, (n, arms_, c) in enumerate(lad):
    v20 = [cm(a, "20%") for a in arms_]
    v0 = [cm(a, "0%") for a in arms_]
    g = [groups(a) for a in arms_]
    ax.bar(i, S.mean(v20), 0.6, color=c)
    if len(v20) > 1:
        ax.plot([i, i], [min(v20), max(v20)], color=INK, lw=2)
    tick0(ax, [i], [S.mean(v0)], 0.6)
    gl = f"{min(g)} to {max(g)}" if min(g) != max(g) else str(g[0])
    ax.annotate(f"{S.mean(v20):.2f}", (i, max(v20)), xytext=(0, 10), textcoords="offset points", ha="center", fontsize=22, color=INK,
                fontweight="semibold")
    ax.annotate(f"{gl} of 20 pairs\nfully right", (i, 1.06), ha="center", fontsize=17, color="#3E4957", annotation_clip=False)
ax.set_xticks(range(4), [l[0] for l in lad], fontsize=19)
ax.set_ylim(0, 1)
ax.set_ylabel("Mean query score, correct values", fontsize=20)
save(fig, "conflict")

# 10. what is left: rule and reading ---------------------------------------------------------------------------------------------------
import re  # noqa: E402

need = {}
for c in cs:
    txt = (REPO / "Query" / "Realistic" / "conflict" / f"{c}.sql").read_text()
    forms = set(re.findall(r"^-- FORM (G\d+[ab]):", txt, re.M))
    for q in re.findall(r"^-- (G\d+[ab]):", txt, re.M):
        need[f"conflict:{c}#{q}"] = "derived" if q in forms else "stated"
def agent_mean(store, kind, t):
    vals = []
    for q, k in need.items():
        if kind and k != kind:
            continue
        c = q.split(":")[1].split("#")[0]
        vals.append(S.mean(json.loads((REPO / "results" / "conflict_agent" / (store + r) / c / "per_query.json").read_text())["per_query"][q]["score"][t]
                           for r in ("", "-r1", "-r2")))
    return S.mean(vals)
G, H = "gold-claude-haiku-5-5", "claude-haiku-5-5-claude-haiku-5-5"
pairs = [("Query needs the\nform as stated", agent_mean(G, "stated", "20%"), agent_mean(G, "stated", "0%"), LIGHT),
         ("Query needs a\nderived form", agent_mean(G, "derived", "20%"), agent_mean(G, "derived", "0%"), OURS),
         ("All queries,\ncorrect values", agent_mean(G, None, "20%"), agent_mean(G, None, "0%"), OURS),
         ("All queries,\nvalues read by Haiku", agent_mean(H, None, "20%"), agent_mean(H, None, "0%"), DOC)]
fig, ax = plt.subplots(figsize=(14, 6.2))
for i, (n, v20, v0, c) in enumerate(pairs):
    x_ = i + (0.4 if i >= 2 else 0)
    ax.bar(x_, v20, 0.6, color=c)
    tick0(ax, [x_], [v0], 0.6)
    ax.annotate(f"{v20:.2f}", (x_, v20), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=22, color=INK, fontweight="semibold")
ax.set_xticks([0, 1, 2.4, 3.4], [p[0] for p in pairs], fontsize=19)
ax.axvline(1.7, color=GREY, lw=1.5, ls=":")
ax.annotate("Error 1: the rule the SQL leaves open", (0.5, 1.04), ha="center", fontsize=19, color=INK, fontweight="semibold", annotation_clip=False)
ax.annotate("Error 2: reading the documents", (2.9, 1.04), ha="center", fontsize=19, color=INK, fontweight="semibold", annotation_clip=False)
ax.set_ylim(0, 1)
ax.set_ylabel("Mean query score, view agent", fontsize=20)
save(fig, "remaining")
print("wrote", sorted(p.name for p in OUT.glob("*.png")))

# 11. small-model ingredient ladder, players (shared read; WHY/ingredients/summary.json) --------------------------------------------
ing = json.loads((WHY / "ingredients" / "summary.json").read_text())["player"]
steps = [("DocETL,\nits wording", "L0 DocETL shared read, harness wording", DOC), ("+ our\nwording", "L1 + our wording", OURS),
         ("+ split long\ndocuments", "L2 + split documents", OURS), ("our reader\n(plain JSON)", "L3 our reader, values as read", OURS),
         ("+ commit\nstep", "L4 + our commit step", OURS), ("our full\nsystem", "our full system, as run", INK)]
fig, ax = plt.subplots(figsize=(14, 6.4))
prev = None
for i, (n, k, c) in enumerate(steps):
    v20, v0 = ing[k]["mean"]["20%"], ing[k]["mean"]["0%"]
    ax.bar(i, v20, 0.62, color=c)
    tick0(ax, [i], [v0], 0.62)
    lab = f"{v20:.2f}" if prev is None or i == len(steps) - 1 else f"{v20:.2f}\n(+{v20 - prev:.2f})"
    ax.annotate(lab, (i, v20), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=20, color=INK, fontweight="semibold")
    if "lost_documents" in ing[k]:
        ax.annotate(f"{ing[k]['lost_documents']} lost", (i, -0.075), ha="center", fontsize=17, color=DOC, annotation_clip=False)
    prev = v20
ax.set_xticks(range(len(steps)), [s[0] for s in steps], fontsize=18)
ax.tick_params(axis="x", pad=34)
ax.set_ylim(0, 0.72)
ax.set_ylabel("Mean query score, players", fontsize=20)
save(fig, "ingredients")

# 12. workload awareness: L4 vs no use lines vs every column, three collections ----------------------------------------------------
allw = json.loads((WHY / "ingredients" / "summary.json").read_text())
cols3 = [("player", "Players"), ("art", "Artists"), ("cspaper", "Papers")]
var = [("L4 + our commit step", "Workload columns,\nwith use lines", OURS), ("W1 L4 without workload use lines", "No use lines", LIGHT),
       ("W2 L4 reading every schema column", "Every column", GREY)]
fig, ax = plt.subplots(figsize=(14, 6.2))
w = 0.26
for j, (k, lab, c) in enumerate(var):
    xs = [i + (j - 1) * w for i in range(len(cols3))]
    v20 = [allw[cc][k]["mean"]["20%"] for cc, _ in cols3]
    v0 = [allw[cc][k]["mean"]["0%"] for cc, _ in cols3]
    ax.bar(xs, v20, w * 0.92, color=c, label=lab.replace("\n", " "))
    tick0(ax, xs, v0, w * 0.92)
    for x_, v in zip(xs, v20):
        ax.annotate(f"{v:.2f}", (x_, v), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=17, color=INK, fontweight="semibold")
ax.set_xticks(range(len(cols3)), [n for _, n in cols3], fontsize=20)
ax.set_ylim(0, 0.68)
ax.set_ylabel("Mean query score", fontsize=20)
ax.legend(frameon=False, fontsize=18, loc="upper right")
save(fig, "workload")
print("wrote extra", ["ingredients.png", "workload.png"])
