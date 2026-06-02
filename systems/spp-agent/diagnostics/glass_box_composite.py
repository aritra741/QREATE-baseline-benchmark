from __future__ import annotations


def compute_glass_box_composite(signals: dict) -> float:
    unit_rate = signals.get("unit_parse_success_rate")
    unit_term = unit_rate if unit_rate is not None else 1.0
    numeric_type_rate = signals.get("numeric_type_success_rate")
    numeric_term = numeric_type_rate if numeric_type_rate is not None else 1.0

    components = [
        signals.get("schema_column_coverage", 0.0),
        1.0 - signals.get("missing_value_rate", 1.0),
        1.0 - signals.get("duplicate_candidate_rate", 1.0),
        1.0 - min(1.0, signals.get("entity_ambiguity_score", 1.0)),
        1.0 - signals.get("json_parse_error_rate", 1.0),
        1.0 - signals.get("extraction_refusal_or_empty_rate", 1.0),
        unit_term,
        numeric_term,
    ]
    return float(sum(components) / len(components))
