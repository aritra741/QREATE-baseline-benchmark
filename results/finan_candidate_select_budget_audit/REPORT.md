# Finan candidate-select θ25 budget audit

**Decision: `even perfect scheduling and compression cannot meet the 25% target`**

Zero-Qwen audit of the frozen schema-grounded candidate-selection arm. No compressed or microbatched model arm was launched.

## Success criterion

Finan product > 0.084, tokens ≤ 345,457, model = Qwen 2.5 7B.
θ100 product 0.1221 is an opportunity result, not task completion.
θ25 product 0.0296 is the official result against this target.

## 1. Frozen-arm reconcile

- Calls: 1174
- Attempted cells: 1174
- Accepted cells: 517
- θ25 spend: 344601
- θ25 product: 0.0296
- θ100 spend: 1303552
- θ100 product: 0.1221
- θ25 journal rows 333 vs reserved prefix 314 (actual charges undershot reservation, so the snapshot kept 333 calls).
- Journal, overlay, bags, and database hashes matched the frozen arm. Plumbing was not modified.

## 2. Token-cost anatomy

| Component | mean | median | p90 | total |
| --- | ---: | ---: | ---: | ---: |
| system_prompt | 122.0 | 122.0 | 122.0 | 143228 |
| repeated_instructions | 70.8 | 72.0 | 76.0 | 83167 |
| output_schema_tool_definition | 109.4 | 109.0 | 111.0 | 128434 |
| authoritative_attribute_description | 29.5 | 33.0 | 40.0 | 34652 |
| document_entity_metadata | 118.1 | 113.0 | 139.0 | 138600 |
| candidate_ids | 23.0 | 23.0 | 23.0 | 26948 |
| candidate_raw_values | 73.8 | 36.0 | 180.0 | 86680 |
| row_labels | 93.2 | 75.0 | 175.0 | 109395 |
| column_headers | 113.3 | 93.0 | 226.0 | 133036 |
| table_titles | 74.4 | 66.0 | 123.0 | 87308 |
| period_unit_currency_metadata | 21.9 | 21.0 | 41.0 | 25764 |
| neighboring_evidence_text | 0.0 | 0.0 | 0.0 | 0 |
| completion | 36.7 | 34.0 | 46.0 | 43055 |
| fixed_overhead | 449.8 | 443.0 | 478.0 | 528081 |
| candidate_dependent_payload | 399.6 | 373.0 | 577.0 | 469131 |
| tokenizer_prompt | 983.7 | 960.0 | 1171.0 | 1154837 |
| api_prompt | 1073.7 | 1050.0 | 1261.0 | 1260497 |

- Tokens per attempted cell: 1110.4
- Tokens per accepted cell: 2521.4
- Tokens per SQL-visible fill: 2797.3
- Fixed overhead per call: mean 449.8
- Candidate-dependent payload per call: mean 399.6
- Proportion removable through shared batching: 0.427
- Proportion removable through deterministic card compression: 0.095
- Neighboring evidence text is absent from every frozen inventory card.

## 3. Compact candidate cards

- Cards: 9414; lossless 9414; residual 0
- Original card tokens total 632258; compact 522608; removed fraction 0.173
- Representation is corpus-agnostic: ID, raw value, row, header, title, period, unit, currency, source offset.
- Removed only after a deterministic proof: default placeholder ≡ omission, equal fields, empty neighbors, `end = start + len(raw_span)`, ranking metadata.
- Field-level report: `card_preservation.jsonl`.

## 4. Microbatch request formats

Prompts were generated, not executed. Batches stay inside one entity/document. Task IDs are unique; candidate IDs are namespaced as `task_id.C#`. The shared schema has no value field.

| Format | calls | prompt tokens | reserved tokens | fits θ25 |
| --- | ---: | ---: | ---: | ---: |
| original one-cell | 1174 | 1154837 | 1380245 | False |
| compact batch-1 | 1174 | 1044825 | 1270233 | False |
| compact batch-2 | 605 | 1112338 | 1228498 | False |
| compact batch-3 | 428 | 1027622 | 1109798 | False |
| compact batch-4 | 333 | 982091 | 1046027 | False |
| compact batch-6 | 241 | 937993 | 988717 | False |
| compact batch-8 | 189 | 912815 | 959704 | False |

- Reserved cost uses Qwen tokenizer prompt tokens plus `max(192, k × mean frozen completion 36.67)`.
- Minimum batch size that places all 1,174 frozen tasks within 345,457: `None`.
- Decision invariance is not assumed from field preservation.

## 5–6. Workload graph and θ25 schedules

- CP-SAT available: False. Solver used: `deterministic_witness_package_greedy`.
- Graph hash: `8accd53c4513accac460b577d1b1dd566c16e29f03e9c97f9c81bfeef74d3c0a`
- Feasible witnesses: 1590; already complete from plumbing: 75; empty unavailable cells: 3

| Schedule | tasks | calls | reserved | witnesses unlocked | queries | objective |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| original_one_cell | 309 | 309 | 345053 | 511 | 16 | 5.8969 |
| compact_one_cell | 343 | 343 | 345393 | 547 | 16 | 6.2585 |
| compact_batch_2 | 353 | 177 | 345241 | 553 | 16 | 6.3195 |
| compact_batch_3 | 392 | 137 | 345206 | 600 | 16 | 6.7926 |
| compact_batch_4 | 413 | 114 | 345421 | 629 | 16 | 7.0852 |
| compact_batch_6 | 439 | 85 | 345434 | 658 | 16 | 7.3771 |
| compact_batch_8 | 447 | 74 | 345112 | 675 | 16 | 7.5479 |

