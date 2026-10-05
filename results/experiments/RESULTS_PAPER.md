# Answers to the research questions

Paper-style answers to the eight research questions. Each section states the question, the answer in one or two
sentences, the evidence, the implication for system design, and the scope of the evidence. The internal record (all
runs, case studies, corrections) is `FINDINGS.md`; the digest with every number is `SUMMARY.md`. Figures are
generated from the result files by `systems/WDIRS/quwarts/scripts/plot_results_paper.py` into `figures/`. A
self-contained Word version with the figures embedded is `RESULTS_PAPER.docx` (rebuild: `module load pandoc/2.19.2`,
then from this folder `sed -E 's#\]\(figures/([a-z0-9_]+\.png)\)#](figures/\1){width=6.5in}#' RESULTS_PAPER.md | pandoc
-f markdown+pipe_tables+link_attributes-implicit_figures -t docx --resource-path=. -o RESULTS_PAPER.docx`).

## Setting and terms

**System.** An LLM-based extraction system turns a document collection into relational tables so that SQL queries can
be answered. It builds an initial database by reading each document once for the columns its known workload uses
(the **build**). When a later query needs a column the build did not extract, it extracts that column on demand
(a **patch**), reading only the documents the query's filters can still select.

**Workload drift.** Each corpus has a known workload and a test set of later queries. A drift level of *p*% means *p*%
of the new columns the test queries need were left out of the build. At 0% the build anticipated every column; at
100% it anticipated none.

**Data.** Five document corpora: research papers (cspaper, 200 documents), basketball players with teams, owners and
cities (player, 4 tables, 216 documents), artists (art, 1,000), medical diseases, drugs and institutions (med, 3
tables, about 300), and court cases (legal, 570). 326 drift test queries over all five.

**Metric.** Per query, structure F2 (are the right rows and groups returned) × cell F1 with 20% numeric tolerance
(are the values right), averaged over queries. 1.0 is a perfect answer.

**Model.** Qwen 2.5 7B Instruct, 4-bit, served locally with Ollama, unless stated. Token counts are input + output.

**Statistics.** Differences between two systems on the same queries are paired; 95% confidence intervals come from a
bootstrap over queries. Most results are single runs. Run-to-run noise was measured: re-running a whole drift stream,
with every extraction repeated, moved its score by at most 0.002; three repeats of one extraction pass varied by up to
0.012 on a 20-query test set. Differences of a few thousandths are within noise and are reported as such.

---

## RQ1. When should a system extract a column up front, and when on demand?

**Answer.** Extract generously up front and patch on demand only what could not be foreseen. On-demand patching is
essential: without it, accuracy collapses as the workload drifts. But anticipating a column is far cheaper than
patching it later, because it adds one field to prompts that are read anyway, while a patch re-reads every document
in scope.

**Evidence.**

*Patching keeps accuracy under drift; a static build does not.* At 100% drift (no new column anticipated):

| Corpus | Static build | With on-demand patching | Paired difference (95% CI) |
|---|---|---|---|
| player | 0.040 | 0.387 | +0.347 (0.287 – 0.411) |
| art | 0.031 | 0.256 | +0.225 (0.152 – 0.304) |
| cspaper | 0.008 | 0.153 | +0.146 (0.092 – 0.204) |
| legal | 0.005 | 0.114 | +0.110 (0.055 – 0.177) |
| med | 0.031 | 0.086 | +0.055 (0.030 – 0.082) |

With patching, the score at 100% drift is never more than 0.014 below the fully anticipated build (0% drift). On
player and cspaper it is slightly higher (+0.008, +0.019), but neither rise is significant (paired 95% CIs −0.007 to
+0.028 and −0.011 to +0.052; query-level gains and losses cancel), so the patched curve is flat under drift. The rise
is not extraction noise either: patching changes 2.5–3.7× as many cells of the drifted columns as re-running the same
stream does, because patches read under a query-specific prompt and only on the documents the query can select. With
a stronger model the rise becomes significant (Qwen 2.5 32B on cspaper: +0.062, 95% CI +0.019 to +0.113; RQ7).

![Score as drift grows, static build vs on-demand patching, per corpus.](figures/rq1_drift.png)
*Figure 1. Score as drift grows, static build vs on-demand patching, per corpus.*

