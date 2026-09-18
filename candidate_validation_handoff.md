# Label-free candidate generation and validation

Deterministic compiler is unchanged: AST eligibility, 3VL, resolved/unresolved fallback, non-destructive merge, realizability closure, exact rewrite.

## Model

Every LLM role (planner, executor, refiner, validator) uses `qwen/qwen-2.5-7b-instruct` through `make_caller` (temperature 0.1, completion cap 280), the same OpenRouter configuration as the DocETL/MOAR-matched QuWARTS arms. All spends go through `TokenLedger`. θ = 1,543,790 includes planner, sample executions, refinement, validator, and full-cohort execution.

## Loop

Cohorts are ranked by `query frequency × amplification × unresolved mass ÷ estimated cost`. For each selected cohort the planner emits three generic plans: **direct**, **decompose**, **gleaning**. Each names prompt, context (`value` | `entity_label` | `document`), passes, and cost. The planner may `abstain`. Prompts contain no dataset names, gold, scorer output, or baseline outputs.

The three plans run on one fixed sample stratified without gold by surface present/absent, short/long document, and current predicate status. Responses are cached by plan-and-input hash; hits do not spend.

Validation is label-free:

- grounded existence: TRUE requires an exact supporting span, checked by `find_surface_span` (or a stored nonempty cell).
- semantic membership: independent pairwise comparisons against the document and predicate; names blinded; A/B order randomized and reversed; a preference is kept only when both orders agree; otherwise a third call, then abstain.

The winner runs on the full unresolved cohort only if it has the most pairwise wins **and** beats fallback by at least two net sample preferences. Otherwise the original-expression fallback stays. After an accepted execute: non-destructive merge, `close_attribute`, rematerialize `sig_*` / `sig_*_r`, re-run affected queries, and return cardinality / emptiness / join-yield / conflict / resolution / token deltas to the planner.

Gold is not read during planning, execution, validation, selection, or stopping. The official scorer runs only after the database is frozen.

## Tests

46 passed (`test_signature_candidates`, `test_signature`, `test_signature_populate`, `test_signature_controller`, `test_truth`): cache hits do not spend; ungrounded spans are rejected; pairwise needs both A/B orders; inconclusive validation keeps fallback; planner/validator templates have no dataset names or gold loaders; 99 gold bag-equivalence tests still pass.

## Comparison

Same A′ row set, Med Q, 80/20 seed 42. Fixed and single-action agent numbers are the stored matched-budget run. Abstain-all is A′ with `sig_*_r = 0`. Stored A′ was scored on original SQL (product 0.108); abstain-all uses the fallback rewrite (product 0.107).

| | Tokens | Planner | Executor | Refiner | Validator | Cohorts att/acc | Structure F2 | Cell F1@0.20 | Product |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Stored A′ | 0 | — | — | — | — | — | 0.474 | 0.126 | 0.108 |
| A′ / abstain-all | 0 | 0 | 0 | 0 | 0 | 0 / 0 | 0.453 | 0.120 | 0.107 |
| Fixed policy | 1,543,732 | 0 | 1,543,732 | 0 | 0 | — | 0.517 | 0.152 | 0.090 |
| Single-action agent | 37,718 | 7,199 | 30,519 | 0 | 0 | 1 / 1 | 0.453 | 0.131 | 0.109 |
| Candidate validation | 1,161,706 | 24,345 | 485,425 | 310,303 | 341,633 | 19 / 8 | 0.495 | 0.118 | 0.109 |

Validator agreement 65 / 336 (0.19); tie/abstain 271 / 336 (0.81). Grounded-span rate 52 / 114 (0.46). Cache hits 1,543 / misses 1,503. Resolved TRUE/FALSE/NULL = 295 / 244 / 0; 4,719 atoms left unresolved. Conflicts 0. Budget remaining 382,084 after all 19 cohorts were attempted.

No test-set **product** moved (cell F1 missing on the changed queries). Structure F2 did:

- `med_groupby20:q9` 0.556 → 0.789 — gleaning / `semantic_membership` on treatments
- `med_agg20:q11` 0.385 → 1.000 — direct / `semantic_membership` on pathogenesis

Train/cardinality-only moves (no test product): gleaning treatments also raised `med_agg20:q1`, `med_groupby20:q0`, `med_groupby20:q18`, and unemptied `med_filterjoin20:q0` / `q18`; gleaning prescription_status raised `med_filterjoin20:q4`; direct pathogenesis also raised `med_groupby20:q6` / `q18`. Five accepted `decompose` / `grounded_existence` plans (manufacturer, international_collaboration, funding_sources, mechanism_of_action, key_technologies) wrote spans but did not change query cardinality.

The arm sits between abstain-all and the single-action agent on product, above both on structure F2, and below fixed on cell F1. High validator tie rate kept most high-frequency membership cohorts on fallback.

Details: `results/quwarts_med_signatures/candidate_validation.json`.
