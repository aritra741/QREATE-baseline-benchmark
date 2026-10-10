# What would top researchers learn from this paper? An audit against the advisor's own papers, and a plan

Date: 2026-10-08. Sources: ten of Anna Fariha's papers read in full or in their key sections (SAGE SIGMOD 2026,
Conformance Constraints SIGMOD 2021, SQuID VLDB 2019, AID SIGMOD 2020, ExDis SIGMOD 2026, DataPrism SIGMOD 2022,
PreView manuscript, the fair-classification analysis SIGMOD 2022, the EDT vision paper, and our QuWARTS demo), plus two
new analyses run today on existing logs (`WHY/context/summary.json`, `quwarts/eval/exp_context.py`).

## 1. How her papers are built

Every full paper follows the same recipe, and the recipe is what she means by "smarts".

**One named object with a definition.** Conformance constraints (a bounded linear projection with a quantitative
violation score). Unsafe tuples. The abduction-ready database and the semantic context of a set of examples. The
profile–violation–transformation triplet. A disparity explanation as a (subpopulation, treatment) pair. Pivot-table
utility and pivot-table diversity. The paper is then about that object: its definition, its properties, how to compute
it, what it is good for.

**One principle, stated in a sentence, about a property that causes an effect, and preferably surprising.** "Projections
with low variance construct effective conformance constraints", with the twist that the low-variance components of
PCA, which everyone discards, are the useful ones. "The examples are more likely to be alike, so a shared property that
is rare in the data is unlikely to be coincidental" (SQuID's abduction prior is the inverse of a filter's selectivity).
"Temporal precedence over-approximates causality; interventions refine it" (AID). "A system malfunctions because of a
property of the data, not because of individual cells, and correlation with failure is not cause" (DataPrism). "The
idle time between a user's queries is a resource" (PreView).

**A mechanism for why the principle holds, formal where possible.** In Conformance Constraints: Lemma 11 (two correlated
projections combine into one with lower variance and a stronger constraint), Theorem 12 (the set of good projections is
uncorrelated), and Proposition 17, which is the real "why": a tuple is unsafe when two models that agree on the training
data disagree on it, and violation of the ideal constraint is sound and complete for that. The principle is not an
observation; it is derived. SQuID proves the abduction algorithm correct; AID gives an information-theoretic convergence
rate; ExDis shows NP-hardness and gives a greedy algorithm; SAGE formulates a constrained optimization (Problem 2.1).

**A technique that follows from the principle, with a cost.** Because low-variance projections are the good ones, the
algorithm is PCA, linear in rows and cubic in attributes. Because semantics prune the pivot-table space, SAGE pushes the
diversity constraint down into the search. Because value lives in future queries, PreView predicts the next queries
(templates and parameters, recency-weighted, Poisson arrival times) and materializes within the time before the next
query. The technique is never "we tried five things".

**Evaluation as questions that could falsify the principle.** The research questions are "Is there a relationship
between constraint violation and prediction error?" (and a curve shows it, tuple by tuple), "Does it persist under
noise?" (yes, and the paper explains why noise weakens both constraints and failures), "Where does the baseline fail and
why?" (W-PCA misses local drift because it has no disjunctive constraints). Each experiment ends with a boxed key
takeaway. In the analysis paper on fair classification, which is the closest in form to ours, the findings are written
as explanations with stated hypotheses: "the impact of enforcing a fairness notion can be explained through the score of
a fairness-unaware classifier for that notion", "we hypothesize that their robustness is due to the fact that the
target demography holds regardless of data errors". That paper does not only compare methods: it injects errors into
the training data in a controlled, disproportionate way, varies the downstream model, and writes a "Lessons" section
about where the field should go.

**Reuse and transfer.** One object serves two applications (trusted ML and drift), and is then reused by later work
(DataPrism uses conformance constraints as one of its profiles). The EDT vision paper is explicit about the attitude:
recommendation "is a search and optimization problem, not a generation problem"; LLMs are "enablers, not complete
solutions"; decompose global objectives for algorithmic benefit.

What she will look for in ours, then, is: the object, the one-sentence principle, the mechanism, the technique that
follows from it, the falsifying questions with the failure cases, and the transfer.

## 2. Our work against that recipe

What we have is a system with a sensible design (workload-aware offline extraction, scoped on-demand extraction,
reuse), a large set of configuration sweeps (drift levels, budgets, five policies, eleven ablations, three models, five
corpora), and a "why" document that explains the sweeps after the fact. Measured against the recipe:

- There is no named object. "Workload-aware extraction" is a design, not a primitive.
- There is no principle stated before the experiments. The experiments ask "which setting works best", and the
  mechanisms were found afterwards by looking at the results.
- Almost all evidence is correlational. The exceptions are the timing replay (patches re-run with the build's prompt:
  463 of 467 queries identical) and, as of today, the paired context comparison below.
- No technique was derived from a principle and then tested. The policies were guesses (cap, pace, oracle, knapsack).
- Nothing is formal. There is a cost model that predicts the break-even within 30%, which is the only derived
  quantity.
- The research questions are comparisons, and the deck reads as a design-space exploration. She is right.

The good news is that the material for the recipe exists in our results; it was never organized as a claim.

## 3. The core we actually have

### The thesis in one sentence

**In a database populated by an LLM, a read is not idempotent: the value of a cell depends on the context in which it
was extracted, and that single property explains when extraction can be deferred, why budget policies that reason
about cost and timing cannot win, why joins fail when keys are extracted per query, and how to tell which columns to
trust without any ground truth.**

That is a property → effect → mechanism statement, it is surprising from a database point of view (a materialized value
is not equal to a recomputed one), it yields a primitive and techniques, and it carries over to any store populated by
a model.

### The object

*Extraction context.* A cell value is v(d, a | c), where d is the document, a the column, and c the context: the field
specification, the other columns asked in the same prompt, the instructions, and the model. In a conventional database
v(d, a) has no third argument.

*Context sensitivity of a column.* s(a) = the share of documents whose value changes between two admissible contexts.
Operationally: ask the column twice in different company and count disagreements.

*An unsafe cell*, by analogy with Fariha's unsafe tuple: a cell is unsafe if two admissible contexts that agree on most
of the corpus disagree on it. Agreement across contexts is *sound* for detecting that the document under-determines a
value (if the document fixed the value, no admissible context would change it) but *not complete*, because contexts can
share a bias (the same label vocabulary, the same misreading of a description). That incompleteness is exactly what we
measured on category columns, where agreeing cells are wrong more often than disagreeing ones. This is a statement we
can make precisely and defend; it is the analog of Proposition 17 and of the false-negative discussion in that paper.

