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


def test_sql_columns_are_kept_even_if_name_looks_like_a_coarsening() -> None:
    logical = infer_logical_schema(
        ["SELECT item.item_status FROM item WHERE item.item_status <> ''"]
    )
    names = {f"{item.entity_type}.{item.name}" for item in logical.attributes}
    assert "item.item_status" in names


def test_like_coverage_is_interval_not_literal_lookup() -> None:
    from quwarts.core.models import PredicateRange, SliceSpec

    spec = SliceSpec(
        kind="ranges",
        ranges=[PredicateRange(attribute="item.kind", op="LIKE", values=["%other%"])],
    )
    assert spec.contains_constants(["%wanted%"], op="LIKE")


def test_like_rewrite_only_when_table_has_derived_column() -> None:
    from quwarts.core.rewrite import apply_like_derived

    sql = "SELECT * FROM disease d WHERE LOWER(d.disease_type) LIKE '%x%' AND d.disease_type <> ''"
    rewritten = apply_like_derived(sql, {"disease": {"disease_type"}})
    assert "disease_type__like" in rewritten
    assert "d.disease_type <> ''" in rewritten or "d.disease_type <>" in rewritten
    skipped = apply_like_derived(sql, {"drug": {"disease_type"}})
    assert "disease_type__like" not in skipped


def test_like_case_is_measured_not_named() -> None:
    from quwarts.core.repair.like_vocab import measure_like_case

    assert measure_like_case(["token_a", "other"], ["token_a"]) == "a"
    assert measure_like_case(["unrelated prose"], ["token_a", "token_b"]) == "b"
    assert measure_like_case(["token_a, token_b"] * 4, ["token_a", "token_b"]) == "c"


def test_string_literal_and_like_force_text() -> None:
    _, workload = analyze_workload(
        {
            "q1": "SELECT d.disease_type FROM disease d WHERE d.disease_type <> ''",
            "q2": "SELECT LOWER(d.disease_type) FROM disease d WHERE LOWER(d.disease_type) LIKE '%infectious%'",
            "q3": (
                "SELECT SUM(CASE WHEN LOWER(dr.prescription_status) LIKE '%prescription_only%' "
                "THEN 1 ELSE 0 END) FROM drug dr WHERE dr.prescription_status <> ''"
            ),
        }
    )
    assert workload.requirements["disease.disease_type"].dtype == "string"
    assert workload.requirements["drug.prescription_status"].dtype == "string"
    assert workload.literal_types["prescription_status"] == "string"
    assert "prescription_only" in workload.like_tokens.get("drug.prescription_status", [])
    assert "prescription_only" in workload.like_tokens.get("prescription_status", [])


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


def test_empty_query_diagnosis_names_first_zero_stage(tmp_path) -> None:
    import sqlite3
    from quwarts.core.repair.diagnose import diagnose_empty_query

    path = tmp_path / "med.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE disease (disease_name TEXT)")
    conn.execute("CREATE TABLE drug (disease_name TEXT)")
    conn.executemany("INSERT INTO disease VALUES (?)", [("HIV",), ("Asthma",)])
    conn.executemany("INSERT INTO drug VALUES (?)", [("Flu",), ("COVID-19",)])
    conn.commit()
    conn.close()
    join_empty = diagnose_empty_query(
        "q_join",
        "SELECT d.disease_name FROM drug d JOIN disease t ON d.disease_name = t.disease_name",
        str(path),
    )
    assert join_empty.cause == "join"
    assert join_empty.first_zero_stage == "join:0"
    assert "repair_join_vocabulary" in join_empty.compatible_actions
    assert "HIV" not in join_empty.unmatched.get("left_unmatched", [])
    assert "Flu" in join_empty.unmatched.get("left_unmatched", [])

    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE art (awards TEXT, tone TEXT)")
    conn.execute("INSERT INTO art VALUES ('none', 'warm')")
    conn.commit()
    conn.close()
    filt = diagnose_empty_query(
        "q_filter",
        "SELECT tone FROM art WHERE awards = 'missing'",
        str(path),
    )
    assert filt.cause == "filter"
    assert filt.first_zero_stage == "filter:0"
    assert filt.predicate == "awards = 'missing'"

    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE disease ADD COLUMN disease_type TEXT")
    conn.execute("UPDATE disease SET disease_type = 'infectious' WHERE disease_name = 'HIV'")
    conn.commit()
    conn.close()
    cross = diagnose_empty_query(
        "q_cross",
        "SELECT d.disease_name FROM drug d JOIN disease t ON d.disease_name = t.disease_name "
        "WHERE t.disease_type <> ''",
        str(path),
    )
    assert cross.cause == "join"
    assert cross.first_zero_stage == "join:0"


