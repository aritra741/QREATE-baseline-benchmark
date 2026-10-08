"""Builds the findings deck (results/experiments/Findings_deck.pptx) from the result figures and numbers.

    ~/venvs/quwarts/bin/python results/experiments/deck/make_deck.py
"""

from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt, Emu

HERE = Path(__file__).resolve().parent
FIG = HERE.parent / "figures"
OUT = HERE.parent / "Findings_deck.pptx"

INK = RGBColor(0x0B, 0x0B, 0x0B)
INK2 = RGBColor(0x52, 0x51, 0x4E)
MUTED = RGBColor(0x89, 0x87, 0x81)
RULE = RGBColor(0xE1, 0xE0, 0xD9)
BLUE = RGBColor(0x2A, 0x78, 0xD6)
ORANGE = RGBColor(0xEB, 0x68, 0x34)
AQUA = RGBColor(0x1B, 0xAF, 0x7A)
YELLOW = RGBColor(0xED, 0xA1, 0x00)
STATUS = {"Conclusive": RGBColor(0x1B, 0x8A, 0x5A), "Partly conclusive": RGBColor(0xC9, 0x83, 0x00),
          "Not conclusive": RGBColor(0x8A, 0x8A, 0x8A), "Running": RGBColor(0x2A, 0x78, 0xD6),
          "Context": RGBColor(0x52, 0x51, 0x4E)}

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
W, H = prs.slide_width, prs.slide_height
BLANK = prs.slide_layouts[6]


def text(slide, x, y, w, h, paras, size=16, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """paras: list of str or (str, dict) with keys size, bold, color, bullet, level."""
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    for i, p in enumerate(paras):
        t, o = (p, {}) if isinstance(p, str) else p
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        bullet = o.get("bullet", False)
        level = o.get("level", 0)
        run = para.add_run()
        run.text = ("•  " if bullet and level == 0 else "–  " if bullet else "") + t
        run.font.size = Pt(o.get("size", size - (2 if level else 0)))
        run.font.bold = o.get("bold", bold)
        run.font.color.rgb = o.get("color", color)
        para.level = level
        para.space_after = Pt(o.get("after", 6))
    return box


def header(slide, title, subtitle=None, status=None):
    text(slide, Inches(0.5), Inches(0.22), Inches(10.6), Inches(0.85), [title], size=22, bold=True,
         anchor=MSO_ANCHOR.MIDDLE)
    if subtitle:
        text(slide, Inches(0.5), Inches(1.08), Inches(12.3), Inches(0.42), [subtitle], size=13, color=INK2)
    if status:
        tag = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(11.25), Inches(0.38), Inches(1.75), Inches(0.42))
        tag.fill.solid()
        tag.fill.fore_color.rgb = STATUS[status]
        tag.line.fill.background()
        tf = tag.text_frame
        tf.margin_left = tf.margin_right = Inches(0.03)
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = status
        r.font.size = Pt(12)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    line = slide.shapes.add_connector(1, Inches(0.5), Inches(1.5), Inches(12.83), Inches(1.5))
    line.line.color.rgb = RULE


def footer(slide, note):
    text(slide, Inches(0.5), Inches(6.95), Inches(12.3), Inches(0.5), [note], size=10, color=MUTED)


def image(slide, name, x, y, w=None, h=None):
    kw = {}
    if w is not None:
        kw["width"] = w
    if h is not None:
        kw["height"] = h
    return slide.shapes.add_picture(str(FIG / name), x, y, **kw)


def table(slide, x, y, w, rows, col_widths=None, size=12, header_fill=RGBColor(0xF1, 0xF0, 0xEC), row_h=Inches(0.36)):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), x, y, w, row_h * len(rows))
    tb = shape.table
    if col_widths:
        for i, cw in enumerate(col_widths):
            tb.columns[i].width = cw
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tb.cell(r, c)
            cell.text = ""
            cell.margin_left = cell.margin_right = Inches(0.06)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            p = cell.text_frame.paragraphs[0]
            run = p.add_run()
            run.text = str(val)
            run.font.size = Pt(size)
            run.font.bold = r == 0
            run.font.color.rgb = INK
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_fill if r == 0 else RGBColor(0xFF, 0xFF, 0xFF)
    return tb


def new(title, subtitle=None, status=None):
    s = prs.slides.add_slide(BLANK)
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = RGBColor(0xFC, 0xFC, 0xFB)
    header(s, title, subtitle, status)
    return s


