# Legal deterministic evidence-card selection

No frozen candidate, plumbing, or query artifact was modified. Reachability assignment manifests were blocked before the first spend. Gold was loaded only after `generation_frozen.json`.

The official result is the predeclared θ25 majority-plus-adjudication database. It scores **0.0639**, below Legal DocETL **0.1235**. The frozen deterministic inventory still contains the diagnostic 0.1886 assignment, so the candidates are sufficient and the selector did not realize them.

## Pre-gold

- Selectable cells: **2958** (20 auto-`KEEP_PLUMBING`)
- Candidate-count distribution: min 0, mean 13.07, max 26
- Cards pruned: **0** (every frozen surface, normalized, and workload-label candidate retained)
- Tokens estimated for Pass A: 3,293,948 reserved
- Tokens spent: **12,056,166** / 12,610,011

| Purpose | Calls | Tokens |
| --- | ---: | ---: |
| Pass A | 2958 | 3,452,863 |
| Pass A repair | 35 | 15,679 |
| Pass B | 2958 | 3,376,185 |
| Pass B repair | 1395 | 646,361 |
| Pass C | 2958 | 3,359,962 |
| Pass C repair | 48 | 22,862 |
| Adjudicate | 1062 | 1,178,367 |
| Adjudicate repair | 10 | 3,887 |

Completed cells by checkpoint (journal prefix; missing later passes are abstentions):

| Checkpoint | Spent | Pass A | Pass B | Pass C | Adjudication |
| --- | ---: | ---: | ---: | ---: | ---: |
| θ5 = 2,522,002 | 2,521,972 | 2055 | 0 | 0 | 0 |
| θ10 = 5,044,004 | 5,043,249 | 2958 | 1091 | 0 | 0 |
| θ25 = 12,610,011 | 12,056,166 | 2958 | 2958 | 2958 | 1062 |

Agreement:

- Unanimous candidate: **343**
- Two-of-three candidate: **867**
- Majority `KEEP_PLUMBING`: **2094**
- Three-way conflict: **1062**
- Single abstention: 14
- Auto-keep (no deterministic candidate): 20

Adjudicator: 775 candidate / 287 `KEEP_PLUMBING`. Malformed parsed responses: 0. Format repairs: 1488 (Pass B accounted for 1395). Official accepted cells: **1659**. SQL-visible cells: **1659**. Reachability artifacts remained inaccessible through freeze.

## Post-freeze scores

| Arm               |     Tokens | Accepted | SQL-visible |     F2 | F1@0.20 | Product |
| ----------------- | ---------: | -------: | ----------: | -----: | ------: | ------: |
| plumbing          |          0 |        0 |           0 | 0.2054 |  0.0365 |  0.0225 |
| Pass A            |  3,468,542 |     1800 |        1800 | 0.6961 |  0.0958 |  0.0881 |
| Pass B            |  4,022,546 |     1184 |        1184 | 0.4234 |  0.0846 |  0.0706 |
| Pass C            |  3,382,824 |     1715 |        1715 | 0.6453 |  0.0806 |  0.0705 |
| majority          | 12,056,166 |      884 |         884 | 0.5451 |  0.0612 |  0.0537 |
| adjudication-only | 12,056,166 |      775 |         775 | 0.5100 |  0.0417 |  0.0342 |
| official θ5       |  2,521,972 |        0 |           0 | 0.2054 |  0.0365 |  0.0225 |
| official θ10      |  5,043,249 |      109 |         109 | 0.2436 |  0.0351 |  0.0234 |
| official θ25      | 12,056,166 |     1659 |        1659 | 0.6692 |  0.0733 |  0.0639 |
| DocETL            | 50,440,043 |          |             | 0.7892 |  0.1294 |  0.1235 |

θ5 equals plumbing because only Pass A had started, so every cell is an abstention under the two-vote rule. θ10 materializes only the 109 cells where Pass A and the first 1091 Pass B decisions already agreed.

## Official θ25 per-query products

| Query | Plumbing | Official | Delta |
| --- | ---: | ---: | ---: |
| `legal_multiagg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q9` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q7` | 0.0000 | 0.0000 | +0.0000 |
| `legal_multiagg20:q11` | 0.0952 | 0.1111 | +0.0159 |
| `legal_multiagg20:q18` | 0.0052 | 0.0296 | +0.0244 |
| `legal_agg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_groupby20:q14` | 0.0588 | 0.2256 | +0.1667 |
| `legal_agg20:q11` | 0.0000 | 0.2500 | +0.2500 |
| `legal_multiagg20:q9` | 0.0000 | 0.0058 | +0.0058 |
| `legal_agg20:q13` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q17` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q8` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q11` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q15` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q3` | 0.2000 | 0.4000 | +0.2000 |
| `legal_agg20:q14` | 0.0000 | 0.0000 | +0.0000 |

## Selector accuracy (post-freeze)

- Exact candidate accuracy: **0.1263** (376 / 2978)
- Workload-observational accuracy: **0.2555**
- Accuracy conditional on gold candidate presence: **0.3605**

| Split | n | Exact |
| --- | ---: | ---: |
| Pass A | 2978 | 400 |
| Pass B | 2978 | 130 |
| Pass C | 2978 | 361 |
| Majority consensus class | 1882 | 232 |
| Three-way class | 1062 | 144 |
| surface writes | 469 | 44 |
| normalized writes | 364 | 61 |
| workload_label writes | 826 | 271 |
| hearing_year | 280 | 117 |
| legal_basis_num | 538 | 108 |
| defendant_current_status | 509 | 83 |
| plaintiff_current_status | 528 | 28 |
| first_judge | 277 | 17 |
| case_number | 485 | 12 |
| case_type | 153 | 11 |
| verdict | 208 | 0 |

Error kinds on official writes: wrong-candidate 1101, wrong-period 174, wrong-unit 8, wrong-component 0, wrong-entity 0.

## Diagnostic 0.1886 comparison (post-freeze only)

- Diagnostic writes: 1297
- Official writes: 1659
- Independently recovered diagnostic-winning IDs: **196**
- Assignment distance (symmetric difference plus ID mismatches): **1922**
- Adjudication vs majority: **improved** (0.0537 → 0.0639), still far below 0.1235

Pass A was the strongest single selector (0.0881) and still missed DocETL. Majority collapsed toward `KEEP_PLUMBING`. Adjudication recovered some cells without harming the majority product.

## Freeze hashes

- Query manifest `340998fcb7072a354604776cb28a7214169b8359a013b3418728ca60a23f9945`
- Inventory `42ef0a8c8247d78a96387898810eef929205d5c78a87d72abed8cf90658cb815`
- Cards `f5939fe96a324e58e56421d6df40a4a51dceb3bbd544194e7fe5aa3ce270527d`
- Policy `a6f2d888f8751eeca4f8960c97e6bfd4d617e1ba12552f1c6ba88cd23c2edb6d`
- Permutations `23272e61b2bd800c36e5fe444d2a093d3b5a39c9b0ea32b7b71b30dd83b6c3b8`
- Prompts `a58bb41e6ed5dc9ca4c879b2ec3b923a608af820cbc0ebe21d6c8bbfa8c83657`
- Schedule `9f9b7a7257c8d1840f34e92c4b7103f4ee6f9d1d488b21d8334464784d8eb235`
- Journal `173af733faee436979f042f67361a7d1ee7aded633b96d2336c9fe7dc12d09f1`
- Ledger `dafc53b680ccc39ab93a47c798302c99932b6a6d23972c39edc323fa7af670ea`

deterministic candidates are sufficient but Qwen selection remains inadequate
