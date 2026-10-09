# What being workload-aware is worth, what the workload tells a system that the documents do not, and which parts of the system should not be an LLM

Date: 2026-10-09. Sources: the recorded runs and ablations (`FINDINGS.md` E12, E13, E8, A3–A14), two new analyses on
the queries and the document text (`quwarts/eval/exp_workload.py`, `WHY/workload/`), and a cell-level study of
stated versus inferred values with a label-free verifier, a priced cascade and a position model
(`quwarts/eval/exp_grounding.py`, `WHY/grounding/`). No new model calls.

## 1. What the system actually takes from the workload, and what each part is worth

QuWARTS reads the reference workload (the build queries, W0) for five things. Each has been measured on its own.

**Which columns to extract.** W0 uses 9 of 21 schema columns on papers, 12 of 32 on players, 15 of 28 on artists, 17
of 52 on medical, 10 of 21 on legal (26–48%), and its demand is concentrated: the three most used columns carry 43–53%
of all column uses in W0 and the top five 65–72% (`WHY/workload/summary.json`). A workload-unaware offline system
extracts every column it can find; one that reads W0 extracts a quarter to a half of them and reads the rest on
demand. The cost side is the break-even of RESEARCH_DEPTH §3: anticipating a column costs 1–13% of extracting it
later, so cutting W0 to 10% of its queries raises total tokens by 7–23% (E12) while leaving accuracy unchanged.
*Workload awareness buys cost, not accuracy, on this axis*, and most of the cost it buys comes from the few columns
every workload leans on.

**The shape of future queries.** Every test query is a benchmark query with one column replaced by a column the
build never read, so by construction no test query's source is in W0. Yet 95% of papers' test queries, 76% of
players', and 100% of artists', medical's and legal's have the same *shape* as some W0 query (the same tables, the
same number of joins, the same aggregates, the same group-by arity), and 27–74% have the identical template down to
the filter columns. **Under 100% column drift the workload still reveals the structure of what will be asked: which
tables join on which keys, which columns group, which aggregates run.** That is what the build uses to extract join
keys once with one definition (player–team keys match 75% of rows in our build against 18–19% when extracted per
query), to derive attributes a query will compare (age from birth year), and to pick the value kind a column must
have. It is the part of the professor's prefetching analogy that holds here: the workload does not say *which* new
column will be asked, it says *how* the next query will use whatever it asks for.

