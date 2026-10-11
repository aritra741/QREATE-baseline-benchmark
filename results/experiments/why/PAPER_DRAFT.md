---
title: "A database built by an LLM is a set of measurements: a catalogue of what each column's reads depend on, and a planner that uses it"
---

Draft 2026-10-11. The evaluation is the V3 family (`V2/summary.json`, `WHY_AUDIT.md`); every other number is
measured (KEY_FINDINGS_WHY.md, RESEARCH_DEPTH.md §8–9). Figures are those of the key-findings document.

# 1. Introduction

A system that builds a database from documents with an LLM reads each document once for the columns its known
workload uses, then answers queries over the table. When the workload drifts, later queries need columns the build
never read, and the system extracts them on demand. Every such system, ours included, carries an assumption from
relational databases that turns out to be false: that reading a value twice gives the same value.

**Reads are not idempotent.** The value an LLM extracts for a cell is a function of the document *and of the prompt
the question was asked in*. Asking a column together with different other columns changes 37% to 42% of its cells;
asking the same columns in another order changes 40% to 44%; running the same prompt twice changes 5% to 6%. How
much a column moves is a property of the column, not of the prompt: the ranking of columns by this sensitivity is
the same under every kind of change we tried (Spearman 0.82 to 0.93), the same for a 7B and a 32B model (0.77),
and the same inside another extraction system (DocETL, −0.73 between our sensitivity and its accuracy). Sensitivity
predicts a column's accuracy at about −0.7 in every model and system we measured, and it is measurable from ten
documents without any labels.

The data-management consequences are concrete. A stored value must carry the prompt it came from, or a column will
mix values from different measurements. Join keys must be extracted once, with one definition, or 75% of rows lose
their partner (18% to 19% match when keys are extracted per query). The unit of extraction, meaning what one prompt
asks for, moves the tokens a given accuracy costs by three- to tenfold, while the scheduling policy moves the score
by 0.01. And a wrong cell is wrong for one of two reasons: the document under-determines it, which no reader
repairs, or the reader misread it, which a stronger reader repairs; the first is visible without labels, the second
is a column property that ten labelled cells reveal.

This paper turns these measurements into a system. Before a column is read for a corpus, a **catalogue** records,
from a probe of ten documents, how far the document determines it, where its values sit, whether it is a coded
absence, how its fill depends on company, and, given ten labelled cells, how often a stronger reader repairs it. A
**planner** consumes the catalogue to decide the unit of extraction, the window each prompt reads, which columns
get a prompt of their own, which vocabulary is declared, and where second looks by a stronger reader are worth
their price. The catalogue is to this system what cardinalities and selectivities are to a relational planner:
cheap statistics, computed once, that are not a model.

On five corpora at full drift the planner holds the recorded system's score within its run-to-run spread on three
corpora and within 0.015 on the other two, at 27% to 89% of the recorded system's reader tokens, and one to two
orders of magnitude below DocETL on both score and tokens; under a budget of a quarter of the recorded spend it
scores 0.344 against 0.176 on players, 0.202 against 0.179 on artists and 0.160 against 0.098 on court judgments,
because it reads a table once and keeps what it read. Each component's ablation lands where the measurements of
Section 2 predict it, and where it does not (medical), the decomposition of Section 5.3 shows variance, not the
component.

Our contributions are (1) the principle, measured and decomposed into its sources, with the properties that make
it usable (per column, cross-model, cross-system, label-free); (2) the catalogue; (3) the planner, each decision
tied to a measured mechanism, including what it deliberately does not do and why; (4) findings that transfer beyond
this system (Section 7), each tested by an intervention with its prediction written first.

# 2. Reads are not idempotent

## 2.1 Three sources of variation

We take five corpora (research papers, basketball players, artists, medical documents, court judgments), a workload
of SQL queries over each, and a drift design in which a share of the columns the test queries need is withheld
from the build. The reader is Qwen 2.5 7B at 4 bits; a 32B model serves as the stronger reader. A query's score is
the product of a structure score and a cell score.

