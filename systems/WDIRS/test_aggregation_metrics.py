"""Tests for aggregation-table evaluation metrics."""

from __future__ import annotations

from spp.aggregation_metrics import (
    AggregationTable,
    ColumnSpec,
    MetricConfig,
    canonicalize,
    evaluate_aggregation_tables,
    table_from_rows,
)


def test_perfect_table_scores_all_ones():
    gold = table_from_rows(
        [
            {"nation": "USA", "cnt": 10},
            {"nation": "Canada", "cnt": 3},
        ],
        key_columns=["nation"],
        measure_columns=["cnt"],
        operators={"cnt": "COUNT"},
    )
    pred = table_from_rows(
        [
            {"nation": "USA", "cnt": 10},
            {"nation": "Canada", "cnt": 3},
        ],
        key_columns=["nation"],
        measure_columns=["cnt"],
        operators={"cnt": "COUNT"},
    )
    result = evaluate_aggregation_tables(pred, gold)
    assert result["structure"]["column"]["key"]["F1"] == 1.0
    assert result["structure"]["column"]["measure"]["F1"] == 1.0
    for tier in ("exact", "normalized", "semantic"):
        assert result["structure"]["row"][tier]["P"] == 1.0
        assert result["structure"]["row"][tier]["R"] == 1.0
        assert result["structure"]["row"][tier]["F1"] == 1.0
    assert result["value"]["row_recall_context"] == 1.0
    assert result["value"]["rel_err_histogram"]["exact_or_le_1pct"] == 1.0
    assert result["rank"]["structure_score"] == 1.0
    for tau in (0.01, 0.05, 0.20):
        assert result["value"]["pass_at_tau"][tau] == 1.0
        assert result["rank"]["cell_f1"][tau] == 1.0
        assert result["rank"]["query_score"][tau] == 1.0
    assert result["value"]["frac_catastrophic"] == 0.0
    assert result["grouping"]["merge_rate"] == 0.0
    assert result["grouping"]["split_rate"] == 0.0


def test_right_structure_values_ten_percent_of_range_flips_across_tau():
    # Gold span = 100 - 0 = 100. Pred is +10 absolute → range_err = 0.10.
    gold = table_from_rows(
        [{"k": "a", "v": 0.0}, {"k": "b", "v": 100.0}],
        key_columns=["k"],
        measure_columns=["v"],
        operators={"v": "SUM"},
    )
    pred = table_from_rows(
        [{"k": "a", "v": 10.0}, {"k": "b", "v": 110.0}],
        key_columns=["k"],
        measure_columns=["v"],
        operators={"v": "SUM"},
    )
    result = evaluate_aggregation_tables(pred, gold)
    assert result["structure"]["row"]["exact"]["F1"] == 1.0
    assert result["rank"]["structure_score"] == 1.0
    assert result["value"]["row_recall_context"] == 1.0
    assert result["value"]["column_ranges"]["v"] == {"min": 0.0, "max": 100.0}
    assert result["value"]["pass_at_tau"][0.05] == 0.0
    assert result["value"]["pass_at_tau"][0.20] == 1.0
    assert result["rank"]["cell_f1"][0.05] == 0.0
    assert result["rank"]["cell_f1"][0.20] == 1.0
    assert result["rank"]["query_score"][0.05] == 0.0
    assert result["rank"]["query_score"][0.20] == 1.0
    assert result["value"]["rel_err_histogram"]["5_to_20pct"] == 1.0


def test_range_error_reports_percentage_points_of_column_span():
    # GT=50, pred=45, column span = 100 → 5 percentage points of the range.
    gold = table_from_rows(
        [{"k": "low", "v": 0}, {"k": "mid", "v": 50}, {"k": "high", "v": 100}],
        key_columns=["k"],
        measure_columns=["v"],
    )
    pred = table_from_rows(
        [{"k": "low", "v": 0}, {"k": "mid", "v": 45}, {"k": "high", "v": 100}],
        key_columns=["k"],
        measure_columns=["v"],
    )
    result = evaluate_aggregation_tables(pred, gold)
    assert result["value"]["column_ranges"]["v"] == {"min": 0.0, "max": 100.0}
    # |45-50|/100 = 0.05 → passes at tau=0.05, fails at tau=0.01.
    assert result["value"]["pass_at_tau"][0.05] == 1.0
    assert result["value"]["pass_at_tau"][0.01] == 2 / 3
    assert result["value"]["rel_err_histogram"]["exact_or_le_1pct"] == 2 / 3
    assert result["value"]["rel_err_histogram"]["5_to_20pct"] == 1 / 3
    assert result["rank"]["structure_score"] == 1.0
    assert result["rank"]["query_score"][0.05] == 1.0
    assert abs(result["rank"]["query_score"][0.01] - (2 / 3)) < 1e-9


