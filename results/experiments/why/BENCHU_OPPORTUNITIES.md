# Bench-U (UDA-Bench, BIT-DataLab, technical report, 29 pp.): what it covers, and where our work adds knowledge

Date: 2026-10-10. Source: `technical_report.pdf` and the repository (`Query/`, `evaluation/`, `systems/`). Our
benchmark is a fork of it: the same `Query/<Dataset>/<Dataset>_attributes.json` files (Art 26 attributes against
their 25, CSPaper 17 against 19, Legal identical), the same document sources, their SQL files under
`Select/Filter/Agg/Mixed/Join`, from which our drift designs draw their 27–118 test queries per corpus. So every
number we have is already on Bench-U's data; what differs is the question asked and the metric.

## 1. What Bench-U establishes

An experiments-and-analysis paper: 6 datasets (ours plus Finance, 100 reports of 130k tokens, and Healthcare,
100,000 documents), 608 queries in five categories, 175 attributes with hand-labelled ground truth (30 annotators,
4,110 hours; inter-annotator agreement 0.88–0.98 on a 191-document sample), 7 systems (Evaporate, Palimpzest,
LOTUS, DocETL, ZenDB, QUEST, UQE) run *one query at a time* with GPT-4.1-mini, scored by tuple-level precision,
recall and F1 with an LLM judge for lexical variants, exact match for MIN/MAX, bounded relative error for the other
aggregates; cost in thousand tokens per document per query; latency in seconds per document per query.

Its findings, each about *which system or technique*, not about *why a value comes out as it does*:
- chunking does not help on short documents and every system struggles on long ones; retrieval is the lever for
  long documents but prunes chunks that held the answer (Insights I–IV; Opportunities I, III);
- extracting the attribute and then checking the filter beats asking the LLM for a boolean (Observation I);
- document-level dynamic plans (QUEST) beat corpus-level ones (ZenDB) on cost (Observation II);
- model selection and cascades (Palimpzest, LOTUS) save cost on the easy dataset and not on the hard one;
- transforming a join into a filter (QUEST) saves cost but loses accuracy; search-based join pruning prunes
  joinable documents (Table 8, Figure 11);
- clustering chunks for aggregation is cheap and inaccurate (Figure 10, Opportunity V);
- few-shot prompts best for extraction, chain-of-thought for filters; better embeddings help retrieval; LLM ranking
  Gemini > GPT > Claude > DeepSeek > Qwen > Llama with cost not following accuracy;
- the stated gaps: finer retrieval and multi-round extraction, multi-modal alignment, chunking, end-to-end
  optimization across retrieval, extraction, filtering, joining and aggregation.

What it does not have, and cannot see with its design:
- **No notion of a workload.** Each of the 608 queries is run and paid for independently; nothing is kept between
  queries, so amortization, reuse, drift, and the cost of anticipating a column do not exist in its model.
- **No notion that a read is a measurement.** A cell's value is treated as a property of (document, attribute,
  system). The same system re-extracts the same attribute in different prompts across queries, and because each
  query is scored alone, inconsistency across queries is invisible.
- **No per-attribute difficulty measure.** "Certain attributes require multi-step reasoning" is stated, not
  measured; per-attribute results are not released; difficulty is attributed to documents (noise, length) and to
  systems, never to the attribute's determinacy.
- **No mechanism for its observations.** Why extract-then-check beats a direct boolean, why retrieval prunes the
  right chunk, why trans-join loses accuracy, why cascades help on Art and not on Legal: described, not explained.
- **No consistency requirement for joins.** Keys are extracted per query, per system.

## 2. Where we add knowledge, ranked

### A. The workload view of Bench-U: amortized cost and consistency across its own queries (strongest, cheapest)

*What they measure:* thousand tokens per document per query, per query. *What we show:* over a workload the
relevant quantity is tokens per document per query *amortized over the queries that reuse a column*. On players our
planner spends 4.4M tokens on 200 documents for 118 queries, about 0.19k tokens per document per query, against
their cheapest system's 2.06k (QUEST) and DocETL's 54k, with higher accuracy on our metric than DocETL's on theirs.
On the four shared datasets this is a factor of ten below the cheapest system in their Table 3 and three orders of
magnitude below the most expensive, and it comes from one decision their systems cannot make: keep what you read.
Add the consistency metric they lack: for a per-query system, the share of (document, attribute) cells whose value
differs between two queries that extracted it (DocETL on our data: 69–100% identical for identical prompts, 37–42%
changing with the field set), and show the join and GROUP BY scores that follow from it.