### The principles, with the evidence we have today

**P1. Where the document under-determines a value, the context decides, and the value is wrong.** Context sensitivity
predicts column accuracy at the same strength for three models: Spearman −0.72 for Qwen 7B (102 columns), −0.72 for
Qwen 32B (47), −0.66 for Llama 8B (21). It is largely a property of the column rather than of the model: the per-column
sensitivity of the 7B correlates 0.61 with the 32B's and 0.53 with Llama's, and the 7B's sensitivity predicts the 32B's
accuracy (−0.62), Llama's (−0.48) and DocETL's (−0.73 on 40 shared columns). The larger model is less sensitive (0.37
against 0.58 on the same 46 columns), so a column's determinacy has a model-dependent floor, which is itself a usable
fact: sensitivity measured with a cheap model bounds what a dearer model will get right. Fail case, by kind: numbers
0.29, categories 0.29, free text 0.31, yes/no 0.59, lists 0.64 (7B). On categories the signal inverts, as above.

**P2. A cell's value has a hidden argument, so reads are not idempotent, and timing is irrelevant.** Same column, same
document, same model: a narrow prompt (one to three columns) and a wide one (four or more) give a different value 41% of
the time with the 7B, 37% with the 32B, 42% with Llama. The average accuracy does not move (0.438 narrow against 0.447
wide for the 7B) because the direction is column-specific: of 54 columns, 16 are better narrow and 17 better wide. So
"ask fewer columns at once" is not a knob; it is a per-column effect with no sign. This resolves one of the document's
open questions in principle: grouping helped on artists because its heavily used new columns are the ones that are
better wide (awards 0.09 → 0.46, century 0.19 → 0.30), and the usage-weighted prediction has the right sign there
(+0.14 predicted, +0.017 measured). It does not predict the small effects on players and medical (both within 0.03),
where cell accuracy and query score come apart; we should say so. Consequences we have already measured: deferring
extraction loses nothing when the context is held fixed (463 of 467); delaying it in a budget changes the answers
(pacing); keys extracted per query match 18% of the time against 75% when extracted once.

**P3. The cost of extraction is the cost of reading the document, so anticipating a column is almost free, and the
limit on anticipation is accuracy, not cost.** Break-even probability ≈ field tokens / document tokens, 1.3% to 13%
measured, predicted within about 30%. In these benchmarks 59% to 86% of schema columns are used by some query and a
column asked once is asked again 57% to 100% of the time, far above break-even. By cost alone one would extract
everything up front; P2 says the price is paid in values, not tokens. The real optimization is therefore to choose
contexts (which columns go together) to maximize accuracy under a cost bound, not to minimize cost.

**P4. Budgeted extraction is a sequential problem in which value is deferred and shared, cost depends on what was
extracted before, and moving an extraction changes its value.** 54% to 97% of an extraction's value goes to later
queries; the largest extractions are the most valuable (capping always loses); filter columns extracted early narrow
later reads (an offline plan mis-prices extractions it reorders); and pacing's effect is the sum of a predictable delay
cost and an unpredictable context effect (P2). A policy that reasons about cost and timing alone cannot win, and we
can say why.

**P5. The model draws coarser categories than the data, and the aggregate decides how much that matters.** 49% of gold
rows keep their exact group label, 23% are merged into another group, 9% are left empty; numbers keep 94%, lists 29%;
MIN is robust (too low 2% of the time), MAX is not; COUNT's low score is a corpus effect, not a property of counting.
The pattern repeats on DocETL's outputs, with the stated exceptions (numbers and averages, for reasons we can name).

### What is established and what is still a hypothesis

Established on existing data: the sensitivity–accuracy relationship and its stability across models and across DocETL;
the paired context effect and its lack of a consistent direction; the timing replay; the cost law; the value-deferral
and order-dependence facts; the label and aggregate breakdowns. Correlational, not yet interventional: everything about
budget policies; the corpus-level direction of grouping effects; the claim that freezing contexts would fix pacing or
DocETL's joins. Not yet formal: the soundness/incompleteness statement; the cost law as a lemma; the budget problem as
an objective.

## 4. What a top researcher would learn

That a database built by an LLM violates the oldest assumption in data management, that a stored value is the value,
and that the violation is measurable per column without labels, is a property of the column more than of the model,
predicts another system's errors, and has to be designed around: cache and materialize by context, extract keys once,
hold contexts fixed when deferring, and treat batching as an accuracy decision rather than a cost decision. They would
also learn the one-line cost law (field tokens over document tokens) and that the budget problem is sequential with
deferred, shared value. These carry over to RAG caches, LLM annotation pipelines, knowledge-graph construction and
semantic operators: anywhere a model's output is stored and reused.

## 5. The plan: turn observations into tested principles

Each item states the prediction before the run, as her papers do, and what we would write if it fails.

### Formal work (no GPU, two to three days)

1. Definitions of extraction context, context sensitivity, unsafe cell; the soundness-not-completeness proposition for
   agreement-based trust, with the category case as the counterexample.
2. The cost lemma: with document tokens D, instructions I, field tokens f, break-even p* = f / (D + I + f), and its
   corollary that for D ≫ f the decision depends only on whether the column is plausibly used.
3. The budget problem as an objective: maximize expected score gain over the remaining stream, where an extraction's
   value is its reuse-weighted future gain, its cost depends on the filter columns already present, and its context is
   fixed per column. State what the policies we tried optimize instead, and why each loses (cap: ignores reuse; pace:
   moves the context; offline plan: mis-prices history-dependent cost).

### From existing logs (no GPU, one day)

4. How cheap is the trust signal? Measure sensitivity on 10, 20 and 40 sampled documents per column and see how well
   the sample predicts the full-corpus accuracy ranking. Prediction: 20 documents suffice (rank correlation above 0.6).
5. Sensitivity under each kind of context change separately (co-asked columns, description present or absent, model),
   from the ablation logs we have (E13-nodesc, E14-bfields, E14-bgroup, head). Prediction: the per-column ranking is
   stable across kinds of change; this is what makes it a column property.
6. Finish the explanation of the grouping ablation: compare cell-level and query-level deltas per corpus to show where
   the two come apart (group labels, aggregates), closing the open question properly.

### Interventions on the GPU (pre-registered)

I1. *Context intervention on fixed documents* (one night). For every new column on all five corpora, 30 documents,
    extract under five contexts: alone, with two random columns, with six, with its natural group, and with a
    paraphrased description. Predictions: (a) sensitivity per column is stable across the kinds of change
    (ρ > 0.6 between pairs); (b) average accuracy is flat across widths but column-specific; (c) the 32B has lower
    sensitivity on every column, never higher; (d) on categories, agreement does not predict correctness. If (a) fails,
    sensitivity is a property of the column–context pair, and the paper's primitive must be indexed by context kind.

