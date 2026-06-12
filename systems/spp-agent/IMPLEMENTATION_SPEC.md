# SPP-Agent Redesign: Implementation Specification

> **For a coding agent.**  
> Follow every section in the order given. Each section lists: the files to touch, the exact changes required, invariants to preserve, and the acceptance test. Do not skip sections. Do not reorder sections. Do not modify files not listed in a section.

---

## 0. Context

### Repository root for this spec
```
systems/spp-agent/
```
All file paths below are relative to this root.

### Ground-truth firewall — NEVER violate
No code that runs at deployment time (probe → agent → pipeline) may import, read, or pass `true_errors`, `reward_rows`, `true_spp_error`, or ground-truth tables **except** inside `stage5/`. Violating this invalidates the entire benchmark.

### Dependency order
```
Task 1  config space expansion
Task 2  query clustering moved to pipeline front
Task 3  cluster-conditioned glass-box signals
Task 4  cluster-stratified LLM judge + cluster BTL with uncertainty
Task 5  surrogate base: uncertainty output
Task 6  per-cluster surrogate bakeoff
Task 7  routing assignment (replaces Stage 3 selection)
Task 8  PipelineResult → routing table
Task 9  Stage 1G: remove ground-truth leak
Task 10 ReAct agent: new action space
Task 11 Evaluation: routed error as primary metric
Task 12 Structured audit log
Task 13 Config.yaml + requirements updates
```

---

## Task 1 — Expand Configuration Space

### Files to modify
- `optimizer/config_space.py`
- `config/defaults.yaml`

### What to change

#### `config/defaults.yaml`

Replace the `population_config_space` block:

```yaml
population_config_space:
  er_strategy:
    - "embedding_0.7"
    - "embedding_0.8"
    - "embedding_0.9"
    - "llm"
  norm_strategy:
    - "dictionary"
    - "llm"
  unit_strategy:
    - "none"
    - "unit"
  miss_strategy:
    - "drop"
    - "mean"
    - "median"
    - "mode"
    - "constant"
    - "llm"
  type_coercion:
    - "strict"
    - "permissive"
    - "llm"
```

This makes the full space 4 × 2 × 2 × 6 × 3 = **288 configs**.

#### `optimizer/config_space.py`

1. Add `type_coercion: str` field to `PopulationConfig`.
2. Update `_make_config_id` to include `type_coercion`:
   ```python
   return f"er={er}|norm={norm}|unit={unit}|miss={miss}|coerce={coerce}"
   ```
3. Update `generate_config_space` to iterate over the new `type_coercion` axis from config.
4. Update `encode_config_features` to append a one-hot for `type_coercion`. The feature vector grows from 8 dims to 8 + 3 = **11 dims** (4 ER + 2 norm + 2 unit + 6 miss + 3 coerce + ... wait: 4+2+2+6+3 = 17 dims).

   Final feature vector order:
   ```
   [er=embedding_0.7, er=embedding_0.8, er=embedding_0.9, er=llm,
    norm=dictionary, norm=llm,
    unit=none, unit=unit,
    miss=drop, miss=mean, miss=median, miss=mode, miss=constant, miss=llm,
    coerce=strict, coerce=permissive, coerce=llm]
   ```
   Total: **17 dims**.

5. Add a helper `_parse_config_id(config_id: str) -> PopulationConfig` that handles the new `coerce=` field (default `"strict"` if absent, for backward-compat with cached probe data).

### Invariants
- `PopulationConfig` must remain a frozen dataclass.
- `generate_config_space()` must return a list deterministically sorted by `config_id` string.
- Old 16-config probe caches (which lack `coerce=`) must still parse via `_parse_config_id` by defaulting `type_coercion="strict"`.

### Acceptance
`len(generate_config_space()) == 288`. Feature vector returned by `encode_config_features` has shape `(17,)`.

---

## Task 2 — Move Query Clustering to Pipeline Front

### Files to modify
- `pipeline/full_pipeline.py`
- `stage4/query_clustering.py` (add one function, no removals)
- `data/instance_builder.py` (no change needed, it already passes queries)

### Background
`cluster_queries_structural` already exists in `stage4/query_clustering.py`. It returns `(labels: list[int], info: dict)`. We need to:
1. Run it **before** the probe phase in `run_spp_pipeline`.
2. Store cluster assignments so every downstream module receives them.

### What to change

#### `stage4/query_clustering.py`

Add a new function after `cluster_queries_structural`:

```python
def choose_n_clusters(queries: list[dict], *, min_k: int = 2, max_k: int = 4, seed: int = 42) -> int:
    """Choose number of clusters using elbow on KMeans inertia.
    Deployment-visible only: uses query structural features.
    Returns k in [min_k, max_k].
    """
```

Implementation: run KMeans for k ∈ range(min_k, max_k+1), compute the inertia drop ratio
`(inertia[k] - inertia[k+1]) / inertia[k]` and pick the k where this ratio first drops below 0.2
(i.e., the gain from adding another cluster becomes small). If `len(queries) < min_k`, return 1.

Add a new dataclass:

```python
@dataclass
class QueryClusters:
    n_clusters: int
    labels: list[int]          # index-aligned with queries list
    cluster_to_queries: dict[int, list[dict]]   # cluster_id -> query dicts
    cluster_types: dict[int, str]   # cluster_id -> "aggregation" | "join" | "filter" | "mixed"
    centroids: list[list[float]]
    info: dict
```

Add `assign_cluster_types(centroids: list[list[float]]) -> dict[int, str]`:
- Feature dim 0=COUNT, 1=SUM, 2=AVG, 3=MIN, 4=MAX → aggregation weight
- Feature dim 6=JOIN → join weight
- Feature dim 7=WHERE → filter weight
- For each centroid: if JOIN > 0.4 → "join"; elif any of dims 0-4 > 0.3 → "aggregation"; elif WHERE > 0.4 → "filter"; else → "mixed"

Add top-level function:

```python
def cluster_workload(queries: list[dict], *, seed: int = 42) -> QueryClusters:
    """Full clustering pipeline. Chooses k, clusters, types. Deployment-visible."""
```

#### `pipeline/full_pipeline.py`

In `run_spp_pipeline`, as the very first step after resolving `thresholds`:

```python
from stage4.query_clustering import cluster_workload
query_clusters = cluster_workload(queries, seed=cfg_seed)
logger.info("Query clusters: n=%d types=%s sizes=%s",
            query_clusters.n_clusters,
            query_clusters.cluster_types,
            {k: len(v) for k, v in query_clusters.cluster_to_queries.items()})
```

Pass `query_clusters` into every downstream function that needs cluster-awareness (Tasks 3, 4, 6, 7).

