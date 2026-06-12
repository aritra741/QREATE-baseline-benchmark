# SPP-Agent Pipeline Overview

This document describes the architecture, decision-making process, and underlying assumptions of the Surrogate-based Pipeline Selection (SPP) agent.

## 1. Pipeline Architecture

The SPP-Agent follows a multi-stage process to select the best database synthesis configurations for a given query workload and document corpus.

### Stage 0: Initialization & Clustering
- **Configuration Space**: The system explores a space of **288 configurations** (ER strategy, normalization, unit handling, missing value strategy, and type coercion).
- **Query Clustering**: Before probing, the input query workload is clustered based on structural features (e.g., presence of JOIN, GROUP BY, WHERE). Clusters are typed as `aggregation`, `join`, `filter`, or `mixed`.

### Stage 1: Probing
- **Initial Probes**: A small subset of configurations (typically 8) is executed on a sampled portion of the corpus.
- **Glass-Box Diagnostics**: For each probe, "glass-box" signals are collected (e.g., schema coverage, missing value rates, entity ambiguity).
- **LLM Judging (BTL)**: An LLM judge compares pairs of synthesized databases for a subset of queries, producing Bradley-Terry-Luce (BTL) quality scores.

### Stage 2: Surrogate Training & Bakeoff
- **Surrogate Models**: Various models (Gaussian Processes, Random Forests, GBDTs, etc.) are trained to map configuration features to the proxy signals (Glass-Box and BTL).
- **Per-Cluster Bakeoff**: For each query cluster, the system runs a "bakeoff" using Leave-One-Out (LOO) cross-validation to determine which surrogate model best predicts performance for that specific query type.

### Stage 3: Routing & Assignment
- **Routing Table**: Instead of picking one global configuration, the system assigns each query cluster to its own "best" configuration.
- **Budget-Aware Selection**: The assignment algorithm (Greedy or ILP) selects configurations to maximize predicted quality across all clusters while staying within a **token budget** for database materialization.

### Stage 4: Execution (Deployment)
- The selected configurations are used to synthesize the final databases.
- Queries are routed to the database corresponding to their cluster.

## 2. Decision Making

The pipeline makes several key decisions at runtime:

1.  **Surrogate Selection**: Which model (e.g., `gp_proxy_glass` vs `llm_judge_btl`) is most trustworthy for a specific cluster? This is decided by the LOO Spearman correlation ($\rho$).
2.  **Adaptive Probing**: The ReAct agent can decide to "probe more" if the initial signals are noisy or surrogates disagree significantly.
3.  **Risk Management**: The agent can choose a `risk_averse` level, which penalizes configurations with high uncertainty (predicted by Gaussian Processes).
4.  **Cluster Granularity**: The agent can override the automatic cluster count if it believes a more granular or more global approach is better.

## 3. Key Assumptions

- **Proxy Validity**: We assume that glass-box signals (extraction quality) and LLM preferences (BTL) are correlated with actual query accuracy (Ground Truth).
- **Structural Similarity**: We assume that queries with similar SQL structures will perform similarly under the same synthesis configuration.
- **Ground-Truth Firewall**: A core invariant is that **Ground Truth (true query results) is never accessed during the selection process**. It is only used in Stage 5 for offline evaluation of the pipeline's effectiveness.
- **Corpus Representativeness**: We assume the sampled documents used during probing are representative of the full corpus.

## 4. Primary Metrics

- **Routed Error**: The mean error (1 - macro-F1) across the workload when each query is executed on its routed database. This is the primary benchmark metric.
- **Regret**: The difference between the system's routed error and the "Oracle" error (the best possible error if we had known the ground truth).
- **Spearman $\rho$**: Used to measure the fidelity of surrogates during the bakeoff stage.

## 5. Pilot & Benchmark Setup (Current State)

The current implementation is being tested on a **20-document pilot** of the `Player` dataset:
- **Corpus-Restricted GT**: Ground truth is automatically filtered to only include entities present in the 20 sampled documents to ensure fair evaluation.
- **Pilot Slice**: Testing is focused on the `agg_only` (aggregation-only) query slice.
- **Performance Note**: On this tiny corpus, absolute accuracy is often low (e.g., 0-33%) due to incomplete extraction or SQL type mismatches (e.g., `AVG` on a string column). The pipeline's goal in this context is to demonstrate correct **relative** selection and routing, even when absolute performance is constrained by the data.
