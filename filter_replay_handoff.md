# Filter-recall zero-token replay

Start: clean frozen single-action incumbent `aprime_agent.db` (product 0.124). Not the 295-addition database. No new Qwen calls. Classifier unchanged. Additive `WHERE original OR EXISTS(filter_additions)` only. Gold after all five databases were frozen. Official score through `official_sql`.

Stored strategy labels: 0. Evidence metadata: 0. Recoverable positives: 295 majority-accepted additions in `aprime_filter.db`.

Official arm, fixed in advance:

```text
accept iff direct == TRUE and evidence_first == TRUE
```

Critique is not in the primary rule. Semantic inference does not require an exact span.

## Replay scores

Incumbent: F2 0.484071 / F1@0.20 0.178452 / product **0.124399**. DocETL product 0.165643.

| Rule | Proposed | Materialized | SQL-visible | Queries changed | Unchanged | Count Δ | Empty bags | Empty filled | Test empty | F2 | F1@0.20 | Product |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|
| primary (official) | 0 | 0 | 0 | 0 | 99 | 0 | 29 → 29 | 0 | 5 | 0.484071 | 0.178452 | **0.124399** |
| two_true_no_false | 0 | 0 | 0 | 0 | 99 | 0 | 29 → 29 | 0 | 5 | 0.484071 | 0.178452 | 0.124399 |
| evidence_plus_one | 0 | 0 | 0 | 0 | 99 | 0 | 29 → 29 | 0 | 5 | 0.484071 | 0.178452 | 0.124399 |
| strict_grounded | 0 | 0 | 0 | 0 | 99 | 0 | 29 → 29 | 0 | 5 | 0.484071 | 0.178452 | 0.124399 |
| broad_original | 295 | 295 | 295 | 75 | 24 | +327 | 29 → 11 | 18 | 2 | 0.463243 | 0.154977 | **0.102577** |

Invariants on every arm: empty wrap is a no-op, no incumbent witness dropped, no unrelated query bag changed, FALSE never written.

## Overlap

Labeled rules selected the empty set. Pairwise intersections among all five rules are 0 except `broad_original` with itself (295).

| Set | n |
|---|---:|
| primary | 0 |
| two_true_no_false | 0 |
| evidence_plus_one | 0 |
| strict_grounded | 0 |
| broad_original | 295 |
| any labeled rule ∩ broad_original | 0 |

## broad_original bag movement

Count mass +327 on the 75 changed queries. Empty bags filled:

```text
med_groupby20:q10, q11, q16, q17
med_join20:q1, q2, q10, q18
med_filterjoin20:q3, q8, q13, q14, q15, q16, q17, q19
med_multiagg20:q8, q9
```

This reproduces the live 295-addition run (product 0.103).

## Gold precision after freeze

Whole-filter witness grain, stem-aligned. Computed only after the five databases were frozen.

| Cohort | n | TP | FP | Unresolved | Precision |
|---|---:|---:|---:|---:|---:|
| broad_original overall | 295 | 111 | 184 | 0 | 0.376271 |
| pattern `unlabeled_majority_accept` | 295 | 111 | 184 | 0 | 0.376271 |
| evidence metadata present | 0 | 0 | 0 | 0 | — |
| evidence metadata absent | 295 | 111 | 184 | 0 | 0.376271 |
| primary / labeled diagnostics | 0 | 0 | 0 | 0 | — |

52 filter signatures in the 295. 19 have precision ≥ 0.5; 26 have precision 0. Those slices are gold-labeled after freeze, not stored decision rules, and were not used to pick an arm.

