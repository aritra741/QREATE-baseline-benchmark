from __future__ import annotations

"""Cluster-conditioned glass-box composite scores.

For each (config, cluster) pair, produce a single quality score by weighting
the tier1 diagnostic signals according to the cluster type.
No ground-truth access anywhere in this module.
"""

CLUSTER_WEIGHTS: dict[str, dict[str, float]] = {
    "aggregation": {
        "schema_column_coverage": 0.10,
        "missing_value_rate_inv": 0.20,
        "duplicate_candidate_rate_inv": 0.05,
        "entity_ambiguity_score_inv": 0.05,
        "json_parse_error_rate_inv": 0.10,
        "extraction_refusal_or_empty_rate_inv": 0.05,
        "unit_parse_success_rate": 0.25,
        "numeric_type_success_rate": 0.20,
    },
    "join": {
        "schema_column_coverage": 0.15,
        "missing_value_rate_inv": 0.10,
        "duplicate_candidate_rate_inv": 0.25,
        "entity_ambiguity_score_inv": 0.25,
        "json_parse_error_rate_inv": 0.10,
        "extraction_refusal_or_empty_rate_inv": 0.05,
        "unit_parse_success_rate": 0.05,
        "numeric_type_success_rate": 0.05,
    },
    "filter": {
        "schema_column_coverage": 0.30,
        "missing_value_rate_inv": 0.15,
        "duplicate_candidate_rate_inv": 0.10,
        "entity_ambiguity_score_inv": 0.10,
        "json_parse_error_rate_inv": 0.10,
        "extraction_refusal_or_empty_rate_inv": 0.05,
        "unit_parse_success_rate": 0.05,
        "numeric_type_success_rate": 0.15,
    },
    "mixed": {
        "schema_column_coverage": 0.125,
        "missing_value_rate_inv": 0.125,
        "duplicate_candidate_rate_inv": 0.125,
        "entity_ambiguity_score_inv": 0.125,
        "json_parse_error_rate_inv": 0.125,
        "extraction_refusal_or_empty_rate_inv": 0.125,
        "unit_parse_success_rate": 0.125,
        "numeric_type_success_rate": 0.125,
    },
}


def _signal_value(tier1: dict, key: str) -> float:
    if key.endswith("_inv"):
        raw_key = key[: -len("_inv")]
        raw = float(tier1.get(raw_key, 1.0))
        return max(0.0, min(1.0, 1.0 - raw))
    if key in tier1:
        return max(0.0, min(1.0, float(tier1[key])))
    return 0.0


def compute_cluster_glass_box(tier1: dict, cluster_type: str) -> float:
    """Compute cluster-conditioned glass-box composite for one (config, cluster) pair."""
    weights = CLUSTER_WEIGHTS.get(cluster_type, CLUSTER_WEIGHTS["mixed"])
    score = 0.0
    for key, weight in weights.items():
        score += weight * _signal_value(tier1, key)
    return max(0.0, min(1.0, score))


def compute_all_cluster_glass_boxes(
    tier1_signals: dict[str, dict],
    cluster_types: dict[int, str],
) -> dict[str, dict[int, float]]:
    """Returns {config_id: {cluster_id: score}} for all (config, cluster) pairs."""
    result: dict[str, dict[int, float]] = {}
    for config_id, tier1 in tier1_signals.items():
        result[config_id] = {}
        for cluster_id, cluster_type in cluster_types.items():
            result[config_id][cluster_id] = compute_cluster_glass_box(tier1, cluster_type)
    return result