I2. *Determinacy-guided second looks* (half a day). With a fixed budget of re-extractions by the 32B, allocate them to
    columns by sensitivity, uniformly, and at random. Prediction: by sensitivity catches 1.4 to 2 times more errors per
    token (from the 69% vs 50% curve), except on categories, where it should not beat random. This is the technique that
    follows from P1.

I3. *Context-frozen DocETL* (one to two nights, the transfer she asked for). Run DocETL with one shared extraction per
    column across its queries (keys first). Predictions: join-key match rises from 18% toward 70% or more and the join
    queries recover most of the 0.125 → 0.008 loss; non-join queries change little; the columns that improve are the
    high-sensitivity ones. If join queries do not recover, the key problem is not consistency but coverage, and P2's
    role in joins is smaller than claimed.

I4. *A policy derived from P4* (one night). Forecast column demand from the workload (cluster query templates, weight by
    recency, as PreView does), hold each column's context fixed, and extract in forecast order under the budget.
    Prediction: beats first come, first served on the corpora with high reuse (players, papers) and never loses; and
    unfreezing the contexts brings back the pacing noise. This replaces "we tried five policies" with "the principle
    says a policy must do these three things; here is the one that does, and here is what happens when you take each
    one away".

I5. *Batching as an accuracy decision* (one night). Choose column groupings to maximize predicted accuracy from the
    per-column context effects measured in I1, under the same token cost. Prediction: beats both "all columns together"
    and "one at a time" on artists, ties elsewhere; and the gain is concentrated on the columns with large, consistent
    narrow-vs-wide differences.

Order: formal work and items 4–6 first (they sharpen the predictions), then I1 and I3 (the two that most change the
paper), then I2, I4, I5.

## 6. What reviewers will say, and the answers

*Prompt sensitivity is known.* Self-consistency and prompt brittleness are documented in NLP. Our contribution is not
that LLM outputs vary; it is that the variation is a per-column, cross-model, cross-system property, that it is the
right trust signal in the absence of labels, and that it breaks the idempotence that data-management systems assume,
with consequences for materialization, joins and budgets. The related-work section must say this plainly and cite the
NLP work; the framing is the same move as "through the data management lens" in the fairness paper.

*Only five corpora, curated benchmark schemas, one corpus with joins, a 7B model as the main one.* True; the cross-model
results help, I3 adds a second system, and the long-document corpora cover the cost law. The curated-schema caveat
limits P3's "anticipate everything" corollary and should be stated.

*The score (structure F2 × cell F1) hides mechanisms.* Agreed; the paper's evidence should be at cell and query level
with the score only as the summary.

*The cost law is obvious.* It is; its role is as the lemma that moves the problem from cost to accuracy, which is not
obvious.

## 7. A framing for the paper

Title directions: "Reads Are Not Idempotent: Context-Dependent Values in LLM-Built Databases and What to Do About
Them"; or "Determinacy: Measuring Trust in Data Extracted by Language Models" (deliberately echoing Conformance
Constraints: Measuring Trust in Data-Driven Systems).

Sections, in her order: the object (context, sensitivity, unsafe cell) with the soundness/incompleteness proposition;
the principles P1–P2 with the cross-model and paired evidence; the cost lemma and the budget formulation (P3–P4); the
techniques derived from them (determinacy-guided second looks, context-frozen reuse, forecast-ordered extraction) each
tested against the prediction; the breakdown by value kind and aggregate (P5) as the consequence section; transfer to
DocETL; lessons. QuWARTS becomes the vehicle, not the contribution.

## 8. Results log (filled in as the plan runs; started 2026-10-08 evening)

**Item 4, how few documents the signal needs.** Sensitivity estimated from n sampled documents per column, against
each column's full-corpus accuracy, Spearman over 101 columns averaged over 30 draws: n = 5 gives −0.62, n = 10 gives
−0.66, n = 20 gives −0.69, the full corpus −0.72 (`WHY/context/sample_curve.json`). The prediction (20 documents
suffice, |ρ| > 0.6) holds; even five documents give most of the signal. A trust check costs a few dozen prompts.

**Item 5, sensitivity under each kind of context change.** From the ablation logs, per column, the share of documents
whose value changes when only one thing about the prompt changes: the description removed, the workload-use phrase
removed, the grouping changed (the table's whole new-column set asked together), or long documents cut at the
window. The column ranking is the same under every kind of change: description vs usage 0.65, description vs grouping
0.60, usage vs grouping 0.71, grouping vs the two-prompt sensitivity 0.84, window vs the others 0.46–0.58 (36–42
columns; `WHY/context/kinds_of_change.json`). Each kind predicts accuracy on its own: usage −0.75, grouping −0.71,
window −0.58, description −0.41. Lists are the most sensitive to every kind of change (0.31–0.65), numbers the least
(0.10–0.23). So "a column's value is determined by the document to the extent that any change of context leaves it
alone" is one property, not four; this is prediction I1(a) confirmed from existing data before the intervention ran.

**Item 6, where cell accuracy and query score come apart.** Per test query at 100% drift, the score change under the
grouping ablation against the usage-weighted change in cell accuracy of the new columns it uses (narrow vs wide
prompt, same documents): Spearman 0.12 over 285 queries; among the 114 queries whose score changed, 0.22, with the
sign agreeing in 54% of cases (`WHY/context/grouping_query_deltas.json`). Mean cell accuracy does not predict which
queries move, because a query's answer depends on particular cells (the group labels of its GROUP BY column, the rows
its filters select), not on a column's average. The paper should say that the context effect is real and
column-specific at cell level, and that its effect on a query has to be measured at query level; the artists result
is the one corpus where the two agree.