def bullets(items, size=15):
    return [(t, {"bullet": True, "size": size}) if isinstance(t, str) else (t[0], {"bullet": True, "level": 1, "size": size - 1})
            for t in items]


def bar_chart(slide, x, y, w, h, categories, series, number_format='0.00', colors=(BLUE, ORANGE, AQUA, YELLOW),
              legend=True, title=None, font=11):
    cd = CategoryChartData()
    cd.categories = categories
    for name, vals in series:
        cd.add_series(name, vals)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, x, y, w, h, cd)
    ch = gf.chart
    ch.font.size = Pt(font)
    ch.has_legend = legend and len(series) > 1
    if ch.has_legend:
        ch.legend.position = XL_LEGEND_POSITION.TOP
        ch.legend.include_in_layout = False
    if title:
        ch.has_title = True
        ch.chart_title.text_frame.text = title
        ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(13)
        ch.chart_title.text_frame.paragraphs[0].runs[0].font.bold = True
    else:
        ch.has_title = False
    plot = ch.plots[0]
    plot.gap_width = 60
    plot.has_data_labels = True
    plot.data_labels.number_format = number_format
    plot.data_labels.number_format_is_linked = False
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    plot.data_labels.font.size = Pt(font - 1)
    for i, s in enumerate(plot.series):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = colors[i % len(colors)]
    va = ch.value_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = RULE
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(font - 1)
    ch.category_axis.tick_labels.font.size = Pt(font)
    return ch


# ------------------------------------------------------------------ 1 title
s = prs.slides.add_slide(BLANK)
s.background.fill.solid()
s.background.fill.fore_color.rgb = RGBColor(0xFC, 0xFC, 0xFB)
text(s, Inches(0.8), Inches(2.0), Inches(11.7), Inches(1.6),
     ["Keeping LLM-built databases accurate when the query workload changes"], size=36, bold=True)
text(s, Inches(0.8), Inches(3.6), Inches(11.7), Inches(1.6),
     ["Experiments and findings: when to extract columns up front vs on demand, how to spend a limited extraction "
      "budget, which parts of the system matter, and what it costs"], size=18, color=INK2)
text(s, Inches(0.8), Inches(5.6), Inches(11.7), Inches(0.9),
     ["Five document corpora · 290 test queries · open models served locally (Qwen 2.5 7B, Llama 3.1 8B, Qwen 2.5 32B)",
      "Status as of 7 October 2026: results marked Running are still being computed"], size=14, color=MUTED)

# ------------------------------------------------------------------ 2 context
s = new("The setting: answering SQL over documents with an LLM-built database", status="Context")
text(s, Inches(0.5), Inches(1.7), Inches(6.3), Inches(5.2), bullets([
    "An LLM reads each document and fills table columns (e.g. a player's team, draft year); SQL queries then run "
    "on these tables.",
    "Build: before any query arrives, the system reads every document once for the columns its known workload uses.",
    "Patch (on-demand extraction): when a new query needs a column the build did not read, the system reads that "
    "column then, only on the documents the query's filters can select, and keeps it for later queries.",
    "Workload drift: later queries need columns nobody anticipated. A drift level of p% means p% of the new columns "
    "were left out of the build (0% = all anticipated, 100% = none).",
    "Static build (the baseline without patching): answers every query from the build alone.",
], size=15))
text(s, Inches(7.1), Inches(1.7), Inches(5.8), Inches(5.2), [("Questions studied", {"bold": True, "size": 17})] + bullets([
    "When should a column be extracted up front, and when on demand?",
    "Is a column read more accurately when a prompt asks for fewer columns?",
    "How should a limited extraction budget be spent?",
    "Can an extraction's cost and value be predicted before running it?",
    "Does a cost-based extraction planner beat one shared extraction pass?",
    "Does the order of extractions change the answers?",
    "Do the conclusions hold across models?",
    "Where do LLM-built databases lose accuracy, and which system components matter?",
], size=14))

