# Legal corpus-grounded sample-probe optimizer

Resumed from the paused silver journal (752 / 768 already done). Benchmark gold was loaded only after `generation_frozen.json`.

## Pre-gold

Sample: 64 train / 32 held-out. Silver cells: 768 (462 value, 300 not present, 6 unresolved, 202 adjudicated, 116 mapped to a frozen candidate). Context: 640 whole-document, 128 exhaustive chunk.

Selected programs: `case_number:3`, `case_type:4`, `defendant_current_status:3`, `first_judge:4`, `hearing_year:4`, `legal_basis_num:4`, `plaintiff_current_status:4`, `verdict:4`.

Held-out silver winner product 0.2801 (LCB 0.1390). Official accepted writes 893.

Tokens: silver probe 6,168,652; silver adjudicate 415,266; silver scan 302,273; program synthesize 589,813; program critique 40,555. Causal spend 7,516,559, under θ25.

## Scores

| Arm                    | Causal tokens | Accepted |     F2 | F1@0.20 | Product |
| ---------------------- | ------------: | -------: | -----: | ------: | ------: |
| plumbing               |             0 |        0 | 0.2054 |  0.0365 |  0.0225 |
| official corpus-probe  |     7,516,559 |      893 | 0.4558 |  0.0564 |  0.0376 |
| DocETL                 |    50,440,043 |          | 0.7892 |  0.1294 |  0.1235 |

## Per-query versus plumbing

| Query | Plumbing | Official | Delta |
| --- | ---: | ---: | ---: |
| `legal_multiagg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q9` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q7` | 0.0000 | 0.0000 | +0.0000 |
| `legal_multiagg20:q11` | 0.0952 | 0.0000 | -0.0952 |
| `legal_multiagg20:q18` | 0.0052 | 0.0000 | -0.0052 |
| `legal_agg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_groupby20:q14` | 0.0588 | 0.2079 | +0.1491 |
| `legal_agg20:q11` | 0.0000 | 0.1852 | +0.1852 |
| `legal_multiagg20:q9` | 0.0000 | 0.0080 | +0.0080 |
| `legal_agg20:q13` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q17` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q8` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q11` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q15` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q3` | 0.2000 | 0.2000 | +0.0000 |
| `legal_agg20:q14` | 0.0000 | 0.0000 | +0.0000 |

Silver-held ranking of considered configs matched gold ranking (`calibrated=true`). The official database is 0.0376, above plumbing 0.0225 and far below DocETL 0.1235. Only 116 / 768 silver cells mapped onto a frozen candidate, so compiled programs had little transferable supervision.

corpus probes rank plans correctly but available programs remain insufficient
