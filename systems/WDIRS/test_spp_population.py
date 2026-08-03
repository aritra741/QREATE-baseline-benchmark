"""Focused regression tests for the WDIRS-backed SPP configuration grid."""

import sys
import types

import pytest

from spp.config_grid import (
    ConfigGridResult,
    SQLExecutionError,
    _build_in_memory_db,
    _execute_sql,
    build_viable_config_search_space,
    official_query_error,
)
from spp.population import (
    _parse_llm_json,
    apply_population,
    repair_join_columns_from_overlap,
)
from spp.population_config import (
    PopulationConfig,
    encode_config_features,
    generate_config_space,
    parse_config_id,
)
from diagnostics.run_config_grid import load_ground_truth


def test_full_population_space_includes_type_coercion_axis():
    configs = generate_config_space()
    assert len(configs) == 288
    assert len(encode_config_features(configs[0])) == 17
    assert parse_config_id("er=llm|norm=llm|unit=unit|miss=llm").type_coercion == "strict"


def test_permissive_type_coercion_extracts_embedded_number():
    records = [{"amount": "pick 12"}, {"amount": "13"}]
    semantic_types = {"amount": "QUANTITY"}
    strict, _ = apply_population(
        records,
        PopulationConfig(type_coercion="strict", miss_strategy="mode"),
        column_semantic_types=semantic_types,
    )
    permissive, _ = apply_population(
        records,
        PopulationConfig(type_coercion="permissive", miss_strategy="mode"),
        column_semantic_types=semantic_types,
    )
    assert strict[0]["amount"] == 13.0
    assert permissive[0]["amount"] == 12.0


def test_categorical_missing_values_are_handled_when_numeric_columns_exist():
    records = [
        {"category": "A", "amount": 1},
        {"category": None, "amount": 2},
        {"category": "A", "amount": 3},
    ]
    populated, _ = apply_population(
        records,
        PopulationConfig(miss_strategy="mode"),
        column_semantic_types={"category": "OTHER", "amount": "QUANTITY"},
    )
    assert populated[1]["category"] == "A"


def test_population_json_parser_handles_qwen_malformed_outputs():
    assert _parse_llm_json("[[0, 1]]\nextra explanation", list) == [[0, 1]]
    assert _parse_llm_json(
        '{"A\\_B": "A B", "C": "C"', dict
    ) == {"A\\_B": "A B", "C": "C"}


def test_rich_entity_resolution_applies_lowercase_canonical_map_keys(monkeypatch):
    class EntityMention:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "entity_resolver",
        types.SimpleNamespace(EntityMention=EntityMention),
    )

    class Result:
        canonical_map = {"alice smith": "Alice Smith"}

    class Resolver:
        def resolve_entities(self, *args, **kwargs):
            return Result()

    populated, _ = apply_population(
        [{"name": "ALICE SMITH"}, {"name": "A. Smith"}],
        PopulationConfig(miss_strategy="mode"),
        column_semantic_types={"name": "PERSON"},
        identity_columns=["name"],
        entity_resolver=Resolver(),
    )
    assert populated[0]["name"] == "Alice Smith"


def test_llm_normalization_does_not_modify_bookkeeping_columns():
    populated, _ = apply_population(
        [{"row_id": "abc", "name": "  Alice  "}],
        PopulationConfig(norm_strategy="llm", miss_strategy="mode"),
        llm_normalize_fn=lambda _value: "NORMALIZED",
    )
    assert populated[0]["row_id"] == "abc"
    assert populated[0]["name"] == "NORMALIZED"


def test_llm_normalization_preserves_case_only_surface_forms():
    populated, _ = apply_population(
        [{"country": "Canada"}],
        PopulationConfig(norm_strategy="llm", miss_strategy="mode"),
        llm_normalize_fn=lambda _value: "canada",
    )
    assert populated[0]["country"] == "Canada"


def test_grouped_categorical_column_can_use_source_observed_abstraction():
    class LLM:
        prompts = []

        def generate(self, prompt, **_kwargs):
            self.prompts.append(prompt)
            return '{"Left Wing": "Attack", "Right Wing": "Attack", "Goalkeeper": "Defense"}'

    llm = LLM()
    populated, _ = apply_population(
        [
            {"role": "Left Wing"},
            {"role": "Right Wing"},
            {"role": "Goalkeeper"},
        ],
        PopulationConfig(norm_strategy="dictionary", miss_strategy="drop"),
        table_name="person",
        protected_columns=["role"],
        abstraction_columns=["role"],
        abstraction_hints={
            "role": "Report the average score for each broad role."
        },
        llm_client=llm,
        source_context=(
            "Left Wing and Right Wing belong to the Attack category. "
            "A Goalkeeper belongs to the Defense category."
        ),
    )
    assert [row["role"] for row in populated] == [
        "Attack",
        "Attack",
        "Defense",
    ]
    assert "source-grounded" in llm.prompts[0].lower()
    assert "expected answers" in llm.prompts[0].lower()
    assert "relevant source excerpts" in llm.prompts[0].lower()
    assert "natural-language grouping requests" in llm.prompts[0].lower()


