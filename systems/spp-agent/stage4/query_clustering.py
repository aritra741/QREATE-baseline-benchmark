from __future__ import annotations

import re
from collections import Counter

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


def sql_structural_features(sql: str) -> list[float]:
    """Return a 9-dim binary feature vector for a SQL string.

    Dimensions: COUNT, SUM, AVG, MIN, MAX, GROUP_BY, JOIN, WHERE, temporal.
    """
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


def cluster_queries_structural(
    queries: list[dict],
    n_clusters: int = 3,
    *,
    seed: int = 42,
) -> tuple[list[int], dict]:
    """Cluster queries by SQL structural features using KMeans."""
    features = np.array(
        [sql_structural_features(q.get("sql_query", "")) for q in queries]
    )
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


def cluster_queries_error_profile(
    queries: list[dict],
    true_errors_by_config: dict[str, dict[str, float]],
    n_clusters: int = 3,
    *,
    seed: int = 42,
) -> tuple[list[int], dict]:
    """Cluster queries by their error vector across all configs.

    *true_errors_by_config* maps ``query_id -> {config_id -> error}``.
    """
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
    """Purity: fraction of queries whose cluster-majority oracle-config
    matches the query's own oracle-best config."""
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
