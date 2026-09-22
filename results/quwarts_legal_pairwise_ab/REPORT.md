# Legal A/B pairwise aggregation

Frozen Pass A/B artifacts were not modified. Gold and the A+B 0.1301 reachability assignment were loaded only after `generation_frozen.json`. Fail-closed open guards blocked `shared_reachability`, `cost_aware_reachability`, and `evidence_card_aggregation_audit` before freeze.

## Pre-gold

| Cohort | Count |
| --- | ---: |
| A=B candidate | 228 |
| A=B KEEP | 904 |
| A candidate / B candidate | 682 |
| A candidate / B KEEP | 890 |
| A KEEP / B candidate | 274 |
| Scheduled disagreement cells | 1846 |
| Completed two-judge pairs | 1846 |
| Unscheduled (budget fallback to A) | 0 |
| Judge 1/2 agreement | 1783 |
| Agreed A candidate | 0 |
| Agreed B candidate | 0 |
| Agreed KEEP | 1783 |
| Judge disagreement falling back to A | 63 |
| Parse failures | 4 |
| Official accepted writes | 287 |

Tokens by judge: J1 938,906; J2 950,315.

Tokens by attribute: `legal_basis_num` 440,642; `case_number` 373,635; `plaintiff_current_status` 254,298; `defendant_current_status` 234,575; `hearing_year` 206,480; `first_judge` 147,229; `verdict` 144,485; `case_type` 87,877.

Causal spend: 9,380,309 (frozen A+B 7,491,088 + pairwise 1,889,221), under θ25 = 12,610,011.

Both judges completed every scheduled cell. Judge 2 never selected a candidate. Judge 1 selected a candidate 59 times; those 59 plus 4 missing/invalid parses are the 63 A-fallback disagreements. Independent rebuilds matched every diagnostic bag set.

## Scores

| Arm                    | Causal tokens | Accepted | SQL-visible |     F2 | F1@0.20 | Product |
| ---------------------- | ------------: | -------: | ----------: | -----: | ------: | ------: |
| plumbing               |             0 |        0 |           0 | 0.2054 |  0.0365 |  0.0225 |
| A                      |     3,468,542 |    1,800 |       1,800 | 0.6961 |  0.0958 |  0.0881 |
| B                      |     7,491,088 |    1,184 |       1,184 | 0.4234 |  0.0846 |  0.0706 |
| Judge 1 + A fallback   |     9,380,309 |      288 |         288 | 0.3278 |  0.0655 |  0.0500 |
| Judge 2 + A fallback   |     9,380,309 |      230 |         230 | 0.3278 |  0.0530 |  0.0375 |
| agreement replacements |     9,380,309 |      287 |         287 | 0.3278 |  0.0655 |  0.0500 |
| agreement additions    |     9,380,309 |    1,800 |       1,800 | 0.6961 |  0.0958 |  0.0881 |
| official pairwise      |     9,380,309 |      287 |         287 | 0.3278 |  0.0655 |  0.0500 |
| DocETL                 |    50,440,043 |          |             | 0.7892 |  0.1294 |  0.1235 |

Official pairwise is identical to agreement-only replacements: the judges never agreed on a candidate ID, so the frozen rule keeps A only on the 228 A=B candidate cells and the 59 A-candidate fallbacks, and otherwise writes KEEP. Agreement-only additions equal A because no agreed candidate was added over an A KEEP.

## Official per-query versus A

| Query | A | Official | Delta vs A |
| --- | ---: | ---: | ---: |
| `legal_multiagg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q9` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q7` | 0.0000 | 0.0000 | +0.0000 |
| `legal_multiagg20:q11` | 0.1111 | 0.1111 | +0.0000 |
| `legal_multiagg20:q18` | 0.0343 | 0.0052 | -0.0291 |
| `legal_agg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_groupby20:q14` | 0.3590 | 0.0588 | -0.3002 |
| `legal_agg20:q11` | 0.5000 | 0.2256 | -0.2744 |
| `legal_multiagg20:q9` | 0.0058 | 0.0000 | -0.0058 |
| `legal_agg20:q13` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q17` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q8` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q11` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q15` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q3` | 0.4000 | 0.4000 | +0.0000 |
| `legal_agg20:q14` | 0.0000 | 0.0000 | +0.0000 |

## Post-freeze diagnostics

Pairwise exact accuracy overall: 0.0098. By disagreement type: A candidate/B candidate 0.0205 (14/682); A candidate/B KEEP 0.0045 (4/890); A KEEP/B candidate 0.0000 (0/274).

Exact accuracy over all 2,978 cells: 0.0235. Observational: 0.0500.

Accuracy when judges agree: 0.0000 (all 1,783 agreements were KEEP). Accuracy when judges disagree (A fallback): 0.2857.

Transitions on disagreement cells: A→B 0; B→A 59; candidate→KEEP 1,513; KEEP→candidate 0.

Distance from the diagnostic A+B 0.1301 assignment: 726. Independently recovered candidate IDs: 227 of 904. Those recoveries are almost exactly the 228 cells where A and B already agreed.

Product trajectory across the pairwise schedule: 25% 0.0601; 50% 0.0583; 75% 0.0443; 100% 0.0500. Additional KEEP replacements steadily erase Pass A writes.

The official pairwise database is 0.0500, below Pass A 0.0881 and below Legal DocETL 0.1235. A+B still contain the 0.1301 win; the binary judges did not identify it.

A fallback is better than pairwise aggregation
