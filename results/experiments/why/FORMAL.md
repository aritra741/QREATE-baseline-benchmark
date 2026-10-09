# Formal statements: extraction context, determinacy, the cost of anticipation, and budgeted extraction

Draft of the paper's definitions section (plan item 1–3 in RESEARCH_DEPTH.md). Everything here is stated so that it
can be checked against the measurements in `WHY/context/summary.json`, `WHY/cost/summary.json` and the I1–I4 runs.

## 1. Extraction context and the value of a cell

Let D be a corpus of documents, A a set of columns, and M a model. An *extraction context* for a column a ∈ A is

  c = (F, C, I, M),

where C ⊆ A with a ∈ C is the set of columns asked in the same prompt, F gives the field specification of every column
in C (name, type, description, allowed values, nullability), I is the instruction text, and M the model. Two contexts
are *admissible* for a if their specifications of a have the same meaning (the same name and type, descriptions that
are paraphrases of each other). Everything else about them may differ.

The *value* of a cell is v(d, a | c) ∈ Dom(a) ∪ {⊥}: what the model returns for document d and column a when asked in
context c. In a conventional database a stored value has no third argument. We say a column is *idempotent* under a
family of admissible contexts if v(d, a | c) = v(d, a | c′) for all d and all c, c′ in the family. Idempotence is what
caching, materialized views, and key-based joins assume.

The *context sensitivity* of a with respect to two admissible contexts is

  s(a; c, c′) = Pr_d [ norm(v(d, a | c)) ≠ norm(v(d, a | c′)) ],

the share of documents whose value changes, after the normalization the scorer uses (case, whitespace, numbers as
numbers). s(a) denotes the mean over a set of context pairs. A cell (d, a) is *determined* by the document if every
admissible context returns the same value, and *under-determined* otherwise. An *unsafe cell*, by analogy with an
unsafe tuple in conformance-constraint discovery, is a cell on which two admissible contexts disagree: the value
depends on how the question was asked.

## 2. Proposition (agreement is sound, not complete)

Let g(d, a) be the gold value and let c, c′ be admissible contexts.

(i) *Soundness.* If v(d, a | c) ≠ v(d, a | c′) then at most one of the two values equals g(d, a). So disagreement is
evidence of an error without any gold data: on a disagreeing cell at least one of the two contexts is wrong, and a
context chosen without knowledge of g is wrong with probability at least 1/2.

(ii) *An accuracy bound.* Let acc(c) be the accuracy of context c on column a over the corpus, and s = s(a; c, c′).
Then

  (acc(c) + acc(c′)) / 2 ≤ 1 − s / 2.

Proof: on the (1 − s) share of agreeing cells the two contexts are both right or both wrong, contributing at most 1−s
to the average; on the s share of disagreeing cells at most one is right, contributing at most s/2. The bound explains
the empirical rule "no column with more than about 55% disagreement is right more than 60% of the time" (the bound at
s = 0.55 is 0.725; the measured accuracies lie well below it, so the bound is loose but in the right direction, and it
is model-free).

(iii) *Incompleteness.* Agreement does not imply correctness. If the admissible contexts share a bias b, a map from gold
values to other values that does not depend on C, I or M (for instance a label vocabulary that merges two gold
categories, or a reading of the description under which a count is left empty), then v(d, a | c) = v(d, a | c′) = b(g(d,
a)) ≠ g(d, a) for every context. Agreement-based trust therefore has no false alarms for under-determination, and
misses exactly the errors that come from a shared bias. Measured: on category columns, cells where two prompts agree
are wrong more often (57%) than cells where they disagree (49%), whereas on numbers, lists and free text disagreement
raises the error rate from 18–49% to 71–81%.

(iv) *Transfer.* If the bias is a property of the column (its description, its gold vocabulary) rather than of M, then
(i)–(iii) hold for any model, and s(a) measured with one model predicts the accuracy of another. Measured: s from the
7B predicts the 32B's accuracy at −0.62, Llama's at −0.48, DocETL's at −0.73.

## 3. Lemma (the cost of anticipating a column)

Let a build prompt for document d already be sent, with T_d document tokens and I instruction tokens. Adding column a
costs f_a tokens (its field line and its answer; 84 at the median). Extracting a later for the same document costs
T_d + I + f_a. If the document is longer than the window W, it is read in k_d = ⌈T_d / W⌉ chunks and the field line is
paid per chunk.

