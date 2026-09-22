# Legal workload-observable sidecars

Qwen cannot resolve enough workload observables under theta25

## Observables

Raw AST occurrences 60. Canonical observables 24. Reuse ratio 0.6000. Joins 0.

| kind | role | attribute | occurrences | queries |
| --- | --- | --- | ---: | ---: |
| group | case_branch | case_number | 1 | 1 |
| group | case_branch | case_number | 1 | 1 |
| group | case_branch | case_type | 4 | 4 |
| group | case_branch | defendant_current_status | 2 | 2 |
| group | case_branch | legal_basis_num | 1 | 1 |
| group | case_branch | plaintiff_current_status | 3 | 3 |
| group | case_branch | verdict | 3 | 3 |
| group | group_key | first_judge | 6 | 3 |
| group | group_key | hearing_year | 2 | 1 |
| numeric | numeric_avg | case_number | 5 | 5 |
| numeric | numeric_avg | legal_basis_num | 6 | 6 |
| numeric | numeric_max | case_number | 1 | 1 |
| predicate | aggregate_indicator | verdict | 2 | 2 |
| predicate | filter | case_type | 1 | 1 |
| predicate | filter | defendant_current_status | 1 | 1 |
| predicate | filter | defendant_current_status | 1 | 1 |
| predicate | filter | hearing_year | 1 | 1 |
| predicate | filter | hearing_year | 1 | 1 |
| predicate | filter | plaintiff_current_status | 1 | 1 |
| predicate | filter | verdict | 1 | 1 |
| presence | is_not_null | case_number | 8 | 8 |
| presence | is_not_null | first_judge | 3 | 3 |
| presence | nonempty | defendant_current_status | 2 | 2 |
| presence | nonempty | plaintiff_current_status | 3 | 3 |

## Evidence and plans

The frozen sample stored 32 evidence packets, all `whole_document`. Full acquisition reached 180 entities and 2,878 entity-bundle calls. Every reached document fit the whole-document budget, because the schedule served shorter documents first. The remaining 390 longer documents stayed unresolved. No retrieval-only absence decision was accepted.

| class | selected | blinded | direct | decompose | glean |
| --- | --- | --- | --- | --- | --- |
| group | decompose | decompose | 37 (4/7) | 49 (5/6) | 0 (0/0) |
| numeric | direct | absolute | 56 (6/10) | 52 (6/14) | 0 (0/0) |
| predicate | decompose | decompose | 45 (5/10) | 61 (7/16) | 0 (0/0) |
| presence | direct | absolute | 17 (2/5) | 7 (1/4) | 0 (0/0) |

## Decisions

Accepted writes 965. Source-supported commitments 965 / 2827 = 0.3414.
Accepted by kind: {'numeric': 139, 'group': 406, 'predicate': 200, 'presence': 220}. Unresolved rows by kind: {'presence': 319, 'group': 973, 'predicate': 1060, 'numeric': 281}.
Presence writes 220, of which case_number 75. Numeric writes 139, of which case_number 66. Group writes 406.
Fallback cells: every unresolved observable stays on the original SQL expression. Changed queries: legal_multiagg20:q4, legal_filter20:q7, legal_multiagg20:q11, legal_multiagg20:q18, legal_agg20:q4, legal_groupby20:q14, legal_agg20:q11, legal_multiagg20:q9, legal_agg20:q17, legal_filter20:q11, legal_filter20:q15, legal_agg20:q3, legal_agg20:q14.

## Tokens

Spent 12587883 / 12610011.

| role | tokens |
| --- | ---: |
| acquire | 11800048 |
| sample | 787835 |

| plan or purpose | tokens |
| --- | ---: |
| decompose | 10106602 |
| direct | 2153111 |
| glean | 319438 |
| sample_judge | 8732 |

## Scores

| arm | tokens | F2 | F1@0.20 | product |
| --- | ---: | ---: | ---: | ---: |
| plumbing | 0 | 0.2054 | 0.0365 | 0.0225 |
| observable sidecars | 12587883 | 0.3266 | 0.0420 | 0.0192 |
| DocETL | 50440043 | 0.7892 | 0.1294 | 0.1235 |

| query | plumbing product | sidecar product | delta |
| --- | ---: | ---: | ---: |
| legal_multiagg20:q4 | 0.0000 | 0.0000 | 0.0000 |
| legal_filter20:q9 | 0.0000 | 0.0000 | 0.0000 |
| legal_filter20:q7 | 0.0000 | 0.0000 | 0.0000 |
| legal_multiagg20:q11 | 0.0952 | 0.0000 | -0.0952 |
| legal_multiagg20:q18 | 0.0052 | 0.0052 | 0.0000 |
| legal_agg20:q4 | 0.0000 | 0.0000 | 0.0000 |
| legal_groupby20:q14 | 0.0588 | 0.0588 | 0.0000 |
| legal_agg20:q11 | 0.0000 | 0.1852 | 0.1852 |
| legal_multiagg20:q9 | 0.0000 | 0.0000 | 0.0000 |
| legal_agg20:q13 | 0.0000 | 0.0000 | 0.0000 |
| legal_agg20:q17 | 0.0000 | 0.0000 | 0.0000 |
| legal_filter20:q8 | 0.0000 | 0.0000 | 0.0000 |
| legal_filter20:q11 | 0.0000 | 0.0000 | 0.0000 |
| legal_filter20:q15 | 0.0000 | 0.0000 | 0.0000 |
| legal_agg20:q3 | 0.2000 | 0.0572 | -0.1428 |
| legal_agg20:q14 | 0.0000 | 0.0000 | 0.0000 |

