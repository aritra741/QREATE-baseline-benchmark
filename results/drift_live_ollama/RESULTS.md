# Real drift runs (template-paired streams, seed 0)

Nothing is read ahead. The build reads every document once with the build workload's columns and descriptions; a query that needs a column not yet extracted reads, at that moment, only the documents that can affect its answer, with that column's description (given with the query, never before). Tokens and cost are OpenRouter's reported usage (qwen/qwen-2.5-7b-instruct); the build's input/output split is estimated from its responses (its calls were made before usage was recorded).

* live: QuWARTS on the stream, real reads. static: the build as it is (no adaptation). reference: the replay on a full read of every column made before the stream (what live would score with no drift cost).
* Accuracy: benchmark metric (structure F2 x cell F1 within 20%), mean over the stream's queries.

## attribute/100

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 21 | 0.106 | 0.004 | - | - | 6 | 1005 | 1.14M / 17k | $0.117 | 0.40M | $0.042 | 0.00M | - | 13s |
| art | 21 | 0.291 | 0.000 | - | - | 4 | 3399 | 3.44M / 64k | $0.357 | 2.43M | $0.260 | 0.00M | - | 32s |
| legal | 14 | 0.148 | 0.010 | - | - | 7 | 3420 | 23.77M / 182k | $2.413 | 4.56M | $0.465 | 0.00M | - | 366s |
| player | 28 | 0.432 | 0.020 | - | - | 7 | 562 | 4.62M / 35k | $0.469 | 2.04M | $0.207 | 0.00M | - | 41s |
| med | 26 | 0.061 | 0.023 | - | - | 10 | 970 | 11.54M / 87k | $1.172 | 2.54M | $0.259 | 0.00M | - | 91s |

## value/100

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 14 | 0.206 | 0.206 | - | - | 1 | 200 | 0.26M / 6k | $0.027 | 0.40M | $0.042 | 0.00M | - | 45s |
| art | 13 | 0.179 | 0.071 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.43M | $0.260 | 0.00M | - | 6s |
| legal | 5 | 0.216 | 0.218 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 4.56M | $0.465 | 0.00M | - | 1s |
| player | 18 | 0.285 | 0.285 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.04M | $0.207 | 0.00M | - | 8s |
| med | 14 | 0.179 | 0.179 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.54M | $0.259 | 0.00M | - | 9s |

## attribute/0

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 21 | 0.177 | 0.177 | - | - | 1 | 200 | 0.25M / 6k | $0.026 | 0.40M | $0.042 | 0.00M | - | 46s |
| art | 21 | 0.188 | 0.187 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.43M | $0.260 | 0.00M | - | 11s |
| legal | 14 | 0.243 | 0.243 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 4.56M | $0.465 | 0.00M | - | 4s |
| player | 28 | 0.299 | 0.299 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.04M | $0.207 | 0.00M | - | 12s |
| med | 26 | 0.124 | 0.124 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.54M | $0.259 | 0.00M | - | 15s |

## combined/0

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 27 | 0.200 | 0.200 | - | - | 1 | 200 | 0.25M / 6k | $0.026 | 0.40M | $0.042 | 0.00M | - | 10s |
| art | 25 | 0.209 | 0.196 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.43M | $0.260 | 0.00M | - | 13s |
| legal | 16 | 0.254 | 0.254 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 4.56M | $0.465 | 0.00M | - | 5s |
| player | 28 | 0.312 | 0.312 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.04M | $0.207 | 0.00M | - | 12s |
| med | 28 | 0.161 | 0.161 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.54M | $0.259 | 0.00M | - | 18s |

## value/0

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 14 | 0.140 | 0.140 | - | - | 1 | 200 | 0.25M / 6k | $0.026 | 0.40M | $0.042 | 0.00M | - | 6s |
| art | 13 | 0.155 | 0.156 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.43M | $0.260 | 0.00M | - | 7s |
| legal | 5 | 0.236 | 0.236 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 4.56M | $0.465 | 0.00M | - | 2s |
| player | 18 | 0.360 | 0.360 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.04M | $0.207 | 0.00M | - | 8s |
| med | 14 | 0.215 | 0.215 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.54M | $0.259 | 0.00M | - | 9s |

## Drifted minus source, same template (attribute axis)

Each attribute/100 query minus its base query in attribute/0, so query difficulty cancels.

| Corpus | Pairs | Live [95% CI] | Reference [95% CI] | Static |
|---|---|---|---|---|

## Fixed questions, attribute_pool axis (same test queries at every level)

Level p: a nested set of the new columns is left out of the build, and the test queries that use them are unanticipated; the other test queries are in the build workload (their columns read at build time). The x-axis is the real drift of each level: the share of new columns missing (their number) and of test queries unanticipated. Change: each query's score minus its score at 0% (same question), mean and 95% CI (bootstrap over base queries: variants of one base query are resampled together).