*Work:* run the planner on the full Bench-U query sets of the four shared datasets and Finance (the catalogue
planner reads a table's schema once, so the number of queries is nearly free), score with their evaluation code
with the exact-match comparator and with a local judge through Ollama's OpenAI-compatible endpoint, and report
their metrics beside ours. About 8 hours of GPU for the five datasets, 6 hours of adaptation. Healthcare's 100,000
documents are out of reach for a 7B on two slices and are left to the limitations.

### B. Determinacy as the difficulty of a Bench-U attribute, label-free, and what it predicts

*What they have:* 175 attributes and the judgment that some need multi-step reasoning. *What we add:* a number per
attribute, the two-context disagreement from ten documents, that predicts accuracy at −0.7 across models and across
systems (DocETL −0.73 on 40 shared columns), marks the cells no stronger model repairs, and separates
under-determination from misreading. Published as a table over all 175 attributes it becomes an artifact other
groups use: which Bench-U attributes are under-determined, by kind (lists and categories first), and which are
merely hard to read. *Work:* the probe over the 175 attributes on ten documents each, 3,500 prompts, two hours;
correlate with their per-dataset F1 by category and with DocETL's per-attribute accuracy, which we hold.

### C. Why retrieval prunes the answer: a window cannot establish an absence

*What they observe:* retrieval-based systems (QUEST, ZenDB) lose on Legal and Finance, "erroneously prune text
chunks that contain valuable information"; chunking helps nowhere on short documents. *What we found:* a read window
locates stated values and cannot certify an absence; on a "0 if none" count read from a cut entry the model leaves
79 of 133 cells empty; lists lose items past the window; dates gain when the chained whole-document read is cut to
the first paragraph. Bench-U's own attribute files are full of absence-coded attributes ("leave empty if not
applicable", "0 if none": fine_amount, legal_fees, nba_championships, awards, evidence, first_judge, the Finance
amounts). *Prediction to test on their data:* retrieval systems lose F1 specifically on absence-coded and list
attributes relative to whole-document systems, and not on stated single-valued ones. *Work:* their per-attribute
outputs are not released, so this needs one retrieval system run on the shared datasets (QUEST is in their
`systems/`), about a day; or, cheaper, our own planner with and without windows on the absence-coded attributes,
which we have already run (I7, I7b) and can report on their attribute taxonomy today.

### D. Why extract-then-check beats a direct boolean: the predicate in the prompt moves the value