**I1 on research papers (7B, 870 prompts, first corpus done).** Sensitivity ranks agree across kinds of change
(plus2 vs plus6 0.79, natural vs plus2 0.82, paraphrase vs plus6 0.97; 6 columns); sensitivity vs accuracy alone
−0.75; mean accuracy by context 0.42 alone, 0.42 with two random columns, 0.48 with six, 0.49 in the natural group,
0.39 with a paraphrased description; on categories, agreeing cells are right 52% of the time and disagreeing cells 14%
(the category exception does not appear on this corpus's two category columns). Full five-corpus results follow.

**I3 on research papers (frozen DocETL, first-query policy): the prediction failed, and the failure is the finding.**
Freezing each column on the first query that needed it cut DocETL's calls from 30,873 to 2,111 and its tokens from
45.6M to 3.0M for the same 143 queries (37 minutes against hours), but the mean score fell from 0.122 to 0.059 (17
queries better, 38 worse). The cause is not the wrapper: in the original run the first query's prompt also returned
an empty paper_name for every document; the original's 0.85 accuracy on that column comes from *other* queries'
prompts. Across the original run, a column's share of non-empty answers ranges from 1% to 100% depending on which
query's prompt extracted it (paper_name: 44 prompts, minimum 0.01, median 0.53, maximum 1.00; the median column's
spread is 0.50). Per-query extraction is therefore a lottery over contexts, and freezing on the first draw makes every
later query hostage to it; the column's 7B sensitivity does not predict which columns lost (ρ = 0.01), the quality of
the frozen context does. This is P2 in its strongest form, and it corrects the plan: the right intervention is not
"freeze on the first context" but "freeze on a determined context". I3b does that without labels: the first two
queries that need a column both extract it, the context with more non-empty answers wins, and the disagreement
between the two is recorded as the column's sensitivity measured inside DocETL. Prediction for I3b: score at or above
the original on papers at about twice the frozen cost (still an order of magnitude below the original), join keys
consistent on players, and DocETL's own two-context disagreement predicts its per-column accuracy as ours does.

**I1 on all five corpora (7B, 5,005 prompts, 39 new columns with ten or more sampled documents; done 23:26).**
(a) *A column's sensitivity ranks the same under every kind of context change:* Spearman between the per-column
sensitivities to two random added columns, six added columns, the natural group and a paraphrased description is
0.82–0.93 for every pair. Sensitivity is one property of the column, not a property of a particular prompt change.
(b) *Average accuracy is flat across contexts and column-specific in direction:* 0.39 alone, 0.37 with two random
columns, 0.41 with six, 0.39 in the natural group, 0.39 with a paraphrased description; 18 columns are better alone
than in the natural group by 0.05 or more and 9 are better in the group. Empty-answer rates are 0.28–0.32 in every
context. (c) Sensitivity predicts accuracy at −0.71, the same as on the full logs. (d) *Agreement vs correctness:* a
lone answer that agrees with the natural group's answer is right 55% of the time, one that differs 15% (690 cells);
lists 61% vs 13%, numbers 44% vs 15%, free text 52% vs 25%. On the intervention's two category columns the signal
also holds (52% vs 14%), so the category exception seen on the full logs (57% vs 49% over the 41-column set, whose
"category" columns are the choice-list ones) does not reproduce on this small sample; the paper should present the
exception as observed on the full-log columns and not yet isolated. By kind: lists are the most sensitive (0.57) and
least accurate (0.27); numbers the least sensitive (0.11). Full table: `I1-context/summary.json`.

**I3 on basketball players (first-query freezing).** Join queries improve as predicted, non-join queries collapse as
on papers. Over 193 queries: join queries 0.022 → 0.041 (86 queries), non-join 0.177 → 0.064, overall 0.108 → 0.054;
calls 34,719 → 1,725. Key match rates: player.team = team.team_name 0.19 → 0.30 (gold 0.63), but team.location =
city.city_name 0.165 → 0.09, because team.location froze on a bad first prompt (accuracy 0.73 → 0.17). The columns
that lost most are the ones whose first prompt happened to be bad (nationality 0.91 → 0.09, nba_championships 0.72 →
0.15); the 7B's sensitivity does not predict the loss (ρ = −0.06). Part of the original's per-query accuracy also
comes from each prompt carrying its own query's SQL constants, so a value is spelled the way that query compares it;
a frozen value is spelled one way for all queries, which an offline table can only recover by normalizing values to
a canonical form (what the QuWARTS build does with entity normalization). Both I3 runs therefore say the same thing:
*freezing a column on an arbitrary context is worse than re-extracting per query; freezing it on a determined context
is the hypothesis still to test* (I3b, running).

**I3b on research papers (freeze on the better of two contexts).** Mean score 0.101 against the original's 0.122
and the first-query variant's 0.059, with 3,937 calls (the original 30,873) and 5.7M tokens (45.6M): choosing the
context by a label-free rule recovers most of what first-query freezing lost, at an eighth of the cost. What is still
missing is explained column by column: paper_name is empty in both of its first two contexts (1 and 2 documents
filled of 200), as are several others (`filled` in `WHY/i3/summary.json`), because two draws from a lottery whose
median fill rate is 0.5 often give two blanks. The rule, not the idea, is the limit; I3c keeps drawing contexts for a
column until one fills at least half the documents (at most four), which is freezing on a *determined* context in the
sense of FORMAL.md §1. DocETL's own two-context disagreement does not yet track accuracy (0.26) because two empty
answers agree; the analysis now also reports disagreement over documents both contexts answered.

**I2, determinacy-guided second looks (1,719 cells re-asked by the 32B alone; budget 600 per allocation; documents up
to 6k tokens): the prediction failed, and the failure separates two kinds of error.** Allocating the budget to the
most sensitive columns first (which put all 600 cells in one list column) gave a net 110 fixes per 1,000 cells;
uniform across columns 48; random 148. In hindsight, over the cells asked, the 600 lowest-sensitivity cells give 132
and the 600 highest 120, so sensitivity does not sort cells by how much a second look pays, in either direction.
What sensitivity does predict is the *32B's own accuracy* on the column (−0.67), exactly as it predicts the 7B's,
DocETL's and Llama's. The two facts together say: a sensitive cell is one the document under-determines, and a
stronger reader cannot determine it either (the 32B is right on 24% of cells in the 0.8–1.0 band, the 7B on 14%);
the cells a stronger reader *fixes* are determined ones the weak reader misread, which sit in low-sensitivity
columns with low accuracy, such as dates written in another format (art.death_date: sensitivity 0.06, the 32B fixes
84% of the 7B's errors; birth_date 0.12 and 73%). Per column, sensitivity and the share of wrong cells the 32B fixes
are unrelated (ρ = −0.09, 27 columns). In the terms of FORMAL.md §2: disagreement is sound for detecting
under-determination, and under-determination is not repaired by re-asking; agreement-with-error is the shared-bias
case, and when the bias is the reader's (a format habit) a different reader repairs it. The technique that follows
from P1 is therefore not "re-ask where sensitive" but "do not spend readers where sensitive; change the specification
or ask a person there, and spend stronger readers where a column is determined yet wrong". The paper should state
I2's result as this correction. Numbers: `I2-secondlook/summary.json` (allocations, by_sensitivity_bin, per_column).

**I3b on basketball players (freeze on the better of two contexts): the transfer prediction holds, and more.**
Over the same 193 queries DocETL scores 0.164 with frozen columns against 0.108 with its own per-query extraction
(join queries 0.022 → 0.055, non-join 0.177 → 0.252; 66 queries better, 35 worse), at 2,821 calls against 34,719
and a twelfth of the tokens. The player–team join key matches 0.41 of rows against 0.19 (gold 0.63). The one key
that got worse, team.location = city.city_name (0.165 → 0.045), is a column both of whose first two contexts were
poor (17 and 25 of 30 documents filled, accuracy 0.17); I3c's stopping rule targets exactly that case. The
instructive part is that *per column* the frozen values are mostly less accurate than the original's pooled values
(draft_pick 0.95 → 0.63, nba_championships 0.72 → 0.15), yet the *queries* score higher: one value per cell, used by
every query, with keys that agree across tables, is worth more to a join or a GROUP BY than higher per-prompt
accuracy that differs from query to query. That is P2 stated as a design rule: consistency of a stored value across
its uses matters more than the accuracy of any one extraction of it. DocETL's own two-context disagreement (over
documents both contexts answered) tracks the 7B's sensitivity only weakly here (−0.26, 20 columns; several columns
have fewer than ten such documents), so the label-free sensitivity measured inside DocETL needs more than two
contexts, which I3c provides. On papers the same rule gave 0.101 against 0.122, so the gain is corpus-dependent:
largest where queries join and group (players), smallest where they mostly filter single tables (papers).