| Signature | n | TP | FP | Precision |
|---|---:|---:|---:|---:|
| be7820a9d7fe7ba8 | 6 | 6 | 0 | 1.000 |
| 489cb5695970fb84 | 3 | 3 | 0 | 1.000 |
| c780c1fa9f884974 | 3 | 3 | 0 | 1.000 |
| f6e89834159885ad | 10 | 9 | 1 | 0.900 |
| a9980f470f178fb4 | 5 | 4 | 1 | 0.800 |
| c99c1a75df85a029 | 8 | 6 | 2 | 0.750 |
| bfab6265840c00ef | 18 | 13 | 5 | 0.722 |
| a7f6f2ba421c0a3e | 6 | 4 | 2 | 0.667 |
| 0b67c9b023cb918a | 3 | 2 | 1 | 0.667 |
| 3256274e81acc18b | 3 | 2 | 1 | 0.667 |
| 585363ccbaf1cf39 | 3 | 2 | 1 | 0.667 |
| 585e3b65a1d9ad50 | 3 | 2 | 1 | 0.667 |
| 7d862e20a2e8f3ba | 3 | 2 | 1 | 0.667 |
| ee35b393a253109d | 3 | 2 | 1 | 0.667 |
| c1115fe6b24662c9 | 19 | 12 | 7 | 0.632 |
| f471982cf3189c53 | 10 | 6 | 4 | 0.600 |
| 2d2f5d368e560360 | 9 | 5 | 4 | 0.556 |
| 6a7435c393cff31e | 8 | 4 | 4 | 0.500 |
| cae11ef6408e7e77 | 2 | 1 | 1 | 0.500 |
| 8ec9fcd9b00ab9db | 11 | 5 | 6 | 0.455 |
| 9de62cf37c9552c1 | 23 | 10 | 13 | 0.435 |
| a480d8d495e763cd | 5 | 2 | 3 | 0.400 |
| 298027844feecdab | 3 | 1 | 2 | 0.333 |
| bc9ef24dfb2daba6 | 4 | 1 | 3 | 0.250 |
| 289e24d8ebc7741a | 10 | 2 | 8 | 0.200 |
| 8ea8527a5ba5caa6 | 25 | 2 | 23 | 0.080 |
| 6ace6136f48c5f9c | 10 | 0 | 10 | 0.000 |
| a0f483561e69257a | 7 | 0 | 7 | 0.000 |
| baec59747cab81df | 6 | 0 | 6 | 0.000 |
| 33a315d653c1cf46 | 5 | 0 | 5 | 0.000 |
| 51a3511fb801ac3a | 5 | 0 | 5 | 0.000 |
| 5e4d92239f5caa88 | 5 | 0 | 5 | 0.000 |
| b0b5b8367bf09742 | 5 | 0 | 5 | 0.000 |
| ca611bf39b953ea0 | 5 | 0 | 5 | 0.000 |
| f09401f785b3f902 | 5 | 0 | 5 | 0.000 |
| 0157802f734625a1 | 4 | 0 | 4 | 0.000 |
| 826290a435e4f6b0 | 4 | 0 | 4 | 0.000 |
| 14e4955323fc5ad5 | 3 | 0 | 3 | 0.000 |
| 579a447621a177f2 | 3 | 0 | 3 | 0.000 |
| 57b8f7c40f4b8aa6 | 3 | 0 | 3 | 0.000 |
| 99f43715059dbee3 | 3 | 0 | 3 | 0.000 |
| e77096e96ec60359 | 3 | 0 | 3 | 0.000 |
| 7a67c4365da18b6a | 2 | 0 | 2 | 0.000 |
| ed37d2cede87bc1f | 2 | 0 | 2 | 0.000 |
| fb768621e8a1b643 | 2 | 0 | 2 | 0.000 |
| 28f3499a852c839d | 1 | 0 | 1 | 0.000 |
| 3cda1c2862da8bf9 | 1 | 0 | 1 | 0.000 |
| 59a89cee9fcb45c9 | 1 | 0 | 1 | 0.000 |
| 5b33823a455bf380 | 1 | 0 | 1 | 0.000 |
| bf268453c19b2aeb | 1 | 0 | 1 | 0.000 |
| cfde472f8d4ee145 | 1 | 0 | 1 | 0.000 |
| f31dc33bef013acc | 1 | 0 | 1 | 0.000 |

## Decision

Primary does not beat 0.124. No stored-decision cohort has precision that improved the official product. Stop filter recall. Do not launch another filter prompt variant. Next: distinct-identity oracle.

Eval: `systems/WDIRS/quwarts/eval/filter_replay.py`. Output: `results/quwarts_med_signatures/filter_replay.json`.