# ------------------------------------------------------------------ 3 setup
s = new("Data, model, metric and statistics", status="Context")
table(s, Inches(0.5), Inches(1.75), Inches(7.4), [
    ["Corpus (short name)", "Documents", "Tables", "Test queries"],
    ["Research papers (cspaper)", "200", "1", "59"],
    ["Basketball players, teams, cities (player)", "216", "4", "118"],
    ["Artists (art)", "1,000", "1", "43"],
    ["Medical: diseases, drugs, institutions (med)", "≈300", "3", "43"],
    ["Court judgments (legal)", "570", "1", "27"],
], col_widths=[Inches(4.1), Inches(1.1), Inches(0.9), Inches(1.3)], size=12)
text(s, Inches(0.5), Inches(4.15), Inches(7.4), Inches(2.8), bullets([
    "Test queries: the benchmark's queries with one column swapped for a column the build did not read "
    "(aggregates are only swapped for numeric columns); all use GROUP BY.",
    "Five drift levels (0, 25, 50, 75, 100%) and five patch budgets (10–100% of what unlimited patching spends).",
], size=13))
text(s, Inches(8.2), Inches(1.75), Inches(4.7), Inches(5.2), bullets([
    "Model: Qwen 2.5 7B Instruct, 4-bit, served locally (Ollama) unless stated.",
    "Score per query: structure F2 (right rows and groups) × cell F1 with 20% numeric tolerance (right values); "
    "averaged over queries. 1.0 = perfect answer.",
    "Differences between two systems are paired over the same queries; 95% confidence intervals by bootstrap.",
    "With these test-set sizes a query-level difference must be about 0.03–0.06 to be detectable; "
    "\"not significant\" means smaller than that, not zero.",
    "Re-running a whole stream changes its score by at most 0.002; every recorded run replays exactly from its "
    "logged model responses.",
], size=13))

# ------------------------------------------------------------------ 4 at a glance
s = new("Findings at a glance")
rows = [["Question", "Answer", "Status"],
        ["Patch on demand or build up front?", "Patching keeps accuracy under drift (static collapses); up-front reading "
         "is 2.7–5.9× cheaper. Anticipate generously, patch the rest.", "Conclusive"],
        ["Fewer columns per prompt more accurate?", "No general effect; large but unpredictable per-column effects.",
         "Conclusive"],
        ["How to spend a limited budget?", "No policy reliably beats first-come-first-served; even a hindsight plan "
         "does not.", "Partly conclusive"],
        ["Predict cost / value of an extraction?", "Cost: yes (within 1%). Value: only partly; 16% of tokens buy "
         "nothing.", "Conclusive"],
        ["Planner vs one shared pass?", "The planner never reaches a shared pass with good field descriptions.",
         "Conclusive"],
        ["Does extraction order matter?", "It changes which documents get read, not the values read.", "Conclusive"],
        ["Across models?", "Same conclusions for 3 models; the larger model is better at the same cost.",
         "Partly conclusive"],
        ["Which components matter?", "Field descriptions and value normalization for accuracy; reuse and scoping "
         "for cost.", "Partly conclusive"],
        ["Cost vs DocETL baseline", "More accurate on every corpus at 5–25× fewer tokens.", "Conclusive"]]
tb = table(s, Inches(0.5), Inches(1.7), Inches(12.3), rows, col_widths=[Inches(3.4), Inches(7.1), Inches(1.8)], size=12,
           row_h=Inches(0.5))
for r in range(1, len(rows)):
    c = tb.cell(r, 2)
    c.text_frame.paragraphs[0].runs[0].font.color.rgb = STATUS[rows[r][2]]
    c.text_frame.paragraphs[0].runs[0].font.bold = True
footer(s, "Partly conclusive: results for med and legal (budget policies, component tests, other models) are still "
          "running, or some per-corpus differences are not statistically significant.")

# ------------------------------------------------------------------ 5 drift
s = new("Patching keeps accuracy under drift; a static build collapses",
        "Score as more of the new columns are left out of the build (0% = all anticipated, 100% = none)", "Conclusive")
image(s, "rq1_drift.png", Inches(0.4), Inches(1.65), w=Inches(12.5))
table(s, Inches(0.5), Inches(4.55), Inches(7.6), [
    ["At 100% drift", "Static build", "With patching", "Difference (95% CI)"],
    ["player", "0.040", "0.387", "+0.35 (0.29 – 0.41)"],
    ["art", "0.031", "0.256", "+0.23 (0.15 – 0.30)"],
    ["cspaper", "0.008", "0.153", "+0.15 (0.09 – 0.20)"],
    ["legal", "0.005", "0.170", "+0.17 (0.10 – 0.24)"],
    ["med", "0.041", "0.115", "+0.07 (0.04 – 0.12)"],
], col_widths=[Inches(1.5), Inches(1.6), Inches(1.8), Inches(2.7)], size=12, row_h=Inches(0.34))
text(s, Inches(8.4), Inches(4.55), Inches(4.5), Inches(2.4), bullets([
    "With patching the score at 100% drift stays within 0.015 of the fully anticipated build on every corpus.",
    "Small rises (cspaper +0.019, player +0.008) are not statistically significant; the patched curve is flat.",
], size=13))

