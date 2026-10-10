# What the semantic-query and LLM-database communities assume, and where our findings give them something

Date: 2026-10-09. A survey of the two areas you named (semantic query processing; LLM-based databases) plus the adjacent
ones they grew out of or depend on (ML-over-unstructured-data query processing, quality-aware extraction optimizers
from the 2000s, caching of model outputs, and the LLM-behaviour literature on prompt sensitivity and nondeterminism).
The point of each section is not the catalogue but the assumption those papers make that our measurements bear on,
written as a question she would ask: a property, an effect, and why, with who else benefits from the answer.

## 1. The landscape in one page

**Semantic query processing** adds LLM-evaluated operators to relational plans and optimizes them.
[LOTUS](https://www.vldb.org/pvldb/vol18/p4171-patel.pdf) (VLDB 2025) defines semantic filter, join, top-k, group-by
and aggregate; each operator's correct answer is *the strongest model applied exhaustively* ("our gold algorithm runs
batched LLM calls over all tuples"), and the optimizer lowers cost with statistical guarantees relative to that gold
run by scoring rows with a cheap proxy (a small model's log-probabilities, or embeddings for joins), labelling a 0.01%
sample with the oracle, and setting pass/fail thresholds by a normal approximation (the SUPG recipe). It processes
rows one per prompt on purpose, "rather than batching multiple tuples within a single prompt invocation", because of
long-context degradation, and it notes that input order "can in fact affect results quality" for aggregates. It says
nothing about reusing outputs across queries and has no token cost model (cost is calls and seconds).
[Palimpzest](https://www.vldb.org/cidrdb/papers/2025/p12-liu.pdf) (CIDR 2025) treats an AI pipeline as a logical plan
and searches physical plans over model choice, code synthesis, "multi-data prompt marshaling" (several fields in one
call) and input trimming; quality is estimated against a *champion model* standing in for ground truth on a 5%
sample; marshaling is treated as a cost question ("process the input tokens just once"), not an accuracy one, and
caching is at dataset granularity with per-record caching as future work. [QUEST](https://arxiv.org/abs/2507.06515)
(VLDB 2025) builds a two-level index so that only the relevant text segments go to the model, orders filters per
document by selectivity × cost, and turns joins into filters. [Larch](https://arxiv.org/abs/2606.07923) learns
selectivities for semantic predicates; [PLOP](https://arxiv.org/pdf/2604.09944) places semantic operators in hybrid
plans by cost; [Sema](https://arxiv.org/pdf/2603.11622), [Stretto](https://arxiv.org/pdf/2602.04430) and
[Kalypso](https://arxiv.org/abs/2607.23815) are execution and serving engines (Kalypso reuses KV-cache state between
pipelined operators); [Cortex AISQL](https://arxiv.org/abs/2511.07663) is Snowflake's production engine (AI-aware
planning, adaptive cascades, join rewriting); [SemBench](https://arxiv.org/abs/2511.01716) benchmarks LOTUS,
Palimpzest, ThalamusDB and BigQuery. The whole area optimizes *where and how often to call the model*; it takes what
the model returns as given.

**LLM-based databases over documents** split into per-query extraction and offline extraction, exactly the axis of
our work. Per-query: [DocETL](https://arxiv.org/abs/2410.12189), [ReDD](https://arxiv.org/abs/2511.02711) (query-
specific schemas, extraction errors detected by classifiers on hidden states with coverage guarantees and a human
correction budget), [UQE](https://arxiv.org/abs/2407.09522), ZenDB, QUEST. Offline: Evaporate, SQUiD, Map&Make,
and QuWARTS. [UDA-Bench](https://arxiv.org/abs/2510.27119) and our demo paper state the trade-off (per-query is
accurate and slow, offline is fast and inaccurate) but neither side has said *why* per-query extraction is more
accurate, and our frozen-DocETL runs say the usual answer is wrong: per-query values are not more accurate per cell,
they are differently inconsistent per query. [Indexing long documents](https://arxiv.org/abs/2608.21237) (VLDB 2026
PhD workshop) reuses a text index across questions. [Research challenges for RDBMSs running LLM queries]
(https://arxiv.org/abs/2508.20912) lists planners treating LLM calls as black boxes, prefix-cache sharing across
low-cardinality columns, and "due to their non-deterministic nature, LLMs can generate syntactically inconsistent
outputs", but has no challenge about reusing outputs across queries. The
[LLM × DATA survey](https://arxiv.org/abs/2505.18458) covers the field without this question either.

**The lineage both areas descend from, mostly uncited.** Query processing over expensive ML models on unstructured
data was worked out for video: [BlazeIt](http://www.bailis.org/papers/blazeit-vldb2020.pdf) (aggregates with
error bounds via proxies as control variates), [SUPG](https://arxiv.org/abs/2004.00827) (selection with precision or
recall guarantees from a proxy and a labelled sample; the method LOTUS reuses), [TASTI](https://arxiv.org/abs/2009.04540)
(one embedding index built once serves many queries' proxies: "removes the need for per-query proxies"), and now
[task cascades](https://arxiv.org/abs/2601.05536) and [streaming cascades](https://arxiv.org/abs/2604.00660). Earlier
still, the quality-aware optimizers for information extraction: the
[SQoUT project](https://ipeirotis.org/publication/building-query-optimizers-for-information-extraction-the-sqout-project/)
(SIGMOD Record 2008; "Join Optimization of Information Extraction Output: Quality Matters!", ICDE 2009) chose per
query among retrieval, extraction and join strategies by cost *and* output quality, and
[Cyclex](https://scholars.duke.edu/publication/807128) (ICDE 2008, "Efficient information extraction over evolving
text data") recycled earlier extraction results over a changed corpus by a cost-based choice between redoing and
reusing; [DeepDive](https://arxiv.org/abs/1502.00731) made knowledge-base construction incremental. The LLM era
changed two things these papers assumed: the extractor is not a trained program with fixed behaviour but a prompt whose
answer depends on its context, and the cost of a read is dominated by the document rather than by the extractor.

**Caching model outputs.** Semantic caches reuse an answer for a similar prompt; [vCache](https://arxiv.org/abs/2502.03771)
(ICLR 2026) makes the reuse decision with a user-set error bound; [FinCacheServe](https://arxiv.org/pdf/2607.26076)
argues reuse must follow a dependency contract (evidence, model identity, generation parameters, document version)
and draws on materialized-view maintenance. None treats *the prompt's other fields* as a dependency of the value.

**LLM behaviour.** [Sclar et al.](https://arxiv.org/abs/2310.11324) (ICLR 2024): meaning-preserving format changes
move accuracy by up to 76 points and the sensitivity correlates only weakly between models. [Semantic entropy]
(https://www.nature.com/articles/s41586-024-07421-0) (Nature 2024): hallucinations are detected by the entropy of
*sampled* answers to one fixed prompt, clustered by meaning. [Thinking Machines](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/):
temperature 0 is not deterministic (80 distinct completions in 1,000 runs) because reduction kernels depend on batch
size. [Joint extraction matters](https://arxiv.org/abs/2503.16868): asking several fields in one prompt helps when the
fields are interdependent. [Murin 2026](https://arxiv.org/abs/2606.05970) on clinical discharge summaries: cross-prompt
agreement κ ≈ 0.69, the disagreement concentrated on "absent versus not documented" (our empty-vs-filled axis), and
model choice dominating prompt phrasing for categorization.

## 2. The assumptions our measurements touch, as why-questions

Each entry: the assumption in the literature; what we measured; the question; what to test; who benefits. They are
ordered by how much they would change what those communities do.

### Q1. What does an accuracy guarantee "relative to the oracle" mean when the oracle's answer depends on how it is asked?

*Assumption.* LOTUS, SUPG, Palimpzest, task cascades, Cortex AISQL and ReDD all define correctness as agreement with
the strongest model run in the most expensive way; the guarantee is "within ε of the gold run with probability 1−δ".
The gold run is one prompt per row, one context, one sample.

*What we measured.* Across 39 columns the same document, column and model give a different value in 37–42% of cells
when the prompt's other columns change (7B, 32B and Llama alike); DocETL's own sampled calls return the identical
value for the same prompt only 69–100% of the time; the 32B's per-column sensitivity correlates 0.60 with the 7B's;
and (FORMAL.md §2) when two admissible contexts disagree on a cell at most one is right, so the mean accuracy of any
pair of contexts is at most 1 − s/2.

*The question.* Is the oracle's self-disagreement a floor on what any guarantee relative to it can mean, and does the
cascade's "error" concentrate in exactly the rows the oracle itself cannot determine? If so, a guarantee should be
stated on the determined part of the data and the under-determined part reported as irreducible, which is a
different, more honest contract than ε.

*Test (cheap, with what we have).* The I1-32B logs give the 32B's own disagreement per column between contexts. For a
semantic filter such as `uses_reranker = Yes` over papers, run the SUPG recipe with the 7B's log-probabilities as
proxy and the 32B as oracle; split the proxy's "errors" by whether the 32B agrees with itself across two contexts on
that row. Prediction: most proxy errors sit where the oracle disagrees with itself, and re-labelling those rows by a
second oracle context changes the gold labels by about the oracle's sensitivity. A second test uses sensitivity itself
as the proxy score (it is label-free and needs ten documents) against log-probabilities.

*Who benefits.* Every system with an oracle-relative guarantee: the guarantee becomes "ε on the determined rows,
plus a measured share of under-determined rows", and optimizers stop spending oracle calls where no oracle can settle
the answer.

### Q2. Which statistics should a semantic query optimizer keep per column, and are they properties of the data or of the model?

*Assumption.* Semantic optimizers estimate selectivity and cost by sampling the model per query (QUEST, Larch, PLOP,
Palimpzest's sentinel plans) and quality by a champion model. Nothing is kept across queries except embeddings.

*What we measured.* Context sensitivity is a column property: it ranks columns the same under five kinds of prompt
change (0.82–0.93), across three models (0.53–0.61), and it predicts accuracy for our system, the 32B, Llama and
DocETL (−0.63 to −0.79); ten sampled documents estimate it to −0.66 against −0.72 for the full corpus. Fill rate per
context is the second statistic (it is what the first query's prompt gets wrong in DocETL).

*The question.* Should a catalogue for LLM-derived columns hold *determinacy* and *fill* the way a relational
catalogue holds cardinality and selectivity, and what decisions do those two numbers settle: plan quality without a
champion model, cascade routing, which columns to materialize, which to send to a person?

*Test.* Replace Palimpzest's champion-model quality estimate with sensitivity measured on its sentinel sample and
compare plan choices; use sensitivity as the proxy in a SUPG cascade (Q1).

*Who benefits.* Optimizer builders (QUEST, Larch, PLOP, Palimpzest, Cortex): one statistic computed once per column,
stable across models, in place of per-query sampling of a champion.

### Q3. Why does per-query extraction score higher than an extracted table, when its values are not more accurate?

*Assumption.* UDA-Bench, our demo, DocETL and ReDD say per-query extraction is more accurate because each prompt is
tailored to the query. The offline camp accepts it.

*What we measured.* In DocETL's original run, a column's share of non-empty answers ranges from 1% to 100% depending
on which query's prompt extracted it (paper_name over 44 prompts: median 0.53); the same prompt returns the same value
69–100% of the time; freezing each column on its first context loses accuracy (players 0.108 → 0.054), freezing it on
a context chosen by fill rate wins (0.145–0.164 at a twelfth of the calls), and the win comes *despite* lower
per-column accuracy than the original's pooled values, because a join or a GROUP BY needs one value per cell, the
same for every query and agreeing across tables.

*The question.* Is "consistency of a value across its uses" the property that per-query systems lack and offline
systems have by construction, and can it be bought at per-query prices by choosing one canonical context per column
without labels? Where does it fail (papers: queries that filter single tables by the query's own constants, where the
tailored prompt's spelling matches the constant)?

*Test.* I3b/I3c are the test; I3d bounds sampling. The remaining piece is the failure case: measure, per query, whether
its filter constants appear in the frozen values' spelling, and whether entity normalization (what the QuWARTS build
does) recovers the papers loss.

*Who benefits.* The per-query systems (a 10× cheaper mode with better joins), the offline systems (an explanation of
when they lose and a fix that is not "extract per query"), and Cyclex/DeepDive-style incremental extraction, which
gets a new rule for what to recycle: a value is reusable only with its context.

### Q4. Do prefix-sharing and KV-cache optimizations preserve the answers?

*Assumption.* [Liu et al.](https://arxiv.org/abs/2403.05821) reorder rows and *fields within a row* so that shared
prefixes hit the KV cache (up to 4.4× faster); the RDBMS-challenges paper proposes "reordering columns based on
cardinality"; Kalypso reuses KV state across operators. All assume the output is invariant to the reordering.

*What we measured.* The co-asked columns change a value in 37–42% of cells. **Answered 2026-10-09 (I1, 7B, 24
columns, 30 documents each): invariance is false.** Shuffling the field lines with the set held fixed changes 40% of
the cells' values, reversing them 44%, against 5–6% for the same prompt run twice; the columns that move are the
sensitive ones (Spearman 0.83 with set sensitivity; lists 0.56, categories 0.52, numbers 0.15, yes/no 0.10). Mean
accuracy is unchanged (0.388 against 0.381), single columns are not: papers' `agent_framework` is right on 20% of
documents when it is the first field and 77% when it is the eleventh or last (first, the model picks 'Other' from
the allowed list; later, it leaves the cell empty, which gold mostly is). Sclar et al.'s format sensitivity holds for
extraction at the cell level, and it holds for the cheapest format change there is.

*The question, now a claim.* A serving optimization that reorders fields for cache hits changes about four
cells in ten, concentrated in the columns that are under-determined anyway; it is a correctness constraint on the
plan, like a non-commuting operator, and the constraint is checkable without labels (determinacy from ten documents).
The constructive side: order is a free knob, and we measured it (24 columns, each first and last among the same
fields): last beats first by 0.046 on average with fewer empties, per column by up to 0.6, numbers and categories
gaining, lists and free text not; but the share of empty gold does not predict the direction (Spearman −0.22), so
the layout rule we proposed does not hold and the knob has to be set per column from a small sample, like the
grouping.

*Test (one evening with the I1 harness).* Add a context kind "same set, shuffled order" and a kind "same set, prefix
reordered as Liu et al. would" for every column; measure per-column change rate and query-score change on the
0% stream. This is the cheapest new result on the list and the one two optimization communities most need.

*Who benefits.* Serving and planning work that reorders prompts for cache hits; they get the set of columns for which
reordering is safe (low sensitivity) and the ones for which it is not.

### Q5. Is grouping fields into one prompt a cost decision or an accuracy decision?

*Assumption.* Palimpzest treats marshaling as cost ("process the input tokens just once"); LOTUS avoids batching rows
for quality; the joint-extraction paper says joint helps when fields are interdependent; practitioners split prompts
"to improve accuracy".

*What we measured.* On average the context does not move accuracy at all (0.37–0.41 across five contexts) while
individual columns move by up to ±0.4 in either direction; by cost, asking a column alongside others is almost free
(the break-even is field tokens over document tokens), and grouped patches cost 17–35% of ungrouped ones.

*The question.* Can the right grouping be chosen per column from a measured context effect rather than by a global
rule, and is the saving on cost (3–6×) larger than any accuracy effect (±0 on average)? I5 (running) tests a grouping
derived from I1 against all-alone and all-together.

*Who benefits.* Palimpzest-style optimizers get a quality model for marshaling; LOTUS gets a reason its row-batching
caution is right for rows and wrong for fields.

### Q6. What must a store of LLM-derived values record so that reuse is sound?

*Assumption.* Semantic caches key on prompt similarity; vCache bounds the error of reusing a similar prompt's answer;
FinCacheServe keys on evidence, model and generation parameters; Palimpzest caches datasets by name. None records
the prompt's other fields, and none treats a repeat of the same prompt as a new measurement.

*What we measured.* Three independent sources make a stored value differ from a recomputed one: the context (37–42%
of cells), the model (sensitivity correlates 0.6 across models, so the same column moves differently), and sampling
(0–31% of cells per column between identical runs). Keeping the context fixed per column removed the timing effect
entirely (463 of 467 queries identical) and the pacing noise.

*The question.* What is the minimal provenance for an LLM-derived cell, (document, column, context, model, sample),
and which reuse rules follow: same context ⇒ reuse; different context ⇒ a new measurement whose disagreement with
the stored one is itself the trust statistic (Q2)? This is materialized-view maintenance with a new kind of
dependency, and the professor's own line of work (data trust, conformance) has the vocabulary for it.

*Who benefits.* Caching systems (a dependency they do not track), incremental KBC (what to recycle), and anyone
building a feature store from model outputs.

### Q7. Why do budget and anticipation policies collapse to first-come-first-served under drift, and what is the right forecast?

*Assumption.* Workload-aware systems (PreView, QuWARTS, view selection) forecast demand from history; LOTUS and
Palimpzest optimize per query with no notion of future queries.

*What we measured.* 54–97% of an extraction's value goes to later queries; under drift the demanded columns are
exactly those with no history, so a reuse forecast has nothing to forecast from and loses to FCFS (I4 on papers:
−0.024 at the 25% budget); meanwhile the break-even probability for anticipating a column is 1–13%, and grouping
new columns into the first patch gets 3–6× cheaper reads.

*The question.* Is "the first request is the forecast" a theorem under column drift (the first demand for a column
predicts its reuse at 57–100%), and does the cheap anticipation rule (ask for every plausible column at the first
read of a document) dominate forecasting? If so, the workload's role is not to predict *which* columns but to set
the schema's vocabulary and groupings, which is what QuWARTS actually uses it for.

*Who benefits.* Workload-aware materialization (PreView's own problem) and the per-query systems, which currently
re-read documents per query.

### Q8. Which errors does a stronger model fix, and which does nothing fix?

*Assumption.* Cascades (LOTUS, task cascades, streaming cascades, Cortex) escalate "uncertain" rows to a stronger
model; ReDD escalates detected errors to humans under a budget.

*What we measured (I2).* Sensitive cells are under-determined by the document and the 32B is wrong on them too (24%
right against the 7B's 14% in the most sensitive band); the cells a stronger reader fixes are determined ones the weak
reader misread (dates: 73–84% fixed). Allocation by sensitivity does not beat random; sensitivity predicts the
stronger model's accuracy (−0.67) but not fixability.

*The question.* Can a cascade be routed by *kind of error*, under-determined rows to specification repair or a person
(ReDD's human budget), misread rows to a stronger model, and does that beat uncertainty-based escalation at equal
cost? The split is label-free: disagreement between two cheap contexts marks under-determination; agreement with a
wrong-looking format marks misreading.

*Who benefits.* Every cascade; the human-correction budget in ReDD; and the clinical-extraction literature, where
Murin's "absent versus not documented" axis is the same under-determination.

### Q9. Which aggregates can be trusted over LLM-extracted values, and can a query planner know in advance?

*Assumption.* Error-aware query answering (ReDD) and approximate query processing over ML (BlazeIt's control
variates) treat error as a per-row quantity to bound.

*What we measured.* MIN is almost never too low (2%), MAX wrong in both directions, AVG and SUM cancel, COUNT inherits
label collapse (23% of gold rows merged into another group), and the same ordering holds in DocETL's outputs; the
collapse rate is a property of the value kind (numbers 94%, lists 29% keep their label).

*The question.* Can the planner attach an expected error to a query from its aggregate and its GROUP BY column's kind
before running it, as a cardinality estimate is attached today, and when does the estimate fail (DocETL's averages,
which read fewer rows)? This is robust statistics applied as a planning statistic.

### Q10. What survives from the quality-aware extraction optimizers of 2008 when the extractor is an LLM?

SQoUT chose among retrieval and extraction strategies by cost and quality with a trained extractor whose behaviour
was fixed; Cyclex recycled extraction output over evolving text by a cost model. Two of their premises fail now: the
extractor is a prompt whose output depends on context and sampling (Q6), and the cost of a read is the document, not
the extractor (the cost lemma). A short section in the paper tracing which of their trade-offs survive, which invert,
and which are new would place the work in a lineage the professor values ("workload gives hints; prefetch") and
that reviewers from the database side will recognize.

## 3. Which to pursue

Three stand out for her criteria (a property, an effect, a mechanism, a transferable rule) and for how little they
cost us:

1. **Q4, reordering is not free** (one evening on the existing harness). A crisp counterexample to an assumption two
   active communities build on, with the sensitive columns identified. Transferable as a correctness constraint.
2. **Q1 with Q8, guarantees and cascades relative to a self-disagreeing oracle** (a day; the I1-32B data already holds
   the oracle's self-disagreement). It reframes "accuracy guarantee" and "escalation" around determinacy, which is the
   paper's primitive, and it speaks directly to LOTUS, SUPG, Cortex and ReDD.
3. **Q3 with Q6, consistency and provenance of LLM-derived values** (already run; needs the failure-case analysis). It
   answers the question both camps of the LLM-database area argue about, with a mechanism and a cheap fix, and it
   gives the caching community a dependency they do not track.

Q2 (determinacy as a catalogue statistic) is the framing that ties these together for the paper; Q5, Q7 and Q9 are
sections we can already write from I1, I4/I5 and the breakdowns; Q10 is a paragraph of positioning.

## Sources

LOTUS: [VLDB 2025](https://www.vldb.org/pvldb/vol18/p4171-patel.pdf), [arXiv 2407.11418](https://arxiv.org/abs/2407.11418), [repository](https://github.com/lotus-data/lotus).
Palimpzest: [CIDR 2025](https://www.vldb.org/cidrdb/papers/2025/p12-liu.pdf), [arXiv 2405.14696](https://arxiv.org/abs/2405.14696).
QUEST: [arXiv 2507.06515](https://arxiv.org/abs/2507.06515). Larch: [arXiv 2606.07923](https://arxiv.org/abs/2606.07923).
PLOP: [arXiv 2604.09944](https://arxiv.org/pdf/2604.09944). Sema: [arXiv 2603.11622](https://arxiv.org/pdf/2603.11622).
Stretto: [arXiv 2602.04430](https://arxiv.org/pdf/2602.04430). Kalypso: [arXiv 2607.23815](https://arxiv.org/abs/2607.23815).
Cortex AISQL: [arXiv 2511.07663](https://arxiv.org/abs/2511.07663). SemBench: [arXiv 2511.01716](https://arxiv.org/abs/2511.01716).
Semantic filter paradigm (CSV): [arXiv 2603.04799](https://arxiv.org/abs/2603.04799).
Optimizing LLM queries in relational workloads: [arXiv 2403.05821](https://arxiv.org/abs/2403.05821).
RDBMS research challenges for LLM queries: [arXiv 2508.20912](https://arxiv.org/abs/2508.20912).
ReDD: [arXiv 2511.02711](https://arxiv.org/abs/2511.02711). Task cascades: [arXiv 2601.05536](https://arxiv.org/abs/2601.05536).
Streaming cascades: [arXiv 2604.00660](https://arxiv.org/abs/2604.00660). Indexing long documents: [arXiv 2608.21237](https://arxiv.org/abs/2608.21237).
UDA-Bench: [arXiv 2510.27119](https://arxiv.org/abs/2510.27119). LLM × DATA survey: [arXiv 2505.18458](https://arxiv.org/abs/2505.18458).
Small open-weight models for databases: [arXiv 2606.31808](https://arxiv.org/abs/2606.31808).
SUPG: [VLDB 2020](https://arxiv.org/abs/2004.00827). BlazeIt: [VLDB 2020](http://www.bailis.org/papers/blazeit-vldb2020.pdf).
TASTI: [arXiv 2009.04540](https://arxiv.org/abs/2009.04540).
SQoUT: [SIGMOD Record 2008](https://ipeirotis.org/publication/building-query-optimizers-for-information-extraction-the-sqout-project/), [Join optimization of IE output, ICDE 2009](https://www.researchgate.net/publication/220966214_Join_Optimization_of_Information_Extraction_Output_Quality_Matters).
Cyclex: [ICDE 2008](https://scholars.duke.edu/publication/807128). DeepDive incremental: [VLDB 2015](https://arxiv.org/abs/1502.00731).
vCache: [arXiv 2502.03771](https://arxiv.org/abs/2502.03771). FinCacheServe: [arXiv 2607.26076](https://arxiv.org/pdf/2607.26076).
Prompt format sensitivity: [Sclar et al., ICLR 2024](https://arxiv.org/abs/2310.11324).
Semantic entropy: [Farquhar et al., Nature 2024](https://www.nature.com/articles/s41586-024-07421-0).
Nondeterminism at temperature 0: [Thinking Machines, 2025](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/), [numerical precision study](https://arxiv.org/pdf/2506.09501).
Joint extraction: [arXiv 2503.16868](https://arxiv.org/abs/2503.16868). Clinical extraction sensitivity: [arXiv 2606.05970](https://arxiv.org/abs/2606.05970).
