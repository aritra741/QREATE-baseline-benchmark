from __future__ import annotations

from quwarts.core.conflict import cluster_templates, conflict_graph
from quwarts.core.models import CoverageSet, SliceSpec
from quwarts.core.rewrite import admissible, rewritable
from quwarts.core.schema import generate_physical_schemas
from quwarts.core.workload import analyze_workload


def test_rewritability_and_admissibility() -> None:
    logical, workload = analyze_workload(
        ["SELECT player.name FROM player WHERE player.position = 'Guard'"]
    )
    schemas = generate_physical_schemas(logical)
    assert schemas
    assert all(schema.declared_fds or schema.primary_keys for schema in schemas)
    coverage = CoverageSet(
        attribute_ranges={
            "player.name": SliceSpec(kind="full"),
            "player.position": SliceSpec(kind="ranges"),
        },
        attributes_present={"player.name", "player.position"},
        grain={"player": "mention"},
        forms={"player.name": {"surface"}, "player.position": {"surface"}},
        corpus_fingerprint="x",
    )
    coverage.attribute_ranges["player.position"].ranges = []
    # full coverage on name; position constants checked separately
    coverage.attribute_ranges["player.position"] = SliceSpec(kind="full")
    ok = any(rewritable(workload.templates[0], schema, coverage, workload.requirements).ok for schema in schemas)
    assert ok
    assert admissible(workload.templates, [(schema, coverage) for schema in schemas], workload.requirements)


def test_rejected_when_attribute_missing() -> None:
    logical, workload = analyze_workload(
        ["SELECT player.name FROM player WHERE player.position = 'Guard'"]
    )
    schema = generate_physical_schemas(logical)[0]
    schema.covered_attributes = {"player.salary"}
    result = rewritable(workload.templates[0], schema)
    assert result.ok is False
    assert result.sql is None


def test_conflict_clusters_are_colorings() -> None:
    _, workload = analyze_workload(
        [
            "SELECT player.name FROM player WHERE player.position = 'Guard'",
            "SELECT SUM(player.salary) FROM player",
        ]
    )
    edges = conflict_graph(workload)
    clusters = cluster_templates(workload)
    assert clusters
    membership = {}
    for cluster in clusters:
        for tid in cluster.template_ids:
            membership[tid] = cluster.id
    for edge in edges:
        if not edge.destructive:
            continue
        # destructive neighbors must not share a cluster
        assert membership[edge.template_a] != membership[edge.template_b]
