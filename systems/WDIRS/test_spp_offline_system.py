"""Regression tests for the offline, budgeted SPP system layer."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

from data_layer import DataLayer
from lattice_planner import LatticePlanner
from extractor import ConstrainedExtractor, ExtractionResult
from spp.budget_ledger import BudgetExhausted, GlobalBudgetLedger
from spp.budgeted_llm import BudgetedLLMClient
from spp.corpus_subset import build_representative_subset
from spp.evidence_store import (
    CellProvenance,
    ContractEvidence,
    DerivationLineage,
    EvidenceAnchor,
    EvidenceStore,
    ValidationOutcome,
)
from spp.experiment import (
    docetl_relative_budgets,
    evaluate_frozen_bundle,
    paired_noninferiority_report,
    selector_top_k_recall,
    summarize_accuracy_cost_frontier,
)
from spp.optimizer import (
    PilotResult,
    canonical_output_signature,
    collapse_output_equivalent,
    diverse_candidate_order,
    progressive_pilot_search,
    select_budgeted_portfolio,
)
from spp.operator_dag import OperatorNode, SharedOperatorDAG
from spp.native_backend import (
    NativeSPPBackend,
    SourceDocument,
    infer_source_entity_vocabulary,
    preprocess_documents,
)
from spp.nl2sql import (
    _semantic_validation_errors,
    _verification_payload,
    make_nl2sql_compiler,
)
from spp.oracle_evaluation import OracleConfigResult, solve_exact_budgeted_oracle
from spp.risk_estimator import CellEvidence, PilotObservation, estimate_query_risk
from spp.quality_signals import (
    MetamorphicCheck,
    metamorphic_consistency,
    profile_relational_database,
)
from spp.schema_materializer import (
    reshape_tables,
    temporary_work_dir,
    write_sqlite_database,
)
from spp.schema_design import generate_schema_designs, generate_synthesis_configs
from spp.query_plan_compiler import compile_query_plan
from spp.sql_validator import validate_sql
from spp.serving import (
    CompiledQuery,
    OfflineQueryServer,
    compile_workload_sql,
    freeze_serving_bundle,
)
from spp.system import OfflineSynthesisSystem
from spp.value_normalization import canonical_date
from spp.spec import (
    AggregateSpec,
    AttributeRef,
    FrozenPortfolio,
    HavingSpec,
    JoinSpec,
    PreprocessingPolicy,
    PredicateSpec,
    QualityEstimate,
    QueryPlan,
    QueryRequirement,
    RelationSpec,
    SchemaDesign,
    SynthesisConfig,
)
from spp.workload_intent import (
    WorkloadIntent,
    _canonicalize_workload_requirements,
    _finalize_requirement_plan,
    _normalize_plan_with_schema,
    _parse_llm_payload,
    _plan_contract_score,
    _plan_from_clause_ledger,
    analyze_sql_contract_workload,
    analyze_workload,
    schema_vocabulary_from_sql,
)
from spp.wdirs_backend import WDIRSPrimitiveBackend
from spp.population_config import PopulationConfig


def _player_requirement() -> QueryRequirement:
    return QueryRequirement(
        query_id="q0",
        text="SELECT name FROM player",
        entities=("player",),
        attributes=("name",),
    )


def test_workload_canonicalization_unifies_inflectional_plan_entities():
    singular_position = AttributeRef("record", "category")
    plural_measure = AttributeRef("records", "amount", "real")
    requirement = QueryRequirement(
        query_id="q0",
        text="Average amount by record category.",
        entities=("record", "records"),
        attributes=("category", "amount"),
        attribute_bindings=(
            ("record", "category"),
            ("records", "amount"),
        ),
        operators=("avg", "group_by", "filter"),
        plan=QueryPlan(
            group_by=(singular_position,),
            aggregates=(
                AggregateSpec("avg", plural_measure, "avg_amount"),
            ),
            predicate=PredicateSpec(
                attribute=singular_position,
                operator="is_not_null",
                value=None,
            ),
        ),
    )

    canonical, metadata = _canonicalize_workload_requirements((requirement,))

    normalized = canonical[0]
    assert normalized.entities == ("record",)
    assert {reference.entity for reference in normalized.plan.attributes()} == {
        "record"
    }
    assert {
        item["alias"] for item in metadata["alias_evidence"]
    } == {"records"}


def test_representative_subset_is_partitioned_and_relevance_ranked(
    tmp_path: Path,
):
    source = tmp_path / "source" / "Example"
    for entity in ("account", "transaction"):
        (source / entity).mkdir(parents=True)
    (source / "account" / "1.txt").write_text("ordinary account")
    (source / "account" / "2.txt").write_text("priority north account")
    (source / "transaction" / "1.txt").write_text("ordinary transaction")
    (source / "transaction" / "2.txt").write_text(
        "priority north transaction"
    )
    root, selected = build_representative_subset(
        source,
        ["Show priority transactions in the north"],
        tmp_path / "subset",
        max_documents_per_entity=1,
        max_document_characters=8,
    )
    assert root == tmp_path / "subset"
    assert selected == ["account/2.txt", "transaction/2.txt"]
    assert (root / "Example" / "account" / "2.txt").is_file()
    assert (root / "Example" / "transaction" / "2.txt").is_file()
    assert (
        root / "Example" / "account" / "2.txt"
    ).read_text() == "priority"


def test_budgeted_client_prefers_call_local_provider_usage():
    class UsageClient:
        model = "test"

        def __init__(self):
            self.usage = None

        def clear_last_usage(self):
            self.usage = None

        def consume_last_usage(self):
            usage, self.usage = self.usage, None
            return usage

        def generate(self, *_args, **_kwargs):
            self.usage = (7, 3)
            return "ok"

    ledger = GlobalBudgetLedger(1_000)
    client = BudgetedLLMClient(
        UsageClient(), ledger, default_stage="test"
    )
    assert client.generate("prompt", max_tokens=100) == "ok"
    assert ledger.actual_spent == 10


def _config(label: str, requirement: QueryRequirement) -> SynthesisConfig:
    relation = RelationSpec(
        name="player", attributes=("name",), primary_key="name"
    )
    schema = SchemaDesign(
        pattern=label,
        relations=(relation,),
        covered_query_ids=(requirement.query_id,),
    )
    return SynthesisConfig(
        schema=schema,
        population=PopulationConfig(
            er_strategy="embedding_0.8",
            miss_strategy="mode",
        ),
        preprocessing=PreprocessingPolicy(strategy="whole_document"),
    )


def _estimate(
    requirement: QueryRequirement, config: SynthesisConfig, score: float
) -> QualityEstimate:
    return QualityEstimate(
        query_id=requirement.query_id,
        config_id=config.config_id,
        precision_proxy=score,
        recall_proxy=score,
        validity=1.0,
        uncertainty=0.0,
        sample_size=10,
    )


def test_budget_ledger_reserves_reconciles_and_charges_failures(tmp_path: Path):
    ledger = GlobalBudgetLedger(100)
    reservation = ledger.reserve(
        stage="pilot",
        operation="extract",
        input_tokens=20,
        max_output_tokens=30,
        config_id="c",
    )
    assert reservation is not None
    assert ledger.available == 50
    ledger.reconcile(reservation, input_tokens=20, output_tokens=5, error="timeout")
    assert ledger.actual_spent == 25
    assert ledger.available == 75
    with pytest.raises(BudgetExhausted):
        ledger.reserve(
            stage="final",
            operation="extract",
            input_tokens=60,
            max_output_tokens=20,
        )
    ledger.save(tmp_path / "ledger.json")
    assert json.loads((tmp_path / "ledger.json").read_text())["actual_spent"] == 25
    assert 10_846_866 in docetl_relative_budgets(54_234_332)


def test_progressive_search_preserves_escrowed_completion_candidate():
    requirement = _player_requirement()
    cheap = _config("cheap", requirement)
    expensive = _config("expensive", requirement)
    costs = {cheap.config_id: 60, expensive.config_id: 80}
    ledger = GlobalBudgetLedger(100)
    escrow = ledger.reserve(
        stage="completion_escrow",
        operation="reserve_full_materialization",
        input_tokens=60,
        max_output_tokens=0,
    )
    assert escrow is not None

    def evaluate(config, sample_fraction, active_ledger):
        reservation = active_ledger.reserve(
            stage="pilot",
            operation="extract",
            input_tokens=30,
            max_output_tokens=0,
            config_id=config.config_id,
        )
        assert reservation is not None
        active_ledger.reconcile(
            reservation, input_tokens=30, output_tokens=0
        )
        return PilotResult(
            config_id=config.config_id,
            estimates={
                requirement.query_id: _estimate(
                    requirement, config, 0.5
                )
            },
            output_signature=config.config_id,
            full_cost_upper_bound=costs[config.config_id],
            sample_fraction=sample_fraction,
        )

    result = progressive_pilot_search(
        [expensive, cheap],
        [requirement],
        evaluate,
        ledger,
        sample_fractions=(0.1,),
        completion_reserve=60,
        completion_costs=costs,
        completion_escrowed=True,
    )
    ledger.cancel(escrow, reason="test completion")

    assert result.survivors == [cheap.config_id]
    assert ledger.available == 70


def test_join_workload_requires_a_relationship_preserving_schema():
    intent = analyze_workload(
        [
            {
                "query_id": "q0",
                "sql": (
                    "SELECT player.name, team.location FROM player "
                    "JOIN team ON player.team = team.team_name"
                ),
            }
        ]
    )
    assert intent.has_joins
    assert {"player", "team"} <= set(intent.requirements[0].entities)
    designs = generate_schema_designs(intent)
    assert {design.pattern for design in designs} == {
        "denormalized",
        "star",
        "snowflake",
    }
    by_pattern = {design.pattern: design for design in designs}
    assert not by_pattern["denormalized"].covers(
        intent.requirements[0]
    )
    assert by_pattern["star"].covers(intent.requirements[0])
    assert by_pattern["snowflake"].covers(intent.requirements[0])
    pruned = generate_synthesis_configs(intent, observed_document_lengths=[500])
    exhaustive = generate_synthesis_configs(
        intent, observed_document_lengths=[500], exhaustive=True
    )
    assert len(pruned) < len(exhaustive)


def test_sql_contract_workload_preserves_exact_plan():
    intent = analyze_sql_contract_workload(
        [
            {
                "query_id": "q0",
                "sql_query": (
                    "SELECT team.name, AVG(player.age) AS avg_player_age "
                    "FROM team JOIN player ON team.name = player.team "
                    "WHERE player.age >= 21 GROUP BY team.name"
                ),
                "nl_query": (
                    "For each team, what is the average age of players aged "
                    "at least 21?"
                ),
            }
        ]
    )

    requirement = intent.requirements[0]
    assert requirement.text.startswith("SELECT team.name")
    assert requirement.entities == ("team", "player")
    assert requirement.plan == QueryPlan(
        projections=(AttributeRef("team", "name"),),
        group_by=(AttributeRef("team", "name"),),
        aggregates=(
            AggregateSpec(
                "avg",
                AttributeRef("player", "age", "real"),
                "avg_player_age",
            ),
        ),
        predicate=PredicateSpec(
            attribute=AttributeRef("player", "age", "integer"),
            operator=">=",
            value=21,
        ),
        joins=(
            JoinSpec(
                AttributeRef("team", "name"),
                AttributeRef("player", "team"),
            ),
        ),
    )
    assert intent.analysis_diagnostics["_workload"]["input_mode"] == (
        "sql_contract"
    )


def test_sql_contract_workload_rejects_non_sql_and_duplicate_ids():
    with pytest.raises(ValueError, match="SELECT/WITH"):
        analyze_sql_contract_workload(
            [{"query_id": "q0", "sql_query": "Count records."}]
        )
    with pytest.raises(ValueError, match="duplicate"):
        analyze_sql_contract_workload(
            [
                {"query_id": "q0", "sql_query": "SELECT name FROM record"},
                {"query_id": "q0", "sql_query": "SELECT value FROM record"},
            ]
        )


def test_sql_contract_expands_in_and_between_predicates():
    intent = analyze_sql_contract_workload(
        [
            {
                "query_id": "in",
                "sql_query": (
                    "SELECT category, COUNT(*) AS count_all FROM record "
                    "WHERE category IN ('A', 'B') GROUP BY category"
                ),
            },
            {
                "query_id": "between",
                "sql_query": (
                    "SELECT category, AVG(value) AS avg_value FROM record "
                    "WHERE value BETWEEN 20 AND 40 GROUP BY category"
                ),
            },
        ]
    )

    in_predicate = intent.requirements[0].plan.predicate
    assert in_predicate is not None
    assert in_predicate.kind == "or"
    assert tuple(child.value for child in in_predicate.children) == ("A", "B")

    between_predicate = intent.requirements[1].plan.predicate
    assert between_predicate is not None
    assert between_predicate.kind == "and"
    assert tuple(
        (child.operator, child.value)
        for child in between_predicate.children
    ) == ((">=", 20), ("<=", 40))


def test_qwen_null_intent_fields_are_treated_as_empty():
    requirements = _parse_llm_payload(
        '[{"query_id":"q0","entities":["player"],"attributes":["name"],'
        '"attribute_bindings":null,"relationships":null,"operators":null,'
        '"units":null}]',
        {"q0": "List player names."},
    )
    assert requirements[0].entities == ("player",)
    assert requirements[0].relationships == ()

    malformed = _parse_llm_payload(
        '[{"query_id":"q0" "entities":["player"],'
        '"attributes":["name"]',
        {"q0": "List player names."},
    )
    assert malformed[0].entities == ("player",)
    assert malformed[0].attributes == ("name",)

    object_entity = _parse_llm_payload(
        '[{"query_id":"q0","entities":'
        '[{"name":"player","semantic_type":"text"}],'
        '"attributes":["name"]}]',
        {"q0": "List player names."},
    )
    assert object_entity[0].entities == ("player",)


def test_typed_plan_prunes_unused_top_level_schema_symbols():
    requirement = _parse_llm_payload(
        """
        [{
          "query_id": "q0",
          "entities": ["account", "place"],
          "attributes": ["category", "name"],
          "attribute_bindings": [
            {"entity": "account", "attribute": "category"},
            {"entity": "place", "attribute": "name"}
          ],
          "relationships": [
            {"left": "account", "relation": "join", "right": "place"}
          ],
          "operators": ["count", "group_by"],
          "plan": {
            "projections": [
              {"entity": "account", "attribute": "category"}
            ],
            "group_by": [
              {"entity": "account", "attribute": "category"}
            ],
            "aggregates": [
              {"function": "count", "attribute": null, "alias": "count_all"}
            ],
            "predicate": null,
            "joins": [],
            "having": []
          }
        }]
        """,
        {"q0": "How many accounts are there for each category?"},
    )[0]

    assert requirement.entities == ("account",)
    assert requirement.attributes == ("category",)
    assert requirement.attribute_bindings == (("account", "category"),)
    assert requirement.relationships == ()


def test_single_mentioned_entity_owns_all_typed_plan_attributes():
    requirement = _parse_llm_payload(
        """
        [{
          "query_id": "q0",
          "entities": ["record", "group"],
          "attribute_bindings": [
            {"entity": "record", "attribute": "category"},
            {"entity": "group", "attribute": "amount"}
          ],
          "operators": ["avg", "group_by"],
          "plan": {
            "projections": [
              {"entity": "record", "attribute": "category"}
            ],
            "group_by": [
              {"entity": "record", "attribute": "category"}
            ],
            "aggregates": [{
              "function": "avg",
              "attribute": {
                "entity": "group",
                "attribute": "amount",
                "semantic_type": "real"
              },
              "alias": "avg_amount"
            }],
            "predicate": null,
            "joins": [],
            "having": []
          }
        }]
        """,
        {"q0": "What is the average record amount for each category?"},
        entity_vocabulary=("record", "group"),
    )[0]

    assert requirement.entities == ("record",)
    assert {
        reference.entity for reference in requirement.plan.attributes()
    } == {"record"}
    assert requirement.attribute_bindings == (
        ("record", "category"),
        ("record", "amount"),
    )


def test_final_plan_boundary_repairs_overwritten_aggregate():
    position = AttributeRef("record", "category")
    measure = AttributeRef("record", "award_count", "integer")
    requirement = QueryRequirement(
        "q0",
        "What is the total number of awards at each category?",
        entities=("record",),
        operators=(),
        plan=QueryPlan(
            projections=(position,),
            group_by=(position,),
            aggregates=(
                AggregateSpec(
                    "count",
                    measure,
                    "count_awards",
                ),
            ),
        ),
    )

    finalized = _finalize_requirement_plan(requirement)

    assert finalized.plan.aggregates == (
        AggregateSpec("sum", measure, "sum_award_count"),
    )
    assert finalized.operators == ("sum", "group_by")
    assert _plan_contract_score(finalized.plan, finalized.text) > 0


def test_preprocessing_policy_changes_actual_document_units():
    documents = [SourceDocument("d", "abcdefghij", {})]
    whole = preprocess_documents(
        documents, PreprocessingPolicy(strategy="whole_document")
    )
    chunked = preprocess_documents(
        documents,
        PreprocessingPolicy(
            strategy="chunked", chunk_size=6, chunk_overlap=2
        ),
    )
    assert [unit.text for unit in whole] == ["abcdefghij"]
    assert [unit.text for unit in chunked] == ["abcdef", "efghij", "ij"]


def test_native_extraction_repairs_qwen_json_syntax(
    tmp_path: Path, monkeypatch
):
    def unavailable_structural_repair(*_args, **_kwargs):
        raise ValueError("forced repair fallback")

    monkeypatch.setattr(
        "spp.native_backend.repair_json", unavailable_structural_repair
    )

    class FakeClient:
        model = "qwen-test"

        def __init__(self):
            self.responses = iter(
                [
                    '[{"name": "Alice" "unsupported": 1}]',
                    '[{"name": ["Alice"]}]',
                ]
            )

        def generate(self, *_args, **_kwargs):
            return next(self.responses)

    requirement = _player_requirement()
    config = _config("denormalized", requirement)
    backend = NativeSPPBackend(
        [SourceDocument("d1", "Alice is a player.", {})],
        FakeClient(),
        max_extraction_tokens=128,
    )
    units = preprocess_documents(backend.documents, config.preprocessing)
    ledger = GlobalBudgetLedger(10_000)
    with EvidenceStore(tmp_path / "evidence.sqlite") as evidence:
        records, _cells = backend._extract_relation(
            config,
            config.schema.relations[0],
            units,
            evidence,
            ledger,
            stage="pilot_extraction",
        )

    assert records[0]["name"] == "Alice"
    assert [
        charge["operation"] for charge in ledger.summary()["charges"]
    ] == ["constrained_extraction", "repair_extraction_json"]


def test_native_extraction_repairs_invalid_json_escape():
    rows = NativeSPPBackend._extract_json_array('[{"name": "A\\_B"}]')
    assert rows == [{"name": "A\\_B"}]


def test_native_extraction_repairs_missing_commas_deterministically():
    rows = NativeSPPBackend._extract_json_array(
        """
        [
          {
            "name": "Alice",
            "team": "Comets"
            "age": 30
          },
          {
            "name": "Bob"
            "team": "Rockets"
          }
        ]
        """
    )
    assert rows == [
        {"name": "Alice", "team": "Comets", "age": 30},
        {"name": "Bob", "team": "Rockets"},
    ]


def test_native_extraction_repairs_truncated_array():
    rows = NativeSPPBackend._extract_json_array(
        '[{"name": "Alice"}, {"name": "Bob"'
    )
    assert rows == [{"name": "Alice"}, {"name": "Bob"}]


def test_sqlite_materializer_serializes_nested_values(tmp_path: Path):
    relation = RelationSpec(
        name="record", attributes=("labels", "metadata")
    )
    schema = SchemaDesign(
        pattern="denormalized",
        relations=(relation,),
        covered_query_ids=("q0",),
    )
    path = write_sqlite_database(
        tmp_path / "nested.sqlite",
        {
            "record": [
                {
                    "labels": ["guard", "forward"],
                    "metadata": {"source": "profile", "rank": 1},
                }
            ]
        },
        schema,
    )
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT labels, metadata FROM record"
        ).fetchone()
    assert row == (
        '["guard","forward"]',
        '{"rank":1,"source":"profile"}',
    )


def test_risk_proxy_requires_grounded_cells_and_coverage():
    observation = PilotObservation(
        query_id="q0",
        config_id="c0",
        cells=[
            CellEvidence("alice", "age", 30, "Alice is 30", True, True, "d1"),
            CellEvidence("bob", "age", 40, None, False, False, "d2"),
        ],
        relevant_evidence_atoms={"alice:age", "bob:age", "carol:age"},
        represented_evidence_atoms={"alice:age", "bob:age"},
        candidate_agreement=0.75,
    )
    estimate = estimate_query_risk(observation, bootstrap_rounds=20)
    assert estimate.precision_proxy == 0.5
    assert estimate.recall_proxy == pytest.approx(2 / 3)
    assert estimate.uncertainty >= 0.25
    assert estimate.lower_confidence_bound() < estimate.f_proxy
    incomplete = estimate_query_risk(
        PilotObservation(
            query_id="q0",
            config_id="incomplete",
            cells=observation.cells,
            relevant_evidence_atoms=observation.relevant_evidence_atoms,
            represented_evidence_atoms=observation.represented_evidence_atoms,
            entity_completeness=2 / 3,
            candidate_agreement=0.75,
        ),
        bootstrap_rounds=20,
    )
    assert incomplete.components["entity_completeness"] == pytest.approx(2 / 3)
    assert incomplete.validity < estimate.validity
    one_document = estimate_query_risk(
        PilotObservation(
            query_id="q1",
            config_id="c1",
            cells=[
                CellEvidence(
                    "alice", "age", 30, "Alice is 30", True, True, "d1"
                )
            ],
            relevant_evidence_atoms={"alice:age"},
            represented_evidence_atoms={"alice:age"},
        ),
        bootstrap_rounds=20,
    )
    assert one_document.uncertainty >= 0.5


def test_output_equivalence_keeps_cheapest_representative():
    signature = canonical_output_signature({"q0": [{"x": 1}]})
    estimate = QualityEstimate("q0", "a", 1, 1, 1, 0, 1)
    pilots = {
        "a": PilotResult("a", {"q0": estimate}, signature, 20, 0.1),
        "b": PilotResult("b", {"q0": estimate}, signature, 10, 0.1),
    }
    retained, eliminated = collapse_output_equivalent(["a", "b"], pilots)
    assert retained == ["b"]
    assert eliminated == {"a": "output-equivalent-to:b"}


def test_output_equivalence_does_not_discard_unique_query_coverage():
    signature = canonical_output_signature({"q0": [{"x": 1}]})
    q0 = QualityEstimate("q0", "a", 1, 1, 1, 0, 1)
    q1 = QualityEstimate("q1", "a", 1, 1, 1, 0, 1)
    pilots = {
        "a": PilotResult(
            "a", {"q0": q0, "q1": q1}, signature, 20, 0.1
        ),
        "b": PilotResult("b", {"q0": q0}, signature, 10, 0.1),
    }
    retained, eliminated = collapse_output_equivalent(["a", "b"], pilots)
    assert retained == ["a", "b"]
    assert eliminated == {}


def test_progressive_dominance_preserves_unique_query_coverage():
    q0 = _player_requirement()
    q1 = QueryRequirement(
        query_id="q1",
        text="SELECT name FROM player",
        entities=("player",),
        attributes=("name",),
    )
    broad = _config("broad", q0)
    broad = SynthesisConfig(
        schema=SchemaDesign(
            pattern=broad.schema.pattern,
            relations=broad.schema.relations,
            covered_query_ids=("q0", "q1"),
        ),
        population=broad.population,
        preprocessing=broad.preprocessing,
    )
    narrow = _config("narrow", q0)

    def evaluate(config, sample_fraction, _ledger):
        scores = {"q0": 0.5, "q1": 0.5}
        if config == narrow:
            scores = {"q0": 1.0}
        return PilotResult(
            config_id=config.config_id,
            estimates={
                query_id: _estimate(
                    q0 if query_id == "q0" else q1,
                    config,
                    score,
                )
                for query_id, score in scores.items()
            },
            output_signature=config.schema.pattern,
            full_cost_upper_bound=20 if config == broad else 10,
            sample_fraction=sample_fraction,
        )

    result = progressive_pilot_search(
        [broad, narrow],
        [q0, q1],
        evaluate,
        GlobalBudgetLedger(100),
        sample_fractions=(0.1,),
        completion_reserve=20,
        completion_costs={
            broad.config_id: 20,
            narrow.config_id: 10,
        },
        completion_escrowed=True,
    )
    assert result.survivors == sorted(
        [broad.config_id, narrow.config_id]
    )


def test_shared_operator_dag_charges_common_work_once():
    dag = SharedOperatorDAG(
        [
            OperatorNode("ingest", "shared", 10),
            OperatorNode("extract-a", "extraction", 20, ("ingest",)),
            OperatorNode("extract-b", "extraction", 30, ("ingest",)),
        ],
        {"a": ("extract-a",), "b": ("extract-b",)},
    )
    assert dag.cost(["a"]) == 30
    assert dag.marginal_cost("b", {"a"}) == 30
    assert dag.cost(["a", "b"]) == 60


def test_pilot_order_spans_different_schema_patterns_early():
    requirement = _player_requirement()
    configs = [
        _config(pattern, requirement)
        for pattern in ("denormalized", "star", "snowflake")
    ]
    patterns = [config.schema.pattern for config in diverse_candidate_order(configs)]
    assert set(patterns[:3]) == {"denormalized", "star", "snowflake"}


def test_portfolio_selection_obeys_budget_and_routes_by_lcb():
    requirement = _player_requirement()
    low = _config("low", requirement)
    high = _config("high", requirement)
    estimates = {
        ("q0", low.config_id): _estimate(requirement, low, 0.5),
        ("q0", high.config_id): _estimate(requirement, high, 0.9),
    }
    portfolio = select_budgeted_portfolio(
        [low, high],
        [requirement],
        estimates,
        {low.config_id: 10, high.config_id: 20},
        token_budget=25,
    )
    assert portfolio.query_to_config["q0"] == high.config_id
    assert portfolio.construction_tokens <= 25


def test_portfolio_selects_multiple_shared_databases_only_for_coverage_gain():
    first = _player_requirement()
    second = QueryRequirement(
        query_id="q1",
        text="SELECT name FROM player",
        entities=("player",),
        attributes=("name",),
    )
    first_only = _config("first", first)
    second_only = _config("second", second)
    estimates = {
        ("q0", first_only.config_id): _estimate(first, first_only, 0.9),
        ("q1", second_only.config_id): _estimate(second, second_only, 0.9),
    }
    portfolio = select_budgeted_portfolio(
        [first_only, second_only],
        [first, second],
        estimates,
        {first_only.config_id: 10, second_only.config_id: 10},
        token_budget=20,
    )
    assert set(portfolio.selected_config_ids) == {
        first_only.config_id,
        second_only.config_id,
    }
    assert portfolio.query_to_config == {
        "q0": first_only.config_id,
        "q1": second_only.config_id,
    }


def test_evidence_store_round_trip(tmp_path: Path):
    path = tmp_path / "evidence.sqlite"
    with EvidenceStore(path) as store:
        store.add_document("d1", "Alice is 30")
        anchor = EvidenceAnchor.create(
            document_id="d1",
            text="Alice is 30",
            start=0,
            end=11,
            anchor_type="fact",
        )
        store.add_anchors([anchor])
        store.add_cell_provenance(
            [
                CellProvenance(
                    config_id="c",
                    relation="player",
                    row_identity="alice",
                    column="age",
                    value_json="30",
                    anchor_id=anchor.anchor_id,
                    entailed=True,
                    span_restored=True,
                )
            ]
        )
        assert len(store.supported_cells(config_id="c")) == 1
        assert store.put_shared_artifact(
            "anchors:d1", stage="anchor", payload=["Alice"], producer_tokens=4
        )
        assert not store.put_shared_artifact(
            "anchors:d1", stage="anchor", payload=["Alice"], producer_tokens=4
        )
        store.add_contract_evidence(
            [
                ContractEvidence(
                    contract_id="attribute:age",
                    relation="player",
                    row_identity="alice",
                    column="age",
                    raw_value_json="30",
                    raw_surface="30",
                    source_unit="year",
                    anchor_id=anchor.anchor_id,
                    accepted=True,
                    validation_status="accepted",
                    metadata={"source": "extractor"},
                )
            ]
        )
        accepted = store.accepted_contract_evidence(
            contract_id="attribute:age"
        )
        assert accepted[0].raw_surface == "30"
        store.add_validation_outcomes(
            [
                ValidationOutcome(
                    contract_id="attribute:age",
                    scope="cell",
                    scope_key="alice:age",
                    code="exact_span",
                    passed=True,
                    severity="error",
                    details={},
                )
            ]
        )
        store.add_derivation_lineage(
            [
                DerivationLineage(
                    config_id="c",
                    relation="player",
                    column="age",
                    source_value_json="30",
                    derived_value_json="30",
                    mapping_kind="identity",
                    evidence_anchor_ids=(anchor.anchor_id,),
                )
            ]
        )
        manifest = store.manifest()
        assert manifest["counts"]["contract_evidence"] == 1
        assert manifest["counts"]["validation_outcomes"] == 1
        assert manifest["counts"]["derivation_lineage"] == 1


def test_frozen_bundle_executes_only_known_readonly_query(tmp_path: Path):
    requirement = _player_requirement()
    config = _config("single", requirement)
    source_db = tmp_path / "source.sqlite"
    with sqlite3.connect(source_db) as connection:
        connection.execute("CREATE TABLE player(name TEXT)")
        connection.execute("INSERT INTO player VALUES ('Alice')")
    portfolio = FrozenPortfolio(
        selected_config_ids=(config.config_id,),
        query_to_config={"q0": config.config_id},
        query_scores={"q0": 1.0},
        construction_tokens=0,
        objective_value=1.0,
    )
    sql = "SELECT name FROM player"
    import hashlib

    compiled = [
        CompiledQuery(
            query_id="q0",
            natural_language_query="Which players?",
            config_id=config.config_id,
            sql=sql,
            sql_sha256=hashlib.sha256(sql.encode()).hexdigest(),
        )
    ]
    ledger = GlobalBudgetLedger(0)
    bundle = tmp_path / "bundle"
    freeze_serving_bundle(
        bundle,
        portfolio,
        compiled,
        {config.config_id: source_db},
        ledger,
    )
    server = OfflineQueryServer(bundle)
    assert server.execute("q0") == [{"name": "Alice"}]
    with pytest.raises(KeyError):
        server.execute("unknown")


def test_compile_failure_aborts_before_bundle_can_be_sealed(
    tmp_path: Path,
):
    requirement = _player_requirement()
    config = _config("single", requirement)
    db_path = tmp_path / "compile_failure.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE player(name TEXT)")
    portfolio = FrozenPortfolio(
        selected_config_ids=(config.config_id,),
        query_to_config={requirement.query_id: config.config_id},
        query_scores={requirement.query_id: 0.0},
        construction_tokens=0,
        objective_value=0.0,
    )

    def failing_compiler(*_args):
        raise ValueError("no such column: nt.team_name")

    with pytest.raises(
        ValueError,
        match=r"failed to compile query 'q0'.*no such column",
    ):
        compile_workload_sql(
            [requirement],
            portfolio,
            {config.config_id: config},
            {config.config_id: db_path},
            failing_compiler,
            GlobalBudgetLedger(0),
        )


def test_exact_budgeted_oracle_respects_selected_construction_cost():
    results = [
        OracleConfigResult("a", 5, {"q0": 0.0, "q1": 1.0}),
        OracleConfigResult("b", 5, {"q0": 1.0, "q1": 0.0}),
        OracleConfigResult("c", 5, {"q0": 0.4, "q1": 0.4}),
    ]
    selected, routing, mean_error = solve_exact_budgeted_oracle(results, 10)
    assert set(selected) == {"a", "b"}
    assert routing == {"q0": "a", "q1": "b"}
    assert mean_error == 0.0


def test_schema_materialization_and_metamorphic_check(tmp_path: Path):
    requirement = _player_requirement()
    config = _config("snowflake", requirement)
    tables = reshape_tables(
        {"player": [{"name": "Alice"}, {"name": "Bob"}]},
        config.schema,
    )
    db_path = write_sqlite_database(
        tmp_path / "materialized.sqlite", tables, config.schema
    )
    consistency = metamorphic_consistency(
        db_path,
        [
            MetamorphicCheck(
                "SELECT name FROM player WHERE name = 'Alice'",
                "SELECT name FROM player WHERE name IN ('Alice')",
            )
        ],
    )
    assert consistency == 1.0


def test_evaluation_reads_ground_truth_only_after_bundle_is_sealed(tmp_path: Path):
    requirement = _player_requirement()
    config = _config("single", requirement)
    db_path = tmp_path / "eval.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE player(name TEXT)")
        connection.execute("INSERT INTO player VALUES ('Alice')")
    sql = "SELECT name FROM player"
    import hashlib

    portfolio = FrozenPortfolio(
        selected_config_ids=(config.config_id,),
        query_to_config={"q0": config.config_id},
        query_scores={"q0": 1.0},
        construction_tokens=7,
        objective_value=1.0,
    )
    bundle = tmp_path / "eval_bundle"
    ledger = GlobalBudgetLedger(10)
    reservation = ledger.reserve(
        stage="final", operation="materialize", input_tokens=7, max_output_tokens=0
    )
    assert reservation is not None
    ledger.reconcile(reservation, input_tokens=7, output_tokens=0)
    freeze_serving_bundle(
        bundle,
        portfolio,
        [
            CompiledQuery(
                "q0",
                "Who?",
                config.config_id,
                sql,
                hashlib.sha256(sql.encode()).hexdigest(),
            )
        ],
        {config.config_id: db_path},
        ledger,
    )
    result = evaluate_frozen_bundle(
        bundle,
        {"q0": [{"name": "Alice"}]},
        lambda predicted, gold: 0.0 if list(predicted) == list(gold) else 1.0,
        method="spp",
        budget=10,
        synthesis_seconds=1.0,
    )
    assert result.mean_error == 0.0
    assert result.unused_tokens == 3
    assert summarize_accuracy_cost_frontier([result]) == [result]
    report = paired_noninferiority_report(result, result, bootstrap_rounds=20)
    assert report["regression_fraction"] == 0.0
    assert selector_top_k_recall(["a", "b"], {"b"}, k=2) == 1.0


def test_end_to_end_system_freezes_routing_sql_and_database(tmp_path: Path):
    class Backend:
        generated_configs = False

        def generate_configs(
            self, intent, *, observed_document_lengths=None
        ):
            self.generated_configs = True
            return generate_synthesis_configs(
                intent,
                observed_document_lengths=observed_document_lengths,
                exhaustive=False,
            )[:1]

        def prepare(self, intent, evidence_store, ledger):
            self.requirements = intent.requirements

        def completion_reserve(self, configs, requirements):
            return 0

        def estimate_full_cost(self, config, requirements):
            return 0

        def pilot(self, config, sample_fraction, evidence_store, ledger):
            raise BudgetExhausted(
                "test budget permits direct completion but no pilot"
            )

        def materialize(
            self, config, evidence_store, ledger, output_path
        ):
            tables = {
                relation.name: [
                    {
                        column: "Alice" if column == "name" else None
                        for column in relation.attributes
                    }
                ]
                for relation in config.schema.relations
            }
            return write_sqlite_database(output_path, tables, config.schema)

        def validate_materialization(
            self, config, database_path, requirements, evidence_store, ledger
        ):
            return {
                requirement.query_id: QualityEstimate(
                    requirement.query_id,
                    config.config_id,
                    0.9,
                    0.9,
                    1.0,
                    0.0,
                    1,
                )
                for requirement in requirements
            }

        def reproducibility_manifest(self):
            return {"backend": "test"}

    def compiler(requirement, config, database_path, ledger):
        relation = next(
            relation
            for relation in config.schema.relations
            if "name" in relation.attributes
        )
        return f'SELECT name FROM "{relation.name}"'

    backend = Backend()
    system = OfflineSynthesisSystem(backend, compiler)
    result = system.synthesize(
        queries=[{"query_id": "q0", "sql": "SELECT name FROM player"}],
        token_budget=0,
        output_dir=tmp_path / "run",
        observed_document_lengths=[100],
        sample_fractions=(0.1,),
    )
    server = OfflineQueryServer(result.serving_manifest.parent)
    assert server.execute("q0") == [{"name": "Alice"}]
    assert backend.generated_configs
    assert (tmp_path / "run" / "synthesis_manifest.json").exists()


def test_nl2sql_repair_cannot_destroy_informative_result(tmp_path: Path):
    class FakeClient:
        model = "fake"

        def __init__(self):
            self.responses = [
                "SELECT player_name, team FROM player",
                json.dumps(
                    {
                        "consistent": False,
                        "reason": "prefer normalized join",
                        "corrected_sql": (
                            "SELECT p.player_name, t.team_name FROM player p "
                            "JOIN team t ON p.team_id = t.team_name"
                        ),
                    }
                ),
            ]

        def generate(self, *args, **kwargs):
            return self.responses.pop(0)

    requirement = QueryRequirement(
        query_id="q",
        text="List each player and their team.",
        entities=("player", "team"),
        attributes=("player_name", "team_name"),
    )
    schema = SchemaDesign(
        pattern="snowflake",
        relations=(
            RelationSpec(
                "player",
                ("player_name", "team", "team_id"),
                "player_name",
                (("team_id", "team", "team_name"),),
            ),
            RelationSpec("team", ("team_name",), "team_name"),
        ),
        covered_query_ids=("q",),
    )
    config = SynthesisConfig(
        schema,
        PopulationConfig(),
        PreprocessingPolicy(strategy="whole_document"),
    )
    db_path = tmp_path / "repair.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE player(player_name TEXT, team TEXT, team_id TEXT)"
        )
        connection.execute("CREATE TABLE team(team_name TEXT)")
        connection.execute(
            "INSERT INTO player VALUES ('Alice', 'Comets', NULL)"
        )
        connection.execute("INSERT INTO team VALUES ('Comets')")
    compiler = make_nl2sql_compiler(FakeClient())
    sql = compiler(requirement, config, db_path, GlobalBudgetLedger(10_000))
    assert sql == "SELECT player_name, team FROM player"

    no_repair = FakeClient()
    no_repair.responses = [
        "SELECT player_name, team FROM player",
        json.dumps(
            {
                "consistent": False,
                "reason": "spurious objection",
                "corrected_sql": None,
            }
        ),
    ]
    sql = make_nl2sql_compiler(no_repair)(
        requirement, config, db_path, GlobalBudgetLedger(10_000)
    )
    assert sql == "SELECT player_name, team FROM player"

    false_consistent = FakeClient()
    false_consistent.responses = [
        "SELECT player_name team medals FROM player",
        json.dumps(
            {
                "consistent": True,
                "reason": "looks correct",
                "corrected_sql": None,
            }
        ),
        "SELECT player_name, team FROM player",
    ]
    sql = make_nl2sql_compiler(false_consistent)(
        requirement, config, db_path, GlobalBudgetLedger(10_000)
    )
    assert sql == "SELECT player_name, team FROM player"
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()


def test_verifier_repairs_qwen_invalid_json_escapes():
    payload = _verification_payload(
        '{"consistent": false, "reason": "bad\\_escape", '
        '"corrected_sql": "SELECT player_name\nFROM player"}'
    )
    assert payload["consistent"] is False
    assert "SELECT player_name\nFROM player" == payload["corrected_sql"]

    truncated = _verification_payload(
        '{"consistent": false, "reason": "syntax", '
        '"corrected_sql": "SELECT player_name FROM player"'
    )
    assert truncated["corrected_sql"] == "SELECT player_name FROM player"


def test_query_plan_compiler_preserves_aggregate_and_literal(tmp_path: Path):
    position = AttributeRef("player", "position", "text")
    college = AttributeRef("player", "college", "text")
    championships = AttributeRef(
        "player", "nba_championships", "integer"
    )
    nationality = AttributeRef("player", "nationality", "text")
    plan = QueryPlan(
        group_by=(position, college),
        aggregates=(
            AggregateSpec("sum", championships, "total_championships"),
        ),
        predicate=PredicateSpec(
            attribute=nationality, operator="=", value="French"
        ),
    )
    relation = RelationSpec(
        "workload_flat",
        ("position", "college", "nba_championships", "nationality"),
        semantic_types=(
            ("position", "text"),
            ("college", "text"),
            ("nba_championships", "integer"),
            ("nationality", "text"),
        ),
    )
    config = SynthesisConfig(
        SchemaDesign("denormalized", (relation,), ("q",)),
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    sql = compile_query_plan(plan, config)
    assert sql is not None
    assert "SUM(" in sql
    assert "COUNT(" not in sql
    assert "'French'" in sql
    assert "France" not in sql

    db_path = write_sqlite_database(
        tmp_path / "semantic.sqlite",
        {
            "workload_flat": [
                {
                    "position": "Guard",
                    "college": "A",
                    "nba_championships": 2,
                    "nationality": "French",
                },
                {
                    "position": "Guard",
                    "college": "A",
                    "nba_championships": 3,
                    "nationality": "French",
                },
                {
                    "position": "Guard",
                    "college": "A",
                    "nba_championships": 20,
                    "nationality": "American",
                },
            ]
        },
        config.schema,
    )
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(sql).fetchall() == [("Guard", "A", 5)]


def _validator_aggregate_fixture(
    tmp_path: Path,
) -> tuple[QueryRequirement, SynthesisConfig, Path]:
    category = AttributeRef("event", "category")
    amount = AttributeRef("event", "amount", "real")
    requirement = QueryRequirement(
        query_id="q",
        text="For each category, total the amount.",
        operators=("sum", "group_by"),
        plan=QueryPlan(
            group_by=(category,),
            aggregates=(AggregateSpec("sum", amount, "total_amount"),),
        ),
    )
    config = SynthesisConfig(
        SchemaDesign(
            "snowflake",
            (RelationSpec("event", ("category", "amount")),),
            ("q",),
        ),
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    database = write_sqlite_database(
        tmp_path / "validator.sqlite",
        {"event": [{"category": "A", "amount": 2.0}]},
        config.schema,
    )
    return requirement, config, database


def test_sql_validator_rejects_missing_group_by(tmp_path: Path):
    requirement, config, database = _validator_aggregate_fixture(tmp_path)
    result = validate_sql(
        requirement,
        config,
        database,
        "SELECT category, SUM(amount) FROM event",
    )
    assert not result.valid
    assert any("missing GROUP BY dimension" in error for error in result.errors)


def test_sql_validator_rejects_sum_null(tmp_path: Path):
    requirement, config, database = _validator_aggregate_fixture(tmp_path)
    result = validate_sql(
        requirement,
        config,
        database,
        "SELECT category, SUM(NULL) FROM event GROUP BY category",
    )
    assert not result.valid
    assert any("SUM(NULL)" in error for error in result.errors)


def test_sql_validator_rejects_wrong_join(tmp_path: Path):
    event_account = AttributeRef("event", "account_id")
    account_key = AttributeRef("account", "account_key")
    requirement = QueryRequirement(
        query_id="q",
        text="Show each event category with its account region.",
        plan=QueryPlan(
            projections=(
                AttributeRef("event", "category"),
                AttributeRef("account", "region"),
            ),
            joins=(JoinSpec(event_account, account_key),),
        ),
    )
    config = SynthesisConfig(
        SchemaDesign(
            "snowflake",
            (
                RelationSpec("event", ("account_id", "category")),
                RelationSpec("account", ("account_key", "region")),
            ),
            ("q",),
        ),
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    database = write_sqlite_database(
        tmp_path / "wrong_join.sqlite",
        {
            "event": [{"account_id": "a", "category": "retail"}],
            "account": [{"account_key": "a", "region": "north"}],
        },
        config.schema,
    )
    result = validate_sql(
        requirement,
        config,
        database,
        "SELECT e.category, a.region FROM event e "
        "JOIN account a ON e.category = a.region",
    )
    assert not result.valid
    assert any("wrong join edge" in error for error in result.errors)


def test_query_plan_compiler_and_validator_preserve_having(
    tmp_path: Path,
):
    category = AttributeRef("event", "category")
    amount = AttributeRef("event", "amount", "real")
    plan = QueryPlan(
        group_by=(category,),
        aggregates=(AggregateSpec("max", amount, "max_amount"),),
        having=(
            HavingSpec(
                aggregate=AggregateSpec("count"),
                operator=">",
                value=1,
            ),
        ),
    )
    requirement = QueryRequirement(
        query_id="q",
        text=(
            "For each category with more than one event, what is the "
            "highest amount?"
        ),
        entities=("event",),
        operators=("max", "group_by", "filter", "having"),
        plan=plan,
    )
    config = SynthesisConfig(
        SchemaDesign(
            "snowflake",
            (RelationSpec("event", ("category", "amount")),),
            ("q",),
        ),
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    database = write_sqlite_database(
        tmp_path / "having.sqlite",
        {
            "event": [
                {"category": "a", "amount": 1},
                {"category": "a", "amount": 2},
                {"category": "b", "amount": 5},
            ]
        },
        config.schema,
    )
    sql = compile_query_plan(plan, config)
    assert sql is not None
    assert "HAVING COUNT(*) > 1" in sql
    assert validate_sql(requirement, config, database, sql).valid
    class NoLLM:
        def generate(self, *_args, **_kwargs):
            raise AssertionError("valid typed plan must not invoke NL2SQL")

    compiled = make_nl2sql_compiler(NoLLM())(
        requirement,
        config,
        database,
        GlobalBudgetLedger(1_000),
    )
    assert compiled == sql
    missing = sql.split("\nHAVING", 1)[0]
    assert any(
        "missing HAVING condition" in error
        for error in validate_sql(
            requirement, config, database, missing
        ).errors
    )


def test_typed_plan_does_not_treat_measure_modifier_as_literal(
    tmp_path: Path,
):
    category = AttributeRef("event", "category")
    awards = AttributeRef("event", "international_awards", "integer")
    plan = QueryPlan(
        group_by=(category,),
        aggregates=(AggregateSpec("avg", awards, "avg_awards"),),
        predicate=PredicateSpec(
            attribute=awards,
            operator=">=",
            value=1,
        ),
    )
    requirement = QueryRequirement(
        query_id="q",
        text=(
            "Among entries with at least one International award, what is "
            "the average number of awards for each category?"
        ),
        entities=("event",),
        operators=("avg", "group_by", "filter"),
        plan=plan,
    )
    config = SynthesisConfig(
        SchemaDesign(
            "snowflake",
            (
                RelationSpec(
                    "event",
                    ("category", "international_awards"),
                ),
            ),
            ("q",),
        ),
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    database = write_sqlite_database(
        tmp_path / "measure_modifier.sqlite",
        {
            "event": [
                {"category": "a", "international_awards": 2},
            ]
        },
        config.schema,
    )

    class NoLLM:
        def generate(self, *_args, **_kwargs):
            raise AssertionError("valid typed plan must not invoke NL2SQL")

    sql = make_nl2sql_compiler(NoLLM())(
        requirement,
        config,
        database,
        GlobalBudgetLedger(1_000),
    )
    assert validate_sql(requirement, config, database, sql).valid


def test_sql_intent_parser_captures_having_aggregate():
    requirement = analyze_workload(
        [
            {
                "query_id": "q",
                "sql": (
                    "SELECT category, MAX(amount) AS max_amount FROM event "
                    "GROUP BY category HAVING COUNT(*) > 1"
                ),
            }
        ]
    ).requirements[0]
    assert requirement.plan is not None
    assert requirement.plan.having == (
        HavingSpec(AggregateSpec("count"), ">", 1),
    )


def test_sql_validator_rejects_wrong_boolean_filter_scope(
    tmp_path: Path,
):
    category = AttributeRef("event", "category")
    amount = AttributeRef("event", "amount", "real")
    plan = QueryPlan(
        group_by=(category,),
        aggregates=(AggregateSpec("sum", amount, "total"),),
        predicate=PredicateSpec(
            kind="and",
            children=(
                PredicateSpec(attribute=amount, operator=">", value=0),
                PredicateSpec(attribute=amount, operator="<", value=10),
            ),
        ),
    )
    requirement = QueryRequirement("q", "sum bounded amounts by category", plan=plan)
    config = SynthesisConfig(
        SchemaDesign(
            "snowflake",
            (RelationSpec("event", ("category", "amount")),),
            ("q",),
        ),
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    database = write_sqlite_database(
        tmp_path / "boolean.sqlite",
        {"event": [{"category": "a", "amount": 2}]},
        config.schema,
    )
    result = validate_sql(
        requirement,
        config,
        database,
        "SELECT category, SUM(amount) FROM event "
        "WHERE amount > 0 OR amount < 10 GROUP BY category",
    )
    assert "predicate boolean structure does not match plan" in result.errors


def test_serving_mandatorily_validates_compiler_sql(tmp_path: Path):
    requirement, config, database = _validator_aggregate_fixture(tmp_path)
    portfolio = FrozenPortfolio(
        selected_config_ids=(config.config_id,),
        query_to_config={"q": config.config_id},
        query_scores={"q": 0.0},
        construction_tokens=0,
        objective_value=0.0,
    )
    with pytest.raises(
        ValueError,
        match="missing GROUP BY dimension",
    ):
        compile_workload_sql(
            [requirement],
            portfolio,
            {config.config_id: config},
            {config.config_id: database},
            lambda *_args: "SELECT category, SUM(amount) FROM event",
            GlobalBudgetLedger(0),
        )


def test_nl2sql_rejects_known_warning_deterministic_fallback(
    tmp_path: Path, monkeypatch
):
    requirement, config, database = _validator_aggregate_fixture(tmp_path)

    class InvalidClient:
        model = "fake"

        def __init__(self):
            self.responses = iter(
                (
                    "SELECT category, SUM(NULL) FROM event GROUP BY category",
                    json.dumps(
                        {
                            "consistent": False,
                            "reason": "invalid aggregate target",
                            "corrected_sql": None,
                        }
                    ),
                    "SELECT category, SUM(NULL) FROM event GROUP BY category",
                )
            )

        def generate(self, *_args, **_kwargs):
            return next(self.responses)

    monkeypatch.setattr(
        "spp.nl2sql.compile_query_plan",
        lambda *_args: (
            "SELECT category, SUM(NULL) FROM event GROUP BY category"
        ),
    )
    compiler = make_nl2sql_compiler(InvalidClient())
    with pytest.raises(ValueError, match=r"SUM\(NULL\)"):
        compiler(
            requirement,
            config,
            database,
            GlobalBudgetLedger(10_000),
        )


def test_query_plan_compiler_uses_declared_join_path(tmp_path: Path):
    nationality = AttributeRef("player", "nationality", "text")
    player_team = AttributeRef("player", "team", "text")
    team_name = AttributeRef("team", "team_name", "text")
    team_city = AttributeRef("team", "location", "text")
    city_name = AttributeRef("city", "city_name", "text")
    population = AttributeRef("city", "population", "integer")
    plan = QueryPlan(
        group_by=(nationality,),
        aggregates=(AggregateSpec("count", None, "count_all"),),
        predicate=PredicateSpec(
            attribute=population, operator="<", value=2_000_000
        ),
        joins=(
            JoinSpec(player_team, team_name),
            JoinSpec(team_city, city_name),
        ),
    )
    schema = SchemaDesign(
        "snowflake",
        (
            RelationSpec("player", ("nationality", "team")),
            RelationSpec("team", ("team_name", "location")),
            RelationSpec(
                "city",
                ("city_name", "population"),
                semantic_types=(("population", "integer"),),
            ),
        ),
        ("q",),
    )
    config = SynthesisConfig(
        schema, PopulationConfig(), PreprocessingPolicy("whole_document")
    )
    sql = compile_query_plan(plan, config)
    assert sql is not None
    assert '"player"."team"' not in sql
    assert "JOIN" in sql
    assert "COUNT(*)" in sql

    db_path = write_sqlite_database(
        tmp_path / "joins.sqlite",
        {
            "player": [
                {"nationality": "French", "team": "A"},
                {"nationality": "American", "team": "B"},
            ],
            "team": [
                {"team_name": "A", "location": "Small"},
                {"team_name": "B", "location": "Large"},
            ],
            "city": [
                {"city_name": "Small", "population": 1_000_000},
                {"city_name": "Large", "population": 3_000_000},
            ],
        },
        schema,
    )
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(sql).fetchall() == [("French", 1)]


def test_query_plan_compiler_is_domain_agnostic(tmp_path: Path):
    account_id = AttributeRef("transaction", "account_id", "text")
    account_key = AttributeRef("account", "account_key", "text")
    region = AttributeRef("account", "region", "text")
    amount = AttributeRef("transaction", "amount", "real")
    status = AttributeRef("transaction", "status", "text")
    plan = QueryPlan(
        group_by=(region,),
        aggregates=(AggregateSpec("sum", amount, "total_amount"),),
        predicate=PredicateSpec(
            attribute=status, operator="=", value="settled"
        ),
        joins=(JoinSpec(account_id, account_key),),
    )
    schema = SchemaDesign(
        "snowflake",
        (
            RelationSpec(
                "transaction",
                ("account_id", "amount", "status"),
                semantic_types=(("amount", "real"),),
            ),
            RelationSpec("account", ("account_key", "region")),
        ),
        ("q",),
    )
    config = SynthesisConfig(
        schema, PopulationConfig(), PreprocessingPolicy("whole_document")
    )
    sql = compile_query_plan(plan, config)
    assert sql is not None
    db_path = write_sqlite_database(
        tmp_path / "domain_neutral.sqlite",
        {
            "transaction": [
                {"account_id": "a", "amount": 4.5, "status": "settled"},
                {"account_id": "a", "amount": 1.5, "status": "pending"},
            ],
            "account": [{"account_key": "a", "region": "north"}],
        },
        schema,
    )
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(sql).fetchall() == [("north", 4.5)]


def test_denormalization_preserves_rows_when_unrelated_relation_is_empty():
    schema = SchemaDesign(
        "denormalized",
        (RelationSpec("workload_flat", ("value",)),),
        ("q",),
    )
    tables = reshape_tables(
        {
            "empty_first": [],
            "populated_second": [{"value": "kept"}],
            "empty_third": [],
        },
        schema,
    )
    assert tables == {"workload_flat": [{"value": "kept"}]}


def test_intent_payload_parses_typed_boolean_query_plan():
    response = json.dumps(
        [
            {
                "query_id": "q",
                "entities": ["player"],
                "attributes": [],
                "attribute_bindings": [],
                "relationships": [],
                "operators": [],
                "units": [],
                "plan": {
                    "projections": [],
                    "group_by": [
                        {
                            "entity": "player",
                            "attribute": "position",
                            "semantic_type": "text",
                        }
                    ],
                    "aggregates": [
                        {
                            "function": "avg",
                            "attribute": {
                                "entity": "player",
                                "attribute": "age",
                                "semantic_type": "real",
                            },
                            "alias": "average_age",
                            "distinct": False,
                        }
                    ],
                    "predicate": {
                        "kind": "or",
                        "children": [
                            {
                                "kind": "predicate",
                                "entity": "player",
                                "attribute": "nationality",
                                "semantic_type": "text",
                                "operator": "=",
                                "value": "American",
                            },
                            {
                                "kind": "predicate",
                                "entity": "player",
                                "attribute": "nationality",
                                "semantic_type": "text",
                                "operator": "<>",
                                "value": "French",
                            },
                        ],
                    },
                    "joins": [],
                },
            }
        ]
    )
    requirement = _parse_llm_payload(response, {"q": "question"})[0]
    assert requirement.plan is not None
    assert requirement.plan.aggregates[0].function == "avg"
    assert requirement.plan.aggregates[0].attribute.semantic_type == "real"
    assert requirement.plan.predicate.kind == "or"
    assert requirement.plan.predicate.children[0].value == "American"
    assert requirement.plan.predicate.children[1].operator == "!="
    assert ("player", "age") in requirement.attribute_bindings


def test_clause_ledger_compiles_boolean_expression_deterministically():
    plan = _plan_from_clause_ledger(
        {
            "projections": [
                {
                    "entity": "event",
                    "attribute": "category",
                    "semantic_type": "text",
                }
            ],
            "group_by": [],
            "aggregate": None,
            "filters": [
                {
                    "id": "f1",
                    "entity": "event",
                    "attribute": "amount",
                    "semantic_type": "real",
                    "operator": "at least",
                    "value": 5,
                },
                {
                    "id": "f2",
                    "entity": "event",
                    "attribute": "status",
                    "semantic_type": "text",
                    "operator": "not equal",
                    "value": "Suspended",
                },
                {
                    "id": "f3",
                    "entity": "event",
                    "attribute": "region",
                    "semantic_type": "text",
                    "operator": "=",
                    "value": "West",
                },
            ],
            "boolean_expression": "(f1 AND f2) OR f3",
            "joins": [],
        },
        entity_vocabulary=("event",),
        attribute_vocabulary={
            "event": ("amount", "category", "region", "status"),
        },
    )

    assert plan is not None
    assert plan.predicate.kind == "or"
    assert plan.predicate.children[0].kind == "and"
    assert plan.predicate.children[0].children[0].operator == ">="
    assert plan.predicate.children[0].children[1].operator == "!="
    assert plan.predicate.children[1].value == "West"
    assert _plan_contract_score(
        QueryPlan(predicate=plan.predicate),
        "Show category where amount is at least 5.",
    ) < _plan_contract_score(
        plan,
        "Show category where amount is at least 5.",
    )


def test_nl_intent_analysis_isolates_queries():
    import threading
    import time

    class BatchClient:
        def __init__(self):
            self.calls = 0
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()

        def generate(self, prompt, **_kwargs):
            with self.lock:
                self.calls += 1
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                time.sleep(0.01)
                query_ids = re.findall(r'"query_id": "(q\d+)"', prompt)
                return json.dumps(
                    [
                        {
                            "query_id": query_id,
                            "entities": ["record"],
                            "attributes": ["category"],
                            "attribute_bindings": [
                                {"entity": "record", "attribute": "category"}
                            ],
                            "relationships": [],
                            "operators": [],
                            "units": [],
                            "plan": {
                                "projections": [
                                    {
                                        "entity": "record",
                                        "attribute": "category",
                                        "semantic_type": "text",
                                    }
                                ],
                                "group_by": [],
                                "aggregates": [],
                                "predicate": None,
                                "joins": [],
                            },
                        }
                        for query_id in query_ids
                    ]
                )
            finally:
                with self.lock:
                    self.active -= 1

    client = BatchClient()
    intent = analyze_workload(
        [
            {"query_id": f"q{index}", "text": f"Show category {index}"}
            for index in range(5)
        ],
        llm_client=client,
        intent_max_workers=3,
    )
    # Each isolated query receives a draft, semantic audit, independent
    # SQL-shaped interpretation, flat clause ledger, and final adjudication.
    assert client.calls == 25
    assert client.max_active > 1
    assert len(intent.requirements) == 5
    assert all(requirement.plan for requirement in intent.requirements)


def test_nl_intent_uses_independent_sql_shadow_candidate():
    class ShadowClient:
        def generate(self, prompt, **_kwargs):
            if prompt.startswith("Adjudicate alternative query plans"):
                return json.dumps(
                    {
                        "selected_source": "sql_shadow",
                        "plan": None,
                        "checks": {
                            "output_count": 1,
                            "filter_count": 1,
                            "literal_count": 1,
                            "boolean_scope": "single predicate",
                            "join_count": 0,
                        },
                    }
                )
            if prompt.startswith("Translate the analytical question"):
                return "SELECT category FROM record WHERE amount > 5"
            return json.dumps(
                [
                    {
                        "query_id": "q0",
                        "entities": ["record"],
                        "attributes": ["category", "amount"],
                        "attribute_bindings": [
                            {"entity": "record", "attribute": "category"},
                            {"entity": "record", "attribute": "amount"},
                        ],
                        "relationships": [],
                        "operators": ["filter"],
                        "units": [],
                        "plan": {
                            "projections": [
                                {
                                    "entity": "record",
                                    "attribute": "category",
                                    "semantic_type": "text",
                                }
                            ],
                            "group_by": [],
                            "aggregates": [],
                            "predicate": None,
                            "joins": [],
                        },
                    }
                ]
            )

    intent = analyze_workload(
        [{"query_id": "q0", "text": "Show category where amount is above 5."}],
        llm_client=ShadowClient(),
        entity_vocabulary=("record",),
        attribute_vocabulary={"record": ("amount", "category")},
    )
    requirement = intent.requirements[0]
    assert requirement.plan is not None
    assert requirement.plan.predicate == PredicateSpec(
        attribute=AttributeRef("record", "amount", "integer"),
        operator=">",
        value=5,
    )
    # A self-adjudicated tie cannot override an independently grounded SQL
    # candidate unless another independent candidate corroborates the choice.
    assert intent.analysis_diagnostics["q0"]["selected_source"] == "sql_shadow"
    assert intent.analysis_diagnostics["q0"]["adjudication"][
        "selected_source"
    ] == "sql_shadow"


def test_schema_stabilization_parallelizes_independent_samples(monkeypatch):
    import threading
    import time

    import config

    monkeypatch.setattr(config, "MAX_PARALLEL_REQUESTS", 4)
    extractor = object.__new__(ConstrainedExtractor)
    extractor.stabilized_schemas = {}
    lock = threading.Lock()
    active = 0
    max_active = 0

    def extract_sample(*_args, **_kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            time.sleep(0.01)
            return ExtractionResult(
                chunk_id="",
                records=[{"category": "value"}],
                schema_keys={"category"},
                extraction_time=0.01,
            )
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(extractor, "_extract_single_chunk", extract_sample)
    stabilized = extractor.stabilize_schema(
        "record",
        {"category": "OTHER"},
        ["sample"] * 8,
    )

    assert max_active > 1
    assert stabilized.frozen_keys == {"category"}


def test_column_batch_merge_preserves_field_local_spans():
    extractor = object.__new__(ConstrainedExtractor)
    merged = extractor._merge_column_batches(
        "doc-1",
        {
            0: ExtractionResult(
                chunk_id="doc-1",
                records=[{"name": "Example"}],
                schema_keys={"name"},
                extraction_time=0.1,
                spans=[{"name": "Example"}],
            ),
            1: ExtractionResult(
                chunk_id="doc-1",
                records=[{"amount": 42}],
                schema_keys={"amount"},
                extraction_time=0.1,
                spans=[{"amount": "amount was 42"}],
            ),
        },
        2,
    )
    assert merged.records == [{"name": "Example", "amount": 42}]
    assert merged.spans == [
        {"name": "Example", "amount": "amount was 42"}
    ]


def test_sqlite_delete_journal_mode_is_configurable(tmp_path, monkeypatch):
    monkeypatch.setenv("WDIRS_SQLITE_JOURNAL_MODE", "DELETE")
    layer = DataLayer(f"sqlite:///{tmp_path / 'journal.sqlite'}")
    try:
        with layer.engine.connect() as connection:
            mode = connection.execute(text("PRAGMA journal_mode")).scalar()
        assert str(mode).lower() == "delete"
    finally:
        layer.close()


def test_intent_constrains_entities_and_repairs_missing_aggregate():
    response = json.dumps(
        [
            {
                "query_id": "q",
                "entities": ["transaction", "region", "amount_measure"],
                "attributes": ["total", "each", "transaction.region"],
                "attribute_bindings": [],
                "relationships": [],
                "operators": ["sum", "group_by"],
                "units": [],
                "plan": {
                    "projections": [
                        {
                            "entity": "transaction",
                            "attribute": "transaction.region",
                            "semantic_type": "text",
                        },
                        {
                            "entity": "amount_measure",
                            "attribute": "transaction/amount",
                            "semantic_type": "real",
                        },
                    ],
                    "group_by": [
                        {
                            "entity": "transaction",
                            "attribute": "region",
                            "semantic_type": "text",
                        }
                    ],
                    "aggregates": [],
                    "predicate": None,
                    "joins": [],
                },
            }
        ]
    )
    requirement = _parse_llm_payload(
        response,
        {"q": "For each region, report the total transaction amount."},
        entity_vocabulary=("account", "transaction"),
    )[0]
    assert requirement.entities == ("transaction",)
    assert requirement.attributes == ("region", "amount")
    assert requirement.plan.aggregates == (
        AggregateSpec(
            "sum",
            AttributeRef("transaction", "amount", "real"),
            "sum_amount",
        ),
    )
    assert "total" not in requirement.attributes


def test_sql_training_workload_constrains_canonical_attribute_names():
    vocabulary = schema_vocabulary_from_sql(
        [
            "SELECT p.position, p.olympic_gold_medals "
            "FROM player p JOIN team t ON p.team = t.team_name"
        ]
    )
    assert vocabulary.entities == ("player", "team")
    assert vocabulary.attributes["player"] == (
        "olympic_gold_medals",
        "position",
        "team",
    )
    response = json.dumps(
        [
            {
                "query_id": "q",
                "entities": ["player"],
                "attributes": [],
                "attribute_bindings": [],
                "relationships": [],
                "operators": ["sum", "group_by"],
                "units": [],
                "plan": {
                    "projections": [],
                    "group_by": [
                        {
                            "entity": "player",
                            "attribute": "playing_position",
                            "semantic_type": "text",
                        }
                    ],
                    "aggregates": [
                        {
                            "function": "sum",
                            "attribute": {
                                "entity": "player",
                                "attribute": "gold_medals",
                                "semantic_type": "integer",
                            },
                            "alias": "total",
                            "distinct": False,
                        }
                    ],
                    "predicate": None,
                    "joins": [],
                },
            }
        ]
    )
    requirement = _parse_llm_payload(
        response,
        {"q": "Total gold medals for each playing position."},
        entity_vocabulary=vocabulary.entities,
        attribute_vocabulary=vocabulary.attributes,
    )[0]
    assert requirement.plan.group_by[0].attribute == "position"
    assert (
        requirement.plan.aggregates[0].attribute.attribute
        == "olympic_gold_medals"
    )


def test_schema_graph_repairs_missing_groups_counts_and_joins():
    college = AttributeRef("player", "college")
    age = AttributeRef("player", "age")
    plan = QueryPlan(
        projections=(college,),
        aggregates=(AggregateSpec("count", None, "count_all"),),
        predicate=PredicateSpec(
            attribute=AttributeRef("player", "team"),
            value={"entity": "team", "attribute": "team_name"},
        ),
    )
    repaired = _normalize_plan_with_schema(
        plan,
        "For each college, how many players have a known age?",
        attribute_vocabulary={
            "player": ("age", "college", "team"),
            "team": ("team_name",),
        },
        join_vocabulary=(
            ("player", "team", "team", "team_name"),
        ),
    )
    assert repaired.predicate is None
    assert repaired.group_by == (college,)
    assert repaired.aggregates[0].attribute == age
    assert repaired.joins == ()

    joined = _normalize_plan_with_schema(
        QueryPlan(
            group_by=(college,),
            aggregates=(
                AggregateSpec(
                    "avg", AttributeRef("team", "championship")
                ),
            ),
        ),
        "Average team championship for each college.",
        attribute_vocabulary={
            "player": ("college", "team"),
            "team": ("championship", "team_name"),
        },
        join_vocabulary=(
            ("player", "team", "team", "team_name"),
        ),
    )
    assert len(joined.joins) == 1
    assert joined.joins[0].left.attribute == "team"
    assert joined.joins[0].right.attribute == "team_name"


def test_missing_non_count_measure_does_not_abort_intent_analysis():
    response = json.dumps(
        [
            {
                "query_id": "q",
                "entities": ["record"],
                "attributes": ["category"],
                "attribute_bindings": [],
                "relationships": [],
                "operators": ["min", "group_by"],
                "units": [],
                "plan": {
                    "projections": [],
                    "group_by": [
                        {
                            "entity": "record",
                            "attribute": "category",
                            "semantic_type": "text",
                        }
                    ],
                    "aggregates": [],
                    "predicate": None,
                    "joins": [],
                },
            }
        ]
    )
    requirement = _parse_llm_payload(
        response, {"q": "What is the fewest value for each category?"}
    )[0]
    assert requirement.plan is not None
    assert requirement.plan.aggregates == ()


def test_nl2sql_uses_query_plan_without_free_form_llm(tmp_path: Path):
    class FailIfCalled:
        model = "unused"

        def generate(self, *_args, **_kwargs):
            raise AssertionError("deterministic query plan should bypass LLM")

    nationality = AttributeRef("player", "nationality", "text")
    plan = QueryPlan(
        aggregates=(AggregateSpec("count", None, "count_all"),),
        predicate=PredicateSpec(
            attribute=nationality, operator="=", value="American"
        ),
    )
    requirement = QueryRequirement(
        query_id="q",
        text="How many American players are there?",
        entities=("player",),
        attributes=("nationality",),
        attribute_bindings=(("player", "nationality"),),
        operators=("count", "filter"),
        plan=plan,
    )
    relation = RelationSpec("player", ("nationality",))
    config = SynthesisConfig(
        SchemaDesign("snowflake", (relation,), ("q",)),
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    db_path = write_sqlite_database(
        tmp_path / "no_llm.sqlite",
        {"player": [{"nationality": "American"}]},
        config.schema,
    )
    ledger = GlobalBudgetLedger(1_000)
    sql = make_nl2sql_compiler(FailIfCalled())(
        requirement, config, db_path, ledger
    )
    assert "COUNT(*)" in sql
    assert "'American'" in sql
    assert ledger.actual_spent == 0


def test_nl2sql_does_not_require_join_for_local_foreign_key_group(
    tmp_path: Path,
):
    class FailIfCalled:
        model = "unused"

        def generate(self, *_args, **_kwargs):
            raise AssertionError("local grouping should bypass LLM")

    nationality = AttributeRef("player", "nationality")
    team = AttributeRef("player", "team")
    medals = AttributeRef("player", "olympic_gold_medals", "integer")
    requirement = QueryRequirement(
        query_id="q",
        text=(
            "For every nationality-and-team combination, what is the "
            "players' combined number of Olympic gold medals?"
        ),
        entities=("player", "team"),
        operators=("sum", "group_by", "join"),
        plan=QueryPlan(
            group_by=(nationality, team),
            aggregates=(AggregateSpec("sum", medals, "sum_medals"),),
        ),
    )
    config = SynthesisConfig(
        SchemaDesign(
            "star",
            (
                RelationSpec(
                    "player",
                    ("nationality", "team", "olympic_gold_medals"),
                ),
                RelationSpec("team", ("team_name",)),
            ),
            ("q",),
        ),
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    database = write_sqlite_database(
        tmp_path / "local_group.sqlite",
        {
            "player": [
                {
                    "nationality": "American",
                    "team": "Comets",
                    "olympic_gold_medals": 2,
                }
            ],
            "team": [{"team_name": "Comets"}],
        },
        config.schema,
    )
    ledger = GlobalBudgetLedger(1_000)
    sql = make_nl2sql_compiler(FailIfCalled())(
        requirement, config, database, ledger
    )
    assert "GROUP BY" in sql
    assert '"nationality"' in sql
    assert '"team"' in sql
    assert ledger.actual_spent == 0


def test_schema_design_propagates_query_plan_semantic_types():
    age = AttributeRef("player", "age", "real")
    requirement = QueryRequirement(
        query_id="q",
        text="What is the average player age?",
        plan=QueryPlan(
            aggregates=(AggregateSpec("avg", age, "average_age"),)
        ),
    )
    assert requirement.required_symbols() == {"player", "age"}
    intent = WorkloadIntent(
        requirements=(requirement,),
        entity_frequency={"player": 1},
        attribute_frequency={"age": 1},
        operator_frequency={"avg": 1},
    )
    for design in generate_schema_designs(intent):
        typed_relations = [
            relation
            for relation in design.relations
            if "age" in relation.attributes
        ]
        assert typed_relations
        assert all(
            relation.semantic_type("age") == "real"
            for relation in typed_relations
        )


def test_denormalized_backend_extracts_entities_before_joining():
    player_team = AttributeRef("player", "team", "text")
    team_name = AttributeRef("team", "team_name", "text")
    team_city = AttributeRef("team", "location", "text")
    city_name = AttributeRef("city", "city_name", "text")
    population = AttributeRef("city", "population", "integer")
    requirement = QueryRequirement(
        query_id="q",
        text="Count players in teams from small cities.",
        entities=("player", "team", "city"),
        attributes=(
            "team", "team_name", "location", "city_name", "population"
        ),
        attribute_bindings=(
            ("player", "team"),
            ("team", "team_name"),
            ("team", "location"),
            ("city", "city_name"),
            ("city", "population"),
        ),
        operators=("count", "filter", "join"),
        plan=QueryPlan(
            aggregates=(AggregateSpec("count", None, "count_all"),),
            predicate=PredicateSpec(
                attribute=population, operator="<", value=2_000_000
            ),
            joins=(
                JoinSpec(player_team, team_name),
                JoinSpec(team_city, city_name),
            ),
        ),
    )
    intent = WorkloadIntent(
        requirements=(requirement,),
        entity_frequency={"player": 1, "team": 1, "city": 1},
        attribute_frequency={name: 1 for name in requirement.attributes},
        operator_frequency={"count": 1, "filter": 1, "join": 1},
    )
    flat = next(
        design
        for design in generate_schema_designs(intent)
        if design.pattern == "denormalized"
    )
    config = SynthesisConfig(
        flat, PopulationConfig(), PreprocessingPolicy("whole_document")
    )
    backend = NativeSPPBackend(
        [SourceDocument("d", "Player, team, and city facts.", {})],
        object(),
    )
    backend.intent = intent
    assert {
        relation.name for relation in backend._extraction_relations(config)
    } == {"player", "team", "city"}
    assert backend._intent_join_pairs() == [
        ("player", "team", "team", "team_name"),
        ("team", "location", "city", "city_name"),
    ]
    partitioned_documents = [
        SourceDocument("player/1.txt", "player facts", {}),
        SourceDocument("team/1.txt", "team facts", {}),
        SourceDocument("city/1.txt", "city facts", {}),
        SourceDocument("owner/1.txt", "unrequested owner facts", {}),
    ]
    units = preprocess_documents(
        partitioned_documents, config.preprocessing
    )
    assert infer_source_entity_vocabulary(partitioned_documents) == (
        "city", "owner", "player", "team"
    )
    extraction_relations = backend._extraction_relations(config)
    routed = {
        relation.name: [
            unit.document_id
            for unit in backend._units_for_relation(
                relation, extraction_relations, units
            )
        ]
        for relation in extraction_relations
    }
    assert routed == {
        "city": ["city/1.txt"],
        "player": ["player/1.txt"],
        "team": ["team/1.txt"],
    }


def test_schema_normalization_repairs_measure_and_leaked_projection():
    college = AttributeRef("person", "college")
    leaked_name = AttributeRef("person", "name")
    repaired = _normalize_plan_with_schema(
        QueryPlan(
            projections=(leaked_name, college),
            group_by=(college,),
            aggregates=(AggregateSpec("avg", college, "avg_college"),),
        ),
        "What is the average number of international awards from each college?",
        attribute_vocabulary={
            "person": ("name", "college", "international_awards")
        },
    )
    assert repaired is not None
    assert repaired.aggregates[0].attribute is not None
    assert repaired.aggregates[0].attribute.entity == "person"
    assert repaired.aggregates[0].attribute.attribute == "international_awards"
    assert repaired.projections == (college,)


def test_schema_normalization_removes_redundant_event_presence_filter():
    process_year = AttributeRef("record", "process_year", "integer")
    processed = AttributeRef("record", "processed", "integer")
    plan = _normalize_plan_with_schema(
        QueryPlan(
            group_by=(process_year,),
            aggregates=(AggregateSpec("count", None, "count_all"),),
            predicate=PredicateSpec(
                kind="and",
                children=(
                    PredicateSpec(
                        attribute=process_year,
                        operator=">",
                        value=2020,
                    ),
                    PredicateSpec(
                        attribute=processed,
                        operator="=",
                        value=True,
                    ),
                ),
            ),
        ),
        "How many records were processed in each year after 2020?",
        attribute_vocabulary={
            "record": ("process_year", "processed"),
        },
    )
    assert plan is not None
    assert plan.predicate == PredicateSpec(
        attribute=process_year,
        operator=">",
        value=2020,
    )


def test_semantic_validator_rejects_artifact_style_contract_violations():
    branch = AttributeRef("transaction", "branch")
    amount = AttributeRef("transaction", "amount", "real")
    year = AttributeRef("transaction", "year", "integer")
    requirement = QueryRequirement(
        query_id="q",
        text=(
            "For each branch, what is the average transaction amount "
            "after 2020 for Canadian customers?"
        ),
        entities=("transaction",),
        operators=("avg", "group_by", "filter"),
        plan=QueryPlan(
            group_by=(branch,),
            aggregates=(AggregateSpec("avg", amount, "avg_amount"),),
            predicate=PredicateSpec(attribute=year, operator=">", value=2020),
        ),
    )
    schema = SchemaDesign(
        "snowflake",
        (
            RelationSpec(
                "transaction",
                ("branch", "amount", "year", "customer_country"),
            ),
        ),
        ("q",),
    )
    config = SynthesisConfig(
        schema, PopulationConfig(), PreprocessingPolicy("whole_document")
    )
    errors = _semantic_validation_errors(
        requirement,
        config,
        "SELECT branch, AVG(branch) FROM transaction GROUP BY branch",
    )
    assert "aggregate target must be transaction.amount" in errors
    assert "missing numeric literal 2020" in errors


def test_temporary_work_dir_tolerates_nonempty_cleanup(tmp_path: Path):
    # Must not raise even when sticky sidecars are present during cleanup.
    with temporary_work_dir("spp-pilot-", parent=tmp_path) as directory:
        path = directory
        (directory / "pilot.sqlite").write_text("x", encoding="utf-8")
        (directory / ".nfsdeadbeef").write_text("stub", encoding="utf-8")
    assert not path.exists()


def test_scalar_count_column_is_not_mistaken_for_count_aggregate():
    championships = AttributeRef(
        "player", "nba_championships", "integer"
    )
    requirement = QueryRequirement(
        query_id="q",
        text="Show each player's NBA championship count.",
        entities=("player",),
        attributes=("nba_championships",),
        attribute_bindings=(("player", "nba_championships"),),
        operators=("projection",),
        plan=QueryPlan(projections=(championships,)),
    )
    config = SynthesisConfig(
        SchemaDesign(
            "denormalized",
            (
                RelationSpec(
                    "player",
                    ("name", "nba_championships"),
                    semantic_types=(("nba_championships", "integer"),),
                ),
            ),
            ("q",),
        ),
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )

    assert _semantic_validation_errors(
        requirement,
        config,
        "SELECT nba_championships FROM player",
    ) == []
    normalized = _normalize_plan_with_schema(
        requirement.plan,
        requirement.text,
        attribute_vocabulary={
            "player": ("name", "nba_championships"),
        },
    )
    assert normalized is not None
    assert normalized.aggregates == ()


def test_projection_for_every_entity_does_not_invent_grouping():
    plan = _normalize_plan_with_schema(
        QueryPlan(
            projections=(
                AttributeRef("person", "group"),
                AttributeRef("person", "nationality"),
                AttributeRef("group", "location"),
                AttributeRef("group", "group_name"),
            ),
            group_by=(AttributeRef("person", "group"),),
        ),
        (
            "For every person matched to a group, show the person's nationality "
            "together with the group's location and name."
        ),
        attribute_vocabulary={
            "person": ("group", "nationality"),
            "group": ("group_name", "location"),
        },
        join_vocabulary=(
            ("person", "group", "group", "group_name"),
        ),
    )
    assert plan is not None
    assert plan.group_by == ()
    assert plan.aggregates == ()


def test_normalization_canonicalizes_dates_without_contradictory_duplicates():
    birth_date = AttributeRef("person", "birth_date", "date")
    plan = _normalize_plan_with_schema(
        QueryPlan(
            projections=(birth_date,),
            predicate=PredicateSpec(
                attribute=birth_date,
                operator="!=",
                value="1959-06-10",
            ),
        ),
        "List birth dates, excluding people born on June 10, 1959.",
        attribute_vocabulary={
            "person": ("birth_date",),
        },
    )
    assert plan is not None
    assert plan.predicate == PredicateSpec(
        attribute=birth_date,
        operator="!=",
        value="1959/6/10",
    )


def test_normalization_treats_comma_number_as_one_literal():
    population = AttributeRef("place", "population", "integer")
    plan = _normalize_plan_with_schema(
        QueryPlan(
            projections=(AttributeRef("place", "name"),),
            predicate=PredicateSpec(
                attribute=population,
                operator="<",
                value=1_603_797,
            ),
        ),
        "Show places whose population is below 1,603,797.",
        attribute_vocabulary={
            "place": ("name", "population"),
        },
    )
    assert plan is not None
    leaves = []

    def collect(predicate):
        if predicate.kind in {"and", "or"}:
            for child in predicate.children:
                collect(child)
        else:
            leaves.append(predicate)

    collect(plan.predicate)
    assert [leaf.value for leaf in leaves] == [1_603_797]


def test_normalization_repairs_or_later_comparison_direction():
    year = AttributeRef("record", "acquisition_year", "integer")
    plan = _normalize_plan_with_schema(
        QueryPlan(
            projections=(AttributeRef("record", "name"),),
            predicate=PredicateSpec(
                attribute=year,
                operator="=",
                value=2000,
            ),
        ),
        "Show records acquired in 2000 or later.",
        attribute_vocabulary={
            "record": ("name", "acquisition_year"),
        },
    )

    assert plan is not None
    assert plan.predicate == PredicateSpec(
        attribute=year,
        operator=">=",
        value=2000,
    )


def test_normalization_expands_worded_magnitude_threshold():
    population = AttributeRef("place", "population", "integer")
    region = AttributeRef("place", "region")
    measure = AttributeRef("place", "measure", "real")
    plan = _normalize_plan_with_schema(
        QueryPlan(
            group_by=(region,),
            aggregates=(AggregateSpec("max", measure, "max_measure"),),
            predicate=PredicateSpec(
                attribute=population,
                operator=">",
                value=1,
            ),
        ),
        (
            "Among places with more than one million residents, "
            "what is the highest measure in each region?"
        ),
        attribute_vocabulary={
            "place": ("measure", "population", "region"),
        },
    )
    assert plan is not None
    assert plan.predicate == PredicateSpec(
        attribute=population,
        operator=">",
        value=1_000_000,
    )


def test_normalization_canonicalizes_group_cardinality_having():
    category = AttributeRef("record", "category")
    score = AttributeRef("record", "score", "integer")
    plan = _normalize_plan_with_schema(
        QueryPlan(
            group_by=(category,),
            aggregates=(AggregateSpec("max", score, "max_score"),),
            having=(
                HavingSpec(
                    AggregateSpec("max", score, "max_score"),
                    ">",
                    1,
                ),
            ),
        ),
        (
            "Among categories with more than one record, "
            "what is the highest score in each category?"
        ),
        attribute_vocabulary={
            "record": ("category", "score"),
        },
    )
    assert plan is not None
    assert plan.having == (
        HavingSpec(
            AggregateSpec("count", None, "count_all"),
            ">",
            1,
        ),
    )


def test_semantic_validator_accepts_inner_join_equivalent_group_key():
    player_team = AttributeRef("player", "team")
    team_name = AttributeRef("team", "team_name")
    requirement = QueryRequirement(
        query_id="q",
        text="For every team, how many players are on that team?",
        entities=("player", "team"),
        operators=("count", "group_by", "join"),
        plan=QueryPlan(
            group_by=(player_team,),
            aggregates=(AggregateSpec("count", None, "count_all"),),
            joins=(JoinSpec(player_team, team_name),),
        ),
    )
    config = SynthesisConfig(
        SchemaDesign(
            "star",
            (
                RelationSpec(
                    "player",
                    ("team",),
                    foreign_keys=(("team", "team", "team_name"),),
                ),
                RelationSpec("team", ("team_name",)),
            ),
            ("q",),
        ),
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    sql = (
        "SELECT t.team_name, COUNT(*) FROM player p "
        "JOIN team t ON p.team = t.team_name GROUP BY t.team_name"
    )
    assert _semantic_validation_errors(requirement, config, sql) == []
    requirement_without_plan_join = QueryRequirement(
        query_id="q",
        text=requirement.text,
        entities=requirement.entities,
        operators=requirement.operators,
        plan=QueryPlan(
            group_by=(player_team,),
            aggregates=(AggregateSpec("count", None, "count_all"),),
        ),
    )
    assert _semantic_validation_errors(
        requirement_without_plan_join, config, sql
    ) == []


def test_aggregate_compiler_drops_non_grouped_projection():
    branch = AttributeRef("transaction", "branch")
    amount = AttributeRef("transaction", "amount", "real")
    leaked = AttributeRef("transaction", "customer_name")
    plan = QueryPlan(
        projections=(leaked,),
        group_by=(branch,),
        aggregates=(AggregateSpec("avg", amount, "avg_amount"),),
    )
    config = SynthesisConfig(
        SchemaDesign(
            "snowflake",
            (
                RelationSpec(
                    "transaction", ("branch", "amount", "customer_name")
                ),
            ),
            ("q",),
        ),
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    sql = compile_query_plan(plan, config)
    assert sql is not None
    assert "customer_name" not in sql


def test_sql_literal_evidence_overrides_wrong_llm_semantic_type():
    class AlwaysNumeric:
        def generate(self, *_args, **_kwargs):
            return "QUANTITY"

    lattice = LatticePlanner(AlwaysNumeric()).parse_workload(
        [
            "SELECT category, AVG(amount) FROM transaction "
            "WHERE category = 'Retail' GROUP BY category"
        ]
    )
    assert lattice.tables["transaction"].columns["category"].semantic_type == "OTHER"
    assert lattice.tables["transaction"].columns["amount"].semantic_type == "QUANTITY"


def test_projection_insert_records_cell_provenance(tmp_path: Path):
    layer = DataLayer(f"sqlite:///{tmp_path / 'provenance.sqlite'}")
    try:
        layer.create_dynamic_table("item", {"name": "TEXT"})
        result = type(
            "ExtractionResult",
            (),
            {
                "error": None,
                "records": [{"name": "Alpha"}],
                "chunk_id": "item/alpha.txt",
            },
        )()
        layer.bulk_insert_records(
            "item",
            [result],
            doc_id_by_chunk_id={
                "item/alpha.txt": "item/alpha.txt"
            },
        )
        with layer.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT column_name, chunk_id, doc_id "
                    "FROM cell_provenance"
                )
            ).one()
        assert tuple(row) == (
            "name",
            "item/alpha.txt",
            "item/alpha.txt",
        )
    finally:
        layer.close()


def test_dynamic_tables_accept_arbitrary_inferred_identifiers(tmp_path: Path):
    layer = DataLayer(f"sqlite:///{tmp_path / 'identifiers.sqlite'}")
    try:
        table_name = "player.olympic_medal"
        column_name = "medal.total"
        layer.create_dynamic_table(table_name, {column_name: "INTEGER"})
        assert layer.table_exists(table_name)
        layer.insert_record(table_name, {column_name: 3})
        rows = layer.get_all_records(table_name)
        assert len(rows) == 1
        assert rows[0][column_name] == 3
    finally:
        layer.close()


def test_wdirs_backend_treats_unmaterialized_inferred_relation_as_empty():
    class MissingTableLayer:
        @staticmethod
        def table_exists(_table_name):
            return False

        @staticmethod
        def get_all_records(_table_name):
            raise AssertionError("must not query a missing table")

    runner = type(
        "Runner",
        (),
        {
            "llm_client": object(),
            "data_layer": MissingTableLayer(),
            "dataset": "Example",
            "cache_dir": Path("."),
            "enable_attribute_discovery": False,
        },
    )()
    backend = WDIRSPrimitiveBackend(runner)
    backend._table_names = ["city.city_name"]
    assert backend._row_count() == 0
    assert backend.reproducibility_manifest()["missing_inferred_tables"] == [
        "city.city_name"
    ]


def test_wdirs_prunes_provably_inert_configuration_axes():
    schema = SchemaDesign(
        "snowflake",
        (RelationSpec("record", ("category",)),),
        ("q",),
    )
    unsafe = SynthesisConfig(
        schema,
        PopulationConfig(
            er_strategy="embedding_0.7",
            norm_strategy="llm",
            miss_strategy="mode",
        ),
        PreprocessingPolicy("chunked", 1000, 100),
    )
    safe = SynthesisConfig(
        schema,
        PopulationConfig(
            er_strategy="embedding_0.7",
            norm_strategy="dictionary",
            miss_strategy="drop",
        ),
        PreprocessingPolicy("whole_document"),
    )
    backend = object.__new__(WDIRSPrimitiveBackend)
    backend.runner = type(
        "Runner",
        (),
        {
            "lattice_planner": type(
                "Planner",
                (),
                {"lattice": type("Lattice", (), {"tables": {}})()},
            )()
        },
    )()
    result = backend.prune_configs((unsafe, safe))
    assert len(result) == 1
    assert result[0].preprocessing.strategy == "whole_document"
    assert result[0].population.norm_strategy == "dictionary"
    assert result[0].population.miss_strategy == "drop"


def test_relational_profile_checks_declared_and_stored_types(
    tmp_path: Path,
):
    database = tmp_path / "types.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE metric(label NUMERIC, amount TEXT)"
        )
        connection.execute(
            "INSERT INTO metric VALUES (12, 'not-a-number')"
        )
    schema = SchemaDesign(
        "snowflake",
        (
            RelationSpec(
                "metric",
                ("label", "amount"),
                semantic_types=(
                    ("label", "text"),
                    ("amount", "real"),
                ),
            ),
        ),
        ("q",),
    )
    diagnostics = profile_relational_database(database, schema)
    assert diagnostics.type_validity == 0.0


def test_materializer_honors_declared_text_over_numeric_values(
    tmp_path: Path,
):
    schema = SchemaDesign(
        "snowflake",
        (
            RelationSpec(
                "record",
                ("category",),
                semantic_types=(("category", "text"),),
            ),
        ),
        ("q",),
    )
    database = write_sqlite_database(
        tmp_path / "declared_text.sqlite",
        {"record": [{"category": 1}, {"category": 2}]},
        schema,
    )
    with sqlite3.connect(database) as connection:
        declared = connection.execute(
            'PRAGMA table_info("record")'
        ).fetchone()[2]
        storage_types = {
            row[0]
            for row in connection.execute(
                'SELECT typeof("category") FROM "record"'
            )
        }
    assert declared == "TEXT"
    assert storage_types == {"text"}


def test_date_normalization_canonicalizes_equivalent_surfaces():
    assert canonical_date("1919-03-23") == "1919/3/23"
    assert canonical_date("March 23, 1919") == "1919/3/23"


def test_schema_context_repairs_small_model_contract_omissions():
    premium = _normalize_plan_with_schema(
        QueryPlan(
            aggregates=(AggregateSpec("count", None, "count_all"),),
        ),
        "How many Premium records are in the dataset?",
        attribute_vocabulary={"record": ("segment",)},
        context_references=(AttributeRef("record", "segment"),),
    )
    assert premium.predicate == PredicateSpec(
        attribute=AttributeRef("record", "segment"),
        operator="=",
        value="Premium",
    )
    assert premium.group_by == (AttributeRef("record", "segment"),)

    repaired = _normalize_plan_with_schema(
        QueryPlan(
            group_by=(AttributeRef("event", "category"),),
            aggregates=(
                AggregateSpec(
                    "avg",
                    AttributeRef("event", "age", "real"),
                    "avg_age",
                ),
            ),
        ),
        (
            "For each event category, what is the average event amount for "
            "events with matching account and region records?"
        ),
        attribute_vocabulary={
            "event": ("account_id", "amount", "category"),
            "account": ("account_key", "region"),
            "region": ("region_name",),
        },
        join_vocabulary=(
            ("event", "account_id", "account", "account_key"),
            ("account", "region", "region", "region_name"),
        ),
        context_references=(
            AttributeRef("event", "amount", "real"),
            AttributeRef("event", "account_id"),
            AttributeRef("account", "account_key"),
            AttributeRef("account", "region"),
            AttributeRef("region", "region_name"),
        ),
    )
    assert repaired.aggregates == (
        AggregateSpec(
            "avg",
            AttributeRef("event", "amount", "real"),
            "avg_event_amount",
        ),
    )
    assert len(repaired.joins) == 2

    known = _normalize_plan_with_schema(
        QueryPlan(
            group_by=(AttributeRef("event", "category"),),
            aggregates=(
                AggregateSpec(
                    "count",
                    AttributeRef("event", "category"),
                    "count_category",
                ),
            ),
            predicate=PredicateSpec(
                attribute=AttributeRef("event", "amount"),
                operator=">",
                value=0,
            ),
        ),
        "How many have a known amount for each category?",
        attribute_vocabulary={
            "event": ("amount", "category"),
        },
    )
    assert known.aggregates[0].attribute == AttributeRef("event", "amount")

    null_filter = _normalize_plan_with_schema(
        QueryPlan(
            group_by=(AttributeRef("event", "category"),),
            aggregates=(
                AggregateSpec(
                    "min",
                    AttributeRef("event", "amount", "real"),
                    "min_amount",
                ),
            ),
            predicate=PredicateSpec(
                attribute=AttributeRef("event", "group"),
                operator="=",
                value=None,
            ),
        ),
        "What is the lowest amount for each category?",
    )
    assert null_filter.predicate is None

    alternatives = _normalize_plan_with_schema(
        QueryPlan(
            group_by=(AttributeRef("event", "group"),),
            aggregates=(
                AggregateSpec(
                    "sum",
                    AttributeRef("event", "amount", "real"),
                    "sum_amount",
                ),
            ),
        ),
        (
            "For each group, total the amount for records that are either "
            "Premium but not Suspended, or do not belong to Legacy Group."
        ),
        attribute_vocabulary={
            "event": ("amount", "category", "group"),
        },
        context_references=(
            AttributeRef("event", "amount", "real"),
            AttributeRef("event", "category"),
            AttributeRef("event", "group"),
        ),
        join_vocabulary=(
            ("event", "group", "group", "group_name"),
        ),
    )
    assert alternatives.predicate.kind == "or"
    assert alternatives.predicate.children[0].children[0].attribute == (
        AttributeRef("event", "category")
    )
    assert alternatives.predicate.children[1].attribute == AttributeRef(
        "event", "group"
    )

    disjunction = _normalize_plan_with_schema(
        QueryPlan(
            group_by=(AttributeRef("event", "category"),),
            aggregates=(
                AggregateSpec(
                    "sum",
                    AttributeRef("event", "amount", "real"),
                    "sum_amount",
                ),
            ),
        ),
        (
            "By category, total the amount for events that are not on Legacy "
            "Group, have more than two retries, or belong to an account opened "
            "in a year other than 1949."
        ),
        attribute_vocabulary={
            "event": ("account_id", "amount", "category", "group", "retries"),
            "account": ("account_key", "opened_year"),
        },
        join_vocabulary=(
            ("event", "account_id", "account", "account_key"),
        ),
    )
    assert disjunction.predicate.kind == "or"
    assert len(disjunction.predicate.children) == 3
    assert disjunction.predicate.children[0].operator == "!="
    assert disjunction.predicate.children[1].value == 2
    assert disjunction.predicate.children[2].attribute == AttributeRef(
        "account", "opened_year", "integer"
    )


def test_normalization_preserves_valid_candidate_semantics():
    plan = QueryPlan(
        projections=(
            AttributeRef("event", "founding_year"),
            AttributeRef("region", "region_name"),
        ),
        predicate=PredicateSpec(
            attribute=AttributeRef("event", "score", "integer"),
            operator=">=",
            value=0,
        ),
        joins=(
            JoinSpec(
                AttributeRef("event", "region_id"),
                AttributeRef("region", "region_id"),
            ),
        ),
    )
    normalized = _normalize_plan_with_schema(
        plan,
        (
            "Show each event's founding year and its region name when the "
            "event score is at least zero."
        ),
        attribute_vocabulary={
            "event": ("founding_year", "region_id", "score"),
            "region": ("region_id", "region_name"),
        },
        join_vocabulary=(
            ("event", "region_id", "region", "region_id"),
        ),
    )

    assert normalized.projections == plan.projections
    assert normalized.predicate.operator == ">="
    assert normalized.joins == plan.joins

    explicit_zero = _normalize_plan_with_schema(
        QueryPlan(
            projections=(AttributeRef("event", "category"),),
            predicate=PredicateSpec(
                attribute=AttributeRef("event", "retry_count", "integer"),
                operator="is_null",
                value=None,
            ),
        ),
        "Show each event category for events with no retry count.",
        attribute_vocabulary={
            "event": ("category", "retry_count"),
        },
    )
    assert explicit_zero.predicate == PredicateSpec(
        attribute=AttributeRef("event", "retry_count", "integer"),
        operator="=",
        value=0,
    )
