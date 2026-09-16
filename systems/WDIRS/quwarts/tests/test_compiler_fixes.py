from __future__ import annotations

from quwarts.core.extract import validate_cell
from quwarts.core.logical import infer_logical_schema, is_coarsening
from quwarts.core.models import SliceSpec
from quwarts.core.pipeline import compile_workload, load_documents
from quwarts.core.schema import _pk_for, generate_physical_schemas
from quwarts.core.workload import analyze_workload

from conftest import CORPUS


def test_derived_aliases_are_not_attributes() -> None:
    sql = (
        "SELECT CAST(draft_year / 10 AS INTEGER) * 10 AS draft_decade, "
        "CASE WHEN age < 30 THEN 'under_30' ELSE '30s' END AS age_band, "
        "COUNT(*) AS player_count FROM player "
        "WHERE draft_year > 0 GROUP BY draft_decade, age_band"
    )
    logical = infer_logical_schema([sql])
    names = {item.name for item in logical.attributes if item.entity_type == "player"}
    assert "draft_year" in names
    assert "age" in names
    assert "draft_decade" not in names
    assert "age_band" not in names
    aliases = {item.alias for item in logical.expressions}
    assert "draft_decade" in aliases
    assert "age_band" in aliases


def test_pk_is_identity_not_first_attribute() -> None:
    sqls = [
        "SELECT city.area, city.city_name FROM city",
        "SELECT owner.acquisition_decade, owner.name FROM owner",
        "SELECT player.id, player.age FROM player",
        "SELECT team.championship, team.team_name FROM team",
    ]
    # acquisition_decade must not enter L; name must.
    logical = infer_logical_schema(
        [
            "SELECT city.area, city.city_name FROM city",
            "SELECT owner.name, owner.own_year FROM owner",
            "SELECT player.id, player.age FROM player",
            "SELECT team.championship, team.team_name FROM team",
        ]
    )
    pks = []
    for entity in logical.entity_types:
        key = _pk_for(entity, logical)
        pks.extend(key)
        assert not any(is_coarsening(part.split(".")[-1]) for part in key)
    assert "city.city_name" in pks
    assert "owner.name" in pks
    assert "player.id" in pks
    assert "team.team_name" in pks
    assert "city.area" not in pks
    assert "team.championship" not in pks
    _ = sqls


def test_between_is_interval_contained() -> None:
    spec = SliceSpec(kind="ranges")
    spec.ranges = []
    from quwarts.core.models import PredicateRange

    spec = SliceSpec(
        kind="ranges",
        ranges=[PredicateRange(attribute="player.draft_pick", op="BETWEEN", values=[1, 14])],
    )
    assert spec.contains_constants([1, 10], op="BETWEEN")
    assert not spec.contains_constants([20, 30], op="BETWEEN")


def test_validate_cell_rejects_garbage() -> None:
    assert validate_cell({"value": None}, "string")[2] == "not_found"
    assert validate_cell({"nested": 1}, "string")[2] == "non_scalar"
    assert validate_cell("Sure, I can help with extracting", "string")[2] == "non_scalar"
    assert validate_cell("of", "numeric")[2] == "dtype_coercion"
    surface, parsed, reason = validate_cell(24, "numeric")
    assert reason is None
    assert parsed == 24
    assert surface == "24"


def test_compile_materializes_one_db_per_cluster(tmp_path) -> None:
    documents = load_documents(CORPUS)
    portfolio = compile_workload(
        documents,
        ["SELECT player.name FROM player WHERE player.position = 'Guard'"],
        theta=5000,
        seed=0,
        artifact_root=tmp_path,
    )
    assert portfolio.databases
    assert portfolio.logical_schema.entity_types
    assert all(db.sqlite_path for db in portfolio.databases)
    _, workload = analyze_workload(
        ["SELECT player.name FROM player WHERE player.position = 'Guard'"],
        portfolio.logical_schema,
    )
    from quwarts.core.conflict import cluster_templates

    assert len(portfolio.configurations) == len(cluster_templates(workload))