def test_junk_rows_penalize_cell_f1_but_not_matched_value_scores():
    gold = table_from_rows(
        [
            {"k": "a", "v": 1},
            {"k": "b", "v": 2},
            {"k": "c", "v": 3},
            {"k": "d", "v": 4},
        ],
        key_columns=["k"],
        measure_columns=["v"],
    )
    pred_rows = [
        {"k": "a", "v": 1},
        {"k": "b", "v": 2},
        {"k": "c", "v": 3},
        {"k": "d", "v": 4},
    ] + [{"k": f"junk{i}", "v": 99} for i in range(12)]
    pred = table_from_rows(
        pred_rows, key_columns=["k"], measure_columns=["v"]
    )
    result = evaluate_aggregation_tables(pred, gold)
    assert result["structure"]["row"]["exact"]["P"] == 4 / 16
    assert result["structure"]["row"]["exact"]["R"] == 1.0
    assert result["value"]["row_recall_context"] == 1.0
    assert result["value"]["pass_at_tau"][0.05] == 1.0
    # 4 TP measure cells, 12 FP junk cells → P=4/16, R=1, F1=0.4
    assert result["rank"]["cell_f1"][0.05] == 0.4
    # structure = row_F1 * col_F1 = (2*P*R/(P+R)) * 1 = 2*(4/16)*1/(4/16+1) = 0.4
    row_f1 = result["structure"]["row"]["semantic"]["F1"]
    assert abs(result["rank"]["structure_score"] - row_f1) < 1e-9
    assert abs(
        result["rank"]["query_score"][0.05]
        - result["rank"]["structure_score"] * 0.4
    ) < 1e-9


def test_synonym_keys_one_to_one_no_double_count():
    gold = table_from_rows(
        [
            {"nation": "United States", "cnt": 10},
            {"nation": "United Kingdom", "cnt": 4},
        ],
        key_columns=["nation"],
        measure_columns=["cnt"],
    )
    pred = table_from_rows(
        [
            {"nation": "USA", "cnt": 10},
            {"nation": "UK", "cnt": 4},
        ],
        key_columns=["nation"],
        measure_columns=["cnt"],
    )
    result = evaluate_aggregation_tables(pred, gold)
    # Exact fails; normalized/semantic succeed via abbreviation map.
    assert result["structure"]["row"]["exact"]["F1"] == 0.0
    assert result["structure"]["row"]["normalized"]["F1"] == 1.0
    assert result["structure"]["row"]["semantic"]["R"] == 1.0
    assert result["structure"]["row"]["semantic"]["P"] == 1.0
    assert result["rank"]["cell_f1"][0.05] == 1.0
    assert result["rank"]["query_score"][0.05] == 1.0

    # One predicted synonym must not claim two gold rows.
    gold_dup = table_from_rows(
        [
            {"nation": "US", "cnt": 10},
            {"nation": "United States", "cnt": 20},
        ],
        key_columns=["nation"],
        measure_columns=["cnt"],
    )
    pred_one = table_from_rows(
        [{"nation": "USA", "cnt": 10}],
        key_columns=["nation"],
        measure_columns=["cnt"],
    )
    one = evaluate_aggregation_tables(pred_one, gold_dup)
    assert one["structure"]["row"]["normalized"]["P"] == 1.0
    assert one["structure"]["row"]["normalized"]["R"] == 0.5
    # One-to-one: a single predicted synonym claims exactly one gold row.
    assert abs(
        one["structure"]["row"]["normalized"]["R"]
        - 1 / 2
    ) < 1e-9