def test_join_diagnosis_allows_only_er_repair() -> None:
    from quwarts.core.repair.actions import eligible_repairs, propose
    from quwarts.core.repair.models import RepairIssue

    issue = RepairIssue(
        kind="empty_query",
        attributes=["drug.disease_name", "disease.disease_name"],
        query_ids=["q_join"],
        severity=1.0,
        detail={
            "cause": "join",
            "compatible_actions": ["repair_join_vocabulary"],
            "unmatched": {"left_unmatched": ["Flu"], "right_values": ["HIV"]},
        },
    )
    actions = {item.action for item in propose(issue, None)}
    assert actions == {"repair_join_vocabulary"}
    assert eligible_repairs([issue], None, blocked={"repair_join_vocabulary"}) == []


def test_failed_action_is_not_repeated() -> None:
    from quwarts.core.repair.actions import eligible_repairs
    from quwarts.core.repair.models import RepairIssue

    issue = RepairIssue(
        kind="empty_query",
        attributes=["art.awards"],
        query_ids=["q1"],
        severity=1.0,
        detail={"cause": "filter", "compatible_actions": ["reextract_attribute_slice"]},
    )
    assert eligible_repairs([issue], None, blocked=set())
    assert eligible_repairs([issue], None, blocked={"reextract_attribute_slice"}) == []


def test_inspect_coercion_reads_evidence_before_reextract() -> None:
    from quwarts.core.extract import EvidenceStore
    from quwarts.core.repair.diagnose import inspect_coercion

    _, workload = analyze_workload(["SELECT awards FROM art WHERE awards > 0"])
    store = EvidenceStore()
    store.put(
        EvidenceRecord(
            key="a", segment_id="s", doc_id="d1", attribute="art.awards",
            surface_value="France", extractor_cfg_hash="h", quality_tier="cheap",
            stage=1, null_reason="dtype_coercion",
        )
    )
    store.put(
        EvidenceRecord(
            key="b", segment_id="s", doc_id="d2", attribute="art.awards",
            surface_value="12", extractor_cfg_hash="h", quality_tier="cheap",
            stage=1, null_reason="dtype_coercion",
        )
    )
    report = inspect_coercion(store, workload, ["art.awards"])
    skipped = {row["surface"] for row in report["skip"]}
    reparses = {row["surface"] for row in report["reparse"]}
    assert "France" in skipped
    assert "12" in reparses
    assert report["reextract"] == []


def test_filter_failure_diagnosis_picks_representation_not_extract() -> None:
    from quwarts.core.extract import EvidenceStore
    from quwarts.core.repair.diagnose import diagnose_filter_failure
    from quwarts.core.repair.represent import extract_unit_and_magnitude, mark_absence_as_null

    _, workload = analyze_workload(["SELECT awards FROM art WHERE awards > 0"])
    store = EvidenceStore()
    for key, surface in (("a", "250 mg"), ("b", "none reported"), ("c", "12-18")):
        store.put(
            EvidenceRecord(
                key=key, segment_id="s", doc_id=key, attribute="art.awards",
                surface_value=surface, extractor_cfg_hash="h", quality_tier="cheap",
                stage=1,
            )
        )
    report = diagnose_filter_failure(
        "art.awards", ["q1"], "awards > 0", [0], store, workload,
    )
    assert report.n_units >= 1
    assert report.n_ranges >= 1
    assert report.n_absence >= 1
    assert report.n_literal_hits == 0
    assert "reextract_attribute_slice" not in report.compatible_actions
    assert "extract_unit_and_magnitude" in report.compatible_actions
    assert extract_unit_and_magnitude(store, ["art.awards"])["n"] == 1
    assert store.records["a"].parsed_value == 250
    assert mark_absence_as_null(store, ["art.awards"])["n"] == 1
    assert store.records["b"].null_reason == "absence"


def test_numeric_category_without_bands_is_infeasible() -> None:
    from quwarts.core.extract import EvidenceStore
    from quwarts.core.repair.diagnose import diagnose_filter_failure

    _, workload = analyze_workload(["SELECT age FROM art WHERE age > 65"])
    store = EvidenceStore()
    store.put(
        EvidenceRecord(
            key="a", segment_id="s", doc_id="d1", attribute="art.age",
            surface_value="adult", extractor_cfg_hash="h", quality_tier="cheap",
            stage=1,
        )
    )
    report = diagnose_filter_failure(
        "art.age", ["q1"], "age > 65", [65], store, workload,
    )
    assert report.shape == "infeasible"
    assert report.compatible_actions == ("infeasible_representation",)
    assert report.samples == ["adult"]


