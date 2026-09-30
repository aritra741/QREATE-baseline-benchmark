# Real drift runs (template-paired streams, seed 0)

Nothing is read ahead. The build reads every document once with the build workload's columns and descriptions; a query that needs a column not yet extracted reads, at that moment, only the documents that can affect its answer, with that column's description (given with the query, never before). Tokens and cost are OpenRouter's reported usage (qwen/qwen-2.5-7b-instruct); the build's input/output split is estimated from its responses (its calls were made before usage was recorded).

* live: QuWARTS on the stream, real reads. static: the build as it is (no adaptation). reference: the replay on a full read of every column made before the stream (what live would score with no drift cost).
* Accuracy: benchmark metric (structure F2 x cell F1 within 20%), mean over the stream's queries.

## attribute/100

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 21 | 0.108 | 0.004 | 0.215 | -0.107 [-0.220, -0.033] | 6 | 1004 | 1.14M / 16k | $0.117 | 0.40M | $0.042 | 0.52M | 2.99 | 51s |
| art | 21 | 0.283 | 0.000 | 0.283 | -0.000 [-0.047, +0.044] | 4 | 3392 | 3.43M / 64k | $0.356 | 2.43M | $0.260 | 3.16M | 1.88 | 226s |
| legal | 14 | 0.167 | 0.000 | 0.202 | -0.035 [-0.099, +0.036] | 7 | 3420 | 23.78M / 199k | $2.418 | 4.56M | $0.465 | 4.96M | 5.76 | 989s |
| player | 28 | 0.429 | 0.023 | 0.396 | +0.033 [-0.015, +0.113] | 7 | 568 | 4.66M / 38k | $0.473 | 2.04M | $0.207 | 2.14M | 3.15 | 209s |
| med | 26 | 0.065 | 0.026 | 0.082 | -0.018 [-0.059, +0.013] | 10 | 966 | 11.48M / 93k | $1.167 | 2.55M | $0.259 | 2.80M | 5.05 | 468s |

## value/100

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 14 | 0.190 | 0.190 | 0.193 | -0.003 [-0.019, +0.011] | 1 | 200 | 0.26M / 5k | $0.027 | 0.40M | $0.042 | 0.52M | 1.27 | 27s |
| art | 13 | 0.192 | 0.078 | 0.229 | -0.037 [-0.085, -0.002] | 0 | 0 | 0.00M / 0k | $0.000 | 2.43M | $0.260 | 3.16M | 0.77 | 4s |
| legal | 5 | 0.229 | 0.230 | 0.215 | +0.013 [-0.040, +0.080] | 0 | 0 | 0.00M / 0k | $0.000 | 4.56M | $0.465 | 4.96M | 0.92 | 2s |
| player | 18 | 0.336 | 0.336 | 0.316 | +0.020 [-0.152, +0.180] | 0 | 0 | 0.00M / 0k | $0.000 | 2.04M | $0.207 | 2.14M | 0.95 | 6s |
| med | 14 | 0.137 | 0.137 | 0.205 | -0.067 [-0.149, +0.001] | 0 | 0 | 0.00M / 0k | $0.000 | 2.55M | $0.259 | 2.80M | 0.91 | 5s |

## attribute/0

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 21 | 0.179 | 0.179 | 0.172 | +0.007 [+0.000, +0.019] | 1 | 200 | 0.25M / 5k | $0.026 | 0.40M | $0.042 | 0.52M | 1.26 | 26s |
| art | 21 | 0.191 | 0.186 | 0.195 | -0.004 [-0.028, +0.020] | 0 | 0 | 0.00M / 0k | $0.000 | 2.43M | $0.260 | 3.16M | 0.77 | 7s |
| legal | 14 | 0.209 | 0.209 | 0.233 | -0.024 [-0.115, +0.040] | 0 | 0 | 0.00M / 0k | $0.000 | 4.56M | $0.465 | 4.96M | 0.92 | 4s |
| player | 28 | 0.306 | 0.306 | 0.307 | -0.001 [-0.016, +0.020] | 0 | 0 | 0.00M / 0k | $0.000 | 2.04M | $0.207 | 2.14M | 0.95 | 10s |
| med | 26 | 0.055 | 0.055 | 0.101 | -0.047 [-0.109, +0.001] | 0 | 0 | 0.00M / 0k | $0.000 | 2.55M | $0.259 | 2.80M | 0.91 | 9s |

