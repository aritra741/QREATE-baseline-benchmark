# SPP-Agent: Full Workflow Documentation

## Table of Contents

1. [What Problem This Solves](#1-what-problem-this-solves)
2. [Core Concepts](#2-core-concepts)
3. [Architecture Overview](#3-architecture-overview)
4. [The Configuration Space](#4-the-configuration-space)
5. [The Probe Run](#5-the-probe-run)
6. [Deployment-Visible Signals](#6-deployment-visible-signals)
7. [Stage 1: Search Space Characterization](#7-stage-1-search-space-characterization)
8. [Stage 2: Surrogate Bakeoff](#8-stage-2-surrogate-bakeoff)
9. [Stage 3: Selection Algorithm](#9-stage-3-selection-algorithm)
10. [Stage 4: Architecture Decisions](#10-stage-4-architecture-decisions)
11. [Stage 5: Evaluation](#11-stage-5-evaluation)
12. [The ReAct Agent](#12-the-react-agent)
13. [Threshold Optimization](#13-threshold-optimization)
14. [How Stages Connect](#14-how-stages-connect)
15. [What the Agent Is Not Allowed to See](#15-what-the-agent-is-not-allowed-to-see)
16. [End-to-End Data Flow](#16-end-to-end-data-flow)
17. [Running the System](#17-running-the-system)

---

## 1. What Problem This Solves

You have a corpus of **unstructured text documents** (e.g., player biography articles, legal filings, financial reports) and a set of **SQL aggregation queries** (e.g., `SELECT AVG(salary) FROM player GROUP BY team`). You want to answer those queries accurately.

To do that you need to:
1. **Extract** structured tuples from the text (using an LLM)
2. **Populate** a relational database from those tuples
3. **Run** the SQL queries against that database

The catch: there is no single "correct" way to do step 2. There are choices to make about how to resolve entity references, normalize strings, parse numeric units, and handle missing values. Different combinations of these choices produce databases of different quality, and the best combination depends on the specific corpus and query workload.

There are **16 possible population configurations** (the Cartesian product of 4 binary/categorical choices). Evaluating all 16 requires running the SQL queries against each populated database and comparing results to ground truth — that is expensive.

**The SPP agent's job:** Given a new corpus and query workload, select the best 1–2 configurations *without* evaluating all 16 against ground truth. It does this using only cheap, deployment-visible proxy signals collected during a brief probe run.

---

## 2. Core Concepts

### Population Config

A set of four choices that determine how extracted tuples are cleaned before loading into the database:

| Axis | Options | What it controls |
|---|---|---|
| `er_strategy` | `embedding_0.7`, `embedding_0.9` | Entity resolution: how aggressively to merge similar entity names using cosine similarity of sentence embeddings |
| `norm_strategy` | `dictionary`, `llm` | String normalization: rule-based (lowercase, collapse whitespace) vs LLM-assisted canonical forms |
| `unit_strategy` | `none`, `unit` | Numeric unit stripping: parse "$1.5M" → 1500000 or leave as-is |
| `miss_strategy` | `drop`, `mean` | Missing value handling: drop rows with nulls or fill with column mean |

Config IDs are encoded as pipe-delimited strings, e.g.:
```
er=embedding_0.7|norm=dictionary|unit=none|miss=drop
```

### SPP Error

The true measure of config quality:

```
SPP_error(configs) = (1/|Q|) Σ_q  min_{c ∈ configs} Err(q, c)
```

Where `Err(q, c)` = 1 − macro_F1 of query `q` executed on the database produced by config `c` compared to ground truth.

Lower is better. This requires ground truth and is only computed during **offline evaluation** (Stage 5). The agent never sees it.

### Surrogate

A cheap proxy function that scores configs without running query evaluation. A surrogate takes probe-visible signals (extraction quality, BTL rankings) as input and outputs a predicted ranking of configs. The best surrogate for a given workload is the one whose ranking best correlates with the true SPP error ranking.

---

## 3. Architecture Overview

```
New corpus + SQL queries
         │
         ▼
 ┌───────────────┐
 │  Probe Run    │  Extract docs with LLM → apply K configs → compute signals → run LLM judge
 └───────┬───────┘
         │  ProbeData (glass-box scores, BTL scores, tier1 signals)
         │  ← All deployment-visible. No query evaluation. ←
         ▼
 ┌───────────────────────────────────────────┐
 │  ReAct Agent  (orchestrates Stages 1–4)  │
 │                                           │
 │  Stage 1: Characterize search space       │
 │     ↓ recommendations (flags)             │
 │  Stage 2: Surrogate bakeoff (LOO ρ)       │
 │     ↓ best surrogate name                 │
 │  Stage 3: Selection algorithm             │
 │     ↓ selected config IDs                 │
 │  Stage 4: Architecture decisions          │
 └───────────────┬───────────────────────────┘
                 │  selected_configs (1–2 config IDs)
                 ▼
 ┌───────────────────────┐
 │  Execute SQL queries  │  ← ground truth first used here
 │  Measure SPP error    │
 └───────────────────────┘
```

The clean separation: everything above "Execute SQL queries" operates with **no ground-truth access**. Evaluation is only used to measure outcomes after decisions are made.

---

## 4. The Configuration Space

Defined in `optimizer/config_space.py`. The full space has 2×2×2×2 = **16 configs**.

Each config is one-hot encoded as a 8-dimensional binary feature vector for use in surrogate models:

```
[er=embedding_0.7, er=embedding_0.9,
 norm=dictionary, norm=llm,
 unit=none, unit=unit,
 miss=drop, miss=mean]
```

Only K=8 configs (by default) are actually probed. The surrogates generalize to all 16.

---

## 5. The Probe Run

Defined in `optimizer/probing.py`. This is the only LLM-expensive step at deployment time.

### What happens

**Step 1 — Document extraction (once, shared)**
A random sample of the corpus (20% by default, minimum 20 docs) is extracted using the extraction LLM (`Qwen2.5-14B-Instruct` or `deepseek-v4-flash`). The LLM reads each document and returns structured JSON with one row per entity per table. This extraction is done *once* and shared across all probed configs.

**Step 2 — Population (per config)**
For each of the K probe configs, the extracted tuples are passed through that config's cleaning pipeline (ER merging, normalization, unit parsing, missing value handling). This produces K different databases.

**Step 3 — Tier 1 diagnostics (per config)**
For each populated database, a set of deployment-visible quality metrics is computed without running SQL against ground truth:
- `schema_column_coverage` — what fraction of schema columns have at least one value
- `missing_value_rate` — what fraction of cells are null/empty
- `duplicate_candidate_rate` — estimated fraction of duplicate rows
- `entity_ambiguity_score` — how many ER merges were ambiguous
- `json_parse_error_rate` — what fraction of LLM extraction responses failed to parse
- `extraction_refusal_or_empty_rate` — what fraction of docs produced no tuples
- `unit_parse_success_rate` — what fraction of numeric cells parsed successfully
- `numeric_type_success_rate` — what fraction of query-referenced numeric columns are castable

These are combined into a single **glass-box composite score**:
```
glass_box = mean([
    schema_column_coverage,
    1 - missing_value_rate,
    1 - duplicate_candidate_rate,
    1 - entity_ambiguity_score,
    1 - json_parse_error_rate,
    1 - extraction_refusal_or_empty_rate,
    unit_parse_success_rate,
    numeric_type_success_rate,
])
```

Higher = better data quality.

**Step 4 — Pairwise LLM judge (cross-config)**
For J pairs of configs (selected by a diversity-maximizing algorithm), the judge LLM is shown:
- The schema description
- A sample of SQL queries from the workload
- Up to 10 rows from each database
- The config settings for each database

It responds with `{"winner": "a"|"b"|"tie", "reasoning": "..."}`. The judge sees query *structure* but not query *answers*. Position is randomly swapped to prevent order bias.

**Step 5 — BTL scoring**
All pairwise comparison outcomes are fed into a **Bradley-Terry-Luce** model fitted via MM updates. This produces a single BTL score per probed config — a continuous measure of how often a config wins comparisons. Configs are ranked by BTL score.

### ProbeData output

```python
ProbeData(
    config_ids: list[str],          # K probed config IDs
    configs: dict[str, PopulationConfig],
    tier1_signals: dict[str, dict], # per-config diagnostics
    glass_box_composites: dict[str, float],  # composite quality score
    pairwise_comparisons: list[dict],        # LLM judge outcomes
    btl_scores: dict[str, float],   # BTL model output
    databases: dict[str, DataFrame], # populated databases (for judge)
    total_cost: float,              # total token cost
    true_errors: dict = {},         # ALWAYS EMPTY at deployment time
)
```

`true_errors` is explicitly kept empty during deployment. It is only populated during offline research evaluation (Stage 5).

---

## 6. Deployment-Visible Signals

These are the only inputs the agent and optimizer are allowed to use:

| Signal | Source | What it measures |
|---|---|---|
| `glass_box_composite` | Tier 1 diagnostics | Overall extraction + cleaning quality for a config |
| `btl_score` | Pairwise LLM judge + BTL model | How often a config produces a "better" database than its peers |
| `glass_box_spread` | Range of glass_box scores | How much configs differ in quality — high spread = clearer winner |
| `btl_spread` | Range of BTL scores | How discriminative the judge was |
| `tier1_signals` | Per-config diagnostics | Granular breakdown (missing rate, numeric castability, etc.) |
| LOO Spearman ρ | Computed by optimizer | How well each surrogate's rankings generalize (leave-one-out cross-val on BTL) |
| SQL structural features | Parsed from queries | Presence of COUNT/SUM/AVG/JOIN/WHERE/temporal keywords per query |
| Schema column types | Schema object | Which columns are int/float/str |
| Token counts | Estimated from docs | Document size distribution |

**What is not allowed:** true query error, macro-F1 against ground truth tables, or any signal derived from running SQL against ground-truth data.

---

## 7. Stage 1: Search Space Characterization

Defined in `stage1/`. Runs 8 independent analyses and produces a `Stage1Report` with boolean recommendation flags.

### 1A — Diminishing Returns
**Question:** Does probing more configs keep improving our understanding, or do gains saturate quickly?

**Method:** Sort configs by glass-box score. Compute the cumulative fraction of the score range captured at each k. Find the smallest k where this fraction exceeds `1 - 1/diminishing_returns_k`.

**Output flag:** `density_greedy_viable` — if True, greedy ranking is good enough; if False, a more thorough search strategy is needed.

### 1B — Error Surface Smoothness
**Question:** Is the quality landscape smooth (one clear winner) or rugged (many local optima)?

**Method:** Build a Hamming-1 neighbor graph over probed configs (each config is connected to configs differing in exactly one axis). Count local minima — configs whose glass-box score is strictly lower than all their Hamming-1 neighbors.

**Output flag:** `smooth` (internal) → fed to Stage 3. If rugged (local_minima > 1), Stage 3 uses Bayesian optimization instead of greedy search.

### 1C — Module Ordering
**Question:** Does the order in which the four axes are applied (ER → norm → unit → miss) matter for the ranking?

**Method:** For each axis, compute variance of glass-box scores grouped by that axis's value. If one axis dominates, it should be applied first.

**Output:** `ordering_sensitive` flag and per-axis effect sizes.

### 1D — Sparse Interactions
**Question:** Are config quality scores driven mainly by individual axis choices (additive), or by specific *combinations* of axes (interactions)?

**Method:** Fit a linear model on one-hot features (main effects only), compute R². Then fit on all pairwise feature products, compute R². The interaction ratio = fraction of total variance explained by interaction terms beyond main effects.

**Output flag:** `use_nonlinear` — if True (interaction ratio > `ThresholdConfig.interaction_ratio`), Stage 2 will deprioritize linear surrogate and prefer GBDT/GP.

### 1E — Probe Fidelity
**Question:** How well do our cheap probe signals (glass-box, BTL) correlate with what would actually be the best config for answering queries?

**Method:** At deployment time (when we have no ground truth), this uses Spearman ρ between glass-box scores and BTL scores as a consistency measure. During offline validation, it can also compare against true errors.

**Key threshold usage:**
- If `spearman_rho >= ThresholdConfig.rho_viable` → probe is trustworthy, proceed with surrogate
- If `ThresholdConfig.rho_bakeoff <= rho < rho_viable` → probe has moderate signal, run surrogate bakeoff
- If `rho < rho_bakeoff` → probe signal is weak, trigger adaptive probing (probe more configs)

**Output flag:** `probe_viable` — gates whether BTL-based surrogates are trusted in Stage 2.

### 1F — Clustering Validity
**Question:** Do the SQL queries in this workload cluster into meaningful groups that might prefer different configs?

**Method:** Extract a 9-dimensional binary feature vector per query (presence of COUNT, SUM, AVG, MIN, MAX, GROUP BY, JOIN, WHERE, temporal keywords). Run KMeans clustering. If true error labels were available (offline only), compute purity. Otherwise report cluster structure only.

**Output flag:** `use_clustering` — gates whether query clustering is activated in Stage 4.

### 1G — Routing Gap
**Question:** How much does choosing the right surrogate matter vs. just using a simple heuristic rule?

**Method:** Compare the error of oracle routing (best surrogate per reward-table row) vs. practical routing (heuristic: if btl_spread > 0 use llm_judge_btl, else if glass_spread > threshold use rf_proxy_glass, else use direct_probe_ranking). The gap is the mean difference in error.

**Output flag:** `use_routing` — if gap > `ThresholdConfig.routing_gap`, the agent should invest in proper routing. Otherwise the heuristic is good enough.

### 1H — Schema Rank Stability
**Question:** Does the surrogate ranking of configs change depending on which parts of the schema we focus on (all columns vs numeric-only vs entity-name-only)?

**Method:** Create three schema views: full schema, numeric-only columns (int/float), entity-only columns (name/team/city etc.). Re-score configs using glass-box signals weighted toward each view. Compute Spearman ρ between full-schema ranking and each variant.

**Output flag:** `schema_first` — if rankings are unstable across schema variants (min ρ < `ThresholdConfig.schema_rank_rho`), schema structure should be treated as a first-class routing signal. Otherwise a flat hierarchy is sufficient.

---

## 8. Stage 2: Surrogate Bakeoff

Defined in `stage2/surrogate_comparison.py` and `thresholds/optimizer.py`.

### The 9 Surrogate Models

| Name | Approach | Strength |
|---|---|---|
| `random_ranking` | Random shuffle | Baseline only |
| `direct_probe_ranking` | Glass-box composite score directly | No fitting needed; fast fallback |
| `glass_box_proxy` | Nearest-neighbor by Hamming distance in config feature space, using glass-box scores | Generalizes to unprobed configs |
| `llm_judge_btl` | Nearest-neighbor using BTL scores | Best when judge has clear signal |
| `linear_proxy_glass` | Linear regression: config one-hot features → glass-box score | Interpretable; good when effects are additive |
| `rf_proxy_glass` | Random Forest: config features → glass-box score | Handles moderate interactions |
| `gbdt_proxy_glass` | Gradient Boosted Trees: config features → glass-box score | Handles interactions, regularized |
| `gp_proxy_glass` | Gaussian Process: RBF kernel, config features → glass-box score | Uncertainty-aware; triggers acquisition-based search |
| `tpe_proxy` | Blended: 0.5 × normalized glass-box + 0.5 × normalized BTL, nearest-neighbor fallback | Combines both signal types |

### How the bakeoff works

**Leave-One-Out (LOO) cross-validation**, using only deployment-visible signals:

For each surrogate:
1. For each probed config `c` (held out):
   - Remove `c` from probe_data
   - Fit the surrogate on the remaining K−1 configs
   - Predict a score for `c`
2. Collect predicted scores for all K held-out configs
3. Compute **Spearman ρ** between predicted scores and BTL scores

BTL scores are used as the reference (not true error) because they are deployment-visible (produced by the LLM judge, not by query evaluation).

The result is a LOO Spearman ρ for each surrogate — a deployment-visible estimate of "how much does this surrogate's ranking generalize?"

### How Stage 1 gates Stage 2

Stage 1 recommendations modify which surrogates are considered:

- `probe_viable = False` → `llm_judge_btl` is excluded (BTL signal is too weak to trust)
- `use_nonlinear = True` → `linear_proxy_glass` is moved to the back of the candidate list (nonlinear models preferred)

After computing LOO ρ for all candidates, the `ThresholdConfig` thresholds determine routing:
- `rho >= rho_viable` → surrogate is trustworthy, pick the one with highest ρ
- `rho_bakeoff <= rho < rho_viable` → proceed but keep bakeoff candidates in mind
- `rho < rho_bakeoff` → signal too weak; in the full pipeline, this triggers adaptive probing

An additional check: if `linear_proxy_glass` LOO ρ is within `linear_tolerance` fraction of the best surrogate's ρ, and `use_nonlinear` is False, prefer linear for interpretability.

If the best surrogate is `gp_proxy_glass` or `tpe_proxy`, a flag `use_acquisition_search = True` is set, which is passed to Stage 3.

---

## 9. Stage 3: Selection Algorithm

Defined in `stage3/`. Given the fitted surrogate, how do we select the best `budget` configs from all 16 candidates?

### The 5 Algorithms

**Greedy** (`stage3/greedy` via `optimizer/ranking_select.py`)
Score all 16 configs with the surrogate, pick top `budget`. O(16) surrogate evaluations.

**Bayesian Optimization** (`stage3/bayesian_opt.py`)
Use Optuna TPE sampler. Each trial selects `budget` configs and scores them with the surrogate. Optuna learns which config combinations score high. Best subset returned after N trials.

**Hyperband** (`stage3/hyperband.py`)
Successive halving: start with all 16, score with surrogate, keep top 1/η fraction, repeat until `budget` configs remain. Good when the surrogate is cheap but you want to avoid evaluating poor configs.

**Coordinate Descent** (`stage3/coord_descent.py`)
Start from the probed config with the highest surrogate score. Iteratively flip one axis at a time (ER, norm, unit, miss); move to neighbor if it improves surrogate score. Repeat until no improvement. Good for smooth landscapes.

**ILP** (`stage3/ilp_select.py`)
LP relaxation of 0-1 knapsack: maximize sum of surrogate scores subject to selecting exactly `budget` configs. Solved via `scipy.optimize.linprog`. Rounds fractional solution by taking top-budget configs by LP weight.

### How Stage 1 and Stage 2 gate Stage 3

The algorithm is chosen automatically based on upstream signals:

```
if use_acquisition_search (Stage 2 picked GP/TPE)
    OR error_surface is rugged (Stage 1B found local minima > 1):
    → use Bayesian Optimization

elif density_greedy_viable (Stage 1A says gains saturate early):
    → use Greedy

else:
    → use Coordinate Descent
```

This means the algorithm choice is data-driven: a complex, multi-modal landscape triggers BO, a well-behaved landscape uses greedy or coord descent.

---

## 10. Stage 4: Architecture Decisions

Defined in `stage4/`. Stage 4 is advisory — it tells the system which components are worth keeping based on Stage 1's analysis.

### Active Components (gated by Stage 1)

| Component | Active when | What it does |
|---|---|---|
| `surrogate` | Always | Core component; never ablated |
| `extraction_reuse` | Always | Sharing extraction across configs (default) |
| `recalibration` | Always | BTL recalibration after probing |
| `routing` | Stage 1G `use_routing=True` | Schema/query feature routing to pick surrogate |
| `flat_vs_hier` | Always | Flat vs hierarchical config search |
| `query_clustering` | Stage 1F `use_clustering=True` | Group queries by SQL structure for per-cluster optimization |
| `schema_pruning` | Stage 1H `schema_first=True` | Prune schema to relevant columns before probing |
| `cluster_refinement` | Stage 1F `use_clustering=True` | Split/merge query clusters after initial formation |

If Stage 1 says a component is not warranted, Stage 4 doesn't even consider it — this avoids wasting ablation budget on components that are provably unnecessary for this workload.

### Schema Pruning Strategies (when active)

- **Compat pruning**: Keep only columns referenced in at least one query
- **Probe pruning**: Keep columns from tables with above-median glass-box coverage
- **Pareto pruning**: Keep columns on the Pareto frontier of (query coverage × probe quality)

### Query Clustering Strategies (when active)

- **Structural clustering**: KMeans on SQL structural features (9-dim binary)
- **Error-profile clustering** (offline only): KMeans on per-query error vectors across configs
- **Refinement**: Split the largest cluster, then optionally merge the two most similar

---

## 11. Stage 5: Evaluation

Defined in `stage5/`. This is the only stage with ground-truth access. It measures the actual SPP error of the selected configs.

### What is evaluated

The full system (stages 1–4 pipeline) vs 5 baselines:

| Method | What it does |
|---|---|
| `full_system` | Pipeline output: configs selected by Stage 1→4 |
| `default` | First config in canonical alphabetical order |
| `single_best` | Best surrogate (from Stage 2) used with greedy, same as Phase 1 |
| `squid` | Nearest historical workload match; reuse its best config |
| `random` | Random budget-matched selection |
| `ilp` | ILP selection with best surrogate |
| `oracle` | Cheats: picks surrogate with lowest true error (from reward table) |

### Metrics reported

- **Average SPP error** across budget levels
- **Average regret** = method error − oracle error (lower is better; 0 = matches oracle)
- **Oracle match rate** = fraction of budget×slice combinations where method picks same surrogate as oracle
- **Worst-case regret** = max regret across budget levels
- **Error-vs-budget curve** = how error decreases as budget increases
- **Cache hit rate** = fraction of selected configs that were directly probed (no extrapolation needed)
- **Token cost** = total LLM tokens consumed by the pipeline
- **Sensitivity** = how much results change when probe count, sample fraction, or budget vary

---

## 12. The ReAct Agent

Defined in `agent/react_agent.py` and `agent/tools.py`.

The agent is an LLM (Qwen2.5-32B or DeepSeek-V4-Flash) running in a **ReAct loop** — a structured alternation of:
1. **Thought**: reasoning about what was observed
2. **Action**: calling one tool and observing the result
3. Repeat until a terminal action is called

### The agent's decision flow

```
Turn 1:  get_dataset_summary()
         → learn workload shape: num docs, token distribution, query types, schema

Turn 2:  run_stage1_characterization()
         → get recommendations: probe_viable, use_nonlinear, use_clustering, etc.
         → get probe_fidelity.spearman_rho

If rho < rho_bakeoff:
Turn 3:  probe_additional_configs({"n_additional": 4})
         → cheaply probe 4 more configs via LLM extraction + judge
Turn 4:  run_stage1_characterization()  ← re-run with expanded probe

Turn N:  run_surrogate_bakeoff()
         → see LOO ρ for all surrogates
         → see which are viable/bakeoff/below threshold

Turn N+1: run_pipeline_and_select({"budget": 1})
         → this single tool call runs the connected Stage 1→2→3→4 pipeline
         → returns selected config IDs, best surrogate, algorithm, components

(Optional) commit({"surrogate_name": "..."})
         → locks in surrogate selection if agent wants to override pipeline
```

### What choices the agent makes

The agent is not just a black-box button-presser. It reasons step-by-step:

1. **Probe adequacy**: Looking at Stage 1 fidelity ρ, it decides whether the current probe data is good enough or whether to expand it. This is adaptive — not every workload needs more probing.

2. **Signal interpretation**: It reads the Stage 1 report and understands what each recommendation means. If `use_nonlinear=True`, it knows to interpret the bakeoff results with a preference for GBDT/GP. If `probe_viable=False`, it knows not to trust BTL-based surrogates.

3. **Surrogate trust**: In `run_surrogate_bakeoff()`, the agent sees concrete LOO ρ numbers per surrogate. It can reason about whether the viable threshold is too high for this dataset, or whether two surrogates are close enough that the linear one should be preferred for interpretability.

4. **Pipeline trigger**: The agent decides when it has gathered enough evidence to trust the pipeline. If all Stage 1 signals are clear and the bakeoff shows a strong winner, it calls `run_pipeline_and_select` confidently. If signals are ambiguous, it may inspect probe diagnostics for specific configs first.

5. **Fallback reasoning**: If the LLM call fails or the agent doesn't commit in time, `rule_based_select` provides a deterministic fallback based on BTL/glass-box spread.

### Fallback hierarchy

```
ReAct agent LLM call succeeds and commits → use committed surrogate
ReAct agent LLM call fails → rule_based_select:
    if btl_spread > 0     → llm_judge_btl
    elif glass_spread > 0.01 → rf_proxy_glass
    else                  → direct_probe_ranking
```

---

## 13. Threshold Optimization

Defined in `thresholds/optimizer.py` and `thresholds/schema.py`.

### The ThresholdConfig

All decision boundaries are collected into a single dataclass:

| Field | Controls | Default prior |
|---|---|---|
| `rho_viable` | Minimum LOO ρ for a surrogate to be "trusted" | 0.65 |
| `rho_bakeoff` | Minimum LOO ρ to consider a surrogate at all | 0.40 |
| `cluster_purity` | Minimum purity for query clustering to be retained | 0.75 |
| `routing_gap` | Max acceptable routing gap before investing in routing | 0.08 |
| `schema_rank_rho` | Minimum cross-variant rank correlation for flat hierarchy | 0.65 |
| `linear_tolerance` | Max ρ gap before non-linear beats linear | 0.08 |
| `interaction_ratio` | Min interaction fraction to prefer nonlinear surrogate | 0.25 |
| `ablation_gain` | Minimum error improvement to retain a component | 0.005 |
| `diminishing_returns_k` | Probe count at which marginal gains saturate | 4 |

None of these values are from the research diagram. They are all learned from data.

### How optimization works (no ground truth)

The optimizer works entirely from deployment-visible signals:

**Step 1 — Precompute LOO ρ for all surrogates** (expensive, done once)

For each surrogate, compute LOO Spearman ρ by:
- Holding out each probed config one at a time
- Fitting the surrogate on the remaining configs
- Predicting the held-out config's score
- Computing Spearman ρ between all predicted scores and BTL scores

BTL scores (not true error) are used as the reference because they are deployment-visible.

**Step 2 — Optimize thresholds via Optuna TPE** (cheap, done N times)

For each trial, Optuna samples a candidate `ThresholdConfig` and calls `simulate_routing`:

```
simulate_routing(surrogate_rhos, tc):
    viable = {surrogates with ρ >= tc.rho_viable}
    bakeoff = {surrogates with tc.rho_bakeoff <= ρ < tc.rho_viable}

    if viable:
        selected_rho = max(viable values)
    elif bakeoff:
        selected_rho = max(bakeoff values)
    else:
        selected_rho = rho of direct_probe_ranking (fallback)

    return best_rho - selected_rho   # ρ-space regret
```

Optuna minimizes ρ-space regret — the gap between the surrogate we'd pick under these thresholds and the best possible surrogate. This is entirely in proxy space, no ground truth.

**Result:** `optimal_thresholds.json` in the results directory. These thresholds are loaded by all stage runners automatically. When the probe cache exists, these thresholds are calibrated to the actual probe data from your dataset.

---

## 14. How Stages Connect

The critical design property: stages are not independent scripts. Each stage's outputs directly constrain the next stage's inputs.

```
ProbeData
    │
    ▼
Stage 1 (characterizer.py)
    ├─ probe_viable ──────────────────────────► Stage 2: exclude llm_judge_btl if False
    ├─ use_nonlinear ─────────────────────────► Stage 2: deprioritize linear surrogate
    ├─ error_surface.smooth ──────────────────► Stage 3: use bayesian_opt if rugged
    ├─ density_greedy_viable ─────────────────► Stage 3: use greedy if True
    ├─ use_clustering ────────────────────────► Stage 4: activate query_clustering
    ├─ use_routing ───────────────────────────► Stage 4: activate routing component
    └─ schema_first ──────────────────────────► Stage 4: activate schema_pruning
    │
    ▼
Stage 2 (surrogate_comparison.py + optimizer.py)
    ├─ best_surrogate ────────────────────────► Stage 3: fit this surrogate
    └─ use_acquisition_search ────────────────► Stage 3: use bayesian_opt if True
    │
    ▼
Stage 3 (comparison.py + algorithm modules)
    └─ selected_config_ids ───────────────────► Stage 4 + Stage 5
    │
    ▼
Stage 4 (ablation.py)
    └─ active_components ─────────────────────► Stage 5 reporting
    │
    ▼
Stage 5 (evaluation.py)
    └─ SPP error measurement ◄─── ground truth enters here for the first time
```

Additionally:

- **Adaptive probing** (triggered in Stage 1 when ρ < rho_bakeoff) re-runs Stage 1 with expanded probe data before Stage 2 begins
- **ThresholdConfig** flows through every stage as a parameter — all routing decisions consume learned thresholds, never hardcoded values

---

## 15. What the Agent Is Not Allowed to See

To be clear about the ground-truth firewall:

| Information | Allowed? | Where it lives |
|---|---|---|
| Text documents in the corpus | ✅ Yes | `corpus` in Instance |
| SQL query text and structure | ✅ Yes | `queries` in Instance |
| Schema (column names and types) | ✅ Yes | `Schema` object |
| Glass-box composite scores | ✅ Yes | `probe_data.glass_box_composites` |
| BTL scores from LLM judge | ✅ Yes | `probe_data.btl_scores` |
| Per-doc extraction quality signals | ✅ Yes | `probe_data.tier1_signals` |
| LOO Spearman ρ between surrogates | ✅ Yes | Computed from above |
| Query SQL execution results on *probe* database | ❌ No | These would reveal ground truth |
| True macro-F1 of any query | ❌ No | Only in Stage 5 evaluation |
| True SPP error for any config | ❌ No | Only in Stage 5 evaluation |
| Ground-truth CSV tables | ❌ No | Only loaded for Stage 5 evaluation |
| Phase 0 reward table | ❌ No | Only used in Stage 5 and for evaluation |

The `ProbeData.true_errors` field is explicitly set to `{}` during deployment. The threshold optimizer explicitly zeroes it out during LOO folds. No path from deployment-time code reaches ground-truth evaluation.

---

## 16. End-to-End Data Flow

### Research time (run once per dataset family)

```
Corpus + Queries + Schema
    ↓
phase0_reward_table.py
    → Run all 6 surrogates × 5 slices × 2 budgets
    → Evaluate true SPP error for each combination
    → Save: results/phase0_reward_table_Player.json
    ↓
phase1_comparison.py --force-probe
    → Run probe on Player agg_only
    → Save: results/phase1_agg_only_probe_context.json  (ProbeData cache)
    ↓
optimize_thresholds.py
    → Load probe cache (no ground truth)
    → Compute LOO ρ for all surrogates
    → Optimize thresholds via Optuna TPE
    → Save: results/optimal_thresholds.json
```

### Deployment time (run for each new workload)

```
New corpus + New SQL queries
    ↓
[Probe run: LLM extraction + LLM judge]
    → glass-box scores, BTL scores, tier1 signals
    ↓
[ReAct Agent]
    Step 1: get_dataset_summary()
    Step 2: run_stage1_characterization()
        → recommendations: probe_viable, use_nonlinear, ...
        → if rho < rho_bakeoff: probe_additional_configs(4) → re-run Stage 1
    Step 3: run_surrogate_bakeoff()
        → LOO ρ for each surrogate vs BTL
        → viable/bakeoff/below lists
    Step 4: run_pipeline_and_select(budget=1)
        Stage 1 recs → narrow Stage 2 surrogate list
        LOO ρ + thresholds → pick best surrogate
        Stage 1 surface shape → pick algorithm (greedy/BO/coord_descent)
        Stage 1 flags → determine Stage 4 active components
        → returns: selected_configs, best_surrogate, best_algorithm
    ↓
Selected config IDs (e.g., ["er=embedding_0.9|norm=llm|unit=unit|miss=drop"])
    ↓
[Materialize database: extract full corpus, apply selected config]
    ↓
[Execute SQL queries on database]
    ↓
[Compare results to ground truth → SPP error]
```

---

## 17. Running the System

### Prerequisites

```bash
cd systems/spp-agent
source .venv/bin/activate
pip install -r requirements.txt  # includes optuna, pulp
```

### LLM setup

**Option A — Local vLLM:**
```bash
vllm serve Qwen/Qwen2.5-32B-Instruct --port 8000
# config/defaults.yaml already points to localhost:8000
```

**Option B — DeepSeek API:**
```bash
export DEEPSEEK_API_KEY=your_key
export SPP_LLM_PROFILE=deepseek_v4_flash
```

### Full online pipeline

```bash
# 1. Generate ground-truth reward table (needed for Stage 5 evaluation only)
python experiments/phase0_reward_table.py

# 2. Run probes and save probe cache (needed for threshold optimization)
python experiments/phase1_comparison.py --force-probe

# 3. Optimize thresholds from probe cache (no ground truth)
python experiments/optimize_thresholds.py --n-trials 100

# 4. Stage 1: characterize this workload
python experiments/stage1_characterize.py --dataset Player --slice agg_only

# 5. Stage 2: surrogate bakeoff
python experiments/stage2_surrogates.py

# 6. Stage 3: algorithm comparison
python experiments/stage3_algorithms.py --budget 2

# 7. Stage 4: ablation
python experiments/stage4_ablation.py

# 8. Stage 5: end-to-end evaluation vs baselines
python experiments/stage5_evaluation.py --budget-levels 1 2
```

### Offline smoke-test (no LLM required)

```bash
python experiments/optimize_thresholds.py --offline --n-trials 20
python experiments/stage1_characterize.py --offline
python experiments/stage5_evaluation.py --offline
```

### Results

All outputs land in `results/`:

| File | Content |
|---|---|
| `optimal_thresholds.json` | Learned ThresholdConfig values |
| `stage1_report.json` | Stage 1 recommendations and analysis details |
| `stage2_report.json` | Surrogate LOO ρ ranking and bakeoff result |
| `stage3_report.json` | Algorithm comparison: scores and wall times |
| `stage4_report.json` | Ablation: which components are retained |
| `stage5_report.json` | End-to-end error, regret, oracle match rate by method |
| `phase0_reward_table_Player.json` | Ground-truth oracle table (research only) |
| `phase1_agg_only_probe_context.json` | Probe cache (reused across experiments) |
