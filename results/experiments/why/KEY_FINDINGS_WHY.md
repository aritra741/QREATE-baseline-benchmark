---
title: "Why the system behaves the way it does"
---

The system builds a database from documents with an LLM. Before queries arrive, it reads every document once for the
columns its known workload uses (the build). When a later query needs a column the build skipped, it extracts that
column on demand, only for the documents the query can select, and keeps the result for later queries. Workload drift
of p% means that p% of the columns needed by the test queries were left out of the build. We use five corpora
(research papers, basketball players, artists, medical documents and court judgments), Qwen 2.5 7B as the main model,
and Qwen 2.5 32B for some comparisons. A query's score is the product of structure F2 and cell F1, averaged over
queries.

The sections below take the main observations from the experiments and ask why each one holds.

# Why does on-demand extraction match the accuracy of extracting everything up front?

Extraction timing turns out to be irrelevant. What matters is the prompt. Drift only changes which prompt reads a
column: the build asks for all of a table's new columns at once, while an on-demand extraction asks for one to three.
To test this we re-ran the fully drifted workloads with every on-demand extraction given exactly the build's prompt.
396 of the 397 queries then scored the same as when everything was extracted up front. The remaining query differs
because of how values are mapped to the workload's vocabulary when results are served, not because of extraction.

The small gaps we saw earlier between up-front and on-demand scores are therefore prompt effects. With the 7B model
they are too small to be significant. With the 32B model they are not: on research papers the on-demand score is 0.062
higher, and almost all of it comes from one column, whether a method uses single-hop or multi-hop reasoning. Asked
together with six other columns, the model leaves it empty for 64% of papers; asked alone, it fills it for 98%.

