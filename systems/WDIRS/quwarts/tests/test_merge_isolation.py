from __future__ import annotations

from quwarts.core.conflict import presuppositions
from quwarts.core.models import Configuration, ModuleConfig, PopulationPolicy, PreprocessPolicy
from quwarts.core.population import _merge, identity_merge_keys, merge_audit
from quwarts.core.schema import canonical_schema
from quwarts.core.workload import analyze_workload


def _config(logical, merge_names: list[str]) -> Configuration:
    pop = PopulationPolicy()
    for name in merge_names:
        pop.er[name] = ModuleConfig(strategy="merge")
    return Configuration(
        id="c",
        schema=canonical_schema(logical),
        pop=pop,
        pre=PreprocessPolicy(mode="whole_document"),
        cluster_id="c0",
    )


def test_group_attribute_does_not_demand_merge() -> None:
    _, workload = analyze_workload(
        ["SELECT COUNT(*) AS n FROM item GROUP BY item.kind"]
    )
    demands = presuppositions(workload.templates[0])
    assert not any(item.module == "er" and item.demand == "merge" for item in demands)


def test_empty_key_does_not_merge() -> None:
    logical, workload = analyze_workload(
        ["SELECT COUNT(*) FROM item a JOIN item b ON a.name = b.name"]
    )
    config = _config(logical, ["item.name", "item.kind"])
    rows = [
        {"doc_id": "item/1", "item.name": None, "name": None, "kind": ""},
        {"doc_id": "item/2", "item.name": None, "name": None, "kind": ""},
    ]
    merged = _merge(rows, config, workload)
    assert len(merged) == 2
    assert merge_audit() == []


def test_categorical_agreement_cannot_establish_identity() -> None:
    logical, workload = analyze_workload(
        ["SELECT COUNT(*) FROM item GROUP BY item.kind"]
    )
    config = _config(logical, ["item.kind"])
    assert identity_merge_keys(workload) == {}
    rows = [
        {"doc_id": "item/1", "kind": "tablet", "item.kind": "tablet"},
        {"doc_id": "item/2", "kind": "tablet", "item.kind": "tablet"},
    ]
    merged = _merge(rows, config, workload)
    assert len(merged) == 2


def test_cross_relation_merge_is_impossible() -> None:
    logical, workload = analyze_workload(
        [
            "SELECT COUNT(*) FROM institution i JOIN drug d "
            "ON i.disease_name = d.disease_name "
            "WHERE i.id >= 1 AND d.id >= 1"
        ]
    )
    config = _config(logical, ["institution.id", "drug.id", "institution.disease_name"])
    rows = [
        {"doc_id": "institution/1", "id": "99", "institution.id": "99", "disease_name": "x"},
        {"doc_id": "drug/1", "id": "99", "drug.id": "99", "disease_name": "x"},
    ]
    merged = _merge(rows, config, workload)
    entities = {str(row["doc_id"]).split("/", 1)[0] for row in merged}
    assert len(merged) == 2
    assert entities == {"institution", "drug"}
    assert merge_audit() == []


def test_identity_merge_records_justification() -> None:
    logical, workload = analyze_workload(
        ["SELECT COUNT(*) FROM item a JOIN item b ON a.name = b.name"]
    )
    config = _config(logical, ["item.name"])
    rows = [
        {"doc_id": "item/1", "name": "alpha", "item.name": "alpha", "kind": "a"},
        {"doc_id": "item/2", "name": "alpha", "item.name": "alpha", "kind": "b"},
    ]
    merged = _merge(rows, config, workload)
    assert len(merged) == 1
    audit = merge_audit()
    assert len(audit) == 1
    assert audit[0]["justification"]
    assert set(audit[0]["docs"]) == {"item/1", "item/2"}
    assert audit[0]["entity"] == "item"
