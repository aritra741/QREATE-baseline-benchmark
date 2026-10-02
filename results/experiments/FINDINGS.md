# Experiment findings (running log)

Results of the experiment plan (`results/drift_design/EXPERIMENT_PLAN.md`), newest last. Every number links to the
file it comes from; step status is in `results/experiments/STATUS.md`. Model: Qwen 2.5 7B on local Ollama (4-bit
unless stated). Scores are per-query structure F2 × cell F1@0.20, averaged.

## Setup checks

**Replays reproduce the recorded runs exactly (cspaper).** All 30 recorded fixed4 streams (5 drift levels × unlimited
and 5 budgets) were re-run from the journals with every query's database kept, with model calls refused: 0 streams
differ in any query's action, missing columns, tokens or score
(`E2-replay/live/cspaper/verify.json`). The per-query analyses below use these databases.

**The error breakdown's scores match the recorded ones** (0 of 59 queries differ at 100% drift;
`E2.4-errors/cspaper/per_query.csv`).

## cspaper

### Patch cost estimates are accurate (E4.1)
Across 128 patches, estimated / actual tokens has median 1.001 and 10th–90th percentile 0.996–1.004
(`E2.2-patches/cspaper/summary.json`). **The budget anomalies are not caused by bad cost estimates.**

### Many patch tokens buy nothing (E2.2)
Share of patch tokens on patches whose query did not improve over static and whose columns no later query
improved with: 0% at 25% and 50% drift, 32% at 75%, 39% at 100% (unlimited streams; `E2.2-patches/cspaper/`).

### Cell values, not structure, limit cspaper (E2.4)
| System | Structure F2 | Cell F1@0.20 | No rows / structure / values / fully right |
|---|---|---|---|
| Static, 100% drift | 0.022 | 0.016 | 40 / 19 / 0 / 0 |
| Unlimited, 0% drift | 0.640 | 0.167 | 6 / 34 / 19 / 0 |
| Unlimited, 100% drift | 0.650 | 0.187 | 6 / 36 / 17 / 0 |
| 10% budget, 25% drift | 0.639 | **0.230** | 7 / 34 / 18 / 0 |
| 10% budget, 100% drift | 0.574 | 0.166 | 7 / 39 / 13 / 0 |

No query is fully right in any stream. Patching recovers the structure (rows and joins) static loses; what remains
is wrong cell values. The odd "10% budget beats unlimited at 25% drift" point is entirely cell F1 (0.230 vs 0.185).
(`E2.4-errors/cspaper/summary.json`)

### Reading a column can make a query worse than leaving it empty (E2.3)
Between a budgeted and the unlimited stream at the same drift level, 88 query answers differ; in 31 the budgeted
(fewer patches) answer scores higher, and 28 of those 31 were answered **without their own patch**. Of the cells
that differ, 12,241 are filled in one stream and empty in the other; only 455 hold two different values
(`E2.3-order/cspaper/summary.json`). Patches never overwrite: a (column, document) is read at most once per stream.

**Case: `agent_framework` (qualitative).** `SELECT agent_framework, COUNT(paper_name) FROM cspaper WHERE
data_modality = 'Text' GROUP BY agent_framework` (25% drift):

| | NULL | Other | ToT | CoT | Multi-Agent | Score |
|---|---|---|---|---|---|---|
| Gold (138 text papers) | 107 | 14 | 1 | 6 | 10 | — |
| Unlimited: patched for every paper | 27 | 82 | 23 | 11 | 12 | 0.32 |
| 10% budget: patch skipped, values from an earlier scoped patch | 129 | 16 | 3 | 4 | 3 | 0.64 |

`agent_framework` only has a value when a paper uses an agent framework; gold leaves it empty for 107 of 138 text
papers. Read for every paper, the model assigns a framework to papers that have none (82 "Other", 23 "ToT"). The
budgeted stream's only values came from an earlier query's patch, scoped by pushdown to the papers that query
selected, so the rest stayed empty, which is right for most of them.

**Which papers were read, and how well (per paper, against gold; 164 of 200 papers match a gold row):**
- The first query of the unlimited stream (a `retrieval_method` query that also needs `agent_framework`) read
  `agent_framework` for all 171 in-scope papers in one 197k-token patch. The 10% budget (116k) could not afford it
  and skipped it; later queries then read the column for 58 papers, each scoped by its own filter.
- On the 45 papers read in both streams, the values are **identical** (12 of 36 gold-matched correct in both): the
  patch prompt's context made no difference here.
- On the 116 papers read only by the unlimited stream, gold is empty for 78 of the 95 matched. The model gave **all
  116** a framework (77 "Other", 21 "ToT"); 13 of 95 are right. Left empty, 78 of 95 would have been right.

So the loss is from *which documents are read*, and from the model never answering "none" for this column. It is
not from the prompt's context.

**Interpretation (to test on the other corpora):** for a *conditional* column (one that applies only when another
holds), an unconditional read invents values, and a wrong value costs more than a missing one, because it moves rows
into wrong groups. This explains the budget anomalies better than the patch order alone: a budgeted stream sometimes
wins by reading *less*. It suggests two system changes to test: read a conditional column only on the documents where
its condition holds, and an explicit "not applicable" answer in the patch prompt.