def test_disjoint_in_list_is_a_domain() -> None:
    from quwarts.core.domain import classify_declared_domains
    from quwarts.core.models import EvidenceRecord

    sql = (
        "SELECT player.name FROM player "
        "WHERE player.position IN ('Frontcourt', 'Backcourt')"
    )
    _, workload = analyze_workload([sql])
    records = [
        EvidenceRecord(
            key="a",
            segment_id="s",
            doc_id="d",
            attribute="player.position",
            surface_value="point guard",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        )
    ]
    classify_declared_domains(workload, records)
    assert workload.requirements["player.position"].declared_domain == ["Backcourt", "Frontcourt"]


def test_overlapping_in_list_is_a_slice() -> None:
    from quwarts.core.domain import classify_declared_domains
    from quwarts.core.models import EvidenceRecord

    _, workload = analyze_workload(
        ["SELECT city_name FROM city WHERE state_name IN ('California', 'Texas')"]
    )
    records = [
        EvidenceRecord(
            key=f"k{index}",
            segment_id="s",
            doc_id=f"d{index}",
            attribute="city.state_name",
            surface_value=value,
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        )
        for index, value in enumerate(["California", "Texas", "Washington"])
    ]
    classify_declared_domains(workload, records)
    assert workload.requirements["city.state_name"].declared_domain == []


def test_domain_disjointness_flags_unmapped_surfaces() -> None:
    from quwarts.core.domain import classify_declared_domains, disjoint_attributes
    from quwarts.core.models import EvidenceRecord

    sql = (
        "SELECT player.name FROM player "
        "WHERE player.position IN ('Frontcourt', 'Backcourt')"
    )
    _, workload = analyze_workload([sql])
    records = [
        EvidenceRecord(
            key="a",
            segment_id="s",
            doc_id="d",
            attribute="player.position",
            surface_value="point guard",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        )
    ]
    classify_declared_domains(workload, records)
    rows = [{"player.position": "point guard", "position": "point guard"}]
    assert "player.position" in disjoint_attributes(rows, workload)
    rows = [{"player.position": "Frontcourt", "position": "Frontcourt"}]
    assert disjoint_attributes(rows, workload) == []


def test_join_case_aliases_ignore_select_case() -> None:
    _, workload = analyze_workload(
        [
            "SELECT CASE WHEN mvp_awards >= 1 THEN 'mvp_winner' ELSE 'no_mvp' END "
            "FROM player p JOIN team t ON p.team = t.team_name "
            "JOIN city c ON c.city_name = CASE t.location "
            "WHEN 'Brooklyn' THEN 'New York City' ELSE t.location END"
        ]
    )
    assert workload.literal_aliases.get("Brooklyn") == "New York City"
    assert "mvp_winner" not in workload.literal_aliases.values()


def test_equijoin_disjointness_and_alias_resolution() -> None:
    from quwarts.core.domain import join_disjoint_pairs
    from quwarts.core.workload import mentions_from_sql

    mentions = mentions_from_sql(
        "SELECT t.team_name FROM player p "
        "JOIN team t ON TRIM(p.team) = TRIM(t.team_name)"
    )
    assert ("player.team", "team.team_name") in mentions["join_pairs"] or (
        "team.team_name",
        "player.team",
    ) in mentions["join_pairs"]
    _, workload = analyze_workload(
        [
            "SELECT t.team_name FROM player p "
            "JOIN team t ON TRIM(p.team) = TRIM(t.team_name)"
        ]
    )
    rows = [
        {"player.team": "Lakers", "team": "Lakers"},
        {"team.team_name": "Los Angeles Lakers", "team_name": "Los Angeles Lakers"},
    ]
    flagged = join_disjoint_pairs(rows, workload)
    assert flagged
    rows = [
        {"player.team": "Los Angeles Lakers", "team.team_name": "Los Angeles Lakers"},
    ]
    assert join_disjoint_pairs(rows, workload) == []


