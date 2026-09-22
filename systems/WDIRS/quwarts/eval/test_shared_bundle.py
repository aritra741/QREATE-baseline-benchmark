"""Deterministic shared-bundle partition and inventory tests. No model calls."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))

from quwarts.core.shared_bundle.graph import AttributeGraph, partition_bundles
from quwarts.core.shared_bundle.inventory import AttributeRecord, compile_attribute_inventory
from quwarts.core.shared_bundle.tasks import build_packages, build_tasks, prefix_within, schedule_packages


def _rec(name: str, occ: int, queries: list[str], others: list[str]) -> AttributeRecord:
    return AttributeRecord(
        name=name,
        sql_type="TEXT",
        occurrence_count=occ,
        queries=queries,
        roles={"WHERE": occ},
        predicate_literals=[],
        numeric_comparisons=[],
        categorical_literals=[],
        cooccurring=others,
        expressions=[],
    )


def test_partition_affinity_and_ties() -> None:
    records = {
        "a": _rec("a", 5, ["q1"], ["c"]),
        "b": _rec("b", 5, ["q2"], ["d"]),
        "c": _rec("c", 4, ["q1"], ["a"]),
        "d": _rec("d", 4, ["q2"], ["b"]),
        "e": _rec("e", 1, ["q3"], []),
    }
    graph = AttributeGraph(
        nodes={name: {"occurrence_count": rec.occurrence_count, "n_queries": rec.n_queries, "roles": rec.roles} for name, rec in records.items()},
        edges={"a|c": 2, "b|d": 2},
    )
    bundles = partition_bundles(records, graph)
    signatures = [item.signature for item in bundles]
    assert signatures == ["a+c", "b+d", "e"]
    assert all(1 <= len(item.attributes) <= 3 for item in bundles)


def test_schedule_skips_too_large_then_takes_next() -> None:
    from quwarts.core.shared_bundle.tasks import CandidateTask, EntityPackage

    def pkg(eid: str, impact: int, cost: int) -> EntityPackage:
        task = CandidateTask(eid, eid, "a", ["a"], ["a"], impact, {})
        item = EntityPackage(eid, eid, [task], impact, cost, impact / cost)
        return item

    packages = [pkg("e2", 10, 80), pkg("e1", 10, 30), pkg("e3", 1, 20)]
    scheduled = schedule_packages(packages, ceiling=50)
    assert [item.entity_id for item in scheduled] == ["e1", "e3"]
    assert [item.entity_id for item in prefix_within(scheduled, 30)] == ["e1"]


def test_inventory_excludes_select_aliases() -> None:
    statements = {
        "q1": "SELECT CASE WHEN revenue > 0 THEN 'ok' ELSE 'no' END AS profit_status, COUNT(*) AS n FROM t WHERE revenue > 0 GROUP BY profit_status"
    }
    records = compile_attribute_inventory(statements)
    assert "revenue" in records
    assert "profit_status" not in records
    assert "n" not in records
    assert records["revenue"].occurrence_count >= 2
    assert records["revenue"].roles.get("WHERE", 0) >= 1


if __name__ == "__main__":
    test_partition_affinity_and_ties()
    test_schedule_skips_too_large_then_takes_next()
    test_inventory_excludes_select_aliases()
    print("ok")
