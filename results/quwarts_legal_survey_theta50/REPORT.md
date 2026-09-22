# Control-variate survey query execution

Conclusion: `survey estimates are too unstable to replace WCCI`

Product: 0.09594618648894966
F2: 0.5919736853589251
Cell F1@0.20: 0.11209985190248349
Tokens: 14067427
Survey-accepted queries: 0
WCCI fallbacks: 16
DocETL product: 0.12350932750098194
WCCI product: 0.09594618648894966

| query | product | decision |
| --- | ---: | --- |
| legal_multiagg20:q4 | 0.0 | wcci_fallback |
| legal_filter20:q9 | 0.22556390977443613 | wcci_fallback |
| legal_filter20:q7 | 0.25 | wcci_fallback |
| legal_multiagg20:q11 | 0.0 | wcci_fallback |
| legal_multiagg20:q18 | 0.06379585326953748 | wcci_fallback |
| legal_agg20:q4 | 0.0 | wcci_fallback |
| legal_groupby20:q14 | 0.07792207792207792 | wcci_fallback |
| legal_agg20:q11 | 0.25 | wcci_fallback |
| legal_multiagg20:q9 | 0.0 | wcci_fallback |
| legal_agg20:q13 | 0.0 | wcci_fallback |
| legal_agg20:q17 | 0.0 | wcci_fallback |
| legal_filter20:q8 | 0.0 | wcci_fallback |
| legal_filter20:q11 | 0.0 | wcci_fallback |
| legal_filter20:q15 | 0.2678571428571429 | wcci_fallback |
| legal_agg20:q3 | 0.4000000000000001 | wcci_fallback |
| legal_agg20:q14 | 0.0 | wcci_fallback |

The contribution programs reproduced all 16 frozen WCCI bags before any Qwen call. The official hybrid bag is the WCCI bag on every query. Cumulative spend is 14,067,427 tokens, including the frozen WCCI spend of 1,639,733. The WCCI database hash is unchanged.

Ignoring the acceptance gate, the survey-all product is 0.07548778549165547, below WCCI. The oracle that picks the better frozen bag per query also stays at the WCCI product, so no survey bag was the better bag. Direct query-answer prompting was not run. Semantic validation did not run on any cell: no proposed TRUE support survived deterministic citation checks, so extraction without semantic validation is the same estimator.

The miss is not one model-quality bucket:

* Sampling variance did not bind. Half-sample, effective-sample-size, and numeric-interval checks were never reached. Known validated responses were 0 for 13 queries, 1 for two queries, and 20 covered absences for `legal_filter20:q15`.
* Contribution-label error did bind. Of 2,800 query-document extractions, 1,746 failed offset checks and 1,017 were UNKNOWN. 1,727 offset failures were text mismatches: the model named a year or label while the offsets pointed at different characters. 488 proposed supports were TRUE and none survived. 22 FALSE absences had complete coverage.
* Missing group-domain error was not observed. No validated group key formed a survey domain.
* Numeric-role error was not reached. Year-as-count and ambiguous-number checks sit behind the offset check.
* Fallback-gate conservatism did not hide a win. The unaccepted survey bags score below WCCI, and the oracle does not promote any of them.

No further Legal prompt or voting variant follows from this arm.
