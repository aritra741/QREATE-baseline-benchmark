# Residual inclusion, not support-set replacement

Query-level replacement undercounted because Qwen omitted incumbent rows. This arm never regenerates a support set.

$$S_{\text{final}} = S_{\text{incumbent}} \cup \Delta^+$$

Incumbent is the single-action agent database (product 0.124 under `official_sql`). Remaining budget is θ − 37,718. No deletions, no group reassignment, no plan-level replacement.

## Missing-column invariant

`referenced attribute ⇒ typed physical column exists` (NULL allowed).

`ensure_referenced_columns` adds every workload-referenced attribute to the applicable table (`drug` / `item` / …, else `fact`). Types: REAL for numeric comparisons and SUM/AVG, TEXT otherwise. SELECT aliases are not columns.

`apply_live_signatures` runs this before signature population. `compile_workload` then refreshes the physical schema from SQLite. `assert_queries_execute` fails only on `no such column`.

On stored A′, `med_agg20:q17` no longer dies on `unsuitable_population`. Rewritten SQL executes; the all-NULL column still yields an empty bag until residual adds flags.

## Residual loop

For each prioritized COUNT query (empty incumbent first, then largest excluded universe):

1. Execute official grain SQL. Keep those entity/group rows.
2. Excluded universe = primary-table entities not in that set.
3. Three proposers see **only** excluded entities, in batches of 6, one decision per entity. Missing output is `unknown`, not exclusion.
4. Union of `include=true` proposals. Adjudicate only those.
5. Condition-level validation: each filter and join independently. Stated facts need an exact span. Semantic facts need two independently worded Qwen judgments. Disagreement is no-add.
6. Existing predicted group: ordinary validation. New group: two strategies must agree on the normalized key, the query must execute, and the added row must appear without dropping incumbent grain rowids.
7. Apply by writing `sig_*=1`, `sig_*_r=1` on the excluded row only. Never UPDATE an incumbent support rowid. Optional write of a currently-NULL simple group column.
8. Counts are SQLite `official_sql` on the mutated incumbent, not `count_from_support`.

Prompts forbid listing or replacing a support set. Cache keys stay `(entity, predicate)`, `(entity, group)`, `(left, right, join)`.

## Tests

45 related + 21 signature/invariant passed, including: missing column becomes typed NULL and executes; A′ rewritten queries have no missing-column error; missing model output is unknown; union cannot drop or reassign incumbent rows; new groups need two strategies; residual prompts have no dataset/gold names.

## Run

```text
A′ → single-action agent (incumbent)
  → ensure referenced columns + signature columns
  → enumerate excluded entities on test COUNT queries
  → propose / union / condition-level validate
  → add only validated support
  → official_sql SQLite counts
```

Eval: `systems/WDIRS/quwarts/eval/residual_arm.py`. Output: `results/quwarts_med_signatures/residual_repair.json`. Gold is loaded only after the database is frozen.
