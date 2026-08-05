"""Offline regressions for the independent NL-only DocETL runner."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

DOCETL_DIR = Path(__file__).resolve().parent
if str(DOCETL_DIR) not in sys.path:
    sys.path.insert(0, str(DOCETL_DIR))

import run_player_nl_only_docetl as nl_runner
from evaluate_player_nl_docetl_bundle import verify_bundle
from run_player_nl_only_docetl import (
    FilterPlan,
    QueryPlan,
    TokenTracker,
    aggregate_records,
    load_nl_workload,
    load_opaque_documents,
    route_documents,
    seal_bundle,
    validate_plan,
)


def _plan(**changes) -> QueryPlan:
    plan = QueryPlan(
        query_id="q0",
        text="Average amount for each category.",
        record_entity="record",
        group_field="category",
        group_type="string",
        group_alias="category",
        aggregate="avg",
        measure_field="amount",
        measure_type="number",
        measure_alias="avg_amount",
    )
    return replace(plan, **changes)


def _record(
    identity: str,
    group: object,
    measure: object,
    **extra,
) -> dict:
    return {
        "supported": True,
        "record_identity": identity,
        "group_value": group,
        "has_measure": measure is not None,
        "measure_value": measure if measure is not None else 0,
        **extra,
    }


def test_synthesis_source_has_no_reference_or_evaluation_imports() -> None:
    path = DOCETL_DIR / "run_player_nl_only_docetl.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = (
        "diagnostics.run_config_grid",
        "spp.aggregation_metrics",
        "spp.config_grid",
        "evaluation",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imports
        for prefix in forbidden
    )
    lowered = source.lower()
    assert "--sql-manifest" not in lowered
    assert "load_ground_truth" not in lowered
    assert "columns_per_table_from_sql" not in lowered
    assert "_raw_doc_records_for_table" not in lowered


def test_nl_loader_rejects_answer_channels(tmp_path: Path) -> None:
    workload = tmp_path / "workload.json"
    workload.write_text(
        json.dumps(
            [
                {
                    "query_id": "q0",
                    "text": "Count records.",
                    "sql": "SELECT COUNT(*) FROM answers",
                }
            ]
        )
    )
    with pytest.raises(ValueError, match="forbidden fields"):
        load_nl_workload(workload)

    forbidden = tmp_path / "Data"
    forbidden.mkdir()
    with pytest.raises(ValueError, match="forbidden"):
        load_opaque_documents(forbidden)


def test_opaque_document_ids_ignore_paths(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    (first / "misleading_a").mkdir(parents=True)
    (second / "misleading_b").mkdir(parents=True)
    text = "Northbank is a place with many residents."
    (first / "misleading_a" / "99.txt").write_text(text)
    (second / "misleading_b" / "1.txt").write_text(text)

    left = load_opaque_documents(first)
    right = load_opaque_documents(second)

    assert [doc.document_id for doc in left] == [
        doc.document_id for doc in right
    ]
    assert "/" not in left[0].document_id
    assert left[0].content_sha256 == hashlib.sha256(text.encode()).hexdigest()


def test_independent_plan_validation_is_generic() -> None:
    plan = validate_plan(
        {
            "query_id": "q",
            "text": "For each region, total amounts over ten.",
            "record_entity": "transactions",
            "group_field": "Region Name",
            "group_type": "STRING",
            "group_alias": "region",
            "aggregate": "SUM",
            "measure_field": "Amount",
            "measure_type": "NUMBER",
            "measure_alias": "total_amount",
            "filters": [
                {
                    "field": "amount",
                    "semantic_type": "number",
                    "operator": ">",
                    "value": "10",
                    "upper_value": "",
                }
            ],
            "having_operator": "",
            "having_value": 0,
        }
    )
    assert plan.record_entity == "transaction"
    assert plan.group_field == "region_name"
    assert plan.aggregate == "sum"
    assert plan.filters == (
        FilterPlan("amount", "number", ">", "10", ""),
    )


def test_planner_retries_omitted_queries_individually(
    monkeypatch,
    tmp_path: Path,
) -> None:
    queries = [
        {"query_id": "q0", "text": "Count records by category."},
        {"query_id": "q1", "text": "Average amount by category."},
    ]

    def fake_run(name, rows, prompt, schema, work, **runtime):
        selected = rows if name.startswith("plan_retry_") else rows[:1]
        output = []
        for row in selected:
            output.append(
                {
                    **row,
                    "record_entity": "record",
                    "group_field": "category",
                    "group_type": "string",
                    "group_alias": "category",
                    "aggregate": "count" if row["query_id"] == "q0" else "avg",
                    "measure_field": (
                        "record" if row["query_id"] == "q0" else "amount"
                    ),
                    "measure_type": "number",
                    "measure_alias": (
                        "record_count"
                        if row["query_id"] == "q0"
                        else "avg_amount"
                    ),
                    "filter_1_field": "",
                    "filter_1_type": "",
                    "filter_1_operator": "",
                    "filter_1_value": "",
                    "filter_1_upper_value": "",
                    "filter_2_field": "",
                    "filter_2_type": "",
                    "filter_2_operator": "",
                    "filter_2_value": "",
                    "filter_2_upper_value": "",
                    "having_operator": "",
                    "having_value": 0,
                }
            )
        return output

    monkeypatch.setattr(nl_runner, "_run_map", fake_run)
    plans = nl_runner.infer_plans(queries, tmp_path)
    assert [plan.query_id for plan in plans] == ["q0", "q1"]


@pytest.mark.parametrize(
    ("aggregate", "alias", "expected"),
    [
        ("count", "record_count", 2),
        ("sum", "sum_amount", 30),
        ("avg", "avg_amount", 15),
        ("min", "min_amount", 10),
        ("max", "max_amount", 20),
    ],
)
def test_deterministic_aggregates_deduplicate_identities(
    aggregate: str,
    alias: str,
    expected: object,
) -> None:
    plan = _plan(aggregate=aggregate, measure_alias=alias)
    records = [
        _record("A", "North", 10),
        _record("A", "North", 999),
        _record("B", "North", 20),
    ]
    assert aggregate_records(plan, records) == [
        {"category": "North", alias: expected}
    ]


def test_filters_and_having_are_applied_after_extraction() -> None:
    plan = _plan(
        aggregate="count",
        measure_alias="record_count",
        filters=(
            FilterPlan("year", "number", "between", "2000", "2010"),
            FilterPlan("kind", "string", "in", "A,B", ""),
        ),
        having_operator=">",
        having_value=1,
    )
    records = [
        _record(
            "A",
            "North",
            1,
            has_filter_0=True,
            filter_0_value=2001,
            has_filter_1=True,
            filter_1_value="A",
        ),
        _record(
            "B",
            "North",
            1,
            has_filter_0=True,
            filter_0_value=2005,
            has_filter_1=True,
            filter_1_value="B",
        ),
        _record(
            "C",
            "South",
            1,
            has_filter_0=True,
            filter_0_value=1990,
            has_filter_1=True,
            filter_1_value="A",
        ),
    ]
    assert aggregate_records(plan, records) == [
        {"category": "North", "record_count": 2}
    ]


def test_content_routes_use_only_classifier_output(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "wrong").mkdir(parents=True)
    (source / "wrong" / "1.txt").write_text("An organization record.")
    document = load_opaque_documents(source)[0]
    routes = route_documents(
        [document],
        [
            {
                "document_id": document.document_id,
                "document_entity": "organizations",
            }
        ],
        ("member", "organization"),
    )
    assert routes["member"] == []
    assert routes["organization"] == [document]


def test_bundle_seal_detects_tampering(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    tracker = TokenTracker()
    tracker.prompt_tokens = 10
    tracker.completion_tokens = 2
    plan = _plan()
    seal_bundle(
        bundle,
        queries=[{"query_id": "q0", "text": plan.text}],
        plans=[plan],
        routing={"record": ["doc-1"]},
        evidence={"q0": [_record("A", "North", 10)]},
        results={"q0": [{"category": "North", "avg_amount": 10}]},
        tracker=tracker,
        model="ollama/example",
        corpus_fingerprint="abc",
    )
    assert verify_bundle(bundle)["construction_tokens"] == 12

    result = bundle / "query_tables" / "q0.json"
    result.write_text("[]")
    with pytest.raises(ValueError, match="artifact mismatch"):
        verify_bundle(bundle)


def test_evaluator_refuses_unsealed_bundle(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsealed"):
        verify_bundle(tmp_path)