The result does not depend on which columns were withheld. Re-drawing the withheld columns three more times at the
same drift levels (cspaper and player), static collapses on every draw (to 0.008 and 0.040 at 100% drift), the
patched curve stays within 0.035 of its 0% score at every level, and no draw's 100% − 0% difference is significant
(cspaper +0.007 to +0.020; player −0.010 to +0.008).

![The drift result across four draws of the withheld columns.](figures/rq1_seeds.png)
*Figure 2. The drift result across four draws of the withheld columns (cspaper, player).*

It does not depend on how much of the workload the build anticipates either. Cutting the build workload to 10%, 25%
or 50% of its queries (same test queries) leaves more columns to the patches (art at 10%: 14 new columns instead of
9). Static still collapses at 100% drift (0.000–0.043), the patched curve stays within 0.025 of its 0% score, and no
100% − 0% difference is significant (−0.015 to +0.014). The cost moves from the build to the patches and grows: art
at 10% saves 1.0M build tokens but adds 2.6M patch tokens (+19% total); cspaper +23%, player +7%.

![The drift result for build workloads cut to 10–50% of their queries.](figures/rq1_train.png)
*Figure 3. The drift result for build workloads cut to 10–50% of their queries (cspaper, player, art).*


*Anticipating is cheaper than patching.* Total tokens (build + patches) and score, from fully anticipated to fully
on demand:

| Corpus | All anticipated | None anticipated | On-demand ÷ anticipated tokens | Break-even probability |
|---|---|---|---|---|
| player | 2.12M, 0.379 | 7.71M, 0.387 | 3.6× | 1.3% |
| med | 2.87M, 0.095 | 22.47M, 0.086 | 7.8× | 1.6% |
| legal | 5.05M, 0.121 | 34.49M, 0.114 | 6.8× | 1.6% |
| art | 3.18M, 0.270 | 8.52M, 0.256 | 2.7× | 12% |
| cspaper | 0.55M, 0.134 | 1.56M, 0.153 | 2.8× | 13% |

The break-even probability is the cost of anticipating a column divided by the cost of patching it: a column is worth
extracting up front if the chance a future query needs it exceeds this value. The build costs are exact up to the
answer tokens of the anticipated fields (estimated at 12 per field; measured 9.5–15), an error of at most about 2%.

![Total extraction tokens relative to a build that anticipated every column.](figures/rq1_anticipation.png)
*Figure 4. Total extraction tokens relative to a build that anticipated every column.*

**Implication.** Treat anticipation as cheap insurance: extract every plausibly useful column during the build, and
keep on-demand patching as the safety net for columns no one foresaw.

**Scope.** Five corpora, all drift levels, one model; four draws of the withheld columns on cspaper and player; three smaller build workloads on cspaper, player and art;
replicated with two other models (RQ7).

---

## RQ2. Is a column extracted more accurately when a prompt asks for fewer columns?

**Answer.** No, not in general. Narrow prompts (one column) help on some corpora and hurt on others, and always cost
several times the tokens. Prompt width is not a lever worth building into the system.

**Evidence.** The same 12 columns extracted from a fixed document sample, 1, 3, 6 or 12 columns per prompt; agreement
with gold where both have a value:

| Corpus | 1 column per prompt | 12 columns per prompt | Difference | Token ratio |
|---|---|---|---|---|
| legal | 0.547 | 0.479 | +0.068 | 10× |
| player | 0.806 | 0.780 | +0.026 | 10× |
| cspaper | 0.572 | 0.580 | −0.008 | 6× |
| med | 0.040 | 0.062 | −0.022 | 10× |
| art | 0.449 | 0.483 | −0.034 | 6× |

The mechanism differs by corpus: a one-column prompt pushes the model to produce *some* value, so it fills cells that
gold leaves empty far more often (art: 98% of gold-empty cells at one column, 60% at twelve). That helps where gold is
mostly filled (legal, player) and hurts where it is often empty (art, med).

![Agreement with gold by number of columns asked per prompt.](figures/rq2_width.png)
*Figure 5. Agreement with gold by number of columns asked per prompt.*

**Implication.** Extract many columns per prompt for cost; do not narrow prompts in the hope of accuracy.

**Scope.** Five corpora, 40–141 documents each, one model.

---

## RQ3. How should an adaptive system spend a limited extraction budget?

**Answer.** Spending the budget first-come-first-served (patch every query that fits) is not monotone: a larger budget
can score lower, because expensive early patches can exhaust the budget without improving any answer. A rule that
reads only the SQL, *never patch for a query whose answer is the minimum or maximum of a text column*, removes these
collapses, saves 16–28% of tokens where it applies, never hurts, and matches a hindsight oracle. No generic pacing or
capping policy is reliably better than first-come-first-served.

