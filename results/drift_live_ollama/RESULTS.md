# Real drift runs (template-paired streams, seed 0)

Nothing is read ahead. The build reads every document once with the build workload's columns and descriptions; a query that needs a column not yet extracted reads, at that moment, only the documents that can affect its answer, with that column's description (given with the query, never before). Tokens and cost are OpenRouter's reported usage (qwen/qwen-2.5-7b-instruct); the build's input/output split is estimated from its responses (its calls were made before usage was recorded).

* live: QuWARTS on the stream, real reads. static: the build as it is (no adaptation). reference: the replay on a full read of every column made before the stream (what live would score with no drift cost).
* Accuracy: benchmark metric (structure F2 x cell F1 within 20%), mean over the stream's queries.

## attribute/100

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 21 | 0.106 | 0.004 | - | - | 6 | 1005 | 1.14M / 17k | $0.117 | 0.40M | $0.042 | 0.00M | - | 13s |
| art | 21 | 0.291 | 0.000 | - | - | 4 | 3399 | 3.44M / 64k | $0.357 | 2.43M | $0.260 | 0.00M | - | 32s |
| player | 28 | 0.432 | 0.020 | - | - | 7 | 562 | 4.62M / 35k | $0.469 | 2.04M | $0.207 | 0.00M | - | 41s |

## value/100

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 14 | 0.206 | 0.206 | - | - | 1 | 200 | 0.26M / 6k | $0.027 | 0.40M | $0.042 | 0.00M | - | 45s |
| art | 13 | 0.179 | 0.071 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.43M | $0.260 | 0.00M | - | 6s |
| player | 18 | 0.285 | 0.285 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.04M | $0.207 | 0.00M | - | 8s |

## attribute/0

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 21 | 0.177 | 0.177 | - | - | 1 | 200 | 0.25M / 6k | $0.026 | 0.40M | $0.042 | 0.00M | - | 46s |
| art | 21 | 0.188 | 0.187 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.43M | $0.260 | 0.00M | - | 11s |
| player | 28 | 0.299 | 0.299 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.04M | $0.207 | 0.00M | - | 12s |

## combined/0

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 27 | 0.200 | 0.200 | - | - | 1 | 200 | 0.25M / 6k | $0.026 | 0.40M | $0.042 | 0.00M | - | 10s |
| art | 25 | 0.209 | 0.196 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.43M | $0.260 | 0.00M | - | 13s |
| player | 28 | 0.312 | 0.312 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.04M | $0.207 | 0.00M | - | 12s |

## value/0

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 14 | 0.140 | 0.140 | - | - | 1 | 200 | 0.25M / 6k | $0.026 | 0.40M | $0.042 | 0.00M | - | 6s |
| art | 13 | 0.155 | 0.156 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.43M | $0.260 | 0.00M | - | 7s |
| player | 18 | 0.360 | 0.360 | - | - | 0 | 0 | 0.00M / 0k | $0.000 | 2.04M | $0.207 | 0.00M | - | 8s |

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
| legal | 0% | 0% (0) | 0% | 27 | 0 | 0.173 | - | 0.173 | 4.94M | 0.00M / 0k | $0.000 | 21s |
| legal | 25% | 40% (2) | 22% | 27 | 3 | 0.165 | -0.008 [-0.024, +0.000] | 0.133 | 4.81M | 7.95M / 60k | $0.807 | 95s |
| legal | 50% | 60% (3) | 52% | 27 | 4 | 0.174 | +0.001 [-0.017, +0.019] | 0.121 | 4.74M | 11.93M / 87k | $1.211 | 138s |
| legal | 75% | 80% (4) | 56% | 27 | 5 | 0.174 | +0.001 [-0.017, +0.019] | 0.121 | 4.63M | 15.68M / 114k | $1.591 | 173s |
| legal | 100% | 100% (5) | 100% | 27 | 6 | 0.170 | -0.003 [-0.028, +0.023] | 0.005 | 4.56M | 19.63M / 141k | $1.991 | 1922s |
| player | 0% | 0% (0) | 0% | 118 | 0 | 0.379 | - | 0.379 | 2.12M | 0.00M / 0k | $0.000 | 91s |
| player | 25% | 29% (2) | 25% | 118 | 3 | 0.381 | +0.001 [-0.000, +0.004] | 0.294 | 2.10M | 1.47M / 10k | $0.149 | 94s |
| player | 50% | 57% (4) | 50% | 118 | 5 | 0.390 | +0.011 [-0.002, +0.032] | 0.210 | 2.07M | 3.32M / 24k | $0.336 | 100s |
| player | 75% | 71% (5) | 76% | 118 | 6 | 0.389 | +0.010 [-0.003, +0.031] | 0.137 | 2.06M | 4.24M / 30k | $0.430 | 100s |
| player | 100% | 100% (7) | 100% | 118 | 8 | 0.387 | +0.008 [-0.009, +0.029] | 0.040 | 2.04M | 5.63M / 40k | $0.571 | 103s |
| med | 0% | 0% (0) | 0% | 43 | 0 | 0.130 | - | 0.130 | 2.81M | 0.00M / 0k | $0.000 | 61s |
| med | 25% | 14% (2) | 26% | 43 | 3 | 0.121 | -0.009 [-0.032, +0.008] | 0.112 | 2.75M | 2.54M / 19k | $0.258 | 134s |
| med | 50% | 36% (5) | 49% | 43 | 5 | 0.117 | -0.014 [-0.054, +0.020] | 0.079 | 2.69M | 5.48M / 39k | $0.556 | 106s |
| med | 75% | 64% (9) | 74% | 43 | 9 | 0.105 | -0.025 [-0.068, +0.009] | 0.043 | 2.62M | 8.99M / 68k | $0.913 | 140s |
| med | 100% | 100% (14) | 100% | 43 | 14 | 0.115 | -0.015 [-0.063, +0.026] | 0.041 | 2.54M | 13.98M / 101k | $1.418 | 1854s |

## Difficulty-matched pairs (attribute axis, no-drift scores within 0.05)

Only pairs whose source and drifted query score the same (within 0.05) when every column was read before the stream, so neither question is easier. QuWARTS's live score at 0% (the sources) and 100% (the drifted queries).

| Corpus | Pairs kept | QuWARTS 0% | QuWARTS 100% | Change [95% CI] | No-drift 0% | No-drift 100% |
|---|---|---|---|---|---|---|

## Difficulty-matched pairs (value axis, no-drift scores within 0.05)

Only pairs whose source and drifted query score the same (within 0.05) when every column was read before the stream, so neither question is easier. QuWARTS's live score at 0% (the sources) and 100% (the drifted queries).

| Corpus | Pairs kept | QuWARTS 0% | QuWARTS 100% | Change [95% CI] | No-drift 0% | No-drift 100% |
|---|---|---|---|---|---|---|