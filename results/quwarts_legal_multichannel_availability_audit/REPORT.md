# Legal multi-channel availability audit

**Decision: `availability remains unresolved because an exact upper bound could not be computed`**

No frozen database, inventory, journal, ledger, prompt, or bag artifact was modified. No model calls were made.

The published 0.0810 / 0.0920 numbers are **forced-fill counterfactuals**, not availability ceilings. They are not maximizations over reachable candidate assignments.

## Central issue

A true availability ceiling cannot fall when the candidate set grows, because it may ignore the extra candidates and keep plumbing. The reported oracles cannot do that.

`oracle_fills` walks inventory order and **obligatorily writes** the first `gold_match`. Plumbing is not retainable once any match exists. `gold_match` accepts exact equality, numeric ±20%, or **bidirectional string substring**. Collision resolution is first-match; later channels never overwrite an earlier match; one candidate is written per cell.

Priority order is inventory concatenation:

```text
surface → normalized → workload_label → composed → semantic
```

Adding surface candidates changes **0.0920 → 0.0810** because **493 cells** receive a different forced write. Surface is concatenated first, so a long span that merely contains a gold digit or label wins.

First divergence: document `10`, attribute `first_judge`.

| | value |
| --- | --- |
| gold | `0` |
| all-expanded write | `Dated: 28 May 2008 Counsel for the Appellant: ...` |
| leave-surface-out write | `2008` |
| mechanism | the surface span substring-matches gold `0` via `2008` |

Divergent forced writes by attribute: `first_judge` 238, `case_number` 102, `defendant_current_status` 54, `plaintiff_current_status` 49, `legal_basis_num` 45, `hearing_year` 5.

Reproduction hashes match the frozen oracle databases byte-for-byte.

## 1. Forced-fill reproductions

Every arm below is a **forced-fill counterfactual**.

| Oracle | Eligible channels | Product | Attempted | Materialized | SQL-visible | Plumbing retainable | Later overwrites earlier |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| surface | surface | 0.0368 | 899 | 899 | 899 | no | no |
| surface + normalized | surface, normalized | 0.0368 | 906 | 906 | 906 | no | no |
| workload labels | workload_label | 0.0425 | 1015 | 1015 | 1015 | no | no |
| semantic | semantic | 0.0225 | 151 | 151 | 151 | no | no |
| composed | composed | 0.0225 | 3 | 3 | 3 | no | no |
| all expanded | all five | 0.0810 | 1485 | 1485 | 1485 | no | no |
| loo surface | all except surface | 0.0920 | 1333 | 1333 | 1333 | no | no |
| loo normalized | all except normalized | 0.0810 | 1482 | 1482 | 1482 | no | no |
| loo workload_label | all except workload_label | 0.0449 | 961 | 961 | 961 | no | no |
| loo semantic | all except semantic | 0.0664 | 1437 | 1437 | 1437 | no | no |
| loo composed | all except composed | 0.0810 | 1485 | 1485 | 1485 | no | no |

These are not availability ceilings.

## 2. Cell-domain construction

Each `(entity_id, attribute)` domain is:

```text
KEEP_PLUMBING
all frozen surface candidates
all frozen normalized candidates
all frozen workload-label candidates
all frozen semantic candidates
all frozen composed candidates
```

Values were deduplicated only after retaining channel, candidate id, and provenance. Two values are observationally equivalent for a query only if they produce identical SQLite one-row results under that query’s comparisons, `LIKE`, `IN`, NULL/empty tests, CASE branches, grouping expressions, counted expressions, and join predicates.

| Recall | Present | N |
| --- | ---: | ---: |
| exact-gold candidate recall | 1112 | 2978 |
| workload-observational recall including KEEP_PLUMBING | 1713 | 2978 |

Exact recall by attribute: `hearing_year` 235/280, `legal_basis_num` 310/538, `defendant_current_status` 274/509, `case_number` 95/485, `plaintiff_current_status` 79/528, `first_judge` 67/277, `case_type` 52/153, **`verdict` 0/208**.

Observational recall is much higher for `verdict` (205/208) and `case_type` (151/153) because CASE `ELSE 'Other'` makes many non-gold strings equivalent to gold values that also fall through to `Other`. That does **not** make them equivalent to gold `Approved`, `Dismissed`, or `Civil Case`.

The old forced-fill “candidate_set_recall” of 1485/2978 used substring `gold_match`. Exact-gold recall after freeze is 1112/2978.

## 3. Monotonicity fixtures