# ------------------------------------------------------------------ 6 robustness
s = new("The drift result does not depend on which columns or how much workload the build saw",
        "Left: four random choices of withheld columns. Right: build workload cut to 10–50% of its queries",
        "Conclusive")
image(s, "rq1_seeds.png", Inches(0.3), Inches(1.7), w=Inches(6.6))
image(s, "rq1_train.png", Inches(7.0), Inches(1.6), h=Inches(4.0))
text(s, Inches(0.5), Inches(5.75), Inches(12.3), Inches(1.3), bullets([
    "Static collapses every time; patching stays flat with no significant 0%→100% difference (−0.015 to +0.020).",
    "A smaller build workload leaves more columns to patching and costs 7–23% more tokens; accuracy is unchanged.",
], size=13))
footer(s, "Withheld-column draws: cspaper and player. Smaller build workloads: cspaper, player, art (med and legal: "
          "not yet re-run).")

# ------------------------------------------------------------------ 7 anticipation
s = new("Reading a column up front is 2.7–5.9× cheaper than patching it later",
        "Total tokens (build + patches) relative to a build that anticipated every column", "Conclusive")
image(s, "rq1_anticipation.png", Inches(0.4), Inches(1.65), h=Inches(4.3))
table(s, Inches(8.8), Inches(1.75), Inches(4.1), [
    ["Corpus", "Patch ÷ up front", "Break-even"],
    ["player", "3.6×", "1.3%"], ["med", "5.9×", "1.9%"], ["legal", "4.9×", "1.9%"],
    ["art", "2.7×", "12%"], ["cspaper", "2.8×", "13%"],
], col_widths=[Inches(1.3), Inches(1.5), Inches(1.3)], size=12)
text(s, Inches(8.8), Inches(4.1), Inches(4.2), Inches(2.9), bullets([
    "Break-even: anticipate a column if the chance a future query needs it exceeds this probability.",
    "Anticipating adds one field to prompts that are read anyway; a patch re-reads every document in scope.",
    "Implication: extract every plausibly useful column during the build; keep patching as the safety net.",
], size=13))

# ------------------------------------------------------------------ 8 why the patched curve moves
s = new("Why patched scores move slightly under drift: the prompt, not drift",
        "Qwen 2.5 32B, 100% drift: patches given the build's prompt, or only its grouping or only its wording",
        "Partly conclusive")
ch = bar_chart(s, Inches(0.4), Inches(1.7), Inches(7.4), Inches(4.4), ["cspaper", "player"], [
    ("0% drift (build's prompt)", (0.162, 0.401)),
    ("100% drift, patch prompt", (0.224, 0.421)),
    ("Patch with build's grouping", (0.155, 0.411)),
    ("Patch with build's wording", (0.227, 0.418))], number_format='0.000')
text(s, Inches(8.1), Inches(1.7), Inches(4.9), Inches(5.3), bullets([
    "A build asks for all of a table's new columns in one prompt; a patch asks for 1–3.",
    "Giving patches the build's exact prompt brings every query back to its 0%-drift score: drift itself and the "
    "set of documents read contribute nothing.",
    "cspaper (+0.062, significant): entirely grouping. One column (single-hop vs multi-hop reasoning) is left empty "
    "on 64% of papers when read with six others, filled on 98% when read alone.",
    "player (+0.020, significant): split between grouping and wording.",
    "With the 7B model the same shifts are too small to be significant at the query level.",
], size=13))
footer(s, "With the 7B model the direction depends on the corpus (narrow prompts help on cspaper and player, hurt on "
          "art), but no single corpus's difference is significant.")

# ------------------------------------------------------------------ 9 width
s = new("Asking for fewer columns per prompt is not more accurate in general",
        "Same 12 columns, same document sample, 1 / 3 / 6 / 12 columns per prompt", "Conclusive")
image(s, "rq2_width.png", Inches(0.4), Inches(1.65), h=Inches(4.3))
text(s, Inches(8.7), Inches(1.7), Inches(4.3), Inches(5.3), bullets([
    "One column per prompt: better on legal (+0.068) and player (+0.026), worse on art (−0.034), flat on cspaper, "
    "mixed on med, and always 6–10× the tokens.",
    "Reading each new column alone vs with 6–8 others, with identical field text: average change 0.03, none "
    "significant across 22 columns, and no column property predicts the direction.",
    "Implication: extract many columns per prompt for cost; do not narrow prompts in the hope of accuracy.",
], size=13))

