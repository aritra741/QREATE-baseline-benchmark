from __future__ import annotations

from quwarts.core.contracts import assign_vocab, case_literals_from_sql, compile_contracts
from quwarts.core.workload import analyze_workload


def test_case_like_literals_strip_percent() -> None:
    sql = (
        "SELECT CASE WHEN LOWER(item.form) LIKE '%tablet%' THEN 1 "
        "WHEN LOWER(item.form) LIKE '%capsule%' THEN 2 ELSE 0 END FROM item"
    )
    found = case_literals_from_sql(sql)
    assert set(found["item.form"]) == {"tablet", "capsule"}


def test_case_literals_are_column_vocab() -> None:
    sql = (
        "SELECT CASE WHEN item.form = 'tablet' THEN 1 "
        "WHEN item.form = 'capsule' THEN 2 ELSE 0 END FROM item"
    )
    found = case_literals_from_sql(sql)
    assert set(found["item.form"]) == {"tablet", "capsule"}
    assert set(found["form"]) == {"tablet", "capsule"}


def test_assign_vocab_does_not_default_to_first_token() -> None:
    assert assign_vocab("oral solution", ["tablet", "capsule"]) is None
    assert assign_vocab("film-coated tablet", ["tablet", "capsule"]) == "tablet"


def test_constrained_cell_keeps_document_surface() -> None:
    from quwarts.core.extract import constrained_cell

    surface, _parsed, reason, residue = constrained_cell(
        {"value": "tablet", "surface": "film-coated tablet"},
        ["tablet", "capsule"],
    )
    assert residue is False
    assert reason is None
    assert surface == "film-coated tablet"


def test_vocab_rewrite_case_not_join() -> None:
    from quwarts.core.rewrite import apply_vocab_derived

    case_sql = "SELECT CASE WHEN item.form = 'tablet' THEN 1 ELSE 0 END FROM item"
    rewritten = apply_vocab_derived(case_sql, {"item": {"form"}})
    assert "form__vocab" in rewritten
    join_sql = "SELECT 1 FROM item a JOIN item b ON a.name = b.name"
    skipped = apply_vocab_derived(join_sql, {"item": {"name"}})
    assert "name__vocab" not in skipped


def test_in_list_is_open_not_closed() -> None:
    _, workload = analyze_workload(
        ["SELECT SUM(1) FROM item WHERE item.kind IN ('a', 'b')"]
    )
    contracts = compile_contracts(workload)
    row = contracts["item.kind"]
    assert row["closed"] is False
    assert "in_list" in row["sources"]
    assert set(row["vocab"]) == {"a", "b"}
