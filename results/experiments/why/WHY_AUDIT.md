# Are we answering why, or reporting? An audit of the claims, and three mechanism tests run on the audit's weak rows

Date: 2026-10-10. Question from the advisor's side, relayed today: do the findings explain their observations or
only report them. The table grades each claim; the sections after it are tests run today on data in hand to turn
the weakest rows into mechanisms.

## 1. The audit

| claim | grade | the why, and how it was tested |
|---|---|---|
| timing is irrelevant, the prompt matters | mechanism tested | hold the prompt fixed and the drift effect vanishes (463 of 467 queries) |
| determinacy predicts accuracy across models and systems | mechanism tested | disagreement arises where the document leaves the answer open; the category exception and the stated-versus-inferred result were predictions of that mechanism and held |
| two kinds of error; only misreadings are repairable | mechanism tested | a stronger reader repairs determined cells and leaves under-determined ones; the verifier finds the latter |
| the cost lemma; the unit of extraction moves cost | mechanism derived | the document dominates the prompt; a column costs 1–13% of a read |
| pacing fails with frozen prompts | mechanism traced | one indivisible spend; 102 skipped queries on one stream |
| windows cannot establish an absence; dates gain under a window | mechanism traced | 79 of 133 counts left empty; the chained read returned the year alone |
| consistency beats accuracy for joins | mechanism tested | keys read once match 75%, per query 18% |
| forecasting fails under drift | mechanism stated | no reuse history to forecast from; reuse statistics support it, no intervention isolates it |
| a vocabulary fixes form, not selection | mechanism stated | the fate decomposition shows it; why the model merges '20th-21st' into '20th' is inferred |
| grouping gains do not reach queries | partly traced | form, emptiness and aggregate fragility shown on examples, not decomposed quantitatively |
| repairability is a column property | **was: observation** | see §3: repairs are restraint and precision, which are column properties |
| context and order change 40% of cells | **was: observation** | see §2: a document property with a small sequential component |
| the first field line is answered differently | observation | no causal account; the layout rule failed |
| structure survives drift; constants not verbatim | artifact of the benchmark | Bench-U's template generator and annotator-normalized labels; to be stated as such |

Half the claims are answered why-questions with a tested mechanism; a quarter have a stated mechanism without an
isolating test; the root phenomenon, why the prompt's arrangement changes a value, was an observation until today.

## 2. Why the arrangement changes the value: a document property, with a small sequential part

Data: the field-order prompts (24 columns, 30 documents, the natural group in three orders). Two hypotheses: (a)
*sequential conditioning*: the model answers fields in prompt order (it does, 354 of 370 responses) and conditions
each answer on the answers before it, so a changed earlier answer changes later ones; (b) *document instability*:
some documents under-determine many fields at once, and any perturbation re-samples all of them.

Test: a field's flip rate when only fields *before* it flipped against when only fields *after* it flipped. Under
(a) the first is larger, since later answers cannot cause earlier ones; under (b) they are equal.

| condition | flip rate | n |
|---|---|---|
| only earlier fields flipped | 0.402 | 801 |
| only later fields flipped | 0.365 | 883 |
| fields on both sides flipped | 0.476 | 3,110 |
| no other field flipped | 0.115 | 226 |
| within documents with 3+ other flips: earlier-only / later-only | 0.499 / 0.440 | 489 / 555 |
| within documents with 1 other flip: earlier-only / later-only | 0.255 / 0.236 | 149 / 161 |

Flip rates by position (first, middle, last field): 0.45, 0.42, 0.47: no position gradient. So the arrangement
effect is mostly (b): flips cluster by document (0.476 when the document flips elsewhere, 0.115 when it does not),
and the sequential part (a) adds 0.02 to 0.06 in the forward direction. *The value a prompt returns for an
under-determined cell is a draw; the arrangement is one of the things that re-draws it, and the document, not the
sequence, decides how many cells are draws.* This is the mechanism behind "determinacy is a property of the column
and the document", measured directly.

## 3. Why repairability is a column property: a stronger reader's repairs are restraint and precision

Data: the 2,999 cells with a 32B second look. For each repaired cell, how the 7B's value related to gold:

| what was wrong with the 7B's value | share of the 388 repairs | share of the 1,694 unrepaired wrong cells |
|---|---|---|
| list with extra items (items the document does not state) | 0.38 | 0.05 |
| date with the right year in another form or precision | 0.21 | 0.01 |
| same text under a stricter scorer | 0.10 | 0.06 |
| empty | 0.07 | 0.06 |
| different content | 0.16 | 0.43 |
| different number | 0.04 | 0.02 |
| list with missing, different or partly overlapping items | 0.02 | 0.31 |