# ------------------------------------------------------------------ 10 column types
s = new("Which columns are sensitive to how they are prompted",
        "Patch prompt vs build prompt, cell by cell against the gold data (48 new columns, Qwen 2.5 7B)",
        "Conclusive")
table(s, Inches(0.5), Inches(1.75), Inches(12.3), [
    ["Kind of column", "What the prompt changes", "Example"],
    ["Numbers and yes/no", "Almost nothing (at most 0.04)", "Draft pick, championships, uses an agent (yes/no)"],
    ["Descriptive text and multi-choice lists that documents often leave unstated",
     "How often the model leaves a cell empty. Narrow prompts abstain more: right where the gold data is often "
     "empty, wrong where it is filled", "Drug storage conditions: +0.43 (gold empty 82%); defendant's status: −0.18 "
     "(gold empty 10%)"],
    ["Values with several possible forms", "The form, not the fact", "Judge: \"Justice Cowdroy\" vs \"Cowdroy\"; counsel "
     "with or without the law firm; century \"20th\" vs \"20th-21st\""],
    ["Columns whose prompt line shows example values", "The examples steer form and filling",
     "Art century: example ranges in the prompt → ranges in the answers"],
], col_widths=[Inches(3.4), Inches(4.8), Inches(4.1)], size=12, row_h=Inches(0.8))
text(s, Inches(0.5), Inches(5.95), Inches(12.3), Inches(1.0), bullets([
    "Per column the effects are large and significant (art 6 of 9 columns, med 5 of 18, legal 4 of 8) but go both "
    "ways, so query-level averages barely move.",
], size=13))
footer(s, "med and legal examples come from the earlier version of their test queries; the comparison has not yet "
          "been repeated on the regenerated queries.")

# ------------------------------------------------------------------ 11 corpus effect
s = new("Corpus effect: prompt sensitivity follows how definite the values are",
        "Average change per column between patch and build prompts", "Partly conclusive")
ch = bar_chart(s, Inches(0.4), Inches(1.7), Inches(6.4), Inches(4.4), ["player", "art", "cspaper", "med", "legal"],
               [("All new columns", (0.028, 0.044, 0.032, 0.109, 0.110)),
                ("Free-text columns only", (0.041, 0.041, 0.015, 0.080, 0.110))], number_format='0.000')
text(s, Inches(7.1), Inches(1.7), Inches(5.9), Inches(5.3), bullets([
    "Med and legal are 2.5–4× as sensitive, even comparing only free-text columns.",
    "Not document length: within a corpus, the two prompts disagree as often on short documents as on long ones "
    "(med 81% vs 71% of cells).",
    "Med's and legal's columns are judgments with no canonical answer (a disease's causes, a party's status), often "
    "unstated (gold empty 27–42%) and often lists: two prompts disagree on 40–80% of cells. Player's are stated "
    "numbers: 7–13%.",
    "Not separable with five corpora: descriptive columns, frequent empty gold values and lists come together in "
    "med and legal.",
], size=13))
footer(s, "Measured on the earlier med and legal query sets; the per-column comparison has not yet been repeated on the "
          "regenerated queries.")

# ------------------------------------------------------------------ 12 budget
s = new("Spending a limited budget: no policy reliably beats first-come-first-served",
        "Mean score over 25 budget × drift settings, difference to first-come-first-served", "Partly conclusive")
image(s, "rq3_policies.png", Inches(0.4), Inches(1.75), w=Inches(7.7))
text(s, Inches(8.3), Inches(1.7), Inches(4.7), Inches(5.3), bullets([
    "Pacing (spend in step with the stream) helps on cspaper and art, hurts on player.",
    "Capping any single extraction hurts on every corpus.",
    "Skipping extractions that bought nothing (known only in hindsight) changes nothing: few did.",
    "An offline plan that knows the whole stream is not better either (−0.008 to +0.003): an extraction's cost and "
    "value depend on what was extracted before it (one chosen extraction grew from 1 to 29 documents without its "
    "predecessors).",
], size=13))
footer(s, "Three corpora. med and legal: running. Not settled: a true upper bound for budget policies and the "
          "value-per-token policies planned but not yet built.")

