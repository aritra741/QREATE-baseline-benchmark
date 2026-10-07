# Experiment summary by research question

Current state of the findings, one section per research question (RQ1–RQ8 in `results/drift_design/EXPERIMENT_PLAN.md`).
Every number here is the latest valid one; the full record, with the evidence, case studies and superseded runs, is
`FINDINGS.md`. Token and latency accounting: `ACCOUNTING.md`. Step status: `STATUS.md`.

Setting: Qwen 2.5 7B on local Ollama (4-bit unless stated), score = per-query structure F2 × cell F1@0.20, averaged.
Drift levels 0–100% withhold new columns from the build (`attribute_pool` test set, all with GROUP BY). Corpora run:
cspaper, player, art (220 test queries). **med and legal: not yet run.**

## Are the measurements trustworthy?

- **Replays are exact.** Every recorded drift stream re-runs from its journals with model calls refused and reproduces
  every query's action, tokens and score. All per-query analyses build on these replays.
- **Run-to-run noise is small.** A whole drift stream re-run with every patch read again moves by 0.000 (cspaper) and
  +0.0015 (player, 95% CI −0.002 to +0.007), although a quarter to a third of responses differ in text. The player
  shared read varies by up to 0.012 on 20 held-out queries across three identical runs.
- **Quantization is a small, real effect.** 16-bit vs 4-bit: +0.03 on the shared read (held-out), +0.004 on a whole
  drift stream. 4-bit results are slightly pessimistic; comparisons on the same server are unaffected.
- **What the test sets can detect** (A15): paired query-level differences of about 0.046 (cspaper), 0.026 (player),
  0.036 (art) at 80% power; smaller "no significant difference" results mean "below that", not "zero".
- **A prompt bug** (2026-10-01 23:40 to 10-02 13:20) invalidated 11 runs; all were re-run. A guard step now replays a
  recorded stream with calls refused before any GPU step.

## RQ1: lazy vs eager materialization under drift

Adaptive patching holds the score as drift grows; the static build collapses.

| Corpus | Static, 0% → 100% drift | Adaptive, 0% → 100% drift | Patch tokens at 100% |
|---|---|---|---|
| player | 0.379 → 0.040 | 0.379 → 0.387 | 5.7M |
| art | 0.270 → 0.031 | 0.270 → 0.256 | 6.1M |
| cspaper | 0.134 → 0.008 | 0.134 → 0.153 | 1.2M |
| med | not yet run | | |
| legal | not yet run | | |

Build costs of the 0–75% levels (E1.3): the measured W0 read plus exactly counted extra prompt lines, with only the
answer tokens estimated (12 per field; measured 9.5–15); accurate to within about 2%. **Reading ahead vs patching
later (E1.4):** anticipating every new column costs 0.07–0.74M extra build tokens; patching them all later costs
1.2–6.1M, at about the same score (lazy ÷ eager total tokens 2.7–3.6×). A column is worth reading up front if the
chance a query will need it exceeds **1.3%** (player) or 12–13% (art, cspaper).

**Robustness.** Four draws of the withheld columns (E11; cspaper, player) and build workloads cut to 10–50% of their
queries (E12; 7 runs): static collapses at 100% drift every time; the patched curve stays flat, with no significant
100% − 0% difference (−0.015 to +0.020). A smaller build workload leaves more columns to the patches and costs more in
total (art at 10%: 8.5M → 10.1M tokens; cspaper +23%, player +7%). The 0% score moves with the share (cspaper 0.134 →
0.149–0.162, player 0.379 → 0.353) because the build groups columns into prompts by workload and a column's values
depend on the prompt it is read in (A6: the columns that change are those read in a prompt of a different size).

## RQ2: is a narrow patch read more accurate than a wide build read?

**No general effect.** The same 12 columns read 1, 3, 6 or 12 at a time on fixed document samples (E2.1b; independent of
the drift test queries, all five corpora): one column per read is better on legal (+0.068 exact agreement) and player
(+0.026), worse on art (−0.034), flat on cspaper, mixed on med, and always 6–10× the tokens.

