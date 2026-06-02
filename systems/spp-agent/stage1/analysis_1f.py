from __future__ import annotations

from collections import Counter

import numpy as np
from sklearn.cluster import KMeans

from thresholds.schema import ThresholdConfig
from utils.logging import setup_logger

logger = setup_logger("spp.stage1.1f")

_AGG_KEYWORDS = ("COUNT", "SUM", "AVG", "MIN", "MAX")
_TEMPORAL_KEYWORDS = (
    "DATE", "TIME", "YEAR", "MONTH", "DAY", "HOUR", "MINUTE", "SECOND",
    "INTERVAL", "TIMESTAMP", "NOW", "CURRENT_DATE",
)


def _extract_sql_features(query: dict) -> list[float]:
    """Binary presence features from SQL text."""
    sql = query.get("sql", query.get("query", "")).upper()
    features: list[float] = []
    for kw in _AGG_KEYWORDS:
        features.append(1.0 if kw in sql else 0.0)
    features.append(1.0 if "GROUP BY" in sql else 0.0)
    features.append(1.0 if "JOIN" in sql else 0.0)
    features.append(1.0 if "WHERE" in sql else 0.0)
    has_temporal = any(kw in sql for kw in _TEMPORAL_KEYWORDS)
    features.append(1.0 if has_temporal else 0.0)
    return features


def analyze_clustering_validity(
    queries: list[dict],
    *,
    thresholds: ThresholdConfig,
    true_errors_by_config: dict[str, dict[str, float]] | None = None,
    n_clusters: int = 3,
    seed: int = 42,
) -> dict:
    """Cluster queries by SQL structure and (optionally) measure purity."""
    if not queries:
        return {
            "n_clusters": 0,
            "cluster_sizes": [],
            "purity": None,
            "recommendation": "insufficient_data",
        }

    x = np.array([_extract_sql_features(q) for q in queries])
    k = min(n_clusters, len(queries))
    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    labels = km.fit_predict(x)

    cluster_sizes = [int(c) for c in sorted(Counter(labels).values(), reverse=True)]

    purity: float | None = None
    if true_errors_by_config:
        # For each query, oracle-best-config = config with minimum error
        query_oracle_labels: list[str] = []
        for idx, q in enumerate(queries):
            qid = q.get("query_id", q.get("id", str(idx)))
            best_config: str | None = None
            best_err = float("inf")
            for cid, err_by_q in true_errors_by_config.items():
                err = err_by_q.get(qid, float("inf"))
                if err < best_err:
                    best_err = err
                    best_config = cid
            query_oracle_labels.append(best_config or "unknown")

        correct = 0
        for cluster_id in range(k):
            members = [query_oracle_labels[i] for i in range(len(queries)) if labels[i] == cluster_id]
            if members:
                most_common = Counter(members).most_common(1)[0][1]
                correct += most_common
        purity = correct / len(queries) if queries else 0.0

    if purity is None:
        recommendation = "insufficient_data"
    elif purity >= thresholds.cluster_purity:
        recommendation = "structural_clustering_valid"
    else:
        recommendation = "try_error_profile_features_or_remove"

    logger.info(
        "Clustering: n_clusters=%d sizes=%s purity=%s rec=%s",
        k, cluster_sizes, purity, recommendation,
    )
    return {
        "n_clusters": k,
        "cluster_sizes": cluster_sizes,
        "purity": purity,
        "recommendation": recommendation,
    }