# ------------------------------------------------------------------ 13 predict cost / value
s = new("Cost can be predicted almost exactly; value only partly",
        "Extractions whose tokens improved no answer, by what the SQL shows (unlimited budget, all drift levels)",
        "Conclusive")
image(s, "rq4_signals.png", Inches(0.4), Inches(1.7), w=Inches(8.4))
text(s, Inches(0.5), Inches(4.6), Inches(12.3), Inches(2.4), bullets([
    "Estimated vs actual extraction tokens: median ratio 0.997–1.005 on every corpus.",
    "16% of extraction tokens improved no answer (player 0%, art 16%, legal 19%, med 33%, cspaper 39% at 100% drift).",
    "Extractions over the whole corpus (no filter in the query) hold 58% of that waste; aggregates such as AVG/SUM "
    "almost never waste.",
    "Implication: a planner can trust its cost model; whole-corpus extractions are the ones whose value to check.",
], size=13))

# ------------------------------------------------------------------ 14 planner
s = new("A cost-based planner never reaches one shared pass with good field descriptions",
        "Basketball players, 20 held-out queries", "Conclusive")
image(s, "rq5_planner.png", Inches(0.4), Inches(1.65), h=Inches(4.6))
text(s, Inches(9.6), Inches(1.7), Inches(3.4), Inches(5.3), bullets([
    "Field descriptions are worth +0.33 on one shared pass (0.234 → 0.560): the largest effect measured.",
    "The planner leaves join keys unread at small budgets and much of its budget unspent at large ones.",
    "Cause: it scores plans by agreement with each query's own extraction, so it cannot recognise a more accurate "
    "shared one.",
], size=13))
footer(s, "One corpus. Not yet done: a planner with a different objective (open).")

# ------------------------------------------------------------------ 15 order
s = new("Extraction order changes which documents are read, not the values read",
        "Cells that differ between a budget-limited and the unlimited run at the same drift level", "Conclusive")
image(s, "rq6_cells.png", Inches(0.4), Inches(1.65), w=Inches(8.4))
text(s, Inches(9.0), Inches(1.7), Inches(4.0), Inches(5.3), bullets([
    "A value is never overwritten; differences are almost all filled-vs-empty.",
    "A budget-limited run beats the unlimited one on 8–31 queries per corpus, nearly all answered without their own "
    "extraction.",
    "Reading a column for documents where it does not apply can hurt: the model invents values (82 papers given an "
    "agent framework they do not have).",
], size=13))

# ------------------------------------------------------------------ 16 models
s = new("The conclusions hold across models; the larger model is better at the same cost",
        "Patched (bars) vs static build (dashed) at 100% drift", "Partly conclusive")
image(s, "rq7_models.png", Inches(0.4), Inches(1.65), w=Inches(12.5))
table(s, Inches(0.5), Inches(5.45), Inches(8.0), [
    ["0% → 100% drift, patched", "Llama 3.1 8B", "Qwen 2.5 7B", "Qwen 2.5 32B"],
    ["cspaper", "0.149 → 0.125", "0.134 → 0.153", "0.162 → 0.224 (significant)"],
    ["player", "0.356 → 0.359", "0.379 → 0.387", "0.401 → 0.421 (significant)"],
    ["art", "0.209 → 0.203", "0.270 → 0.256", "0.293 → 0.289"],
], col_widths=[Inches(2.3), Inches(1.7), Inches(1.7), Inches(2.3)], size=11, row_h=Inches(0.3))
text(s, Inches(8.8), Inches(5.45), Inches(4.2), Inches(1.6), bullets([
    "Extraction tokens are nearly the same for every model.",
    "med and legal with the other models: not yet re-run.",
], size=12))

# ------------------------------------------------------------------ 17 accuracy loss
s = new("Where accuracy is lost: values on most corpora, structure on med",
        "Structure F2 (right rows and groups) and cell F1 (right values), with patching at 100% drift",
        "Conclusive")
image(s, "rq8_bottleneck.png", Inches(0.4), Inches(1.65), h=Inches(3.6))
text(s, Inches(8.7), Inches(1.7), Inches(4.3), Inches(5.3), bullets([
    "Med loses structure: list-valued join keys and exact comparison of free text return too few rows.",
    "The benchmark marks columns \"never null\" that its own gold data often leaves empty (19 of 59 on three "
    "corpora). Emptying exactly those cells would raise cspaper from 0.153 to 0.193.",
    "Telling the model it may leave fields empty does not recover this: it then also misses real values.",
], size=13))
text(s, Inches(0.5), Inches(5.45), Inches(8.0), Inches(1.5), bullets([
    "By query type: AVG 0.40, SUM 0.34, MIN over numbers 0.31, COUNT 0.23, MAX over numbers 0.19.",
], size=12))