**Per column the prompt matters a lot** (A3, cell level, patch prompt vs build prompt, McNemar per column): significant
on 6 of art's 9 new columns, 1 of cspaper's 6, none of player's 7, in both directions, so query-level means barely
move. What separates columns: numeric and yes/no columns are insensitive (|change| ≤ 0.04); with 1–2 columns per
prompt the model leaves free-text and multi-choice cells empty more often, which helps where gold is often empty and
hurts where it is filled; and values with an ambiguous form (titles, ranges, several categories) follow whatever
example values the prompt's usage phrase shows (art `century`: build "20th-21st", patch "20th").

The adaptive curve's small rises under drift (cspaper +0.019, player +0.008) are this prompt effect (E14), not drift.

## RQ3: budget policies for adaptive extraction

Mean score over 25 budget × drift settings per corpus:

| Policy | cspaper | player | art | med | legal |
|---|---|---|---|---|---|
| first-come-first-served (fcfs) | 0.1453 | 0.3363 | 0.2356 | not yet run | not yet run |
| hindsight oracle | 0.1453 | 0.3363 | 0.2356 | | |
| per-patch cap | 0.1398 | 0.3076 | 0.2263 | | |
| pacing | **0.1466** | 0.3260 | **0.2405** | | |
| offline knapsack (E3.1) | 0.1369 | **0.3389** | 0.2306 | | |

No policy is reliably better than fcfs: pacing wins on cspaper and art and loses on player; the cap is never best;
the hindsight oracle equals fcfs (few patches bought nothing). cspaper "10% budget beats unlimited": reading a column
for every document can hurt (see RQ8, never-null metadata).

**Offline knapsack (E3.1).** Knowing the whole stream and picking the patches with the most measured value per budget
is not better than fcfs (cspaper −0.008, art −0.005, player +0.003) because a patch's cost and value depend on the
patches before it (a chosen player patch grew from 1 to 29 documents without its predecessors and was skipped). It
leaves 39% of cspaper's full budget unspent at the same score.

## RQ4: estimating cost and value

- **Cost estimates are accurate**: median estimated/actual patch tokens 0.997–1.005.
- **Value**: share of patch tokens that bought no score (on the query or any later query using the columns),
  unlimited at 100% drift: player 0%, art 16%, cspaper 39%. Over all 67 patches of the unlimited streams (31.5M tokens)
  5% bought nothing; unfiltered whole-corpus patches hold 86% of that waste (7% of their own tokens), filtered patches
  2%.

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

Noise and quantization: see the first section. Other models (E6.2, E6.3), all 4-bit on local Ollama:

| | Llama 3.1 8B | Qwen 2.5 7B | Qwen 2.5 32B |
|---|---|---|---|
| Player shared read, held-out 20 | 0.466 | 0.560 | **0.690** |
| Player, adaptive 0% → 100% drift (static at 100%) | 0.356 → 0.359 (0.040) | 0.379 → 0.387 (0.040) | 0.401 → **0.421** (0.052) |
| cspaper, adaptive 0% → 100% drift (static at 100%) | 0.149 → 0.125 (0.008) | 0.134 → 0.153 (0.008) | 0.162 → **0.224** (0.008) |
| art, adaptive 0% → 100% drift (static at 100%) | 0.209 → 0.203 (0.031) | 0.270 → 0.256 (0.031) | 0.293 → 0.289 (0.031) |
| med, legal | not yet run | | |

The adaptive-vs-static result holds for every model at the same patch cost; model scale is the largest single effect
measured (+0.13 held-out from 7B to 32B). The 32B model's drift rise is significant on cspaper (+0.062) and player
(+0.020), not on art; giving its patches the build's prompt removes it exactly (E14 with 32B), and on cspaper the
build's grouping alone does (0.155 vs 0.162 at 0%): one column, `reasoning_depth`, is left empty on 64% of papers
when read with six other columns and filled on 98% when read alone.

## RQ8: where accuracy is lost