def test_merge_case_fires_merge_rate_and_excludes_value_error():
    gold = table_from_rows(
        [
            {"region": "California East", "sales": 10},
            {"region": "California West", "sales": 20},
        ],
        key_columns=["region"],
        measure_columns=["sales"],
        operators={"sales": "SUM"},
    )
    pred = table_from_rows(
        [{"region": "California", "sales": 30}],
        key_columns=["region"],
        measure_columns=["sales"],
        operators={"sales": "SUM"},
    )
    # Lower theta so "California" soft-matches both region keys via token overlap.
    config = MetricConfig(theta=0.5)
    result = evaluate_aggregation_tables(pred, gold, config=config)
    assert result["grouping"]["merge_rate"] == 1.0
    # Merged row is excluded from value scoring → empty numeric distribution,
    # so catastrophic rate stays 0 instead of recording a fake value error.
    assert result["value"]["rel_err_histogram"] == {
        "exact_or_le_1pct": 0.0,
        "1_to_5pct": 0.0,
        "5_to_20pct": 0.0,
        "20_to_100pct": 0.0,
        "gt_100pct": 0.0,
    }
    assert result["value"]["frac_catastrophic"] == 0.0
    # Vacuous pass when no clean matched cells remain.
    assert result["value"]["pass_at_tau"][0.05] == 1.0


def test_zero_true_cell_uses_range_not_relative_blowup():
    gold = table_from_rows(
        [{"k": "a", "v": 0}, {"k": "b", "v": 10}],
        key_columns=["k"],
        measure_columns=["v"],
    )
    pred = table_from_rows(
        [{"k": "a", "v": 0}, {"k": "b", "v": 10}],
        key_columns=["k"],
        measure_columns=["v"],
    )
    result = evaluate_aggregation_tables(pred, gold)
    assert result["value"]["zero_true_count"] == 1
    assert result["value"]["pass_at_tau"][0.05] == 1.0
    assert result["value"]["column_ranges"]["v"] == {"min": 0.0, "max": 10.0}
    assert math_is_finite_hist(result)

    # Pred=5 vs true=0 with span=10 → range_err=0.5; no division-by-zero blowup.
    pred_bad = table_from_rows(
        [{"k": "a", "v": 5}, {"k": "b", "v": 10}],
        key_columns=["k"],
        measure_columns=["v"],
    )
    bad = evaluate_aggregation_tables(pred_bad, gold)
    assert bad["value"]["zero_true_count"] == 1
    assert bad["value"]["frac_catastrophic"] == 0.0
    assert bad["value"]["rel_err_histogram"]["20_to_100pct"] == 0.5
    assert bad["value"]["rel_err_histogram"]["exact_or_le_1pct"] == 0.5
    assert bad["value"]["pass_at_tau"][0.05] == 0.5


def math_is_finite_hist(result):
    for value in result["value"]["rel_err_histogram"].values():
        assert value == value  # not NaN
        assert value != float("inf")
    return True


def test_canonicalize_is_logged_stage_and_normalizes_numbers():
    assert canonicalize(2023.0, value_type="numeric") == 2023
    assert canonicalize("  USA ", value_type="string") == "united states"
    assert canonicalize("2023/1/2", value_type="date") == "2023-01-02"


def test_column_alignment_reports_key_and_measure_separately():
    gold = AggregationTable(
        columns=(
            ColumnSpec("nationality", "key", "string"),
            ColumnSpec("avg_age", "measure", "numeric", "AVG"),
        ),
        rows=({"nationality": "American", "avg_age": 70},),
    )
    pred = AggregationTable(
        columns=(
            ColumnSpec("nation", "key", "string"),
            ColumnSpec("avg_age", "measure", "numeric", "AVG"),
            ColumnSpec("extra", "measure", "numeric"),
        ),
        rows=({"nation": "American", "avg_age": 70, "extra": 1},),
    )
    config = MetricConfig(theta=0.5)
    result = evaluate_aggregation_tables(pred, gold, config=config)
    assert "key" in result["structure"]["column"]
    assert "measure" in result["structure"]["column"]
    assert "P" in result["structure"]["column"]["key"]
    assert "R" in result["structure"]["column"]["key"]


def test_one_key_one_measure_columns_align_by_role_when_names_differ():
    gold = table_from_rows(
        [{"nationality": "American", "avg_age": 70}],
        key_columns=["nationality"],
        measure_columns=["avg_age"],
    )
    pred = table_from_rows(
        [{"group_label": "American", "metric": 70}],
        key_columns=["group_label"],
        measure_columns=["metric"],
    )
    result = evaluate_aggregation_tables(pred, gold)
    assert result["structure"]["column"]["key"]["F1"] == 1.0
    assert result["structure"]["column"]["measure"]["F1"] == 1.0
    assert result["rank"]["structure_score"] == 1.0
    assert result["rank"]["cell_f1"][0.05] == 1.0
    assert result["rank"]["query_score"][0.05] == 1.0
