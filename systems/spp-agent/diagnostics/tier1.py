from __future__ import annotations

import numpy as np
import pandas as pd

from diagnostics.glass_box_composite import compute_glass_box_composite
from diagnostics.type_validity import query_column_type_validity, required_table_row_count
from pipeline.extraction import ExtractionResult
from pipeline.population import PopulationDiagnostics
from pipeline.schema import Schema


def compute_tier1(
    extraction: ExtractionResult,
    population_diagnostics: PopulationDiagnostics,
    schema: Schema,
    db: dict[str, pd.DataFrame],
    *,
    queries: list[dict] | None = None,
    required_tables: set[str] | None = None,
) -> dict:
    tuple_counts = [sig["tuple_count"] for sig in extraction.per_doc_signals]
    tuple_count = int(sum(tuple_counts))
    tuple_var = float(np.var(tuple_counts)) if tuple_counts else 0.0

    total_cells = 0
    filled_cells = 0
    schema_columns = 0
    covered_columns = 0

    for table, cols in schema.tables.items():
        df = db.get(table, pd.DataFrame())
        for col in cols:
            schema_columns += 1
            if col in df.columns and df[col].notna().any() and (df[col].astype(str).str.strip() != "").any():
                covered_columns += 1
            if col in df.columns:
                series = df[col]
                total_cells += len(series)
                filled_cells += int(series.notna().sum()) + int((series.astype(str).str.strip() != "").sum())

    schema_column_coverage = covered_columns / schema_columns if schema_columns else 0.0
    missing_value_rate = 1.0 - (filled_cells / (2 * total_cells)) if total_cells else 1.0
    missing_value_rate = max(0.0, min(1.0, missing_value_rate))

    json_errors = sum(1 for s in extraction.per_doc_signals if not s["json_parse_success"])
    json_parse_error_rate = json_errors / len(extraction.per_doc_signals) if extraction.per_doc_signals else 0.0

    refusal_or_empty = sum(
        1 for s in extraction.per_doc_signals if s["extraction_refusal"] or s["empty_output"]
    )
    extraction_refusal_or_empty_rate = (
        refusal_or_empty / len(extraction.per_doc_signals) if extraction.per_doc_signals else 0.0
    )

    unit_total = population_diagnostics.unit_parse_successes + population_diagnostics.unit_parse_failures
    unit_parse_success_rate = (
        population_diagnostics.unit_parse_successes / unit_total if unit_total else 1.0
    )

    entity_ambiguity_score = (
        population_diagnostics.er_ambiguous_pairs / max(1, population_diagnostics.er_merge_count + 1)
    )

    signals: dict = {
        "tuple_count": tuple_count,
        "tuple_count_variance_by_doc": tuple_var,
        "schema_column_coverage": schema_column_coverage,
        "missing_value_rate": missing_value_rate,
        "duplicate_candidate_rate": population_diagnostics.duplicate_rate,
        "entity_ambiguity_score": entity_ambiguity_score,
        "normalization_entropy": population_diagnostics.norm_entropy,
        "unit_parse_success_rate": unit_parse_success_rate,
        "json_parse_error_rate": json_parse_error_rate,
        "extraction_refusal_or_empty_rate": extraction_refusal_or_empty_rate,
    }

    if required_tables:
        signals["required_table_row_count"] = required_table_row_count(required_tables, db)

    if queries:
        type_signals = query_column_type_validity(queries, schema, db)
        signals.update(type_signals)
    else:
        signals["numeric_type_success_rate"] = 1.0
        signals["query_column_type_validity"] = 1.0
        signals["numeric_column_checks"] = []

    signals["glass_box_composite"] = compute_glass_box_composite(signals)
    return signals
