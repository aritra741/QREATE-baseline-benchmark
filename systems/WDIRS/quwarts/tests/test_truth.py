from __future__ import annotations

import sqlite3

from quwarts.core.truth import (
    assert_null_shared,
    as_sql_int,
    cells_for_source,
    label_from_classifier,
    rewrite_cell,
    sql_and,
    sql_not,
    sql_or,
    sql_from_source,
)


def _sqlite_not(value: int | None) -> int | None:
    conn = sqlite3.connect(":memory:")
    try:
        row = conn.execute("SELECT NOT ?", (value,)).fetchone()
        return row[0]
    finally:
        conn.close()


def _sqlite_binop(op: str, left: int | None, right: int | None) -> int | None:
    conn = sqlite3.connect(":memory:")
    try:
        row = conn.execute(f"SELECT ? {op} ?", (left, right)).fetchone()
        return row[0]
    finally:
        conn.close()


def test_null_source_propagates_to_all_derived() -> None:
    truths = [sql_from_source(True, True), sql_from_source(True, False), sql_from_source(True, None)]
    assert truths == ["NULL", "NULL", "NULL"]
    assert_null_shared(True, truths)


def test_classifier_uncertainty_is_not_false() -> None:
    label = label_from_classifier(False, False, "uncertain")
    assert label.sql_truth == "NULL"
    assert label.classifier_status == "uncertain"
    assert as_sql_int(label.sql_truth) is None
    known_false = label_from_classifier(False, False, "known")
    assert known_false.sql_truth == "FALSE"
    assert as_sql_int(known_false.sql_truth) == 0


def test_null_false_unknown_are_distinguishable() -> None:
    values = {
        "NULL": as_sql_int("NULL"),
        "FALSE": as_sql_int("FALSE"),
        "TRUE": as_sql_int("TRUE"),
        "UNKNOWN": as_sql_int(label_from_classifier(False, None, "uncertain").sql_truth),
    }
    assert values["NULL"] is None
    assert values["UNKNOWN"] is None
    assert values["FALSE"] == 0
    assert values["TRUE"] == 1
    assert values["FALSE"] != values["NULL"]
    status = label_from_classifier(False, None, "uncertain").classifier_status
    assert status == "uncertain"
    assert label_from_classifier(False, False, "known").classifier_status == "known"


def test_three_valued_ops_match_sqlite() -> None:
    domain: list[tuple[str, int | None]] = [("TRUE", 1), ("FALSE", 0), ("NULL", None)]
    for name, raw in domain:
        assert as_sql_int(sql_not(name)) == _sqlite_not(raw)  # type: ignore[arg-type]
    for left_name, left in domain:
        for right_name, right in domain:
            assert as_sql_int(sql_and(left_name, right_name)) == _sqlite_binop("AND", left, right)  # type: ignore[arg-type]
            assert as_sql_int(sql_or(left_name, right_name)) == _sqlite_binop("OR", left, right)  # type: ignore[arg-type]


def test_rewrite_cell_drops_classifier_status() -> None:
    uncertain = label_from_classifier(False, True, "uncertain")
    failed = label_from_classifier(False, False, "failed")
    known = label_from_classifier(False, False, "known")
    assert rewrite_cell(uncertain) is None
    assert rewrite_cell(failed) is None
    assert rewrite_cell(known) == 0


def test_null_source_shared_across_predicates() -> None:
    labels = cells_for_source(True, [(True, "known"), (False, "uncertain"), (None, "failed")])
    assert [item.sql_truth for item in labels] == ["NULL", "NULL", "NULL"]
    assert [rewrite_cell(item) for item in labels] == [None, None, None]


def test_empty_compare_null_is_null_not_true() -> None:
    """The earlier <> '' failure: NULL source is NULL, not FALSE."""

    assert sql_from_source(True, False) == "NULL"
    assert sql_from_source(False, False) == "FALSE"
    assert sql_from_source(False, True) == "TRUE"
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.execute("INSERT INTO t VALUES (NULL), (''), ('x')")
        rows = conn.execute(
            "SELECT CASE WHEN v IS NULL THEN NULL WHEN v <> '' THEN 1 ELSE 0 END FROM t ORDER BY rowid"
        ).fetchall()
        assert rows == [(None,), (0,), (1,)]
    finally:
        conn.close()