## combined/0

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 27 | 0.187 | 0.187 | 0.186 | +0.001 [-0.008, +0.012] | 1 | 200 | 0.25M / 5k | $0.026 | 0.40M | $0.042 | 0.52M | 1.26 | 7s |
| art | 25 | 0.218 | 0.208 | 0.220 | -0.002 [-0.028, +0.026] | 0 | 0 | 0.00M / 0k | $0.000 | 2.43M | $0.260 | 3.16M | 0.77 | 8s |
| legal | 16 | 0.216 | 0.216 | 0.225 | -0.008 [-0.095, +0.056] | 0 | 0 | 0.00M / 0k | $0.000 | 4.56M | $0.465 | 4.96M | 0.92 | 6s |
| player | 28 | 0.366 | 0.366 | 0.378 | -0.012 [-0.021, -0.004] | 0 | 0 | 0.00M / 0k | $0.000 | 2.04M | $0.207 | 2.14M | 0.95 | 10s |
| med | 28 | 0.095 | 0.095 | 0.141 | -0.046 [-0.111, +0.013] | 0 | 0 | 0.00M / 0k | $0.000 | 2.55M | $0.259 | 2.80M | 0.91 | 10s |

## value/0

| Corpus | Queries | Live | Static | Reference | Live - reference [95% CI] | Patches | Docs read | Patch tokens (in / out) | Patch cost | Build tokens | Build cost | Full-read tokens (est.) | Live total / full read | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cspaper | 14 | 0.112 | 0.112 | 0.118 | -0.006 [-0.019, +0.004] | 1 | 200 | 0.25M / 5k | $0.026 | 0.40M | $0.042 | 0.52M | 1.26 | 4s |
| art | 13 | 0.163 | 0.169 | 0.201 | -0.038 [-0.121, +0.029] | 0 | 0 | 0.00M / 0k | $0.000 | 2.43M | $0.260 | 3.16M | 0.77 | 4s |
| legal | 5 | 0.155 | 0.155 | 0.105 | +0.050 [+0.000, +0.130] | 0 | 0 | 0.00M / 0k | $0.000 | 4.56M | $0.465 | 4.96M | 0.92 | 2s |
| player | 18 | 0.408 | 0.408 | 0.402 | +0.006 [-0.019, +0.044] | 0 | 0 | 0.00M / 0k | $0.000 | 2.04M | $0.207 | 2.14M | 0.95 | 6s |
| med | 14 | 0.161 | 0.161 | 0.189 | -0.027 [-0.119, +0.058] | 0 | 0 | 0.00M / 0k | $0.000 | 2.55M | $0.259 | 2.80M | 0.91 | 5s |

## Drifted minus source, same template (attribute axis)

Each attribute/100 query minus its base query in attribute/0, so query difficulty cancels.

| Corpus | Pairs | Live [95% CI] | Reference [95% CI] | Static |
|---|---|---|---|---|
| cspaper | 21 | -0.070 [-0.147, -0.005] | +0.043 [-0.051, +0.168] | -0.174 |
| art | 21 | +0.092 [-0.051, +0.244] | +0.088 [-0.040, +0.218] | -0.186 |
| legal | 14 | -0.042 [-0.132, +0.052] | -0.031 [-0.155, +0.095] | -0.208 |
| player | 28 | +0.123 [-0.012, +0.268] | +0.089 [-0.036, +0.225] | -0.283 |
| med | 26 | +0.010 [-0.021, +0.045] | -0.019 [-0.047, +0.004] | -0.029 |