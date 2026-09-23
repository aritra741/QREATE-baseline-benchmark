# Fused query maps

Decision: `fused query maps beat Legal DocETL`

Each document is sent once for a compatible pair. The two queries keep separate field namespaces, and SQLite runs the original SQL on a query-local relation. The official policy is `fusion_same_attribute`.

| Checkpoint | Queries | Product | F2 | Cell F1@0.20 | Tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| θ25 | 10 | 0.1392681566553747 | 0.5812648025717464 | 0.16332417582417583 | 10,769,944 |
| θ50 | 16 | 0.14382694759870493 | 0.8069935355289884 | 0.17591765873015874 | 18,412,006 |
| θ75 | 16 | 0.14382694759870493 | 0.8069935355289884 | 0.17591765873015874 | 18,412,006 |
| Plumbing | 16 | 0.022455905439098717 | | | |
| WCCI | 16 | 0.09594618648894966 | | | |
| Legal DocETL | 16 | 0.12350932750098194 | | | 50,440,043 |

θ50 and θ75 are the same journal. The full plan reserved 18,227,575 tokens and finished at 18,412,006, under both ceilings. θ25 is a byte prefix. Token use is 36.5% of DocETL.

`fusion_direct` scores 0.13543970219666815. `fusion_same_attribute` scores 0.14382694759870493.

## Execution

Eight eligible pairs cover all 16 queries. 4,096 calls were fused and 928 were singleton splits after a section union would not fit. 2,804 calls used the whole document and 2,220 used ordered sections.

Subresults: 1,880 valid, 6,351 repaired, 889 terminal fallbacks. Errors: 87 malformed outputs and 802 wrong types. θ75 has no empty bags and no SQL execution failures. θ25 has one empty bag because six queries were still on plumbing.

## Per-query product at θ75

Nonzero: legal_agg20:q13 0.500000, legal_filter20:q8 0.500000, legal_filter20:q9 0.451128, legal_agg20:q11 0.451128, legal_groupby20:q14 0.225564, legal_multiagg20:q9 0.121124, legal_multiagg20:q18 0.052288. The other nine queries are 0.