| Fixture | Result |
| --- | --- |
| adding a candidate cannot remove KEEP_PLUMBING | pass |
| KEEP_PLUMBING is always in the domain | pass |
| a larger channel set contains every assignment reachable by a smaller set | pass |
| duplicate candidate IDs cannot change reachable values | pass |
| channel order cannot change the reachable domain | pass |
| query-local assignments are stored per query and do not write a shared sidecar | pass |
| NULL, empty, false, unknown, absent | distinct under `IS NOT NULL`; collapsed by `verdict = 'Approved'` because none equal `Approved` |

First cell where all-channel and leave-surface-out forced-fill diverge: document `10`, `first_judge`, as above.

## 4. Exhaustive 32-subset replay

Five channels, 32 subsets, zero model calls. Two policies per subset:

1. **Forced-fill**: write the first `gold_match` (old oracle).
2. **Optional-write**: independently keep plumbing, or write one exact-gold / observationally equivalent candidate. Never write a candidate merely because it exists.

| Channels | Forced-fill product | Optional-write product | Forced writes | Optional writes | Queries changed |
| --- | ---: | ---: | ---: | ---: | ---: |
| none | 0.0225 | 0.0225 | 0 | 0 | 0 |
| surface | 0.0368 | 0.0359 | 899 | 484 | 2 |
| normalized | 0.0475 | 0.0350 | 555 | 348 | 1 |
| surface,normalized | 0.0368 | 0.0359 | 906 | 530 | 2 |
| workload_label | 0.0425 | 0.0696 | 1015 | 805 | 4 |
| surface,workload_label | 0.0664 | 0.0811 | 1434 | 1034 | 6 |
| normalized,workload_label | 0.0666 | 0.0700 | 1274 | 999 | 5 |
| surface,normalized,workload_label | 0.0664 | 0.0811 | 1437 | 1079 | 6 |
| semantic | 0.0225 | 0.0225 | 151 | 114 | 0 |
| surface,semantic | 0.0449 | 0.0359 | 955 | 554 | 2 |
| normalized,semantic | 0.0475 | 0.0350 | 625 | 418 | 1 |
| surface,normalized,semantic | 0.0449 | 0.0359 | 961 | 594 | 2 |
| workload_label,semantic | 0.0684 | 0.0696 | 1112 | 887 | 6 |
| surface,workload_label,semantic | 0.0810 | 0.0811 | 1482 | 1091 | 8 |
| normalized,workload_label,semantic | 0.0920 | 0.0700 | 1333 | 1055 | 8 |
| surface,normalized,workload_label,semantic | 0.0810 | 0.0811 | 1485 | 1130 | 8 |
| composed | 0.0225 | 0.0225 | 3 | 3 | 0 |
| surface,composed | 0.0368 | 0.0359 | 899 | 487 | 2 |
| normalized,composed | 0.0475 | 0.0350 | 555 | 348 | 1 |
| surface,normalized,composed | 0.0368 | 0.0359 | 906 | 530 | 2 |
| workload_label,composed | 0.0425 | 0.0696 | 1018 | 808 | 4 |
| surface,workload_label,composed | 0.0664 | 0.0811 | 1434 | 1037 | 6 |
| normalized,workload_label,composed | 0.0666 | 0.0700 | 1274 | 999 | 5 |
| surface,normalized,workload_label,composed | 0.0664 | 0.0811 | 1437 | 1079 | 6 |
| semantic,composed | 0.0225 | 0.0225 | 153 | 116 | 0 |
| surface,semantic,composed | 0.0449 | 0.0359 | 955 | 556 | 2 |
| normalized,semantic,composed | 0.0475 | 0.0350 | 625 | 418 | 1 |
| surface,normalized,semantic,composed | 0.0449 | 0.0359 | 961 | 594 | 2 |
| workload_label,semantic,composed | 0.0684 | 0.0696 | 1114 | 889 | 6 |
| surface,workload_label,semantic,composed | 0.0810 | 0.0811 | 1482 | 1093 | 8 |
| normalized,workload_label,semantic,composed | 0.0920 | 0.0700 | 1333 | 1055 | 8 |
| surface,normalized,workload_label,semantic,composed | 0.0810 | 0.0811 | 1485 | 1130 | 8 |

Best forced-fill subset: `{normalized, workload_label, semantic}` at **0.0920** (same as leave-surface-out).
Best optional-write subset in the 32-channel search: `{surface, workload_label}` at **0.0811**.

Isolated `workload_label` is the clearest forced-fill understatement: optional-write 0.0696 vs forced-fill 0.0425. On the all-channel shared database the two policies are almost identical (0.0811 vs 0.0810), because observational writes still collide across queries.

