"""Focused, domain-agnostic intent and physical-schema hardening tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from spp.population_config import PopulationConfig
from spp.spec import (
    AggregateSpec,
    AttributeRef,
    HavingSpec,
    PredicateSpec,
    PreprocessingPolicy,
    QueryPlan,
    QueryRequirement,
    RelationSpec,
    SchemaDesign,
    SynthesisConfig,
)
from spp.system import OfflineSynthesisSystem
from spp.workload_intent import (
    WorkloadIntent,
    _bind_plan_to_entity_vocabulary,
    _canonical_entity,
    _expected_aggregate,
    _expects_group_cardinality_having,
    _plan_contract_diagnostics,
    _normalize_plan_with_schema,
    analyze_workload,
    workload_intent_from_payload,
    workload_intent_to_payload,
)
from spp.wdirs_backend import WDIRSPrimitiveBackend


def test_analyze_workload_canonicalizes_plural_alias_from_shared_evidence():
    intent = analyze_workload(
        [
            "SELECT name, club FROM player",
            (
                "SELECT name, club, COUNT(*) FROM players "
                "WHERE club = 'A' GROUP BY name, club"
            ),
        ]
    )

    assert {entity for req in intent.requirements for entity in req.entities} == {
        "player"
    }
    assert {
        reference.entity
        for req in intent.requirements
        for reference in req.plan.attributes()
    } == {"player"}
    assert intent.requirements[1].plan.predicate.attribute.entity == "player"
    assert {
        reference.entity
        for reference in intent.requirements[1].plan.group_by
    } == {"player"}
    canonicalization = intent.analysis_diagnostics["_workload"][
        "canonicalization"
    ]
    assert canonicalization["entity_aliases"] == {"players": "player"}
    assert canonicalization["alias_evidence"][0]["shared_attributes"] == [
        "club",
        "name",
    ]


def test_source_vocabulary_bounds_high_confidence_entity_aliases():
    vocabulary = ("player", "team", "owner", "city")
    assert _canonical_entity("players", vocabulary) == "player"
    assert _canonical_entity("nba_team", vocabulary) == "team"
    assert _canonical_entity("cities", vocabulary) == ""
    assert _canonical_entity("award", vocabulary) == ""


def test_source_vocabulary_rejects_phantom_sql_plan_entities():
    vocabulary = ("player", "team", "owner", "city")
    assert (
        _bind_plan_to_entity_vocabulary(
            QueryPlan(projections=(AttributeRef("cities", "state"),)),
            vocabulary,
        )
        is None
    )
    assert (
        _bind_plan_to_entity_vocabulary(
            QueryPlan(projections=(AttributeRef("players", "nationality"),)),
            vocabulary,
        )
        == QueryPlan(
            projections=(AttributeRef("player", "nationality"),)
        )
    )


def test_source_vocabulary_is_enforced_across_all_workload_candidates():
    intent = analyze_workload(
        [
            "SELECT name FROM teams",
            "SELECT nationality FROM players",
        ],
        entity_vocabulary=("team", "player", "owner", "city"),
    )
    assert [requirement.entities for requirement in intent.requirements] == [
        ("team",),
        ("player",),
    ]
    assert {
        reference.entity
        for requirement in intent.requirements
        for reference in requirement.plan.attributes()
    } == {"team", "player"}


def test_workload_rejects_unresolved_entities_outside_source_partitions():
    with pytest.raises(
        ValueError,
        match="outside the observed source partitions",
    ):
        analyze_workload(
            ["SELECT nationality FROM people"],
            entity_vocabulary=("team", "player", "owner", "city"),
        )


def test_presence_boolean_is_rewritten_to_numeric_measure_filter():
    measure = AttributeRef("record", "title_count", "integer")
    normalized = _normalize_plan_with_schema(
        QueryPlan(
            aggregates=(AggregateSpec("sum", measure, "total_titles"),),
            predicate=PredicateSpec(
                attribute=AttributeRef(
                    "record",
                    "has_world_title",
                    "boolean",
                ),
                operator="=",
                value=True,
            ),
        ),
        "Among records with at least one world title, show total titles.",
    )
    assert normalized is not None
    assert normalized.predicate == PredicateSpec(
        attribute=measure,
        operator=">=",
        value=1,
    )


def test_boolean_normalization_preserves_nested_scope():
    first = PredicateSpec(
        attribute=AttributeRef("event", "kind"),
        operator="=",
        value="a",
    )
    second = PredicateSpec(
        attribute=AttributeRef("event", "kind"),
        operator="=",
        value="b",
    )
    active = PredicateSpec(
        attribute=AttributeRef("event", "active", "boolean"),
        operator="=",
        value=True,
    )
    predicate = PredicateSpec(
        kind="and",
        children=(
            PredicateSpec(kind="or", children=(first, second)),
            active,
        ),
    )
    normalized = _normalize_plan_with_schema(
        QueryPlan(
            projections=(AttributeRef("event", "name"),),
            predicate=predicate,
        ),
        "Show active events whose kind is either a or b.",
    )
    assert normalized is not None
    assert normalized.predicate == predicate


def test_workload_intent_contains_no_benchmark_domain_literals():
    source = (
        Path(__file__).parent / "spp" / "workload_intent.py"
    ).read_text(encoding="utf-8").lower()
    for term in (
        "player",
        "team",
        "city",
        "college",
        "nba",
        "fiba",
        "mvp",
        "olympic",
        "championship",
        "drafted",
        "founded",
        "aged",
    ):
        assert not re.search(rf"\b{term}s?\b", source), term


def test_canonical_workload_intent_json_round_trip():
    intent = analyze_workload(
        ["SELECT team, COUNT(*) FROM player GROUP BY team"]
    )
    restored = workload_intent_from_payload(
        json.loads(json.dumps(workload_intent_to_payload(intent)))
    )
    assert restored == intent


def test_group_cardinality_having_is_not_confused_with_scalar_magnitude():
    assert _expects_group_cardinality_having(
        "Among categories with more than one event, show the maximum amount."
    )
    assert not _expects_group_cardinality_having(
        "Among cities with more than one million people, show the maximum GDP."
    )


def test_all_player_nl_aggregation_queries_have_generic_operation_cues():
    workload_path = (
        Path(__file__).resolve().parents[2]
        / "case study"
        / "docetl_Player_v7"
        / "query_manifest_nl.json"
    )
    rows = json.loads(workload_path.read_text(encoding="utf-8"))
    expected = {
        "q0": "avg", "q1": "count", "q2": "avg", "q3": "max",
        "q4": "sum", "q5": "max", "q6": "count", "q7": "min",
        "q8": "avg", "q9": "count", "q10": "sum", "q11": "count",
        "q12": "max", "q13": "count", "q14": "sum", "q15": "avg",
        "q16": "avg", "q17": "min", "q18": "avg", "q19": "max",
    }
    assert {row["query_id"] for row in rows} == set(expected)
    for row in rows:
        assert _expected_aggregate(row["text"]) == expected[row["query_id"]]
        violations = _plan_contract_diagnostics(
            QueryRequirement(row["query_id"], row["text"])
        )
        assert "missing_plan_for_aggregate" in violations
        assert "missing_plan_for_group" in violations
    q3 = next(row for row in rows if row["query_id"] == "q3")
    assert "missing_plan_for_having" in _plan_contract_diagnostics(
        QueryRequirement("q3", q3["text"])
    )


def test_canonicalization_does_not_merge_unrelated_single_field_entities():
    intent = analyze_workload(
        [
            "SELECT name FROM vessel",
            "SELECT name FROM archive",
            "SELECT title, era FROM artifact",
            "SELECT title, era FROM artifacts",
        ]
    )

    entities = {entity for req in intent.requirements for entity in req.entities}
    assert {"vessel", "archive", "artifact"} <= entities
    assert "artifacts" not in entities
    aliases = intent.analysis_diagnostics["_workload"]["canonicalization"][
        "entity_aliases"
    ]
    assert aliases == {"artifacts": "artifact"}


def test_plan_contract_diagnostics_are_hard_and_domain_agnostic():
    missing = QueryRequirement(
        query_id="q",
        text=(
            "What is the average amount for each category where amount is "
            "greater than 5?"
        ),
        entities=("event",),
        attributes=("amount", "category"),
        operators=("avg", "group_by", "filter"),
        plan=QueryPlan(projections=(AttributeRef("event", "category"),)),
    )
    assert set(_plan_contract_diagnostics(missing)) == {
        "missing_or_wrong_aggregate",
        "missing_group_by",
        "missing_filter",
    }

    complete = QueryRequirement(
        query_id="q",
        text=missing.text,
        entities=("event",),
        operators=missing.operators,
        plan=QueryPlan(
            group_by=(AttributeRef("event", "category"),),
            aggregates=(),
            predicate=PredicateSpec(
                attribute=AttributeRef("event", "amount", "real"),
                operator=">",
                value=5,
            ),
        ),
    )
    assert _plan_contract_diagnostics(complete) == (
        "missing_or_wrong_aggregate",
        "group_by_without_aggregate",
    )


def test_having_does_not_require_a_duplicate_where_filter():
    category = AttributeRef("event", "category")
    requirement = QueryRequirement(
        "q",
        "Among categories with more than one event, show the highest amount.",
        operators=("max", "group_by", "filter", "having"),
        plan=QueryPlan(
            group_by=(category,),
            aggregates=(
                AggregateSpec(
                    "max",
                    AttributeRef("event", "amount", "real"),
                ),
            ),
            having=(
                HavingSpec(AggregateSpec("count"), ">", 1),
            ),
        ),
    )
    assert _plan_contract_diagnostics(requirement) == ()


def test_normalization_recovers_known_dimension_filter_generically():
    category = AttributeRef("event", "category")
    plan = QueryPlan(
        group_by=(category,),
        aggregates=(
            AggregateSpec(
                "sum",
                AttributeRef("event", "amount", "real"),
            ),
        ),
    )
    normalized = _normalize_plan_with_schema(
        plan,
        "Among events with a known category, total the amount at each category.",
    )
    assert normalized is not None
    assert normalized.predicate == PredicateSpec(
        attribute=category,
        operator="is_not_null",
    )


def test_system_rejects_contract_failure_before_candidate_generation(tmp_path):
    requirement = QueryRequirement(
        "q",
        "Average amount for each category.",
        entities=("event",),
        attributes=("amount", "category"),
        operators=("avg", "group_by"),
        plan=QueryPlan(projections=(AttributeRef("event", "category"),)),
    )
    intent = WorkloadIntent(
        (requirement,),
        {"event": 1},
        {"amount": 1, "category": 1},
        {"avg": 1, "group_by": 1},
    )
    system = OfflineSynthesisSystem(
        object(),
        lambda *_args: "",
        intent_analyzer=lambda _queries, _ledger: intent,
    )

    with pytest.raises(ValueError, match="workload plan contract failed"):
        system.synthesize(
            queries=[requirement.text],
            token_budget=100,
            output_dir=tmp_path / "output",
        )


class _Layer:
    def __init__(self, tables):
        self.tables = tables

    def table_exists(self, table):
        return table in self.tables

    def get_all_records(self, table):
        return list(self.tables[table])


def _backend(tables, intent, tmp_path: Path) -> WDIRSPrimitiveBackend:
    lattice = type("Lattice", (), {"tables": {}})()
    runner = type(
        "Runner",
        (),
        {
            "llm_client": object(),
            "data_layer": _Layer(tables),
            "lattice_planner": type("Planner", (), {"lattice": lattice})(),
            "dataset": "Synthetic",
            "cache_dir": tmp_path / "cache",
            "enable_attribute_discovery": False,
        },
    )()
    backend = WDIRSPrimitiveBackend(runner, scratch_dir=tmp_path / "scratch")
    backend.intent = intent
    backend._table_names = sorted(tables)
    return backend


def test_physical_gate_removes_all_null_and_phantom_query_coverage(tmp_path):
    valid = QueryRequirement(
        "valid",
        "List event labels.",
        entities=("event",),
        attributes=("label",),
        attribute_bindings=(("event", "label"),),
    )
    null = QueryRequirement(
        "null",
        "List event amounts.",
        entities=("event",),
        attributes=("amount",),
        attribute_bindings=(("event", "amount"),),
    )
    phantom = QueryRequirement(
        "phantom",
        "List archive titles.",
        entities=("archive",),
        attributes=("title",),
        attribute_bindings=(("archive", "title"),),
    )
    intent = WorkloadIntent(
        (valid, null, phantom),
        {"event": 2, "archive": 1},
        {"label": 1, "amount": 1, "title": 1},
        {},
    )
    schema = SchemaDesign(
        "snowflake",
        (
            RelationSpec("event", ("label", "amount")),
            RelationSpec("archive", ("title",)),
        ),
        ("valid", "null", "phantom"),
    )
    config = SynthesisConfig(
        schema,
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    backend = _backend(
        {"event": [{"label": "Launch", "amount": None}]},
        intent,
        tmp_path,
    )

    result = backend.prune_configs((config,))

    assert len(result) == 1
    assert result[0].schema.covered_query_ids == ("valid",)
    assert backend._physical_requirement_issues == {
        "null": ["all_null_required_column:event.amount"],
        "phantom": ["missing_physical_table:archive"],
    }


def test_physical_gate_removes_unbindable_multi_relation_plan(tmp_path):
    category = AttributeRef("event", "category")
    amount = AttributeRef("account", "amount", "real")
    requirement = QueryRequirement(
        "q",
        "For each event category, total the account amount.",
        entities=("event", "account"),
        plan=QueryPlan(
            group_by=(category,),
            aggregates=(AggregateSpec("sum", amount, "total_amount"),),
        ),
    )
    intent = WorkloadIntent(
        (requirement,),
        {"event": 1, "account": 1},
        {"category": 1, "amount": 1},
        {"sum": 1, "group_by": 1},
    )
    config = SynthesisConfig(
        SchemaDesign(
            "snowflake",
            (
                RelationSpec("event", ("category",)),
                RelationSpec("account", ("amount",)),
            ),
            ("q",),
        ),
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    backend = _backend(
        {
            "event": [{"category": "a"}],
            "account": [{"amount": 2}],
        },
        intent,
        tmp_path,
    )
    assert backend.prune_configs((config,)) == ()
    assert backend._physical_requirement_issues == {}
    assert backend._physical_config_issues[config.config_id] == {
        "q": "typed query plan cannot bind to candidate schema"
    }


def test_cache_fingerprint_rejects_different_canonical_workload(tmp_path):
    first = WorkloadIntent(
        (QueryRequirement("q", "List labels.", entities=("event",)),),
        {"event": 1},
        {},
        {},
    )
    second = WorkloadIntent(
        (QueryRequirement("q", "List titles.", entities=("archive",)),),
        {"archive": 1},
        {},
        {},
    )
    backend = _backend({}, first, tmp_path)
    Path(backend.runner.cache_dir).mkdir(parents=True)

    backend._fingerprint_cache_state(first)
    with pytest.raises(ValueError, match="fingerprint does not match"):
        backend._fingerprint_cache_state(second)
