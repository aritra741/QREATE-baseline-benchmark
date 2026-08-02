"""Domain-neutral tests for contract-centric QuWARTS."""

from __future__ import annotations

import json
from pathlib import Path

from spp.evidence_store import CellProvenance, EvidenceAnchor, EvidenceStore
from spp.contract_extractor import (
    ContractExtraction,
    ContractExtractor,
    DerivationMapping,
    ExtractionRecord,
    RelationshipRecord,
)
from spp.budget_ledger import GlobalBudgetLedger
from spp.contract_backend import (
    ContractBackend,
    ContractDocument,
    RelationEdge,
    SharedExtraction,
    WorkloadRelationGraph,
    _contract_extraction_parts,
    build_workload_relation_graph,
)
from spp.contract_validation import (
    AdaptiveRepairAdmission,
    ValidationIssue,
    validate_count_date,
    validate_extraction,
    validate_field_local_span,
    validate_identity,
    validate_units_and_conflicts,
    targeted_repair_targets,
)
from spp.spec import (
    AggregateSpec,
    AttributeRef,
    JoinSpec,
    PredicateSpec,
    QualityEstimate,
    QueryPlan,
    QueryRequirement,
    PreprocessingPolicy,
    RelationSpec,
    SchemaDesign,
    SynthesisConfig,
)
from spp.population_config import PopulationConfig
from spp.query_quality import QueryAssessment, assess_query_quality
from spp.schema_materializer import write_sqlite_database
from spp.workload_contract import (
    AttributeContract,
    EntityContract,
    WorkloadContract,
    compile_workload_contract,
)
from spp.workload_intent import WorkloadIntent


def _intent(*requirements: QueryRequirement) -> WorkloadIntent:
    return WorkloadIntent(
        requirements=tuple(requirements),
        entity_frequency={},
        attribute_frequency={},
        operator_frequency={},
    )


def test_workload_contract_preserves_shared_query_roles_and_join_edges():
    account_id = AttributeRef("account", "account_id", "text")
    amount = AttributeRef("transaction", "amount", "real")
    transaction_account = AttributeRef(
        "transaction", "account_id", "text"
    )
    requirement = QueryRequirement(
        query_id="q0",
        text="Average transaction amount for each account over a threshold.",
        entities=("account", "transaction"),
        attributes=("account_id", "amount"),
        attribute_bindings=(
            ("account", "account_id"),
            ("transaction", "amount"),
            ("transaction", "account_id"),
        ),
        relationships=(("account", "has", "transaction"),),
        operators=("avg", "group", "filter", "join"),
        units=("currency",),
        plan=QueryPlan(
            projections=(account_id,),
            group_by=(account_id,),
            aggregates=(AggregateSpec("avg", amount),),
            predicate=PredicateSpec(
                attribute=amount, operator=">", value=100
            ),
            joins=(JoinSpec(account_id, transaction_account),),
        ),
    )
    contract = compile_workload_contract(_intent(requirement))
    assert {entity.name for entity in contract.entities} == {
        "account",
        "transaction",
    }
    amount_contract = next(
        field
        for field in contract.attributes
        if field.entity == "transaction" and field.name == "amount"
    )
    roles = dict(amount_contract.contexts)["q0"]
    assert "aggregate:avg" in roles
    assert "filter:>" in roles
    assert contract.relationships
    assert contract.fingerprint == compile_workload_contract(
        _intent(requirement)
    ).fingerprint
    graph = build_workload_relation_graph(_intent(requirement), contract)
    assert graph.pattern == "snowflake"
    assert {relation.name for relation in graph.relations} == {
        "account",
        "transaction",
    }
    assert all(
        relation.name != "workload_flat" for relation in graph.relations
    )


def test_field_local_validation_rejects_value_from_another_span():
    record = ExtractionRecord(
        entity="account",
        attribute="balance",
        identity="Example account",
        value=200,
        exact_span="Example account opened in 2001",
        unit=None,
        document_id="account/1.txt",
        unit_id="u",
        span_start=0,
        span_end=30,
    )
    issues = validate_field_local_span(
        record,
        "Example account opened in 2001 and has a balance of 200.",
        semantic_types=("integer",),
    )
    assert {issue.code for issue in issues} == {"field_value_not_in_span"}