Let p be the probability that some later query needs a, and let the later extraction read a fraction σ ≤ 1 of the
documents (the scope that the query's filters select). Over n documents,

  cost(anticipate) = Σ_d k_d f_a,     E[cost(later)] = p σ Σ_d (T_d + k_d (I + f_a)).

Anticipation is worth it when p exceeds the *break-even probability*

  p* = Σ_d k_d f_a / ( σ Σ_d (T_d + k_d (I + f_a)) ).

Two consequences. For documents within one window (k_d = 1), p* ≈ f_a / (σ (T + I + f_a)): the threshold is the ratio
of field tokens to document tokens, divided by the scope. For long documents, T_d / k_d ≈ W, so p* does not fall below
f_a / (σ (W + I + f_a)) however long the documents are: the window, not the document, sets the floor (about 0.8% at
W = 10k and f_a = 84, against 1.9% measured on medical and legal, where σ < 1 and I is paid per chunk). Scope explains
why the measured break-even on papers and artists (13.1%, 12.2%) exceeds the σ = 1 prediction (9.9%, 9.3%).

Corollary (what limits anticipation). In the benchmarks 59–86% of schema columns are used by some query, far above p*,
so by cost alone every column would be anticipated. The limit is Section 2: adding columns to C changes v(d, a | c)
for the columns already there (37–42% of cells change between a narrow and a wide context) with no consistent
direction, so the choice of C is an accuracy decision, not a cost decision.

## 4. Problem (budgeted extraction with deferred, shared value)

Queries q_1, …, q_n arrive in order. Before q_i the system holds extracted columns E_i (each with its context). A patch
P at step i extracts a set of (column, document scope) pairs; its cost is cost(P | E_i), which depends on E_i because
columns already present let filters narrow the scope (pushdown); its value is

  V(P | E_i) = Σ_{j ≥ i} [ score(q_j | E_j ∪ P) − score(q_j | E_j) ],

shared with every later query that uses its columns. The online problem is to choose patches with Σ cost ≤ B to
maximize Σ_j score(q_j | E_j).

Three measured properties shape any policy. (P-a) Most of V(P | E_i) lies in j > i (54–97% of the score gain goes to
later queries). (P-b) cost(P | E) is history-dependent: removing a predecessor can raise a patch's cost from 1 document
to 29. (P-c) If the context in which P runs depends on E_i (the patch asks whatever else is missing), then by Section 2
the values, and so V, depend on *when* P runs, not only on whether it runs.

The policies we tried each violate one of these. A per-patch cap bounds cost(P) alone and discards the patches with the
largest V (rank correlation of cost with value 0.28–0.63 on four corpora). Pacing bounds cumulative cost, which moves
P in time and so changes its context (P-c): its effect is the sum of a predictable delay cost and an unpredictable
value change, and the sign differs by corpus. The hindsight oracle and the offline knapsack use the true V but price
P as if E were fixed (P-b). A policy consistent with P-a to P-c (i) forecasts reuse from the known workload rather than
judging a patch by its own query, (ii) holds each column's context fixed so that V(P) is a function of E alone, and
(iii) extracts filter columns first so that cost(P | E) is as small as it can be. I4 tests (i) with and without (ii).

## 5. Statement (coarsening and aggregate sensitivity)

Let the extracted value of a numeric column be v̂ = v + ε. For a group G, MIN(v̂) < MIN(v) only if some ε < 0 reaches
below the minimum; if extraction errors are rarely downward (measured: 2% of MIN groups too low), the minimum is wrong
only when its row is missing. MAX(v̂) ≠ MAX(v) whenever any single ε > 0 exceeds the gap to the maximum, so one inflated
value anywhere in G decides it (21% too high, 20% too low). AVG and SUM average ε over G, so zero-mean errors cancel
(54% and 63% of groups within 20%). COUNT(G) changes by one for every row whose group label is merged into or out of
G, so it inherits the label-collapse rate of the GROUP BY column (23% of gold rows merged into another group), and its
low pooled score is a corpus effect, not a property of counting. For a GROUP BY column, the share of gold rows that keep
their exact label falls with the number of ways a value can be written: numbers 94–96%, categories 57%, yes/no 70%,
lists 29–30%.
