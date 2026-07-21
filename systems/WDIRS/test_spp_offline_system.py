"""Regression tests for the offline, budgeted SPP system layer."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from spp.budget_ledger import BudgetExhausted, GlobalBudgetLedger
from spp.evidence_store import CellProvenance, EvidenceAnchor, EvidenceStore
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
from spp.nl2sql import _verification_payload, make_nl2sql_compiler
from spp.oracle_evaluation import OracleConfigResult, solve_exact_budgeted_oracle
from spp.risk_estimator import CellEvidence, PilotObservation, estimate_query_risk
from spp.quality_signals import MetamorphicCheck, metamorphic_consistency
from spp.schema_materializer import reshape_tables, write_sqlite_database
from spp.schema_design import generate_schema_designs, generate_synthesis_configs
from spp.query_plan_compiler import compile_query_plan
from spp.serving import CompiledQuery, OfflineQueryServer, freeze_serving_bundle
from spp.system import OfflineSynthesisSystem
from spp.spec import (
    AggregateSpec,
    AttributeRef,
    FrozenPortfolio,
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
    _normalize_plan_with_schema,
    _parse_llm_payload,
    analyze_workload,
    schema_vocabulary_from_sql,
)
from spp.population_config import PopulationConfig


def _player_requirement() -> QueryRequirement:
    return QueryRequirement(
        query_id="q0",
        text="SELECT name FROM player",
        entities=("player",),
        attributes=("name",),
    )


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


def test_sql_workload_intent_and_schema_patterns_are_full_cover():
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
    assert all(design.covers(intent.requirements[0]) for design in designs)
    pruned = generate_synthesis_configs(intent, observed_document_lengths=[500])
    exhaustive = generate_synthesis_configs(
        intent, observed_document_lengths=[500], exhaustive=True
    )
    assert len(pruned) < len(exhaustive)


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

    system = OfflineSynthesisSystem(Backend(), compiler)
    result = system.synthesize(
        queries=[{"query_id": "q0", "sql": "SELECT name FROM player"}],
        token_budget=0,
        output_dir=tmp_path / "run",
        observed_document_lengths=[100],
        sample_fractions=(0.1,),
    )
    server = OfflineQueryServer(result.serving_manifest.parent)
    assert server.execute("q0") == [{"name": "Alice"}]
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


def test_nl_intent_analysis_isolates_queries():
    class BatchClient:
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, **_kwargs):
            self.calls += 1
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

    client = BatchClient()
    intent = analyze_workload(
        [
            {"query_id": f"q{index}", "text": f"Show category {index}"}
            for index in range(5)
        ],
        llm_client=client,
    )
    assert client.calls == 10
    assert len(intent.requirements) == 5
    assert all(requirement.plan for requirement in intent.requirements)


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
