# Legal checked-ranker label repair

Gold was loaded only after `generation_frozen.json`. No new model calls were made. Frozen checked-extraction artifacts were not modified.

## Labels

Training groups 60. Validation groups 32. Repaired positive rows 184 and negative rows 1014. Value-identical multi-positive groups 52. All-positive groups 0.

Query-result equivalence on the training cells had marked 525 rows positive and 24 groups all-positive. After value-identity repair those training figures are 125 positives and 0 all-positive groups.

Extracted KEEP labels: 2, both in validation. Training DO_NOT_WRITE count: 0. A weighted two-class gate is undefined on that split. The one-class SVM preserved both validation KEEP cells and was selected over isolation forest.

## Validation

Selected policy `ranker_only`. Candidate accuracy 8/32. Committed precision 8/11. UNCERTAIN writes 12/152. KEEP preservation 2/2.

Train-on-train writeability recall 51/60. Top-1 value class 38/60. Positive-set recall 73/125.

Same-denominator baselines: always abstain 0/32, highest-priority channel 19/32, source-supported channel 19/32, repaired ranker 8/32.

Full-corpus writes 219. By attribute: {"hearing_year": 124, "case_type": 32, "defendant_current_status": 59, "plaintiff_current_status": 4}. By channel: {"workload_label": 37, "surface": 181, "normalized": 1}.

## Scores

| Arm | Causal tokens | Writes | F2 | F1@0.20 | Product |
| --- | ---: | ---: | ---: | ---: | ---: |
| plumbing | 0 | 0 | 0.2054 | 0.0365 | 0.0225 |
| previous checked ranker | 3626478 | 136 | 0.2054 | 0.0490 | 0.0350 |
| label repair | 3626478 | 219 | 0.2402 | 0.0490 | 0.0350 |
| DocETL | 50440043 |  | 0.7892 | 0.1294 | 0.1235 |

## Per-query versus plumbing

| Query | Plumbing | Repair | Delta |
| --- | ---: | ---: | ---: |
| `legal_multiagg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q9` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q7` | 0.0000 | 0.0000 | +0.0000 |
| `legal_multiagg20:q11` | 0.0952 | 0.0952 | +0.0000 |
| `legal_multiagg20:q18` | 0.0052 | 0.0052 | +0.0000 |
| `legal_agg20:q4` | 0.0000 | 0.0000 | +0.0000 |
| `legal_groupby20:q14` | 0.0588 | 0.0588 | +0.0000 |
| `legal_agg20:q11` | 0.0000 | 0.0000 | +0.0000 |
| `legal_multiagg20:q9` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q13` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q17` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q8` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q11` | 0.0000 | 0.0000 | +0.0000 |
| `legal_filter20:q15` | 0.0000 | 0.0000 | +0.0000 |
| `legal_agg20:q3` | 0.2000 | 0.4000 | +0.2000 |
| `legal_agg20:q14` | 0.0000 | 0.0000 | +0.0000 |

## Hashes

```json
{
  "labels": "085edbda66f81feb34a567cb43d4b567a55c25304dcaef6098de699a54183e25",
  "policy_lattice": "95f175a814b1532536ae3ababfa9f67f43aa9389ce0619406b921206bf294bab",
  "validation": "575f5535d2e6ca736edd1c9a7eddd1b050adf18c1f88b8fa9c9bdfa2ad5c7a3c",
  "selected_policy": "d6bc6fe855f6c3f640fd53db7a311d6bb4fbf1b7c92f5abccc427c5438d909c3",
  "models": "4123e7da434c37679e9815677fe3c5140d1e5a4661c71687d2903e6afc964c74",
  "assignment": "a421b08c64668b2ab3e5b81f53104cfcb3ce6dee43dfd905d5e0fbaa31a7253b",
  "official_db": "9e6e9430191e822efccf1eace0236b15eae6e4a477779da669f00b492bdd782c",
  "official_bags": "6fc37b925ddb44ccc839d2d85951ecd201895be3c71d1bfac179f1e0b35a1384",
  "configuration": "95f175a814b1532536ae3ababfa9f67f43aa9389ce0619406b921206bf294bab",
  "ledger": "b76e05007045f3372b02449646019d82f3be0061563828c3f850bb62161100cd",
  "causal_spent": 3626478,
  "new_model_spend": 0,
  "rebuild_match": true,
  "gold_loaded": true,
  "writes": 219
}
```

repaired selector does not generalize
