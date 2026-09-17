from __future__ import annotations

from quwarts.core.amplify import amp
from quwarts.core.domain import apply_evidence_types
from quwarts.core.logical import identity_name, infer_logical_schema
from quwarts.core.models import (
    AttributeRequirement,
    AttributeStats,
    EvidenceRecord,
    Role,
    Workload,
)
from quwarts.core.pilot import synthetic_stats
from quwarts.core.quality import route_count
from quwarts.core.repair.er import resolve_shared_ids
from quwarts.core.repair.models import RepairIssue
from quwarts.core.repair.rank import priority
from quwarts.core.schema import _pk_for
from quwarts.core.workload import analyze_workload


def test_attribute_names_do_not_set_type() -> None:
    logical = infer_logical_schema(["SELECT art.salary, art.birth_country, art.founded_date FROM art"])
    assert {item.dtype for item in logical.attributes} == {"unknown"}
    assert identity_name("art", ["salary", "birth_country"]) is None


def test_sum_declares_numeric_without_using_the_name() -> None:
    _, workload = analyze_workload(["SELECT SUM(art.awards) FROM art"])
    assert workload.requirements["art.awards"].dtype == "numeric"
    assert Role.AGG_ADDITIVE in workload.requirements["art.awards"].roles


def test_literals_still_type_columns() -> None:
    _, workload = analyze_workload(
        {
            "q1": "SELECT birth_country FROM art WHERE birth_country IN ('France', 'Germany')",
            "q2": "SELECT awards FROM art WHERE awards > 0",
        }
    )
    assert workload.requirements["art.birth_country"].dtype == "string"
    assert workload.requirements["art.awards"].dtype == "numeric"


def test_evidence_types_only_when_sql_left_unknown() -> None:
    _, workload = analyze_workload(["SELECT art.tone FROM art"])
    assert workload.requirements["art.tone"].dtype == "unknown"
    records = [
        EvidenceRecord(
            key="a",
            segment_id="s",
            doc_id="d1",
            attribute="art.tone",
            surface_value="warm",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        )
    ]
    apply_evidence_types(workload, records)
    assert workload.requirements["art.tone"].dtype == "string"


def test_unknown_type_is_not_discarded() -> None:
    from quwarts.core.extract import validate_cell

    surface, _parsed, reason = validate_cell("France", "unknown")
    assert surface == "France"
    assert reason == "type_unresolved"


def test_pk_is_not_inferred_from_column_names() -> None:
    logical = infer_logical_schema(
        [
            "SELECT city.area, city.city_name FROM city",
            "SELECT team.championship, team.team_name FROM team",
        ]
    )
    assert _pk_for("city", logical) == []
    assert _pk_for("team", logical) == []
    names = [item.name for item in logical.attributes if item.entity_type == "city"]
    assert identity_name("city", names) is None


def test_join_authority_is_empty() -> None:
    from quwarts.core.extract import join_authority

    _, workload = analyze_workload(
        ["SELECT t.team_name FROM player p JOIN team t ON p.team = t.team_name"]
    )
    assert join_authority(workload) == {}


def test_shared_er_assigns_one_id_across_join_attributes() -> None:
    _, workload = analyze_workload(
        ["SELECT t.team_name FROM player p JOIN team t ON p.team = t.team_name"]
    )
    records = [
        EvidenceRecord(
            key="a", segment_id="s", doc_id="d1", attribute="player.team",
            surface_value="Lakers", extractor_cfg_hash="h", quality_tier="cheap", stage=1,
        ),
        EvidenceRecord(
            key="b", segment_id="s", doc_id="d2", attribute="team.team_name",
            surface_value="lakers.", extractor_cfg_hash="h", quality_tier="cheap", stage=1,
        ),
    ]
    shared = resolve_shared_ids(records, workload)
    left = shared["maps"]["player.team"]["Lakers"]
    right = shared["maps"]["team.team_name"]["lakers."]
    assert left == right
    assert left.startswith("er:")
    surfaces = {row["surface"]: row["canonical_id"] for row in shared["table"]}
    assert surfaces["Lakers"] == surfaces["lakers."]