**Evidence.**

*Why first-come-first-served collapses.* On legal at 100% drift, a 50% budget scores 0.053 while a 25% budget
scores 0.110. The 50% budget spends 8M of its 14.5M tokens on two early patches whose queries ask for the
alphabetically smallest counsel name per group; no extraction can answer those, and they help no later query. The 25%
budget cannot afford them and spends on patches that 19 later queries use.

![Legal at 100% drift: score by budget, first-come-first-served vs skipping MIN/MAX-over-text queries.](figures/rq3_legal_budget.png)
*Figure 6. Legal at 100% drift: score by budget, first-come-first-served vs skipping MIN/MAX-over-text queries.*

*Such queries are unwinnable and expensive everywhere.* The 45 of 326 test queries that take MIN/MAX of a text column
score 0.03 on average with our system and 0.001 with the baseline, yet trigger 33% of all patch tokens.

*Five policies* (mean score over 25 budget × drift settings per corpus; tokens in parentheses where they differ):

| Policy | cspaper | player | art | legal | med |
|---|---|---|---|---|---|
| First-come-first-served | 0.1453 | **0.3363** | 0.2356 | 0.1106 (219M) | 0.0797 (154M) |
| Skip MIN/MAX-over-text queries | 0.1453 | 0.3363 | 0.2356 | **0.1136** (158M) | **0.0828** (130M) |
| Hindsight oracle (skip patches that bought nothing) | 0.1453 | 0.3363 | 0.2356 | 0.1129 (158M) | 0.0797 (130M) |
| Cap any single patch at 25% of the budget | 0.1398 | 0.3076 | 0.2263 | 0.0992 | 0.0812 |
| Pacing (spend in step with the stream) | **0.1466** | 0.3260 | **0.2405** | 0.1030 | 0.0821 |

The SQL rule has no effect where no query matches (cspaper, player, art), and on legal it removes the collapse (50%
budget at 100% drift: 0.053 → 0.107) while saving 28% of tokens. Pacing helps where early patches over-read
(cspaper, art) and hurts where early patches are the valuable ones (player, legal). Whether any skipping helps tracks
the share of patch tokens that bought nothing: none on player, about a third on legal and med.

![Each policy's mean score minus first-come-first-served, per corpus.](figures/rq3_policies.png)
*Figure 7. Each policy's mean score minus first-come-first-served, per corpus.*

**Implication.** Budgeted adaptive extraction needs value-aware skipping, and simple SQL-level signals already
capture most of the value of hindsight; budget pacing and per-patch caps are not safe defaults.

**Scope.** Five corpora × five budgets × five drift levels. Not yet computed: the offline optimum over all patch
subsets, which would bound every policy.

---

## RQ4. Can the cost and the value of an extraction be predicted before it is run?

**Answer.** Cost, yes, almost exactly. Value only partly: a large share of extraction tokens buy nothing, and two
signals visible in the SQL locate most of that waste.

**Evidence.**

*Cost.* The median ratio of estimated to actual patch tokens is between 0.997 and 1.005 on every corpus.

*Value.* Share of patch tokens that improved neither the triggering query nor any later query using the same
columns: player 0%, art 16%, med 32%, legal 39%, cspaper 39%. Over all 138 patches (152M tokens, 29% wasted):

| Signal visible in the SQL | Share of its tokens wasted | Share of all waste it covers |
|---|---|---|
| MIN/MAX over a text column | 68% | 73% |
| No filter (the patch reads the whole corpus) | 44% | 89% |
| A filter scopes the patch | 8% | 11% |
| AVG/SUM aggregate | 1% | 1% |

![Wasted extraction tokens by SQL-visible signal.](figures/rq4_signals.png)
*Figure 8. Wasted extraction tokens by SQL-visible signal.*

**Implication.** A planner can trust its cost model and should spend its modelling effort on value; cheap SQL
features already separate risky extractions (whole-corpus reads for text extrema) from safe ones (scoped, numeric).

**Scope.** Five corpora, the unlimited streams at full drift.

---

## RQ5. Does a cost-based extraction planner beat a single shared extraction pass?

**Answer.** Given the same information, the planner beats a single pass at higher budgets, but it never reaches a
single pass that has better field descriptions, and it leaves much of its budget unspent. Both failures have one
cause: the planner measures loss as disagreement with each query's own extraction, so it treats that extraction as
the truth and cannot recognise a more accurate shared one.

**Evidence.** Player, 20 held-out queries:

| System | Score | Tokens |
|---|---|---|
| One shared pass, field names and types only | 0.234 | 1.25M |
| Planner, names and types, 25% / 75% budget | 0.232 / 0.340 | 2.6M / 5.6M |
| Planner with the benchmark's field descriptions, 25% / 75% | 0.247 / 0.381 | 2.4M / 3.9M |
| Same, with join keys weighted as the whole query, 75% | 0.422 | 3.4M |
| **One shared pass with the field descriptions** | **0.560** | **1.30M** |
| Planner building on that pass (fills only its gaps), 75% target | 0.566 | 4.93M |

The field descriptions are worth +0.33 on a single pass (structure F2 0.42 → 0.87), the largest single effect we
measured. At small budgets the planner loses mainly by leaving join keys unread (it values each column separately,
while a missing join key zeroes the whole query). At a 100% budget it plans 4.9M of 10.6M available tokens, because
its estimated loss is already 0.027 per query.

![Score vs tokens for planner configurations and single shared passes (player).](figures/rq5_planner.png)
*Figure 9. Score vs tokens for planner configurations and single shared passes (player).*

**Implication.** An extraction planner's objective must estimate accuracy, not agreement with its own reads (for
example from a small labelled sample or agreement across independent contexts), and must account for join keys at
query level. More extractions with the same model and inputs buy little; better field descriptions and a stronger
model buy a lot (RQ7).