These are diagnostics, not official arms. Optional-write is not monotone in the channel set either, because observational matches are query-shared: a write that helps one query can hurt another. The 32-subset optional-write policy uses one shared database.

## 5. Query-local relaxed availability bound

Each of the 16 queries may choose its own assignment. Choices need not stay consistent across queries. Each cell may keep plumbing or take one frozen candidate. No invented gold values. This relaxation is an upper bound on any real shared materialization.

COUNT-style queries used max-flow / clipped count vectors. AVG/MAX/HAVING queries that could not be solved exactly report a feasible lower bound and a certified optimistic upper. Two earlier 1.0 gold-versus-gold AVG uppers were rejected; those queries now use the best constructed / plumbing / forced product.

| Query | Plumbing | Forced all | Best reachable | Certified upper bound | DocETL | Exact? |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `legal_multiagg20:q4` | 0.0000 | 0.0001 | 0.0000 | 0.3704 | 0.0000 | no |
| `legal_filter20:q9` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no |
| `legal_filter20:q7` | 0.0000 | 0.0000 | 0.0000 | 0.6767 | 0.0000 | no |
| `legal_multiagg20:q11` | 0.0952 | 0.0000 | 0.0000 | 0.0952 | 0.1111 | no |
| `legal_multiagg20:q18` | 0.0052 | 0.0481 | 0.0052 | 0.0481 | 0.1881 | no |
| `legal_agg20:q4` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no |
| `legal_groupby20:q14` | 0.0588 | 0.2256 | 0.0588 | 0.2256 | 0.2500 | no |
| `legal_agg20:q11` | 0.0000 | 0.2256 | 0.4511 | 0.4511 | 1.0000 | no |
| `legal_multiagg20:q9` | 0.0000 | 0.0285 | 0.0000 | 0.0285 | 0.2270 | no |
| `legal_agg20:q13` | 0.0000 | 0.0000 | 0.0000 | 0.1176 | 0.0000 | no |
| `legal_agg20:q17` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no |
| `legal_filter20:q8` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no |
| `legal_filter20:q11` | 0.0000 | 0.2256 | 0.0000 | 0.2256 | 0.0000 | no |
| `legal_filter20:q15` | 0.0000 | 0.1923 | 0.0000 | 0.1923 | 0.0000 | no |
| `legal_agg20:q3` | 0.2000 | 0.3497 | 0.6000 | 0.8000 | 0.2000 | no |
| `legal_agg20:q14` | 0.0000 | 0.0000 | 0.0000 | 0.3704 | 0.0000 | no |

Mean of certified per-query upper bounds (no query had an exact optimum): **0.2251**.

That mean exceeds DocETL 0.1235, but it is **not** an exact query-local optimum. Several COUNT queries cannot reach gold counts because frozen non-NULL plumbing over-fills a group or capacity is short (`q3` feasible 0.60, optimistic 0.80; `q4`/`q8`/`q9` certified 0). AVG/MAX/HAVING queries were not solved by exact DP/IP.

Unsupported features where the result is not exact: joint AVG/MAX/HAVING cell match; non-excludable leftover rows; insufficient capacity or frozen plumbing overfill.

## 6. Attribute/channel cohort search

Eight queried attributes × five channels = 40 optional write groups. Exhaustive 2^40 is infeasible. Beam-equivalent coordinate descent ran from three deterministic starts: plumbing, all-expanded, leave-surface-out; each with a forward pass and a backward pass.

| Start | Starting product | Best from that start |
| ---: | ---: | ---: |
| plumbing | 0.0225 | improved by adding `case_number:surface` then `case_type:workload_label` |
| all-expanded | 0.0811 | **0.0927** after turning **off** `defendant_current_status:workload_label` |
| leave-surface-out | 0.0700 | did not beat 0.0927 |

Best feasible shared-database product: **0.0927** (881 optional writes).

That improvement traces to query bags: `legal_agg20:q17` rose 0 → 0.25 and `legal_agg20:q3` stayed 0.80, while `legal_multiagg20:q18` fell 0.082 → 0.019. This is a **lower bound** on attainable candidate performance, not a ceiling. It is still below DocETL 0.1235.

## 7. Candidate-generation funnel

2,978 NULL cells were inventory-eligible. Every routed attribute includes `semantic`, so all 2,978 were job-eligible. **785** were scheduled; **2,193** were never scheduled because generation spend reached 12,263,034 of the 12,264,554 generation cap. The remaining budget was reserved for the unchanged 345,457-token selector. Job order is generic (occurrence × query count × unresolved / estimated cost).