*Context.* For every column the drifted workload needs and the build lacks, thirty documents were read in five
contexts: the column alone, with two random columns of its table, with six, in the build's natural group, and alone
with a paraphrased description (39 columns, 5,005 prompts). The mean accuracy is the same in every context (0.37 to
0.41); the direction of the effect is each column's own, 18 columns more accurate alone by 0.05 or more and 9 less.
Then the same fields in another order: shuffling changes 40% of cells, reversing 44%, as much as adding six columns;
a "never null" count is left empty on 87% of documents when it heads the list and 47% when it closes it; a category
whose gold is mostly empty is filled with 'Other' first and left empty last (0.20 against 0.77 correct). Context is
not a semantic interaction among fields; it is the prompt's arrangement.

*Model.* The 32B model is barely less sensitive than the 7B on average (0.38 against 0.39), more sensitive on 13 of
39 columns, and ranks the columns the same way (0.77).

*Sampling.* With a fixed temperature the same prompt changes 5% to 6% of cells between runs; DocETL, which sets no
temperature, returns the same value 69% to 100% of the time.

*Why the arrangement changes the value.* Two hypotheses: the model answers fields in prompt order (it does, 96% of
responses) and conditions each answer on the ones before it; or some documents under-determine many fields at once
and any perturbation re-samples them all. A field's flip rate is 0.40 when only earlier fields flipped and 0.37 when
only later ones did, 0.48 when the document flipped on both sides and 0.12 when it flipped nowhere else, with no
gradient by position. The arrangement effect is mostly the document's: the value of an under-determined cell is a
draw, the prompt is one of the things that re-draws it, and the document decides how many cells are draws. The
sequential part adds a few points in the forward direction.

## 2.2 Determinacy

The disagreement between two prompts on a column predicts the column's accuracy: −0.76 over 41 columns in the
recorded runs, −0.71 on the intervention's 39, −0.73 for DocETL's accuracy on the same columns, −0.63 for DocETL's
own two-query disagreement against its own accuracy. Ten sampled documents give almost the full ranking (−0.66
against −0.72). Cell by cell, a disagreeing cell is wrong 79% of the time and an agreeing one 44%. The signal fails
in one informative place: on category columns both prompts choose the same coarse label, so agreement is not
evidence of correctness, which is a shared bias no reader repairs. Whether the gold value is stated verbatim in the
document makes no difference to disagreement (48.6% against 48.8%): under-determination is about selection and
rendering, not reading.

## 2.3 Two kinds of error, and where repair is possible

A 32B second look at 1,719 cells the 7B had served repaired determined cells the 7B had misread (dates in another
format: 73% to 84% repaired) and left under-determined cells as they were. A label-free verifier built from
grounding, disagreement, emptiness and sensitivity predicts whether a cell is wrong at AUROC 0.85 and transfers
across corpora (0.75 to 0.89); used to route 600 second looks it selects cells that are wrong 99% of the time, of
which the 32B repairs 13%, against 32% of random's. The same features predict "wrong and repaired" at 0.53. What
predicts repair is the column: net repair rates range from −0.67 to +0.56 per look, and estimating them from ten
labelled cells per column routes 600 looks to 189 net fixes against 59 for random, 402 per dollar against 123.
What the stronger reader repairs is mostly restraint and precision: 38% of its repairs are lists from which it drops
items the document does not state, 21% dates it writes in full where the weaker reader wrote the year, 10% form;
a different fact is 20%. That is why repair is a column property, and why most of it is available without the
stronger reader (Section 4.5).

## 2.4 What a store must do

Key values by their prompt, and treat a re-read as a new measurement. Freeze a canonical prompt as a byte string,
order included. Extract join keys once. Choose the context a column is frozen on by how well it determines the
column (its fill), not by which query came first: applied inside DocETL, this holds its accuracy within 0.01 on
three corpora at 13% to 45% of the tokens, and on players lifts it from 0.108 to 0.145–0.164 with joins from 0.022
to 0.029–0.055.

# 3. The catalogue

For each column, computed before the column is read for the corpus, from a probe of ten documents (each column
alone, then in its frozen group):

