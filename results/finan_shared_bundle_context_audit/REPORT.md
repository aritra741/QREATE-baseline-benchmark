# Finan shared-bundle evidence-location audit

Zero-Qwen audit of the frozen shared-bundle arm. No extraction calls. Frozen artifacts were read only.

## Decision

**`selection among present candidates dominates`**

When a recoverable gold form is already in the frozen mid-cut (C0), the arm still accepts the wrong value most of the time (23/57 exact). A C0 availability oracle that copies those gold cells onto plumbing scores **0.0717**, versus the frozen arm **0.0411**. That gap is larger than the extra lift from table-aware retrieval (C1/C2 oracles **0.0767**).

Secondary mechanisms:

- **Evidence location** for numeric table fields. Gold is recoverable in the full source for 76.6% of workload cells, but only 46.0% of frozen-task cells in C0. Revenue C0 coverage is 2/13; total_debt 2/11. Mid-cut drops comma-scaled table numbers (`27,802`, `458,467`).
- **Workload CASE/predicate labels leaked into the prompt.** 19 accepted “other” rows equal a literal from the shared-bundle use block (`EY`, `PwC`, `KPMG`, `No`, `NASDAQ`, `100000000`).
- **Not bundling.** After holding gold-in-C0 fixed, size-1 and size-2 have one accepted cell each. That is not enough to say bundle size reduces quality.
- **Not units.** Zero accepted fills classified as unit/sign conversion.
- **Not missing gold.** One accepted fill has gold unavailable in the source document.

## Reproduction gate

| Check | Result |
| --- | --- |
| Frozen bags reproduce | yes (`beb62d10ee9aee4a915fc3e78598753a3e772ac87fdd5be1c4de39764a3266f8`) |
| Calls / fills | 115 / 79 |
| Product | 0.0410632404875826 → **0.0411** |
| Gold loaded before C0/C1/C2 hash | no |
| Frozen shared / exact / plumbing unmodified | yes |

## Context hashes (pre-gold)

| Object | SHA-256 |
| --- | --- |
| C0 | `294851cf3b5b1bae2daccd2eb355df6e4bf21d98a3e4baf933bb2113f0b22f6f` |
| C1 | `c74574c33ebbc655c3e1cc45759ae5eb266d2e77406e3d07f302dd4d8f42a73b` |
| C2 | `3d1ab1116a5626b6762c173afb5073a0e6e4bc9b2524a138b7b2fec21e679694` |
| All context metadata | `57a86b8aebad9f24b0955631744ea72a08ab3acd5a4dca8a5df24e8cd3346f17` |
| Plumbing | `ad91c2554f32510cb378737009e6479cfcb71299f245c7fe766722057b2b2a3d` |
| Shared frozen.json | `107109f58db066ad77380f9e754282397b477eb52eb49f242b4c66d183e4dfee` |
| Exact-message frozen.json | `2ca732b10253cc8d4fc383bf65935b7360635bc77cfd38672b53ff63532272e4` |

C0 is the exact document body from each frozen request. C1 is BM25 over layout blocks using only attribute tokens, SQL literals, operators, CASE labels, and workload expressions. C2 is half head/tail mid-cut plus half C1, with exact-overlap dedupe.

## Context-token distributions (115 tasks)

| Context | min | mean | max |
| --- | ---: | ---: | ---: |
| C0 | 7738 | 11314.8 | 11664 |
| C1 | 9126 | 11409.8 | 11691 |
| C2 | 11204 | 11527.4 | 11689 |

Pairwise token-set Jaccard: C0∩C1 0.301, C0∩C2 0.498, C1∩C2 0.527.

C1 selected block types: paragraph 5736, table_row 5251, table_header 1502, section_heading 1440, list 640, table_title 162.

## Source and context coverage

Recoverable gold representation, after contexts were frozen. Strings: exact normalized / case-punct / token-or-alias. Numerics: formatting-equivalent forms only (commas, `$`, parentheses, `%`, unit words in the same header/table). Arbitrary numeric proximity was not counted.

| Scope | source | C0 | C1 | C2 |
| --- | ---: | ---: | ---: | ---: |
| All gold workload cells | 0.766 (n=1306) | — | — | — |
| Frozen document–bundle cells | — | 0.460 (n=200) | 0.580 | 0.560 |
| Accepted model outputs | 0.986 (n=72) | 0.792 | 0.861 | 0.847 |
| Missing / unaccepted task cells | 0.758 (n=128) | 0.273 | 0.422 | 0.398 |

C1 recovers gold that mid-cut drops, especially:

| Attribute | source | C0 | C1 | C2 |
| --- | ---: | ---: | ---: | ---: |
| auditor | 0.949 | 0.875 | 0.812 | 0.938 |
| revenue | 0.600 | 0.154 | 0.462 | 0.308 |
| total_debt | 0.580 | 0.182 | 0.273 | 0.182 |
| cash_reserves | 0.636 | 0.133 | 0.200 | 0.200 |
| earnings_per_share | 0.554 | 0.067 | 0.200 | 0.200 |
| net_assets | 0.608 | 0.062 | 0.000 | 0.000 |
| exchange_code | 0.948 | 1.000 | 1.000 | 1.000 |
| major_equity_changes | 0.949 | 1.000 | 1.000 | 1.000 |