def test_coverage_null_does_not_overwrite_full() -> None:
    from quwarts.core.materialize import coverage_set
    from quwarts.core.models import (
        Configuration,
        EvidenceRecord,
        PopulationPolicy,
        PreprocessPolicy,
        SourceDocument,
    )
    from quwarts.core.schema import canonical_schema

    sql = "SELECT city.population FROM city WHERE city.population > 500000"
    logical, workload = analyze_workload([sql])
    records = [
        EvidenceRecord(
            key="a",
            segment_id="s1",
            doc_id="city/1",
            attribute="city.population",
            surface_value="800000",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        ),
        EvidenceRecord(
            key="b",
            segment_id="s2",
            doc_id="city/2",
            attribute="city.population",
            surface_value=None,
            null_reason="not_found",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        ),
    ]
    config = Configuration(
        id="c",
        schema=canonical_schema(logical),
        pop=PopulationPolicy(),
        pre=PreprocessPolicy(mode="whole_document"),
        cluster_id="c0",
    )
    coverage = coverage_set(
        records,
        config,
        workload,
        [SourceDocument(doc_id="city/1", text="x"), SourceDocument(doc_id="city/2", text="y")],
    )
    assert coverage.attribute_ranges["city.population"].kind == "full"


def test_coarsening_conflict_is_non_destructive() -> None:
    from quwarts.core.conflict import conflict_graph, conflict_mix
    from quwarts.core.models import DerivedExpression, Role, Template, Workload

    coarsen = Template(
        id="t_decade",
        canonical_sql="SELECT draft_decade FROM player GROUP BY draft_decade",
        roles_by_attribute={"player.draft_decade": {Role.GROUP}},
        entity_types={"player"},
    )
    key = Template(
        id="t_key",
        canonical_sql="SELECT draft_decade FROM player",
        roles_by_attribute={"player.draft_decade": {Role.KEY}},
        entity_types={"player"},
    )
    identity_a = Template(
        id="t_team_g",
        canonical_sql="SELECT team FROM player GROUP BY team",
        roles_by_attribute={"player.team": {Role.GROUP}},
        entity_types={"player"},
    )
    identity_b = Template(
        id="t_team_k",
        canonical_sql="SELECT team FROM player",
        roles_by_attribute={"player.team": {Role.KEY}},
        entity_types={"player"},
    )
    workload = Workload(
        templates=[coarsen, key, identity_a, identity_b],
        requirements={},
    )
    expressions = [
        DerivedExpression(
            alias="draft_decade",
            entity_type="player",
            base_attributes=["player.draft_year"],
            sql="CAST(draft_year / 10 AS INTEGER) * 10",
        )
    ]
    edges = conflict_graph(workload, expressions)
    mix = conflict_mix(edges)
    decade = [edge for edge in edges if edge.cell[1] == "player.draft_decade"]
    team = [edge for edge in edges if edge.cell[1] == "player.team"]
    assert decade
    assert all(not edge.destructive for edge in decade)
    assert team
    assert all(edge.destructive for edge in team)
    assert mix["destructive"] >= 1
    assert mix["non_destructive"] >= 1


def test_identity_join_and_group_are_separate_clusters() -> None:
    from quwarts.core.conflict import cluster_templates
    from quwarts.core.models import Role, Template, Workload

    grouped = Template(
        id="g",
        canonical_sql="SELECT team FROM player GROUP BY team",
        roles_by_attribute={"player.team": {Role.GROUP}},
        entity_types={"player"},
    )
    joined = Template(
        id="j",
        canonical_sql="SELECT team FROM player",
        roles_by_attribute={"player.team": {Role.KEY, Role.JOIN}},
        entity_types={"player"},
        join_pairs=[("player.team", "team.team_name")],
    )
    workload = Workload(templates=[grouped, joined], requirements={})
    clusters = cluster_templates(workload)
    assert len(clusters) == 2