| Corpus | Bottleneck (unlimited, 100% drift) | Structure F2 / Cell F1 |
|---|---|---|
| player | cell values (rows and joins stay right; static loses only cells) | 0.753 / 0.468 |
| art | both | 0.527 / 0.340 |
| cspaper | cell values | 0.650 / 0.187 |
| med | not yet run | |
| legal | not yet run | |

Cross-cutting causes:
- **Benchmark metadata says "never null" where gold is often empty**: 19 of the 59 never-null columns of cspaper,
  player and art are empty in ≥5% of gold rows (e.g. cspaper `performance_on_hotpotqa` 84%). The prompt must then
  invent values. Prompt-level fixes (dropping "Never null", a field-level null hint, relaxing only the contradictory
  field) move scores by −0.053 to +0.020: not a usable lever on this model.
- **Values right in substance, wrong in form**: lenient vs exact agreement, e.g. art `field` 0.92 vs 0.13; the
  benchmark's tolerant score is only 0.01–0.03 higher. Canonicalizing to the workload's vocabulary gains nothing
  (E8): the gaps are in GROUP BY labels the workload never names.
- **Query type** (E9, patched at 100% drift): AVG 0.42, SUM 0.35, MIN over numbers 0.33, COUNT 0.28, MAX over numbers
  0.18.

## Ablations (E13, E14)

One component turned off at a time, unlimited stream at 100% drift (paired; * significant; med and legal not yet run):
- **Accuracy**: field descriptions (cspaper −0.034*, player −0.136*, art −0.101*), value normalization at commit
  (player −0.131*, cspaper −0.011*), the view's value representation (art −0.066*).
- **Cost**: reuse of patched columns (without it 4.9–16.9× the tokens, score −0.012 to +0.010), scope (up to 1.46×).
- **Neither**: the workload usage phrase, chained reading of long documents (saves 42% of patch tokens on player for
  −0.004), batching other workload columns into a patch.
- **Why the patched score moves under drift (E14)**: giving patches the build's exact prompt (no new calls needed)
  moves each 100%-drift score to its 0%-drift score; on cspaper over every document it reproduces the 0% stream
  (58/59 queries). The grouping (1–3 columns per patch vs all new columns per build prompt) carries it; field specs
  and scope do not.

## Baseline: DocETL on the drift queries

DocETL (same model, one map per query and table, the fair prompt) at 100% drift; paired difference with 95% bootstrap
CI:

| Corpus | Queries | DocETL | Ours, adaptive | Ours − DocETL (95% CI) | DocETL tokens | Ours: build + patches | Ratio |
|---|---|---|---|---|---|---|---|
| player | 118 | 0.081 | 0.387 | +0.306 (+0.246, +0.367) | 190.6M | 7.71M | 25× |
| cspaper | 59 | 0.105 | 0.153 | +0.049 (+0.003, +0.093) | 20.7M | 1.56M | 13× |
| art | 43 | 0.167 | 0.256 | +0.089 (+0.047, +0.134) | 57.9M | 8.52M | 7× |
| med | not yet run | | | | | | |
| legal | not yet run | | | | | | |

On player DocETL scores 0.125 / 0.034 / 0.008 on queries with 0 / 1 / 2+ joins.

## Status (2026-10-07)

Done on cspaper, player and art: replays and per-corpus analyses; noise, quantization; null handling (E7 family);
prompt width (E2.1b, all five corpora); canonicalization (E8); query types (E9); budget policies (E3.1, E3.2); other
models (Llama 3.1 8B, Qwen 2.5 32B); planner attribution and fixes (E5.0–E5.4); build-cost accuracy (E1.3);
anticipation (E1.4); patch-value signals (E4.1); token and latency accounting (`ACCOUNTING.md`); other drift draws
(E11) and smaller build workloads (E12); DocETL; component ablations (E13); prompt factors (E14, also with 32B);
per-column analyses (A3, A6, A15).

Not yet run: med and legal (all experiments).

Open:
- A planner objective that can recognise a shared read better than per-query reads (RQ5): the current one treats each
  query's own read as the truth.
