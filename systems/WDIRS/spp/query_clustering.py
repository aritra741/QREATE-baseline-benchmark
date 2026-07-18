"""Phase 3 — Structural query clustering (ported from spp-agent's
`stage4/query_clustering.py`, lightly adapted).

This module has no dependency on extraction/population quality -- it only
parses SQL structure (COUNT/SUM/AVG/MIN/MAX, GROUP BY, JOIN, WHERE,
temporal-column hints) -- so it can be reused close to verbatim, per the
migration plan's Phase 3.

Query dicts use the key "sql" (WDIRS's convention) rather than spp-agent's
"sql_query".
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.cluster import KMeans

logger = logging.getLogger(__name__)

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
    labels: List[int]
    cluster_to_queries: Dict[int, List[dict]]
    cluster_types: Dict[int, str]
    centroids: List[List[float]]
    info: dict


def _sql_text(query: dict) -> str:
    return query.get("sql") or query.get("sql_query") or ""


def sql_structural_features(sql: str) -> List[float]:
    """9-dim binary feature vector for a SQL string."""
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
    queries: List[dict],
    *,
    min_k: int = 2,
    max_k: int = 4,
    seed: int = 42,
) -> int:
    """Choose number of clusters via the elbow method on KMeans inertia."""
    if len(queries) < min_k:
        return 1

    features = np.array([sql_structural_features(_sql_text(q)) for q in queries])
    if len(features) < 2:
        return 1

    inertias: Dict[int, float] = {}
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


def assign_cluster_types(centroids: List[List[float]]) -> Dict[int, str]:
    """Map cluster centroids to workload types: aggregation/join/filter/mixed."""
    types: Dict[int, str] = {}
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
    queries: List[dict],
    n_clusters: int = 3,
    *,
    seed: int = 42,
) -> Tuple[List[int], dict]:
    """Cluster queries by SQL structural features using KMeans."""
    if not queries:
        return [], {"cluster_sizes": {}, "inertia": 0.0, "centroids": []}

    features = np.array([sql_structural_features(_sql_text(q)) for q in queries])
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


def cluster_workload(
    queries: List[dict], *, seed: int = 42, n_clusters: Optional[int] = None
) -> QueryClusters:
    """Full clustering pipeline: choose k, cluster, type the clusters."""
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

    cluster_to_queries: Dict[int, List[dict]] = {i: [] for i in range(k)}
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