![Figure 1. Scores with everything extracted up front, with on-demand extraction, and with on-demand extraction using
the build's prompt.](figures/w1_when_vs_how.png){width=6.5in}

This holds on three corpora with the 7B model and on two with the 32B model. The same test on the medical and legal
corpora is still running. In practice, a system can defer extraction without losing accuracy, and the thing to
control is prompt design.

# Why is reading a column up front so much cheaper than extracting it later?

Anticipating a column costs 2.7 to 5.9 times less than extracting it on demand, and the break-even probability (the
chance a future query needs a column above which it is worth reading up front) ranges from 1.3% to 13%. Both follow
from where the tokens go. Every extraction prompt contains the whole document. Adding one column to a build prompt that
is sent anyway costs only the column's description and its answer, 84 tokens at the median. Extracting the column
later pays for the document again, a median of 745 to 9,537 tokens depending on the corpus, plus 66 tokens of
instructions. The break-even probability should then be close to the ratio of description tokens to document tokens.

A model built only from these token counts predicts the measured break-even within about 30% on every corpus and puts
the corpora in the right order:

| Corpus | Median document (tokens) | Predicted | Measured |
|---|---|---|---|
| Research papers | 928 | 9.9% | 13.1% |
| Artists | 745 | 9.3% | 12.2% |
| Basketball players | 995 | 1.7% | 1.3% |
| Medical | 9,537 | 1.7% | 1.9% |
| Court judgments | 4,762 | 2.0% | 1.9% |

On papers and artists the measured value is higher than predicted because on-demand extractions there read only the
documents a query's filters select, which the model ignores.

![Figure 2. Left: composition of one extraction prompt at each corpus's median document length. Right: predicted and
measured break-even probability.](figures/w2_cost_mechanism.png){width=6.5in}

For corpora with long documents this means almost any plausibly useful column is worth extracting up front, since the
threshold is around 2%. For short documents it is closer to 10%, and that is where knowing the workload saves the
most.

# Why can't a budget policy beat extracting whatever fits, first come, first served?

We tried pacing the budget, capping any single extraction, skipping extractions that bought nothing in hindsight, and
an offline plan that knew the whole workload in advance. None was reliably better than first come, first served. The
main reason is that an extraction's value mostly arrives later. Across the five corpora, 54% to 97% of the score gain
from an extraction goes to later queries that reuse the column, rather than to the query that triggered it (97% on
research papers, 54% on court judgments). Several extractions do nothing for their own query and a lot for later
ones. A policy deciding when a query arrives cannot see this.

![Figure 3. Share of each extraction's score gain that goes to its own query and to later
queries.](figures/w3_value_timing.png){width=6.5in}

The offline plan fails for an additional reason: an extraction's cost depends on what was extracted before it. Earlier
extractions make filter columns available, which narrows the documents later extractions read. Under first come, first
served the same query almost always costs the same as without a budget (94% to 100% of cases), but once the plan
removes an extraction's predecessors its cost can jump. In one case it went from 1 document to 29 and no longer fit.

So budgeted extraction is a sequential problem in which value is deferred and shared between queries. A useful policy
would need to forecast which columns future queries will use. Estimating each extraction's value on its own is not
enough. The policy comparison covers three corpora so far, with medical and legal still running, and we do not yet
have a true upper bound for budget policies.

# Why do field descriptions matter more than anything else we changed?

Most extraction errors come from the specification rather than from reading. Given only a column name, the model often
does not know what to write, whether that is a count, a list of years, or a date in a particular format. It leaves the
cell empty or writes the value in another form. Without descriptions in the on-demand prompts, a count of FIBA World
Cup appearances falls from 0.86 to 0.01 correct because the model leaves it empty. An artist's award count falls from
0.74 to 0.06, and birth dates from 0.38 to 0.00 because they come back in a different format. Adding the benchmark's
descriptions to a single extraction pass raised its score from 0.234 to 0.560, the largest effect in the whole study.

![Figure 4. Share of cells correct with and without field descriptions.](figures/w6_specification.png){width=6.5in}

The same problem shows up in values that are right in substance but wrong in form. On one artist column, values agree
with the gold data 92% of the time if we ignore case, punctuation and list order, but only 13% of the time exactly,
and a GROUP BY needs the exact form. The evidence here comes from cell-level comparisons. We have not yet run the
causal test of rewriting ambiguous descriptions and measuring the gain.

# Why are some columns, and some corpora, so sensitive to the prompt?

When a document states a value plainly, as with a number or a yes/no answer, any reasonable prompt returns it. When
the document does not settle the answer, for example a disease's causes, a party's status, or a value it never
mentions, the prompt decides. It does this through how readily the model leaves a cell empty and through the example
values the prompt shows.

We measured, for each column the test queries need, how often the build's prompt and the on-demand prompt give
different values for the same document. Across 41 columns this disagreement is a strong predictor of error (Spearman
−0.76). Numbers disagree on 9% of cells, yes/no columns on 24%, free text on 47% and categories on 60%. No column with
more than about 55% disagreement is right more than 60% of the time. The reverse does not hold: some columns are
consistent and still wrong because both prompts make the same formatting error.

![Figure 5. Disagreement between two prompts against accuracy, one point per column.](figures/w4_determinacy.png){width=6.5in}

The medical corpus, whose columns are mostly descriptive judgments, stands out. Its two prompts disagree on 75% of
cells, against 28% to 34% for papers, artists and court judgments and 10% for basketball players. Document length
does not explain this; on the earlier version of the medical and legal queries, prompts disagreed about as often on
short documents as on long ones. With five corpora we cannot separate three properties that occur together in the
medical corpus: descriptive columns, gold values that are often empty, and list-valued columns. One practical use of
this result is that disagreement between two cheap prompts can flag columns that need a better description or a human
look, before any gold data exists.

# Why does extracting a column for more documents sometimes make answers worse?

When a column does not apply to a document, the model rarely leaves it empty, especially when the schema says the
column is never null. Extracting "agent framework" for every paper assigned one to 82 papers that have none. The
budgeted run extracted it only for the papers earlier queries had selected, and was more accurate. More generally, a
budgeted run beats the unlimited one on 8 to 31 queries per corpus, and nearly all of those queries were answered
without an extraction of their own.

The benchmark makes this worse. It marks 19 of the 59 columns on three corpora as never null, although its own gold
data often leaves them empty. Emptying exactly those cells would raise the research-papers score from 0.153 to 0.193.
Limiting extraction to documents where a column applies is therefore a matter of correctness as well as cost. This
rests on case evidence and an oracle measurement; we have not yet counted invented values against applicability in a
controlled way.

# Why does DocETL fail on queries that join tables?

DocETL extracts each table separately for each query. On basketball players its scores drop from 0.125 for queries
without joins to 0.034 with one join and 0.008 with two or more. A join only matches rows whose keys agree, and keys
extracted independently mostly do not. In DocETL's per-query tables, 18% of player rows find their team and 19% of
team rows find their city. In our build the figures are 75% and 97%, and in the gold data 63% and 93% (the gold data
contains players whose team has no row of its own). Our build extracts each table's keys once with the same field
definitions, and later queries reuse them.

![Figure 6. Share of rows whose join key finds a partner in the joined table.](figures/w5_join_keys.png){width=6.5in}

Basketball players is the only corpus with joins, so this rests on one corpus.

# Why does a cost-based extraction planner fall short of one shared extraction pass?

The planner estimates its loss as disagreement with each query's own extraction, which means it treats its own
extractions as correct. It cannot tell that a shared extraction is more accurate, and once its extractions agree with
each other it sees nothing left to gain. It also values columns one at a time, while a missing join key makes the
whole query fail. On basketball players its best configuration reaches 0.42, against 0.56 for one shared pass with
descriptions. At the full budget it plans only 4.9M of the 10.6M available tokens because its estimated loss is
already 0.027 per query. We know the cause but have not built a planner with a different objective. Such a planner
would need some estimate of accuracy, for instance from a small labelled sample or from disagreement between prompts
as in the previous section.

# Open questions

Several things remain unexplained. With the 7B model, asking for fewer columns helps on papers and players and hurts
on artists, and we do not know why the direction depends on the corpus. Grouping columns matters for the 32B model
but barely for the 7B model. We cannot yet say how much of the medical corpus's prompt sensitivity comes from each of
the three properties listed above, or what the best achievable budget policy is. The findings also have not been
tested beyond five corpora and three models, or on a different split of the workload into known and later queries.

# Methods

All analyses in this document reuse existing runs and needed no new model calls. The timing test re-ran the drifted
workloads from logged model responses, with on-demand extractions given the build's prompt. The cost model counts the
tokens of each new column's description and answer, of the instructions, and of up to 60 documents per table (split
into chunks as the system splits long documents); it compares the tokens added to build prompts with the tokens of a
one-column on-demand prompt. Value timing uses, for every on-demand extraction in the unlimited runs, the score change
of its own query and of later queries that use its columns. The specification and determinacy results compare cell
values with the gold data per column; determinacy uses the 41 columns with at least ten documents. The join analysis
checks, for each basketball-player query with a join, how many rows' keys appear in the joined table.
