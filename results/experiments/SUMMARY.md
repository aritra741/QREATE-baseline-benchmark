# Experiment summary by research question

Current state of the findings, one section per research question (RQ1–RQ8 in `results/drift_design/EXPERIMENT_PLAN.md`).
Every number here is the latest valid one; the full record, with the evidence, case studies and superseded runs, is
`FINDINGS.md`. Token and latency accounting: `ACCOUNTING.md`. Step status: `STATUS.md`.

Setting: five corpora (cspaper, player, art, med, legal), Qwen 2.5 7B on local Ollama (4-bit unless stated), score =
per-query structure F2 × cell F1@0.20, averaged. Drift levels 0–100% withhold new columns from the build
(`attribute_pool` test set, 326 test queries, all with GROUP BY).

## Are the measurements trustworthy?

- **Replays are exact.** Every recorded drift stream (150 streams, five corpora) re-runs from its journals with model
  calls refused and reproduces every query's action, tokens and score. All per-query analyses build on these replays.
- **Run-to-run noise is small.** A whole drift stream re-run with every patch read again moves by 0.000 (cspaper) and
  +0.0015 (player, 95% CI −0.002 to +0.007), although a quarter to a third of responses differ in text. The player
  shared read varies by up to 0.012 on 20 held-out queries across three identical runs.
- **Quantization is a small, real effect.** 16-bit vs 4-bit: +0.03 on the shared read (held-out), +0.004 on a whole
  drift stream. 4-bit results are slightly pessimistic; comparisons on the same server are unaffected.
- **A prompt bug** (2026-10-01 23:40 to 10-02 13:20) invalidated 11 runs; all were re-run. A guard step now replays a
  recorded stream with calls refused before any GPU step.

## RQ1: lazy vs eager materialization under drift

Adaptive patching holds the score as drift grows; the static build collapses.

| Corpus | Static, 0% → 100% drift | Adaptive, 0% → 100% drift | Patch tokens at 100% |
|---|---|---|---|
| player | 0.379 → 0.040 | 0.379 → 0.387 | 5.7M |
| art | 0.270 → 0.031 | 0.270 → 0.256 | 6.1M |
| cspaper | 0.134 → 0.008 | 0.134 → 0.153 | 1.2M |
| legal | 0.121 → 0.005 | 0.121 → 0.114 | 29.9M |
| med | 0.095 → 0.031 | 0.095 → 0.086 | 19.9M |

Build costs of the 0–75% levels (E1.3): the measured W0 read plus exactly counted extra prompt lines, with only the
answer tokens estimated (12 per field; measured 9.5–15); accurate to within about 2%. **Reading ahead vs patching later (E1.4):** the drift
levels form an anticipation sweep. Anticipating every new column costs 0.07–0.74M extra build tokens; patching them
all later costs 1.2–29.9M, at about the same score (lazy ÷ eager total tokens 2.7–7.8×). A column is worth reading up
front if the chance a query will need it exceeds **1.3–1.6%** (player, med, legal) or 12–13% (art, cspaper): anticipate
generously, patch only what could not be foreseen.

**Robustness.** Four draws of the withheld columns (E11; cspaper, player) and build workloads cut to 10–50% of their
queries (E12; cspaper, player, art): static collapses at 100% drift every time; the patched curve stays flat, with no
significant 100% − 0% difference (−0.015 to +0.020). A smaller build workload leaves more columns to the patches and
costs more in total (art at 10%: 8.5M → 10.1M tokens; cspaper 10%: +23%; player 10%: +7%).

## RQ2: is a narrow patch read more accurate than a wide build read?

**No general effect.** The same 12 columns read 1, 3, 6 or 12 at a time (E2.1b): one column per read is better on
legal (+0.068 exact agreement) and player (+0.026), worse on art (−0.034), flat on cspaper, mixed on med, and always
6–10× the tokens. Narrow reads invent more values where gold is often empty (art: 98% of gold-empty cells filled at
width 1, 60% at width 12). The adaptive curve's small rises under drift (cspaper +0.02, player +0.01) come from
*which documents get read* (E2.3), not from prompt width.

## RQ3: budget policies for adaptive extraction

**The anomalies of first-come-first-served (fcfs) are explained.**
- Legal "25% budget beats 50%": the 50% budget spends 8M of 14.5M tokens on two early patches that buy nothing; the
  25% budget cannot afford them and spends on patches that feed 19 later queries.
- cspaper "10% budget beats unlimited": reading a column for every document can hurt (see RQ8, never-null metadata).