### Invariants
- If `len(queries) == 0`, `cluster_workload` returns a single cluster containing no queries.
- The `labels` list is index-aligned with the input `queries` list (not sorted by query_id).
- `cluster_types` keys are integers matching the labels.

---

## Task 3 — Cluster-Conditioned Glass-Box Signals

### Files to create
- `diagnostics/cluster_glass_box.py`

### Files to modify
- `optimizer/probing.py`
- `optimizer/probing.py` → `ProbeData` dataclass

### New file: `diagnostics/cluster_glass_box.py`

```python
"""Cluster-conditioned glass-box composite scores.

For each (config, cluster) pair, produce a single quality score by weighting
the tier1 diagnostic signals according to the cluster type.
No ground-truth access anywhere in this module.
"""
```

#### Signal weight tables

Define a constant `CLUSTER_WEIGHTS: dict[str, dict[str, float]]`:

```python
CLUSTER_WEIGHTS = {
    "aggregation": {
        "schema_column_coverage":          0.10,
        "missing_value_rate_inv":          0.20,   # = 1 - missing_value_rate
        "duplicate_candidate_rate_inv":    0.05,
        "entity_ambiguity_score_inv":      0.05,
        "json_parse_error_rate_inv":       0.10,
        "extraction_refusal_or_empty_rate_inv": 0.05,
        "unit_parse_success_rate":         0.25,
        "numeric_type_success_rate":       0.20,
    },
    "join": {
        "schema_column_coverage":          0.15,
        "missing_value_rate_inv":          0.10,
        "duplicate_candidate_rate_inv":    0.25,
        "entity_ambiguity_score_inv":      0.25,
        "json_parse_error_rate_inv":       0.10,
        "extraction_refusal_or_empty_rate_inv": 0.05,
        "unit_parse_success_rate":         0.05,
        "numeric_type_success_rate":       0.05,
    },
    "filter": {
        "schema_column_coverage":          0.30,
        "missing_value_rate_inv":          0.15,
        "duplicate_candidate_rate_inv":    0.10,
        "entity_ambiguity_score_inv":      0.10,
        "json_parse_error_rate_inv":       0.10,
        "extraction_refusal_or_empty_rate_inv": 0.05,
        "unit_parse_success_rate":         0.05,
        "numeric_type_success_rate":       0.15,
    },
    "mixed": {   # equal weighting (same as existing global composite)
        "schema_column_coverage":          0.125,
        "missing_value_rate_inv":          0.125,
        "duplicate_candidate_rate_inv":    0.125,
        "entity_ambiguity_score_inv":      0.125,
        "json_parse_error_rate_inv":       0.125,
        "extraction_refusal_or_empty_rate_inv": 0.125,
        "unit_parse_success_rate":         0.125,
        "numeric_type_success_rate":       0.125,
    },
}
```

All weights within a cluster type must sum to 1.0.

#### Function signature

```python
def compute_cluster_glass_box(
    tier1: dict,
    cluster_type: str,
) -> float:
    """Compute cluster-conditioned glass-box composite for one (config, cluster) pair.

    tier1: raw signals dict from compute_tier1().
    cluster_type: one of "aggregation", "join", "filter", "mixed".
    Returns float in [0, 1].
    """
```

Implementation:
- Build a `signals` dict mapping each weight key to its value from `tier1`. For keys ending in `_inv`, compute `1.0 - tier1[key_without_inv]`, clamped to [0, 1].
- `missing_value_rate_inv` = `1.0 - tier1.get("missing_value_rate", 0.0)`
- `duplicate_candidate_rate_inv` = `1.0 - tier1.get("duplicate_candidate_rate", 0.0)`
- `entity_ambiguity_score_inv` = `1.0 - tier1.get("entity_ambiguity_score", 0.0)`
- `json_parse_error_rate_inv` = `1.0 - tier1.get("json_parse_error_rate", 0.0)`
- `extraction_refusal_or_empty_rate_inv` = `1.0 - tier1.get("extraction_refusal_or_empty_rate", 0.0)`
- For missing values in `tier1`, use the default that indicates worst quality (0.0 or 1.0 as appropriate).
- If `cluster_type` not in `CLUSTER_WEIGHTS`, fall back to `"mixed"`.
- Weighted average: `sum(weight * signals[key] for key, weight in weights.items())`.

Add a second function:

```python
def compute_all_cluster_glass_boxes(
    tier1_signals: dict[str, dict],       # config_id -> tier1 dict
    cluster_types: dict[int, str],        # cluster_id -> cluster type string
) -> dict[str, dict[int, float]]:
    """Returns {config_id: {cluster_id: score}} for all (config, cluster) pairs."""
```

#### `optimizer/probing.py` — `ProbeData` changes

Add two fields to `ProbeData`:

```python
cluster_glass_box_composites: dict[str, dict[int, float]] = field(default_factory=dict)
# {config_id: {cluster_id: cluster-conditioned score}}

cluster_btl_scores: dict[int, dict[str, float]] = field(default_factory=dict)
# {cluster_id: {config_id: btl_score}}  — populated in Task 4
```

These use `field(default_factory=...)` so old callers creating `ProbeData` without them still work.

In `run_probes`, after the BTL step, compute and attach cluster glass-box scores:

```python
from diagnostics.cluster_glass_box import compute_all_cluster_glass_boxes
# query_clusters is passed in as a new optional parameter
if query_clusters is not None:
    cluster_gb = compute_all_cluster_glass_boxes(tier1_signals, query_clusters.cluster_types)
    # attach to returned ProbeData
```

Add `query_clusters` as an optional keyword argument to `run_probes`. When `None`, skip cluster glass-box computation (backward-compat).

### Invariants
- The existing `glass_box_composites` (global composite) must still be computed and stored — it is used as fallback by existing surrogates.
- `cluster_glass_box_composites` scores are in [0, 1].

---

## Task 4 — Cluster-Stratified LLM Judging + Cluster BTL with Uncertainty

### Files to modify
- `judge/pairwise.py`
- `judge/btl.py`
- `optimizer/probing.py`

### `judge/pairwise.py`

Modify `judge_pairwise` to accept an optional `cluster_queries: list[dict] | None = None` keyword argument. When provided, use only those queries in the prompt instead of `queries[:8]`.  
Change the prompt instruction to:
```
"Which populated database is likely to answer the following {cluster_type} queries more accurately?"
```
where `cluster_type` is an optional `str` parameter defaulting to `"workload"`.

Keep the existing signature fully backward-compatible (all new params are keyword-only with defaults).

### `judge/btl.py`

Add a new function below `fit_btl`:

```python
def fit_btl_with_uncertainty(
    comparisons: list[dict],
    *,
    all_config_ids: list[str] | None = None,
    n_bootstrap: int = 50,
    seed: int = 42,
    max_iter: int = 200,
    tol: float = 1e-9,
) -> dict[str, tuple[float, float]]:
    """Fit BTL with bootstrap uncertainty estimates.

    Returns {config_id: (mean_score, std_score)}.
    Uses n_bootstrap resamples of the comparisons list.
    If fewer than 2 comparisons, returns score=1.0, std=0.0 for all configs.
    """
```

Implementation:
1. Call `fit_btl(comparisons, all_config_ids=all_config_ids)` once for the point estimate.
2. Bootstrap: for each of `n_bootstrap` iterations, resample `comparisons` with replacement using `random.Random(seed + i)`, call `fit_btl` on the resample, collect scores.
3. For each config, compute `mean` and `std` across bootstrap scores.
4. Return `{cid: (mean, std)}`.

If fewer than 2 comparisons, skip bootstrapping and return `{cid: (score, 0.0)}`.

### `optimizer/probing.py`

In `run_probes`, replace the current single judge loop with a **cluster-stratified** loop:

```python
# When query_clusters is provided:
for cluster_id, cluster_queries_list in query_clusters.cluster_to_queries.items():
    cluster_type = query_clusters.cluster_types[cluster_id]
    cluster_comparisons = []
    for (a, b) in pairs:
        result = judge_pairwise(
            databases[a], databases[b], schema,
            workload_queries, configs[a], configs[b],
            llm_cfg["judge_model"],
            required_tables=required_tables,
            cluster_queries=cluster_queries_list,
            cluster_type=cluster_type,
        )
        # ... record winner/loser into cluster_comparisons
    btl_result = fit_btl_with_uncertainty(cluster_comparisons, all_config_ids=config_ids)
    cluster_btl_scores[cluster_id] = {cid: score for cid, (score, _) in btl_result.items()}
    cluster_btl_uncertainty[cluster_id] = {cid: std for cid, (_, std) in btl_result.items()}
```

When `query_clusters is None`, fall back to the current global judge loop (single BTL, no cluster split). This preserves backward compatibility.

Add to `ProbeData`:
```python
cluster_btl_uncertainty: dict[int, dict[str, float]] = field(default_factory=dict)
# {cluster_id: {config_id: std_of_btl_score}}
```

Also retain `pairwise_comparisons` as the union of all cluster comparisons (for backward compat with anything that reads it).

### Cost accounting
Each cluster judge call costs tokens. Add them all to `total_cost`.

### Invariants
- When `query_clusters` is `None`, `ProbeData.cluster_btl_scores` and `cluster_btl_uncertainty` are empty dicts. Downstream code must handle this with fallback to `btl_scores`.
- `judge_pairwise` signature remains backward-compatible.

---

## Task 5 — Surrogate Base: Uncertainty Output

### Files to modify
- `surrogates/base.py`
- `surrogates/gp_proxy_glass.py`
- `surrogates/rf_proxy_glass.py`
- `surrogates/gbdt_proxy_glass.py`
- `surrogates/linear_proxy_glass.py`
- `surrogates/direct_probe_ranking.py`
- `surrogates/glass_box_proxy.py`
- `surrogates/llm_judge_btl.py`
- `surrogates/tpe_proxy.py`
- `surrogates/random_ranking.py`

### `surrogates/base.py`

Add two new methods to `BaseSurrogate`:

```python
def score_with_uncertainty(self, config_id: str) -> tuple[float, float]:
    """Return (predicted_score, uncertainty_estimate).

    Default implementation: uncertainty = 0.0 (point estimate surrogates).
    Override in surrogates that can produce calibrated uncertainty (e.g. GP).
    """
    return self.score(config_id), 0.0

def fit_cluster(self, probe_data, cluster_id: int) -> None:
    """Fit surrogate using cluster-conditioned signals for a specific cluster.

    Default: fall back to global fit(probe_data).
    Override in surrogates that can use cluster_glass_box_composites or
    cluster_btl_scores.
    """
    self.fit(probe_data)
```

Do **not** change `score` or `rank` signatures.

### `surrogates/gp_proxy_glass.py`

Override `score_with_uncertainty`: use the GP posterior `predict(return_std=True)` to return `(mean, std)`. The GP already has a fitted sklearn `GaussianProcessRegressor`; call `gpr.predict([feature_vec], return_std=True)` and return `(float(mean[0]), float(std[0]))`.

Override `fit_cluster`: if `probe_data.cluster_glass_box_composites` is non-empty and `cluster_id` is in any config's dict, use the cluster-conditioned scores instead of the global composite as training targets.

### All other surrogates
Override `score_with_uncertainty` only in `gp_proxy_glass`. All others inherit the default `(score, 0.0)` — this is correct, no changes needed.

Override `fit_cluster` only in surrogates that store `glass_box_composites` or `btl_scores` internally. The minimal correct implementation for all surrogates other than GP:

```python
def fit_cluster(self, probe_data, cluster_id: int) -> None:
    # Use cluster-conditioned glass_box if available, else fall back to global
    if probe_data.cluster_glass_box_composites:
        # Build a temporary view of probe_data with cluster-specific composites
        import copy
        pd_view = copy.copy(probe_data)
        pd_view.glass_box_composites = {
            cid: probe_data.cluster_glass_box_composites.get(cid, {}).get(cluster_id, v)
            for cid, v in probe_data.glass_box_composites.items()
        }
        if probe_data.cluster_btl_scores.get(cluster_id):
            pd_view.btl_scores = probe_data.cluster_btl_scores[cluster_id]
        self.fit(pd_view)
    else:
        self.fit(probe_data)
```

Add this to: `direct_probe_ranking`, `glass_box_proxy`, `llm_judge_btl`, `linear_proxy_glass`, `rf_proxy_glass`, `gbdt_proxy_glass`, `tpe_proxy`, `random_ranking`.

### Invariants
- Existing `fit` and `score` methods are not changed. `fit_cluster` is additive.
- `score_with_uncertainty` returns `(float, float)` always.

---

## Task 6 — Per-Cluster Surrogate Bakeoff

### Files to modify
- `stage2/surrogate_comparison.py`
- `thresholds/optimizer.py`

### `stage2/surrogate_comparison.py`

Add a new function (do not remove or modify existing `compare_surrogates`):

```python
def compare_surrogates_per_cluster(
    probe_data,
    surrogates: list[str],
    query_clusters,           # QueryClusters dataclass from stage4/query_clustering.py
    *,
    thresholds,
    seed: int = 42,
) -> dict[int, "SurrogateComparisonResult"]:
    """Run surrogate bakeoff separately for each query cluster.

    For each cluster:
      - Fit each surrogate using fit_cluster(probe_data, cluster_id).
      - LOO validation: reference signal = cluster-specific BTL scores
        (probe_data.cluster_btl_scores[cluster_id]).
        If cluster BTL scores are absent, fall back to global BTL scores.
      - Return SurrogateComparisonResult for that cluster.

    Returns {cluster_id: SurrogateComparisonResult}.
    """
```