def test_apply_domain_maps_surface_to_declared() -> None:
    from quwarts.core.domain import apply_domain

    mapping = {"point guard": "Backcourt", "center": "Frontcourt"}
    domain = ["Frontcourt", "Backcourt"]
    assert apply_domain("point guard", mapping, domain) == "Backcourt"
    assert apply_domain("Frontcourt", mapping, domain) == "Frontcourt"
    assert apply_domain("mascot", mapping, domain) is None
    assert apply_domain("Olympiacos", {"Lakers": "Los Angeles Lakers"}, []) == "Olympiacos"


def test_rewrite_substitutes_canonical_on_join_when_asked() -> None:
    from quwarts.core.rewrite import apply_identity_keys

    sql = "SELECT t.team_name FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name)"
    rewritten = apply_identity_keys(sql, "canonical", "surface", {"team", "team_name"})
    assert "team__canonical" in rewritten
    assert "team_name__canonical" in rewritten
    surface = apply_identity_keys(sql, "surface", "surface", {"team", "team_name"})
    assert "team__canonical" not in surface
    onesided = apply_identity_keys(sql, "canonical", "surface", {"team"})
    assert "team__canonical" not in onesided


def test_rewrite_group_by_uses_canonical() -> None:
    from quwarts.core.rewrite import apply_identity_keys

    sql = "SELECT team, COUNT(*) FROM player GROUP BY team"
    rewritten = apply_identity_keys(sql, "surface", "canonical", {"team"})
    assert "GROUP BY" in rewritten.upper()
    assert "team__canonical" in rewritten


def test_join_yield_and_corroboration(tmp_path) -> None:
    import sqlite3

    from quwarts.core.domain import _corroborate
    from quwarts.core.models import EvidenceRecord
    from quwarts.core.rewrite import join_yield

    path = tmp_path / "yield.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE player (team TEXT, position TEXT)")
    conn.execute("CREATE TABLE team (team_name TEXT)")
    conn.execute("INSERT INTO player VALUES ('Lakers', 'Guard'), ('Heat', 'Forward')")
    conn.execute("INSERT INTO team VALUES ('Lakers')")
    conn.commit()
    conn.close()
    sql = (
        "SELECT p.team FROM player p JOIN team t ON p.team = t.team_name "
        "WHERE p.position = 'Guard'"
    )
    assert join_yield(sql, str(path)) == 1.0
    empty = (
        "SELECT p.team FROM player p JOIN team t ON p.team = t.team_name "
        "WHERE p.position = 'Forward'"
    )
    assert join_yield(empty, str(path)) == 0.0

    records = [
        EvidenceRecord(
            key="a",
            segment_id="s",
            doc_id="d1",
            attribute="player.team",
            surface_value="Royals",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        ),
        EvidenceRecord(
            key="b",
            segment_id="s",
            doc_id="d1",
            attribute="team.team_name",
            surface_value="Cavaliers",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        ),
        EvidenceRecord(
            key="c",
            segment_id="s",
            doc_id="d2",
            attribute="player.team",
            surface_value="Lakers",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        ),
        EvidenceRecord(
            key="d",
            segment_id="s",
            doc_id="d3",
            attribute="player.team",
            surface_value="Lakers",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        ),
        EvidenceRecord(
            key="e",
            segment_id="s",
            doc_id="d4",
            attribute="team.team_name",
            surface_value="Los Angeles Lakers",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        ),
    ]
    kept = _corroborate(
        {"Royals": "Cavaliers", "Lakers": "Los Angeles Lakers"},
        records,
    )
    assert "Royals" not in kept
    assert kept["Lakers"] == "Los Angeles Lakers"