def test_count_contract_rejects_calendar_year_contamination():
    field = AttributeContract(
        entity="event",
        name="event_count",
        semantic_types=("integer",),
    )
    record = {
        "entity": "event",
        "attribute": "event_count",
        "identity": "Example",
        "value": 2020,
        "exact_span": "The event occurred in 2020.",
    }
    issues = validate_count_date(record, field)
    assert "calendar_year_as_count" in {issue.code for issue in issues}


def test_contract_response_parser_accepts_envelopes_and_mixed_arrays():
    row = {
        "identity": "Example",
        "value": "Example",
        "exact_span": "Example",
        "unit": None,
    }
    assert ContractExtractor._parse_response(
        f"```json\n{json.dumps({'records': [row]})}\n```"
    ) == [row]
    assert ContractExtractor._parse_response(
        json.dumps([row, "discard this commentary", None])
    ) == [row]
    assert ContractExtractor._recover_scalar_entity_response(
        '["Example"]',
        "Example is the primary subject.",
    ) == [row]
    assert (
        ContractExtractor._recover_scalar_entity_response(
            '["Example", "Related"]',
            "Example is the primary subject. Related is mentioned.",
        )
        == []
    )


def test_partition_heading_provides_source_grounded_entity_identity(tmp_path):
    class NoLLM:
        def generate(self, *_args, **_kwargs):
            raise AssertionError("partition heading should avoid an LLM call")

    document = type(
        "Document",
        (),
        {
            "document_id": "record/1.txt",
            "text": "\nExample Subject\n\nExample Subject has a value.",
            "metadata": {},
        },
    )()
    contract = WorkloadContract(
        entities=(EntityContract("record"),),
        attributes=(),
        relationships=(),
    )
    with EvidenceStore(tmp_path / "heading.sqlite") as evidence:
        extractor = ContractExtractor(
            (document,),
            NoLLM(),
            evidence,
            max_workers=1,
        )
        records = extractor.extract_entities(contract)
    assert len(records) == 1
    assert records[0].identity == "Example Subject"
    assert records[0].exact_span == "Example Subject"


def test_identity_validation_accepts_unique_source_local_name_surface():
    record = {
        "entity": "person",
        "attribute": "value",
        "identity": "Jaden Ivey",
        "exact_span": "Ivey was selected with the fifth overall pick.",
    }
    assert validate_identity(
        record,
        ("Jaden Ivey",),
        require_span_support=True,
    ) == ()


def test_field_grounding_accepts_explicit_boolean_and_singular_event():
    boolean_record = {
        "entity": "item",
        "attribute": "verified",
        "identity": "Item",
        "value": True,
        "exact_span": "Item was verified.",
    }
    assert validate_field_local_span(
        boolean_record,
        "Item was verified.",
        semantic_types=("boolean",),
    ) == ()
    count_record = {
        "entity": "item",
        "attribute": "awards",
        "identity": "Item",
        "value": 1,
        "exact_span": "Item received an award.",
    }
    assert validate_field_local_span(
        count_record,
        "Item received an award.",
        semantic_types=("integer",),
    ) == ()


def test_age_derivation_uses_birth_year_and_corpus_reference_year(tmp_path):
    document = type(
        "Document",
        (),
        {
            "document_id": "person/1.txt",
            "text": (
                "\nExample Person\n\n"
                "Example Person (born January 2, 2000) is documented here. "
                "The record was updated in 2024."
            ),
            "metadata": {},
        },
    )()
    contract = WorkloadContract(
        entities=(EntityContract("person"),),
        attributes=(
            AttributeContract(
                "person",
                "age",
                semantic_types=("integer",),
            ),
        ),
        relationships=(),
    )
    with EvidenceStore(tmp_path / "age.sqlite") as evidence:
        extractor = ContractExtractor(
            (document,),
            object(),
            evidence,
            max_workers=1,
        )
        extraction = extractor.extract(contract)
    assert len(extraction.attribute_records) == 1
    age = extraction.attribute_records[0]
    assert age.value == 24
    assert age.derivation_kind == "age_from_birth_year"
    assert validate_extraction(
        extraction,
        contract,
        {"person/1.txt": document.text},
    ) == ()


