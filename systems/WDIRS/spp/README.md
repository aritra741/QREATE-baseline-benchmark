# Offline workload-aware relational synthesis

This package implements the deployable system separately from the
ground-truth-only oracle track.

## Deployable path

1. `workload_intent.py` converts SQL or natural-language workloads to a typed,
   schema-independent query-plan IR (projections, aggregates, predicates,
   joins, and semantic column types).
2. `schema_design.py` creates workload-pruned denormalized, star, snowflake,
   preprocessing, and population candidates.
3. `evidence_store.py` stores shared source anchors and cell provenance.
4. `risk_estimator.py` estimates query-conditioned F1-like quality and
   uncertainty from provenance coverage and relational consistency.
5. `optimizer.py` performs progressive pilots, output-equivalence pruning,
   confidence-dominance pruning, and budgeted portfolio/routing selection.
6. `query_plan_compiler.py` deterministically binds the IR to each selected
   schema and emits SQLite SQL; `system.py` validates it and freezes a serving
   bundle. Free-form NL2SQL remains only as a compatibility fallback when an
   older workload has no complete plan.
7. `serving.py` opens checksum-verified SQLite files in immutable read-only
   mode and executes only precompiled workload SQL.

All LLM calls must use `BudgetedLLMClient`. It reserves prompt plus maximum
completion tokens before dispatch and reconciles actual provider usage,
including failed calls, into one `GlobalBudgetLedger`.

Run the native new-system backend:

```bash
python systems/WDIRS/diagnostics/run_native_spp.py \
  --corpus-dir Dataset/Player \
  --workload workload.json \
  --output results/native_spp_Player \
  --token-budget 10846866
```

The native backend applies each candidate preprocessing policy before
candidate extraction. `run_offline_spp.py` is a compatibility/regression
adapter that reuses WDIRS extraction primitives; WDIRS itself is not inserted
into the selected portfolio.

```bash
python systems/WDIRS/diagnostics/run_offline_spp.py \
  --dataset Player \
  --workload workload.json \
  --output results/offline_spp_Player \
  --token-budget 10846866
```

Serve a frozen query without extraction:

```bash
python systems/WDIRS/diagnostics/serve_spp_bundle.py \
  results/offline_spp_Player/serving_bundle q0
```

## Evaluation firewall

`system.py` has no ground-truth input and does not import evaluation or oracle
modules. Evaluation begins only after `manifest.json`, database checksums,
fixed SQL, routing, and `SEALED` exist.

`experiment.py` supports method/baseline matrices, multiple budgets, ablations,
scalability labels, accuracy-cost frontiers, and unused-budget reporting.
`oracle_evaluation.py` computes the best single configuration, exact
same-budget routed portfolio (binary ILP), and unconstrained per-query oracle.
Oracle enumeration tokens and time are reported separately and are never
credited to the deployable budget.

Build oracle references from a separate exhaustive run:

```bash
python systems/WDIRS/diagnostics/build_spp_oracle_references.py \
  --exhaustive-results exhaustive_results.json \
  --deployment-manifest results/offline_spp_Player/serving_bundle/manifest.json \
  --token-budget 10846866 \
  --output results/oracle_Player/references.json
```