def test_equijoin_unifies_type_to_string() -> None:
    from quwarts.core.conflict import cluster_templates
    from quwarts.core.domain import unify_join_types
    from quwarts.core.models import EvidenceRecord, Role
    from quwarts.core.population import policy_from_demands
    from quwarts.core.workload import analyze_workload

    _, workload = analyze_workload(
        [
            "SELECT t.team_name, COUNT(t.team_name) FROM player p "
            "JOIN team t ON p.team = t.team_name GROUP BY t.team_name"
        ]
    )
    records = [
        EvidenceRecord(
            key="a",
            segment_id="s",
            doc_id="team/1",
            attribute="team.team_name",
            surface_value="Sacramento Kings",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        )
    ]
    if "team.team_name" in workload.requirements:
        workload.requirements["team.team_name"].roles.add(Role.AGG_ADDITIVE)
        workload.requirements["team.team_name"].dtype = "numeric"
    unify_join_types(workload, records)
    assert workload.join_types["team.team_name"] == "string"
    assert workload.join_types["player.team"] == "string"
    clusters = cluster_templates(workload)
    pop = policy_from_demands(clusters[0].resolved_demands, workload)
    assert pop.type["team.team_name"].strategy == "string"


def test_equijoin_type_unification_errors_when_irreconcilable() -> None:
    from quwarts.core.domain import TypeUnificationError, unify_join_types
    from quwarts.core.models import EvidenceRecord
    from quwarts.core.workload import analyze_workload

    _, workload = analyze_workload(
        ["SELECT a.x FROM a JOIN b ON a.x = b.y"]
    )
    if "a.x" in workload.requirements:
        workload.requirements["a.x"].dtype = "numeric"
    if "b.y" in workload.requirements:
        workload.requirements["b.y"].dtype = "date"
    records = [
        EvidenceRecord(
            key="a",
            segment_id="s",
            doc_id="d1",
            attribute="a.x",
            surface_value="2020",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        ),
        EvidenceRecord(
            key="b",
            segment_id="s",
            doc_id="d2",
            attribute="b.y",
            surface_value="1995",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        ),
    ]
    try:
        unify_join_types(workload, records)
    except TypeUnificationError:
        return
    raise AssertionError("expected TypeUnificationError")


def test_bridge_keeps_identity_relations_and_cardinality() -> None:
    from quwarts.core.bridge import KEEP_RELATIONS, _enforce_left_function, _typed_links

    class Caller:
        def complete(self, prompt, purpose, **kwargs):
            return (
                '{"Royals": {"right": "Kings", "relation": "historical_name"},'
                ' "Wizards": {"right": "Go-Go", "relation": "affiliate"},'
                ' "Lakers": {"right": "Lakers", "relation": "alias"}}'
            )

    kept = _typed_links(
        ["Royals", "Wizards", "Lakers"],
        ["Kings", "Go-Go", "Lakers", "Clippers"],
        Caller(),
        "player.team",
        "team.team_name",
    )
    pairs = {(src, dest, rel) for src, dest, rel in kept}
    assert ("Royals", "Kings", "historical_name") in pairs
    assert ("Lakers", "Lakers", "alias") in pairs
    assert not any(src == "Wizards" for src, _, _ in kept)
    assert all(rel in KEEP_RELATIONS for _, _, rel in kept)

    rows = _enforce_left_function(
        [
            {"left_value": "Royals", "right_value": "Kings"},
            {"left_value": "Royals", "right_value": "Cavaliers"},
            {"left_value": "Hawks", "right_value": "Hawks"},
        ]
    )
    assert [row["left_value"] for row in rows] == ["Hawks"]