*What they observe:* decomposing a filter into extraction and comparison is more accurate (Observation I,
Summary II). *The mechanism we can measure:* a value extracted with the predicate in the prompt is a different
measurement from one extracted without it. We have the prompt mode (`render_prompt` with the SQL context and "do not
copy SQL constants") and the usage-phrase ablation; an intervention on fixed documents, each column with and without
its query's predicate, counts the cells that flip toward satisfying the predicate ("predicate leakage"), by kind and
by determinacy. *Work:* an I1-style harness, 39 columns, thirty documents, one hour of GPU; the prediction is that
leakage is concentrated in under-determined columns, where the model has no stated value to hold on to.

### E. Why cascades help on Art and not on Legal, and how to route them

*What they do:* model selection and cascades per query with a target accuracy (Palimpzest, LOTUS), helpful on Art,
not on Legal. *What we found:* a stronger reader repairs misreadings of determined columns and nothing else; no
label-free feature predicts which cells it repairs (AUROC 0.53), but ten labelled cells per column do (net repair
rates from −0.67 to +0.56; routing by them gives three times random's repairs); the price of a look is the
document's length, so a cascade is budgeted in tokens. Art is short documents with determined columns (dates,
cities); Legal is long documents with under-determined ones (statuses, labels). That is their observation with a
mechanism and an estimator. *Work:* none beyond the write-up; optionally the column-rate router on their Art and
Legal attributes with GPT-4.1-nano/mini if an API budget appears.

### F. Why trans-join loses accuracy: keys are extracted once or not at all

*What they observe:* QUEST's join-to-filter transformation and search-based join pruning lose accuracy. *What we
found:* keys extracted per query match 18–19% of rows; extracted once with one definition, 75%; the same key in two
prompts is two measurements. *Work:* the write-up, plus the consistency metric of A applied to the join keys of
Player and Med.

### G. Aggregates: the label mix, not the cell accuracy, decides COUNT and GROUP BY

*What they do:* score aggregates by bounded relative error per group; cluster chunks for cheap group-bys
(inaccurate). *What we found:* label collapse (23% of gold rows merged into another group), the direction of each
aggregate's error (max from one inflated cell, counts from every misclassified row), a vocabulary fixes form, not
selection, and in the planner a GROUP BY score moved by +0.07 while per-cell accuracy moved +0.02 because the label
mix changed. *Work:* report on their Agg category with their relative-error metric once A is run.

### H. Prompt arrangement as a factor they did not vary

Their prompt ablation varies zero-shot, few-shot and chain-of-thought. The field set and the field order inside one
prompt change 37–44% of cells, as much as the model does; the first field line is answered differently from the
rest. Their systems feed one attribute at a time (LOTUS, UQE) or all at once (Palimpzest, DocETL) without noticing
that this is a measurement choice. *Work:* the write-up; optionally the position effect on their attribute lists.

## 3. What we should not claim

Their systems ran GPT-4.1-mini; our reader is a 4-bit Qwen 7B, so accuracy comparisons against their Table 3 are
not like for like, and the honest claims are about cost per document per query amortized over a workload (A),
about consistency (A, F), and about mechanisms that hold across models (B, C, D, E: our cross-model rank 0.77 says
the attribute properties transfer). Healthcare is out of reach. The inter-annotator sample is not released, so the
test that human disagreement coincides with LLM two-context disagreement waits on the authors.

## 4. Order

A (the workload view on their benchmark, with their evaluation code) is the one that changes the paper: it makes
Bench-U's numbers the baseline table and our planner the system. B, C and D are new knowledge each measurable in a
few hours on hardware we have. E, F, G, H are write-ups of results in hand, placed against their observations.

## 5. Status, 2026-10-10 10:15: the pipeline runs, first numbers on their metric (exact match, no judge)

Bench-U's current evaluation package (`evaluation_benchu/`, their `run_eval` with the alignment ids and the join
aliasing their ground-truth runner uses) scores the planner's served tables on their query files
(`quwarts/eval/exp_benchu.py`): the run's final table gets their id columns, every query is executed as their
evaluator rewrites it for the ground truth, and `run_eval` compares per column. Exact matching (their LLM judge for
lexical variants is available through the local 7B, but it calls the model once per non-identical cell, thousands of
calls per Select query, so it is used on samples only). The planner's run at 100% drift, ten-sample rules (V2):

| dataset | queries | mean F1, scored | mean F1, unanswerable as 0 | Select | Filter | Join | Agg | Mixed | k tokens / doc / query |
|---|---|---|---|---|---|---|---|---|---|
| Player | 144 | 0.572 | 0.401 | 0.66 | 0.48 | 0.59 | 0.96 | 0.62 | 0.17 (their cheapest 3.8, DocETL 54) |
| CSPaper | 86 | 0.377 | 0.377 | 0.59 | 0.26 | | 0.91 | 0.26 | 0.05 (6.2, 41) |
| Art | 86 | 0.315 | 0.296 | 0.47 | 0.26 | | 0.50 | 0.29 | 0.05 (0.75, 6.6) |
| Med | 132 | 0.197 | 0.125 | 0.35 | 0.16 | 0.05 | 0.53 | 0.20 | 0.47 (their Healthcare is another set) |
| Legal | 86 | 0.397 | 0.397 | 0.52 | 0.30 | | 0.70 | 0.70 | 0.36 (6.2, 93) |

Unanswerable queries are those on columns the drift workload never requested (Player's owner table, Med's
institution table, Art's image-only `theme`): the planner on *their* workload reads them on first touch, which is
the queued V3-benchu run; on papers that run already answers every query (F1 0.376, the same table) at 0.039k
tokens per document per query without the build and about 0.07k with it, against their cheapest 6.2k. Their Table 3
numbers are GPT-4.1-mini with a judge; ours are a 4-bit 7B with exact matching, so the accuracy columns are not
like for like (their Select F1 on Player 0.84–0.89, CSPaper 0.56–0.65, Art 0.58–0.65, Legal 0.57–0.68), and the
claim this supports is the cost one: the same families of query answered from one kept table at one to two
orders of magnitude fewer tokens per document per query than any per-query system in their table. Their harness's
own failures on their own queries (DuckDB rejects `avg(TIME)` on two Med aggregates; `theme` is absent from their Art
ground truth) are left as unanswerable.
