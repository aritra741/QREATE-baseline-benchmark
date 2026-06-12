# SPP-Agent Implementation Details

This document provides a technical deep-dive into the specific implementation of the Surrogate-based Pipeline Selection (SPP) agent.

## 1. Query Clustering (`stage4/query_clustering.py`)

The pipeline begins by analyzing the query workload to group similar queries.

### Structural Feature Extraction
Each query is converted into a **9-dimensional binary feature vector** based on SQL keywords:
- `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` (Dimensions 0-4)
- `GROUP BY` (Dimension 5)
- `JOIN` (Dimension 6)
- `WHERE` (Dimension 7)
- `TEMPORAL` (Dimension 8 - e.g., `date`, `year`, `birth_date`)

### Automatic Cluster Selection ($k$)
The number of clusters $k$ (between 2 and 4) is chosen using the **Elbow Method** on KMeans inertia:
- KMeans is run for $k \in [2, 4]$.
- The "inertia drop ratio" $(I_k - I_{k+1}) / I_k$ is calculated.
- The system picks the $k$ where the ratio first drops below **0.2**.

### Cluster Type Assignment
Clusters are typed based on their centroid's feature weights:
- **`join`**: if `JOIN` weight > 0.4.
- **`aggregation`**: if any `AGG` weight (dims 0-4) > 0.3.
- **`filter`**: if `WHERE` weight > 0.4.
- **`mixed`**: default fallback.

---

## 2. Cluster-Conditioned Glass-Box Signals (`diagnostics/cluster_glass_box.py`)

Extraction quality is measured using "glass-box" signals from the synthesized databases. These signals are weighted differently depending on the **cluster type**:

| Signal | Aggregation | Join | Filter | Mixed |
| :--- | :---: | :---: | :---: | :---: |
| `schema_column_coverage` | 10% | 15% | 30% | 12.5% |
| `missing_value_rate_inv` | 20% | 10% | 15% | 12.5% |
| `duplicate_candidate_rate_inv` | 5% | 25% | 10% | 12.5% |
| `entity_ambiguity_score_inv` | 5% | 25% | 10% | 12.5% |
| `json_parse_error_rate_inv` | 10% | 10% | 10% | 12.5% |
| `unit_parse_success_rate` | 25% | 5% | 5% | 12.5% |
| `numeric_type_success_rate` | 20% | 5% | 15% | 12.5% |

*Note: `_inv` signals are calculated as `1.0 - raw_signal`.*

---

## 3. LLM Judging & BTL Modeling (`judge/btl.py`)

### Pairwise Comparison
An LLM judge compares two synthesized databases (Config A vs Config B) for a specific query cluster. The prompt is customized by cluster type (e.g., "Which database is better for these *aggregation* queries?").

### Bradley-Terry-Luce (BTL) Fitting
- **Point Estimates**: Fitted using **Minorization-Maximization (MM) updates** to converge on quality scores for each configuration.
- **Uncertainty Estimation**: The system uses **Bootstrapping** (default 50 iterations). It resamples the judge's comparisons with replacement and re-fits the BTL model to calculate the mean and standard deviation ($\sigma$) of the scores.

---

## 4. Routing & Assignment (`stage3/routing_assignment.py`)

The system solves a joint selection and routing problem to stay within the token budget.

### The Greedy Assignment Algorithm
1.  **Sort Clusters**: Clusters are processed in order of **size** (number of queries), ensuring larger clusters get priority.
2.  **Adjusted Scoring**: If the agent chooses `risk_averse`, the score for config $c$ on cluster $i$ is:
    $$Score_{i,c} = \text{PredictedQuality}_{i,c} - \lambda \cdot \text{Uncertainty}_{i,c}$$
    (where $\lambda = 0.5$ by default).
3.  **Materialization Loop**:
    - For each cluster, try the top-ranked config.
    - If the config is already "materialized" (selected by a previous cluster), assign it for free.
    - If not, check if the **marginal token cost** fits in the remaining budget.
    - If no new configs are affordable, fall back to the best already-materialized config for that cluster.

---

## 5. ReAct Agent Action Space (`agent/tools.py`)

 The ReAct agent orchestrates the pipeline using a specialized toolset:

- **`run_stage1_characterization`**: Analyzes the search space and provides recommendations (e.g., "use_routing=True").
- **`run_surrogate_bakeoff`**: Runs Leave-One-Out cross-validation for all surrogates **per cluster** to find the best predictor.
- **`choose_cluster_granularity`**: Allows the agent to force a specific number of clusters (1-4).
- **`probe_additional_configs`**: Expands the probe set (up to 8 more) if signals are too noisy.
- **`choose_risk_level`**: Toggles between `risk_neutral` and `risk_averse`.
- **`emit_routing_table`**: The terminal action that finalizes the routing and materializes the databases.

---

## 6. Implementation Invariants

- **Ground-Truth Firewall**: No deployment code (anything outside `stage5/`) is permitted to import or read `true_errors`, `reward_rows`, or ground-truth tables.
- **Deteriminism**: All stochastic components (KMeans, BTL bootstrap, Surrogate fitting) use a fixed seed (default 42) propagated from the global configuration.
- **Backward Compatibility**: The `AgentToolkit` can reload from legacy JSON caches by mapping old "global" signals to the new cluster-aware structures.