Schedules and projections were hashed before gold was loaded.

## 7. Official zero-token scheduling replay

- Actual spend: 325311 / 345457
- Tasks replayed: 309
- Official 16-query product: **0.0714**
- Structure F2 0.3922; cell F1@0.20 0.1137
- Bag hash: `8bd3cce24a274ed18d1557b318ba0e796b96d839b346b062a76d18158db2a9c1`
- This is a valid zero-call counterfactual: frozen prompts and outputs were reused; only the predeclared schedule changed.

## 8. Decision-invariance projections

These are **not official model results**. They ask what the score would be if compact or batched presentation preserved each frozen per-cell decision.

| Format | calls | tokens | cells | witnesses | queries | projected product |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compact_one_cell | 343 | 345393 | 343 | 547 | 16 | 0.0714 |
| compact_batch_2 | 177 | 345241 | 353 | 553 | 16 | 0.0734 |
| compact_batch_3 | 137 | 345206 | 392 | 600 | 16 | 0.0714 |
| compact_batch_4 | 114 | 345421 | 413 | 629 | 16 | 0.0734 |
| compact_batch_6 | 85 | 345434 | 439 | 658 | 16 | 0.0721 |
| compact_batch_8 | 74 | 345112 | 447 | 675 | 16 | 0.0744 |

- Full θ100 coverage inside θ25? compact-1 `False`; first fitting batch size `None`.

## 9. Post-freeze diagnostic ceilings

These are diagnostics, not official model results.

- Scheduling oracle, gold-match cells only: 0.0337 on 76 tasks (reserved 84,904). This is not a ceiling because it is below the official replay.
- Scheduling oracle, gold-aware query knapsack of frozen decisions: 0.0546 on 265 tasks (reserved 300,303).
- Scheduling oracle, best attained frozen-decision subset at θ25: **0.0714** (the official gold-free replay). No gold-aware subset we constructed beat that.
- Candidate-label oracle on the original one-cell gold-free schedule: 0.0651 (35 gold-present fills).
- Candidate-label oracle on the compact batch-8 gold-free schedule: **0.0750** (62 gold-present fills). This is the candidate-label ceiling.
- Minimum compact/batched reserved tokens to carry all 1,174 frozen θ100 decisions: batch-1 1,270,233; batch-2 1,228,498; batch-3 1,109,798; batch-4 1,046,027; batch-6 988,717; batch-8 959,704. All exceed 345,457.

## 10. Required conclusions

- Scheduling alone beats 0.084: **False** (official replay 0.0714).
- Compact single-cell prompts can fit enough coverage: **False** (all 1,174 fit=False; invariance product 0.0714).
- Minimum batch size for all 1,174 tasks within 345,457: **None**.
- Information removed by compression: default placeholders, proven-duplicate layout fields, empty neighbors, recoverable `end`, ranking metadata, and repeated card-field labels. Residual neighbor text never appeared.
- Gold-free scheduler vs score-lift queries: captured ['finan_agg20:q14', 'finan_filter20:q8', 'finan_filter20:q9', 'finan_groupby20:q14', 'finan_multiagg20:q11', 'finan_multiagg20:q18', 'finan_multiagg20:q4'] of ['finan_agg20:q14', 'finan_filter20:q8', 'finan_filter20:q9', 'finan_groupby20:q14', 'finan_multiagg20:q11', 'finan_multiagg20:q18', 'finan_multiagg20:q4'] (fraction 1.0).
- θ25 scheduling ceiling: 0.0714 (best frozen-decision subset; gold-aware alternatives 0.0337 and 0.0546 did not exceed it)
- Candidate-label ceiling: 0.0750 (compact batch-8 gold-free schedule with the correct candidate whenever it is present)
- Graph hash `8accd53c4513accac460b577d1b1dd566c16e29f03e9c97f9c81bfeef74d3c0a`; replay bag `8bd3cce24a274ed18d1557b318ba0e796b96d839b346b062a76d18158db2a9c1`; schedule hashes {'original_one_cell': 'dddf773e453b38ea13ee0da67f64e69eb841f3207635ba38ab50b8cf03af0385', 'compact_one_cell': 'd2d066a53ade983636e40660604d6361741f6418e6ddb68663fadb1c1310e846', 'compact_batch_2': 'c24478e012a158cbd5f3d4d837b0e0cf2efa8b63ed8115b7bdde8556e1e47a69', 'compact_batch_3': 'a8eae961c4005a09dce1098ca2aa10fe6213f974b12c5bd59d32df35cf33849a', 'compact_batch_4': 'd844b4bdb0d2100f8e9c8061d84228f35cd20c9a2eb0cfff9f239df35e8cc125', 'compact_batch_6': 'c78d582b38b0470403fefcc6333dd39c9066a2bdd04abca1e35e88367713d758', 'compact_batch_8': 'ee65799516dbfc04c1489ae65807780338139e4a2cba77f639eac9605ec6d7e7'}.

**Primary decision:** `even perfect scheduling and compression cannot meet the 25% target`

