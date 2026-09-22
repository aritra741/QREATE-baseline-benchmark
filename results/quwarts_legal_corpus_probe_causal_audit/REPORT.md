# Legal corpus-probe causal audit

Zero Qwen. Frozen corpus-probe artifacts were not modified. The 0.1886 figure is cited only as prior evidence that deterministic candidates can realize a shared assignment; that assignment was not executed.

Decision: silver reference is inaccurate

Replace silver labels with a checked extractor before any program search; the current references do not match gold often enough to supervise a selector.

## Silver reference

Cells 768. Silver-correct (exact, typed, or correct NULL presence) 0.284. Exact on gold-positive cells 113/723 = 0.156. Train 0.291 (512 cells), held-out 0.270 (256 cells).

Class counts: exact 113, typed-only 71, observational-only 96, incorrect value 171, incorrect value on null gold 11, incorrect `NOT_PRESENT` 266, correct null presence 34, unresolved 6. `NOT_PRESENT` is the largest error, not an unresolved or mapper bucket.

| Attribute | n | exact | silver-correct | incorrect NOT_PRESENT |
| --- | ---: | ---: | ---: | ---: |
| case_number | 96 | 0.052 | 0.062 | 0.323 |
| case_type | 96 | 0.021 | 0.271 | 0.021 |
| defendant_current_status | 96 | 0.000 | 0.042 | 0.802 |
| first_judge | 96 | 0.146 | 0.146 | 0.594 |
| hearing_year | 96 | 0.573 | 0.573 | 0.156 |
| legal_basis_num | 96 | 0.385 | 0.385 | 0.271 |
| plaintiff_current_status | 96 | 0.000 | 0.375 | 0.438 |
| verdict | 96 | 0.000 | 0.417 | 0.167 |

## Mapping cross-tab

| Silver correct? | Gold-equivalent candidate? | Silver-equivalent candidate? | Mapper selected it? | Count |
| --- | --- | --- | --- | ---: |
| False | False | False | False | 155 |
| True | False | False | False | 105 |
| True | True | True | True | 60 |
| False | True | True | False | 36 |
| False | False | True | False | 29 |
| False | False | True | True | 29 |
| False | True | True | True | 27 |
| True | True | True | False | 11 |
| True | False | True | False | 8 |
| False | True | False | False | 2 |

Mapped 116/768. Mapped silver-value 116/462. Gold-equivalent candidate 227/723. Correctly mapped 60/184. Observationally mappable 71/184.

## Ceilings

Restricting SQL to the 96 sampled rows and scoring against full-corpus gold collapses structure F2 to 0, because the official answers were computed on all 570 rows. The products below keep the official 570-row database. A and B write only on the sampled entities. D is the exact maximum over the frozen program family on the full corpus. Identical program fills collapse 5^8 = 390,625 labelings to 81 distinct configurations; all 81 were scored.

| Ceiling | Accepted | F2 | F1@0.20 | Product |
| --- | ---: | ---: | ---: | ---: |
| A gold-best candidate on the 96-entity sample, embedded in the 570-row database | 226 | 0.4694 | 0.0537 | 0.0374 |
| B silver-correct cells mapped by equivalence, same embedding | 52 | 0.2273 | 0.0351 | 0.0234 |
| C case_number `case_number:0` | 66 | 0.2054 | 0.0282 | 0.0165 |
| C case_type `case_type:0` | 54 | 0.2649 | 0.0354 | 0.0236 |
| C defendant_current_status `defendant_current_status:0` | 321 | 0.2402 | 0.0365 | 0.0225 |
| C first_judge `first_judge:0` | 185 | 0.2115 | 0.0365 | 0.0225 |
| C hearing_year `hearing_year:0` | 13 | 0.2054 | 0.0365 | 0.0225 |
| C legal_basis_num `legal_basis_num:2` | 44 | 0.2233 | 0.0351 | 0.0234 |
| C plaintiff_current_status `plaintiff_current_status:0` | 154 | 0.2218 | 0.0574 | 0.0340 |
| C verdict `verdict:0` | 43 | 0.2054 | 0.0365 | 0.0225 |
| D best frozen 8-program family (81 exact configs) | 1007 | 0.4320 | 0.0625 | 0.0446 |
| DocETL |  |  |  | 0.1235 |

Any frozen eight-program configuration beats 0.1235: False. Configurations above DocETL: 0.

## Calibration

Compared configurations: 33. Spearman held-out silver vs gold 0.6554970344941643. Kendall 0.6827586206896552.
Selected gold 0.03756624217150533. Best compared gold 0.03756624217150533. Best family gold 0.04460751960751961. Regret vs best family 0.007041277436014279.
Held-out silver product 0.2801 is a 32-row score against a silver-materialized database. Official 0.0376 is a 570-row score against benchmark gold. The gap is mostly a change of label and population, not only a rank error.

## Extrapolation

| Attribute | Mapped train + | KEEP train | Full writes | Ratio | Write exact precision | Unseen channels |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| case_number | 14 | 50 | 155 | 11.1 | 0.039 | normalized |
| case_type | 4 | 60 | 54 | 13.5 | 0.222 | normalized, surface |
| defendant_current_status | 0 | 64 | 252 | 252.0 | 0.230 | normalized, surface, workload_label |
| first_judge | 2 | 62 | 185 | 92.5 | 0.000 | surface |
| hearing_year | 19 | 45 | 13 | 0.7 | 0.154 | — |
| legal_basis_num | 32 | 32 | 37 | 1.2 | 0.432 | — |
| plaintiff_current_status | 0 | 64 | 154 | 154.0 | 0.000 | surface, workload_label |
| verdict | 5 | 59 | 43 | 8.6 | 0.000 | normalized, surface |

## Regressions

`legal_multiagg20:q11` plumbing 0.0952 → official 0.0000. Reverting every `case_number` write restores 0.1111. Reverting any other attribute leaves the product at 0. No single `case_number` write moves the product.
Class: count inflation. The query keeps `WHERE case_number IS NOT NULL`. Joint NULL-to-value fills change group counts and `AVG(case_number)` together.

`legal_multiagg20:q18` plumbing 0.0052 → official 0.0000. Reverting every `case_number` write restores 0.0095. Reverting `defendant_current_status` or `plaintiff_current_status` alone only returns the product to the plumbing value. No single write moves the product.
Class: count inflation through the same `case_number IS NOT NULL` filter, which also changes the `HAVING COUNT(*) >= 3` groups.

## Hashes

```json
{
  "silver_journal": "8fcb48291166d936d5f6170cc0d9796f73daaa219db8879fc3c2d9b4c98d2edb",
  "programs": "4cdcd21f899d61b65243af5e92ad1efd1ac2054a4df5478dfe2a2d06690af06a",
  "sample_split": "2e4a6b9da598c9e2d90cd0c55c502d76422aa3145fe5ca4f058733ba5cb5d8f3",
  "assignment": "c7193f165eeaf8f7232993b1a3a00489606cb412fd2e500f666866db45492c4c",
  "official_db": "57184bfc669b43e473bc7cebe51bec1f641984bb8da29f970d48135817381f24",
  "inventory": "42ef0a8c8247d78a96387898810eef929205d5c78a87d72abed8cf90658cb815",
  "generation_frozen": "689f956b3206706545af4a67dfd0cabd8a3a7ed41e2b4231d309ae94638b389e"
}
```

silver reference is inaccurate
