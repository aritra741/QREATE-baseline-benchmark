"""Deployment-visible structural scores for meta-controller selection.

These scores intentionally avoid glass-box composites and BTL judge outputs.
"""

from __future__ import annotations

from typing import Any


def compute_structural_selection_score(tier1: dict[str, Any]) -> float:
    """Weighted combination of tier-1 extraction/population signals."""
    coverage = float(tier1.get("schema_column_coverage", 0.0))
    missing = 1.0 - float(tier1.get("missing_value_rate", 1.0))
    unit = float(tier1.get("unit_parse_success_rate", 1.0))
    numeric = float(tier1.get("numeric_type_success_rate", 1.0))
    type_valid = float(tier1.get("query_column_type_validity", 1.0))
    dup_penalty = 1.0 - min(1.0, float(tier1.get("duplicate_candidate_rate", 0.0)))
    ambiguity_penalty = 1.0 - min(1.0, float(tier1.get("entity_ambiguity_score", 0.0)))
    refusal_penalty = 1.0 - min(
        1.0, float(tier1.get("extraction_refusal_or_empty_rate", 0.0))
    )
    weights = (0.25, 0.15, 0.10, 0.20, 0.15, 0.05, 0.05, 0.05)
    components = (
        coverage,
        missing,
        unit,
        numeric,
        type_valid,
        dup_penalty,
        ambiguity_penalty,
        refusal_penalty,
    )
    return float(sum(w * c for w, c in zip(weights, components)))


def structural_scores_from_probe(probe_data) -> dict[str, float]:
    scores: dict[str, float] = {}
    for cid in probe_data.config_ids:
        tier1 = probe_data.tier1_signals.get(cid, {})
        scores[cid] = compute_structural_selection_score(tier1)
    return scores


def probe_data_with_selection_scores(probe_data, scores: dict[str, float]):
    """Adapter so legacy routing helpers use structural scores, not glass-box."""
    import copy

    view = copy.copy(probe_data)
    view.glass_box_composites = dict(scores)
    return view