SQL-role coverage on frozen tasks: CASE 0.62 C0 / 0.78 C1; aggregate input 0.24 C0 / 0.33 C1. Numeric aggregates are the location problem. Categorical CASE fields are usually already in C0.

The `cash_reserves+net_profit_or_loss+revenue` bundle is the worst location case (C0 0.116, C1 0.302). `auditor+exchange_code+major_equity_changes` is already covered (C0 0.959).

## Error taxonomy (79 accepted fills)

| Category | n |
| --- | ---: |
| correct | 25 |
| other (workload predicate/CASE literal copied) | 19 |
| correct gold present in C0, wrong occurrence selected | 9 |
| gold internally inconsistent or unalignable | 7 |
| correct gold absent from C0, present in full document | 12 |
| total chosen instead of component | 3 |
| wrong reporting period/year | 2 |
| component chosen instead of total | 1 |
| gold unavailable in the full document | 1 |
| unit scaling / sign-percent | 0 |

The 19 `other` rows all have textual evidence that the prediction equals a workload literal from the shared use block, not a document span of the gold value.

### Auditor 0/15, revenue 0/8, total_debt 0/5

These do **not** share one mechanism.

**Auditor.** Gold legal names are in C0 for 14/16 frozen auditor tasks. The model returned CASE family labels from the use block (`EY`, `PwC`, `KPMG`, `Other`, `Deloitte`). Examples: `EY` vs `Ernst & Young LLP`; `Other` vs `Moss Adams LLP`; one miss (`EY` vs `Grant Thornton LLP`). Two golds were mid-cut out (`Deloitte & Touche LLP`, `KPMG AZSA LLC`). One gold cell is empty.

**Revenue.** Five of eight accepted fills have gold in the source as a table-scaled form that C0 dropped (`27,802`, `1,089,752`, `458,467`). Three of those predictions are the predicate literal `100000000`. Two gold cells are empty. One is a year mismatch.

**Total debt.** Same location pattern: `2,289` and `557,678` sit in the source table and not in C0. Two gold cells empty. One wrong occurrence (`10000000` vs `15000000`, both in C0).

## Bundling controls

| Slice | accepted | exact | rate |
| --- | ---: | ---: | ---: |
| bundle size 1 | 1 | 1 | 1.00 |
| bundle size 2 | 3 | 1 | 0.33 |
| bundle size 3 | 75 | 23 | 0.31 |
| gold in C0 | 57 | 23 | 0.40 |
| gold not in C0 | 22 | 2 | 0.09 |
| size 3 and gold in C0 | 55 | 21 | 0.38 |
| size 1 and gold in C0 | 1 | 1 | 1.00 |
| mixed-type bundle | 22 | 6 | 0.27 |
| homogeneous bundle | 57 | 19 | 0.33 |
| whole document | 2 | 2 | 1.00 |
| mid-cut | 77 | 23 | 0.30 |

Gold-context presence moves exact rate from 0.09 to 0.40. Bundle size after that control does not have enough size-1/2 accepts to claim bundling is the cause.

## Overlap with exact-message extraction

Only document `10` appears in both frozen arms. Two overlapping accepted cells:

| | exact-message wrong | exact-message correct |
| --- | ---: | ---: |
| shared-bundle correct | 1 | 1 |
| shared-bundle wrong | 0 | 0 |

Too few cells to compare prompt style. The shared-bundle arm is not losing cells that exact-message already got right on the overlap.

## SQL-visible error counts

Leave-one-cell gold substitution on every incorrect or missing attempted cell, everything else frozen. Ranked by number of individually SQL-visible cells, not summed lift.

| Attribute | SQL-visible incorrect/missing cells |
| --- | ---: |
| remuneration_policy | 17 |
| cash_reserves | 14 |
| earnings_per_share | 12 |
| major_equity_changes | 11 |
| principal_activities | 7 |
| net_profit_or_loss | 7 |
| auditor | 6 |
| the_highest_ownership_stake | 5 |
| revenue | 3 |
| business_segments_num | 3 |
| net_assets | 2 |
| total_debt | 1 |

Single-cell effects: change no bag 87; change only an unscored bag 31; change product 30; change test structure 27. Do not add those product lifts.

## Availability oracles

Gold is copied onto plumbing only when a deterministic recoverable form is in that frozen context. Other cells stay plumbing-null. Sidecar writes: C0 92, C1 116, C2 112.

| System | 16-query product |
| --- | ---: |
| plumbing | 0.0158 |
| frozen shared-bundle | 0.0411 |
| C0 availability oracle | 0.0717 |
| C1 availability oracle | 0.0767 |
| C2 availability oracle | 0.0767 |
| DocETL | 0.084 |

C1 and C2 write more cells than C0 but do not beat DocETL. Perfect selection from the frozen mid-cut already closes most of the shared-bundle gap.

## Invalid / unalignable

- 7 accepted fills have empty or unnormalizable gold (`auditor` on 100; `revenue` on 53 and 16; `total_debt` on 53 and 100; `major_equity_changes` on 100; `business_segments_num` one cell).
- 1 accepted fill has gold absent from the full source (`remuneration_policy`).
- No bag-reproduction or product-gate failure.
- No Qwen call.

Artifacts: `results/finan_shared_bundle_context_audit/`.
