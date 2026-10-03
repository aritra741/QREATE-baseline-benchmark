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

Not yet done: measured (not estimated) build costs per drift level (E1.3) and the anticipation sweep (E1.4).

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

Generic policies (E3.2), mean over 25 streams (cspaper / legal): fcfs 0.1453 / 0.1106; **fragile 0.1453 / 0.1136**;
hindsight oracle 0.1453 / 0.1129; per-patch cap 0.1398 / 0.0992; pacing **0.1466** / 0.1030. Pacing is best on cspaper
(and beats unlimited there at high budgets: 0.172 at 0.54M vs 0.153 at 1.16M) but worst-but-one on legal, where it
delays the useful early patches; the cap hurts small budgets on both. **The SQL-based `fragile` rule is the only
policy that never hurts**, and on legal it matches the hindsight oracle. Pending: oracle / cap / pace on med, and all
policies on player and art.

## RQ4: estimating cost and value

- **Cost estimates are accurate**: median estimated/actual patch tokens 0.997–1.005 on all five corpora.
- **Value is the hard part**: share of patch tokens that bought no score (on the query or any later query using the
  columns), unlimited at 100% drift: player 0%, art 16%, med 32%, legal 39%, cspaper 39%.
- One value signal is visible in the SQL alone: MIN/MAX over text (RQ3).

## RQ5: why the planner loses to a simple shared read

Player, same 20 held-out queries, same server: one shared read of every input-workload column scores **0.560 at
1.3M tokens**; the budgeted planner at most **0.340 at 5.5–6.7M**. Not yet attributed per cause (E5.1) or fixed (E5.2).

## RQ6: order effects and consistency

- Patches never overwrite: a (column, document) is read at most once per stream.
- Across budgets at the same drift level, differing cells are almost all filled in one stream and empty in the other
  (cspaper 12,241 vs 455 with two different values; player 38,028 vs 0).
- A budgeted stream beats unlimited on 8–31 queries per corpus, nearly all answered without their own patch: reading
  less sometimes helps (RQ8).

## RQ7: robustness to serving and model

Noise and quantization: see the first section. Pending: Llama 3.1 8B and Qwen 2.5 32B (E6.2).

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
  to +0.020: not a usable lever on this model.
- **Values right in substance, wrong in form**: lenient vs exact agreement, e.g. art `field` 0.92 vs 0.13; the
  benchmark's tolerant score is only 0.01–0.03 higher. Canonicalizing to the workload's vocabulary gains nothing
  (E8): the gaps are in GROUP BY labels the workload never names.
- **Query type** (E9): AVG/SUM 0.36, MIN/MAX over numbers 0.24, COUNT 0.21, MIN/MAX over text 0.03.

## Baseline: DocETL on the drift queries

DocETL (same model, one map per query and table, the fair prompt) at 100% drift, on the test queries it has scored
(complete for cspaper, player and med; art and legal still running):

| Corpus | Queries | DocETL | Ours, adaptive | Ours, static | DocETL tokens | Ours: patches + one shared build |
|---|---|---|---|---|---|---|
| cspaper | 59 of 59 | 0.105 | 0.153 | 0.008 | 20.7M | 1.16M + 0.40M |
| player | 118 of 118 | 0.081 | 0.387 | 0.040 | 190.6M | 5.67M + 2.04M |
| med | 76 of 76 | 0.056 | 0.086 | 0.031 | 170.6M | 19.92M + 2.54M |
| art | 30 of 43 | 0.151 | 0.235 | 0.044 | 40.5M | 6.08M + 2.43M (all 43) |
| legal | 8 of 30 | 0.016 | 0.137 | 0.000 | 137.4M | 15.97M + 4.56M (these 8) |

Adaptive patching is above DocETL on every corpus at 4–25× fewer tokens; DocETL is above our static build. **DocETL
collapses with joins** on player (0.125 → 0.034 → 0.008 for 0 / 1 / 2+ joins, all 118 queries) while ours stays at
0.37–0.44 (likely cause, not yet checked value by value: join keys extracted by separate per-table maps do not match).