**Scope.** One corpus (player), one model; the planner budget sweep was run on player only.

---

## RQ6. Does the order of extractions change the answers?

**Answer.** Order changes *which* documents get extracted, not the values extracted, and extracting less sometimes
helps. The system never overwrites an extracted value.

**Evidence.** Each (column, document) pair is extracted at most once per stream. Comparing a budgeted stream with the
unlimited one at the same drift level, the cells that differ are almost all filled in one and empty in the other
(cspaper: 12,241 such cells vs 455 with two different values; player: 38,028 vs 0). A budgeted stream beats the
unlimited one on 8–31 queries per corpus, nearly all answered without their own patch. In the clearest case
(cspaper, a column defined only for papers that use an agent framework), the unlimited stream extracted it for every
paper and the model assigned a framework to 82 papers that have none; the budgeted stream extracted it only on the
papers earlier queries had selected and left the rest empty, which is correct for most of them.

![Cells that differ between budgeted and unlimited streams, by kind (log scale).](figures/rq6_cells.png)
*Figure 10. Cells that differ between budgeted and unlimited streams, by kind (log scale).*

**Implication.** Extracting a column for documents where it does not apply is harmful, not merely wasteful; scoping
extractions to the documents a query can select is a correctness feature as well as a cost one.

**Scope.** Five corpora, all budget × drift settings.

---

## RQ7. Do the conclusions hold across models and serving setups?

**Answer.** Yes. The main result (patching preserves accuracy under drift, at the same cost) holds for three models
from two families, and the serving setup moves scores by much less than the effects reported here. Model capacity is
the largest lever after field descriptions.

**Evidence.**

| | Llama 3.1 8B | Qwen 2.5 7B | Qwen 2.5 32B |
|---|---|---|---|
| Player, one shared pass (20 held-out queries) | 0.466 | 0.560 | **0.690** |
| Player, static / patched at 100% drift | 0.040 / 0.359 | 0.040 / 0.387 | 0.052 / **0.421** |
| cspaper, patched at 0% → 100% drift (static at 100%) | 0.149 → 0.125 (0.008) | 0.134 → 0.153 (0.008) | 0.162 → **0.224** (0.008) |

Patch costs are the same for every model (player 5.7–5.8M, cspaper 1.2–1.3M tokens). On serving: 16-bit instead of
4-bit weights adds +0.03 on a single pass and +0.004 on a whole drift stream; repeated runs vary by at most 0.012 on
20 queries and 0.002 on a stream.

![Three models: single pass, and patched vs static at 100% drift.](figures/rq7_models.png)
*Figure 11. Three models: single pass, and patched vs static at 100% drift.*

**Implication.** The system-level conclusions are not artefacts of one small, quantized model; a stronger model
raises every number without changing what the system should do.

**Scope.** Two corpora for the other models; quantization on one corpus.

---

## RQ8. Where do LLM-built databases lose accuracy?