def test_rename_is_bridge_not_within_column_merge() -> None:
    from quwarts.core.bridge import build_bridges
    from quwarts.core.domain import build_domain_maps
    from quwarts.core.models import EvidenceRecord
    from quwarts.core.workload import analyze_workload

    _, workload = analyze_workload(
        [
            "SELECT t.team_name FROM player p "
            "JOIN team t ON TRIM(p.team) = TRIM(t.team_name)"
        ]
    )
    records = [
        EvidenceRecord(
            key="a",
            segment_id="s",
            doc_id="d1",
            attribute="player.team",
            surface_value="Philadelphia Warriors",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        ),
        EvidenceRecord(
            key="b",
            segment_id="s",
            doc_id="d2",
            attribute="player.team",
            surface_value="Philadelphia Warriors",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        ),
        EvidenceRecord(
            key="c",
            segment_id="s",
            doc_id="d3",
            attribute="team.team_name",
            surface_value="Philadelphia 76ers",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        ),
    ]
    _, report = build_domain_maps(records, workload)
    maps = report.get("maps") or {}
    team_map = maps.get("player.team") or {}
    assert "Philadelphia Warriors" not in team_map
    bridges = build_bridges(
        [("player.team", "team.team_name")],
        records,
        workload,
        caller=None,
        linkage={"Philadelphia Warriors": "Philadelphia 76ers"},
    )
    rows = bridges[("player.team", "team.team_name")]
    assert any(
        row["left_value"] == "Philadelphia Warriors"
        and row["right_value"] == "Philadelphia 76ers"
        for row in rows
    )


def test_bridge_rewrite_keeps_surface_columns(tmp_path) -> None:
    import sqlite3

    from quwarts.core.bridge import write_bridges
    from quwarts.core.rewrite import apply_bridges, join_yield

    path = tmp_path / "bridge.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE player (team TEXT, position TEXT)")
    conn.execute("CREATE TABLE team (team_name TEXT)")
    conn.execute("INSERT INTO player VALUES ('Royals', 'Guard')")
    conn.execute("INSERT INTO team VALUES ('Kings')")
    conn.commit()
    conn.close()
    sql = (
        "SELECT p.team FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) "
        "WHERE p.position = 'Guard'"
    )
    assert join_yield(sql, str(path)) == 0.0
    write_bridges(
        str(path),
        {
            ("player.team", "team.team_name"): [
                {
                    "left_value": "Royals",
                    "right_value": "Kings",
                    "evidence": "equijoin:player.team=team.team_name",
                    "confidence": "0.7",
                }
            ]
        },
    )
    rewritten = apply_bridges(sql, str(path))
    assert "bridge_player_team__team_team_name" in rewritten
    assert "p.team" in rewritten or "p.\"team\"" in rewritten
    assert "team__canonical" not in rewritten
    assert "OR" in rewritten.upper()
    assert join_yield(rewritten, str(path)) == 1.0

    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO player VALUES ('Lakers', 'Guard')")
    conn.execute("INSERT INTO team VALUES ('Lakers')")
    conn.commit()
    conn.close()
    mixed = (
        "SELECT p.team FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) "
        "WHERE p.position = 'Guard'"
    )
    mixed_sql = apply_bridges(mixed, str(path))
    assert join_yield(mixed_sql, str(path)) == 1.0


def test_join_authority_picks_identity_side() -> None:
    from quwarts.core.extract import join_authority
    from quwarts.core.workload import analyze_workload

    logical, workload = analyze_workload(
        [
            "SELECT t.team_name FROM player p JOIN team t ON p.team = t.team_name",
            "SELECT t.location FROM team t JOIN city c ON c.city_name = t.location",
        ]
    )
    refs = join_authority(workload, logical)
    assert refs.get("player.team") == "team.team_name"
    assert refs.get("team.location") == "city.city_name"
    assert "team.team_name" not in refs
    assert "city.city_name" not in refs


def test_constrained_cell_vocab_and_other() -> None:
    from quwarts.core.extract import constrained_cell

    vocab = ["Golden State Warriors", "Sacramento Kings"]
    surface, _parsed, reason, residue = constrained_cell("Golden State Warriors", vocab)
    assert reason is None
    assert residue is False
    assert surface == "Golden State Warriors"
    surface, _parsed, _reason, residue = constrained_cell(
        {"value": "other", "surface": "Philadelphia Warriors"}, vocab
    )
    assert residue is True
    assert surface == "Philadelphia Warriors"
    surface, _parsed, _reason, residue = constrained_cell("Cincinnati Royals", vocab)
    assert residue is True
    assert surface == "Cincinnati Royals"


