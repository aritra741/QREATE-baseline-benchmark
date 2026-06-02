from __future__ import annotations

import numpy as np
from scipy.stats import kendalltau, spearmanr


def top_k_overlap(
    proxy_scores: dict[str, float],
    true_errors: dict[str, float],
    k: int = 3,
) -> float:
    """
    Fraction of overlap between top-k configs.

    proxy_scores: higher is better
    true_errors: lower is better
    """
    common = set(proxy_scores) & set(true_errors)
    if not common or k <= 0:
        return 0.0

    k = min(k, len(common))
    proxy_top = set(sorted(common, key=lambda cid: proxy_scores[cid], reverse=True)[:k])
    true_top = set(sorted(common, key=lambda cid: true_errors[cid])[:k])
    return len(proxy_top & true_top) / k


def proxy_vs_true_correlation(
    proxy_scores: dict[str, float],
    true_errors: dict[str, float],
    *,
    k: int = 3,
) -> dict:
    ids = sorted(set(proxy_scores) & set(true_errors))
    if len(ids) < 2:
        return {
            "spearman": None,
            "kendall": None,
            "top3_overlap": top_k_overlap(proxy_scores, true_errors, k=k),
            "proxy_top3": sorted(ids, key=lambda x: proxy_scores[x], reverse=True)[:k],
            "true_top3": sorted(ids, key=lambda x: true_errors[x])[:k],
        }

    x = np.array([proxy_scores[i] for i in ids])
    y = np.array([-true_errors[i] for i in ids])

    return {
        "spearman": float(spearmanr(x, y).correlation),
        "kendall": float(kendalltau(x, y).correlation),
        "top3_overlap": top_k_overlap(proxy_scores, true_errors, k=k),
        "proxy_top3": sorted(ids, key=lambda x: proxy_scores[x], reverse=True)[:k],
        "true_top3": sorted(ids, key=lambda x: true_errors[x])[:k],
    }


def scores_from_config_table(
    config_table: list[dict],
    proxy_key: str,
    true_key: str = "true_error",
) -> tuple[dict[str, float], dict[str, float]]:
    proxy = {row["config_id"]: float(row[proxy_key]) for row in config_table if row.get(proxy_key) is not None}
    true_err = {row["config_id"]: float(row[true_key]) for row in config_table if row.get(true_key) is not None}
    return proxy, true_err
