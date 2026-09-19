# Residual inclusion at query-correct witness grain

$$S_{\text{final}} = S_{\text{incumbent}} \cup \Delta^+$$

Incumbent is the single-action agent database. Remaining budget is θ − 37,718. Gold stays unused for decisions. Official score is a pre-spend no-op gate, then the frozen report.

## Join rewrite

Eligible joins become `original_on OR EXISTS(positive resolved edge)`. Empty infrastructure does not wrap away join-aware `__canonical` keys: group rewrite, then join-aware, then the additive `EXISTS`. Negative edges are stored only.

## Blocking

Join candidates come from ON AST blockers (normalized equality, token/delimiter overlap, transformed keys, inverted indexes, top-k retrieval when a join value is missing). Caps: 8 per left row, 48 per query. No left × right Cartesian is sent to Qwen. No signal ⇒ skip the cohort.

## Execution

Prioritized COUNT queries run in round-robin batches of 6. Each batch estimates cost, takes a remaining-budget quota, proposes, validates completed proposals, materializes immediately, checks all 99 bags, then checkpoints. A later `BudgetExhausted` does not discard already-accepted additions.

## Run

```text
pre-spend: 99/99 bags, F2=0.484 F1=0.178 product=0.124
proposed → validated → materialized → SQL-visible: 11 → 4 → 0 → 0
tokens: 909,152 (37,718 + 871,434)
final: F2=0.484 F1@0.20=0.178 product=0.124
```

Eval: `systems/WDIRS/quwarts/eval/residual_arm.py`. Output: `results/quwarts_med_signatures/residual_repair.json`.