| statistic | what it is | what it decides |
|---|---|---|
| kind | number, yes/no, category, list, free text (schema) | exemptions |
| sensitivity | share of probe documents whose value changes between alone and group | which cells not to trust; reporting |
| fill alone, fill in group | share of documents answered | the determined context (the fill rule) |
| grounding | share of lone values stated verbatim in the document | the absence test |
| position | farthest stated value, as a share of the document | the window |
| absence-coded | stated values in fewer than a third of filled cells | window exemption |
| vocabulary | a declared label set, when the schema supplies one | allowed values (never for lists) |
| cost per document | tokens | every cost decision |
| repair rate | net repairs by the stronger reader on ten labelled cells (optional) | second-look routing |

The probe costs ten lone reads per column plus the group reads of ten documents, which the extraction reuses.
Everything but the repair rate needs no labels.

# 4. The planner

## 4.1 The unit of extraction

On a table's first on-demand request the planner reads *every remaining schema column of the table* for the
documents the query can select, in frozen prompts of at most sixteen fields, and keeps everything it read. The cost
lemma justifies the anticipation: an extra column costs 1% to 13% of a separate read, far below the probability
that a schema column is needed under drift. There is no reuse history to forecast from, so extraction is first come,
first served; a policy that forecasts reuse loses 0.011 on average with no wins (Section 6), and pacing cannot
afford a frozen prompt's indivisible spend. Columns the whole-document group under-fills, filled on at least 30% of
the probe documents alone, on fewer than half as many in the group, with their lone values mostly stated in the
document, get a prompt of their own: a narrow group if that prompt restores their fill, otherwise each alone. This
is the fill rule that fixed DocETL, applied per column before the corpus is read. With twenty probe documents the
rule fires on one medical column (`drug.manufacturer`) and on none of the other corpora; with ten it fired on two
papers columns in one run and none in another, which is the instability of Section 6.

## 4.2 Windows

Columns whose stated values sit in the first third of a document form a head prompt cut at their largest share;
everything else reads the whole document. Lists are exempt (items scatter), and so are coded absences: a window can
locate a stated value but cannot establish an absence, and a "0 if none" count read from a cut entry is left empty
on 79 of 133 players. Windows and grouping are planned together, because a prompt takes the largest share of its
columns, and an exemption propagates through the group: artists' birth date gained 0.41 in a prompt whose columns
were all windowed and lost it when a list joined the prompt.

## 4.3 Vocabulary

A declared label set is a schema input. Where one exists for a single-valued column, the planner lists it as the
column's allowed values: it fixes form, not selection (artists' century: "own label in another form" from 50% to
6%, exact from 27% to 52%, merged from 23% to 43%; the six grouping queries from 0.22 to 0.35; legal from 0.170 to
0.269 in two runs). For list columns an allowed list invites selection and the column gets worse, so lists never
get one. The workload's constants are examples of form, not a vocabulary; declaring them alone has no measurable
effect.

## 4.4 Second looks

With ten labelled cells per column the planner asks the stronger reader for them, takes the net repair rate, and
spends a budget of 25% of the extraction's tokens, at the stronger reader's price, on the columns with a positive
rate, cheapest documents first. It does not route by a cell-level verifier, which finds wrong cells and not
repairable ones.

## 4.5 The item filter

A list keeps only the items stated verbatim in the document. Of what a stronger reader repairs, 38% are lists to
which the weaker reader added items the document does not state, and the check does that repair without a model:
on the recorded run's 11,001 list cells, 0.250 to 0.299, 146 of 192 of the 32B's fixes on the second-look pool
with 4 breaks against its 17. The check hurts where unstated items are paraphrased truths (a nationality for a
country, a domain label), and the probe tells the two apart without labels: an invented item is unstable across
contexts, a paraphrased truth is stable; the filter is switched on per column where unstated items are mostly
unstable, which keeps the gains and removes every losing column.

## 4.6 Normalization and scope

Values are committed in the forms the workload compares (0.13 on players, 0.07 on artists), and on-demand reads
cover only the documents a query's filter can select (up to 46% of the tokens).

# 5. Evaluation

## 5.1 Setup

Five corpora (research papers, 200 documents; basketball players, 200 across four tables; artists, 1,000; medical,
297 across three tables; court judgments, 570), the same test queries as the earlier sections (59, 118, 43, 43 and
27), Qwen 2.5 7B at 4 bits as the reader and Qwen 2.5 32B as the stronger reader, both local. The recorded system is
the one the earlier sections measured: the W0 build, then on demand one prompt per query's missing columns. The
planner (V3) probes twenty documents per table, freezes its prompts, routes second looks by repair rates from twenty
labelled cells with three net repairs required, and applies the item filter where the probe switches it on. Every
run is a replay clone of the recorded run, so the build is identical and only on-demand reads are paid; a second
run of the planner on every corpus gives the run-to-run spread; tokens are counted for the 7B and the 32B
separately. A query's score is structure times cell accuracy as before.