**Queries whose answer is MIN/MAX over a text column** (45 of 326) score 0.03 for every system yet take 33% of patch
tokens. A `fragile` policy that never patches for them (E3.3):

| Corpus | Mean score, fcfs → fragile | Tokens (25 streams) | Effect |
|---|---|---|---|
| legal | 0.1106 → 0.1136 | 219M → 158M (−28%) | budget collapses removed (50% budget at 100% drift: 0.053 → 0.107) |
| med | 0.0797 → 0.0828 | 154M → 130M (−16%) | monotone in budget; matches unlimited at ⅔ of its tokens |
| cspaper (control) | 0.1453 → 0.1453 | identical | exact no-op (no such queries) |

Generic policies (E3.2), mean score over 25 streams per corpus:

| Policy | cspaper | player | art | legal | med |
|---|---|---|---|---|---|
| fcfs | 0.1453 | **0.3363** | 0.2356 | 0.1106 | 0.0797 |
| fragile | 0.1453 | 0.3363 | 0.2356 | **0.1136** | **0.0828** |
| hindsight oracle | 0.1453 | 0.3363 | 0.2356 | 0.1129 | 0.0797 |
| per-patch cap | 0.1398 | 0.3076 | 0.2263 | 0.0992 | 0.0812 |
| pacing | **0.1466** | 0.3260 | **0.2405** | 0.1030 | 0.0821 |

**`fragile` is the only policy that never hurts** (a no-op where nothing matches, best on legal and med, at −16 to
−28% tokens there), and it matches or beats the hindsight oracle. Pacing wins on cspaper and art but loses on player
and legal; the cap is never best. Whether skipping helps tracks the share of wasted patch tokens: none on player
(where fcfs is best), a third on legal and med.

## RQ4: estimating cost and value

- **Cost estimates are accurate**: median estimated/actual patch tokens 0.997–1.005 on all five corpora.
- **Value is the hard part**: share of patch tokens that bought no score (on the query or any later query using the
  columns), unlimited at 100% drift: player 0%, art 16%, med 32%, legal 39%, cspaper 39%.
- Value signals visible in the SQL (E4.1, 138 patches, 29% of patch tokens wasted): **MIN/MAX over a text column**
  (68% of its tokens wasted; 73% of all waste) and **an unfiltered whole-corpus patch** (89% of all waste, but only
  44% of its own tokens wasted). Filtered patches waste 8%, AVG/SUM patches 1%.

## RQ5: the planner vs a single shared read

**Corrected (2026-10-04).** The earlier comparison (planner 0.340 vs shared read 0.560) mixed planning with input
information: the shared read had the benchmark's column descriptions, the planner's reads only names and types. With
the same information (E5.0), the shared read scores **0.234** on the 20 held-out player queries (1.25M tokens); the
planner matches it at a 25% budget (0.232, 2.6M) and beats it at 75–100% (**0.340**, 5.5–6.7M). The descriptions
themselves are worth **+0.33** (structure F2 0.42 → 0.87), the largest single effect measured.

Where the planner loses points (E5.1): at budgets up to 50%, mostly join keys it leaves unread (each such query
zeroes; the planner values columns one by one); at 75–100%, the values of columns it does read. With the descriptions too
(E5.2), the planner reaches 0.247 at 25% and 0.381 at 75%; weighting join keys as the whole query (E5.3) gives 0.422 at
75% but 0.199 at 25%. **No planner configuration reaches the shared read with descriptions (0.560 at 1.3M tokens)**:
the planner prefers per-query contexts and undervalues one shared read of every workload column.

