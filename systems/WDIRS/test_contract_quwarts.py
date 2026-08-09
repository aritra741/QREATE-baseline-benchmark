"""Domain-neutral tests for contract-centric QuWARTS."""

from __future__ import annotations

import json
from pathlib import Path

from spp.calculation_tools import operands_are_grounded
from spp.cell_verifier import (
    BudgetAwareCellVerifier,
    CellClaim,
    VerificationDecision,
    VerificationReport,
)
from spp.evidence_store import CellProvenance, EvidenceAnchor, EvidenceStore
from spp.contract_extractor import (
    ContractExtraction,
    ContractExtractor,
    DerivationMapping,
    ExtractionRecord,
    RelationshipRecord,
    SourceDocument,
    route_documents_by_content,
)
from spp.budget_ledger import GlobalBudgetLedger
from spp.contract_backend import (
    ContractBackend,
    ContractDocument,
    RelationEdge,
    SharedCellEvidence,
    SharedExtraction,
    WorkloadRelationGraph,
    _contract_extraction_parts,
    _merge_shared_extractions,
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
from spp.query_plan_compiler import compile_query_plan
from spp.query_quality import QueryAssessment, assess_query_quality
from spp.schema_materializer import write_sqlite_database
from spp.workload_contract import (
    AttributeContract,
    EntityContract,
    RelationshipContract,
    WorkloadContract,
    compile_workload_contract,
)
from spp.workload_intent import WorkloadIntent, analyze_sql_contract_workload


def _intent(*requirements: QueryRequirement) -> WorkloadIntent:
    return WorkloadIntent(
        requirements=tuple(requirements),
        entity_frequency={},
        attribute_frequency={},
        operator_frequency={},
    )


def test_content_routing_ignores_misleading_document_paths():
    contract = WorkloadContract(
        entities=(
            EntityContract("vehicle"),
            EntityContract("place"),
        ),
        attributes=(
            AttributeContract("vehicle", "wheel_count"),
            AttributeContract("place", "population"),
        ),
        relationships=(),
    )
    documents = (
        SourceDocument(
            "place/misleading.txt",
            "Roadster\nThis vehicle has four wheels.",
        ),
        SourceDocument(
            "vehicle/misleading.txt",
            "Northbank\nIts population is 12000 residents.",
        ),
    )

    routes = route_documents_by_content(documents, contract)

    assert routes["vehicle"] == ("place/misleading.txt",)
    assert routes["place"] == ("vehicle/misleading.txt",)


def test_content_routing_uses_primary_subject_before_related_entities():
    contract = WorkloadContract(
        entities=(
            EntityContract("member"),
            EntityContract("organization"),
        ),
        attributes=(
            AttributeContract("member", "organization_name"),
            AttributeContract("member", "score"),
            AttributeContract("organization", "score"),
            AttributeContract("organization", "member_count"),
        ),
        relationships=(),
    )
    documents = (
        SourceDocument(
            "opaque-1",
            "Alice is a member of the North organization and has score 4.",
        ),
        SourceDocument(
            "opaque-2",
            "North is an organization whose members have a combined score of 8.",
        ),
    )

    routes = route_documents_by_content(documents, contract)

    assert routes["member"] == ("opaque-1",)
    assert routes["organization"] == ("opaque-2",)


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


def test_workload_contract_preserves_query_scoped_category_targets():
    position = AttributeRef("player", "position", "text")
    requirement = QueryRequirement(
        query_id="q0",
        text="How many players are Frontcourt and Backcourt?",
        entities=("player",),
        attributes=("position",),
        attribute_bindings=(("player", "position"),),
        operators=("group", "filter"),
        plan=QueryPlan(
            projections=(position,),
            group_by=(position,),
            predicate=PredicateSpec(
                kind="or",
                children=(
                    PredicateSpec(
                        attribute=position,
                        operator="=",
                        value="Frontcourt",
                    ),
                    PredicateSpec(
                        attribute=position,
                        operator="=",
                        value="Backcourt",
                    ),
                ),
            ),
        ),
    )

    contract = compile_workload_contract(_intent(requirement))
    attribute = contract.attributes_for("player")[0]

    assert attribute.value_constraints == (
        ("q0", ("Backcourt", "Frontcourt")),
    )


def test_sql_contract_preserves_player_team_owner_join_key_chain():
    intent = analyze_sql_contract_workload(
        [
            {
                "query_id": "q0",
                "sql_query": (
                    "SELECT o.name, COUNT(*) AS player_count "
                    "FROM player p "
                    "JOIN team t ON p.team = t.team_name "
                    "JOIN owner o ON t.team_name = o.nba_team "
                    "GROUP BY o.name"
                ),
            }
        ]
    )

    contract = compile_workload_contract(intent)
    endpoint_pairs = {
        (
            relationship.left_entity,
            left_attribute,
            relationship.right_entity,
            right_attribute,
        )
        for relationship in contract.relationships
        for left_attribute, right_attribute in relationship.endpoint_pairs
    }

    assert endpoint_pairs == {
        ("player", "team", "team", "team_name"),
        ("team", "team_name", "owner", "nba_team"),
    }


def test_derived_group_contract_targets_source_columns_not_aliases():
    intent = analyze_sql_contract_workload(
        [
            {
                "query_id": "q0",
                "sql_query": (
                    "SELECT CASE WHEN age < 30 THEN 'young' ELSE 'older' "
                    "END AS age_band, COUNT(*) AS player_count "
                    "FROM player GROUP BY age_band"
                ),
            }
        ]
    )

    contract = compile_workload_contract(intent)
    attributes = {
        attribute.name: attribute
        for attribute in contract.attributes_for("player")
    }

    assert "age" in attributes
    assert "age_band" not in attributes
    assert dict(attributes["age"].contexts)["q0"] == (
        "binding",
        "group_by",
        "projection",
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
    assert next(
        issue
        for issue in issues
        if issue.code == "calendar_year_as_count"
    ).severity == "warning"


def test_award_count_flags_bare_calendar_year_for_semantic_verification():
    field = AttributeContract(
        entity="person",
        name="mvp_awards",
        semantic_types=("integer",),
    )
    record = {
        "entity": "person",
        "attribute": "mvp_awards",
        "identity": "Example",
        "value": 2021,
        "exact_span": "2021",
    }
    issues = validate_count_date(record, field)
    assert "calendar_year_as_count" in {issue.code for issue in issues}
    assert next(
        issue
        for issue in issues
        if issue.code == "calendar_year_as_count"
    ).severity == "warning"


def test_casefold_taxonomy_collapses_surface_variants():
    attribute = AttributeContract(
        "person", "role", semantic_types=("text",)
    )
    records = (
        ExtractionRecord(
            "person",
            "role",
            "A",
            "Guard",
            "Guard",
            None,
            "person/1.txt",
            "u1",
            0,
            5,
        ),
        ExtractionRecord(
            "person",
            "role",
            "B",
            "guard",
            "guard",
            None,
            "person/2.txt",
            "u2",
            0,
            5,
        ),
    )
    mappings = ContractExtractor._casefold_taxonomy_mappings(
        attribute, records
    )
    assert len(mappings) == 1
    assert {mappings[0].source_value, mappings[0].target_value} == {
        "Guard",
        "guard",
    }


def test_casefold_taxonomy_runs_after_an_llm_budget_boundary(tmp_path):
    class NoCallClient:
        model = "fixture"
        ledger = type("Ledger", (), {"actual_spent": 0})()

        def generate(self, *_args, **_kwargs):
            raise AssertionError("casefold mapping must not call the LLM")

    attribute = AttributeContract(
        "person",
        "role",
        semantic_types=("text",),
        contexts=(("q0", ("group_by", "filter:is_not_null")),),
    )
    contract = WorkloadContract(
        entities=(EntityContract("person"),),
        attributes=(attribute,),
        relationships=(),
    )
    records = tuple(
        ExtractionRecord(
            "person",
            "role",
            identity,
            value,
            value,
            None,
            f"person/{identity}.txt",
            identity,
            0,
            len(value),
        )
        for identity, value in (("a", "Guard"), ("b", "guard"))
    )
    documents = tuple(
        type(
            "Document",
            (),
            {
                "document_id": record.document_id,
                "text": record.exact_span,
                "metadata": {},
            },
        )()
        for record in records
    )
    with EvidenceStore(tmp_path / "evidence.sqlite") as store:
        extractor = ContractExtractor(documents, NoCallClient(), store)
        extractor._budget_exhausted = True
        mappings = extractor._taxonomy_mappings(contract, records)
    assert len(mappings) == 1


def test_mapping_escrow_is_released_for_taxonomy(tmp_path):
    ledger = GlobalBudgetLedger(20_000)
    reservation_id = ledger.reserve(
        stage="contract_extraction",
        operation="required_taxonomy_escrow",
        input_tokens=0,
        max_output_tokens=16_384,
    )

    class EscrowClient:
        model = "fixture"

        def __init__(self):
            self.ledger = ledger

    document = type(
        "Document",
        (),
        {
            "document_id": "item/1.txt",
            "text": "An item.",
            "metadata": {},
        },
    )()
    with EvidenceStore(tmp_path / "escrow.sqlite") as evidence:
        extractor = ContractExtractor(
            (document,), EscrowClient(), evidence
        )
        extractor.set_mapping_escrow(reservation_id)
        assert ledger.available == 3_616
        extractor.release_mapping_escrow()

    assert ledger.available == 20_000
    assert ledger.charges()[0].status == "cancelled"


def test_filtered_grouping_uses_sql_category_targets_for_taxonomy(tmp_path):
    class PositionTaxonomyClient:
        model = "fixture"

        def __init__(self):
            self.ledger = type("Ledger", (), {"actual_spent": 0})()

        def generate(self, prompt, **_kwargs):
            assert (
                'Canonical target values: ["Backcourt", "Frontcourt"]'
                in prompt
            )
            return json.dumps(
                [
                    {
                        "source_value": "Center",
                        "target_value": "Frontcourt",
                    },
                    {
                        "source_value": "Point Guard",
                        "target_value": "Backcourt",
                    },
                    {
                        "source_value": "Power Forward",
                        "target_value": "Frontcourt",
                    },
                    {
                        "source_value": "Shooting Guard",
                        "target_value": "Backcourt",
                    },
                ]
            )

    document = type(
        "Document",
        (),
        {
            "document_id": "player/1.txt",
            "text": "Center Point Guard Power Forward Shooting Guard",
            "metadata": {},
        },
    )()
    attribute = AttributeContract(
        "player",
        "position",
        semantic_types=("text",),
        contexts=(("q0", ("filter:=", "group_by")),),
        query_hints=(
            ("q0", "How many players are Frontcourt and Backcourt?"),
        ),
        value_constraints=(("q0", ("Backcourt", "Frontcourt")),),
    )
    contract = WorkloadContract(
        entities=(EntityContract("player"),),
        attributes=(attribute,),
        relationships=(),
    )
    records = tuple(
        ExtractionRecord(
            "player",
            "position",
            str(index),
            value,
            value,
            None,
            "player/1.txt",
            "u1",
            index,
            index + len(value),
        )
        for index, value in enumerate(
            (
                "Center",
                "Point Guard",
                "Power Forward",
                "Shooting Guard",
            )
        )
    )

    with EvidenceStore(tmp_path / "position-taxonomy.sqlite") as evidence:
        extractor = ContractExtractor(
            (document,),
            PositionTaxonomyClient(),
            evidence,
            max_workers=1,
        )
        mappings = extractor._taxonomy_mappings(contract, records)

    assert {
        (mapping.source_value, mapping.target_value)
        for mapping in mappings
    } == {
        ("Center", "Frontcourt"),
        ("Point Guard", "Backcourt"),
        ("Power Forward", "Frontcourt"),
        ("Shooting Guard", "Backcourt"),
    }
    assert {record.value for record in records} == {
        "Center",
        "Point Guard",
        "Power Forward",
        "Shooting Guard",
    }


def test_join_key_er_resolves_declared_multihop_component_only(tmp_path):
    class JoinEntityClient:
        model = "fixture"

        def __init__(self):
            self.ledger = type("Ledger", (), {"actual_spent": 0})()

        def generate(self, prompt, **_kwargs):
            assert '"player", "team"' in prompt
            assert '"team", "team_name"' in prompt
            assert '"owner", "nba_team"' in prompt
            return json.dumps(
                [
                    {
                        "entity": "player",
                        "attribute": "team",
                        "source_value": "LA Lakers",
                        "target_value": "Los Angeles Lakers",
                    },
                    {
                        "entity": "player",
                        "attribute": "team",
                        "source_value": "New York Liberty",
                        "target_value": "New York Knicks",
                    },
                    {
                        "entity": "player",
                        "attribute": "team",
                        "source_value": "Boston Celtics",
                        "target_value": "Invented Celtics",
                    },
                ]
            )

    contract = WorkloadContract(
        entities=(
            EntityContract("player"),
            EntityContract("team"),
            EntityContract("owner"),
        ),
        attributes=(
            AttributeContract("player", "team"),
            AttributeContract("team", "team_name"),
            AttributeContract("owner", "nba_team"),
            AttributeContract("owner", "name"),
        ),
        relationships=(
            RelationshipContract(
                "team=team_name",
                "player",
                "team",
                left_attributes=("team",),
                right_attributes=("team_name",),
            ),
            RelationshipContract(
                "team_name=nba_team",
                "team",
                "owner",
                left_attributes=("team_name",),
                right_attributes=("nba_team",),
            ),
        ),
    )
    values = {
        ("player", "team"): (
            "LA Lakers",
            "Boston Celtics",
            "New York Liberty",
        ),
        ("team", "team_name"): (
            "Los Angeles Lakers",
            "Boston Celtics",
            "New York Knicks",
        ),
        ("owner", "nba_team"): (
            "Los Angeles Lakers",
            "Boston Celtics",
        ),
        # This is deliberately not a declared join endpoint.
        ("owner", "name"): ("Lakers Ownership Group",),
    }
    records = tuple(
        ExtractionRecord(
            entity,
            attribute,
            f"{entity}-{index}",
            value,
            value,
            None,
            "player/1.txt",
            "u1",
            index,
            index + len(value),
        )
        for (entity, attribute), observed in values.items()
        for index, value in enumerate(observed)
    )
    document = type(
        "Document",
        (),
        {
            "document_id": "player/1.txt",
            "text": " ".join(
                value
                for observed in values.values()
                for value in observed
            ),
            "metadata": {},
        },
    )()

    with EvidenceStore(tmp_path / "join-er.sqlite") as evidence:
        extractor = ContractExtractor(
            (document,),
            JoinEntityClient(),
            evidence,
            max_workers=1,
        )
        mappings = extractor._join_key_mappings(contract, records)

    assert {
        (
            mapping.entity,
            mapping.attribute,
            mapping.source_value,
            mapping.target_value,
            mapping.mapping_kind,
        )
        for mapping in mappings
    } == {
        (
            "player",
            "team",
            "LA Lakers",
            "Los Angeles Lakers",
            "entity",
        )
    }
    assert "Lakers Ownership Group" in {
        record.value for record in records
    }


def test_entity_derivation_changes_semantic_join_key_but_not_raw_table():
    mapping = DerivationMapping(
        entity="player",
        attribute="team",
        source_value="LA Lakers",
        target_value="Los Angeles Lakers",
        mapping_kind="entity",
        supporting_document_ids=("player/1.txt", "team/1.txt"),
    )
    raw_tables = {
        "player": ({"row_id": "p1", "team": "LA Lakers"},),
        "team": (
            {
                "row_id": "t1",
                "team_name": "Los Angeles Lakers",
            },
        ),
    }
    backend = ContractBackend(
        (ContractDocument("player/1.txt", "LA Lakers"),),
        object(),
    )
    backend.relation_graph = WorkloadRelationGraph(
        relations=(
            RelationSpec(
                "player",
                ("team",),
                semantic_types=(("team", "text"),),
            ),
            RelationSpec(
                "team",
                ("team_name",),
                semantic_types=(("team_name", "text"),),
            ),
        ),
        edges=(
            RelationEdge(
                "player",
                "team",
                "team",
                "team_name",
            ),
        ),
        covered_query_ids=("q0",),
    )
    backend._shared = SharedExtraction(
        raw_tables=raw_tables,
        evidence=(),
        metadata={"derivation_mappings": (mapping.to_payload(),)},
    )

    semantic = backend._derived_semantic_tables(raw_tables)

    assert raw_tables["player"][0]["team"] == "LA Lakers"
    assert semantic["player"][0]["team"] == "Los Angeles Lakers"
    assert semantic["team"][0]["team_name"] == "Los Angeles Lakers"


def test_partial_llm_taxonomy_preserves_supported_mappings(tmp_path):
    class PartialTaxonomyClient:
        model = "fixture"

        def __init__(self):
            self.ledger = type("Ledger", (), {"actual_spent": 0})()

        def generate(self, *_args, **_kwargs):
            return json.dumps(
                [{"source_value": "A", "target_value": "Broad"}]
            )

    document = type(
        "Document",
        (),
        {
            "document_id": "item/1.txt",
            "text": "\nItem\n\nA B",
            "metadata": {},
        },
    )()
    attribute = AttributeContract(
        "item",
        "category",
        semantic_types=("text",),
        contexts=(("q0", ("group_by",)),),
        query_hints=(("q0", "Group each item by category."),),
    )
    contract = WorkloadContract(
        entities=(EntityContract("item"),),
        attributes=(attribute,),
        relationships=(),
    )
    records = tuple(
        ExtractionRecord(
            "item",
            "category",
            "Item",
            value,
            value,
            None,
            "item/1.txt",
            "u1",
            index,
            index + 1,
        )
        for index, value in enumerate(("A", "B"))
    )
    with EvidenceStore(tmp_path / "partial-taxonomy.sqlite") as evidence:
        extractor = ContractExtractor(
            (document,),
            PartialTaxonomyClient(),
            evidence,
            max_workers=1,
        )
        mappings = extractor._taxonomy_mappings(contract, records)
    assert {
        (mapping.source_value, mapping.target_value)
        for mapping in mappings
    } == {("A", "Broad")}


def test_partial_llm_taxonomy_is_completed_by_targeted_retry(tmp_path):
    class RepairingTaxonomyClient:
        model = "fixture"

        def __init__(self):
            self.ledger = type("Ledger", (), {"actual_spent": 0})()

        def generate(self, prompt, **_kwargs):
            if "Complete an otherwise valid categorical mapping" in prompt:
                return json.dumps(
                    [{"source_value": "B", "target_value": "Broad"}]
                )
            return json.dumps(
                [{"source_value": "A", "target_value": "Broad"}]
            )

    document = type(
        "Document",
        (),
        {
            "document_id": "item/1.txt",
            "text": "\nItem\n\nA B",
            "metadata": {},
        },
    )()
    attribute = AttributeContract(
        "item",
        "category",
        semantic_types=("text",),
        contexts=(("q0", ("group_by",)),),
        query_hints=(("q0", "Group each item by category."),),
    )
    contract = WorkloadContract(
        entities=(EntityContract("item"),),
        attributes=(attribute,),
        relationships=(),
    )
    records = tuple(
        ExtractionRecord(
            "item",
            "category",
            "Item",
            value,
            value,
            None,
            "item/1.txt",
            "u1",
            index,
            index + 1,
        )
        for index, value in enumerate(("A", "B"))
    )
    with EvidenceStore(tmp_path / "repaired-taxonomy.sqlite") as evidence:
        extractor = ContractExtractor(
            (document,),
            RepairingTaxonomyClient(),
            evidence,
            max_workers=1,
        )
        mappings = extractor._taxonomy_mappings(contract, records)
    assert {
        (mapping.source_value, mapping.target_value)
        for mapping in mappings
    } == {("A", "Broad"), ("B", "Broad")}


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


def test_content_heading_provides_source_grounded_entity_identity(tmp_path):
    class NoLLM:
        def generate(self, *_args, **_kwargs):
            raise AssertionError("content heading should avoid an LLM call")

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


def test_model_requested_calculation_uses_allowlisted_tools(tmp_path):
    class CalculationClient:
        model = "fixture"

        def __init__(self):
            self.ledger = type("Ledger", (), {"actual_spent": 0})()

        def generate(self, prompt, **_kwargs):
            if "Decide whether any missing numeric attribute" not in prompt:
                return "[]"
            return json.dumps(
                [
                    {
                        "identity": "Example Person",
                        "attribute": "age",
                        "tool": "calculator",
                        "operation": "subtract",
                        "operands": [2026, 2000],
                        "source_operands": [2000],
                        "exact_span": (
                            "Example Person (born January 2, 2000) "
                            "is documented here."
                        ),
                        "unit": "years",
                    }
                ]
            )

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
            CalculationClient(),
            evidence,
            max_workers=1,
        )
        extraction = extractor.extract(contract)
    assert extractor.reference_year == 2026
    assert len(extraction.attribute_records) == 1
    age = extraction.attribute_records[0]
    assert age.value == 26
    assert age.derivation_kind == "tool_calculation"
    assert validate_extraction(
        extraction,
        contract,
        {"person/1.txt": document.text},
    ) == ()


def test_calculation_tool_rejects_unprovenanced_operands():
    assert not operands_are_grounded(
        [20, 5],
        [5],
        "The source explicitly states 5.",
        corpus_reference_year=2026,
    )
    assert operands_are_grounded(
        [2026, 5],
        [5],
        "The source explicitly states 5.",
        corpus_reference_year=2026,
    )


def test_budget_aware_verifier_uses_llm_and_preserves_low_confidence():
    class VerificationClient:
        model = "fixture"

        def generate(self, _prompt, **_kwargs):
            return json.dumps(
                [
                    {
                        "claim_id": "accepted",
                        "status": "entailed",
                        "confidence": 0.95,
                        "reason": "direct support",
                    },
                    {
                        "claim_id": "uncertain",
                        "status": "entailed",
                        "confidence": 0.40,
                        "reason": "weak support",
                    },
                ]
            )

    verifier = BudgetAwareCellVerifier(
        VerificationClient(),
        GlobalBudgetLedger(100_000),
        completion_reserve=0,
        batch_size=2,
        nli_local_only=True,
    )
    claims = (
        CellClaim(
            "accepted",
            "item",
            "r1",
            "Item",
            "amount",
            5,
            ("integer",),
            (),
            "Item has amount 5.",
        ),
        CellClaim(
            "uncertain",
            "item",
            "r1",
            "Item",
            "count",
            2023,
            ("integer",),
            (),
            "Item received an award in 2023.",
        ),
    )
    report = verifier.verify(claims)
    decisions = {decision.claim_id: decision for decision in report.decisions}
    assert decisions["accepted"].status == "entailed"
    assert decisions["uncertain"].status == "abstain"
    assert report.llm_claims == 2


def test_cell_claim_exposes_checked_derivation_lineage_to_verifiers():
    claim = CellClaim(
        "derived",
        "person",
        "r1",
        "Example Person",
        "elapsed",
        26,
        ("integer",),
        (),
        "Example Person began in 2000.",
        derivation_lineage={
            "kind": "tool_calculation",
            "inputs": {
                "operation": "subtract",
                "operands": [2026, 2000],
            },
        },
    )
    assert "tool_calculation" in claim.nli_premise
    assert "not a nearby date" in claim.hypothesis
    assert claim.prompt_payload()["derivation_lineage"]["kind"] == (
        "tool_calculation"
    )


def test_quarantine_requires_a_confident_negative_decision():
    assert VerificationDecision(
        "bad", "contradicted", 0.95, "fixture"
    ).should_quarantine()
    assert not VerificationDecision(
        "uncertain", "abstain", 0.99, "fixture"
    ).should_quarantine()
    assert not VerificationDecision(
        "weak", "unsupported", 0.50, "fixture"
    ).should_quarantine()


def test_budget_aware_verifier_falls_back_to_nli_without_llm_budget():
    class NoCallClient:
        model = "fixture"

        def generate(self, *_args, **_kwargs):
            raise AssertionError("LLM must not run without budget")

    class Config:
        id2label = {
            0: "contradiction",
            1: "entailment",
            2: "neutral",
        }

    class Model:
        config = Config()

    class FakeNLI:
        model = Model()

        def predict(self, pairs, **_kwargs):
            assert len(pairs) == 2
            return (
                (8.0, 0.0, 0.0),
                (0.0, 8.0, 0.0),
            )

    verifier = BudgetAwareCellVerifier(
        NoCallClient(),
        GlobalBudgetLedger(100_000),
        completion_reserve=0,
        llm_token_budget=0,
    )
    verifier._nli = FakeNLI()
    claims = tuple(
        CellClaim(
            claim_id,
            "item",
            "r1",
            "Item",
            "amount",
            value,
            ("integer",),
            (),
            f"Item has amount {value}.",
        )
        for claim_id, value in (("bad", 9), ("good", 5))
    )
    report = verifier.verify(claims)
    decisions = {decision.claim_id: decision for decision in report.decisions}
    assert decisions["bad"].status == "contradicted"
    assert decisions["good"].status == "entailed"
    assert report.llm_claims == 0
    assert report.nli_claims == 2


def test_backend_quarantines_only_verifier_rejections():
    class SelectiveVerifier:
        seen_attributes = ()

        def __init__(self, _client, _ledger):
            pass

        def verify(self, claims):
            type(self).seen_attributes = tuple(
                claim.attribute for claim in claims
            )
            return VerificationReport(
                decisions=tuple(
                    VerificationDecision(
                        claim.claim_id,
                        (
                            "unsupported"
                            if claim.attribute == "awards"
                            else "abstain"
                        ),
                        0.99,
                        "fixture",
                    )
                    for claim in claims
                ),
                llm_claims=len(claims),
                nli_claims=0,
                unverified_claims=0,
            )

    relation = RelationSpec(
        "item",
        ("name", "category", "awards", "amount"),
        primary_key="name",
        semantic_types=(
            ("name", "text"),
            ("category", "text"),
            ("awards", "integer"),
            ("amount", "integer"),
        ),
    )
    backend = ContractBackend(
        (ContractDocument("item/1.txt", "Item has amount 5 in 2023."),),
        object(),
        verify_extracted_cells=True,
        cell_verifier_factory=SelectiveVerifier,
    )
    backend.contract = WorkloadContract(
        entities=(EntityContract("item"),),
        attributes=(
            AttributeContract(
                "item", "awards", semantic_types=("integer",)
            ),
            AttributeContract(
                "item", "category", semantic_types=("text",)
            ),
            AttributeContract(
                "item", "amount", semantic_types=("integer",)
            ),
        ),
        relationships=(),
    )
    backend.relation_graph = WorkloadRelationGraph(
        relations=(relation,),
        edges=(),
        covered_query_ids=("q0",),
    )
    shared = SharedExtraction(
        raw_tables={
            "item": (
                {
                    "row_id": "r1",
                    "name": "Item",
                    "category": "Example",
                    "awards": 2023,
                    "amount": 5,
                },
            )
        },
        evidence=(
            SharedCellEvidence(
                "item",
                "r1",
                "category",
                "Example",
                "a0",
                "item/1.txt",
                "Item",
                0,
                4,
                True,
                True,
            ),
            SharedCellEvidence(
                "item",
                "r1",
                "awards",
                2023,
                "a1",
                "item/1.txt",
                "2023",
                21,
                25,
                True,
                True,
            ),
            SharedCellEvidence(
                "item",
                "r1",
                "amount",
                5,
                "a2",
                "item/1.txt",
                "5",
                16,
                17,
                True,
                True,
            ),
        ),
    )
    verified = backend._verify_shared_values(
        shared, GlobalBudgetLedger(10_000)
    )
    assert verified.raw_tables["item"] == (
        {
            "row_id": "r1",
            "name": "Item",
            "category": "Example",
            "awards": 2023,
            "amount": 5,
        },
    )
    assert {
        cell.column for cell in verified.evidence
    } == {"category", "awards", "amount"}
    backend._shared = verified
    semantic = backend._derived_semantic_tables(verified.raw_tables)
    assert "awards" not in semantic["item"][0]
    assert semantic["item"][0]["amount"] == 5
    assert set(SelectiveVerifier.seen_attributes) == {"awards", "amount"}
    verification = verified.metadata["cell_verification"]
    assert verification["policy_version"] == 5
    assert verification["rejected_or_quarantined_count"] == 1
    assert verification["skipped_low_risk_count"] == 1
    assert verification["preserved_uncertain_count"] == 1


def test_verification_summary_does_not_change_shared_cache_key():
    backend = ContractBackend(
        (ContractDocument("item/1.txt", "Item has amount 5."),),
        object(),
        verify_extracted_cells=True,
    )
    backend.contract = WorkloadContract(
        entities=(EntityContract("item"),),
        attributes=(
            AttributeContract(
                "item", "amount", semantic_types=("integer",)
            ),
        ),
        relationships=(),
    )
    backend.relation_graph = WorkloadRelationGraph(
        relations=(
            RelationSpec(
                "item",
                ("amount",),
                semantic_types=(("amount", "integer"),),
            ),
        ),
        edges=(),
        covered_query_ids=("q0",),
    )
    before = backend._shared_key()
    backend._shared = SharedExtraction(
        raw_tables={"item": ()},
        evidence=(),
        metadata={
            "cell_verification": {
                "verifier_version": 2,
                "accepted_count": 10,
            }
        },
    )
    assert backend._shared_key() == before


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


def test_bulk_heading_fallback_never_overwrites_nonidentity_location(
    tmp_path,
):
    class FakeBulkExtractor:
        def extract_batch(
            self,
            _texts,
            document_ids,
            _relation,
            _schema,
            _keys,
            **_kwargs,
        ):
            return [
                type(
                    "Result",
                    (),
                    {
                        "chunk_id": document_id,
                        "records": (
                            {
                                "name": "Model Name",
                                "location": "Actual Place",
                            },
                        ),
                        "spans": (),
                        "error": None,
                    },
                )()
                for document_id in document_ids
            ]

    backend = ContractBackend(
        (
            ContractDocument(
                "group/1.txt",
                "\nHeading Name\n\nThe group is based in Actual Place.",
            ),
        ),
        type("Client", (), {})(),
        scratch_dir=tmp_path,
        use_bulk_extraction=True,
        bulk_extractor_factory=lambda _client, _cache: FakeBulkExtractor(),
        verify_extracted_cells=False,
    )
    backend.contract = WorkloadContract(
        entities=(EntityContract("group"),),
        attributes=(
            AttributeContract("group", "name"),
            AttributeContract("group", "location"),
        ),
        relationships=(),
    )
    backend.relation_graph = WorkloadRelationGraph(
        relations=(
            RelationSpec(
                "group",
                ("name", "location"),
                primary_key="name",
            ),
        ),
        edges=(),
        covered_query_ids=("q0",),
    )
    shared = backend._bulk_extract_shared(GlobalBudgetLedger(10_000))
    assert shared.raw_tables["group"][0]["name"] == "Heading Name"
    assert shared.raw_tables["group"][0]["location"] == "Actual Place"


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


def test_aggregate_additivity_rejects_non_numeric_group_without_crashing(
    tmp_path: Path,
):
    category = AttributeRef("record", "category", "text")
    amount = AttributeRef("record", "amount", "real")
    requirement = QueryRequirement(
        query_id="q0",
        text="Minimum amount for each category.",
        entities=("record",),
        plan=QueryPlan(
            projections=(category,),
            group_by=(category,),
            aggregates=(
                AggregateSpec("min", amount, alias="min_amount"),
            ),
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
        tmp_path / "mixed-aggregate.sqlite",
        {
            "record": [
                {"category": "A", "amount": 1},
                {"category": "B", "amount": "Second-Round"},
            ]
        },
        schema,
    )

    assessment = assess_query_quality(
        requirement,
        config,
        database,
        None,
    )

    assert assessment.error is None
    assert assessment.estimate.components["aggregate_additivity"] == 0.0


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
    backend.contract = compile_workload_contract(_intent(requirement))
    shared = SharedExtraction(
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
    backend._shared = shared
    refined = backend.refine_intent(_intent(requirement))
    join = refined.requirements[0].plan.joins[0]
    assert (join.left.attribute, join.right.attribute) == (
        "name",
        "team_name",
    )
    assert join.left.semantic_type == "text"
    assert join.right.semantic_type == "text"
    assert backend.generate_configs(refined)
    assert backend._shared is shared
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


def test_contract_backend_never_uses_analytical_measures_as_join_keys(
    tmp_path,
):
    team_name = AttributeRef("team", "name")
    team_measure = AttributeRef("team", "championships", "integer")
    player_team = AttributeRef("player", "team_name")
    player_measure = AttributeRef(
        "player", "championships_won", "integer"
    )
    requirements = (
        QueryRequirement(
            "q0",
            "Average championships won by players for each team.",
            entities=("team", "player"),
            plan=QueryPlan(
                group_by=(team_name,),
                aggregates=(AggregateSpec("avg", player_measure),),
                joins=(JoinSpec(team_measure, player_measure),),
            ),
        ),
        QueryRequirement(
            "q1",
            "Total championships for each team.",
            entities=("team",),
            plan=QueryPlan(
                group_by=(team_name,),
                aggregates=(AggregateSpec("sum", team_measure),),
            ),
        ),
    )
    backend = ContractBackend(
        (ContractDocument("opaque", "Example"),),
        object(),
        scratch_dir=tmp_path,
    )
    backend.relation_graph = WorkloadRelationGraph(
        relations=(
            RelationSpec(
                "team",
                ("name", "championships"),
                semantic_types=(
                    ("name", "text"),
                    ("championships", "integer"),
                ),
            ),
            RelationSpec(
                "player",
                ("team_name", "championships_won"),
                semantic_types=(
                    ("team_name", "text"),
                    ("championships_won", "integer"),
                ),
            ),
        ),
        edges=(
            RelationEdge(
                "team",
                "championships",
                "player",
                "championships_won",
            ),
        ),
        covered_query_ids=("q0", "q1"),
    )
    backend._shared = SharedExtraction(
        raw_tables={
            "team": (
                {"name": "A", "championships": 1},
                {"name": "B", "championships": 2},
            ),
            "player": (
                {"team_name": "A", "championships_won": 1},
                {"team_name": "B", "championships_won": 2},
            ),
        },
        evidence=(),
    )

    refined = backend.refine_intent(_intent(*requirements))

    join = refined.requirements[0].plan.joins[0]
    assert (join.left.attribute, join.right.attribute) == (
        "name",
        "team_name",
    )


def test_contract_backend_physically_binds_inflectional_plan_entities(
    tmp_path,
):
    category = AttributeRef("record", "category")
    amount = AttributeRef("records", "amount", "real")
    requirement = QueryRequirement(
        "q0",
        "Average amount by record category.",
        entities=("record", "records"),
        attribute_bindings=(
            ("record", "category"),
            ("records", "amount"),
        ),
        operators=("avg", "group_by"),
        plan=QueryPlan(
            group_by=(category,),
            aggregates=(AggregateSpec("avg", amount, "avg_amount"),),
        ),
    )
    backend = ContractBackend(
        (ContractDocument("opaque", "Example"),),
        object(),
        scratch_dir=tmp_path,
    )
    backend.relation_graph = WorkloadRelationGraph(
        relations=(
            RelationSpec(
                "record",
                ("category", "amount"),
                semantic_types=(("amount", "real"),),
            ),
        ),
        edges=(),
        covered_query_ids=("q0",),
    )
    backend._shared = SharedExtraction(
        raw_tables={"record": ({"category": "A", "amount": 10},)},
        evidence=(),
    )

    refined = backend.refine_intent(_intent(requirement))

    bound = refined.requirements[0]
    assert bound.entities == ("record",)
    assert set(bound.attribute_bindings) == {
        ("record", "category"),
        ("record", "amount"),
    }
    assert {
        reference.entity for reference in bound.plan.attributes()
    } == {"record"}
    probe = SynthesisConfig(
        backend.relation_graph.schema,
        PopulationConfig(),
        PreprocessingPolicy("whole_document"),
    )
    assert compile_query_plan(bound.plan, probe) is not None


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


def test_contract_backend_bulk_extraction_preserves_coherent_rows(tmp_path):
    class BulkExtractor:
        def extract_batch(
            self,
            texts,
            document_ids,
            _table,
            schema,
            *_args,
            **_kwargs,
        ):
            results = []
            for text, document_id in zip(texts, document_ids):
                name = text.splitlines()[1]
                age = 40 if name.startswith("Alpha") else 50
                record = {
                    column: (
                        name if column == "name" else age
                    )
                    for column in schema
                }
                spans = {
                    "name": name,
                    "age": str(age),
                }
                results.append(
                    type(
                        "Result",
                        (),
                        {
                            "chunk_id": document_id,
                            "records": [record],
                            "spans": [spans],
                            "error": None,
                        },
                    )()
                )
            return results

    documents = tuple(
        ContractDocument(
            f"person/{index}.txt",
            f"\n{name} Person\n\n{name} Person is age {age}.",
        )
        for index, (name, age) in enumerate(
            (("Alpha", 40), ("Beta", 50)),
            start=1,
        )
    )
    name = AttributeRef("person", "name", "text")
    age = AttributeRef("person", "age", "real")
    intent = _intent(
        QueryRequirement(
            "q0",
            "Average age for each person.",
            entities=("person",),
            attribute_bindings=(
                ("person", "name"),
                ("person", "age"),
            ),
            plan=QueryPlan(
                group_by=(name,),
                aggregates=(AggregateSpec("avg", age),),
            ),
        )
    )
    backend = ContractBackend(
        documents,
        type("Client", (), {})(),
        scratch_dir=tmp_path,
        use_bulk_extraction=True,
        bulk_extractor_factory=lambda _client, _cache: BulkExtractor(),
    )
    backend._ensure_contract(intent)
    shared = backend._bulk_extract_shared(GlobalBudgetLedger(100_000))
    rows = shared.raw_tables["person"]
    assert len(rows) == 2
    assert {
        (row["name"], row["age"]) for row in rows
    } == {
        ("Alpha Person", 40),
        ("Beta Person", 50),
    }
    assert all(cell.supported for cell in shared.evidence)


def test_bulk_values_participate_in_contract_taxonomy_induction(tmp_path):
    class MappingExtractor:
        def derive_mappings(self, _contract, records):
            assert {record.value for record in records} == {"Detailed"}
            return (
                DerivationMapping(
                    entity="item",
                    attribute="category",
                    source_value="Detailed",
                    target_value="Broad",
                    mapping_kind="taxonomy",
                    supporting_document_ids=("item/1.txt",),
                ),
            )

    backend = ContractBackend(
        (ContractDocument("item/1.txt", "Detailed"),),
        type("Client", (), {})(),
        scratch_dir=tmp_path,
    )
    backend.contract = WorkloadContract(
        entities=(EntityContract("item"),),
        attributes=(
            AttributeContract(
                "item", "category", semantic_types=("text",)
            ),
        ),
        relationships=(),
    )
    bulk = SharedExtraction(
        raw_tables={
            "item": (
                {"row_id": "row-1", "category": "Detailed"},
            )
        },
        evidence=(
            SharedCellEvidence(
                relation="item",
                row_identity="row-1",
                column="category",
                value="Detailed",
                anchor_id="anchor",
                document_id="item/1.txt",
                anchor_text="Detailed",
                start=0,
                end=8,
                entailed=True,
                span_restored=True,
            ),
        ),
    )
    result = backend._add_bulk_derivation_mappings(
        MappingExtractor(),
        ContractExtraction("contract", (), ()),
        bulk,
    )
    assert result.derivation_mappings[0].target_value == "Broad"


def test_supported_contract_cell_overrides_conflicting_bulk_value():
    primary = SharedExtraction(
        raw_tables={"entity": ({"row_id": "r1", "name": "Wrong"},)},
        evidence=(),
    )
    secondary = SharedExtraction(
        raw_tables={"entity": ({"row_id": "r1", "name": "Canonical"},)},
        evidence=(
            SharedCellEvidence(
                relation="entity",
                row_identity="r1",
                column="name",
                value="Canonical",
                anchor_id="a1",
                document_id="entity/1.txt",
                anchor_text="Canonical",
                start=0,
                end=9,
                entailed=True,
                span_restored=True,
            ),
        ),
    )
    merged = _merge_shared_extractions(primary, secondary)
    assert merged.raw_tables["entity"][0]["name"] == "Canonical"


def test_bulk_scalar_gate_enforces_declared_types_without_semantic_ranges():
    relation = RelationSpec(
        "entity",
        ("awards", "titles", "age", "active"),
        semantic_types=(
            ("awards", "integer"),
            ("titles", "text"),
            ("age", "real"),
            ("active", "boolean"),
        ),
    )
    assert ContractBackend._bulk_value_plausible(relation, "awards", 2023)
    assert ContractBackend._bulk_value_plausible(relation, "titles", 2023)
    assert ContractBackend._bulk_value_plausible(relation, "awards", 18)
    assert ContractBackend._bulk_value_plausible(
        relation, "awards", (1 << 63) - 1
    )
    assert ContractBackend._bulk_value_plausible(
        relation, "awards", -(1 << 63)
    )
    assert not ContractBackend._bulk_value_plausible(
        relation, "awards", 1 << 63
    )
    assert not ContractBackend._bulk_value_plausible(
        relation, "awards", str(1 << 80)
    )
    assert ContractBackend._bulk_value_plausible(relation, "age", 136)
    assert ContractBackend._bulk_value_plausible(relation, "age", 86)
    assert not ContractBackend._bulk_value_plausible(
        relation, "titles", "null"
    )
    assert not ContractBackend._bulk_value_plausible(
        relation, "awards", "event description"
    )
    assert not ContractBackend._bulk_value_plausible(
        relation, "active", "organization name"
    )
    assert ContractBackend._bulk_value_plausible(
        relation, "active", "true"
    )
    assert not ContractBackend._bulk_value_plausible(
        relation, "age", float("inf")
    )
    assert not ContractBackend._bulk_value_plausible(
        relation, "awards", True
    )
    assert not ContractBackend._bulk_value_plausible(
        relation, "titles", ["not", "a", "scalar"]
    )


def test_bulk_count_type_comes_from_workload_role_not_column_name():
    backend = ContractBackend(
        (ContractDocument("record/1.txt", "Example"),),
        object(),
    )
    backend.contract = WorkloadContract(
        entities=(EntityContract("record"),),
        attributes=(
            AttributeContract(
                "record",
                "metric",
                semantic_types=("integer",),
                contexts=(("q0", ("aggregate:sum",)),),
                query_hints=(
                    ("q0", "What is the total number of metrics?"),
                ),
            ),
            AttributeContract(
                "record",
                "period",
                semantic_types=("integer",),
                contexts=(("q1", ("group_by",)),),
                query_hints=(
                    ("q1", "How many records occurred in each period?"),
                ),
            ),
        ),
        relationships=(),
    )
    relation = RelationSpec(
        "record",
        ("metric", "period"),
        semantic_types=(
            ("metric", "integer"),
            ("period", "integer"),
        ),
    )
    assert backend._bulk_semantic_type(relation, "metric") == (
        "QUANTITY_COUNT"
    )
    assert backend._bulk_semantic_type(relation, "period") == "QUANTITY"
    assert backend._bulk_coverage_floor(relation, "metric") == 0.10
    assert backend._bulk_coverage_floor(relation, "period") == 0.75


def test_post_merge_scalar_gate_preserves_raw_and_filters_projection():
    relation = RelationSpec(
        "entity",
        ("name", "awards", "age"),
        semantic_types=(
            ("name", "text"),
            ("awards", "integer"),
            ("age", "real"),
        ),
    )
    backend = ContractBackend(
        (ContractDocument("entity/1.txt", "Example"),),
        object(),
    )
    backend.relation_graph = WorkloadRelationGraph(
        pattern="snowflake",
        relations=(relation,),
        edges=(),
        covered_query_ids=("q0",),
    )
    shared = SharedExtraction(
        raw_tables={
            "entity": (
                {
                    "row_id": "r1",
                    "name": "Example",
                    "awards": float("inf"),
                    "age": 681,
                },
            )
        },
        evidence=(
            SharedCellEvidence(
                relation="entity",
                row_identity="r1",
                column="awards",
                value=float("inf"),
                anchor_id="a",
                document_id="entity/1.txt",
                anchor_text="2023",
                start=0,
                end=4,
                entailed=True,
                span_restored=True,
            ),
        ),
    )
    cleaned = backend._sanitize_shared_values(shared)
    assert cleaned.raw_tables["entity"] == (
        {
            "row_id": "r1",
            "name": "Example",
            "awards": float("inf"),
            "age": 681,
        },
    )
    assert cleaned.evidence == shared.evidence
    projected = backend._materializable_raw_tables(cleaned.raw_tables)
    assert projected["entity"] == [
        {"row_id": "r1", "name": "Example", "age": 681}
    ]
    assert cleaned.metadata["plausibility_rejected_cell_count"] == 1


def test_semantic_mapping_applies_to_same_unsupported_surface():
    relation = RelationSpec(
        "person",
        ("role",),
        semantic_types=(("role", "text"),),
    )
    backend = ContractBackend(
        (ContractDocument("person/1.txt", "Guard"),),
        object(),
    )
    backend.relation_graph = WorkloadRelationGraph(
        pattern="snowflake",
        relations=(relation,),
        edges=(),
        covered_query_ids=("q0",),
    )
    backend._shared = SharedExtraction(
        raw_tables={
            "person": (
                {"row_id": "r1", "role": "Guard"},
                {"row_id": "r2", "role": "Guard"},
            )
        },
        evidence=(
            SharedCellEvidence(
                relation="person",
                row_identity="r1",
                column="role",
                value="Guard",
                anchor_id="a",
                document_id="person/1.txt",
                anchor_text="Guard",
                start=0,
                end=5,
                entailed=True,
                span_restored=True,
            ),
        ),
        metadata={
            "derivation_mappings": (
                {
                    "entity": "person",
                    "attribute": "role",
                    "source_value": "Guard",
                    "target_value": "Backcourt",
                    "mapping_kind": "taxonomy",
                },
            )
        },
    )
    semantic = backend._derived_semantic_tables(
        backend._shared.raw_tables
    )
    assert [row["role"] for row in semantic["person"]] == [
        "Backcourt",
        "Backcourt",
    ]


def test_optional_query_mapping_does_not_invalidate_raw_candidate():
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
    assert raw_result.validity == 1.0
    assert raw_result.components["contract_mapping_alignment"] == 0.0
    assert raw_result.components["contract_mapping_available"] == 1.0
    assert semantic_result.validity == 1.0
    assert semantic_result.components["contract_mapping_alignment"] == 1.0


def test_required_predicate_vocabulary_forces_semantic_candidate():
    position = AttributeRef("player", "position", "text")
    requirement = QueryRequirement(
        query_id="q0",
        text=(
            "SELECT position, COUNT(*) FROM player "
            "WHERE position IN ('Frontcourt', 'Backcourt') "
            "GROUP BY position"
        ),
        entities=("player",),
        attributes=("position",),
        attribute_bindings=(("player", "position"),),
        plan=QueryPlan(
            projections=(position,),
            group_by=(position,),
            aggregates=(AggregateSpec("count"),),
            predicate=PredicateSpec(
                kind="or",
                children=(
                    PredicateSpec(
                        attribute=position,
                        operator="=",
                        value="Frontcourt",
                    ),
                    PredicateSpec(
                        attribute=position,
                        operator="=",
                        value="Backcourt",
                    ),
                ),
            ),
        ),
    )
    intent = _intent(requirement)
    backend = ContractBackend(
        (ContractDocument("player/1.txt", "A point guard."),),
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
        raw_tables={
            "player": (
                {"row_id": "1", "position": "point guard"},
                {"row_id": "2", "position": "center"},
                {"row_id": "3", "position": "player"},
            )
        },
        evidence=(),
        metadata={
            "derivation_mappings": (
                {
                    "entity": "player",
                    "attribute": "position",
                    "source_value": "point guard",
                    "target_value": "Backcourt",
                    "mapping_kind": "taxonomy",
                },
                {
                    "entity": "player",
                    "attribute": "position",
                    "source_value": "center",
                    "target_value": "Frontcourt",
                    "mapping_kind": "taxonomy",
                },
            )
        },
    )
    semantic_tables = backend._derived_semantic_tables(
        backend._shared.raw_tables
    )
    assert [
        row.get("position") for row in semantic_tables["player"]
    ] == ["Backcourt", "Frontcourt", None]
    assert backend._semantic_changes_are_supported(semantic_tables)

    def assessment(config: SynthesisConfig) -> QueryAssessment:
        return QueryAssessment(
            QualityEstimate(
                "q0",
                config.config_id,
                1.0,
                1.0,
                1.0,
                0.0,
                3,
            ),
            None,
            None,
        )

    raw_estimate = backend._apply_mapping_contract(
        raw,
        {"q0": assessment(raw)},
        backend._shared.raw_tables,
    )["q0"].estimate
    semantic_estimate = backend._apply_mapping_contract(
        semantic,
        {"q0": assessment(semantic)},
        semantic_tables,
    )["q0"].estimate

    assert raw_estimate.validity == 0.0
    assert raw_estimate.components["contract_vocabulary_alignment"] == 0.0
    assert not raw_estimate.route_eligible
    assert semantic_estimate.validity == 1.0
    assert (
        semantic_estimate.components["contract_vocabulary_alignment"]
        == 1.0
    )
    assert semantic_estimate.route_eligible
    retained = backend._apply_candidate_retention_contract(
        semantic,
        semantic_tables,
        backend._shared.raw_tables,
        {
            "q0": QueryAssessment(
                semantic_estimate,
                None,
                None,
            )
        },
    )["q0"].estimate
    assert retained.validity == 1.0


def test_semantic_overlay_cannot_win_by_dropping_required_cells():
    category = AttributeRef("item", "category", "text")
    requirement = QueryRequirement(
        query_id="q0",
        text="Count records for each category.",
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
    semantic = next(
        config
        for config in backend.generate_configs(intent)
        if config.population.norm_strategy == "contract_mapping"
    )
    backend.intent = intent
    assessment = QueryAssessment(
        QualityEstimate(
            "q0",
            semantic.config_id,
            1.0,
            1.0,
            1.0,
            0.0,
            1,
        ),
        None,
        None,
    )
    adjusted = backend._apply_candidate_retention_contract(
        semantic,
        {"item": [{"row_id": "r1"}]},
        {"item": [{"row_id": "r1", "category": "Detailed"}]},
        {"q0": assessment},
    )["q0"].estimate
    assert adjusted.validity == 0.0
    assert adjusted.recall_proxy == 0.0
    assert adjusted.components["non_destructive_overlay"] == 0.0


def test_contract_modules_do_not_contain_benchmark_path_literals():
    root = Path(__file__).resolve().parent / "spp"
    forbidden = ("data/", ".csv", "evaluation.json")
    for name in (
        "workload_contract.py",
        "contract_extractor.py",
        "cell_verifier.py",
        "contract_validation.py",
        "contract_backend.py",
        "query_quality.py",
    ):
        source = (root / name).read_text(encoding="utf-8").lower()
        assert not any(value in source for value in forbidden)