# ------------------------------------------------------------------ 18 form
s = new("Many values are right in substance but wrong in form",
        "Agreement with gold, exact vs lenient (case, punctuation, list order ignored), ten columns with the largest gap",
        "Conclusive")
image(s, "rq8_form.png", Inches(0.4), Inches(1.65), h=Inches(4.3))
text(s, Inches(8.7), Inches(1.7), Inches(4.3), Inches(5.3), bullets([
    "Example: art field of work is right in substance 0.92 of the time, in exact form 0.13.",
    "Mapping values to the forms the workload uses gains nothing deterministically, and +0.003 on art with the model "
    "doing the mapping: the mismatches are in labels no query names.",
    "Dates: normalization kept only the year of \"2010/7/15\". Keeping dates as written makes art's death dates "
    "right 0.88 instead of 0.31 of the time, but raises the art score only +0.006 (one query gains).",
], size=13))

# ------------------------------------------------------------------ 19 ablations
s = new("Which components matter: one component turned off at a time",
        "Score change against the full system at 100% drift (filled = significant), and extraction tokens",
        "Partly conclusive")
image(s, "ablations.png", Inches(0.3), Inches(1.6), h=Inches(4.3))
text(s, Inches(0.5), Inches(5.95), Inches(12.3), Inches(1.0), bullets([
    "Accuracy: field descriptions (up to −0.136 without), value normalization (−0.131 on player), mapping free-text "
    "values to the workload's forms (−0.066 on art). Cost: reusing extracted columns (without it 4.9–16.9× the "
    "tokens) and limiting extraction to the documents a query selects (up to 1.46×).",
], size=13))
footer(s, "Three corpora; med and legal running. Every one of these runs was replayed exactly from its logged model "
          "responses.")

# ------------------------------------------------------------------ 20 ablations per column
s = new("What the components do, column by column", status="Conclusive")
table(s, Inches(0.5), Inches(1.75), Inches(12.3), [
    ["Component turned off", "What changes in the extracted values"],
    ["Field descriptions", "Counts left empty and dates written in another form: player FIBA World Cup appearances "
     "right 0.01 instead of 0.86; art awards 0.06 instead of 0.74"],
    ["Value normalization when values are stored", "Counts lose their \"0 if none\" value (player FIBA World Cup 0.08 "
     "instead of 0.86); but dates come out better (art death date 0.88 instead of 0.31) — two large effects that "
     "cancel on art"],
    ["Limiting extraction to the query's documents / extracting other workload columns together",
     "On art one column (nationality, read one column per prompt) gains: +0.011, not an effect of scope itself"],
    ["The workload usage phrase in the prompt", "Changes values without moving the score: art birth city right on "
     "205 more documents without it"],
], col_widths=[Inches(3.8), Inches(8.5)], size=13, row_h=Inches(0.85))
footer(s, "Cell-level comparison against the gold data, McNemar test per column with multiple-comparison correction.")

# ------------------------------------------------------------------ 21 cost
s = new("What it costs: patching is most of the cost under drift, still cents per corpus",
        "Build + all extractions per corpus; Qwen 2.5 7B at OpenRouter list price ($0.10 / $0.20 per million "
        "input / output tokens)", "Conclusive")
bar_chart(s, Inches(0.4), Inches(1.75), Inches(7.0), Inches(4.3), ["cspaper", "player", "art", "med", "legal"], [
    ("Every column anticipated (0% drift)", (0.058, 0.214, 0.339, 0.286, 0.503)),
    ("None anticipated (100% drift)", (0.160, 0.778, 0.881, 1.677, 2.456))], number_format='$0.00')
text(s, Inches(7.7), Inches(1.75), Inches(5.3), Inches(5.3), bullets([
    "At 100% drift extractions on demand are 71–85% of all tokens.",
    "Only 6–14 queries per corpus need one (the first to use each new column), at 0.2–3.9M tokens "
    "($0.02–0.33) each; every later query reuses it at no extra cost.",
    "Without reuse, on-demand extraction costs 5–17× more.",
    "DocETL on the same queries: $2.13 (cspaper) to $33.52 (legal).",
    "Other models at list price: Llama 3.1 8B about half; Qwen 2.5 32B is not listed (similar models: about the same "
    "to 7× more).",
], size=13))
footer(s, "Prices fetched 7 October 2026; local serving cost not included. Tokens are measured; builds at partial "
          "drift levels estimated within about 2%.")