**I3c (keep drawing contexts until one fills half the documents, at most four) and a third source of
non-idempotence.** Papers: 0.113 against the original's 0.122 at 6,613 calls (4.7× fewer), 31 queries better and 28
worse, so the determined-context rule essentially matches per-query extraction on the corpus where freezing had hurt
most, with paper_name now filled for 200 of 200 documents on its fourth context after 0, 2 and 6. Players: 0.119
against 0.108, below the two-try run's 0.164. That gap led to a check that changes how all three DocETL comparisons
must be read: DocETL sets no temperature, so its calls are sampled, and the same prompt on the same documents returns
the identical value in only 69–100% of cases between two runs (median about 0.85 per column; `I3d` replicates I3b to
bound the spread). Sampling is therefore a third reason a stored value is not the value, alongside the prompt's
context and the model, and it applies to the original per-query DocETL run as much as to the frozen ones. Until the
replicate reports, the defensible statement is: freezing each column on a determined context gives DocETL between
0.113 and 0.122 on papers (original 0.122) and between 0.119 and 0.164 on players (original 0.108) at a fifth to a
twelfth of the calls, with joins consistently better (0.022 → 0.041–0.055) and the player–team key match 0.28–0.41
against 0.19.

**Frozen contexts are also the cheap contexts (from the E14-bgroup and recorded streams, unlimited budget, 100%
drift).** When every on-demand patch asks for the table's whole set of new columns (so each column is always
extracted in the same context), the stream reads each document once for all of them instead of once per query's
missing columns: tokens fall to 30% of the recorded run's on papers, 35% on players, 27% on artists, 17% on medical
and 22% on legal (patches 7 → 4, 8 → 4, 9 → 2, 14 → 3, 6 → 1), and the score rises on artists (0.256 → 0.272),
medical (0.115 → 0.140) and legal (0.170 → 0.192) while falling on papers (0.153 → 0.131) and players (0.387 →
0.378). This is the cost lemma (FORMAL.md §3) inside the stream: a column the next query might need costs its field
line, not another read of the document, so asking for all of them at the first patch is anticipation at the cheap
rate. It also means I4's budget comparisons between the frozen and recorded families must be read on absolute tokens
(each family's budgets are shares of its own unlimited spend, 3–6× apart); the analysis now reports score against
tokens for both.

**I1 on the 32B (papers, players, artists; 15 documents per table; 20 columns).** The same picture at higher accuracy:
sensitivity ranks the columns the same under the kinds of change (0.59–0.91 between pairs); sensitivity vs accuracy
alone −0.79; agreeing lone answers right 72% of the time, differing ones 14%. The 32B is less sensitive on average
(0.21 against the 7B's 0.25 on the same columns) and its per-column sensitivity correlates 0.60 with the 7B's; the
7B's sensitivity predicts the 32B's accuracy at −0.71. Prediction (c), that the 32B is never more sensitive, fails on
5 of 20 columns (by 0.05 or more), so "less sensitive on average" is the defensible form. One difference from the 7B:
the 32B's accuracy is highest in the natural group (0.66 against 0.57 alone; 7 columns better alone, 4 better
grouped), where the 7B's was flat; a larger model makes more use of co-asked columns. `I1-context/summary.json`.

**I3d, the replicate of the two-try run on players.** 0.145 against the first run's 0.164 over the 193 drift queries
(original 0.108); over all 274 queries 0.150 against 0.154; 150 of 274 queries score identically and the mean
absolute per-query difference is 0.06. Join queries 0.029 (first run 0.055; original 0.022); player–team key match
0.23 (0.41; original 0.19). So the headline holds under sampling, +34% to +52% over per-query extraction at a twelfth
of the calls, while the join improvement is real but its size is within the sampling spread. The paper should report
both runs.

**I4, the forecast policy and frozen contexts under a budget (level 100, budgets 25% and 50%, five corpora).**
*The forecast policy never beats first come, first served:* with contexts frozen, forecast − fcfs is −0.011 on
average over ten streams, 0 wins and 6 losses (by more than 0.002), at 95% of the tokens; the one large loss is
medical at 50% (−0.055), where skipping an early expensive patch with no known reuse lost the columns that later
queries needed most. The reason is the one the design of the benchmark forces: under column drift the columns in
demand are exactly those no known query uses, so a reuse forecast has no history to forecast from until the first
request, and the first request is itself the best predictor of reuse (57–100% of columns asked once are asked again).
First come, first served *is* the forecast policy in that regime. Prediction I4 therefore fails, and it fails for a
reason that generalizes: forecasting pays only where the workload repeats templates (PreView's setting), not where
it drifts.

*What does move the budget curve is the extraction unit, not the schedule.* Compared on absolute tokens (each
family's percentage budgets are shares of its own unlimited spend, which differ 3–6×), freezing each table's new
columns into one prompt dominates the recorded one-prompt-per-query policy on four of five corpora: players 0.348 at
0.98M tokens against the recorded 0.293 at 2.8M; artists 0.197 at 0.8M against 0.191 at 2.5M; medical 0.122 at 1.2M
against 0.115 at 13.1M; legal 0.192 at 4.3M (unlimited) against 0.170 at 19.8M. Papers is the exception: equal at
0.1M tokens (0.131 against 0.120) but the recorded run reaches 0.153 at 1.2M where the frozen one stops at 0.131,
because grouping lowers the accuracy of papers' most used columns (Section 1). Across the recorded sweep the five
scheduling policies we tried move the score by at most ±0.01 at a given budget; changing what one prompt asks for
moves the tokens needed for a given score by 3–10×. That is the cost lemma and the context finding together, and it
is the budget section's conclusion: *decide the unit of extraction by each column's context effect, then spend first
come, first served.* `WHY/i4/summary.json`, figure `figures/w12_budget_curves.png`.

*Pacing with frozen contexts (all ten streams, 2026-10-09 12:24).* Pacing loses to first come, first served by 0.034
on average (1 win, 6 losses), and the frozen context exposes the mechanism: a frozen patch reads all of a table's
new columns in one prompt, so it is one large indivisible spend (players: 0.98M tokens at the first query), and a
rule that releases the budget in proportion to the stream's progress cannot afford it until late. On players at 50%
the paced stream skips the first query's patch and the 101 later queries that need the same table, spends 0.55M of
its 1.0M on two small patches, and scores 0.142 against 0.348 for fcfs, which spent 0.98M at query 0 and answered 111
queries. With per-query contexts (the recorded runs) patches are small and pacing is a wash (+0.006, 6 wins, 4
losses). *The unit of extraction decides which budget policies are admissible:* grouping makes spending lumpy, a
lumpy spend needs a lump-sum rule, and pacing assumes divisibility. This completes the budget conclusion: choose the
unit by the context effect, then spend first come, first served, because the policies that smooth spending are the
ones the unit breaks.

*The forecast policy without frozen contexts* is a wash against the recorded fcfs streams: +0.005 on average at 86%
of the tokens, 4 wins and 6 losses; gains on artists (+0.037 at 25%, +0.064 at 50%), losses on papers, medical and
legal (−0.014 to −0.025). With per-query contexts every skipped patch changes the prompt a column is later read in,
so the per-corpus sign is the value effect of the pacing analysis, not the schedule; the comparison that holds the
prompt fixed (frozen forecast against frozen fcfs: −0.011, 0 wins) is the one that tests the policy. Prediction I4
fails in both forms.

**I3d on papers.** The second two-try run scores 0.093 against the first's 0.101 (original 0.122; 116 of 143 queries
identical), so on papers the determined-context rule stays about 20% below per-query extraction in both runs, and
the sampling spread (about 0.01 on the mean) does not change either corpus's conclusion.

**Queued 2026-10-09 10:40, predictions written before the runs (from WORKLOAD_AWARENESS.md §3).** All on the gpu lane
after I5, so nothing shares the 7B server.
- *I2b, the verifier as the router of second looks* (`exp_secondlook`: allocations `classifier`, `disagreeing`,
  `classifier_per_token`, 600 cells each, 1,280 new 32B reads; the verifier's scores are out-of-fold by column).
  Prediction: `classifier` and `disagreeing` catch more wrong cells than `by_sensitivity` (whose selection is 0.62
  wrong) because they add disagreement and empties; per dollar `classifier_per_token` is best, since the price of a
  fix is the document's length; `classifier` alone may not beat `most_sensitive_first` per dollar, because its top
  cells are artists' empties in long documents (525 of 600 are art). A failure would be the classifier's top cells
  being empties the 32B also leaves empty: then net fixes per cell fall below random, and the verifier is a detector
  of under-determination, not of fixable error.
- *I6, the label contract* (`QUWARTS_LABEL_CONTRACT`, five columns: art.century; legal.judgment_year,
  defendant_current_status; drug.recommended_usage, activation_conditions). Prediction: on art.century the merged and
  other-form rows (now about 60%) fall by at least half; legal.judgment_year becomes nearly exact; the corpus scores
  move by under 0.01 because the contracted columns are few. Papers and players have nothing to contract (their
  GROUP BY columns are declared, in the build, or identifiers), which is itself the result: the vocabulary is rarely
  what is missing.
- *I7, per-column read windows* (`QUWARTS_WINDOW_SHARES`, learned label-free from where the 7B's own stated values
  sit; players 0.29–0.53, papers 0.33–0.90, artists 0.10–0.88, medical 0.54–0.89; legal none). Prediction: patch tokens
  fall by about half on players and 15–30% elsewhere, scores within 0.02 of the recorded 100% stream; artists' birth
  and death dates (windows of a tenth) stay as accurate, because the value is in the first lines, and any loss
  concentrates in list columns whose later items the window cuts.

**I1, field order (Q4 of LITERATURE_IDEAS.md): the same fields in another order, 7B, 24 columns of the natural
groups, 30 documents each (`I1-context/summary.json`, `order_effect`).** Shuffling the field lines changes 40% of
the cells' values and reversing them 44%, against 44% for adding six random fields to a column asked alone and
5–6% for the same prompt run twice (E1.1). *The order of the fields is as much of the context as the set of fields*,
and the columns it moves are the same ones (Spearman 0.83 between a column's order change and its set sensitivity):
lists 0.56 and categories 0.52 against numbers 0.15 and yes/no 0.10. The mean accuracy does not move (0.388 natural,
0.381 shuffled), the columns do: papers' `agent_framework` (allowed values Other, Multi-Agent Collaboration, CoT,
ToT; gold null for 25 of 30 papers) is answered 'Other' on 28 of 30 when it is the first field line and left empty
on 25 of 30 when it is the eleventh or the last (accuracy 0.20 against 0.77), while `reasoning_depth` splits 19/11
multi-hop/single-hop in one order and 13/17 in another with no accuracy change. Two readings: a field answered first
is answered before the model has placed the document (it picks a label from the allowed list), and an
under-determined mapping flips with any perturbation of the prompt, sampling excluded. For the paper this closes the
question of what "context" means: not a semantic interaction among fields but the prompt's arrangement, which is
why the determinacy of a column is measurable with any cheap perturbation (Section 3's ten-document estimate) and
why a canonical context has to be frozen as a byte string, order included (P2). It also suggests an intervention
we have not run: place a column whose gold is mostly empty after the fields that make its absence evident
(`use_agent` before `agent_framework`), a layout rule that costs nothing.


**I5, the build's prompt groups (all ten streams, 2026-10-09 17:51; `WHY/i5/summary.json`).** Every new column read
alone (`alone`), or the I1 rule (`chosen`: a column more accurate alone on the 30-document sample gets its own prompt,
the rest stay grouped), level-0 build, scored on the 0% stream. *The per-column prediction transfers from 30 documents
to the whole build:* the five columns I1 flagged as better alone gain +0.136 (alone) and +0.138 (chosen) in cell
accuracy, four of five up by more than 0.02 and none down in the chosen run; the nine columns I1 flagged as better in
the group gain +0.005 when read alone (five of nine down); the ten with no difference +0.018. *The query score does
not follow:* alone +0.011 papers, +0.006 players, +0.004 artists, −0.028 medical, +0.002 legal; chosen −0.000 to
−0.010 on every corpus. The two legal runs are the same prompts (all five columns alone) and differ by 0.006, the
noise floor. Prediction I5 fails on its first half (chosen beats neither grouping on artists) and holds on its second
(the gain sits where I1 said). Three mechanisms, visible query by query: (1) *form*: legal `judge_name` goes from 0.03
to 0.45 correct because the lone prompt writes 'Flick' where the group prompt wrote 'Justice Flick', and the GROUP BY
on it moves +0.03; (2) *emptiness*: `defendant_current_status` alone leaves 214 cells empty against 85 in the group
(0.65 → 0.48) and the filters on it select other rows; (3) *aggregates over a changed numeric column*: artists'
`awards` loses 0.07 alone and AVG(awards) by continent loses 0.45; medical's COUNT(manufacturer) and
COUNT(single_dose) lose 0.37 as the lone prompts fill and empty different cells. The context effect is per column and
predictable, but at the cell level it is mostly a change of form and of emptiness, which queries that group, filter
or aggregate see as a mixed bag; and it is expensive, since a column alone costs a document (cost lemma): `alone`
spends 2.8–6.4× the supplement tokens, `chosen` 1.5–4.7×. The decision this supports: choose the grouping for cost
and consistency, harvest the per-column gains through normalization where they are form (a view rule maps 'Justice
Flick' to 'Flick' for nothing), and read a column alone only when its emptiness or selection matters to a query and
the document is short.

**I3c on artists (2026-10-09 19:05).** The determined-context rule (up to four draws until a context fills half the
documents) scores 0.191 against per-query DocETL's 0.188 (18 queries better, 23 worse) at 26,075 calls against 55,860
and 33M tokens against 74M. 18 of 24 columns settle on their first context, 2 on the second, 1 on the third, 3 never
reach half fill in four. Across the three corpora the rule holds per-query accuracy within 0.01 (papers −0.009,
players +0.011, artists +0.004) at 13–45% of the tokens; the reduction is smallest on artists because its documents
are short (the call, not the document, dominates) and the rule's extra draws cost whole passes over 1,000 documents.

**I6, the label contract, artists and medical (2026-10-09 19:34; legal running).** *Artists:* declaring the four
labels of `century` raises the column from 0.195 to 0.382 correct and the corpus score from 0.256 to 0.275; the six
queries that group by century go from 0.216 to 0.350, all six up. The fate of its 709 gold rows shows what the
contract does and does not do: "own label in another form" falls from 50% to 6% ('20th century' becomes '20th'),
exact rises from 27% to 52%, and *merged rises from 23% to 43%*: once the forms are fixed, the model's choice between
'20th' and '19th-20th' is exposed as a judgment it gets wrong on four rows in ten. *Medical:* the two contracted
columns are multi-valued, and listing 7 and 16 allowed values made the model select more of them: `recommended_usage`
falls from 0.204 to 0.051 correct (17 distinct labels served against 12), `activation_conditions` from 0.153 to
0.133; the corpus loses 0.013 and the six grouping queries fall from 0.099 to 0.054. Prediction I6 (merged rows fall
by at least half, scores move under 0.01) fails in both directions and for a reason worth stating: *a vocabulary
fixes form, not selection.* On a single-valued column whose labels are forms of a stated fact, the contract converts
"other form" into "exact" and the residual is the mapping judgment; on a multi-valued column an allowed-values list is
an invitation to select, and selection is the under-determined part. Papers and players had nothing to contract.

**I7, per-column read windows, papers, players, artists (2026-10-09 19:10; medical running).** Tokens: papers
×0.88, players ×0.41 (the first-window ablation: ×0.58), artists ×0.75. Scores: papers 0.1533 → 0.1533, players
0.387 → 0.366 (−0.021), artists 0.256 → 0.257. Per column the window is a double-edged change of context. *Artists'
dates improve by a lot:* `birth_date` 0.38 → 0.79 and `death_date` 0.31 → 0.56 when the read stops at a tenth of the
article: the first paragraph states the full date, and the chained read of the whole article returns the year alone
('1917' against '1917/6/4'), so the window removes both the distractors and the chunk reduction that coarsened the
value (the same effect as a narrower prompt). *Lists lose:* `field` 0.13 → 0.03,
`birth_city` 0.39 → 0.28, since items sit beyond the window. *Absence-coded counts collapse:* players'
`nba_championships` 0.95 → 0.40 and `fiba_world_cup` 0.86 → 0.25. Their windows (0.33, 0.32) were learned from the
17–18 players for whom a count is stated; for the majority, whose gold is 0 because nothing is stated, the model
needs the whole entry to answer 0, and with a cut entry it leaves the cell empty (79 of 133 players against 0 before),
"never null" notwithstanding. *A window can locate a
stated value but cannot establish an absence*, so the position rule must exempt columns whose gold is mostly a
coded absence (fill of the stated sample below about a third), and lists whose items scatter. Prediction I7 holds
on tokens (players about half, others 12–25%) and on where losses sit (lists), fails on players' score by 0.001
beyond its 0.02 margin, and missed the absence mechanism and the date gain.

**I2b, the verifier as the router of second looks (2026-10-09 20:07; 1,280 new 32B reads, 2,999 cells with a second
look in all; `I2-secondlook/summary.json`, `router.json`).** Routing 600 cells by the verifier's P(wrong) selects
cells that are wrong 99% of the time (592 of 600, against 360 for random and 527 for most-sensitive-first), and the
32B fixes 75 of them while breaking 3: net 72, $0.52, 137 net fixes per dollar. Random: net 89 (114 fixed, 25
broken), $0.55, 163 per dollar. Most-sensitive-first: net 66, $0.44, 152 per dollar. Disagreeing-first: net 49, 88
per dollar. P(wrong) per token: net 14 (the cheapest high-scoring cells are empties in short documents that stay
empty). Prediction I2b fails, and in the way its failure clause foresaw: *the verifier is a detector of
under-determination, not of repairable error.* Of the wrong cells it selects, 13% are repaired; of random's, 32%.
Fitting the same label-free features to the outcome "wrong and repaired by the 32B" on all 2,999 cells gives AUROC
0.53 out-of-fold by column (against 0.84 for "wrong"): *no label-free feature predicts which wrong cells a stronger
reader repairs*, and the coefficients that do appear point away from the verifier's (less sensitive, not fully
grounded, lists). Repair rates by kind are flat and low: lists 23% of wrong cells, numbers 19%, free text 14%
(categories 43% and yes/no 50% on tens of cells). What is left to a router is cost: most-sensitive-first pays
$0.44 for 600 cells because sensitive columns sit in short documents, and that, not fixability, is why it is close
to random per dollar. The honest conclusion for the cascade section: a second look repairs about a fifth of wrong
cells whoever chooses them; choose them by price, and spend the verifier on what it can do, which is to say which
cells not to trust (99% precision at 600) rather than which to re-read. The repairable cells are the misreadings of
determined columns (I2: dates fixed 73–84%), and finding those needs a per-column estimate from a few labelled cells,
not a cell-level label-free score.

**I7 on medical (2026-10-09 20:41).** Windows (shares 0.54–0.89 on 8 of 14 columns) score 0.1217 against the recorded
0.1152 at 89% of the tokens; the first-window ablation scores 0.126 at 79%. Per column the changes are small (−0.03
to +0.07, `single_dose` +0.07, `risk_factors` +0.03, `affected_organs` −0.03), so on a corpus of long documents with
list columns whose items scatter, the learned windows are safe but save less than the fixed cut, because the stated
items the shares were learned from sit late (p90 0.77–0.93). Across the four corpora: tokens ×0.41 to ×0.89, scores
−0.021 to +0.007, with the gains and losses concentrated in a few columns of a predictable kind.

**I6 on legal (2026-10-09 20:47).** The contract on `defendant_current_status` (38 labels) and `judgment_year` (4)
lifts the corpus from 0.170 to 0.269 and the seven grouping queries from 0.174 to 0.315 (4 up, 0 down); the status
column goes from 0.425 to 0.479 correct with merged rows down from 25% to 15% (66 distinct labels served against 23:
the model also combines allowed values), the year column slips from 0.996 to 0.963. Most of the corpus gain is in
queries that *filter* on the status ('Government', 'Company'), which now match the form the queries compare with:
the literal gap closed by declaration. The two contracted columns' prompts are in every legal patch, so all 570
documents were re-read; a replicate run is queued to bound the sampling share of the +0.099.

**I2b addendum: repairability is a column property, and ten labelled cells find it (`I2-secondlook/router.json`,
`per_column_estimate_from_10_labelled`).** Over the 25 columns with 20 or more second looks, the net repair rate of a
second look ranges from −0.67 to +0.56 per cell (median 0): artists' `death_date` +0.56, `birth_city` +0.54,
`birth_date` +0.43, papers' `agent_framework` +0.29, legal's `defendant_current_status` +0.26, and columns where the
32B breaks more than it fixes. Estimating each column's rate from ten labelled second looks and routing 600 looks
to the held-out cells by that rate gives net 189 fixes (20 draws, sd 12) against 59 for random and 68 for
most-sensitive-first; by rate per dollar 181 fixes for $0.45 (402 per dollar against 123 for random); the hindsight
column order gives 206. So the cell-level verifier cannot see repairability (AUROC 0.53) but the column can: a
stronger reader repairs misreadings of determined columns (dates in another format, a city named in the first
line), and which columns those are is learnt from a handful of labels, not from label-free features. *The cascade
router is a per-column table of repair rates, estimated from ten cells each, with price in the denominator.* That is
also the shape of the budget result and the context result: the column is the unit of every decision in this
system.

**I1-position, the layout rule (2026-10-09 21:56; 24 columns, 30 documents each, the focal column first or last
among the same fields; `I1-context/summary.json`, `position_effect`).** Last beats first by 0.046 on average (0.385
→ 0.430; the build's alphabetical order sits at 0.388) with fewer empties (0.34 → 0.30); 8 columns are better last
by 0.05 or more and 7 better first. The gain is in numbers (+0.15: artists' `awards` 0.20 → 0.60 and players'
`nba_championships` 0.13 → 0.43, "never null" counts that are left empty on 87% of documents when asked first and
on 47% when last) and categories (+0.30: `agent_framework` 0.20 → 0.80, filled with 'Other' when first, left empty
when last, which gold mostly is); lists −0.01 and free text −0.06. The rule I proposed ("a mostly-empty column goes
last") is not what the data say: the share of empty gold does not predict the gain (Spearman −0.22; mostly-empty
columns +0.075, the rest +0.031, on 8 and 16 columns), and the two mechanisms run in opposite directions, a count
is *filled* when last and a label is *dropped* when last. What holds is narrower and still useful: *the first field
line is answered differently from the rest*, by up to 0.6 per column, so position is a free per-column knob the
30-document test can set (as it set the grouping in I5), and a canonical prompt must fix the order (P2). An
extraction harness that puts a column first because a query asked for it (DocETL's per-query maps, where the
requested field heads the list) pays this on every such column.

**I7b, the window rule with its exemptions, and I6rep on artists (2026-10-09 21:33; `WHY/i7b_windows`,
`WHY/i6rep_contract`).** *Players:* with the two count columns exempt (whole entries again), their accuracy is the
recorded one, the five windowed columns stay within ±0.07, tokens are 62% of recorded, and the score is still
0.355 against 0.387 (I7: 0.366). The loss is the same three queries as in I7: filtered aggregates over two or three
rows (`AVG(draft_pick)` and `SUM(draft_pick)`, `SUM(draft_year)` for one nationality), 1.0 → 0.0, which hinge on
single cells that the 0.53 and 0.48 windows changed; `draft_pick` 0.70 → 0.68 and `draft_year` 0.78 → 0.77 in
accuracy. *Per-column accuracy within 0.02 is no safety margin for an aggregate over a filter that keeps three
rows* (the aggregate finding, again). I7's spurious gain on `fiba_world_cup` queries (+1.5 in summed score while the
column fell from 0.86 to 0.25) is gone with the exemption, which is why I7b scores lower than I7 although its cells
are better. *Artists:* exempting the lists took the dates' gain with it: `birth_date` is back to 0.38 (I7: 0.79)
because its patch prompt also asks `nationality` and `birth_city`, both exempt, and a prompt takes the largest
share, so the whole article is read again; `death_date` keeps +0.25 (its prompt's columns are all windowed); tokens
97% of recorded, score unchanged. *Exemptions propagate through grouping*: a column's window applies only when every
column in its prompt has one, so windows and grouping have to be planned together (a dates-only prompt at a tenth of
the article plus the lists' prompt at the whole costs 10% more tokens than one prompt and gains 0.25–0.41 on the
dates: an accuracy decision, not a cost one, like I5). *I6rep on artists:* the contract's gain replicates (0.279
against the first run's 0.275, recorded 0.256; century 0.376 against 0.382; the six grouping queries 0.392 against
0.350), so the +0.02 on artists is not sampling.
