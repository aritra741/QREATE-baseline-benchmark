---
title: "Why the system behaves the way it does"
---

The system builds a database from documents with an LLM. Before queries arrive, it reads every document once for the
columns its known workload uses (the *build*). When a later query needs a column the build skipped, it extracts that
column *on demand*, only for the documents the query can select, and keeps the result for later queries. *Workload
drift* of p% means that p% of the columns needed by the test queries were left out of the build. We use five corpora
(research papers, basketball players, artists, medical documents and court judgments), Qwen 2.5 7B as the main model,
and Qwen 2.5 32B for some comparisons. A query's score is the product of structure F2 and cell F1, averaged over
queries.

The sections below take the main observations from the experiments and ask why each one holds, starting with the
ones that matter most.

# Why does on-demand extraction match the accuracy of extracting everything up front?

**Extraction timing turns out to be irrelevant; what matters is the prompt.** Drift only changes which prompt reads a
column: the build asks for all of a table's new columns at once, while an on-demand extraction asks for one to three.
To test this we re-ran the fully drifted workloads with every on-demand extraction given exactly the build's prompt.
**463 of the 467 queries then scored the same as when everything was extracted up front.** One of the remaining
queries (research papers) differs because of how values are mapped to the workload's vocabulary when results are
served, not because of extraction. The other three are on the medical (2 of 43) and legal (1 of 27) corpora, and we
have not yet traced them.

The small gaps we saw earlier between up-front and on-demand scores are therefore prompt effects. With the 7B model
they are too small to be significant. With the 32B model they are not: on research papers the on-demand score is 0.062
higher, and almost all of it comes from one column, whether a method uses single-hop or multi-hop reasoning. Asked
together with six other columns, the model leaves it empty for 64% of papers; asked alone, it fills it for 98%.