def test_repair_cost_is_observed_spend_not_a_table() -> None:
    from quwarts.core.ledger import TokenLedger
    from quwarts.core.repair.actions import estimate_cost

    assert estimate_cost("extract_unit_and_magnitude", 12) == 0
    assert estimate_cost("infeasible_representation", 8) == 0
    assert estimate_cost("reextract_attribute_slice", 3) == 3

    ledger = TokenLedger(theta=10_000)
    ledger.spend(120, "extract", attribute="art.awards")
    ledger.spend(80, "extract", attribute="art.awards")
    assert estimate_cost("reextract_attribute_slice", 2, ledger, ["art.awards"]) == 200
    ledger.spend(50, "extract", attribute="art.tone")
    assert estimate_cost("reextract_attribute_slice", 1, ledger, ["art.awards"]) == 100


def test_like_vocab_survives_vote_replace() -> None:
    from quwarts.core.extract import carry_derived_keys, prefer_constrained_records

    primary = EvidenceRecord(
        key="p", segment_id="s", doc_id="d1", attribute="item.kind",
        surface_value="viral", extractor_cfg_hash="h", quality_tier="cheap",
        stage=1, candidate_keys={"route": "primary", "like_vocab": "viral|bacterial"},
    )
    voted = EvidenceRecord(
        key="v", segment_id="s", doc_id="d1", attribute="item.kind",
        surface_value="viral", extractor_cfg_hash="voted", quality_tier="expensive",
        stage=3, candidate_keys={"route": "voted", "grounded": "1"},
    )
    kept = prefer_constrained_records([primary, voted])
    assert len(kept) == 1
    assert (kept[0].candidate_keys or {}).get("like_vocab") in (None, "")
    carried = carry_derived_keys(kept, [primary, voted])
    assert carried[0].candidate_keys.get("like_vocab") == "viral|bacterial"


def test_high_amp_cells_exclude_join() -> None:
    from quwarts.core.quality import high_amp_cell_attributes

    _, workload = analyze_workload(
        {
            "q1": "SELECT SUM(item.amount), item.kind FROM item GROUP BY item.kind",
            "q2": "SELECT COUNT(DISTINCT item.kind) FROM item",
            "q3": "SELECT item.amount FROM item JOIN other ON item.name = other.name",
        }
    )
    names = high_amp_cell_attributes(workload)
    assert "item.amount" in names
    assert "item.kind" in names
    assert "other.name" not in names or Role.JOIN in workload.requirements["other.name"].roles
    join_only = [
        name
        for name in names
        if workload.requirements[name].roles <= {Role.JOIN, Role.KEY, Role.PROJECT}
    ]
    assert join_only == []


def test_blocking_admission_counts_prefix() -> None:
    from quwarts.core.repair.join_profile import blocking_admission

    report = blocking_admission(
        ["cardiovascular disease", "diabetes"],
        ["cardiovascular diseases", "anemia"],
        prefix=3,
        threshold=0.92,
    )
    assert report["possible_pairs"] == 4
    assert report["admitted_pairs"] == 1
    assert report["high_admitted"] == 1
    assert report["high_blocked"] == 0
    blocked = blocking_admission(["xyzabc"], ["abcxyz"], prefix=3, threshold=0.5)
    assert blocked["admitted_pairs"] == 0
    assert blocked["high_blocked"] >= 1


def test_canonical_lookup_uses_er_map_when_norm_is_domain() -> None:
    from quwarts.core.models import ModuleConfig, PopulationPolicy
    from quwarts.core.population import _canonical

    pop = PopulationPolicy()
    pop.norm["item.name"] = ModuleConfig(strategy="domain", params={"map": {}, "domain": ["x"]})
    pop.er["item.name"] = ModuleConfig(
        strategy="identity",
        params={"map": {"Cardiovascular Disease": "er:abc"}},
    )
    record = EvidenceRecord(
        key="k", segment_id="s", doc_id="d", attribute="item.name",
        surface_value="cardiovascular disease", extractor_cfg_hash="h",
        quality_tier="cheap", stage=1,
    )
    assert _canonical(record, pop, "cardiovascular disease") == "er:abc"


