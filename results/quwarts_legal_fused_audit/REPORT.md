# Legal fused-map audit

Decision: `Legal fused result invalid`

Phase B was not started. No new Legal model calls were issued.

Final decision: `audit invalidates the Legal win`

## What the rebuild matched

Official bags were rebuilt from the call journal and a clean plumbing copy. Frozen result databases were not the reconstruction source.

| Check | Result |
| --- | --- |
| θ25, θ50, θ75 `fusion_same_attribute` bags | Byte-identical to the frozen bags |
| θ25 journal | Byte prefix of θ50 |
| θ50 and θ75 journals | Byte-identical |
| All 16 queries at θ50 | Present |
| Unfinished θ25 queries | Plumbing-identical bags for `legal_filter20:q15`, `legal_filter20:q7`, `legal_multiagg20:q11`, `legal_multiagg20:q18`, `legal_multiagg20:q4`, `legal_multiagg20:q9` |
| Entity identity | Matches plumbing |
| Pair namespace mismatches | 0 of 4,096 paired calls |
| Missing subresult erasing its partner | 0; 375 partners were kept |
| Same-attribute violations | 0 |

Recomputed products:

| Arm | Product |
| --- | --- |
| Plumbing | 0.022455905439098717 |
| WCCI | 0.09594618648894966 |
| `fusion_direct` | 0.13543970219666815 |
| `fusion_same_attribute` | 0.14382694759870493 |
| Legal DocETL | 0.12350932750098194 |

Plumbing and WCCI were rescored from their databases. Both fusion products were rescored from the rebuilt databases. The DocETL figure is `mean_query_score["0.2"]` in the frozen Legal evaluation file.

## Repair classes

9,120 subresults = 1,880 + 6,351 + 889.

| Class | Count |
| --- | ---: |
| `valid_original` | 1,880 |
| `deterministic_schema_repair` | 0 |
| `model_format_repair` | 6,351 |
| `type_coercion` | 0 |
| `sentinel_normalization` | 0 |
| `missing_field_fill` | 0 |
| `rejected` | 0 |
| `terminal_fallback` | 889 |

`valid_original` is a first validation pass that the runner accepted. The stored fields are already normalized, and the raw model text was not kept, so a case-fold or integer coercion inside that pass cannot be separated from an untouched value.

`model_format_repair` is a second model call. The runner marks the subresult repaired only after that call validates. There is no separate deterministic schema-repair path.

Representative stored records:

- `valid_original`: document `1.txt`, query `legal_agg20:q11`, field `plaintiff_current_status` = null.
- `model_format_repair`: document `1.txt`, query `legal_agg20:q14`, fields `first_judge` = null and `legal_basis_num` = null. The task recorded a repair-token charge. The original malformed text is absent.
- `terminal_fallback`: document `176.txt`, query `legal_agg20:q14`, error `wrong type`, fields null. Plumbing was left in place for that query and document.

The 87 malformed outputs and 802 wrong-type outputs are the 889 terminal fallbacks. Successful repairs clear the stored error, so those 889 failures are disjoint from the 6,351 repaired subresults. The pre-repair error class of the 6,351 is not recoverable.

## Why the repair audit fails

Every stored repair can be checked for query identity, entity identity, and later same-attribute sharing. It cannot be checked against the raw subresult. The journal stores the validated field object, the status, and a combined token count. It does not store the first model string or the repair-model string.

These required proofs are therefore unavailable for the 6,351 repairs:

- The repair uses only the same query’s raw subresult.
- The repair does not invent a semantic value.
- The repair does not change one non-sentinel value into another.
- A wrong-type value is accepted only through a frozen deterministic conversion.

Repair-call tokens are in the ledger. That part holds. The missing raw text is the material failure.

## Same-attribute shares

273 shared cells. Every share had one donor, the same entity, the same base attribute, the same physical type, a non-sentinel source, and an absent target.

| Attribute | Cells |
| --- | ---: |
| `legal_basis_num` | 106 |
| `case_number` | 68 |
| `verdict` | 59 |
| `case_type` | 40 |

| Route | Cells |
| --- | ---: |
| `legal_multiagg20:q11` → `legal_multiagg20:q4` | 154 |
| `legal_multiagg20:q4` → `legal_multiagg20:q11` | 44 |
| `legal_filter20:q11` → `legal_groupby20:q14` | 29 |
| `legal_filter20:q15` → `legal_filter20:q7` | 15 |
| `legal_filter20:q7` → `legal_filter20:q15` | 15 |
| `legal_groupby20:q14` → `legal_filter20:q11` | 11 |
| `legal_multiagg20:q18` → `legal_multiagg20:q9` | 5 |

Official bags that differ from `fusion_direct`: `legal_filter20:q15`, `legal_filter20:q7`, `legal_multiagg20:q11`, `legal_multiagg20:q18`, `legal_multiagg20:q4`, `legal_multiagg20:q9`. The 40 shares between `legal_filter20:q11` and `legal_groupby20:q14` do not change those official bags.

## Cost

| Bucket | Tokens |
| --- | ---: |
| Primary calls, prompt + completion combined | 17,013,058 |
| Repair calls, prompt + completion combined | 1,398,948 |
| Failed HTTP calls | 0 |
| Terminal fallbacks | 889 subresults |
| Ledger total | 18,412,006 |

Prompt tokens and completion tokens were not stored separately. `make_caller` returns one sum.

The plan reserved 18,227,575 from the local tokenizer: each task reserved `count_tokens(prompt) + 280`, plus a repair pool of `180 + 280` per task. The API counted 184,431 more tokens than that local estimate, about 1.0%. The ledger total 18,412,006 stays under θ50 at 25,220,022. No task is marked `budget_held`.

## Inputs opened before freeze

Opened while building the plan and the databases:

- `results/docetl_legal_case80/query_manifest.json`
- `Query/Legal/Legal_attributes.json`
- `source_data/Legal/legal_case/*.txt`
- `results/quwarts_legal_plumbing/artifacts/databases/legal_plumbing.db`
- DocETL `strict_render` and `validate_output_types` as code
- `compile_query_schema` as code
- The Qwen tokenizer

Gold (`Data/Legal/Legal.csv`) is opened only inside scoring, after the databases exist and before `frozen.json` is written. It is not written into the fused databases. DocETL map rows, cached completions, Stage A values, historical query tables, reachability assignments, and WCCI values are named only in the open-guard block list. They are not read into the fused databases.

## Phase B and Phase C

The reusable policy was not hashed. Med and Finan were not run.

There is no three-corpus fused-map table. The operator-portfolio macro is not claimed, because the Legal arm in that portfolio is the audited `fusion_same_attribute` result and the audit failed.