def test_heading_derivation_separates_entity_name_and_region(tmp_path):
    document = type(
        "Document",
        (),
        {
            "document_id": "place/1.txt",
            "text": "\nExample City, Example Region\n\nSource text.",
            "metadata": {},
        },
    )()
    contract = WorkloadContract(
        entities=(EntityContract("place"),),
        attributes=(
            AttributeContract(
                "place", "name", semantic_types=("text",)
            ),
            AttributeContract(
                "place", "region", semantic_types=("text",)
            ),
        ),
        relationships=(),
    )
    with EvidenceStore(tmp_path / "heading.sqlite") as evidence:
        extraction = ContractExtractor(
            (document,),
            object(),
            evidence,
            max_workers=1,
        ).extract(contract)
    values = {
        record.attribute: record.value
        for record in extraction.attribute_records
    }
    assert values == {
        "name": "Example City",
        "region": "Example Region",
    }
    assert validate_extraction(
        extraction,
        contract,
        {"place/1.txt": document.text},
    ) == ()


def test_attribute_canonicalization_uses_each_documents_identity(tmp_path):
    class AttributeClient:
        def __init__(self):
            self.ledger = type("Ledger", (), {"actual_spent": 0})()

        def generate(self, prompt, **_kwargs):
            if "Alpha Record" in prompt:
                return (
                    '[{"identity":"Alpha","value":"Type A",'
                    '"exact_span":"Alpha Record is Type A.","unit":null}]'
                )
            return (
                '[{"identity":"Beta","value":"Type B",'
                '"exact_span":"Beta Record is Type B.","unit":null}]'
            )

    documents = tuple(
        type(
            "Document",
            (),
            {
                "document_id": f"record/{index}.txt",
                "text": f"\n{name} Record\n\n{name} Record is Type {kind}.",
                "metadata": {},
            },
        )()
        for index, (name, kind) in enumerate(
            (("Alpha", "A"), ("Beta", "B")),
            start=1,
        )
    )
    contract = WorkloadContract(
        entities=(EntityContract("record"),),
        attributes=(
            AttributeContract(
                "record", "kind", semantic_types=("text",)
            ),
        ),
        relationships=(),
    )
    with EvidenceStore(tmp_path / "identity-context.sqlite") as evidence:
        extraction = ContractExtractor(
            documents,
            AttributeClient(),
            evidence,
            max_workers=1,
        ).extract(contract)
    assert {
        record.identity for record in extraction.attribute_records
    } == {"Alpha Record", "Beta Record"}


def test_contract_extraction_retries_bad_shape_without_aborting(tmp_path):
    class FormatRetryClient:
        def __init__(self):
            self.responses = iter(('["not an object"]', "[null]"))
            self.ledger = type("Ledger", (), {"actual_spent": 0})()
            self.calls = 0

        def generate(self, *_args, **_kwargs):
            self.calls += 1
            return next(self.responses)

    client = FormatRetryClient()
    document = type(
        "Document",
        (),
        {
            "document_id": "record/1.txt",
            "text": "Example",
            "metadata": {},
        },
    )()
    with EvidenceStore(tmp_path / "malformed.sqlite") as evidence:
        extractor = ContractExtractor(
            (document,),
            client,
            evidence,
            max_workers=1,
        )
        rows = extractor._rows(
            phase="entity",
            prompt="Return the entity row.",
            unit=extractor.units[0],
            max_tokens=32,
        )
    assert rows == []
    assert client.calls == 2


def test_attribute_context_is_bounded_and_preserves_source_offsets(tmp_path):
    relevant = "Subject has rare metric 42."
    text = "Subject\n" + ("irrelevant material " * 1500) + relevant
    document = type(
        "Document",
        (),
        {
            "document_id": "record/1.txt",
            "text": text,
            "metadata": {},
        },
    )()
    with EvidenceStore(tmp_path / "focused.sqlite") as evidence:
        extractor = ContractExtractor(
            (document,),
            object(),
            evidence,
            max_workers=1,
            max_context_characters=1200,
        )
        focused = extractor._focused_unit(
            extractor.units[0],
            terms=("rare_metric",),
        )
        assert len(focused.text) <= 1202
        assert relevant in focused.text
        records = extractor._records(
            phase="attribute",
            entity="record",
            attribute="rare_metric",
            unit=focused,
            rows=(
                {
                    "identity": "Subject",
                    "value": 42,
                    "exact_span": relevant,
                    "unit": None,
                },
            ),
        )
    assert len(records) == 1
    assert records[0].span_start == text.index(relevant)
    assert text[records[0].span_start : records[0].span_end] == relevant