So 69% of what the stronger reader repairs is *restraint* (it does not add items the document does not state) and
*precision* (it writes the full date where the 7B wrote the year: 81 of 82 repaired dates were year-only, one was a
format change). Reading a different fact is 20% of repairs. That is why repair is a column property: columns whose
errors are over-selected lists or coarse dates are repairable, columns whose errors are different content are not.

Two consequences, both tested today:

- *Restraint can be a string check.* Drop from a served list every item not stated verbatim in the document (numbers
  in any common form). On the 992 list cells of the second-look pool: accuracy 0.158 → 0.301 (the 32B: 0.335), 146
  fixes and 4 breaks (the 32B: 192 and 17), 118 of the fixes the same cells. On all 11,001 list cells of the
  recorded run: 0.250 → 0.299, 531 net fixes; by corpus medical 0.093 → 0.234, artists 0.259 → 0.292, legal 0.454
  → 0.488, papers 0.484 → 0.374. Papers loses because its list columns are labels the text paraphrases
  (`application_domain` 'Healthcare', `data_modality`), and artists' `birth_country` loses 89 cells for the same
  reason (the document says 'French', the gold 'France'): there the unstated items are truths in another form. The
  two cases are told apart without labels by the probe: *an invented item is unstable across contexts, a paraphrased
  truth is stable*. Per column, the share of unstated items that differ between the lone and the grouped read is
  0.52–0.97 where the filter helps (genre, challenges, conditions, symptoms) and 0.09–0.35 where it hurts
  (country, domain, modality, nationality). Switching the filter on only where that share is at least a half keeps
  530 of the 531 net fixes and removes every column that lost more than 8. It is the grounding result ("a list with
  an invented item is never right") turned into an operator with the determinacy result as its guard, and it is now
  a planner component (`itemfilter`, on by default, the probe deciding per column; `QUWARTS_PLANNER_OFF` turns it
  off for the ablation).
- *Precision needs a read, but a short one.* The year-only dates come from the chained whole-document read; the
  head window at a tenth of the article returned the full date (I7: `birth_date` 0.38 → 0.79). So the date repairs
  the 32B makes are available from the 7B by reading less, not more.

## 2b. Why the first field line is answered differently: conditioning on the content of earlier answers

Papers' `agent_framework` (allowed values Other, Multi-Agent Collaboration, CoT, ToT; gold empty for most papers),
by what precedes it in the prompt (210 reads per condition in the natural, shuffled, reversed, first and last
orders):

| what precedes the field | n | empty | 'Other' |
|---|---|---|---|
| nothing (the field is first) | 210 | 0.00 | 0.93 |
| `use_agent` answered 'No' before it | 70 | 1.00 | 0.00 |
| `use_agent` answered 'Yes' before it | 10 | 0.00 | 0.20 (a framework otherwise) |
| `use_agent` comes after it | 150 | 0.41 | 0.51 |

The model derives the framework from its own earlier answer when it has one, and falls back to the default label
when it has none. The same priming holds for filling in general: a field is filled on 81% of documents when at
least two thirds of the fields before it were filled, on 63% when fewer than a third were. So the position effect
is sequential conditioning on the *content and fill* of earlier answers, which the flip test of §2 could only see
as a small forward asymmetry because most flips are the document's. For a planner this is usable: a field that
depends on another (a framework on whether an agent is used; a count on whether the list is empty) should follow
it in the prompt, and a derived field should not be asked at all when its parent is known.

## 3b. Why the model merges centuries: a derivable label extracted as a judgment

Artists' `century` ("when the artist was active or influential") has no stated rule. Gold follows the lifespan
(birth-century to death-century) on 74% of 709 artists; the recorded model agrees with that span on 47%, and the
model with the declared label list on 28%. Under the contract every merge goes the same way, '19th-20th' or '20th'
served as '20th-21st' for artists born 1880–1910 who died 1950–1990: the model grounds the label in any century
the text mentions, including posthumous retrospectives and sales, and the declared list makes the widest label
available. Computing the century from the birth and death dates the system already extracts would match gold on
74% of rows against the model's 47%: *a derived attribute extracted as a judgment is a label-collapse mechanism, and
the repair is a rule, not a reader.* The planner should derive such columns (century, age, decade) from their
parents instead of asking for them, which the usage phrase already marks (age is defined from the dates in the
schema).

## 5. Why cell gains do not reach queries: a wrong cell costs more than a right cell earns (counterfactual tables)

Method (`exp_cause.py`): take the recorded served table and the other run's values; sort every differing cell into
form (same fact, other rendering), empty (a value appears or disappears), items (a list changes), fact (different
content), and by whether the change made the cell right, made a right cell wrong, or left it wrong; build a table
for each subset with the system's own representation; score every test query on it with the benchmark scorer. The
table with every change applied reproduces the other run's stream (papers: identical query results on 42 of 59,
identical mean, the rest being queries scored before their columns were complete).