**Unused budget** (player sweep: 4.86M planned of 10.58M available at 100%): the objective saturates (expected loss
0.027 per query, measured as disagreement with each query's own read), and "leave unread" is measured as nearly free
where a query's own probe reads were mostly empty (`player.team`: 0.13, so the join key stays unread). Spending the
budget on top of the shared read (E5.4) keeps its accuracy but adds only +0.002 to +0.006 at 2.2–3.8× the tokens. More
reads of the same documents with the same model buy little; descriptions (+0.33) and a stronger model (+0.13) are the
levers.

## RQ6: order effects and consistency

- Patches never overwrite: a (column, document) is read at most once per stream.
- Across budgets at the same drift level, differing cells are almost all filled in one stream and empty in the other
  (cspaper 12,241 vs 455 with two different values; player 38,028 vs 0).
- A budgeted stream beats unlimited on 8–31 queries per corpus, nearly all answered without their own patch: reading
  less sometimes helps (RQ8).

## RQ7: robustness to serving and model

Noise and quantization: see the first section. Other models (E6.2), all 4-bit on local Ollama:

| | Llama 3.1 8B | Qwen 2.5 7B | Qwen 2.5 32B |
|---|---|---|---|
| Player shared read, held-out 20 | 0.466 | 0.560 | **0.690** |
| Player, adaptive / static at 100% drift | 0.359 / 0.040 | 0.387 / 0.040 | **0.421** / 0.052 |
| cspaper, adaptive 0% → 100% drift (static at 100%) | 0.149 → 0.125 (0.008) | 0.134 → 0.153 (0.008) | 0.162 → **0.224** (0.008) |

The adaptive-vs-static result holds for every model at the same patch cost; model scale is the largest single effect
measured (+0.13 held-out from 7B to 32B), and the 32B model's adaptive curve rises under drift (cspaper +0.06).

## RQ8: where accuracy is lost

| Corpus | Bottleneck (unlimited, 100% drift) | Structure F2 / Cell F1 |
|---|---|---|
| player | cell values (rows and joins stay right; static loses only cells) | 0.753 / 0.468 |
| art | both | 0.527 / 0.340 |
| cspaper | cell values | 0.650 / 0.187 |
| legal | cell values | 0.758 / 0.168 |
| med | structure: too few rows (61 of 76 queries), list-valued join keys, exact comparison of free text | 0.335 / 0.157 |

Cross-cutting causes:
- **Benchmark metadata says "never null" where gold is often empty**: 69 of 132 never-null columns are empty in ≥5% of
  gold rows (57 used by the workloads); e.g. med `sequelae` 85%. The prompt must then invent values. Prompt-level
  fixes (dropping "Never null", a field-level null hint, relaxing only the contradictory field) move scores by −0.053
  to +0.020 on player and cspaper, and dropping "Never null" costs −0.043 on med (fewer invented values, many more
  missed ones): not a usable lever on this model.
- **Values right in substance, wrong in form**: lenient vs exact agreement, e.g. art `field` 0.92 vs 0.13; the
  benchmark's tolerant score is only 0.01–0.03 higher. Canonicalizing to the workload's vocabulary gains nothing
  (E8): the gaps are in GROUP BY labels the workload never names.
- **Query type** (E9): AVG/SUM 0.36, MIN/MAX over numbers 0.24, COUNT 0.21, MIN/MAX over text 0.03.

## Baseline: DocETL on the drift queries

DocETL (same model, one map per query and table, the fair prompt) at 100% drift, all 326 drift test queries; paired
difference with 95% bootstrap CI:

| Corpus | Queries | DocETL | Ours, adaptive | Ours − DocETL (95% CI) | DocETL tokens | Ours: build + patches | Ratio |
|---|---|---|---|---|---|---|---|
| player | 118 | 0.081 | 0.387 | +0.306 (+0.246, +0.367) | 190.6M | 7.71M | 25× |
| cspaper | 59 | 0.105 | 0.153 | +0.049 (+0.003, +0.093) | 20.7M | 1.56M | 13× |
| art | 43 | 0.167 | 0.256 | +0.089 (+0.047, +0.134) | 57.9M | 8.52M | 7× |
| med | 76 | 0.056 | 0.086 | +0.030 (+0.009, +0.054) | 170.6M | 22.47M | 8× |
| legal | 30 | 0.040 | 0.114 | +0.075 (+0.029, +0.124) | 475.1M | 34.49M | 14× |

On player DocETL scores 0.125 / 0.034 / 0.008 on queries with 0 / 1 / 2+ joins.

## Status (2026-10-04, job 16050764)

Done: replays and per-corpus analyses (all five corpora); noise, quantization; null handling (E7 family); prompt width
(E2.1b); canonicalization (E8); query types (E9); budget policies on all five corpora (E3.2, E3.3); other models
(Llama 3.1 8B, Qwen 2.5 32B); planner attribution and fixes (E5.0–E5.3); build-cost accuracy (E1.3); anticipation
(E1.4); patch-value signals (E4.1); token and latency accounting (`ACCOUNTING.md`); other drift draws (E11) and
smaller build workloads (E12: cspaper, player, art, med; legal running); DocETL on all 326 drift test queries.

Open:
- An offline best-possible budget policy (E3.1, a knapsack over patches re-scored by replay); the hindsight oracle and
  the `fragile` rule stand in for it now.
- A planner objective that can recognise a shared read better than per-query reads (RQ5): the current one treats each
  query's own read as the truth.