Implementation:
1. For each `cluster_id` in `range(query_clusters.n_clusters)`:
   a. Get `ref_scores = probe_data.cluster_btl_scores.get(cluster_id) or probe_data.btl_scores`.
   b. Build a per-cluster `true_errors` proxy: `{cid: -ref_scores[cid] for cid in config_ids}`.
   c. For each surrogate name, compute LOO metrics using `_compute_metrics` but with a modified version that calls `surrogate.fit_cluster(reduced_probe_data, cluster_id)` instead of `surrogate.fit(reduced_probe_data)`.
   d. Produce `SurrogateComparisonResult`.
2. Return the dict.

Add a helper for the per-cluster LOO step:

```python
def _compute_metrics_cluster(
    surrogate_name: str,
    probe_data,
    cluster_id: int,
    ref_btl_scores: dict[str, float],
    seed: int,
) -> SurrogateMetrics:
    """LOO metrics for one surrogate on one cluster."""
```

This mirrors `_compute_metrics` but:
- Uses `surrogate.fit_cluster(reduced, cluster_id)` instead of `surrogate.fit(reduced)`.
- Uses `ref_btl_scores` (cluster BTL, negated) as the reference instead of `true_errors`.

### `thresholds/optimizer.py`

Add a helper:

```python
def _compute_loo_rhos_per_cluster(
    probe_data,
    query_clusters,
) -> dict[int, dict[str, float]]:
    """Returns {cluster_id: {surrogate_name: loo_rho}} for all clusters."""
```

This calls `_compute_loo_rhos` with cluster-specific BTL as the reference for each cluster.

### Invariants
- Existing `compare_surrogates` and `_compute_loo_rhos` are not modified.
- If `query_clusters.n_clusters == 1`, returns a single-element dict `{0: result}`.
- If cluster BTL unavailable, falls back gracefully to global BTL.

---

## Task 7 — Routing Assignment (Replaces Stage 3 Global Selection)

### Files to create
- `stage3/routing_assignment.py`

### Files to modify
- `pipeline/full_pipeline.py` (wire in the new step)

### New file: `stage3/routing_assignment.py`

```python
"""Cluster-to-configuration assignment under token budget constraints.

Replaces the Stage 3 greedy/BO/ILP/coord_descent global ranking.
No ground-truth access.
"""
```

#### Data structures

```python
@dataclass
class RoutingTable:
    cluster_to_config: dict[int, str]   # cluster_id -> config_id
    selected_configs: list[str]          # distinct config_ids (deduplicated)
    cluster_types: dict[int, str]        # cluster_id -> cluster type string
    assignment_scores: dict[int, float]  # cluster_id -> best predicted score
    assignment_uncertainty: dict[int, float]  # cluster_id -> uncertainty of chosen config
    n_materializations: int              # len(selected_configs)
    risk_level: str                      # "risk_neutral" | "risk_averse"
    token_cost_estimate: float
```

#### Main function

```python
def assign_configs_to_clusters(
    query_clusters,                          # QueryClusters
    probe_data,                              # ProbeData
    cluster_surrogates: dict[int, str],      # {cluster_id: surrogate_name} from bakeoff
    all_config_ids: list[str],               # full candidate space (all 288 or subset)
    token_budget,                            # TokenBudget instance
    cost_model,                              # CostModel instance
    n_docs: int,
    *,
    risk_level: str = "risk_neutral",        # "risk_neutral" | "risk_averse"
    risk_lambda: float = 0.5,               # penalty weight for uncertainty
    seed: int = 42,
) -> RoutingTable:
    """Jointly select configurations and build routing table.

    Algorithm:
    1. For each cluster, score all candidate configs using the cluster's surrogate
       (fitted with fit_cluster). Score = predicted_quality - risk_lambda * uncertainty
       if risk_averse, else just predicted_quality.
    2. For each cluster, rank configs by adjusted score → preferred config list.
    3. Solve assignment: greedily assign best-scoring config per cluster, subject
       to token budget (shared materialization reuse).
    4. If budget is tight, merge clusters to the same config (choose the one
       with highest summed adjusted score across clusters).
    5. Return RoutingTable.
    """
```

#### Budget-aware assignment algorithm (step 3-4)

```
materialized = {}   # config_id -> bool (already counted in budget)
routing = {}        # cluster_id -> config_id

sort clusters by cluster size descending (larger clusters get first pick)

for cluster_id in sorted_clusters:
    surrogate = fit_cluster(probe_data, cluster_id) for cluster_surrogates[cluster_id]
    ranked = [(config_id, score, uncertainty) for config_id in all_config_ids]
    sorted by adjusted_score desc

    for (config_id, score, uncertainty) in ranked:
        if config_id in materialized:
            # reuse: no extra cost
            routing[cluster_id] = config_id
            break
        marginal = cost_model.config_marginal_cost(config_id, n_docs)
        if token_budget.remaining >= marginal:
            token_budget.spend(marginal, label=f"materialize:{config_id}")
            materialized[config_id] = True
            routing[cluster_id] = config_id
            break
    else:
        # nothing affordable: assign cheapest already-materialized config
        if materialized:
            routing[cluster_id] = max(materialized, key=lambda c: surrogate.score(c))
        else:
            # absolute fallback: pick first in ranked list regardless of budget
            routing[cluster_id] = ranked[0][0]
```

#### Fallback function

```python
def deterministic_routing_fallback(
    query_clusters,
    probe_data,
) -> RoutingTable:
    """Deterministic fallback when surrogates are unavailable.

    Assigns the config with the highest global glass-box score to all clusters.
    """
```

### Invariants
- `RoutingTable.selected_configs` is always a deduplicated list (no repeats).
- At least 1 config is always selected.
- `cluster_to_config` keys cover all cluster IDs in `query_clusters`.
- This module never reads `true_errors`, `reward_rows`, or any ground-truth field.

---

## Task 8 — PipelineResult → Routing Table Output

### Files to modify
- `pipeline/full_pipeline.py`
- `agent/tools.py`

### `pipeline/full_pipeline.py`

#### `PipelineResult` dataclass

Add fields; keep all existing fields for backward compatibility:

```python
@dataclass
class PipelineResult:
    # EXISTING fields (do not remove):
    selected_configs: list[str]          # now = routing_table.selected_configs
    best_surrogate: str                  # global fallback surrogate name
    best_algorithm: str                  # set to "routing_assignment"
    stage1_recommendations: dict[str, Any]
    stage1_probe_fidelity_rho: float
    stage2_surrogate_rhos: dict[str, float]
    stage3_algorithm_scores: dict[str, float]
    stage4_retained_components: list[str]
    n_probe_configs_used: int
    probing_expanded: bool
    token_budget_total: float
    token_budget_spent: float
    token_budget_remaining: float
    n_configs_selected: int
    thresholds_used: dict[str, Any]

    # NEW fields:
    routing_table: "RoutingTable | None" = None  # from stage3/routing_assignment.py
    cluster_surrogates: dict[int, str] = field(default_factory=dict)
    # {cluster_id: surrogate_name selected for that cluster}
    query_cluster_info: dict[str, Any] = field(default_factory=dict)
    # serializable summary of QueryClusters
    risk_level: str = "risk_neutral"
```

#### `run_spp_pipeline` wiring

Replace the current Stage 3 call block with:

```python
# Stage 3: per-cluster surrogate bakeoff
from stage2.surrogate_comparison import compare_surrogates_per_cluster
cluster_bakeoff_results = compare_surrogates_per_cluster(
    probe_data, candidate_surrogates, query_clusters, thresholds=tc, seed=seed
)
cluster_surrogates = {cid: res.best_surrogate for cid, res in cluster_bakeoff_results.items()}

# Stage 3 → routing assignment
from stage3.routing_assignment import assign_configs_to_clusters
routing_table = assign_configs_to_clusters(
    query_clusters, probe_data, cluster_surrogates,
    all_config_ids=all_candidate_ids,
    token_budget=token_budget,
    cost_model=cost_model,
    n_docs=n_docs,
    risk_level=agent_risk_level,  # passed through from agent decision
    seed=seed,
)
```

Remove the old calls to Stage 3 algorithm selection (`_stage2_to_stage3_algorithm`, `run_stage3_*`). The `best_algorithm` field is set to `"routing_assignment"`.

Set `selected_configs = routing_table.selected_configs` and `n_configs_selected = routing_table.n_materializations`.

#### `agent/tools.py`

In `run_pipeline_and_select` return dict, add:

```python
"routing_table": {
    str(k): v for k, v in result.routing_table.cluster_to_config.items()
} if result.routing_table else {},
"cluster_surrogates": {str(k): v for k, v in result.cluster_surrogates.items()},
"query_cluster_info": result.query_cluster_info,
"risk_level": result.risk_level,
```

### Invariants
- All existing keys in the `run_pipeline_and_select` return dict are preserved.
- `PipelineResult.selected_configs` continues to work for callers that haven't been updated yet.

---

## Task 9 — Stage 1G: Remove Ground-Truth Leak

### Files to modify
- `stage1/analysis_1g.py`
- `stage1/characterizer.py`

### `stage1/analysis_1g.py`

**Full rewrite.** Replace the current `analyze_routing_gap` function.

The new function measures **surrogate disagreement** — how much different surrogates disagree on config rankings. High disagreement across surrogates means routing matters; invest in it.

```python
def analyze_routing_gap(
    probe_data,
    *,
    thresholds,
    reward_rows: list[dict] | None = None,   # kept for signature compat; NEVER READ
) -> dict:
    """Measure surrogate disagreement as a deployment-visible routing signal.

    Does NOT use reward_rows, true_errors, or any ground-truth signal.
    reward_rows parameter is accepted but ignored.

    Disagreement metric: mean Kendall-tau distance between all pairs of
    surrogate rankings on the probed configs.
    High disagreement (> thresholds.routing_gap proxy) → surrogates differ →
    routing across surrogates is valuable → use_routing=True.
    """
```

Implementation:
1. Score all probed configs with the following 4 deployment-visible surrogates (no ground truth needed):
   - `direct_probe_ranking`
   - `glass_box_proxy`
   - `llm_judge_btl` (skip if `probe_data.btl_scores` is empty)
   - `rf_proxy_glass`
2. For each surrogate, get ranked list of config IDs.
3. Compute pairwise Kendall-tau between all surrogate ranking pairs using `scipy.stats.kendalltau`.
4. Mean disagreement = `1 - mean(|tau|)` across all pairs (higher = more disagreement).
5. If mean_disagreement > 0.3 (a deployment-visible threshold, add to `ThresholdConfig` as `surrogate_disagreement_threshold: float = 0.3`): `recommendation = "co_optimize_routing"`. Else: `recommendation = "routing_secondary"`.

Return dict:
```python
{
    "surrogate_rankings": {name: ranked_list},
    "pairwise_kendall_tau": {f"{a}_vs_{b}": tau},
    "mean_disagreement": float,
    "disagreement_above_threshold": bool,
    "recommendation": str,
}
```

### `stage1/characterizer.py`

Remove `reward_rows` from the `analyze_routing_gap` call:
```python
routing = analyze_routing_gap(probe_data, thresholds=thresholds)
```
(Pass nothing for `reward_rows`; the parameter is still accepted but ignored in the new implementation.)

Also remove `reward_rows` from the `characterize` function signature entirely, and from all callers that pass it.

### `thresholds/schema.py`

Add to `ThresholdConfig`:
```python
surrogate_disagreement_threshold: float = 0.3
```

Add to `THRESHOLD_SEARCH_SPACES`:
```python
"surrogate_disagreement_threshold": ("float", 0.1, 0.7),
```

### Invariants
- `analyze_routing_gap` must never import from `stage5`, never read `true_spp_error`, never read `reward_rows` content.
- The function signature keeps `reward_rows=None` for backward compatibility with any callers, but the body discards it immediately.

---

## Task 10 — ReAct Agent: Extended Action Space

### Files to modify
- `agent/tools.py`
- `agent/prompts/react_system.txt`
- `agent/react_agent.py`

### `agent/tools.py`

#### New tool names

Add to `TOOL_NAMES`:
```python
"choose_cluster_granularity",
"stop_probing",
"choose_risk_level",
"emit_routing_table",
```

Remove `"commit"` from this list (the action is now replaced by `"emit_routing_table"`).  
Keep `"commit"` as an alias in `dispatch` that calls `emit_routing_table` with the same surrogate — for backward compat with any cached agent traces.

#### New fields in `AgentToolkit`
```python
risk_level: str = field(default="risk_neutral", init=False)
routing_table: dict[int, str] = field(default_factory=dict, init=False)
probing_stopped: bool = field(default=False, init=False)
n_clusters_chosen: int = field(default=0, init=False)
```

#### New tool: `choose_cluster_granularity`

```python
def choose_cluster_granularity(self, n_clusters: int) -> dict[str, Any]:
    """Agent decides how many query clusters to use.

    n_clusters: 1 (global) to 4.
    Overwrites the auto-chosen cluster count from cluster_workload().
    Returns the updated cluster structure.
    Allowed only before run_pipeline_and_select.
    """
```

If `n_clusters < 1` or `n_clusters > 6`, return an error dict. Re-run `cluster_workload` with the forced `n_clusters` (pass it as a fixed override to KMeans). Log the decision. Return summary of resulting clusters.