def test_conflicts_are_retained_as_validation_outcomes():
    field = AttributeContract(
        entity="account",
        name="balance",
        semantic_types=("real",),
        units=("USD",),
    )
    records = [
        {
            "entity": "account",
            "attribute": "balance",
            "identity": "A",
            "value": 10,
            "unit": "USD",
        },
        {
            "entity": "account",
            "attribute": "balance",
            "identity": "A",
            "value": 12,
            "unit": "USD",
        },
    ]
    issues = validate_units_and_conflicts(records, (field,))
    assert "conflicting_values" in {issue.code for issue in issues}


def test_unit_derivations_keep_raw_value_and_explicit_lineage():
    assert ContractExtractor._unit_scale("million units") == 1_000_000
    mapping = DerivationMapping(
        entity="measurement",
        attribute="amount",
        source_value=1.2,
        target_value=1_200_000,
        mapping_kind="unit",
        source_unit="million units",
        target_unit="units",
        supporting_document_ids=("measurement/1.txt",),
    )
    assert mapping.source_value == 1.2
    assert mapping.target_value == 1_200_000
    assert mapping.to_payload()["mapping_kind"] == "unit"
    taxonomy = DerivationMapping(
        entity="item",
        attribute="category",
        source_value="Detailed class",
        target_value="Broad class",
        mapping_kind="taxonomy",
        supporting_document_ids=("item/1.txt", "item/2.txt"),
    )
    assert taxonomy.supporting_document_ids
    assert taxonomy.source_value != taxonomy.target_value


def test_adaptive_repair_requires_novel_violation_and_preserves_reserve():
    admission = AdaptiveRepairAdmission()
    issue = ValidationIssue(
        code="field_value_not_in_span",
        message="not locally grounded",
        entity="account",
        attribute="balance",
    )
    assert admission.admit(
        (issue,),
        estimated_repair_tokens=100,
        completion_reserve=500,
        remaining_tokens=1000,
    )
    assert not admission.admit(
        (issue,),
        estimated_repair_tokens=100,
        completion_reserve=500,
        remaining_tokens=1000,
    )
    novel = ValidationIssue(
        code="unit_mismatch",
        message="wrong dimension",
        entity="account",
        attribute="balance",
    )
    assert not admission.admit(
        (novel,),
        estimated_repair_tokens=501,
        completion_reserve=500,
        remaining_tokens=1000,
    )


def test_uncovered_attribute_creates_one_document_local_repair_target():
    balance = AttributeRef("account", "balance", "real")
    requirement = QueryRequirement(
        query_id="q0",
        text="Show each account balance.",
        entities=("account",),
        attributes=("balance",),
        attribute_bindings=(("account", "balance"),),
        plan=QueryPlan(projections=(balance,)),
    )
    contract = compile_workload_contract(_intent(requirement))
    entity_record = ExtractionRecord(
        entity="account",
        attribute=None,
        identity="Account Alpha",
        value="Account Alpha",
        exact_span="Account Alpha",
        unit=None,
        document_id="account/1.txt",
        unit_id="u",
        span_start=0,
        span_end=13,
    )
    extraction = ContractExtraction(
        contract.fingerprint,
        (entity_record,),
        (),
    )
    issues = validate_extraction(
        extraction,
        contract,
        {"account/1.txt": "Account Alpha has no stated balance."},
    )
    assert "attribute_contract_uncovered" in {
        issue.code for issue in issues
    }
    targets = targeted_repair_targets(issues)
    assert any(
        target.phase == "attribute"
        and target.document_id == "account/1.txt"
        and target.attribute == "balance"
        for target in targets
    )


