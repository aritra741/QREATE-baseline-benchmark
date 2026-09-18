# Fallback equivalence and query-level support sets

## 1. Fallback invariant

The 0.001 gap was a scoring-path mismatch, not a broken CASE fallback.

On stored A′ (`880034ed40a0895c.db`, sha `68e88d21…`):

- original SQL and all-unresolved `rewrite_sql` bags match on all 99 queries (errors, including `med_agg20:q17` / missing `unsuitable_population`, count as empty).
- sqlglot reserializes every statement (`!=` → `<>`); bags do not change.
- stored A′ was scored with `serve_plans` → `_join_aware_sql` (canonical IDs, `__like` / `__vocab`).
- abstain-all was scored with `rewrite_sql` only, so it reported 0.453 / 0.107.

Join-aware original = join-aware rewrite = stored A′: structure **0.474**, cell F1@0.20 **0.126**, product **0.108**.

`official_sql` is that path. The previous bag test pointed at `systems/results/…` and skipped; it now uses the real artifact and treats SQL errors as empty. 54 tests passed before the query-arm run; query-support unit tests are 7 passed.

Until every arm is scored with `official_sql`, 0.001 gaps are not meaningful.

## 2. Predicate-level validator

Left as a recorded failure. 81% ties, no test-product movement under the old (non-join-aware) scorer. Not extended. Re-scored with `official_sql` it is 0.110 product (below).

## 3. Query-level support sets

Candidates emit supporting rows for each test count query (`entity_id`, `included`, `group_key`, `join_partner_ids`, evidence). Counts are taken from that set. Three plans: direct, decompose (cached obligations), gleaning. Validation is only the symmetric difference of support sets. Empty candidates that wipe a nonempty A′ set are rejected. Gold is applied only after freeze.

θ = 1,543,790. Spent 1,543,555. 20 test queries: 6 accepted (`direct`), 14 retained A′ after budget ran out (~235 tokens left from `med_join20:q15` onward, except the last few already decided as A′).

| Arm | Tokens | F2 | F1@0.20 | Product |
|---|---:|---:|---:|---:|
| Stored / official A′ | 0 | 0.474 | 0.126 | 0.108 |
| Single-action agent (`official_sql`) | 37,718 | 0.484 | 0.178 | 0.124 |
| Predicate-level candidates (`official_sql`) | 1,161,706 | 0.517 | 0.123 | 0.110 |
| Query-level support sets | 1,543,555 | 0.349 | 0.080 | 0.066 |

Accepted `direct` plans undercounted the gold support (q5 −50, q9 −88, q7 −74, q17 −91, q4 −75, q15 −14) and collapsed group keys. That moved product **down**. The mechanism reaches count cells; Qwen 2.5 7B still cannot hold the A′ support set when it is allowed to replace it.

Per-query groups, entity IDs, under/overcount: `results/quwarts_med_signatures/query_support.json`.
