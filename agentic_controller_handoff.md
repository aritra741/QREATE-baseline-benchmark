# Agentic acquisition controller

Deterministic compiler is unchanged: AST eligibility, 3VL, merge, closure, exact rewrite, row/key preservation, budget, unresolved fallback.

## Rewrite

Each live predicate has two columns:

- `sig_{id}` — `sig_truth` ∈ {1, 0, NULL}
- `sig_{id}_r` — `sig_resolved` ∈ {1, 0}

```sql
CASE WHEN sig_resolved = 1 THEN sig_truth ELSE original_predicate END
```

Unresolved (`resolved = 0`) uses the original expression. Resolved SQL NULL (`resolved = 1`, truth NULL) is 3VL unknown and is not the same as fallback.

## Action schema

```json
{
  "scope": {
    "predicate_ids": [],
    "attribute": "",
    "entity_cohort": "unresolved"
  },
  "operator": "grounded_existence | semantic_membership | abstain",
  "context": "value | entity_label | document",
  "model": "",
  "max_tokens": 0,
  "reason": ""
}
```

`validate_action` drops out-of-class atoms. Invalid operators become `abstain`. Existence cannot write membership; membership cannot write presence.

## Controller prompt

`signature_controller.CONTROLLER_PROMPT` asks for one JSON action. It lists only the three typed operators. Attribute names appear only in the STATE payload as AST parameters. No dataset names, no gold, no scorer, no DocETL.

Observation: unresolved counts by class, query frequency, amplification, roles, surface/entity-label rates, representative clips, prior outcomes, conflicts, abstentions, empty-query rate, spent/remaining.

## Validation loop

1. Observe (no gold).
2. Propose: fixed policy (`freq × amp × unresolved`) or agent (`sig_controller` through TokenLedger).
3. Validate schema and operator scope.
4. Execute existing operators on the unresolved cohort.
5. Non-destructive merge, `close_attribute`, rematerialize `sig_*` / `sig_*_r`.
6. Record resolved atoms, grounded-span rate, conflicts, abstentions, emptiness, tokens, remaining budget.
7. Repeat until no unresolved work, budget exhaustion, or abstain/repeat stop.

Fixed baseline is still `populate_signatures`. Agent uses `run_acquisition(policy="agent")`.

## Tests

36 passed (`test_signature`, `test_signature_populate`, `test_signature_controller`, `test_truth`):

- all-unresolved signatures reproduce A′ bags
- resolved SQL NULL ≠ unresolved fallback
- abstain does not change query results
- agent cannot write the other class or non-signature columns; rewrite keeps `CASE … ELSE original`
- operators cannot overwrite each other’s atoms
- budget exhaustion leaves `resolved = 0` and original results
- no dataset/attribute allowlist in controller policy
- 99 gold bag-equivalence tests still pass

## Matched-budget comparison

Same model (`qwen/qwen-2.5-7b-instruct`), operators, θ = 1,543,790, A′ row set, Med Q. Gold used only after each arm.

| | Tokens | Controller | Operators | Structure F2 | Cell F1@0.20 | Product |
|---|---:|---:|---:|---:|---:|---:|
| A′ | — | — | — | — | — | 0.108 |
| Fixed policy | 1,543,732 | 0 | 1,543,732 | 0.517 | 0.152 | 0.090 |
| Agent policy | 37,718 | 7,199 | 30,519 | 0.453 | 0.131 | 0.109 |

Agent Δ product vs fixed: +0.019. Agent Δ tokens vs fixed: −1,506,014.

The agent issued two actions: `semantic_membership` on the highest-frequency unresolved membership cohort, then `abstain` on repeat. Most atoms stayed unresolved, so the original-expression fallback kept A′ behavior. Fixed policy spent the full budget and replaced many predicates with model truths, which lowered the product.

Per-query products and costs: `results/quwarts_med_signatures/acquisition_compare.json`.
