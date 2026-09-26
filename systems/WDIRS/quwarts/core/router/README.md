# QuWARTS router (router-v1)

A gold-free controller that assigns each workload attribute to one operator
family *before execution*, from workload SQL, the raw corpus, an optional
incumbent database, and a small budgeted probe. Rules come from a redundancy
argument (see `policy.py`), not from comparing benchmark scores of arms.

## Pipeline

| Stage | Module | Tokens | Output |
|---|---|---|---|
| Workload features | `workload_features.py` | 0 | roles, query ids, compared literals, closed-label flag per attribute |
| Corpus features | `corpus_features.py` | 0 | per-table token stats, context fit `lambda`, read costs, label-surface rate |
| Residue | `residue.py` | 0 | rows where a workload condition is SQL-UNKNOWN inside incumbent support; incumbent trust (grounding or label validity) |
| Probe | `probes.py` | <= 10% of theta | `kappa`, `g`, `delta` (net of noise), `delta_cross`, `r` per attribute, with a raw journal |
| Policy | `policy.py` | 0 | route per attribute (R1-R5), cost estimate, budget fit, coverage |
| Plan | `plan.py` | 0 | hashed manifest (`plan_hash`, `frozen_hash`, input hashes) |

## Rules

| Rule | Route | Condition |
|---|---|---|
| R1 | `repair` | residue fraction <= 10% and incumbent trust >= 0.5 |
| R2 | `program` | extractive (g >= 0.5), shareable (delta <= 0.2), and either lambda > 1 or anchor regularity r >= 0.5 |
| R2' | `canonical_map` | extractive and shareable, fits, no stable anchor |
| R3 | `fused_map` | interpretive or query-dependent, documents fit |
| R4 | `retrieval_map` | interpretive or query-dependent, documents do not fit |
| R5 | `keep` | the required reads do not fit theta after dropping the lowest-value query slots |

When the probe is unaffordable (for example, long documents with a small
theta), zero-token priors stand in for `g` and `delta` and the reason is
recorded in the plan.

The plan verdict is `workload_served` (coverage >= 0.8), `partially_served`,
`predicted_loss` (coverage < 0.5), or `infeasible_at_theta`.

## Usage

From `systems/WDIRS`:

```bash
python -m quwarts.eval.router_plan --corpus legal          # zero-token dry run
python -m quwarts.eval.router_plan --corpus legal --probe  # spend the probe budget
```

Plans are written to `results/quwarts_router/<corpus>/{dry_run,probe}/`.

## Protocol

1. Constants in `constants.py` are frozen; their hash is in every plan.
2. Med, Finan, and Legal informed the design. Agreement with their outcomes is
   a sanity check, not validation.
3. Validation is one frozen run on corpora not used in router design, scored
   on whether the plan verdict and operator choice predict the outcome.
4. Operator executors are not yet wired to plans (see "Next").

## Next

- Executor adapters that run each route from a plan (group repair, amortized
  programs, fused maps) under one shared ledger.
- A probe run per corpus, then freeze and evaluate on held-out corpora.