# ------------------------------------------------------------------ 22 DocETL
s = new("Compared with DocETL: more accurate on every corpus at 5–25× fewer tokens",
        "Same model and queries at 100% drift; DocETL extracts per query and does not reuse extractions",
        "Conclusive")
image(s, "docetl.png", Inches(0.4), Inches(1.65), w=Inches(12.5))
text(s, Inches(0.5), Inches(5.85), Inches(12.3), Inches(1.1), bullets([
    "Significant on every corpus (e.g. med +0.044, CI 0.012–0.078; player +0.306). DocETL collapses on queries with "
    "joins (player: 0.125 / 0.034 / 0.008 for 0 / 1 / 2+ joins), likely because separately extracted join keys do not "
    "match (not verified value by value).",
], size=13))
footer(s, "legal: 21 of 27 queries (DocETL not yet run on 6 regenerated queries).")

# ------------------------------------------------------------------ 23 not conclusive
s = new("What is not conclusive yet", status="Not conclusive")
text(s, Inches(0.5), Inches(1.7), Inches(12.3), Inches(5.3), bullets([
    "Drift rises with the 7B model (cspaper +0.019, player +0.008) are below what the test sets can detect; only the "
    "32B model's rises are significant.",
    "Budget policies have no true upper bound: an extraction's cost and value depend on order, so the offline plan "
    "is a heuristic, not an optimum. Value-per-token policies are planned but not built.",
    "Corpus effect: descriptive columns, often-empty gold values and list values occur together in med and legal; "
    "five corpora cannot separate them.",
    "DocETL's collapse on joins is attributed to mismatched join keys without a value-by-value check.",
    "The planner's failure has a diagnosed cause but no tested fix.",
    "The train/test split of the workload was never redrawn (only shrunk); generality beyond five corpora and three "
    "models is untested.",
    "No comparison yet with extracting every schema column up front, the alternative that would show whether "
    "workload-aware building saves cost.",
], size=15))

# ------------------------------------------------------------------ 24 status
s = new("Status and next steps", status="Running")
text(s, Inches(0.5), Inches(1.7), Inches(6.0), Inches(5.3), [("Running now", {"bold": True, "size": 17})] + bullets([
    "med and legal: budget policies (cap, pacing, hindsight, offline plan) and component tests; finish tonight.",
], size=14) + [("Next (new compute job)", {"bold": True, "size": 17})] + bullets([
    "med and legal with the other models and with smaller build workloads.",
    "DocETL on legal's 6 regenerated queries.",
    "Baseline that extracts every schema column up front.",
], size=14))
text(s, Inches(6.9), Inches(1.7), Inches(6.0), Inches(5.3), [("Open research items", {"bold": True, "size": 17})] + bullets([
    "An upper bound for budget policies (iteratively re-priced offline plan).",
    "Value-per-token budget policies.",
    "A planner objective that can recognise a better shared extraction.",
    "Redrawn train/test splits.",
    "Turn on date-preserving normalization by default (small, safe accuracy gain).",
], size=14))

# ------------------------------------------------------------------ 25 conclusion
s = new("Conclusions")
text(s, Inches(0.5), Inches(1.7), Inches(12.3), Inches(5.3), bullets([
    "Extract on demand as a safety net, but read every plausibly useful column up front: patching keeps accuracy when "
    "the workload drifts, and anticipating is 2.7–5.9× cheaper than patching later.",
    "Most of the cost under drift is a handful of whole-corpus extractions, each paid once and reused; reuse and "
    "scoping keep it small (cents per corpus at small-model prices, 5–25× below DocETL).",
    "Accuracy is set by what the model is told and how values are stored, not by budgeting or prompt width: field "
    "descriptions and value normalization matter most; prompt grouping changes values in a corpus-specific direction.",
    "Simple budget policies and even a hindsight plan do not beat spending first-come-first-served; a planner needs "
    "an objective that estimates accuracy, not agreement with its own extractions.",
    "A larger model raises accuracy at the same extraction cost; the system-level conclusions hold across models.",
    "The benchmark itself limits scores: \"never null\" metadata that its gold data contradicts, and values judged by "
    "exact form.",
], size=16))

prs.save(OUT)
print(OUT, len(prs.slides), "slides")