def test_sparse_join_columns_are_rebound_by_populated_value_overlap():
    left = [
        {"foreign_id": 10, "organization_name": "Alpha"},
        {"foreign_id": 20, "organization_name": "Beta"},
    ]
    right = [
        {"id": 1, "name": "Alpha"},
        {"id": 2, "name": "Beta"},
    ]
    repaired = repair_join_columns_from_overlap(
        left, "foreign_id", right, "id"
    )
    assert repaired == ("organization_name", "name")
    assert [row["foreign_id"] for row in left] == ["Alpha", "Beta"]
    assert [row["id"] for row in right] == ["Alpha", "Beta"]


def test_tiny_exact_id_overlap_does_not_override_broad_name_overlap():
    left = [
        {"foreign_id": 1, "organization_name": "Alpha"},
        {"foreign_id": 20, "organization_name": "Beta"},
        {"foreign_id": 30, "organization_name": "Gamma"},
    ]
    right = [
        {"id": 1, "name": "Alpha"},
        {"id": 2, "name": "Beta"},
        {"id": 3, "name": "Gamma"},
    ]
    repaired = repair_join_columns_from_overlap(
        left,
        "foreign_id",
        right,
        "id",
        left_table="member",
        right_table="organization",
    )
    assert repaired == ("organization_name", "name")


def test_workload_columns_are_not_fabricated_by_imputation():
    populated, _ = apply_population(
        [
            {"category": "A", "measure": 1},
            {"category": None, "measure": None},
        ],
        PopulationConfig(miss_strategy="mode"),
        column_semantic_types={
            "category": "text",
            "measure": "integer",
        },
        protected_columns=["category", "measure"],
    )
    assert populated[1] == {"category": None, "measure": None}


def test_lowercase_semantic_numeric_types_are_respected():
    populated, _ = apply_population(
        [{"amount": "USD 12"}, {"amount": "13"}],
        PopulationConfig(
            type_coercion="permissive", miss_strategy="mode"
        ),
        column_semantic_types={"amount": "real"},
    )
    assert populated[0]["amount"] == 12.0


def test_empty_populated_table_keeps_schema_and_sql_errors_are_not_empty_results():
    conn = _build_in_memory_db(
        {"player": []},
        table_schemas={"player": {"age": "QUANTITY"}},
    )
    assert _execute_sql(conn, "SELECT age FROM player") == []
    with pytest.raises(SQLExecutionError):
        _execute_sql(conn, "SELECT missing FROM player")
    conn.close()


def test_flat_queries_do_not_make_every_config_ever_optimal():
    grid = ConfigGridResult(
        n_queries=2,
        config_space_size=2,
        per_config={
            "a": {
                "per_query": [
                    {"query_id": "flat", "query_error": 1.0},
                    {"query_id": "signal", "query_error": 0.0},
                ]
            },
            "b": {
                "per_query": [
                    {"query_id": "flat", "query_error": 1.0},
                    {"query_id": "signal", "query_error": 1.0},
                ]
            },
        },
    )
    report = build_viable_config_search_space(grid)
    assert report["ever_optimal_config_ids"] == ["a"]
    assert report["n_ever_optimal_including_flat_queries"] == 2
    assert report["n_behaviorally_distinct_error_profiles"] == 2


def test_official_query_error_uses_column_macro_f1():
    attributes = {
        "player": {
            "name": {"value_type": "str"},
            "age": {"value_type": "int"},
        }
    }
    sql = "SELECT name, age FROM player"
    gold = [{"name": "Alice", "age": 30}]
    assert official_query_error(sql, gold, list(gold), attributes) == 0.0
    assert official_query_error(
        sql, gold, [{"name": "Alice", "age": 40}], attributes
    ) > 0.0
    assert official_query_error(sql, [], [], attributes) == 0.0
    assert official_query_error(sql, [], gold, attributes) == 1.0


def test_player_ground_truth_is_trimmed_and_join_aligned():
    ground_truth = load_ground_truth("Player")
    conn = _build_in_memory_db(ground_truth)
    rows = _execute_sql(
        conn,
        "SELECT COUNT(*) AS n FROM player "
        "JOIN team ON player.team = team.team_name "
        "JOIN owner ON team.ownership = owner.name",
    )
    conn.close()
    assert rows[0]["n"] > 0
