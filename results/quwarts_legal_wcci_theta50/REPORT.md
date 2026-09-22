# Workload-calibrated collective inference

Conclusion: `collective inference improves Legal but remains below DocETL`

Selected plan: `bootstrap_robust`
Product: 0.09594618648894966
F2: 0.5919736853589251
Cell F1@0.20: 0.11209985190248349
DocETL product: 0.12350932750098194
Tokens: 1639733
Writes: 2550
Probe-validation utility: 0.8552631578947368
Probe-test utility: 0.7513812154696132
Design hash: `31a65335c4837927c93d3c4998695875aba986dbdb7fb3260e90bae4465c753b`
Database hash: `52a772cd04a1f8abe19d9ed73091779ef0593f6e681c4847095e3b2ce9936117`
Bag hash: `3bf8f1764778ef5fb332a3d9179b70f3204e6f26afcfb3fdf901d1db35021615`

| query | product |
| --- | ---: |
| legal_multiagg20:q4 | 0.0 |
| legal_filter20:q9 | 0.22556390977443613 |
| legal_filter20:q7 | 0.25 |
| legal_multiagg20:q11 | 0.0 |
| legal_multiagg20:q18 | 0.06379585326953748 |
| legal_agg20:q4 | 0.0 |
| legal_groupby20:q14 | 0.07792207792207792 |
| legal_agg20:q11 | 0.25 |
| legal_multiagg20:q9 | 0.0 |
| legal_agg20:q13 | 0.0 |
| legal_agg20:q17 | 0.0 |
| legal_filter20:q8 | 0.0 |
| legal_filter20:q11 | 0.0 |
| legal_filter20:q15 | 0.2678571428571429 |
| legal_agg20:q3 | 0.4000000000000001 |
| legal_agg20:q14 | 0.0 |

Plumbing product: 0.022455905439098717. The official plan is above plumbing and below DocETL.

Probe-validation utility was 0.8552631578947368. Untouched probe-test utility was 0.7513812154696132. That is a generalization drop, and it stays above the plumbing probe utility of 0.5263157894736842, so the scorer transferred incompletely rather than collapsing.

The frozen plan-selection rule chose `bootstrap_robust` because its lower confidence bound matched `scorer_only` and beat the constrained plans. Presence and pairwise penalties cut validation utility from 0.855 to 0.776, so those population constraints did not survive held-out probe selection. On gold, the diagnostic pairwise and full-WCCI ablations score 0.09694299669628618, slightly above the official 0.09594618648894966. They are not promoted.

Queries that remain wrong are the numeric and group interactions. Product stays 0 for `legal_multiagg20:q4`, `legal_multiagg20:q11`, `legal_multiagg20:q9`, `legal_agg20:q4`, `legal_agg20:q13`, `legal_agg20:q17`, `legal_agg20:q14`, `legal_filter20:q8`, and `legal_filter20:q11`. Several of those have structure F2 of 1 and cell F1 of 0: the bag shape appears, and the CASE bands on `case_number` and `legal_basis_num`, plus `first_judge` group counts, are still wrong. Filters on hearing year, verdict, and some party status moved.

Against the diagnostic reachability fills, 496 of 1,351 overlapping cells agree (0.3671354552183568). That comparison was not used to choose the plan.

| ablation | product | writes | official |
| --- | ---: | ---: | --- |
| plumbing | 0.022455905439098717 | 0 | no |
| scorer only | 0.09594618648894966 | 2550 | no |
| univariate constraints | 0.09594618648894966 | 2321 | no |
| pairwise constraints | 0.09694299669628618 | 2044 | no |
| query-observable constraints | 0.09694299669628618 | 2044 | no |
| full WCCI | 0.09694299669628618 | 2044 | no |
| conservative | 0.016176470588235296 | 922 | no |
| bootstrap-robust | 0.09594618648894966 | 2550 | yes |

No further Legal prompt, vote, replica, threshold change, or budget increase follows from this arm.
