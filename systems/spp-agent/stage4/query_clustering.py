from __future__ import annotations

import copy
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np
from sklearn.cluster import KMeans

from utils.logging import setup_logger

logger = setup_logger("spp.stage4.query_clustering")

_COUNT_RE = re.compile(r"\bcount\s*\(", re.IGNORECASE)
_SUM_RE = re.compile(r"\bsum\s*\(", re.IGNORECASE)
_AVG_RE = re.compile(r"\bavg\s*\(", re.IGNORECASE)
_MIN_RE = re.compile(r"\bmin\s*\(", re.IGNORECASE)
_MAX_RE = re.compile(r"\bmax\s*\(", re.IGNORECASE)
_GROUP_BY_RE = re.compile(r"\bgroup\s+by\b", re.IGNORECASE)
_JOIN_RE = re.compile(r"\bjoin\b", re.IGNORECASE)
_WHERE_RE = re.compile(r"\bwhere\b", re.IGNORECASE)
_TEMPORAL_RE = re.compile(
    r"\b(birth_date|draft_year|founded_year|death_date|year|date)\b|"
    r"\b(year|date)\s*\(|extract\s*\(",
    re.IGNORECASE,
)


@dataclass
class QueryClusters:
    n_clusters: int
    labels: list[int]
    cluster_to_queries: dict[int, list[dict]]
    cluster_types: dict[int, str]
    centroids: list[list[float]]
    info: dict


def sql_structural_features(sql: str) -> list[float]:
    """Return a 9-dim binary feature vector for a SQL string."""
    return [
        float(bool(_COUNT_RE.search(sql))),
        float(bool(_SUM_RE.search(sql))),
        float(bool(_AVG_RE.search(sql))),
        float(bool(_MIN_RE.search(sql))),
        float(bool(_MAX_RE.search(sql))),
        float(bool(_GROUP_BY_RE.search(sql))),
        float(bool(_JOIN_RE.search(sql))),
        float(bool(_WHERE_RE.search(sql))),
        float(bool(_TEMPORAL_RE.search(sql))),
    ]


def choose_n_clusters(
    queries: list[dict],
    *,
    min_k: int = 2,
    max_k: int = 4,
    seed: int = 42,
) -> int:
    """Choose number of clusters using elbow on KMeans inertia."""
    if len(queries) < min_k:
        return 1

    features = np.array([sql_structural_features(q.get("sql_query", "")) for q in queries])
    if len(features) < 2:
        return 1

    inertias: dict[int, float] = {}
    for k in range(min_k, min(max_k, len(queries)) + 1):
        km = KMeans(n_clusters=k, random_state=seed, n_init=10)
        km.fit(features)
        inertias[k] = float(km.inertia_)

    for k in range(min_k, max_k):
        if k + 1 not in inertias:
            break
        current = inertias[k]
        next_k = inertias[k + 1]
        if current <= 0:
            continue
        drop_ratio = (current - next_k) / current
        if drop_ratio < 0.2:
            logger.info("Elbow at k=%d (drop_ratio=%.3f)", k, drop_ratio)
            return k

    return min(max_k, len(queries))


def assign_cluster_types(centroids: list[list[float]]) -> dict[int, str]:
    """Map cluster centroids to workload types."""
    types: dict[int, str] = {}
    for idx, centroid in enumerate(centroids):
        join_w = centroid[6] if len(centroid) > 6 else 0.0
        where_w = centroid[7] if len(centroid) > 7 else 0.0
        agg_w = max(centroid[0:5]) if len(centroid) >= 5 else 0.0

        if join_w > 0.4:
            types[idx] = "join"
        elif agg_w > 0.3:
            types[idx] = "aggregation"
        elif where_w > 0.4:
            types[idx] = "filter"
        else:
            types[idx] = "mixed"
    return types


