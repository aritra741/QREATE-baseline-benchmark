# Deterministic evidence re-anchoring

Conclusion: `re-anchoring enables estimation but repaired survey remains below DocETL`

The original survey artifacts were not modified. Extraction prompts, the sample, contribution programs, the estimator, and the acceptance thresholds are the frozen ones. The only new model calls were the frozen semantic validator, after the gold-free recovery gate passed.

Returned offsets do not address the source document. Across the 1,746 offset failures there were no matches to source codepoints, UTF-8 bytes, chunk coordinates, or the rendered prompt. 1,078 cited strings occur exactly once in the source, 339 are repeated, 26 match only after the frozen normalization, and 303 have no coherent coordinate system.

Re-anchoring recovered 1,067 exact rendered-context spans, 158 repeated spans with the same contribution, 26 normalized spans, and 22 frozen-candidate spans. 471 responses stayed rejected. That left 66 SQL-visible TRUE contributions and 8 queries with at least 10 known contributions, so the recovery gate passed.

The validator accepted 56 of those 66 contributions and rejected 10. The frozen acceptance rule then kept every WCCI bag. `legal_agg20:q3` had 46 validator accepts and was rejected for a response rate below 0.45 among WCCI-supported documents. `legal_agg20:q4` had 10 accepts, below the frozen minimum of 20 known responses. Neither query reached the half-sample or interval gates. This is not a sampling-variance result. The addresses were repaired, and the validated contributions were still too few for the frozen response gates.

| Arm | Product | Accepted queries | Known contributions | Tokens |
| --- | ---: | ---: | ---: | ---: |
| WCCI | 0.09594618648894966 | — | full corpus | 1639733 |
| original survey | 0.09594618648894966 | 0 | 22 | 14067427 |
| re-anchored before semantic validation | 0.09594618648894966 | 0 | 66 | 14067427 |
| repaired official survey | 0.09594618648894966 | 0 | 56 | 14096994 |
| DocETL | 0.12350932750098194 | — | — | 50440043 |

The pre-validator row uses the same acceptance rule. It also falls back on every query, so its product is the WCCI product. Official F2 is 0.5919736853589251 and cell F1@0.20 is 0.11209985190248349. The WCCI database hash is unchanged, and every fallback bag matches the frozen WCCI bag.

| query | original known | recovered known | validator accept / reject | decision | product |
| --- | ---: | ---: | --- | --- | ---: |
| legal_agg20:q3 | 0 | 62 | 46 / 2 | wcci_fallback, low response rate | 0.4000000000000001 |
| legal_agg20:q4 | 0 | 14 | 10 / 3 | wcci_fallback, too few responses | 0.0 |
| legal_filter20:q9 | 1 | 19 | 0 / 5 | wcci_fallback, too few responses | 0.22556390977443613 |
| legal_filter20:q15 | 20 | 33 | 0 / 0 | wcci_fallback, low response rate | 0.2678571428571429 |
| legal_multiagg20:q11 | 0 | 27 | 0 / 0 | wcci_fallback, low response rate | 0.0 |
| legal_multiagg20:q18 | 0 | 28 | 0 / 0 | wcci_fallback, low response rate | 0.06379585326953748 |
| legal_multiagg20:q9 | 0 | 18 | 0 / 0 | wcci_fallback, too few responses | 0.0 |
| legal_filter20:q7 | 0 | 11 | 0 / 0 | wcci_fallback, too few responses | 0.25 |
| legal_agg20:q17 | 0 | 9 | 0 / 0 | wcci_fallback, too few responses | 0.0 |
| legal_agg20:q11 | 1 | 8 | 0 / 0 | wcci_fallback, too few responses | 0.25 |
| legal_filter20:q11 | 0 | 5 | 0 / 0 | wcci_fallback, too few responses | 0.0 |
| legal_multiagg20:q4 | 0 | 2 | 0 / 0 | wcci_fallback, too few responses | 0.0 |
| legal_agg20:q14 | 0 | 1 | 0 / 0 | wcci_fallback, too few responses | 0.0 |
| legal_groupby20:q14 | 0 | 0 | 0 / 0 | wcci_fallback, too few responses | 0.07792207792207792 |
| legal_agg20:q13 | 0 | 0 | 0 / 0 | wcci_fallback, too few responses | 0.0 |
| legal_filter20:q8 | 0 | 0 | 0 / 0 | wcci_fallback, too few responses | 0.0 |

No new extraction prompt, replica, or vote follows from this repair.
