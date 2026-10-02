# Experiment plan: adaptive LLM materialization under drift and budget

The plan behind the research questions RQ1–RQ8. Each RQ lists its hypothesis, the quantitative
experiments, the qualitative analysis, what data each one needs, its cost, and what result would
change the paper. Phases are ordered so that the cheap checks that decide whether an anomaly is
real run before anything that builds on that anomaly.

## Data we already have (no new model calls)

| Source | What it holds |
|---|---|
| `results/drift_live_ollama/<c>/streams/*.jsonl` | One row per test query: `action` (answer / patch / skipped), `missing` columns, tokens, `benchmark` and `static_benchmark` scores. Streams: unlimited `fixed4-*`, budgeted `fixed4bNNN-*`, five drift levels, five corpora. |
| `results/drift_live_ollama/<c>/build_reads.jsonl`, `patch_reads.jsonl` | Every LLM read (prompt hash, document, columns, response). A policy that only uses reads already in these journals replays **for free**. |
| `results/drift_live_ollama/<c>/state/`, `builds/` | Build databases and stream state. |
| `results/quwarts_player_budget_sweep_ollama/fNNN/` | Planner sweep: plans, probe journals, per-query scores. |
| `results/quwarts_router_v3/player{,_ollama}/shared_read_protocol/` | Shared read on OpenRouter (0.609) and Ollama (0.560); 216 responses each. |
| `results/docetl_drift_ollama/` | DocETL on the drift queries (still running). |

**Tooling to build once (Phase 0), used by every RQ:**
1. *Stream replayer*: rebuilds the database a stream had at query *k* from the journals, and re-scores
   a query against any database state. No LLM calls when every read is cached.
2. *Per-column scorer*: accuracy of one column (cell F1 against gold, per document) independent of
   any query, so read quality can be separated from query structure.
3. *Score decomposer*: for each query, structure F2 and cell F1 separately, plus a failure label
   (no rows, wrong join, wrong values, extra rows).
4. *Bootstrap CIs*: paired bootstrap over queries (and over documents for column-level numbers),
   reported on every table and chart.

## Phase 1: is it real? (RQ7, noise; about one GPU day)

### E1.1 Run-to-run variance
- **Run:** repeat 3 streams unchanged, read cache cleared: player and legal at 100% drift unlimited, and
  legal at 25%/50% budget. Also repeat the player shared read twice.
- **Measure:** the spread of scores across repeats; the share of read responses that come back
  byte-identical.
- **Decision:** if repeats vary by more than about 0.02, report every result with CIs plus repeats, and
  call any gap smaller than the spread noise. That covers cspaper's 25%-drift bump, med's budget
  steps and player's 20→25% jump.
- **Cost:** about 25M tokens, roughly 4 GPU hours.

### E1.2 Serving-setup sensitivity (0.609 vs 0.560)
- **Known:** the local server runs `qwen2.5:7b-instruct` at 4-bit (`Q4_K_M`). The GPU has 96 GB, so
  the 16-bit model (`qwen2.5:7b-instruct-fp16`, about 15 GB) fits alongside it.
- **Quantitative:**
  - Diff the 216 OpenRouter vs Ollama shared-read responses value by value, for each column.
  - Record the temperature, and how often a prompt was cut short.
  - Rerun the shared read on the local 16-bit model to isolate quantization: about 1.3M tokens.
- **Qualitative:** read 30 cells where the two backends disagree, and group the differences into
  formatting, missed value, wrong value, and invented value.
- **Decision:** if quantization explains the gap, run the headline comparisons on the 16-bit model
  (E6.2) and state the serving setup in the paper.

## Phase 2: per-column and per-patch analysis on existing logs (RQ2, RQ6, RQ8; no new model calls)