## Role separation on the bags

Plumbing row counts versus sidecar counts: `legal_multiagg20:q11` 2 to 1, `legal_multiagg20:q18` stayed 1, `legal_agg20:q3` 5 to 18, `legal_agg20:q4` and `legal_agg20:q14` 145 to 101, `legal_multiagg20:q4` 55 to 22, `legal_agg20:q11` 1 to 2.

Presence and numeric sidecars for `case_number` are separate: 75 presence writes and 66 numeric writes. The role fixtures passed, so a presence write cannot supply `AVG(case_number)` and a numeric write cannot satisfy `IS NOT NULL`. `legal_multiagg20:q11` still fell from 0.0952 to 0. The bag shrank from 2 rows to 1, which is the opposite of the earlier count inflation, and the remaining row did not match. `legal_multiagg20:q18` stayed at 0.0052 rather than falling to 0.

Group labels did move grouping without being filter predicates: `hearing_year` received 70 group-key writes and `legal_agg20:q3` grew from 5 rows to 18, cutting that query's product from 0.2000 to 0.0572. `first_judge` received 83 group-key writes and the judge bags shrank from 145 rows to 101. One grouping query improved: `legal_agg20:q11` rose from 0 to 0.1852.

Numeric writes were accepted only when one integer occupied the cited span and a year-like value was rejected for attributes whose description is not a year. Those writes did not recover the `q11` average. F2 rose from 0.2054 to 0.3266 and cell F1@0.20 rose from 0.0365 to 0.0420, but the mean of per-query products fell because the `q11` and `q3` losses outweigh the one gain.

965 decisions were resolved. Every other observable stayed on the original SQL expression.

## Invariants

Empty-sidecar bag match was required before model calls. Role fixtures: {'empty_count_zero': True, 'numeric_does_not_satisfy_presence': True, 'presence_does_not_change_avg': True, 'rewrite_unused': True, 'unresolved_matches_empty': True}.
Base hash ffdd6625ccab49814a6b6aee4fdf8025553327918ff94fd8102d620c21d58da4. Identity hash d2bf32ccd77ca0ed5614307195ae8a592e13060508cf4c8afabf80da6262f71f. Bag hash 160a3c93696b843142bf4152476630f7e8ddfb71e5d217769c93d2fc92b252ee. Plumbing bag hash 8852a9c46bfcd48cf50b3f380da26fe9137642f2004bfe0df13a6bcb339d2e36.
Rebuild base match True. Rebuild identity match True. Rebuild bag match True. Edge rows 0.
A presence sidecar does not supply an AVG input. A numeric sidecar does not satisfy IS NOT NULL. Group labels replace CASE or group-key expressions only. Unresolved decisions use the original expression.

case_number presence and case_number numeric are different observables. COUNT support can change only through the presence atom. AVG changes only through the numeric atom, and only for rows the presence atom already admits.

## Hashes

```json
{
  "observables_hash": "16ba1ead1cc969828d409a5fdeb475614000739553d9a1b4b156e68e31bdd4bf",
  "prompts_hash": "4e716de85dbe912101bb031593ac1b0cbf465a473ce42bc36d2b261f8d2ea287",
  "sample_hash": "28a8de05ad9d54790eb0d8ac2c8c5d317c2091757d9aa6165ff97ba74b77ff54",
  "plans_hash": "4bbcdfd4bd29270d6f22beed2cd2976d19ea9029195f21829f0b54ad0d5fa62b",
  "schedule_hash": "02798e7b899c60aafc81800d1f16214628e50a587562970473c33a492d9e7d1f",
  "base_hash": "ffdd6625ccab49814a6b6aee4fdf8025553327918ff94fd8102d620c21d58da4",
  "identity_hash": "d2bf32ccd77ca0ed5614307195ae8a592e13060508cf4c8afabf80da6262f71f",
  "bag_hash": "160a3c93696b843142bf4152476630f7e8ddfb71e5d217769c93d2fc92b252ee",
  "plumbing_bag_hash": "8852a9c46bfcd48cf50b3f380da26fe9137642f2004bfe0df13a6bcb339d2e36",
  "db_hash": "ba34dffc98fd5c9fb04bf1e0bc8908856dfdb66a15322d2d811865cd4b85ce84",
  "ledger_fingerprint": "42db177a42d1d39ab96a08fdfa6bc85dc87b938dc832d8065f8f772d91892096",
  "gold_loaded": true,
  "rebuild_bag_match": true
}
```

Qwen cannot resolve enough workload observables under theta25