![Figure 1. Scores with everything extracted up front, with on-demand extraction, and with on-demand extraction using
the build's prompt.](figures/w1_when_vs_how.png){width=6.5in}

This holds on all five corpora with the 7B model and on two with the 32B model. In practice, a system can defer extraction without losing accuracy, and the thing to
control is prompt design.

# Why do queries fail, and does it depend on the kind of query?

Looking at individual queries rather than averages, **most failures are the wrong set of groups, and almost always too
few groups.** At 100% drift, 79% of the 290 test queries return groups that differ from the gold answer, 13% return
the right groups with wrong values, 4% return no rows and 5% are fully right. More than half of all queries (55%)
return fewer groups than the gold answer.

**The groups go missing because extraction collapses labels.** For each GROUP BY column we compared the number of
distinct values in the extracted table with the number in the gold table. In 59% of these columns the extraction has
fewer distinct values, and in only 11% it has more. The collapse is strongest on research papers (median ratio 0.67)
and medical documents (0.75), and absent on basketball players and court judgments (1.0), which matches how the
corpora rank overall. The more groups a gold answer has, the more of them are missed: 47% of queries with one to
three gold groups return too few, against 81% of queries with more than thirty.

![Figure 2. (a) Distinct values in the extracted GROUP BY column relative to gold. (b) Share of queries returning too
few groups, by the number of groups in the gold answer.](figures/b7_label_collapse.png){width=6.5in}

To see how labels collapse we followed every gold row of every GROUP BY column (17,021 rows) into the extracted table.
45% get the exact gold label. 22% get a label of their own that is spelled differently, so the group survives under
another name. **24% are merged into a label that mostly belongs to a different gold group, and only 9% are left
empty.** Groups therefore disappear mainly because the model draws category boundaries more coarsely than the gold
data, not because it fails to answer.

**Whether a column collapses depends on what kind of value it holds.** GROUP BY columns that hold numbers or years keep
the exact label for 94% of rows, because a number has one obvious way to be written and no boundary to choose. Free
categories keep it for 49%, and the merges follow the model's own idea of the categories: on artists, "20th century"
absorbs the gold groups "19th-20th" and "20th-21st", and on court judgments one case-type label holds 235
administrative, 155 civil and 56 commercial cases. Two-valued columns (yes/no, 0/1) merge 24% of rows, almost always
into the majority answer: "is this the first judgment in the case?" is answered "0" for 261 judgments that are not and
212 that are. Lists of values do worst (29% exact, 32% merged), because the model keeps one item of a list such as "oral,
intravenous" and so joins the group of that single item. This also explains the corpus differences. Medical columns
are mostly lists and free-text categories, and 44% of their rows get a differently spelled label and 19% none, the
highest of any corpus. Basketball players group mostly by short factual values such as team and position and keep 79%
exact.

![Figure 3. Where each gold row of a GROUP BY column ends up in the extracted table, by kind of column (a) and by
corpus (b), at 100% drift.](figures/b8_label_fate.png){width=6.5in}

The aggregate matters as much as the grouping. AVG queries score 0.38, SUM and MIN 0.32, COUNT 0.21 and MAX 0.17, and
**this ordering is the same at every drift level**, so it is a property of the aggregate rather than of drift. It
follows from how each aggregate reacts to one wrong or missing row. We matched predicted and gold groups by their keys
and compared the aggregate values. Averages and sums are within 20% of gold in 54% and 63% of groups because
individual errors partly cancel. MIN is within 20% in 78% of groups and almost never too low (2%): extraction rarely
produces a value smaller than the true minimum, so a minimum only goes wrong when its row is missing. MAX is wrong in
both directions (21% too high, 20% too low), because one inflated value anywhere in the group becomes the maximum.
COUNT is within 20% in only 42% of groups, too low in 33% and too high in 25%, because every row whose label is
missing or merged moves a count. That is the same label collapse as above.

![Figure 4. Mean score by aggregate across drift levels, with on-demand extraction (a) and the static build
(b).](figures/b1_aggregate_drift.png){width=6.5in}

![Figure 5. Aggregate values in matched groups at 100% drift: too low, within 20% of gold, or too
high.](figures/b6_aggregate_direction.png){width=6.5in}

Filters and joins follow the same logic. Queries with no filter score lowest (0.23, against 0.29 with one filter),
and 113 of the 119 have wrong groups: without a filter the query groups the whole corpus, so many more groups have to
come out right. With three or more filters the score drops again (0.21), since each condition depends on another
extracted column and the errors compound. Queries with joins score higher (0.30 with one join, 0.38 with two or more),
but all of them are on basketball players, the easiest corpus. Within that corpus the scores are 0.37, 0.44 and 0.38
for zero, one and two or more joins, so joins do not hurt this system, because keys are extracted once and
consistently (see the DocETL section).

These patterns are correlational and partly confounded by corpus: joins occur only on basketball players, and the
corpora differ in how many groups their queries have.

# Why is reading a column up front so much cheaper than extracting it later?

Anticipating a column costs 2.7 to 5.9 times less than extracting it on demand, and the *break-even probability* (the
chance a future query needs a column above which it is worth reading up front) ranges from 1.3% to 13%. **Both follow
from where the tokens go: every extraction prompt contains the whole document.** Adding one column to a build prompt
that is sent anyway costs only the column's description and its answer, 84 tokens at the median. Extracting the
column later pays for the document again, a median of 745 to 9,537 tokens depending on the corpus, plus 66 tokens of
instructions. The break-even probability should then be close to the ratio of description tokens to document tokens.

**A model built only from these token counts predicts the measured break-even within about 30% on every corpus** and
puts the corpora in the right order:

| Corpus | Median document (tokens) | Predicted | Measured |
|---|---|---|---|
| Research papers | 928 | 9.9% | 13.1% |
| Artists | 745 | 9.3% | 12.2% |
| Basketball players | 995 | 1.7% | 1.3% |
| Medical | 9,537 | 1.7% | 1.9% |
| Court judgments | 4,762 | 2.0% | 1.9% |

On papers and artists the measured value is higher than predicted because on-demand extractions there read only the
documents a query's filters select, which the model ignores.

![Figure 6. Left: composition of one extraction prompt at each corpus's median document length. Right: predicted and
measured break-even probability.](figures/w2_cost_mechanism.png){width=6.5in}

For corpora with long documents this means almost any plausibly useful column is worth extracting up front, since the
threshold is around 2%. For short documents it is closer to 10%, and that is where knowing the workload saves the
most.

# Why can't a budget policy beat extracting whatever fits, first come, first served?

We tried pacing the budget, capping any single extraction, skipping extractions that bought nothing in hindsight, and
an offline plan that knew the whole workload in advance, on all five corpora. None was reliably better than first
come, first served. The best gain of any policy on any corpus is 0.005 in mean score, and every policy that does not
use hindsight loses on at least one corpus (pacing by 0.010 on basketball players, the offline plan by 0.008 on
research papers). Skipping extractions that bought nothing in hindsight keeps the score and only saves tokens (up to
17% on medical).
**The main reason is that an extraction's value mostly arrives later.** Across the five corpora, 54% to 97% of the
score gain from an extraction goes to later queries that reuse the column, rather than to the query that triggered it
(97% on research papers, 54% on court judgments). Several extractions do nothing for their own query and a lot for
later ones. A policy deciding when a query arrives cannot see this.

![Figure 7. Share of each extraction's score gain that goes to its own query and to later
queries.](figures/w3_value_timing.png){width=6.5in}

**Capping the size of an extraction always loses (by 0.006 to 0.029), because the largest extractions are the most
valuable ones.** In the unlimited runs the rank correlation between an extraction's token cost and its total value is
0.28 to 0.63 on four corpora. A large extraction reads a column for many documents, and many later queries reuse it.
The cap costs least on research papers, the one corpus where size and value are unrelated (correlation −0.01), and
most on basketball players.

**Pacing does not drop extractions, it delays them, so whether it helps depends on two opposing effects.** 89% to
100% of the extractions that pacing skips are made later in the same stream, reading the same documents. The delay
has a predictable cost: queries that arrive while the column is still missing get worse. Among queries where the two
policies hold different columns, pacing loses on four of five corpora (on research papers 8 such queries get worse
and none better). The second effect is not predictable. Once both policies hold the column, its values still differ,
because the delayed extraction ran in a different prompt, next to different columns. These queries move in both
directions and, summed, favour pacing on four corpora and strongly disfavour it on basketball players (49 better, 108
worse). The two effects add up to the observed sign on every corpus: pacing helps on artists, research papers and
medical, and hurts on basketball players and court judgments. **So pacing wins only when re-extracting a column in
different company happens to improve its values by more than the delay costs.** This is the prompt sensitivity of the
section on prompts below, appearing through the budget, and it explains why no policy that reasons only about cost
and timing can win reliably.

The offline plan fails for an additional reason: an extraction's cost depends on what was extracted before it. Earlier
extractions make filter columns available, which narrows the documents later extractions read. Under first come, first
served the same query almost always costs the same as without a budget (94% to 100% of cases), but once the plan
removes an extraction's predecessors its cost can jump. In one case it went from 1 document to 29 and no longer fit.

So budgeted extraction is a sequential problem in which value is deferred and shared between queries, and in which
moving an extraction changes its values as well as its timing. A useful policy would need to forecast which columns
future queries will use and keep each column's extraction prompt fixed; estimating each extraction's value on its own
is not enough. We do not yet have a true upper bound for budget policies, and we have not explained why the value
effect turns against pacing on basketball players.

# Why do field descriptions matter more than anything else we changed?

**Most extraction errors come from the specification rather than from reading.** Given only a column name, the model
often does not know what to write, whether that is a count, a list of years, or a date in a particular format. It
leaves the cell empty or writes the value in another form. Without descriptions in the on-demand prompts, a count of
FIBA World Cup appearances falls from 0.86 to 0.01 correct because the model leaves it empty. An artist's award count
falls from 0.74 to 0.06, and birth dates from 0.38 to 0.00 because they come back in a different format. **Adding the
benchmark's descriptions to a single extraction pass raised its score from 0.234 to 0.560, the largest effect in the
whole study.**

![Figure 8. Share of cells correct with and without field descriptions.](figures/w6_specification.png){width=6.5in}

The same problem shows up in values that are right in substance but wrong in form. On one artist column, values agree
with the gold data 92% of the time if we ignore case, punctuation and list order, but only 13% of the time exactly,
and a GROUP BY needs the exact form. The evidence here comes from cell-level comparisons. We have not yet run the
causal test of rewriting ambiguous descriptions and measuring the gain.

# Why are some columns, and some corpora, so sensitive to the prompt?

When a document states a value plainly, as with a number or a yes/no answer, any reasonable prompt returns it. **When
the document does not settle the answer, the prompt decides.** Examples are a disease's causes, a party's status, or a
value the document never mentions. The prompt decides through how readily the model leaves a cell empty and through
the example values it shows.

We measured, for each column the test queries need, how often the build's prompt and the on-demand prompt give
different values for the same document. **Across 41 columns this disagreement is a strong predictor of error
(Spearman −0.76).** Numbers disagree on 9% of cells, yes/no columns on 24%, free text on 47% and categories on 60%. No
column with more than about 55% disagreement is right more than 60% of the time. The reverse does not hold: some
columns are consistent and still wrong because both prompts make the same formatting error.

![Figure 9. Disagreement between two prompts against accuracy, one point per column.](figures/w4_determinacy.png){width=6.5in}

The medical corpus, whose columns are mostly descriptive judgments, stands out. Its two prompts disagree on 75% of
cells, against 28% to 34% for papers, artists and court judgments and 10% for basketball players. Document length
does not explain this; on the earlier version of the medical and legal queries, prompts disagreed about as often on
short documents as on long ones. With five corpora we cannot separate three properties that occur together in the
medical corpus: descriptive columns, gold values that are often empty, and list-valued columns. One practical use of
this result is that disagreement between two cheap prompts can flag columns that need a better description or a human
look, before any gold data exists.

# Why does extracting a column for more documents sometimes make answers worse?

**When a column does not apply to a document, the model rarely leaves it empty**, especially when the schema says the
column is never null. Extracting "agent framework" for every paper assigned one to 82 papers that have none. The
budgeted run extracted it only for the papers earlier queries had selected, and was more accurate. More generally, a
budgeted run beats the unlimited one on 8 to 31 queries per corpus, and nearly all of those queries were answered
without an extraction of their own.

The benchmark makes this worse. It marks 19 of the 59 columns on three corpora as never null, although its own gold
data often leaves them empty. Emptying exactly those cells would raise the research-papers score from 0.153 to 0.193.
Limiting extraction to documents where a column applies is therefore a matter of correctness as well as cost. This
rests on case evidence and an oracle measurement; we have not yet counted invented values against applicability in a
controlled way.

# Why does a cost-based extraction planner fall short of one shared extraction pass?

**The planner estimates its loss as disagreement with each query's own extraction, which means it treats its own
extractions as correct.** It cannot tell that a shared extraction is more accurate, and once its extractions agree with
each other it sees nothing left to gain. It also values columns one at a time, while a missing join key makes the
whole query fail. On basketball players its best configuration reaches 0.42, against 0.56 for one shared pass with
descriptions. At the full budget it plans only 4.9M of the 10.6M available tokens because its estimated loss is
already 0.027 per query.

We know the cause but have not built a planner with a different objective. Such a planner would need some estimate of
accuracy, for instance from a small labelled sample or from the disagreement between prompts described above.

# Why does DocETL fail on queries that join tables?

DocETL extracts each table separately for each query. On basketball players its scores drop from 0.125 for queries
without joins to 0.034 with one join and 0.008 with two or more. **A join only matches rows whose keys agree, and keys
extracted independently mostly do not.** In DocETL's per-query tables, 18% of player rows find their team and 19% of
team rows find their city. In our build the figures are 75% and 97%, and in the gold data 63% and 93% (the gold data
contains players whose team has no row of its own). Our build extracts each table's keys once with the same field
definitions, and later queries reuse them.

![Figure 10. Share of rows whose join key finds a partner in the joined table.](figures/w5_join_keys.png){width=6.5in}

Basketball players is the only corpus with joins, so this rests on one corpus.

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
checks, for each basketball-player query with a join, how many rows' keys appear in the joined table. The query
breakdown uses, for every test query and drift level, its structure and value scores and its predicted and gold row
counts; the label analysis counts distinct values per GROUP BY column in the served and gold tables, and the aggregate
analysis runs each query on both and compares values in groups matched by key. The label-fate analysis assigns each
predicted label to the gold group that most of its rows belong to, and classifies every gold row as exact, own label
in another form, merged into another group's label, or empty. The pacing analysis compares each paced stream with
the first-come stream at the same budget and drift level, query by query, and records whether the two held the same
needed columns when the query arrived.

# Appendix: example test queries

Each test query is a benchmark query with one column replaced by a column the build did not read. A few per corpus, chosen to cover the aggregates and, where the corpus has them, joins and several filter conditions.

## Research papers (59 test queries)

```sql
SELECT performance_on_NQ, COUNT(paper_name) AS count_papers FROM cspaper WHERE uses_reranker = 'Yes' GROUP BY performance_on_NQ
```

```sql
SELECT retrieval_method, SUM(baseline_amount) AS sum_baseline_amount FROM cspaper WHERE uses_reranker = 'No' OR performance_on_hotpotqa = 'F1: 62.2' OR baseline = 'Traditional RAG' GROUP BY retrieval_method
```

```sql
SELECT agent_framework, MAX(baseline_amount) AS max_baselines FROM cspaper WHERE agent_framework IN ('Other', 'Multi-Agent Collaboration') AND NOT baseline_amount IS NULL GROUP BY agent_framework
```

```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph-based%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web Search%' THEN 'Web Search' WHEN retrieval_method <> '' THEN 'Other' END AS retrieval_family, agent_framework, COUNT(*) AS paper_count FROM cspaper WHERE retrieval_method <> '' AND agent_framework IN ('Other', 'Multi-Agent Collaboration') GROUP BY retrieval_family, agent_framework
```

## Basketball players (118 test queries)

```sql
SELECT t.team_name, COUNT(*) AS player_count, AVG(p.draft_pick) AS avg_age, SUM(CASE WHEN NOT p.olympic_gold_medals IS NULL THEN p.olympic_gold_medals ELSE 0 END) AS total_recorded_olympic_golds FROM player AS p JOIN team AS t ON TRIM(p.team) = TRIM(t.team_name) GROUP BY t.team_name HAVING COUNT(*) >= 2
```

```sql
SELECT player.team, SUM(player.nba_championships) AS sum_player_mvp_awards FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE player.age > 28 GROUP BY player.team
```

```sql
SELECT player.position, MAX(player.draft_year) AS max_player_mvp_awards FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY player.position
```

```sql
SELECT player.team, AVG(player.draft_year) AS avg_player_age FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE (city.city_name = 'Los Angeles') OR (player.mvp_awards >= 1) GROUP BY player.team
```

## Artists (43 test queries)

```sql
SELECT zodiac, COUNT(birth_date) AS count_art_institution FROM art GROUP BY zodiac
```

```sql
SELECT genre, AVG(awards) AS avg_age FROM art WHERE birth_country = 'British India' OR teaching <> 0 GROUP BY genre
```

```sql
SELECT nationality, MAX(age) AS max_age FROM art WHERE tone = 'Warm' GROUP BY nationality
```

```sql
SELECT nationality, COUNT(*) AS artist_count FROM art WHERE tone IN ('Bright', 'Dark') AND nationality <> '' GROUP BY nationality HAVING COUNT(*) >= 5
```

## Medical (43 test queries)

```sql
SELECT prescription_status, COUNT(recommended_usage) AS count_side_effects FROM drug WHERE administration_route <> 'inhalation' GROUP BY prescription_status
```

```sql
SELECT disease.complications, COUNT(disease.treatments) AS count_disease_treatments FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY disease.complications
```

```sql
SELECT prescription_status, COUNT(mechanism_of_action) AS count_generic_name FROM drug WHERE (administration_route = 'injection') AND (administration_route <> 'subcutaneous') GROUP BY prescription_status
```

## Court judgments (27 test queries)

```sql
SELECT CASE WHEN case_type IN ('Administrative Case', 'Civil Case', 'Commercial Case') THEN case_type ELSE 'Other' END AS case_family, COUNT(*) AS case_count FROM legal WHERE fine_amount IN ('0', '5000', '20000') GROUP BY case_family
```

```sql
SELECT CASE WHEN verdict IN ('Dismissed', 'Approved', 'Others') THEN verdict ELSE 'Other' END AS verdict_family, AVG(legal_basis_num) AS avg_statutes FROM legal WHERE judgment_year = '2009' AND case_number >= 3 GROUP BY verdict_family
```

```sql
SELECT evidence, MIN(judgment_year) AS min_hearing_year FROM legal GROUP BY evidence
```

```sql
SELECT verdict, MIN(legal_basis_num) AS min_legal_basis_num FROM legal WHERE fine_amount = '20000' AND defendant <> 'Construction, Forestry, Mining and Energy Union' AND fine_amount <> '70000' GROUP BY verdict
```

