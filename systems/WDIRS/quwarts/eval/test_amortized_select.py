"""Generic widgets for the amortized selection program. No corpus names."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))

from quwarts.core.amortized_select.dsl import allowed_term_bank, apply_critic_fixes, validate_spec, normalize_spec
from quwarts.core.amortized_select.executor import execute_cell
from quwarts.core.amortized_select.features import annotate_candidate, spec_tokens
from quwarts.core.amortized_select.sample import sample_attribute


def test_untraceable_term_rejected() -> None:
    spec = normalize_spec(
        {
            "preferred_metadata_terms": {"row_label": ["zyxwidgetonly"], "column_header": [], "table_title": [], "section_title": []},
            "task_class": "extractive",
        },
        "widget_count",
        "extractive",
    )
    bank = allowed_term_bank("number of widgets", "widget_count", [])
    errors = validate_spec(spec, name="widget_count", description="number of widgets", bank=bank, literals=["ACME"], entity_names=[])
    assert any(item.startswith("untraceable_term") for item in errors)


def test_shared_metadata_term_allowed() -> None:
    feats = [
        [{"row_label": "Widgets total", "column_header": "Year", "table_title": "Ops", "section_title": "Ops", "raw_span": "1", "id": "C1"}],
        [{"row_label": "Widgets total", "column_header": "Year", "table_title": "Ops", "section_title": "Ops", "raw_span": "2", "id": "C1"}],
    ]
    bank = allowed_term_bank("total widgets", "widget_count", feats)
    spec = normalize_spec(
        {"preferred_metadata_terms": {"row_label": ["widgets", "total"], "column_header": [], "table_title": [], "section_title": []}},
        "widget_count",
        "extractive",
    )
    errors = validate_spec(spec, name="widget_count", description="total widgets", bank=bank, literals=[], entity_names=[])
    assert errors == []


def test_executor_prefers_total_and_abstains_on_tie() -> None:
    spec = {
        "preferred_metadata_terms": {"row_label": ["widgets"], "column_header": [], "table_title": [], "section_title": []},
        "rejected_metadata_terms": {"row_label": [], "column_header": [], "table_title": [], "section_title": []},
        "period_policy": "latest",
        "scope_policy": "total",
        "unit_policy": "any",
        "value_form": "number",
        "allowed_operations": ["identity"],
        "tie_break_order": ["scope", "period"],
        "abstain_on_conflict": True,
    }
    toks = spec_tokens("widget_count", "total widgets")
    a = annotate_candidate(
        {"id": "C1", "raw_span": "10", "normalized": 10, "row_label": "Widgets total", "column_header": "2022", "table_title": "", "heading": "", "period": "2022", "unit": "", "currency": "", "start": 10, "kind": "table_row"},
        toks,
        100,
        1,
    )
    b = annotate_candidate(
        {"id": "C2", "raw_span": "3", "normalized": 3, "row_label": "North segment widgets", "column_header": "2022", "table_title": "", "heading": "", "period": "2022", "unit": "", "currency": "", "start": 20, "kind": "table_row"},
        toks,
        100,
        1,
    )
    out = execute_cell(spec, [a, b])
    assert out["status"] == "selected"
    assert out["candidate_ids"] == ["C1"]
    twin = annotate_candidate(
        {"id": "C3", "raw_span": "11", "normalized": 11, "row_label": "Widgets total", "column_header": "2022", "table_title": "", "heading": "", "period": "2022", "unit": "", "currency": "", "start": 30, "kind": "table_row"},
        toks,
        100,
        1,
    )
    tied = execute_cell(spec, [a, twin])
    assert tied["status"] == "abstain"
    assert tied["tie"] is True


def test_critic_removes_invalid_term() -> None:
    spec = normalize_spec(
        {"preferred_metadata_terms": {"row_label": ["widgets", "zyxonly"], "column_header": [], "table_title": [], "section_title": []}},
        "widget_count",
        "extractive",
    )
    bank = allowed_term_bank("total widgets", "widget_count", [])
    fixed = apply_critic_fixes(
        spec,
        {"invalid_terms": ["zyxonly"]},
        bank=bank,
        description="total widgets for the reporting period",
        allows_sum=False,
        unit_percent=False,
        domain=[],
    )
    assert "zyxonly" not in fixed["preferred_metadata_terms"]["row_label"]
    assert fixed["period_policy"] == "reporting_period"


def test_sampler_is_deterministic() -> None:
    rows = [{"entity_id": f"e{i}", "document_id": f"d{i}", "attribute": "widget_count"} for i in range(6)]
    feats = {(row["entity_id"], "widget_count"): [] for row in rows}
    left = [item["entity_id"] for item in sample_attribute(rows, feats, 3)]
    right = [item["entity_id"] for item in sample_attribute(rows, feats, 3)]
    assert left == right