#### New tool: `stop_probing`

```python
def stop_probing(self) -> dict[str, Any]:
    """Agent explicitly stops probe expansion and moves to selection.

    Sets self.probing_stopped = True.
    Returns current probe summary.
    """
```

#### New tool: `choose_risk_level`

```python
def choose_risk_level(self, level: str) -> dict[str, Any]:
    """Agent sets risk preference for routing assignment.

    level: "risk_neutral" | "risk_averse"
    risk_averse penalizes uncertain configs even if they score higher in expectation.
    """
```

Validates `level` is one of the two allowed values. Sets `self.risk_level = level`. Returns confirmation.

#### New tool: `emit_routing_table`

```python
def emit_routing_table(self, surrogate_name: str = "") -> dict[str, Any]:
    """Agent finalizes routing by calling run_pipeline_and_select with current settings.

    This replaces commit() as the terminal action.
    If surrogate_name is provided, it is used as a global override for all clusters.
    Returns the same dict as run_pipeline_and_select plus the routing table.
    """
```

Internally calls `self.run_pipeline_and_select(...)`. Sets `self.committed_surrogate` for backward compat.

#### Modified adaptive probing logic in `probe_additional_configs`

Replace the old docstring and logic:

```
Old: "Call this when Stage 1 probe fidelity is too low (rho < rho_bakeoff)."
New: "Call this when cost-benefit analysis shows more probing would improve routing."
```

The function now accepts a `reasoning: str = ""` parameter that the agent must provide explaining why it decided to probe more. Log this reason. The old logic body is unchanged.

#### `dispatch` update

Add routing for all 4 new tools. Keep `"commit"` routing as alias to `emit_routing_table`.

### `agent/prompts/react_system.txt`

**Full rewrite.** New content:

```
You are an SPP pipeline agent for workload-aware database synthesis.

Your goal: Given a corpus, query workload, and token budget, select configurations
and emit a ROUTING TABLE mapping query clusters to synthesized databases.
The routing table is the final output — not a ranked config list.

You work only from deployment-visible signals:
  - Glass-box composite scores per cluster (extraction quality)
  - Cluster-conditioned BTL scores (LLM judge, no query evaluation)
  - LOO Spearman ρ between surrogate predictions and BTL scores
  - Query cluster structure (SQL structural features)
  - Uncertainty estimates from surrogate models
  - Token budget and cost estimates

You NEVER use: ground-truth query results, true errors, macro-F1, reward tables.

--- TOOL GROUPS ---

Inspection tools (cheap, call freely):
- get_dataset_summary()            — corpus shape, token counts, schema
- get_probe_diagnostics({config_id}) — per-config extraction quality signals
- get_btl_rankings()               — global BTL scores
- get_surrogate_ranking({surrogate_name}) — proxy ranking for one surrogate
- compare_surrogates({surrogate_a, surrogate_b}) — ranking agreement

Clustering tools:
- choose_cluster_granularity({n_clusters}) — override auto cluster count (1-4)

Pipeline orchestration:
- run_stage1_characterization()    — characterize search space; returns recommendations
- run_surrogate_bakeoff()          — per-cluster LOO Spearman ρ for all surrogates
- probe_additional_configs({n_additional, reasoning}) — expand probe set
- stop_probing()                   — explicitly stop probe expansion

Risk control:
- choose_risk_level({level})       — "risk_neutral" | "risk_averse"

Terminal action:
- emit_routing_table({surrogate_name}) — run full pipeline and emit routing table

--- RECOMMENDED STRATEGY ---

1. Call get_dataset_summary() to understand workload shape and query types.
2. Call run_stage1_characterization() to see cluster structure and probe fidelity.
3. Decide cluster granularity: if surrogate_disagreement is high, keep multiple clusters.
   Call choose_cluster_granularity({n_clusters}) only if you want to override.
4. Check probe_fidelity.spearman_rho:
   - If rho is very low AND budget allows more probing: call probe_additional_configs.
   - If budget is tight or top configs are already distinguishable: call stop_probing.
5. Call run_surrogate_bakeoff() to see per-cluster LOO ρ.
6. Optionally call choose_risk_level({level}) if uncertainty is high.
7. Call emit_routing_table() to finalize the routing table and materialize databases.

--- ADAPTIVE PROBING DECISION ---

Before calling probe_additional_configs, reason about:
  - Are the top-2 configs for any cluster within each other's BTL uncertainty?
  - Do different surrogates disagree on which config is best for a cluster?
  - How much budget would probing cost vs how many materializations that forfeits?
Only probe more if the expected benefit outweighs the cost.

--- FORMAT ---

Each turn respond with JSON only:
{
  "thought": "brief reasoning referencing specific signals observed",
  "action": "<tool_name>",
  "action_input": {}
}

Examples:
{"thought": "Start by understanding workload.", "action": "get_dataset_summary", "action_input": {}}
{"thought": "Stage 1 shows 3 clusters: agg, join, filter. Disagreement is high.", "action": "run_surrogate_bakeoff", "action_input": {}}
{"thought": "BTL uncertainty for cluster 1 is high. Probing 4 more configs would cost 8000 tokens, leaving enough for 2 materializations.", "action": "probe_additional_configs", "action_input": {"n_additional": 4, "reasoning": "cluster 1 top-2 configs are within 1 std of each other"}}
{"thought": "Bakeoff complete. Per-cluster surrogates chosen. Budget permits 3 materializations. Emitting routing table.", "action": "emit_routing_table", "action_input": {}}

Do not output final answers outside the tool loop.
Do not access ground-truth error anywhere.
```

### `agent/react_agent.py`

1. Update `run_react_loop`:
   - Change terminal action detection from `action == "commit"` to `action in {"commit", "emit_routing_table"}`.
   - On terminal action, call `toolkit.emit_routing_table(...)` or `toolkit.commit(...)` respectively.
   - The returned `(surrogate, note, trace)` tuple is unchanged for backward compat.

2. Update `rule_based_select` fallback to also set `routing_table` via `deterministic_routing_fallback` from `stage3/routing_assignment.py`.

### Invariants
- `select_surrogate` external API is unchanged.
- `AgentToolkit.committed_surrogate` is still set (for any code that reads it).
- Max turns stays at 8 (from config).

---

## Task 11 — Evaluation: Routed Error as Primary Metric

### Files to modify
- `stage5/evaluation.py`
- `stage5/baselines.py`

### `stage5/evaluation.py`

#### New `EvaluationResult` fields

Add (do not remove existing fields):
```python
routing_table: dict[int, str] = field(default_factory=dict)
routed_error: float = 0.0          # PRIMARY: per-query routed execution error
oracle_min_error: float = 0.0      # SECONDARY: min over all selected configs
routing_regret: float = 0.0        # routed_error - oracle_min_error
```

