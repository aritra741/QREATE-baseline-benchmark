# Legal forced binary A/B aggregation

Frozen Pass A/B artifacts were not modified. Gold and reachability assignments were loaded only after `generation_frozen.json`. Prior pairwise judge outputs were blocked.

## Pre-gold

Synthetic gate: **24/24** correct, **12/12** order-consistent, **12/12** parsed. The frozen prompt then ran on Legal.

| Cohort | Count |
| --- | ---: |
| A=B candidate | 228 |
| A=B plumbing | 904 |
| A candidate / B candidate | 682 |
| A candidate / B plumbing | 890 |
| A plumbing / B candidate | 274 |
| Completed pairs | 1846 |
| Unscheduled A fallbacks | 0 |
| Consistent A | 343 |
| Consistent B | 465 |
| Order disagreements | 1038 |
| Malformed responses | 73 |
| Official accepted writes | 1414 |

Tokens by direction: forward 1,085,292; reverse 1,085,297; gate 13,240.

Tokens by attribute: `legal_basis_num` 506,232; `case_number` 433,048; `plaintiff_current_status` 289,326; `defendant_current_status` 269,340; `hearing_year` 237,432; `first_judge` 170,666; `verdict` 163,795; `case_type` 100,750.

Causal spend: 9,674,917 (frozen A+B 7,491,088 + gate 13,240 + Legal pairs 2,170,589), under θ25 = 12,610,011. Independent rebuilds matched every diagnostic bag set.

Unlike the previous KEEP-escape arm, the model did discriminate: 465 order-consistent B replacements and 343 order-consistent A retentions. Most remaining cells (1,038) were order-sensitive or malformed and fell back to A.

## Scores

| Arm                    | Causal tokens | Accepted |     F2 | F1@0.20 | Product |
| ---------------------- | ------------: | -------: | -----: | ------: | ------: |
| plumbing               |             0 |        0 | 0.2054 |  0.0365 |  0.0225 |
| A                      |     3,468,542 |    1,800 | 0.6961 |  0.0958 |  0.0881 |
| B                      |     7,491,088 |    1,184 | 0.4234 |  0.0846 |  0.0706 |
| forward only           |     9,674,917 |    1,248 | 0.5468 |  0.0783 |  0.0671 |
| reverse only           |     9,674,917 |    1,206 | 0.5337 |  0.0753 |  0.0665 |
| official forced binary |     9,674,917 |    1,414 | 0.6071 |  0.0642 |  0.0556 |
| DocETL                 |    50,440,043 |          | 0.7892 |  0.1294 |  0.1235 |

## Official per-query versus A

| Query | A | Official | Delta vs A |
| --- | ---: | ---: | ---: |
| `legal_multiagg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q9` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q7` | 0.0000 | 0.0000 | +0.0000 |
| `legal_multiagg20:q11` | 0.1111 | 0.0000 | -0.1111 |
| `legal_multiagg20:q18` | 0.0343 | 0.0087 | -0.0256 |
| `legal_agg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_groupby20:q14` | 0.3590 | 0.2256 | -0.1334 |
| `legal_agg20:q11` | 0.5000 | 0.2500 | -0.2500 |
| `legal_multiagg20:q9` | 0.0058 | 0.0058 | +0.0000 |
| `legal_agg20:q13` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q17` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q8` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q11` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q15` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q3` | 0.4000 | 0.4000 | +0.0000 |
| `legal_agg20:q14` | 0.0000 | 0.0000 | +0.0000 |

## Post-freeze diagnostics

Exact accuracy: 0.1014. Observational: 0.2119.

Consistent-A accuracy: 0.1574. Consistent-B accuracy: 0.0280. The 465 B replacements were almost all wrong.

Transitions on disagreement cells: A→B 465; B→A 1,381; candidate→plumbing 388; plumbing→candidate 2.

Distance from the diagnostic A+B 0.1301 assignment: 908. Independently recovered candidate IDs: 650 / 904.

Product by schedule prefix: 25% 0.0630; 50% 0.0628; 75% 0.0628; 100% 0.0556.

The official forced-binary database is 0.0556, below Pass A 0.0881 and below Legal DocETL 0.1235. The prompt can discriminate synthetic fixtures and does choose between A and B on Legal, but order-consistent B choices harm A. Prompt and voting variants should stop here.

forced binary harms A