def cluster_queries_structural(
    queries: list[dict],
    n_clusters: int = 3,
    *,
    seed: int = 42,
) -> tuple[list[int], dict]:
    """Cluster queries by SQL structural features using KMeans."""
    if not queries:
        return [], {"cluster_sizes": {}, "inertia": 0.0, "centroids": []}

    features = np.array([sql_structural_features(q.get("sql_query", "")) for q in queries])
    effective_k = min(n_clusters, len(queries))
    km = KMeans(n_clusters=effective_k, random_state=seed, n_init=10)
    labels = km.fit_predict(features).tolist()

    cluster_sizes = Counter(labels)
    info = {
        "centroids": km.cluster_centers_.tolist(),
        "cluster_sizes": dict(cluster_sizes),
        "inertia": float(km.inertia_),
    }
    logger.info(
        "Structural clustering k=%d sizes=%s inertia=%.4f",
        effective_k,
        dict(cluster_sizes),
        km.inertia_,
    )
    return labels, info


def cluster_workload(queries: list[dict], *, seed: int = 42, n_clusters: int | None = None) -> QueryClusters:
    """Full clustering pipeline. Chooses k, clusters, types. Deployment-visible."""
    if not queries:
        return QueryClusters(
            n_clusters=1,
            labels=[],
            cluster_to_queries={0: []},
            cluster_types={0: "mixed"},
            centroids=[],
            info={"cluster_sizes": {0: 0}},
        )

    k = n_clusters if n_clusters is not None else choose_n_clusters(queries, seed=seed)
    k = max(1, min(k, len(queries)))
    labels, info = cluster_queries_structural(queries, n_clusters=k, seed=seed)

    cluster_to_queries: dict[int, list[dict]] = {i: [] for i in range(k)}
    for query, label in zip(queries, labels):
        cluster_to_queries.setdefault(label, []).append(query)

    centroids = info.get("centroids", [])
    cluster_types = assign_cluster_types(centroids) if centroids else {0: "mixed"}

    return QueryClusters(
        n_clusters=k,
        labels=labels,
        cluster_to_queries=cluster_to_queries,
        cluster_types=cluster_types,
        centroids=centroids,
        info=info,
    )


def cluster_queries_error_profile(
    queries: list[dict],
    true_errors_by_config: dict[str, dict[str, float]],
    n_clusters: int = 3,
    *,
    seed: int = 42,
) -> tuple[list[int], dict]:
    """Cluster queries by their error vector across all configs (offline only)."""
    if not queries:
        return [], {}

    sample_key = next(iter(true_errors_by_config))
    config_ids = sorted(true_errors_by_config[sample_key].keys())

    rows: list[list[float]] = []
    for q in queries:
        qid = q.get("query_id", q.get("id", ""))
        errs = true_errors_by_config.get(qid, {})
        rows.append([errs.get(cid, 0.0) for cid in config_ids])

    features = np.array(rows)
    effective_k = min(n_clusters, len(queries))
    km = KMeans(n_clusters=effective_k, random_state=seed, n_init=10)
    labels = km.fit_predict(features).tolist()

    cluster_sizes = Counter(labels)
    info = {
        "centroids": km.cluster_centers_.tolist(),
        "cluster_sizes": dict(cluster_sizes),
        "inertia": float(km.inertia_),
        "config_ids_used": config_ids,
    }
    logger.info(
        "Error-profile clustering k=%d sizes=%s inertia=%.4f",
        effective_k,
        dict(cluster_sizes),
        km.inertia_,
    )
    return labels, info


def clustering_purity(
    labels: list[int],
    oracle_best_configs: list[str],
) -> float:
    """Purity: fraction of queries whose cluster-majority oracle-config matches."""
    if not labels:
        return 0.0

    cluster_majority: dict[int, str] = {}
    cluster_configs: dict[int, list[str]] = {}
    for lab, cfg in zip(labels, oracle_best_configs):
        cluster_configs.setdefault(lab, []).append(cfg)
    for lab, cfgs in cluster_configs.items():
        cluster_majority[lab] = Counter(cfgs).most_common(1)[0][0]

    correct = sum(
        1
        for lab, cfg in zip(labels, oracle_best_configs)
        if cluster_majority[lab] == cfg
    )
    purity = correct / len(labels)
    logger.info("Clustering purity=%.4f (%d/%d)", purity, correct, len(labels))
    return purity