## 5.2 At full drift

| corpus | recorded | planner (two runs) | 7B tokens, planner / recorded | 32B tokens | DocETL (score, tokens) |
|---|---|---|---|---|---|
| papers | 0.153 | 0.138, 0.136 | 0.52M / 1.16M | 0.20M | 0.122, 45.6M |
| players | 0.387 | 0.377, 0.374 | 5.02M / 5.67M | 1.25M | 0.108, 316M |
| artists | 0.256 | 0.255, 0.250 | 2.33M / 6.08M | 0.21M | 0.188, 74M |
| medical | 0.115 | 0.107, 0.098 | 7.11M / 14.08M | 2.91M | 0.099 |
| court judgments | 0.170 | 0.178, 0.168 | 5.33M / 19.77M | 0.52M | 0.046 |

The planner keeps the recorded accuracy on artists, medical and court judgments (differences inside the two-run
spread of 0.005 to 0.010) and loses 0.015 on papers and 0.010 on players, whose spreads are 0.002 and 0.003. Its
reader tokens are 27% of the recorded system's on court judgments, 38% on artists, 45% on papers, 50% on medical and
89% on players; the stronger reader adds 0.2M to 2.9M, so on players the planner with second looks spends more in all
than the recorded system (6.3M against 5.7M) for 0.011 of score, and the second looks are the component to switch
off there. DocETL, which extracts per query, is below the planner on every corpus by 0.016 to 0.27 at 8 to 60 times
the tokens (its medical and legal runs were not re-costed).

## 5.3 Ablations

Score at full drift with one component off, and the reader tokens where the component changes them:

| corpus | planner | no unit decision (tokens) | no second looks | no item filter |
|---|---|---|---|---|
| papers | 0.138 (0.52M) | 0.145 (1.49M) | 0.129 | 0.135 |
| players | 0.377 (5.02M) | 0.387 (7.57M) | 0.366 | 0.370 |
| artists | 0.255 (2.33M) | 0.262 (6.90M) | 0.257 | 0.260 |
| medical | 0.107 (7.11M) | 0.113 (17.20M) | 0.078 | 0.138 |
| court judgments | 0.178 (5.33M) | 0.170 (20.45M) | 0.167 | 0.168 |

*The unit decision* (every remaining column of a table in frozen prompts at first touch) is what cuts the tokens,
by 1.5 to 3.8 times, at a cost of 0.006 to 0.010 on four corpora and a gain of 0.008 on court judgments. *Second
looks* add 0.009 on papers, 0.011 on players and court judgments, 0.029 on medical, and nothing on artists; the
column-rate router spends them where the per-cell repair rate is high, and Section 2.3 says why that is not the
same as where queries gain. *The item filter* adds 0.003 to 0.010 on four corpora and appears to cost 0.031 on
medical; there, however, the three medical runs' final tables differ by 0.01 in score while the streams differ by
0.06, because medical patches two tables at different queries and each query sees the table of its time, so the
medical ablation is within the run-to-run and timing variance and no component claim is made for it (WHY_AUDIT.md
§7). The decomposition of Section 2 gives the mechanism for the small losses on papers and players: the cells the
planner changes are more often right, but a cell that turns from right to wrong on a grouping or filter column costs
two to four times what a cell that becomes right earns.

## 5.4 Drift and budget curves

At 50% drift the planner scores 0.145, 0.379, 0.260, 0.111 and 0.205 against the recorded 0.147, 0.390, 0.267,
0.117 and 0.174, at 81%, 97%, 57%, 73% and 75% of the reader tokens; at 0% both are the build. Under a budget,
first come first served with the budget set to 25% and 50% of the recorded system's unlimited spend:

| corpus | 25%: planner / recorded | 50%: planner / recorded |
|---|---|---|
| papers | 0.150 / 0.137 | 0.138 / 0.147 |
| players | 0.344 / 0.176 | 0.366 / 0.293 |
| artists | 0.202 / 0.179 | 0.254 / 0.191 |
| medical | 0.075 / 0.079 | 0.085 / 0.104 |
| court judgments | 0.160 / 0.098 | 0.160 / 0.146 |

The budget curve is where the unit decision shows: with a quarter of the spend the planner has already read each
touched table once and answers the rest of the stream from it, while the recorded system is still paying per query
(players 0.344 against 0.176, court judgments 0.160 against 0.098). Medical is the exception at both budgets, for
the reason of Section 6: its frozen reads are large and indivisible, and a budget that cannot afford one loses the
table's columns altogether.

## 5.5 Cost

In the OpenRouter list prices of the two models, the planner's full-drift runs cost $0.07 (papers), $0.50 (players),
$0.26 (artists), $1.0 (medical) and $0.58 (court judgments) against the recorded system's $0.12, $0.57, $0.61, $1.41
and $1.98, and DocETL's $4.6 and $32 on the two corpora costed. The dollar amounts are small and the ratios are
what matter: the planner is the cheapest system on every corpus but players, where its second looks are not worth
their price.

# 6. What the planner's failures teach

Each was tried, with its prediction written first, and failed for a stated reason.

- *Forecasting reuse* loses to first come, first served (−0.011, 0 wins of 10 streams) because under column drift
  the columns in demand are those no known query uses: the first request is itself the best predictor of reuse.
- *Pacing* loses 0.034 with frozen prompts because a frozen prompt is one indivisible spend; with per-query prompts
  it is a wash. The unit of extraction decides which policies are admissible.
- *Grouping for accuracy*: the per-column context effect transfers from thirty documents to the full build (+0.14
  on the flagged columns) and the query score does not move, because the cell changes are form and emptiness,
  which aggregates and filters reward inconsistently, and a column alone costs a document.
- *A label-free verifier as the router of second looks* detects under-determination, which no reader repairs.
- *Windows* cannot establish an absence; *vocabularies* for lists invite selection.
- *A layout rule* for field order does not exist: last beats first by 0.046 on average, but the share of empty gold
  does not predict the direction; position is a per-column knob the probe can set.

# 7. Findings that generalize

1. An LLM read is a measurement: its value carries its prompt, model and sample. Caches, views and pipelines that
   key values by document and column mix measurements.
2. Determinacy is a column property, measurable from ten documents without labels, that predicts accuracy across
   models and systems and marks the cells no reader will fix.
3. Repairability is a column property too, invisible to label-free features and visible to ten labels per column;
   a cascade should be budgeted in tokens and routed by column.
4. The unit of extraction, not the schedule, moves cost; forecasts need history that drift withholds; smooth
   spending rules break on indivisible reads.
5. Consistency of a value across its uses matters more to joins and grouping than the accuracy of any one read.
6. A read window locates stated values and cannot establish an absence; windows and grouping are one decision.
7. A vocabulary fixes form, not selection; label collapse is mostly a mapping judgment under a declared vocabulary.
8. The first field line of a prompt is answered differently from the rest, by up to 0.6 per column.

# 8. Related work

Semantic query processing and LLM-built tables (LOTUS, Palimpzest, DocETL, ZenDB, Evaporate, UQE, QUEST), where
extraction is per query or per operator and values are not keyed by their prompt; workload-aware and robust physical
design (CliffGuard), which the unit decision follows in spirit; model cascades with proxy scores and oracle budgets
(SUPG, LOTUS), which our column-rate router refines and which our verifier result bounds; prompt sensitivity in NLP
(Sclar et al.; self-consistency), whose finding we give a per-column, cross-system, label-free form with
data-management consequences; prefix-sharing and KV-cache reordering (Liu et al.), which our order result turns into
a correctness constraint; incremental extraction and knowledge-base refresh (Cyclex, DeepDive), which get a new rule
for what to recycle.

# 9. Limitations

One model family at 4 bits for the reader and the stronger reader; one benchmark family with our own drift splits;
the labelled sample the second-look router needs; low absolute scores, and query sets of 27 to 118 where filtered
aggregates over few rows flip on single cells, so every delta is reported against a measured run-to-run floor.