def test_executed_quality_reports_ground_truth_free_metamorphic_signals(
    tmp_path: Path,
):
    category = AttributeRef("record", "category", "text")
    amount = AttributeRef("record", "amount", "real")
    requirement = QueryRequirement(
        query_id="q0",
        text="Average amount for each category when amount is positive.",
        entities=("record",),
        attributes=("category", "amount"),
        attribute_bindings=(
            ("record", "category"),
            ("record", "amount"),
        ),
        operators=("avg", "group", "filter"),
        plan=QueryPlan(
            projections=(category,),
            group_by=(category,),
            aggregates=(AggregateSpec("avg", amount, alias="avg_amount"),),
            predicate=PredicateSpec(
                attribute=amount, operator=">", value=0
            ),
        ),
    )
    schema = SchemaDesign(
        pattern="snowflake",
        relations=(
            RelationSpec(
                "record",
                ("category", "amount"),
                semantic_types=(
                    ("category", "text"),
                    ("amount", "real"),
                ),
            ),
        ),
        covered_query_ids=("q0",),
    )
    config = SynthesisConfig(
        schema=schema,
        population=PopulationConfig(
            er_strategy="raw",
            norm_strategy="raw",
            unit_strategy="none",
            miss_strategy="drop",
            type_coercion="strict",
        ),
        preprocessing=PreprocessingPolicy("whole_document"),
    )
    database = write_sqlite_database(
        tmp_path / "candidate.sqlite",
        {
            "record": [
                {"category": "A", "amount": 10},
                {"category": "A", "amount": 20},
                {"category": "B", "amount": 5},
            ]
        },
        schema,
    )
    with EvidenceStore(tmp_path / "evidence.sqlite") as evidence:
        rows = []
        for index, (category_value, amount_value) in enumerate(
            (("A", 10), ("A", 20), ("B", 5))
        ):
            document_id = f"record/{index}.txt"
            text = f"{category_value} has amount {amount_value}"
            evidence.add_document(document_id, text)
            for column, value, surface in (
                ("category", category_value, category_value),
                ("amount", amount_value, str(amount_value)),
            ):
                start = text.index(surface)
                anchor = EvidenceAnchor.create(
                    document_id=document_id,
                    text=surface,
                    start=start,
                    end=start + len(surface),
                    anchor_type="contract_attribute_span",
                )
                evidence.add_anchors((anchor,))
                rows.append(
                    CellProvenance(
                        config.config_id,
                        "record",
                        str(index),
                        column,
                        f'"{value}"'
                        if isinstance(value, str)
                        else str(value),
                        anchor.anchor_id,
                        True,
                        True,
                    )
                )
        evidence.add_cell_provenance(rows)
        assessment = assess_query_quality(
            requirement, config, database, evidence
        )
    assert assessment.error is None
    assert assessment.execution is not None
    assert assessment.execution.rows == (
        {"category": "A", "avg_amount": 15.0},
        {"category": "B", "avg_amount": 5.0},
    )
    for signal in (
        "required_attribute_coverage",
        "output_stability",
        "metamorphic_consistency",
        "predicate_monotonicity",
        "aggregate_bounds",
        "grouping_consistency",
        "bootstrap_stability",
    ):
        assert signal in assessment.estimate.components
    assert assessment.estimate.components["required_attribute_coverage"] == 1.0


