# Integrity audit of the frozen Legal checked-extraction ranker

No Qwen calls. Frozen files under `results/quwarts_legal_checked_rank/` were not modified. Diagnostic databases are in this directory only.

## 1. Canonical cell universe

There is one row for each of 120 entities × 8 attributes = **960** cells. The journal has 960 lines, **0** duplicate keys, **0** missing cells, and **0** cells with more than one terminal state. Train and validation entities are disjoint (640 and 320 cells). All 120 sample entities have a completed scan. Three scan-journal entities are outside this sample and were not labeled.

| Terminal state | Cells |
| --- | ---: |
| `CANDIDATE` | 92 |
| `KEEP_PLUMBING` | 425 |
| `UNCERTAIN` | 443 |
| `MISSING_PIPELINE_OUTPUT` | 0 |

`Cells = 537` is the non-incumbent subset. Plumbing already held a value on **423** cells, and those were recorded as `KEEP_PLUMBING` with reason `incumbent_non_null` without a matcher call. 960 − 423 = 537.

The two-cell gap between 92 + 443 = 535 and 537 is the **2** extracted `KEEP_PLUMBING` decisions. Those are the only absence claims. The other 423 KEEP rows are incumbents, not checked absences. 423 + 2 = 425.

## 2. Denominators

Each table uses one denominator. Rates the original report mixed across 537 and 960 are separated here.

### All 960 canonical cells

| Metric | Numerator | Denominator | Rate |
| --- | ---: | ---: | ---: |
| Exact accuracy | 47 | 960 | 0.0490 |
| Observational, UNCERTAIN counted as miss | 81 | 960 | 0.0844 |
| Committed-candidate observational accuracy | 67 | 92 | 0.7283 |
| Decided-label observational accuracy | 81 | 517 | 0.1567 |
| Candidate rate | 92 | 960 | 0.0958 |
| KEEP rate | 425 | 960 | 0.4427 |
| UNCERTAIN rate | 443 | 960 | 0.4615 |
| Candidate coverage of gold-positive cells | 322 | 910 | 0.3538 |
| False absence, incumbents included | 411 | 910 | 0.4516 |

The 411 false-absence numerator counts incumbent KEEP cells whose plumbing value is not the gold value. Those cells were not absence decisions.

### Published non-incumbent universe (the report's 537)

| Metric | Numerator | Denominator | Rate |
| --- | ---: | ---: | ---: |
| Exact accuracy | 33 | 537 | 0.0615 |
| Observational, UNCERTAIN counted as miss | 67 | 537 | 0.1248 |
| Committed-candidate observational accuracy | 67 | 92 | 0.7283 |
| Decided-label observational accuracy | 67 | 94 | 0.7128 |
| Candidate rate | 92 | 537 | 0.1713 |
| KEEP rate | 2 | 537 | 0.0037 |
| UNCERTAIN rate | 443 | 537 | 0.8250 |
| Candidate coverage | 322 | 501 | 0.6427 |
| False absence | 2 | 501 | 0.0040 |

The original KEEP rate of 0.4427 used 425/960, while the candidate and UNCERTAIN rates used 537. Exact 0.0615, observational-including-UNCERTAIN 0.1248, committed-candidate 0.7283, decided 0.7128, coverage 0.6427, and false absence 0.0040 match this 537-cell table.

### Committed candidate labels only (92)

Observational accuracy **67/92 = 0.7283**. Exact accuracy **33/92 = 0.3587**. Gold-positive coverage inside this subset is **78/90 = 0.8667**.

`checked references are accurate` is supported on these 92 committed decisions. It is not supported on the full reference population: observational accuracy on all 960 cells is **81/960 = 0.0844**, and 443 cells are `UNCERTAIN`.

### Ranker-training cells (60) and ranker-validation cells (34)

These are non-incumbent, non-UNCERTAIN cells that entered the matrix. Dropped groups: **0**.

| Universe | Checked label vs gold | Candidate rate | KEEP rate |
| --- | --- | ---: | ---: |
| 60 training cells | 43/60 = 0.7167 observational | 60/60 | 0/60 |
| 34 validation cells | 24/34 = 0.7059 observational | 32/34 | 2/34 |

Ranker agreement with the checked label, using the deployed trace:

| Universe | Numerator | Denominator | Rate |
| --- | ---: | ---: | ---: |
| Training cells | 4 | 60 | 0.0667 |
| Validation cells | 2 | 34 | 0.0588 |
| All 537 non-incumbent cells, the published agreement denominator | 6 | 537 | 0.0112 |

The published validation agreement of about 0.0108 was 2/186 non-incumbent validation cells, including `UNCERTAIN` cells the ranker was never trained on. On the 34 cells actually used for validation, deployed agreement is 2/34.

## 3. What the ranker was trained on

The matrix has **1,319** rows (842 train, 477 validation), **817** positives and **502** negatives, **60** train groups and **34** validation groups. Labels are pointwise 0/1. Candidate IDs are not classes. No entity is in both splits. Class weights are uniform. `GroupKFold` was a diagnostic grid only; the fitted model is not a grouped ranker.

Every raw positive ID exists in that cell's candidate list (**0** missing). No equivalent ID was stored as a negative. `UNCERTAIN` cells were skipped, not converted to KEEP or to a negative. `KEEP` is the all-zero channel row with the keep bit set, at both fit and apply. Write confidence is the selected row's P(y=1): **0** writes carry the KEEP feature vector. Abstentions log the rejected top candidate's score, not the KEEP row's score.