| Corpus | Level | Columns missing | Queries unanticipated | Queries | Patched | QuWARTS | Change vs 0% [95% CI] | Static | Build tokens | Patch tokens (in / out) | Patch cost | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 0% | 0% (0) | 0% | 59 | 0 | 0.134 | - | 0.134 | 0.55M | 0.00M / 0k | $0.000 | 28s |
| cspaper | 25% | 14% (1) | 30% | 59 | 6 | 0.154 | +0.020 [-0.002, +0.046] | 0.098 | 0.52M | 0.23M / 3k | $0.023 | 28s |
| cspaper | 50% | 43% (3) | 49% | 59 | 5 | 0.147 | +0.013 [-0.009, +0.037] | 0.036 | 0.49M | 0.47M / 9k | $0.048 | 289s |
| cspaper | 75% | 57% (4) | 76% | 59 | 4 | 0.149 | +0.015 [-0.012, +0.040] | 0.008 | 0.47M | 0.68M / 11k | $0.070 | 244s |
| cspaper | 100% | 100% (7) | 100% | 59 | 7 | 0.153 | +0.019 [-0.013, +0.053] | 0.008 | 0.40M | 1.14M / 20k | $0.118 | 691s |
| art | 0% | 0% (0) | 0% | 43 | 0 | 0.270 | - | 0.270 | 3.18M | 0.00M / 0k | $0.000 | 32s |
| art | 25% | 33% (3) | 26% | 43 | 4 | 0.266 | -0.004 [-0.008, -0.000] | 0.202 | 2.94M | 1.99M / 46k | $0.209 | 199s |
| art | 50% | 44% (4) | 49% | 43 | 4 | 0.267 | -0.003 [-0.017, +0.011] | 0.146 | 2.84M | 2.47M / 64k | $0.259 | 45s |
| art | 75% | 56% (5) | 77% | 43 | 6 | 0.260 | -0.010 [-0.037, +0.012] | 0.048 | 2.77M | 3.44M / 74k | $0.359 | 281s |
| art | 100% | 100% (9) | 100% | 43 | 9 | 0.256 | -0.014 [-0.042, +0.007] | 0.031 | 2.43M | 5.95M / 132k | $0.621 | 5193s |
| legal | 0% | 0% (0) | 0% | 30 | 0 | 0.121 | - | 0.121 | 5.05M | 0.00M / 0k | $0.000 | 14s |
| legal | 25% | 25% (2) | 23% | 30 | 3 | 0.122 | +0.001 [+0.000, +0.003] | 0.102 | 4.95M | 7.92M / 65k | $0.805 | 63s |
| legal | 50% | 38% (3) | 50% | 30 | 5 | 0.127 | +0.006 [+0.001, +0.014] | 0.054 | 4.88M | 11.88M / 95k | $1.207 | 321s |
| legal | 75% | 62% (5) | 77% | 30 | 7 | 0.113 | -0.009 [-0.044, +0.016] | 0.021 | 4.77M | 19.82M / 152k | $2.012 | 134s |
| legal | 100% | 100% (8) | 100% | 30 | 10 | 0.114 | -0.007 [-0.051, +0.034] | 0.005 | 4.56M | 29.70M / 229k | $3.016 | 6969s |
| player | 0% | 0% (0) | 0% | 118 | 0 | 0.379 | - | 0.379 | 2.12M | 0.00M / 0k | $0.000 | 91s |
| player | 25% | 29% (2) | 25% | 118 | 3 | 0.381 | +0.001 [-0.000, +0.004] | 0.294 | 2.10M | 1.47M / 10k | $0.149 | 94s |
| player | 50% | 57% (4) | 50% | 118 | 5 | 0.390 | +0.011 [-0.002, +0.032] | 0.210 | 2.07M | 3.32M / 24k | $0.336 | 100s |
| player | 75% | 71% (5) | 76% | 118 | 6 | 0.389 | +0.010 [-0.003, +0.031] | 0.137 | 2.06M | 4.24M / 30k | $0.430 | 100s |
| player | 100% | 100% (7) | 100% | 118 | 8 | 0.387 | +0.008 [-0.009, +0.029] | 0.040 | 2.04M | 5.63M / 40k | $0.571 | 103s |
| med | 0% | 0% (0) | 0% | 76 | 0 | 0.095 | - | 0.095 | 2.87M | 0.00M / 0k | $0.000 | 67s |
| med | 25% | 28% (5) | 25% | 76 | 5 | 0.087 | -0.008 [-0.020, -0.000] | 0.072 | 2.77M | 5.34M / 41k | $0.542 | 101s |
| med | 50% | 56% (10) | 50% | 76 | 10 | 0.094 | -0.002 [-0.015, +0.010] | 0.065 | 2.69M | 10.99M / 78k | $1.115 | 136s |
| med | 75% | 72% (13) | 75% | 76 | 13 | 0.081 | -0.014 [-0.031, -0.000] | 0.037 | 2.64M | 14.46M / 103k | $1.467 | 152s |
| med | 100% | 100% (18) | 100% | 76 | 18 | 0.086 | -0.009 [-0.025, +0.004] | 0.031 | 2.54M | 19.79M / 138k | $2.006 | 5002s |

## Difficulty-matched pairs (attribute axis, no-drift scores within 0.05)

Only pairs whose source and drifted query score the same (within 0.05) when every column was read before the stream, so neither question is easier. QuWARTS's live score at 0% (the sources) and 100% (the drifted queries).

| Corpus | Pairs kept | QuWARTS 0% | QuWARTS 100% | Change [95% CI] | No-drift 0% | No-drift 100% |
|---|---|---|---|---|---|---|

## Difficulty-matched pairs (value axis, no-drift scores within 0.05)

Only pairs whose source and drifted query score the same (within 0.05) when every column was read before the stream, so neither question is easier. QuWARTS's live score at 0% (the sources) and 100% (the drifted queries).

| Corpus | Pairs kept | QuWARTS 0% | QuWARTS 100% | Change [95% CI] | No-drift 0% | No-drift 100% |
|---|---|---|---|---|---|---|