**Answer.** It depends on the corpus. Where documents have simple facts and tables join cleanly, the loss is in cell
values; where values are free text, lists or join keys, it is in structure (wrong or missing rows and groups). Two
causes cut across corpora and bound every system: the benchmark's metadata instructs extractors to fill fields that
its own gold leaves empty, and values are often right in substance but not in the exact form a query groups by.

**Evidence.**

*Bottleneck per corpus* (patched, 100% drift):

| Corpus | Structure F2 | Cell F1 | Where the loss is |
|---|---|---|---|
| player | 0.753 | 0.468 | cell values; rows and joins stay right |
| legal | 0.758 | 0.168 | cell values |
| cspaper | 0.650 | 0.187 | cell values, e.g. results tables deep in papers |
| art | 0.527 | 0.340 | both |
| med | 0.335 | 0.157 | structure: 61 of 76 queries return too few rows (list-valued join keys, free-text comparisons) |

![Structure F2 vs cell F1 per corpus, with on-demand patching at 100% drift.](figures/rq8_bottleneck.png)
*Figure 12. Structure F2 vs cell F1 per corpus, with on-demand patching at 100% drift.*

*Metadata contradicts gold.* Of the 132 columns the benchmark's attribute files mark "never null", 69 are empty in at
least 5% of gold rows (57 of them used by the workloads; e.g. a medical column empty in 85% of gold rows). Extractors
told "never null" must invent values. Telling the model it may leave text fields empty does not help: it trades
invented values for missed ones (score changes from −0.053 to +0.020 on four corpora; −0.043 on med).

*Right in substance, wrong in form.* For list-valued and free-text columns, lenient agreement with gold (any shared
list item; case and punctuation ignored) far exceeds exact agreement (e.g. an art column 0.92 vs 0.13), yet the
benchmark's tolerant score is only 0.01–0.03 above the strict one, because a GROUP BY needs the exact label.
Normalizing values to the constants the workload uses gains nothing: the mismatches are in labels no query names.

![Exact vs lenient agreement for the ten columns with the largest gap.](figures/rq8_form.png)
*Figure 13. Exact vs lenient agreement for the ten columns with the largest gap.*

*By query type:* AVG/SUM 0.36, MIN/MAX over numbers 0.24, COUNT 0.21, MIN/MAX over text 0.03.

**Implication.** Benchmarks for LLM-based extraction should check their attribute metadata against their gold and
score set-valued columns as sets; systems gain most from accurate field definitions and from treating text extrema
and list-valued join keys as special cases.

**Scope.** Five corpora; one model for the per-column analysis.

---

## Comparison with DocETL

**Answer.** On the same drift queries and model, on-demand patching is more accurate than DocETL on every corpus and
uses 7–25× fewer tokens. DocETL extracts per query and does not reuse extractions; its accuracy collapses on joins.

| Corpus | Queries | DocETL | Ours (patched) | Paired difference (95% CI) | DocETL tokens | Ours (build + patches) | Ratio |
|---|---|---|---|---|---|---|---|
| player | 118 | 0.081 | 0.387 | +0.306 (0.246 – 0.368) | 190.6M | 7.71M | 25× |
| cspaper | 59 | 0.105 | 0.153 | +0.049 (0.004 – 0.093) | 20.7M | 1.56M | 13× |
| art | 43 | 0.167 | 0.256 | +0.089 (0.047 – 0.135) | 57.9M | 8.51M | 7× |
| med | 76 | 0.056 | 0.086 | +0.030 (0.010 – 0.054) | 170.6M | 22.46M | 8× |
| legal | 16 of 30 | 0.046 | 0.147 | +0.101 (0.046 – 0.165) | 269.1M | 26.73M | 10× |

![Ours vs DocETL per corpus (left) and on player by number of joins (right).](figures/docetl.png)
*Figure 14. Ours vs DocETL per corpus (left) and on player by number of joins (right).*

At 100% drift; DocETL with the same 4-bit Qwen 2.5 7B, one map operation per query and table with an equal-effort
prompt. On player, DocETL scores 0.125 / 0.034 / 0.008 on queries with 0 / 1 / 2+ joins, while ours stays at 0.37–0.44;
the likely cause (not yet verified value by value) is that join keys extracted by separate per-table operations do
not match, whereas our build extracts every table's keys with the same field definitions.

**Scope.** Legal is 16 of 30 queries (DocETL takes about 3 hours per legal query); the other corpora are complete.