def test_vote_amplified_agrees_then_grounds() -> None:
    from quwarts.core.extract import EvidenceStore
    from quwarts.core.ledger import TokenLedger
    from quwarts.core.models import SourceDocument
    from quwarts.core.quality import vote_amplified

    _, workload = analyze_workload(["SELECT SUM(item.amount) FROM item GROUP BY item.kind"])
    store = EvidenceStore()
    store.put(
        EvidenceRecord(
            key="p", segment_id="s", doc_id="d1", attribute="item.amount",
            surface_value="12", extractor_cfg_hash="h", quality_tier="cheap",
            stage=1, candidate_keys={"route": "primary"},
        )
    )
    store.put(
        EvidenceRecord(
            key="k", segment_id="s", doc_id="d1", attribute="item.kind",
            surface_value="viral", extractor_cfg_hash="h", quality_tier="cheap",
            stage=1, candidate_keys={"route": "primary"},
        )
    )
    docs = [SourceDocument(doc_id="d1", text="dose 12 viral")]

    class Fake:
        def __init__(self) -> None:
            self.store = store
            self.ledger = TokenLedger(theta=10_000)
            self.route = "primary"

        def configure_route(self, route="primary", **_kwargs):
            self.route = route

        def extract_attributes(self, documents, attributes, tiers, **_kwargs):
            name = attributes[0]
            value = "12" if name == "item.amount" else "viral"
            for doc in documents:
                store.put(
                    EvidenceRecord(
                        key=f"{self.route}-{name}",
                        segment_id="s",
                        doc_id=doc.doc_id,
                        attribute=name,
                        surface_value=value,
                        extractor_cfg_hash=self.route,
                        quality_tier="expensive",
                        stage=3,
                        candidate_keys={"route": self.route},
                    )
                )

        def commit_vote(self, doc_id, attribute, surface, parsed, reason):
            store.put(
                EvidenceRecord(
                    key=f"voted-{attribute}",
                    segment_id="s",
                    doc_id=doc_id,
                    attribute=attribute,
                    surface_value=surface,
                    parsed_value=parsed,
                    null_reason=reason,
                    extractor_cfg_hash="voted",
                    quality_tier="expensive",
                    stage=3,
                    candidate_keys={"route": "voted", "grounded": "0" if reason == "ungrounded" else "1"},
                )
            )
            return True

    report = vote_amplified(Fake(), docs, workload, ceiling=5000)
    assert report["n_agreed"] >= 1
    assert report["n_grounded"] >= 1
    voted = [row for row in store.records.values() if row.extractor_cfg_hash == "voted"]
    assert any(row.surface_value == "12" for row in voted)


def test_vote_amplified_nulls_ungrounded() -> None:
    from quwarts.core.extract import EvidenceStore
    from quwarts.core.ledger import TokenLedger
    from quwarts.core.models import SourceDocument
    from quwarts.core.quality import vote_amplified

    _, workload = analyze_workload(["SELECT SUM(item.amount) FROM item"])
    store = EvidenceStore()
    store.put(
        EvidenceRecord(
            key="p", segment_id="s", doc_id="d1", attribute="item.amount",
            surface_value="999", extractor_cfg_hash="h", quality_tier="cheap",
            stage=1, candidate_keys={"route": "primary"},
        )
    )
    docs = [SourceDocument(doc_id="d1", text="no numeric mention here")]

    class Fake:
        def __init__(self) -> None:
            self.store = store
            self.ledger = TokenLedger(theta=10_000)
            self.route = "primary"

        def configure_route(self, route="primary", **_kwargs):
            self.route = route

        def extract_attributes(self, documents, attributes, tiers, **_kwargs):
            for doc in documents:
                store.put(
                    EvidenceRecord(
                        key=f"{self.route}-item.amount",
                        segment_id="s",
                        doc_id=doc.doc_id,
                        attribute="item.amount",
                        surface_value="999",
                        extractor_cfg_hash=self.route,
                        quality_tier="expensive",
                        stage=3,
                        candidate_keys={"route": self.route},
                    )
                )

        def commit_vote(self, doc_id, attribute, surface, parsed, reason):
            store.put(
                EvidenceRecord(
                    key="voted-item.amount",
                    segment_id="s",
                    doc_id=doc_id,
                    attribute=attribute,
                    surface_value=surface,
                    parsed_value=parsed,
                    null_reason=reason,
                    extractor_cfg_hash="voted",
                    quality_tier="expensive",
                    stage=3,
                    candidate_keys={"route": "voted", "grounded": "0" if reason == "ungrounded" else "1"},
                )
            )
            return True

    report = vote_amplified(Fake(), docs, workload, ceiling=5000)
    assert report["n_ungrounded"] >= 1
    voted = store.records["voted-item.amount"]
    assert voted.surface_value is None
    assert voted.null_reason == "ungrounded"