Rename existing `error` field use to `oracle_min_error` in the oracle baseline path. For all non-oracle methods, compute `routed_error` as the primary metric.

#### New function: `evaluate_routing_table`

```python
def evaluate_routing_table(
    routing_table: dict[int, str],       # cluster_id -> config_id
    query_clusters,                       # QueryClusters (with labels)
    queries: list[dict],
    ground_truth_tables: dict[str, pd.DataFrame],
    databases_by_config: dict[str, dict[str, pd.DataFrame]],
    error_fn,                             # callable(query, db, gt) -> float
) -> float:
    """Compute routed SPP error.

    For each query:
      1. Get its cluster label.
      2. Look up config in routing_table[cluster_id].
      3. Execute query on databases_by_config[config_id].
      4. Compare result to ground_truth_tables.
      5. Accumulate error.

    Returns mean error across all queries.
    No oracle choice — each query uses exactly the routed database.
    """
```

This is the primary evaluation function. It must be called for **all methods** (full system, baselines), not just oracle.

#### Update existing `evaluate_method` or equivalent

For baselines that produce a `routing_table` (even a trivial one assigning all clusters to the same config), call `evaluate_routing_table`. For baselines that only produce a `selected_configs` list, build a trivial routing table (all clusters → best surrogate-scored config in selected set), then call `evaluate_routing_table`.

#### Reporting

In any summary or CSV output, place `routed_error` as the first column. Add a note `"oracle_min_error is reported as upper bound only"`.

### `stage5/baselines.py`

For each baseline function, add a `build_trivial_routing_table(selected_configs, query_clusters, probe_data)` helper call that assigns all clusters to the top-scored config in `selected_configs` (by global glass-box score). This makes all baselines report routed error rather than oracle-min.

### Invariants
- `oracle_min_error` is still computed and reported (for comparability with prior work).
- The evaluator must not choose among configs after seeing the result (no post-hoc oracle).
- Stage 5 is the only module that reads `ground_truth_tables`.

---

## Task 12 — Structured Audit Log

### Files to create
- `utils/audit.py`

### Files to modify
- `agent/react_agent.py`
- `pipeline/full_pipeline.py`

### New file: `utils/audit.py`

```python
"""Structured audit log for SPP-Agent runs.

Every agent run produces a complete, reproducible audit log.
The log is a dict that can be serialized to JSON.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class AuditLog:
    run_id: str                    # uuid4, set at start
    timestamp: str                 # ISO-8601
    token_budget_initial: int

    # Probe phase
    probe_config_ids: list[str] = field(default_factory=list)
    probe_expanded: bool = False
    probe_n_judge_pairs: int = 0
    probe_total_token_cost: float = 0.0

    # Cluster assignments
    n_clusters: int = 0
    cluster_types: dict[int, str] = field(default_factory=dict)
    cluster_sizes: dict[int, int] = field(default_factory=dict)
    cluster_labels: list[int] = field(default_factory=list)   # index-aligned with queries

    # BTL scores and uncertainty per cluster
    cluster_btl_scores: dict[int, dict[str, float]] = field(default_factory=dict)
    cluster_btl_uncertainty: dict[int, dict[str, float]] = field(default_factory=dict)

    # Surrogate validation per cluster
    cluster_surrogate_loo_rhos: dict[int, dict[str, float]] = field(default_factory=dict)
    cluster_selected_surrogates: dict[int, str] = field(default_factory=dict)

    # Agent actions (ordered)
    agent_actions: list[dict[str, Any]] = field(default_factory=list)
    # Each entry: {"turn": int, "thought": str, "action": str, "action_input": dict,
    #              "observation_summary": str, "timestamp": str}

    # Final outputs
    routing_table: dict[int, str] = field(default_factory=dict)   # cluster -> config
    selected_configs: list[str] = field(default_factory=list)
    risk_level: str = "risk_neutral"
    n_materializations: int = 0
    token_budget_spent: int = 0
    token_budget_remaining: int = 0

    # Fallback info
    used_fallback: bool = False
    fallback_reason: str = ""

    def log_action(self, turn: int, thought: str, action: str,
                   action_input: dict, observation: dict) -> None:
        summary = str(observation)[:300]
        self.agent_actions.append({
            "turn": turn,
            "thought": thought,
            "action": action,
            "action_input": action_input,
            "observation_summary": summary,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

Add `save_audit_log(log: AuditLog, path: Path) -> None` that writes JSON.

### `agent/react_agent.py`

In `run_react_loop`:
1. Create an `AuditLog` at the start of the loop.
2. After every tool call, call `audit_log.log_action(turn, thought, action, action_input, observation)`.
3. Populate `audit_log.routing_table`, `audit_log.selected_configs`, etc., from the terminal action result.
4. Save to `results/audit_<run_id>.json` at the end.
5. Return the `AuditLog` as a 4th element of the tuple (or attach to `trace`).

### `pipeline/full_pipeline.py`

In `run_spp_pipeline`, attach a reference to the audit log in `PipelineResult` (add field `audit_log: dict = field(default_factory=dict)`). Populate it from the running audit.

### Invariants
- Audit log is always written, even when fallback is used.
- Observation summaries are truncated at 300 chars to keep logs manageable.
- `run_id` uses `uuid.uuid4()`.

---

## Task 13 — Config and Requirements Updates

### Files to modify
- `config/defaults.yaml`
- `requirements.txt`

### `config/defaults.yaml`

Add under `stage3:`:
```yaml
stage3:
  risk_level: "risk_neutral"          # default; agent can override
  risk_lambda: 0.5                    # uncertainty penalty weight
  routing_assignment:
    sort_clusters_by_size: true       # largest cluster gets first config pick
```

Remove the old `algorithms:` list under `stage3` (greedy, bayesian_opt, etc.) since routing_assignment replaces them. Keep `bo_n_trials` and `hyperband_eta` commented out for reference.

Add under `agent:`:
```yaml
agent:
  max_turns: 10          # increased from 8 (new agent has more actions)
  default_risk_level: "risk_neutral"
```

Update `token_budget` default:
```yaml
token_budget: 500000    # unchanged
```

Add under `stage2:`:
```yaml
stage2:
  per_cluster_bakeoff: true    # enable per-cluster surrogate selection