The positive set is not the committed ID. `equivalent_ids` marks another candidate positive when substituting it leaves every workload query's result unchanged on that plumbing row. On mostly null rows that tie is common. Of 60 training cells, **15** have one positive ID, **45** have an expanded set, and **24** mark every candidate positive. Median positive fraction is **0.93**. `first_judge` has **0** candidate labels in the sample (70 incumbent KEEP and 50 UNCERTAIN). Both extracted KEEP labels are in validation, so training has **0** positive KEEP rows.

Three training columns have zero variance. Two are constant by construction: `plumbing_null` (only null cells are trained) and `amplification` (every attribute was marked amplification-sensitive, so the 0.75 floor replaces the selected 0.55 threshold on every cell). Opposite-label feature collisions: **0**.

## 4. Overfit tests

Unconstrained argmax, no threshold, selected hyperparameters (50 trees, depth 2, learning rate 0.1), train on the 60 training cells and score those same cells:

| Test | Top-1 | Positive-set recall |
| --- | --- | --- |
| Selected features | 48/60 = 0.8000 | 486/525 = 0.9257 |
| Plus a cell identifier | 46/60 = 0.7667 | — |
| Plus a unique row identifier | 50/60 = 0.8333 | 492/525 = 0.9371 |

A cell identifier cannot separate candidates inside one group, and it does not improve fit. The row identifier improves top-1 only from 48 to 50. The learner does fit the supplied labels (set recall 0.93). It does not fail the broken-pipeline gate. KEEP accuracy has denominator 0 because training contains no KEEP-positive cell. `case_number` top-1 is 2/6; `first_judge` is absent.

The hand fixture ranks both cells correctly (top-1 2/2, set recall 4/4). Cell A recovers `c1`. Cell B's two equivalent positives tie, the margin is 0, and the frozen rule returns `KEEP_PLUMBING` instead of either positive ID. Ranking works. Threshold recovery does not, when the runner-up is an equivalent positive.

Baselines on the same **34** validation cells:

| Policy | Top-1 vs checked label |
| --- | --- |
| Checked label | 34/34 = 1.0000 |
| Highest-priority channel | 20/34 = 0.5882 |
| Random, seed 120 | 18/34 = 0.5294 |
| Train-only ranker, frozen threshold | 6/34 = 0.1765 |
| Always KEEP / always abstain | 2/34 = 0.0588 |
| Deployed full-corpus trace | 2/34 = 0.0588 |

The deployed trace was produced by a model refit on train and validation together, so that row is not a held-out score. The train-only ranker under the frozen write rule is still well below the channel baseline and the random baseline. Unconstrained training fit is real; the write rule does not reproduce it. The ranker does not operationally overfit its training labels: deployed agreement on those 60 cells is 4/60.

## 5. Checker versus ranker

| Database | Writes | Product | What moves |
| --- | ---: | ---: | --- |
| Plumbing | 0 | 0.0225 | — |
| 92 committed checked decisions | 92 | 0.0298 | `legal_filter20:q11` 0.0000 → 0.1176 |
| Verifier-agreed subset | 80 | 0.0298 | same `q11` move |
| Ranker on the 16 sample writes | 16 | 0.0225 | no query moves |
| Ranker on the 136 full-corpus writes | 136 | 0.0350 | `legal_agg20:q3` 0.2000 → 0.4000 |

The 92 committed labels are the best cell-level references and still only reach product 0.0298. The sample ranker writes add nothing. The full-corpus ranker adds a different query, `q3`, and does not recover the checker's `q11` gain. Checker quality, ranker compression, and extrapolation are separate losses. None approaches DocETL at 0.1235.

## 6. Extrapolation

Of 136 full-corpus writes, **1** is on `first_judge`, the attribute with zero positive training rows. That write is also the one unseen channel. Median Euclidean distance to the nearest positive training vector of the same attribute is **0.80**. Forcing that zero-positive attribute back to KEEP leaves 135 writes and the same product, **0.0350**.

## 7. Budget

Spend is 3,626,478 / 12,610,011 because the sample was frozen at 120 entities. The protocol shrinks the sample when a call would exceed a cap; it never enlarges the sample when spend lands under the cap. Incumbent cells make no calls. Observed cost is **30,221** tokens per sample entity. Remaining budget can fund **297** further complete entity packages. 450 entities were not in the sample. Scan used 997,621 of 8,196,507. Verification and absence used 1,989,565 of 3,152,502. Adjudication used 639,292 against a 630,500 cap. Those calls were not run.

## Causes

| Cause | Count |
| --- | ---: |
| Query-result equivalence expanded the positive set | 45 of 60 training cells |
| `UNCERTAIN` cells excluded from supervision | 443 |
| Training cells with a KEEP-positive label | 0 |
| Validation cells the frozen ranker misses while the channel baseline is the comparator | ranker 6/34, channel baseline 20/34 |
| Published metrics whose denominator is the 537-cell subset rather than 960 | the `Cells = 537` block |

The unique-row memorization test still reaches set recall 492/525, so the learner is not a broken pipeline. The labels it receives, the write rule, the missing supervision, and the reported denominators are separate failures.

mixed failure

Use the committed candidate ID, plus value-identical aliases only, as the positive set. Do not mark a candidate positive because a single-row query result is unchanged, and do not abstain when the runner-up is in that same positive set.