Papers, the planner's run under the refined rules against the recorded run (cell accuracy of the changed cells:
empty 0.17 → 0.45, fact 0.19 → 0.27; query score 0.153 → 0.138):

| changed cells | GROUP BY queries | COUNT | filter | numeric aggregate |
|---|---|---|---|---|
| became right (empty → value) | +0.004 | +0.002 | +0.002 | +0.015 |
| became right (other fact) | +0.005 | +0.007 | +0.006 | 0 |
| right became wrong (value → empty) | −0.013 | −0.013 | −0.008 | −0.015 |
| right became wrong (other fact) | −0.019 | −0.024 | −0.022 | 0 |
| wrong stayed wrong (other wrong fact) | −0.004 | −0.005 | −0.005 | 0 |

Cells that became right lift the group-by score by 0.009; cells that turned from right to wrong cost 0.032, three
and a half times as much, although the second set is smaller. The same decomposition on the first-rules run (score
0.153 → 0.217, the counterfactual with every change reproducing 0.214) shows the other face of the same mechanism:

| changed cells (first-rules run) | GROUP BY | COUNT | filter |
|---|---|---|---|
| became right (other fact) | +0.043 (12 queries moved) | +0.052 | +0.041 |
| right became wrong (other fact) | +0.006 | +0.008 | +0.007 |
| wrong stayed wrong (another wrong fact) | +0.009 | +0.011 | +0.011 |
| empty → value, right / wrong | +0.004 / −0.006 | | |

Here cells that went from right to wrong did not hurt, and cells that stayed wrong but changed label helped. *A
GROUP BY or COUNT query scores the distribution of labels over rows, not the cells*: a change helps when it moves a
row toward the group sizes gold has, whatever the cell's own correctness, and hurts when it moves a row out of a
true group into a false one (two errors in the result for one cell). In the refined run the changes were of the
second kind and per-cell accuracy rose while the score fell; in the first-rules run the second looks on
`reasoning_depth` moved 59 rows' labels toward gold's mix and the score rose by more than the cells' accuracy did.
For a system this says two things: an empty cell is cheaper than a wrong one on a grouping or filter column, so
restraint (the item filter, the "never null" absence value) is worth more than fill; and a planner that could see
a column's label distribution (the probe sees it on ten documents) could predict which columns' second looks pay
at the query level. Players, the planner's run under the refined rules (0.387 → 0.376; 569 changed cells, of
which 499 are form only): the form changes move no query (±0.001 across every operator); cells that became right
lift group-by queries by 0.004 (10 queries); cells that turned from right to wrong cost 0.011 on group-by, 0.019
on filters and 0.024 on joins (4–5 queries each). The asymmetry holds on a corpus with joins, where a key that goes
wrong loses its partner row outright.

## 6. Why the planner's score moved 0.217 → 0.138 on papers between two runs: decisions on ten samples flip

The two runs differ in two thresholds and in sampling. The sensitivity ranking of the columns barely moved (mean
change 0.03 to 0.10 across corpora), but the binary decisions did: on papers the narrow prompt for
`agent_framework` was taken in one run and not the other, and the repair rate of `reasoning_depth` from ten labelled
cells was +0.3 in one run and −0.1 in the other, so the second looks that moved the group-by queries (+2.75 summed
in the first run) were not taken in the second. Medical flipped two repair decisions and one narrow prompt; players,
artists and legal kept their decisions and their scores within 0.02. *Ten documents rank columns (Spearman −0.66
against −0.72 for the full corpus) but cannot carry a per-column binary decision whose margin is one or two
documents.* The final system (V3) probes twenty documents, estimates repair rates from twenty labelled cells, and
routes only with three net repairs; the ten-sample runs are kept as the measurement of this instability.

## 4. What this changes in the paper

The root claim gets its mechanism (§2), the repair claim gets its mechanism and a free operator (§3), and the
system gains a component derived from a why. The remaining observation-level rows are the position effect (no
mechanism found) and the two benchmark artifacts, which the paper should name as artifacts.