**The vocabulary of values.** For each constant a query compares a column with, we checked whether the documents
whose gold value matches it contain that constant verbatim. On players they almost always do (93% of constants,
team and city names appear as such). Elsewhere they mostly do not: papers 41%, artists 40%, medical 69%, legal 57%,
and some never appear at all: artists' `color = 'Earth Tones'` (151 gold rows, never written in any document),
`century = '20th-21st'` (166 rows; documents say "mid-20th century"), legal's `case_type = 'Administrative Case'`
(344 rows; the judgments never classify themselves), papers' `use_agent = 'Yes'` (47 rows). **These are labels the
workload defines, not facts the text states, and only a system that has seen the workload can produce them in the
form a query will compare.** The usage phrase in our field specs carries such examples ("compared with specific
values, for example 'Multi-Agent Collaboration', 'Other'"); its measured effect on the score is nil (E13: −0.006 to
+0.010), but it changes values (artists' `birth_city` right on 205 more documents without it, `century` right on
252 more with the build's phrase), which says the vocabulary matters column by column in both directions, and that
example values steer form more than correctness. Canonicalizing values to the known constants after extraction
(E8) does not help either, because the vocabulary a GROUP BY needs, the set of labels gold uses, is exactly what
the workload does not name. The natural remedy is a *label contract*: the workload declares the vocabulary of the
columns it groups by. Checking it against the 47 GROUP BY columns of the test queries (`exp_contract.py`,
`I6-contract/report.json`) shows where it applies and where it cannot. 22 are read by the build and keep their
vocabulary across drift. Of the 25 read on demand, 3 already list their labels in the prompt, 17 are identifiers or
open lists (colleges, death dates, drugs, fields: 55–751 distinct values that no contract can enumerate), and 5 have
a small vocabulary the prompt does not state: artists' `century` ('19th-20th', '20th', '20th-21st'), legal's
`judgment_year` and `defendant_current_status`, medical's `recommended_usage` and `activation_conditions`. And the
columns with the largest merges (legal `case_type`, 235 administrative cases served as civil; artists'
`birth_continent`; papers' `topic`) are build columns whose prompt lists the labels. **Label collapse is mostly the
model's mapping of a passage to a declared label, not a missing vocabulary**, and that mapping is what context
sensitivity measures; a contract can fix only the few columns where no vocabulary exists (the I6 run, queued,
measures how much).

**Normalization and derived values.** Commit-time normalization, which stores numbers and absence values in the
form the workload compares ("0 if none"), is worth 0.131 on players and 0.011 on papers (E13), and the view's mapping
of free-text labels to the workload's forms is worth 0.066 on artists. These are the workload's forms applied to
the model's output; without a workload there is no target form.

**Scope.** Reading on demand only the documents a query's filters select saves up to 46% of patch tokens at no
accuracy cost (E13); the filters come from the queries.

Two things people attribute to workload awareness are not it. Field descriptions, the largest accuracy factor in
the study (−0.034 to −0.136 without them), come from the schema, not the workload, and UDA-Bench had already shown
their value for DocETL. And the drift result itself, that on-demand extraction keeps the score the static build
loses, does not depend on the workload at all (E12: identical at every train share); it depends on the prompt being
held fixed (RESEARCH_DEPTH P2).

**So how much does being workload-aware help?** On cost, by a factor: 7–25× fewer tokens than DocETL at higher
accuracy on every corpus (FINDINGS), of which the workload's column selection, scope and grouping are the largest
parts. On accuracy, through normalization to the workload's forms (0.01–0.13 depending on how numeric the corpus
is) and through consistent join keys; the headline accuracy gains over per-query systems come from consistency, which
an offline table has by construction (RESEARCH_DEPTH I3b), not from knowing the queries. The honest sentence for
the paper: *the workload tells the system what to normalize to, what to join on and what to read first; it does
not tell it what to extract, because what is asked next is exactly what has not been asked before.*

## 2. Stated or inferred: where a value comes from, cell by cell

The hypothesis was that a column is determined by the document when its value is stated in the text and
under-determined when it must be inferred, and that context sensitivity measures this. It is wrong in the simple
form and right in a more useful one.

At the column level, the share of gold values that appear verbatim in their documents does not predict sensitivity
(Spearman −0.05 over 101 columns) or accuracy (0.09). At the cell level the result is sharper: **whether the gold
value is stated verbatim makes no difference to whether two prompts disagree (48.6% when stated, 48.8% when not)**,
though stated values are extracted right more often (0.43 against 0.32). Under-determination is therefore not the
absence of the fact from the page. It is the choice the model must make even when the fact is there: which of the
mentioned items belong in a list (artists' `field`: "painting and sculpture" is in the text, and the list is right
only if the model picks exactly those), which label a passage maps to (`reasoning_depth`, `case_type`: the labels
are never in the text), and whether to leave a cell empty (26% of all cells are empty; their accuracy is 0.34, which
is the share of them gold also leaves empty). Disagreement is about selection and rendering, not about reading.

Grounding the *extracted* value, a string check with no model and no labels, does carry information, but by kind:
numbers found verbatim in the document are right 95% of the time against 73% when not; free text 64% against 39%;
categories 69% against 61% (labels are not in the text by nature, 19% grounded); lists 28% against 14%, and for
lists the decisive check is whether *every* item is stated: 36% right when all are, 0% when any item is invented.
Across the 2×2 of grounding and disagreement, agreement matters more than grounding (grounded and agreeing 0.63,
ungrounded and agreeing 0.69, grounded but disagreeing 0.20, ungrounded and disagreeing 0.11).

## 3. The parts that should not be an LLM

Your question was whether a classifier, a cascade with token accounting, and other non-LLM algorithms can make the
system cheaper, faster or more accurate, rather than treating every step as a black box. Four such components fall
out of the measurements, each with its own cost in tokens and dollars (rates: the OpenRouter prices in
`COST/summary.json`, Qwen 7B $0.10/$0.20 per million input/output tokens, Qwen 32B $0.08–0.66/$0.28–1.00).

**A label-free verifier (logistic regression) that tells which cells to trust.** Features that need no gold: is the
extracted value stated in the document, are all its items stated, do two contexts disagree, is the cell empty, how
long is the value, the column's sensitivity (from ten documents) and fill rate, and the value kind. Predicting
whether a cell is wrong: AUROC 0.85 with cross-validation by column (a column's cells never split between training
and test) and 0.75–0.89 training on four corpora and testing on the fifth (papers 0.75, players 0.83, artists 0.89,
medical 0.77, legal 0.76). Grounding alone is useless (0.44), disagreement alone 0.70; the combination with
empties and sensitivity is what works. The coefficients say what a verifier should look at: an empty cell (+3.2), a
sensitive column (+3.4), a list with an item not in the text (grounded +3.3, every item grounded −3.9, so an
invented item is the strongest single sign of a wrong list), disagreement (+1.0). This is a few hundred bytes of
model that transfers across corpora and costs nothing per cell. *It is the cascade router.*

**A cascade priced in dollars, and why the accounting changes the answer.** On the 1,719 cells the 32B re-read in
I2, routing 600 of them by six rules: counted per cell (RESEARCH_DEPTH I2) random was best; counted per dollar it is
not. Most-sensitive-first gives 66 net fixes for $0.44 (152 fixes per dollar at the high 32B rate) because the
sensitive columns live in short documents; disagreeing-first gives the most fixes, 69, for $0.62 (111 per dollar);
the classifier's ranking 65 for $0.58 (111 per dollar); random 59 for $0.63 (93 per dollar); ungrounded-first is
worst (33 for $0.58), because an ungrounded value is often an empty or a label, which the stronger model does not
settle either. **The price of a fix depends more on the length of the document than on the rule**, which is the cost
lemma again: a second look pays the document, not the field. Two consequences for the paper. First, a cascade over
documents should be budgeted in tokens, not in rows, and a router should weigh the expected fix by the document's
length; LOTUS, task cascades and Cortex budget in oracle calls. Second, the whole second-look study cost between
$0.50 and $1.40; per-query DocETL on papers spent 45.6M tokens ($4.60–9.10 at 7B rates) against 3–6M for the
frozen variants ($0.30–0.60); the cost differences this work measures are factors of ten, and the dollar amounts
are small enough that *accuracy per dollar*, not dollars, should be the reported quantity.

**A position model: how much of a document a column needs.** For each column, the relative position in the
document of the stated gold value: on players 90% of stated values sit within the first 18.5% of the document and
12 of 13 columns need only the first half (an encyclopedia entry states the facts first); on papers and artists the
90th percentile is at 66%, on medical 74%, on legal 79% (lists and judgments scatter their facts). Reading each
column only as far as its 90th percentile would save 82% of the tokens on players, 34% on papers and artists, 26%
on medical and 21% on legal, at a 10% miss rate by construction. This explains the "first window only" ablation
(21–42% of tokens saved for −0.012 to +0.015) and improves on it: a per-column window learned from a sample of
positions is a cheaper read plan than a fixed window, and it needs no model. It also needs no gold: learned from
where the 7B's *own* stated values sit in the recorded run, the shares for the columns read on demand are within
0.01–0.08 of the gold-based ones on papers, players and artists (0.18 on medical, where the model's list items sit
later than gold's, so the learned window is the conservative one). Those are the shares the queued I7 run uses:
players 0.29–0.53, papers 0.33–0.90, artists 0.10–0.88 (birth date, death date and nationality in the first tenth),
medical 0.54–0.89. Legal gets none: its on-demand columns (judge, year, the parties' status) sit in the last 2% of a
judgment, so the whole document is the window, which is why "first window only" cost legal its −0.012. A read that
asks several columns takes the largest share, and that is optimal: reading two columns in one prompt costs the
longer window once, reading them apart costs both.

**The things we already do without a model, named as such.** Determinacy estimated from ten sampled documents
(ρ −0.66 against −0.72 for the full corpus); the context chosen for a column by its fill rate (what made frozen
DocETL beat per-query DocETL); the cost lemma that decides anticipation from a token count; scope from the query's
filters; commit-time normalization to the workload's forms. Together with the verifier and the position model they
form an *extraction catalogue* per column (kind, determinacy, fill by context, grounding rate, position, cost per
document), which is to an LLM-built database what cardinalities and selectivities are to a relational one: the
statistics the planner needs, computed once, cheap, and not a model.

**What should stay an LLM, and what we should not pretend about it.** Reading a document and writing a value is the
model's job; selecting among candidate labels when the workload has not named them is where it is weakest (label
collapse), and no non-LLM step recovers a label set nobody declared (E8). Where a column is under-determined, no
cascade helps (I2); the repair is a specification, a vocabulary, or a person, and the verifier above is what tells
you which cells those are.

## 4. Observations the community can use

1. The workload's structure survives column drift: in 76–100% of test queries the tables, joins, aggregates and
   group-by shape already occur in the training workload. Systems should learn structure (keys, kinds, groupings)
   from workloads and learn columns on demand; forecasting columns under drift does not work (I4).
2. About half of the constants queries compare with never appear verbatim in the documents, so a document-only
   extractor cannot be expected to produce them in the query's form. But the vocabulary is rarely what is missing:
   of 25 GROUP BY columns read on demand, 5 lack a small label set, and the largest merges happen on columns whose
   prompt lists the labels. Label collapse is the model's mapping of a passage to a declared label; measure it as
   sensitivity, and expect a vocabulary declaration to fix only the columns where none exists.
3. Under-determination is a property of the schema's representation (lists, labels, empties), not of the text. Two
   extractors disagree as often on stated facts as on unstated ones; they disagree about what to select and how to
   write it. "Make the schema more determinate" (enumerate labels, fix list semantics, define absence) is the
   lever, and it is a data-management lever.
4. Grounding is a kind-specific check: strong for numbers and names, decisive for lists (any invented item), weak for
   labels. A verifier built from grounding, disagreement, empties and sensitivity predicts wrong cells at AUROC 0.85
   without labels and transfers across corpora.
5. Budget cascades in tokens and price fixes per dollar; document length, not the routing rule, sets the price.
6. Where a value sits in a document is a column property; per-column read windows are a cheap, model-free plan.

## 5. What is still missing

Three deployments are queued behind the current 7B runs, each with a prediction written down first
(RESEARCH_DEPTH.md §8): the verifier as the router of 600 second looks on the 32B (I2b: more net fixes per dollar
than random and than most-sensitive-first, because it adds disagreement and empties to sensitivity); the label
contract on the five columns that lack a vocabulary (I6: their merged rows fall by at least half, the corpus score
moves by under 0.01, because those columns carry few rows); per-column windows on papers, players, artists and
medical (I7: players' patch tokens fall by about half, the others' by 15–30%, scores within 0.02 of recorded). The
"structure survives drift" result should be checked on a workload whose structure does drift (a different split of
templates between train and test), which the benchmark does not provide.