| Stage | Count |
| --- | ---: |
| eligible | 2978 |
| scheduled | 785 |
| context built | 785 |
| proposal call completed | 785 |
| parsed (not malformed) | 739 |
| malformed | 46 |
| candidates emitted | 1635 |
| evidence attached | every stored semantic/composed candidate |
| normalized candidates stored | 12148 |
| verified supported | 519 |
| verified uncertain | 732 |
| verified unsupported | 384 |
| stored official-selection eligible | official inventory uses `eligible is not False` |
| gold exact match after freeze | 1112 cells |
| gold observational match after freeze | 1713 cells |

Tokens per scheduled proposal cell: min 1,142, p50 5,290, p90 9,075, max 11,658, mean 5,638.
Packed context tokens: min 376, p50 4,001, p90 7,913, max 10,017, mean 4,317.
Candidates emitted per call: mean 2.08, p50 2, max 4.
Prompt/completion splits were **not persisted** in the frozen proposal journal; only ledger `actual` and packed `context_tokens` exist. Verification calls: mean 4,790 tokens, n=1,635.

| Context mode | Calls | Emitted | Mean call tokens | Mean context tokens | Mean emitted |
| --- | ---: | ---: | ---: | ---: | ---: |
| whole_document | 641 | 1298 | 5698 | 4389 | 2.02 |
| retrieved_pack | 144 | 337 | 5371 | 4001 | 2.34 |

Long whole-document contexts received most of the generation budget (641/785 calls) and had a **lower yield** (2.02 vs 2.34 candidates per call).

Scheduled cells were spread almost evenly (~98 per attribute). Exact-gold yield after freeze is still zero for `verdict`.

## 8. Semantic and composed failure

Isolated semantic and composed forced-fill arms both remain at plumbing product **0.0225**.

| Channel | Proposed | Unique non-NULL | supported / uncertain / unsupported | Exact gold | Observational | SQL-visible forced writes | Isolated product |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| semantic | 765 | 167 | 218 verified, 547 uncertain | 121 | 148 | 151 | 0.0225 |
| composed | 11 | 6 | 4 verified, 7 uncertain | 3 | 0 | 3 | 0.0225 |

Semantic writes that fired were substring/forced matches. They moved structure on some queries whose cell F1 stayed zero, so the mean per-query product did not leave plumbing. Composed volume is negligible (11 candidates, 3 writes). Queries that could change in principle include every Legal query for semantic, and only the `first_judge` / `legal_basis_num` aggregates for composed.

Missing exact-gold values after freeze, classified without attribute-specific rules:

| Attribute | Present verbatim, generator missed | Deterministically normalizable | Workload-visible label | Semantically inferable | Compositional | Unavailable | Serialization / ontology |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| case_number | 389 |  |  |  |  |  | 1 |
| legal_basis_num | 228 |  |  |  |  |  |  |
| first_judge | 210 |  |  |  |  |  |  |
| verdict | 123 |  | 82 |  |  |  | 3 |
| defendant_current_status | 22 |  | 148 | 1 |  |  | 12 |
| plaintiff_current_status | 82 |  | 71 | 8 |  |  | 45 |
| case_type |  |  | 99 |  |  |  | 2 |
| hearing_year | 42 |  |  |  |  |  |  |

`verdict` has **zero** exact-gold candidates. Many gold labels are present verbatim or are workload-visible (`Approved`, `Dismissed`, `Others`), but the generator did not emit them as exact values. That blocks filter queries `q9` and `q15`.

## 9. Correct decision criterion

| Quantity | Product |
| --- | ---: |
| DocETL | 0.1235 |
| Official selected replica | 0.0329 |
| Forced-fill all-expanded | 0.0810 |
| Forced-fill leave-surface-out | 0.0920 |
| Optional-write all-expanded | 0.0811 |
| Best feasible shared-database cohort search | **0.0927** (lower bound) |
| Certified query-local mean upper | **0.2251** (not exact) |

`expanded candidate availability remains insufficient` is retained only if the certified query-local relaxed upper bound is ≤ 0.1235. It is not: 0.2251 > 0.1235.

The current evidence therefore does **not** prove an availability ceiling.

No query had an exact query-local optimum, so the 0.2251 figure cannot be treated as a solved relaxation. Optional-write only barely beat forced-fill on the shared all-channel database (0.0811 vs 0.0810). Shared cohort search reached 0.0927, still below DocETL.

**Primary decision:** `availability remains unresolved because an exact upper bound could not be computed`

Separately, the best feasible shared-database product found by cohort search is **0.0927**. That is a lower bound on attainable frozen-candidate performance, not a ceiling.

No new model arm was launched.