```

### `requirements.txt`

Add (if not already present):
```
scipy>=1.10       # already present — confirms kendalltau available
uuid              # stdlib, no pip needed
```

No new third-party packages are required by this redesign.

---

## Cross-Cutting Invariants (Apply Everywhere)

1. **No ground-truth in deployment path.** Any function that imports from `stage5/` must not be called from `optimizer/probing.py`, `pipeline/full_pipeline.py`, `agent/`, `stage1/`, `stage2/`, `stage3/`, `stage4/`, `surrogates/`, `judge/`, or `diagnostics/`.

2. **Backward compatibility for cached probe data.** `ProbeData` new fields use `field(default_factory=...)`. Old JSON caches deserialized via `AgentToolkit.from_cache` will produce empty dicts for new cluster-aware fields. All downstream code must handle empty dicts gracefully with `or {}` fallbacks.

3. **Seed propagation.** Every stochastic operation (KMeans, bootstrap BTL, surrogate fitting) must accept and use a `seed` or `random_state` parameter derived from `cfg["experiment"]["seed"]` (currently `42`).

4. **Logging.** Every new function must call `logger = setup_logger("spp.<module>")` and emit at least one `logger.info` call describing its inputs and outputs.

5. **No circular imports.** Import hierarchy:
   ```
   utils/ ← diagnostics/ ← optimizer/ ← pipeline/ ← stage1-4/ ← agent/
   ```
   `stage5/` sits outside this hierarchy and may import from anywhere. Nothing else imports from `stage5/`.

6. **Type annotations.** All new function signatures must have complete Python type annotations. Use `from __future__ import annotations` at the top of every new file.

---

## Acceptance Tests (Run After All Tasks)

These are smoke-test checks that can be run without an LLM (use `--offline` flag where supported):

### T1 — Config space size
```python
from optimizer.config_space import generate_config_space
assert len(generate_config_space()) == 288
from optimizer.config_space import encode_config_features
cfg = generate_config_space()[0]
import numpy as np
assert encode_config_features(cfg).shape == (17,)
```

### T2 — Cluster workload
```python
from stage4.query_clustering import cluster_workload
queries = [{"sql_query": "SELECT COUNT(*) FROM player GROUP BY team"}] * 5
qc = cluster_workload(queries)
assert 1 <= qc.n_clusters <= 4
assert len(qc.labels) == 5
assert all(t in {"aggregation", "join", "filter", "mixed"} for t in qc.cluster_types.values())
```

### T3 — Cluster glass-box
```python
from diagnostics.cluster_glass_box import compute_cluster_glass_box
tier1 = {"schema_column_coverage": 0.8, "missing_value_rate": 0.1,
         "duplicate_candidate_rate": 0.05, "entity_ambiguity_score": 0.1,
         "json_parse_error_rate": 0.0, "extraction_refusal_or_empty_rate": 0.0,
         "unit_parse_success_rate": 1.0, "numeric_type_success_rate": 0.9}
for ct in ["aggregation", "join", "filter", "mixed"]:
    score = compute_cluster_glass_box(tier1, ct)
    assert 0.0 <= score <= 1.0
```

### T4 — BTL with uncertainty
```python
from judge.btl import fit_btl_with_uncertainty
comps = [{"winner": "A", "loser": "B"}, {"winner": "A", "loser": "C"},
         {"winner": "B", "loser": "C"}]
result = fit_btl_with_uncertainty(comps, all_config_ids=["A","B","C"], n_bootstrap=10)
assert set(result.keys()) == {"A", "B", "C"}
assert all(isinstance(v, tuple) and len(v) == 2 for v in result.values())
```

### T5 — Surrogate uncertainty
```python
from optimizer.probing import ProbeData
# (construct minimal ProbeData with 4 configs, glass_box_composites, btl_scores)
from surrogates.registry import build_surrogate
for name in ["direct_probe_ranking", "rf_proxy_glass", "gp_proxy_glass"]:
    s = build_surrogate(name)
    s.fit(probe_data)
    score, unc = s.score_with_uncertainty(probe_data.config_ids[0])
    assert isinstance(score, float)
    assert isinstance(unc, float) and unc >= 0.0
```

### T6 — Stage 1G no ground truth
```python
from stage1.analysis_1g import analyze_routing_gap
# confirm it does not raise even when reward_rows=None
result = analyze_routing_gap(probe_data, thresholds=tc, reward_rows=None)
assert "recommendation" in result
assert "mean_disagreement" in result
# confirm reward_rows=[{"true_spp_error": 0}] is ignored
result2 = analyze_routing_gap(probe_data, thresholds=tc,
                              reward_rows=[{"true_spp_error": 0.1}])
assert result["mean_disagreement"] == result2["mean_disagreement"]
```

### T7 — Routing table structure
```python
from stage3.routing_assignment import assign_configs_to_clusters, RoutingTable
# (use minimal fixtures)
rt = assign_configs_to_clusters(...)
assert isinstance(rt, RoutingTable)
assert set(rt.cluster_to_config.keys()) == set(range(qc.n_clusters))
assert len(rt.selected_configs) == len(set(rt.cluster_to_config.values()))
assert rt.n_materializations == len(rt.selected_configs)
```

### T8 — Audit log written
```python
from utils.audit import AuditLog
import uuid
log = AuditLog(run_id=str(uuid.uuid4()), timestamp="2026-01-01T00:00:00Z",
               token_budget_initial=500000)
log.log_action(1, "test thought", "get_dataset_summary", {}, {"result": "ok"})
d = log.to_dict()
assert "agent_actions" in d
assert d["agent_actions"][0]["action"] == "get_dataset_summary"
```

### T9 — Offline smoke test
```bash
python experiments/stage1_characterize.py --offline
python experiments/stage5_evaluation.py --offline
```
Both must complete without `ImportError`, `AttributeError`, or unhandled `KeyError`.

---

## File Change Summary

| File | Action |
|---|---|
| `optimizer/config_space.py` | Modify |
| `config/defaults.yaml` | Modify |
| `stage4/query_clustering.py` | Modify (add functions/dataclass) |
| `pipeline/full_pipeline.py` | Modify |
| `diagnostics/cluster_glass_box.py` | **Create** |
| `optimizer/probing.py` | Modify |
| `judge/pairwise.py` | Modify |
| `judge/btl.py` | Modify |
| `surrogates/base.py` | Modify |
| `surrogates/*.py` (all 9) | Modify |
| `stage2/surrogate_comparison.py` | Modify |
| `thresholds/optimizer.py` | Modify |
| `thresholds/schema.py` | Modify |
| `stage3/routing_assignment.py` | **Create** |
| `stage1/analysis_1g.py` | Modify (full rewrite of function body) |
| `stage1/characterizer.py` | Modify |
| `agent/tools.py` | Modify |
| `agent/prompts/react_system.txt` | Modify (full rewrite) |
| `agent/react_agent.py` | Modify |
| `stage5/evaluation.py` | Modify |
| `stage5/baselines.py` | Modify |
| `utils/audit.py` | **Create** |
| `requirements.txt` | Modify (minor) |

**New files: 3** (`cluster_glass_box.py`, `routing_assignment.py`, `audit.py`)  
**Modified files: 21**  
**Deleted files: 0**