def test_query_quality_rejects_missing_required_attribute_evidence(
    tmp_path: Path,
):
    category = AttributeRef("record", "category", "text")
    amount = AttributeRef("record", "amount", "real")
    requirement = QueryRequirement(
        query_id="q0",
        text="Average amount for each category.",
        entities=("record",),
        plan=QueryPlan(
            group_by=(category,),
            aggregates=(AggregateSpec("avg", amount, alias="avg_amount"),),
        ),
    )
    schema = SchemaDesign(
        "snowflake",
        (
            RelationSpec(
                "record",
                ("category", "amount"),
                semantic_types=(("category", "text"), ("amount", "real")),
            ),
        ),
        ("q0",),
    )
    config = SynthesisConfig(
        schema,
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    database = write_sqlite_database(
        tmp_path / "missing.sqlite",
        {"record": [{"category": "A", "amount": None}]},
        schema,
    )
    assessment = assess_query_quality(
        requirement,
        config,
        database,
        None,
    )
    assert assessment.estimate.components["required_attribute_coverage"] == 0.0
    assert assessment.estimate.validity == 0.0


def test_contract_backend_materializes_explicit_relationship_edges(
    tmp_path: Path,
):
    class FakeClient:
        model = "fixture-model"

        def generate(self, prompt, **_kwargs):
            if "Entity contract:" in prompt:
                if '"entity": "account"' in prompt:
                    return (
                        '[{"identity":"Account Alpha","value":"Account Alpha",'
                        '"exact_span":"Account Alpha","unit":null}]'
                    )
                return (
                    '[{"identity":"Transaction T","value":"Transaction T",'
                    '"exact_span":"Transaction T","unit":null}]'
                )
            if "Relationship contract:" in prompt:
                if "belongs to Account Alpha" not in prompt:
                    return "[]"
                return (
                    '[{"left_identity":"Account Alpha",'
                    '"right_identity":"Transaction T",'
                    '"exact_span":"Transaction T belongs to Account Alpha"}]'
                )
            if '"attribute": "amount"' in prompt:
                return (
                    '[{"identity":"Transaction T","value":10,'
                    '"exact_span":"Transaction T belongs to Account Alpha '
                    'and has amount 10","unit":null}]'
                )
            return "[]"

    account_id = AttributeRef("account", "id", "text")
    transaction_account = AttributeRef(
        "transaction", "account_id", "text"
    )
    amount = AttributeRef("transaction", "amount", "real")
    requirement = QueryRequirement(
        query_id="q0",
        text="Sum transaction amounts for each account.",
        entities=("account", "transaction"),
        attributes=("id", "account_id", "amount"),
        attribute_bindings=(
            ("account", "id"),
            ("transaction", "account_id"),
            ("transaction", "amount"),
        ),
        relationships=(("account", "id=account_id", "transaction"),),
        operators=("sum", "group", "join"),
        plan=QueryPlan(
            projections=(account_id,),
            group_by=(account_id,),
            aggregates=(
                AggregateSpec("sum", amount, alias="sum_amount"),
            ),
            joins=(JoinSpec(account_id, transaction_account),),
        ),
    )
    intent = _intent(requirement)
    backend = ContractBackend(
        (
            ContractDocument(
                "account/1.txt",
                "Account Alpha is an account.",
            ),
            ContractDocument(
                "transaction/1.txt",
                "Transaction T belongs to Account Alpha and has amount 10.",
            ),
        ),
        FakeClient(),
        scratch_dir=tmp_path,
    )
    configs = backend.generate_configs(
        intent, observed_document_lengths=(28, 62)
    )
    ledger = GlobalBudgetLedger(100_000)
    with EvidenceStore(tmp_path / "backend-evidence.sqlite") as evidence:
        backend.prepare(intent, evidence, ledger)
        retained = backend.prune_configs(configs)
        assert retained
        database = backend.materialize(
            retained[0],
            evidence,
            ledger,
            tmp_path / "backend.sqlite",
        )
        assessment = assess_query_quality(
            requirement, retained[0], database, evidence
        )
    assert assessment.error is None
    assert assessment.execution is not None
    assert assessment.execution.rows == (
        {"id": "Account Alpha", "sum_amount": 10},
    )


def test_contract_backend_rebinds_join_only_from_observed_overlap(tmp_path):
    team_id = AttributeRef("team", "id", "integer")
    team_name = AttributeRef("team", "name", "text")
    player_team_id = AttributeRef("player", "team_id", "integer")
    player_name = AttributeRef("player", "name", "text")
    requirement = QueryRequirement(
        "q0",
        "List players for each team.",
        entities=("team", "player"),
        plan=QueryPlan(
            group_by=(team_name,),
            aggregates=(AggregateSpec("count", player_name),),
            joins=(JoinSpec(team_id, player_team_id),),
        ),
    )
    backend = ContractBackend(
        (ContractDocument("record/1.txt", "Example"),),
        object(),
        scratch_dir=tmp_path,
    )
    backend.relation_graph = WorkloadRelationGraph(
        relations=(
            RelationSpec(
                "team",
                ("id", "name"),
                semantic_types=(("id", "integer"), ("name", "text")),
            ),
            RelationSpec(
                "player",
                ("name", "team_id", "team_name"),
                semantic_types=(
                    ("name", "text"),
                    ("team_id", "integer"),
                    ("team_name", "text"),
                ),
            ),
        ),
        edges=(RelationEdge("team", "id", "player", "team_id"),),
        covered_query_ids=("q0",),
    )
    backend._shared = SharedExtraction(
        raw_tables={
            "team": (
                {"id": None, "name": "A"},
                {"id": None, "name": "B"},
            ),
            "player": (
                {"name": "P1", "team_id": None, "team_name": "A"},
                {"name": "P2", "team_id": None, "team_name": "B"},
            ),
        },
        evidence=(),
    )
    refined = backend.refine_intent(_intent(requirement))
    join = refined.requirements[0].plan.joins[0]
    assert (join.left.attribute, join.right.attribute) == (
        "name",
        "team_name",
    )
    assert join.left.semantic_type == "text"
    assert join.right.semantic_type == "text"
    disconnected = QueryRequirement(
        "q1",
        "List players for each team.",
        entities=("team", "player"),
        plan=QueryPlan(
            group_by=(team_name,),
            aggregates=(AggregateSpec("count", player_name),),
        ),
    )
    disconnected_intent = _intent(disconnected)
    schema = backend._validated_schema(disconnected_intent)
    assert schema.covered_query_ids == ("q1",)
    assert backend._preparation_unbound_query_ids == ("q1",)
    repaired = backend.refine_intent(disconnected_intent)
    repaired_join = repaired.requirements[0].plan.joins[0]
    assert (repaired_join.left.attribute, repaired_join.right.attribute) == (
        "name",
        "team_name",
    )


def test_relationship_materialization_cannot_create_unknown_endpoint_rows():
    entity_player = ExtractionRecord(
        "player",
        None,
        "Player A",
        "Player A",
        "Player A",
        None,
        "player/1.txt",
        "u1",
        0,
        8,
    )
    nationality = ExtractionRecord(
        "player",
        "nationality",
        "Player A",
        "Example",
        "Player A is Example",
        None,
        "player/1.txt",
        "u1",
        0,
        19,
    )
    entity_team = ExtractionRecord(
        "team",
        None,
        "Team A",
        "Team A",
        "Team A",
        None,
        "team/1.txt",
        "u2",
        0,
        6,
    )
    relationship = RelationshipRecord(
        "member_of",
        "player",
        "team",
        "Player A",
        "Unknown Team",
        "Player A joined Unknown Team",
        "player/1.txt",
        "u1",
        0,
        28,
    )
    graph = WorkloadRelationGraph(
        relations=(
            RelationSpec("player", ("nationality", "team_name")),
            RelationSpec("team", ("name",), primary_key="name"),
        ),
        edges=(
            RelationEdge("player", "team_name", "team", "name"),
        ),
        covered_query_ids=("q0",),
    )
    raw, _evidence = _contract_extraction_parts(
        ContractExtraction(
            "contract",
            (entity_player, entity_team),
            (nationality,),
            (relationship,),
        ),
        graph,
        set(),
        set(),
    )
    assert len(raw["player"]) == 1
    assert [row["name"] for row in raw["team"]] == ["Team A"]


def test_raw_candidate_cannot_ignore_an_explicit_query_mapping():
    category = AttributeRef("item", "category", "text")
    requirement = QueryRequirement(
        query_id="q0",
        text="Group items by the requested broad category.",
        entities=("item",),
        attributes=("category",),
        attribute_bindings=(("item", "category"),),
        plan=QueryPlan(
            projections=(category,),
            group_by=(category,),
            aggregates=(AggregateSpec("count"),),
        ),
    )
    intent = _intent(requirement)
    backend = ContractBackend(
        (ContractDocument("item/1.txt", "An item."),),
        object(),
    )
    configs = backend.generate_configs(intent)
    raw = next(
        config
        for config in configs
        if config.population.norm_strategy == "raw"
    )
    semantic = next(
        config
        for config in configs
        if config.population.norm_strategy == "contract_mapping"
    )
    backend.intent = intent
    backend._shared = SharedExtraction(
        raw_tables={"item": ()},
        evidence=(),
        metadata={
            "derivation_mappings": [
                {
                    "entity": "item",
                    "attribute": "category",
                    "source_value": "Detailed",
                    "target_value": "Broad",
                    "mapping_kind": "taxonomy",
                }
            ]
        },
    )

    def assessment(config: SynthesisConfig) -> QueryAssessment:
        return QueryAssessment(
            QualityEstimate(
                "q0",
                config.config_id,
                1.0,
                1.0,
                1.0,
                0.0,
                1,
            ),
            None,
            None,
        )

    raw_result = backend._apply_mapping_contract(
        raw, {"q0": assessment(raw)}
    )["q0"].estimate
    semantic_result = backend._apply_mapping_contract(
        semantic, {"q0": assessment(semantic)}
    )["q0"].estimate
    assert raw_result.validity == 0.0
    assert raw_result.components["contract_mapping_alignment"] == 0.0
    assert semantic_result.validity == 1.0
    assert semantic_result.components["contract_mapping_alignment"] == 1.0


def test_contract_modules_do_not_contain_benchmark_path_literals():
    root = Path(__file__).resolve().parent / "spp"
    forbidden = ("data/", ".csv", "evaluation.json")
    for name in (
        "workload_contract.py",
        "contract_extractor.py",
        "contract_validation.py",
        "contract_backend.py",
        "query_quality.py",
    ):
        source = (root / name).read_text(encoding="utf-8").lower()
        assert not any(value in source for value in forbidden)