### E2.1 Build read vs patch read accuracy (RQ2)
- **Quantitative:**
  - For every column extracted both by the build read (at a lower drift level) and by a patch
    (at a higher level), compare per-column cell F1 on the same documents.
  - Regress accuracy on how many columns the read extracts at once, the prompt length, and the
    document length.
- **Qualitative:** for the 10 columns with the largest gap, put both prompts and responses side by
  side and say why one is better: focus, usage phrase, example constants, or truncation.
- **New run (small):** a prompt-width sweep. Extract a fixed set of 12 columns in reads of 1, 3, 6
  and 12 columns at a time, on a 50-document sample per corpus. About 5M tokens.
- **Decision:** if narrower reads are reliably more accurate, prompt width becomes a physical-design
  choice (RQ2's headline). Then test whether this explains rebuild vs augmentation (`REBUILD_QUALITY.md`).

### E2.2 Patch value accounting (RQ3, RQ4 input)
- **Quantitative:**
  - For every patch: its tokens; the score of the query that triggered it; its effect on every
    later query (replay with and without it); and how many later queries use the columns it filled.
  - Report the share of patch tokens that bought no score at all.
- **Qualitative:** classify each wasted patch: join key still missing; empty or ambiguous gold;
  wrong values; or a column not in the documents.
  - Start with legal queries 1 and 2 (4M tokens each, score 0), then cover all corpora.

### E2.3 Order effects and overwrites (RQ6)
- **Quantitative:**
  - Replay legal query 11 against the database states of the 25%, 50% and unlimited streams.
  - Diff the columns it reads, cell by cell.
  - Across all streams, count the values a patch *overwrote* rather than filled, and how
    accuracy changed on overwritten cells.
- **Policy run (replay only):** "fill only, never overwrite" vs the current policy, on all
  unlimited streams.
- **Qualitative:** document 5 cases where order changed an answer, with the exact cells involved.

### E2.4 Error breakdown (RQ8)
- **Quantitative:** split each query's score into structure F2 and cell F1, and label each failure,
  for: ours (shared read, planner at 25%, adaptive at 0% and 100% drift), DocETL, and static.
  Report this per corpus.
- **Qualitative:** 5 failed queries per corpus for us and for DocETL, with the reason for each.
- **Med specifically:** document length vs context window; whether gold values sit beyond what a
  read covers; structure vs cell share of the loss.

## Phase 3: budget policies (RQ3, RQ4; mostly replay)

### E3.1 Offline best-possible policy
- From E2.2's per-patch costs and effects, compute the best set of patches under each budget with
  the whole workload known in advance (a knapsack over patches, re-scored by replay).
- This upper-bounds every online policy and gives a competitive ratio per corpus and budget.

### E3.2 Online policies
Run each policy on all corpora, all 5 budgets and all 5 drift levels:
1. first-come first-served (current);
2. a cap on any single patch's cost (a share of the remaining budget);
3. reserve a share of the budget for later queries;
4. skip by expected value per token, using E4.1's estimator;
5. a hindsight-free version of the offline policy, using only past queries.

Most of these replay from cached reads. New reads arise only where a policy patches something no
earlier stream did (about 10–30M tokens in total).

- **Metrics:** score vs budget, whether the curve is monotone, the competitive ratio, and tokens
  wasted.
- **Decision:** a policy that is monotone and within about 10% of the offline best becomes the
  system's policy, and the comparison becomes RQ3's main figure.

### E4.1 Cost and value estimation (RQ4)
- **Cost:** estimated vs actual tokens for every read, as a calibration plot and error per corpus.
  Then fix the estimator: count each document's tokens exactly instead of averaging.
- **Value:** predict a patch's score gain from cheap features: join-key coverage, how selective the
  query is, how many documents are in scope, and a 5-document probe read. Evaluate with
  cross-validation across corpora, and plug the result into policy 4.

## Phase 4: planner failure analysis (RQ5; small runs)

### E5.1 Attribute the planner's losses
- **Quantitative:** for each of the 20 held-out queries at each budget, classify why the planner
  lost to the shared read:
  - a column left unread;
  - a join key left unread;
  - a probe-measured provider that differs from the shared read;
  - a weaker read prompt.
  Sum the score lost to each cause.
- **Qualitative:** walk through 3 planner decisions on player end to end: the probe evidence,
  the decision, and the outcome.

### E5.2 Planner fixes (ablations)
Run each fix alone and all together:
1. Offer the shared read as a candidate plan without first measuring it with probes.
2. Treat a query as worthless if any of its join keys is missing.
3. Spend the budget until it runs out.

Run the player budget sweep again at 10%, 25% and 50%. About 15M tokens.

- **Decision:** if the planner with all fixes doesn't at least match the shared read, the paper
  presents the planner as an ablation and the shared read plus adaptive patching as the system.

## Phase 5: lazy vs eager (RQ1; reuses Phases 2–3)

### E1.3 Measured build costs
Read and count the tokens of each drift level's build exactly, replacing the "one shared read"
estimate in `prepare_supplement`. This costs about 0 new tokens if the build's prompts can be
re-counted, and about 5M per corpus if the builds are re-read.

### E1.4 How much to anticipate
- **Sweep:** the share of anticipated columns read at build time (0, 25, 50, 75, 100%) × drift
  level × budget.
- **Measure:** total tokens and score, to find where reading ahead stops paying off.
- **Model:** fit a simple cost model (build cost + drift × patch cost) and check its predicted
  crossover against the measured one.

## Phase 6: baselines and generality

- **E6.1 DocETL drift:** finish the run, then add DocETL's error breakdown (E2.4) and cost to every
  drift chart.
- **E6.2 Other local models:** rerun the headline comparisons on models that fit on our GPU:
  - which comparisons: shared read, adaptive vs static at 0% and 100% drift, and the best budget policy;
  - which corpora: 2 (player and one of legal or med);
  - which models: `qwen2.5:7b-instruct-fp16`, a larger model (`qwen2.5:14b-instruct` or
    `qwen2.5:32b-instruct` at 4-bit), and one from another family (`llama3.1:8b-instruct`).
  - **Tests:** whether the conclusions hold across model size, quantization and model family.
  - **Cost:** about 60–80M tokens per model. GPU time grows with model size, so expect about 2–3
    days for the 32B model while the GPU is shared.
  - Frontier models are out of scope for now.

## Schedule and cost

| Phase | RQs | New tokens | GPU time | Depends on |
|---|---|---|---|---|
| 0 Tooling | all | 0 | 0 | — |
| 1 Is it real | RQ7 | ~27M | ~1 day | 0 |
| 2 Log analysis | RQ2, RQ6, RQ8 | ~5M (width sweep) | hours | 0, 1 |
| 3 Budget policies | RQ3, RQ4 | ~10–30M | ~1 day | 2.2 |
| 4 Planner | RQ5 | ~15M | ~0.5 day | 2.4 |
| 5 Lazy vs eager | RQ1 | 0–25M | ~1 day | 3 |
| 6 Baselines | RQ7, all | DocETL running; ~60–80M per extra local model | ~1–3 days per model | 1–5 |

Phases 2 and 4 can run alongside 3. The GPU is shared with the DocETL drift run until it finishes,
so GPU times are estimates under sharing.

## Figures and tables this produces

1. Score vs drift: static, adaptive and DocETL (exists; add CIs and DocETL).
2. Score vs budget per corpus, by policy, with the offline best as the ceiling (RQ3 headline).
3. Build-read vs patch-read accuracy per column, and accuracy vs prompt width (RQ2 headline).
4. Patch cost vs value scatter, with wasted tokens marked (RQ3/RQ4).
5. Estimated vs actual cost calibration (RQ4).
6. Planner losses by cause (RQ5).
7. Error breakdown per system and corpus (RQ8).
8. Variance and serving-setup table (RQ7).
