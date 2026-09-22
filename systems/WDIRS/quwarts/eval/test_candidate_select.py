"""Gold-free candidate-selection tests. No model calls."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))

from quwarts.core.candidate_select.candidates import generate_pool, rank_and_cap
from quwarts.core.candidate_select.construct import construct_classification, construct_extractive
from quwarts.core.candidate_select.prompt import assemble, prefix_contains_literal
from quwarts.core.candidate_select.schema_spec import AttrSpec, parse_schema_domain
from quwarts.core.shared_bundle.context_blocks import parse_layout


def test_domain_from_official_description() -> None:
    labels = parse_schema_domain("binary flag; choose one from ['Yes', 'No'].")
    assert labels == ["Yes", "No"]
    empty = parse_schema_domain("name of the responsible organization.")
    assert empty == []


def test_candidates_have_source_offsets() -> None:
    text = "RESULTS\nWidgets | 2022 | 2021\nTotal widgets | 27,802 | 21,000\nContact: Example Partners.\n"
    spec = AttrSpec(
        name="widgets",
        official_description="total widgets reported for the period. Enter a number.",
        sql_type="REAL",
        dtype="numeric",
        usage="numerical",
        is_fixed=False,
        schema_domain=[],
        roles={"WHERE": 1},
        n_expressions=2,
        n_queries=2,
        allows_sum=False,
        requires_usd=False,
        target_currency=None,
        unit_percent=False,
        task_class="extractive",
    )
    blocks = parse_layout("doc", text)
    kept = rank_and_cap(generate_pool(blocks, spec, text, text), spec)
    assert kept
    assert all(item.opaque_id.startswith("C") for item in kept)
    assert all(item.end > item.start >= 0 for item in kept)
    assert any(item.normalized in {27802, 21000} for item in kept)


def test_construct_uses_ids_only() -> None:
    spec = AttrSpec("widgets", "total widgets", "REAL", "numeric", "numerical", False, [], {}, 1, 1, False, False, None, False, "extractive")
    from quwarts.core.candidate_select.candidates import Candidate

    cands = [
        Candidate("C1", "27,802", 27802, "Total widgets", "2022", "Results", "Results", "2022", None, None, 10, 16, "", "Total widgets 27,802", True, 1.0, "table_row"),
        Candidate("C2", "21,000", 21000, "Total widgets", "2021", "Results", "Results", "2021", None, None, 20, 26, "", "Total widgets 21,000", True, 0.8, "table_row"),
    ]
    built = construct_extractive(spec=spec, candidates=cands, candidate_ids=["C1"], operation="identity", status="selected")
    assert built["value"] == 27802
    assert built["used_ids"] == ["C1"]
    denied = construct_extractive(spec=spec, candidates=cands, candidate_ids=["C9"], operation="identity", status="selected")
    assert denied["value"] is None


def test_extractive_prompt_has_no_predicate_literals() -> None:
    spec = AttrSpec("widgets", "total widgets reported for the period.", "REAL", "numeric", "numerical", False, [], {}, 1, 1, False, False, None, False, "extractive")
    from quwarts.core.candidate_select.candidates import Candidate

    cands = [Candidate("C1", "458467", 458467, "Widgets", "2022", "Results", "Results", "2022", None, None, 4, 10, "", "Widgets 458467", True, 1.0, "table_row")]
    rendered = assemble(spec, cands, "Report 2022")
    leaked = prefix_contains_literal(rendered["user"], ["100000000", "LABEL"], "Widgets 458467", spec.official_description)
    assert leaked == []
    assert "candidate_ids" in rendered["output_schema"]
    assert "value" not in rendered["output_schema"]


def test_classification_rejects_off_domain() -> None:
    spec = AttrSpec("flag", "choose one from ['Yes', 'No']", "TEXT", "string", "categorical", True, ["Yes", "No"], {}, 1, 1, False, False, None, False, "classification")
    out = construct_classification(spec=spec, label="Other", status="selected", evidence_ids=[], candidates=[])
    assert out["value"] is None
    ok = construct_classification(spec=spec, label="Yes", status="selected", evidence_ids=[], candidates=[])
    assert ok["value"] == "Yes"


if __name__ == "__main__":
    test_domain_from_official_description()
    test_candidates_have_source_offsets()
    test_construct_uses_ids_only()
    test_extractive_prompt_has_no_predicate_literals()
    test_classification_rejects_off_domain()
    print("ok")