def test_complete_authority_adds_missing_identity_row() -> None:
    from quwarts.core.extract import complete_authority
    from quwarts.core.models import EvidenceRecord
    from quwarts.core.workload import analyze_workload

    _, workload = analyze_workload(
        ["SELECT t.team_name FROM player p JOIN team t ON p.team = t.team_name"]
    )
    records = [
        EvidenceRecord(
            key="p",
            segment_id="s",
            doc_id="player/1",
            attribute="player.team",
            surface_value="Rochester Royals",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=2,
        ),
        EvidenceRecord(
            key="t",
            segment_id="s2",
            doc_id="team/1",
            attribute="team.team_name",
            surface_value="Sacramento Kings",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=2,
        ),
    ]
    completed = complete_authority(records, workload)
    names = {
        row.surface_value
        for row in completed
        if row.attribute == "team.team_name"
    }
    assert "Sacramento Kings" in names
    assert "Rochester Royals" in names
    assert any(
        row.doc_id.startswith("team/join_complete/")
        and row.surface_value == "Rochester Royals"
        for row in completed
    )


def test_complete_authority_ignores_identity_on_wrong_entity_doc() -> None:
    from quwarts.core.extract import complete_authority
    from quwarts.core.models import EvidenceRecord
    from quwarts.core.workload import analyze_workload

    _, workload = analyze_workload(
        ["SELECT t.team_name FROM player p JOIN team t ON p.team = t.team_name"]
    )
    records = [
        EvidenceRecord(
            key="p",
            segment_id="s",
            doc_id="player/1",
            attribute="player.team",
            surface_value="Rochester Royals",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=2,
        ),
        EvidenceRecord(
            key="t_wrong",
            segment_id="s2",
            doc_id="player/1",
            attribute="team.team_name",
            surface_value="Rochester Royals",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=2,
        ),
        EvidenceRecord(
            key="t",
            segment_id="s3",
            doc_id="team/1",
            attribute="team.team_name",
            surface_value="Sacramento Kings",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=2,
        ),
    ]
    completed = complete_authority(records, workload)
    assert any(
        row.doc_id.startswith("team/join_complete/")
        and row.surface_value == "Rochester Royals"
        for row in completed
    )


def test_bridge_rename_requires_comention() -> None:
    from quwarts.core.bridge import build_bridges
    from quwarts.core.models import EvidenceRecord, SourceDocument
    from quwarts.core.workload import analyze_workload

    _, workload = analyze_workload(
        ["SELECT t.team_name FROM player p JOIN team t ON p.team = t.team_name"]
    )
    records = [
        EvidenceRecord(
            key="p",
            segment_id="s",
            doc_id="player/1",
            attribute="player.team",
            surface_value="Philadelphia Warriors",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=2,
        ),
        EvidenceRecord(
            key="t",
            segment_id="s2",
            doc_id="team/1",
            attribute="team.team_name",
            surface_value="Philadelphia 76ers",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=2,
        ),
    ]

    class Caller:
        def complete(self, prompt, purpose, **kwargs):
            return (
                '{"Philadelphia Warriors": {"right": "Philadelphia 76ers",'
                ' "relation": "rename"},'
                ' "Sonics": {"right": "Philadelphia 76ers", "relation": "alias"}}'
            )

    silent = [SourceDocument(doc_id="d", text="A player for the club.")]
    both = [
        SourceDocument(
            doc_id="d",
            text="The Philadelphia Warriors later became distinct from the Philadelphia 76ers.",
        )
    ]
    dropped = build_bridges(
        [("player.team", "team.team_name")],
        records,
        workload,
        caller=Caller(),
        documents=silent,
    )
    rows = dropped.get(("player.team", "team.team_name")) or []
    assert not any(
        row["left_value"] == "Philadelphia Warriors"
        and row.get("relation") == "rename"
        for row in rows
    )
    kept = build_bridges(
        [("player.team", "team.team_name")],
        records,
        workload,
        caller=Caller(),
        documents=both,
    )
    rows = kept[("player.team", "team.team_name")]
    assert any(
        row["left_value"] == "Philadelphia Warriors"
        and row["right_value"] == "Philadelphia 76ers"
        and row.get("relation") == "rename"
        for row in rows
    )


