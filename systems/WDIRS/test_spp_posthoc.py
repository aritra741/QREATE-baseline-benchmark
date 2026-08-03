"""Tests for evaluation-only SPP post-hoc decomposition."""

from __future__ import annotations

import pytest

from diagnostics.analyze_spp_posthoc import (
    _plan_shape_score,
    _role_align_plan,
    _routing_summary,
)
from spp.spec import (
    AggregateSpec,
    AttributeRef,
    PredicateSpec,
    QueryPlan,
)


def test_plan_shape_score_ignores_symbols_but_preserves_logic():
    generated = QueryPlan(
        group_by=(AttributeRef("record", "category"),),
        aggregates=(
            AggregateSpec(
                "avg", AttributeRef("record", "amount", "real")
            ),
        ),
        predicate=PredicateSpec(
            attribute=AttributeRef("record", "year", "integer"),
            operator=">",
            value=2020,
        ),
    )
    renamed = QueryPlan(
        group_by=(AttributeRef("entry", "segment"),),
        aggregates=(
            AggregateSpec(
                "avg", AttributeRef("entry", "value", "real")
            ),
        ),
        predicate=PredicateSpec(
            attribute=AttributeRef("entry", "calendar_year", "integer"),
            operator=">",
            value=2020,
        ),
    )
    score, agreement = _plan_shape_score(generated, renamed)
    assert score == 1.0
    assert all(agreement.values())

    wrong = QueryPlan(
        group_by=renamed.group_by,
        aggregates=(
            AggregateSpec(
                "max", AttributeRef("entry", "value", "real")
            ),
        ),
    )
    score, agreement = _plan_shape_score(generated, wrong)
    assert score < 1.0
    assert not agreement["aggregates"]
    assert not agreement["predicate"]


def test_role_alignment_preserves_generated_operations_and_literals():
    generated = QueryPlan(
        group_by=(AttributeRef("record", "category"),),
        aggregates=(
            AggregateSpec(
                "avg",
                AttributeRef("record", "amount", "real"),
                "avg_amount",
            ),
        ),
        predicate=PredicateSpec(
            attribute=AttributeRef("record", "year", "integer"),
            operator=">",
            value=2020,
        ),
    )
    reference = QueryPlan(
        group_by=(AttributeRef("entry", "segment"),),
        aggregates=(
            AggregateSpec(
                "avg",
                AttributeRef("entry", "value", "real"),
                "expected_average",
            ),
        ),
        predicate=PredicateSpec(
            attribute=AttributeRef(
                "entry", "calendar_year", "integer"
            ),
            operator=">=",
            value=2019,
        ),
    )
    aligned, conflicts = _role_align_plan(generated, reference)
    assert conflicts == ()
    assert aligned.group_by == (AttributeRef("entry", "segment"),)
    assert aligned.aggregates[0].attribute == AttributeRef(
        "entry", "value", "real"
    )
    assert aligned.aggregates[0].alias == "avg_amount"
    assert aligned.predicate == PredicateSpec(
        attribute=AttributeRef("entry", "calendar_year", "integer"),
        operator=">",
        value=2020,
    )


def test_routing_summary_quantifies_materialized_candidate_regret():
    matrix = {
        "raw": {
            "q0": {"query_score": {"0.2": 0.8}},
            "q1": {"query_score": {"0.2": 0.2}},
        },
        "semantic": {
            "q0": {"query_score": {"0.2": 0.4}},
            "q1": {"query_score": {"0.2": 0.9}},
        },
    }
    result = _routing_summary(
        matrix,
        {"q0": "semantic", "q1": "raw"},
        ("q0", "q1"),
        tau=0.2,
    )
    assert result["selected_mean_query_score"] == pytest.approx(0.3)
    assert result["materialized_oracle_mean_query_score"] == pytest.approx(
        0.85
    )
    assert result["routing_regret"] == pytest.approx(0.55)
    assert result["oracle_query_to_config"] == {
        "q0": "raw",
        "q1": "semantic",
    }
