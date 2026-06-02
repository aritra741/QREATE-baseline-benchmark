from __future__ import annotations

from collections import Counter

import numpy as np
from sklearn.cluster import KMeans

from utils.logging import setup_logger

logger = setup_logger("spp.stage4.cluster_refinement")


def _largest_cluster(labels: list[int]) -> int:
    """Return the label of the largest cluster."""
    counts = Counter(labels)
    return counts.most_common(1)[0][0]


def _cluster_centroid(
    features: np.ndarray,
    labels: np.ndarray,
    cluster_id: int,
) -> np.ndarray:
    mask = labels == cluster_id
    return features[mask].mean(axis=0)


def refine_split(
    labels: list[int],
    features: list[list[float]],
    *,
    seed: int = 42,
) -> list[int]:
    """Split the largest cluster in two using KMeans(2)."""
    feat_arr = np.array(features)
    lab_arr = np.array(labels)
    target = _largest_cluster(labels)

    mask = lab_arr == target
    if mask.sum() < 2:
        logger.info("Largest cluster has <2 members; no split performed")
        return list(labels)

    km = KMeans(n_clusters=2, random_state=seed, n_init=10)
    sub_labels = km.fit_predict(feat_arr[mask])

    new_label = max(labels) + 1
    result = list(labels)
    idx = 0
    for i, is_target in enumerate(mask):
        if is_target:
            if sub_labels[idx] == 1:
                result[i] = new_label
            idx += 1

    logger.info(
        "Split cluster %d -> {%d, %d} (sizes %d, %d)",
        target,
        target,
        new_label,
        int((sub_labels == 0).sum()),
        int((sub_labels == 1).sum()),
    )
    return result


def _merge_two_closest(
    labels: list[int],
    features: list[list[float]],
) -> list[int]:
    """Merge the two most similar clusters (by centroid Euclidean distance)."""
    feat_arr = np.array(features)
    lab_arr = np.array(labels)
    unique = sorted(set(labels))

    if len(unique) < 2:
        return list(labels)

    centroids = {
        c: _cluster_centroid(feat_arr, lab_arr, c) for c in unique
    }

    best_dist = float("inf")
    merge_pair: tuple[int, int] = (unique[0], unique[1])
    for i, c1 in enumerate(unique):
        for c2 in unique[i + 1 :]:
            d = float(np.linalg.norm(centroids[c1] - centroids[c2]))
            if d < best_dist:
                best_dist = d
                merge_pair = (c1, c2)

    keep, drop = merge_pair
    result = [keep if lab == drop else lab for lab in labels]
    logger.info(
        "Merged cluster %d into %d (distance=%.4f)",
        drop,
        keep,
        best_dist,
    )
    return result


def refine_split_merge(
    labels: list[int],
    features: list[list[float]],
    *,
    seed: int = 42,
) -> list[int]:
    """Split largest cluster, then merge the two most similar clusters."""
    after_split = refine_split(labels, features, seed=seed)
    return _merge_two_closest(after_split, features)


def refine_alternating(
    labels: list[int],
    features: list[list[float]],
    *,
    n_rounds: int = 3,
    seed: int = 42,
) -> list[int]:
    """Alternate split and merge for *n_rounds*."""
    current = list(labels)
    for rnd in range(n_rounds):
        current = refine_split(current, features, seed=seed + rnd)
        current = _merge_two_closest(current, features)
        logger.info(
            "Alternating round %d/%d clusters=%d",
            rnd + 1,
            n_rounds,
            len(set(current)),
        )
    return current