def test_ranker_uses_amp_not_key_over_projection() -> None:
    stats = synthetic_stats(n_rows=100, n_groups=4, n_distinct=20, rho=0.2, n_scored_columns=1)
    measure = AttributeRequirement(
        name="art.awards",
        entity_type="art",
        dtype="numeric",
        roles={Role.AGG_ADDITIVE},
        freq_weight=8.0,
        stats=AttributeStats(
            n_rows=100, n_groups=4, group_size=1.0, n_distinct=20,
            multiplicity=1.0, rho=0.2, n_scored_columns=1,
        ),
    )
    key = AttributeRequirement(
        name="art.id",
        entity_type="art",
        dtype="string",
        roles={Role.KEY},
        freq_weight=1.0,
        stats=stats,
    )
    workload = Workload(
        templates=[],
        requirements={"art.awards": measure, "art.id": key},
    )
    measure.amp = amp(measure)
    key.amp = amp(key)
    assert measure.amp > key.amp
    sum_issue = RepairIssue(
        kind="high_null",
        attributes=["art.awards"],
        query_ids=["q1"],
        severity=1.0,
    )
    key_issue = RepairIssue(
        kind="high_null",
        attributes=["art.id"],
        query_ids=["q1"],
        severity=1.0,
    )
    assert priority(sum_issue, workload, 100, 1) > priority(key_issue, workload, 100, 1)


def test_route_count_follows_amp() -> None:
    stats = synthetic_stats(n_rows=100, n_groups=10, n_distinct=20, rho=0.25, n_scored_columns=2)
    key = AttributeRequirement(
        name="e.id", entity_type="e", dtype="string",
        roles={Role.KEY}, freq_weight=1.0, stats=stats,
    )
    project = AttributeRequirement(
        name="e.p", entity_type="e", dtype="string",
        roles={Role.PROJECT}, freq_weight=1.0, stats=stats,
    )
    additive = AttributeRequirement(
        name="e.awards", entity_type="e", dtype="numeric",
        roles={Role.AGG_ADDITIVE}, freq_weight=1.0, stats=stats,
    )
    assert route_count(key) == 3
    assert route_count(project) == 1
    assert route_count(additive) >= 2


def test_mean_per_query_product_is_not_product_of_means() -> None:
    from quwarts.experiments.repair_art import mean_per_query_product

    report = {
        "mean_structure_f2": 0.5,
        "mean_cell_f1_20": 0.4,
        "per_query": [
            {"structure_f2": 1.0, "cell_f1_20": 0.0},
            {"structure_f2": 0.0, "cell_f1_20": 0.8},
        ],
    }
    assert mean_per_query_product(report) == 0.0


def test_repair_agent_keeps_routing(tmp_path) -> None:
    from quwarts.core.ledger import TokenLedger
    from quwarts.core.extract import EvidenceStore, StagedExtractor
    from quwarts.core.models import FrozenPortfolio, SourceDocument
    from quwarts.core.repair.agent import run_repair_agent

    logical, workload = analyze_workload(["SELECT art.tone FROM art"])
    store = EvidenceStore(tmp_path / "evidence")
    ledger = TokenLedger(theta=100, seed=0)
    extractor = StagedExtractor(store=store, ledger=ledger, caller=None, seed=0)
    documents = [SourceDocument(doc_id="d1", text="tone: warm")]
    portfolio = FrozenPortfolio(
        configurations=[],
        route={"t1": "cfg-a"},
        rewrites={},
        databases=[],
        tokens_spent=0,
        cache_hit_rate=0.0,
        seed=0,
        logical_schema=logical,
    )
    report = run_repair_agent(
        extractor, documents, workload, portfolio, {"q1": "SELECT art.tone FROM art"},
        logical=logical,
    )
    assert report.routing == {"t1": "cfg-a"}
    assert report.stopped == "below_min_repair_tokens"
