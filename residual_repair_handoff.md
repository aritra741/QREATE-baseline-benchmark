# Residual inclusion at query-correct witness grain

Query-level replacement omitted incumbent rows. This arm only adds residual support, and it no longer treats every COUNT as a primary-entity problem.

$$S_{\text{final}} = S_{\text{incumbent}} \cup \Delta^+$$

Incumbent is the single-action agent database. Remaining budget is θ − 37,718. Gold stays unavailable until the database is frozen.

## Witness grain

Each COUNT query compiles a `WitnessSpec` from the AST:

- `COUNT(*)`: primary row ID
- `COUNT(column)`: row ID plus counted-value non-nullness
- join count: participating row IDs
- `COUNT(DISTINCT x)`: canonical distinct identity
- grouped count: that tuple plus a normalized group key
- multivalued join ON (`||` / token `LIKE`): entity-edge pair

Incumbent support, the excluded universe, and additions all use this grain. Occupied join tuples / rows are not re-proposed, so incumbent group assignments cannot be rewritten.

## Join edges

A validated join writes `signature_edges(join_signature_id, left_rowid, right_rowid, truth, resolved, provenance)`. The join id is canonical over the sorted tables and ON SQL. Official SQL uses a resolved edge when present and otherwise the original ON. Existing edges are never deleted or flipped.

## Group signatures

Inferred labels go to `sig_group_{expr}` / `sig_group_{expr}_r` on the owning table. Official SQL rewrites only that GROUP BY / CASE expression. Shared base columns are not written.

## Cohort invariants

After each accepted query cohort, all 99 statements are re-executed. Rollback if:

- an incumbent witness disappears
- an incumbent group assignment changes
- an incumbent edge disappears
- an unrelated query bag changes (no shared predicate, join, or group expression)

Ineffective additions (not SQL-visible) are rolled back and get no further escalation.

The missing-column invariant remains: referenced attributes exist as typed NULL columns before any model call.

## Run

```text
A′ → single-action agent
  → referenced columns + signature columns + group columns + edge table
  → excluded witnesses on test COUNT queries
  → propose / union / condition-level validate
  → materialize filters, edges, and group signatures only
  → 99-query interference check
  → official_sql counts
```

Eval: `systems/WDIRS/quwarts/eval/residual_arm.py`. Output: `results/quwarts_med_signatures/residual_repair.json`.