def test_prefer_constrained_replaces_freeform_cache() -> None:
    from quwarts.core.extract import prefer_constrained_records
    from quwarts.core.models import EvidenceRecord

    free = EvidenceRecord(
        key="old",
        segment_id="s",
        doc_id="d",
        attribute="player.team",
        surface_value="Philadelphia Warriors",
        extractor_cfg_hash="old",
        quality_tier="cheap",
        stage=2,
        candidate_keys={"surface": "Philadelphia Warriors"},
    )
    constrained = EvidenceRecord(
        key="new",
        segment_id="s",
        doc_id="d",
        attribute="player.team",
        surface_value="Golden State Warriors",
        extractor_cfg_hash="new",
        quality_tier="cheap",
        stage=2,
        candidate_keys={"surface": "Golden State Warriors", "constrained": "vocab"},
    )
    kept = prefer_constrained_records([free, constrained])
    assert len(kept) == 1
    assert kept[0].surface_value == "Golden State Warriors"


def test_constrained_extract_uses_authority_vocab() -> None:
    from quwarts.core.extract import EvidenceStore, StagedExtractor
    from quwarts.core.ledger import TokenLedger
    from quwarts.core.models import EvidenceRecord, PreprocessPolicy, SourceDocument
    from quwarts.core.workload import analyze_workload

    class Caller:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def complete(self, prompt, purpose, **kwargs):
            self.prompts.append(prompt)
            return '{"player.team": "Sacramento Kings"}'

    logical, workload = analyze_workload(
        ["SELECT t.team_name FROM player p JOIN team t ON p.team = t.team_name"]
    )
    store = EvidenceStore()
    store.put(
        EvidenceRecord(
            key="auth",
            segment_id="team-s",
            doc_id="team/1",
            attribute="team.team_name",
            surface_value="Sacramento Kings",
            extractor_cfg_hash="h",
            quality_tier="cheap",
            stage=1,
        )
    )
    caller = Caller()
    extractor = StagedExtractor(
        store=store, ledger=TokenLedger(theta=10000, seed=0), caller=caller, seed=0,
    )
    extractor.extract(
        [SourceDocument(doc_id="player/1", text="He played for the Cincinnati Royals.")],
        workload,
        PreprocessPolicy(mode="whole_document"),
        {name: "cheap" for name in workload.requirements},
        logical=logical,
    )
    constrained = [prompt for prompt in caller.prompts if "ALLOWED" in prompt]
    assert constrained
    assert "Sacramento Kings" in constrained[0]
    records = [row for row in store.records.values() if row.attribute == "player.team"]
    assert records
    assert records[0].surface_value == "Sacramento Kings"
    assert records[0].candidate_keys.get("constrained") == "vocab"


def test_physical_keys_are_never_coarsenings() -> None:
    logical = infer_logical_schema(
        [
            "SELECT CAST(founded_year / 10 AS INTEGER) * 10 AS founded_decade, "
            "team_name FROM team WHERE founded_year > 0 GROUP BY founded_decade, team_name"
        ]
    )
    for schema in generate_physical_schemas(logical):
        for keys in schema.primary_keys.values():
            assert not any(is_coarsening(item.split(".")[-1]) for item in keys)
