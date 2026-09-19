from __future__ import annotations

import sqlite3
from pathlib import Path

from quwarts.core.group_case_escape import all_else_escape, eval_case_state, unknown_else_escape
from quwarts.core.query_group import (
    FROZEN_GROUP_POLICY,
    LIVE_GROUP_POLICY,
    accept_live_materialize,
    apply_live_group_policy,
    compile_group_expr,
    extract_group_expressions,
    group_bags,
    official_bags,
    rewrite_group_sql,
)


SEARCHED = "CASE WHEN manufacturer <> '' THEN 'known_manufacturer' ELSE 'manufacturer_unknown' END"
SEARCHED_SQL = f"SELECT {SEARCHED} AS mfr_status, COUNT(*) AS n FROM drug GROUP BY mfr_status"
MULTI = (
    "CASE WHEN flag = 1 THEN 'first' WHEN flag = 1 THEN 'second' "
    "WHEN flag = 2 THEN 'third' ELSE 'else' END"
)
MULTI_SQL = f"SELECT {MULTI} AS g, COUNT(*) AS n FROM drug GROUP BY g"
OMITTED = "CASE WHEN flag = 1 THEN 'one' END"
OMITTED_SQL = f"SELECT {OMITTED} AS g, COUNT(*) AS n FROM drug GROUP BY g"
SIMPLE = "CASE manufacturer WHEN 'Pfizer' THEN 'known' WHEN '' THEN 'empty' ELSE 'other' END"
SIMPLE_SQL = f"SELECT {SIMPLE} AS g, COUNT(*) AS n FROM drug GROUP BY g"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE drug (manufacturer TEXT, flag INTEGER);
        INSERT INTO drug(rowid, manufacturer, flag) VALUES
          (1, NULL, NULL),
          (2, '', 3),
          (3, 'Pfizer', 1),
          (4, 'Pfizer', 2);
        """
    )
    return conn


def _file_db(tmp_path: Path) -> Path:
    dest = tmp_path / "agent.db"
    conn = sqlite3.connect(str(dest))
    conn.executescript(
        """
        CREATE TABLE drug (manufacturer TEXT, flag INTEGER);
        INSERT INTO drug(rowid, manufacturer, flag) VALUES
          (1, NULL, NULL),
          (2, '', 3),
          (3, 'Pfizer', 1);
        """
    )
    conn.commit()
    conn.close()
    return dest


def test_sqlite_3vl_when_null_false_true() -> None:
    conn = _conn()
    null = eval_case_state(conn, SEARCHED_SQL, SEARCHED_SQL, SEARCHED, "1")
    empty = eval_case_state(conn, SEARCHED_SQL, SEARCHED_SQL, SEARCHED, "2")
    known = eval_case_state(conn, SEARCHED_SQL, SEARCHED_SQL, SEARCHED, "3")
    assert null["truths"] == ["NULL"]
    assert null["selected"] == "ELSE"
    assert empty["truths"] == ["FALSE"]
    assert empty["selected"] == "ELSE"
    assert known["truths"] == ["TRUE"]
    assert known["selected"] == "branch"
    conn.close()


def test_multiple_when_precedence() -> None:
    conn = _conn()
    first = eval_case_state(conn, MULTI_SQL, MULTI_SQL, MULTI, "3")
    third = eval_case_state(conn, MULTI_SQL, MULTI_SQL, MULTI, "4")
    unknown = eval_case_state(conn, MULTI_SQL, MULTI_SQL, MULTI, "1")
    all_false = eval_case_state(conn, MULTI_SQL, MULTI_SQL, MULTI, "2")
    assert first["truths"][0] == "TRUE"
    assert first["selected"] == "branch"
    assert first["original_result"] == "first"
    assert first["selected_index"] == 1
    assert third["original_result"] == "third"
    assert unknown["truths"] == ["NULL", "NULL", "NULL"]
    assert unknown["selected"] == "ELSE"
    assert all_false["truths"] == ["FALSE", "FALSE", "FALSE"]
    assert all_false["selected"] == "ELSE"
    conn.close()


def test_explicit_and_omitted_else() -> None:
    conn = _conn()
    explicit = eval_case_state(conn, SEARCHED_SQL, SEARCHED_SQL, SEARCHED, "1")
    omitted = eval_case_state(conn, OMITTED_SQL, OMITTED_SQL, OMITTED, "1")
    omitted_false = eval_case_state(conn, OMITTED_SQL, OMITTED_SQL, OMITTED, "2")
    assert explicit["else_value"] == "manufacturer_unknown"
    assert omitted["else_value"] is None
    assert omitted["selected"] == "ELSE"
    assert omitted["original_result"] is None
    assert omitted_false["selected"] == "ELSE"
    assert omitted_false["original_result"] is None
    conn.close()


def test_searched_and_simple_case() -> None:
    conn = _conn()
    searched = eval_case_state(conn, SEARCHED_SQL, SEARCHED_SQL, SEARCHED, "1")
    simple_null = eval_case_state(conn, SIMPLE_SQL, SIMPLE_SQL, SIMPLE, "1")
    simple_empty = eval_case_state(conn, SIMPLE_SQL, SIMPLE_SQL, SIMPLE, "2")
    simple_known = eval_case_state(conn, SIMPLE_SQL, SIMPLE_SQL, SIMPLE, "3")
    assert searched["selected"] == "ELSE"
    assert simple_null["truths"][0] == "NULL"
    assert simple_null["selected"] == "ELSE"
    assert simple_null["original_result"] == "other"
    assert simple_empty["truths"] == ["FALSE", "TRUE"]
    assert simple_empty["original_result"] == "empty"
    assert simple_known["truths"][0] == "TRUE"
    assert simple_known["original_result"] == "known"
    conn.close()


def test_null_and_illegal_labels_rejected() -> None:
    conn = _conn()
    state = eval_case_state(conn, SEARCHED_SQL, SEARCHED_SQL, SEARCHED, "1")
    legal = {"resolved": True, "agreement": "majority", "group_value": "known_manufacturer"}
    assert unknown_else_escape(state, legal)
    assert unknown_else_escape(state, {**legal, "group_value": None}) is False
    assert unknown_else_escape(state, {**legal, "group_value": "NULL"}) is False
    assert unknown_else_escape(state, {**legal, "group_value": "not_a_branch"}) is False
    assert accept_live_materialize(state, {**legal, "group_value": "manufacturer_unknown"}) is False
    conn.close()


def test_true_branch_never_overwritten() -> None:
    conn = _conn()
    known = eval_case_state(conn, SEARCHED_SQL, SEARCHED_SQL, SEARCHED, "3")
    multi = eval_case_state(conn, MULTI_SQL, MULTI_SQL, MULTI, "3")
    vote = {"resolved": True, "agreement": "majority", "group_value": "manufacturer_unknown"}
    other = {"resolved": True, "agreement": "majority", "group_value": "second"}
    assert known["selected"] == "branch"
    assert unknown_else_escape(known, vote) is False
    assert accept_live_materialize(known, vote) is False
    assert all_else_escape(known, vote) is False
    assert unknown_else_escape(multi, other) is False
    conn.close()


def test_live_policy_is_unknown_else_not_all_false() -> None:
    conn = _conn()
    unknown = eval_case_state(conn, SEARCHED_SQL, SEARCHED_SQL, SEARCHED, "1")
    all_false = eval_case_state(conn, SEARCHED_SQL, SEARCHED_SQL, SEARCHED, "2")
    vote = {"resolved": True, "agreement": "majority", "group_value": "known_manufacturer"}
    assert LIVE_GROUP_POLICY == "unknown_else_escape"
    assert FROZEN_GROUP_POLICY["all_else_escape"] == "diagnostic_only"
    assert accept_live_materialize(unknown, vote)
    assert accept_live_materialize(all_false, vote) is False
    assert all_else_escape(all_false, vote)
    conn.close()


def test_empty_sidecar_matches_incumbent(tmp_path: Path) -> None:
    dest = _file_db(tmp_path)
    queries = [{"query_id": "q", "sql": SEARCHED_SQL}]
    statements = {"q": SEARCHED_SQL}
    empty = apply_live_group_policy(dest, queries, [], [])
    assert empty["n_attempted"] == 0
    assert empty["n_materialized"] == 0
    assert group_bags(dest, statements, [], site_local=True) == official_bags(dest, statements, [])
    exprs = extract_group_expressions(SEARCHED_SQL)
    conn = sqlite3.connect(str(dest))
    assert list(conn.execute(SEARCHED_SQL)) == list(conn.execute(rewrite_group_sql(SEARCHED_SQL, exprs, site_id="q")))
    conn.close()


def test_compile_has_no_dataset_or_query_allowlists() -> None:
    expr = compile_group_expr("g", SEARCHED)
    assert expr.eligible
    assert "known_manufacturer" in expr.allowed
    widget = compile_group_expr(
        "g",
        "CASE WHEN color <> '' THEN 'known_color' ELSE 'color_unknown' END",
    )
    assert widget.eligible
    root = Path(__file__).resolve().parents[1] / "core"
    forbidden = (
        "queries_for",
        "gold_name",
        "med_agg",
        "legal_",
        "finan_",
        '"Med"',
        '"Legal"',
        '"Finan"',
    )
    for name in ("query_group.py", "group_case_escape.py"):
        text = (root / name).read_text()
        for token in forbidden:
            assert token not in text, f"{token} in {name}"


def test_materialize_does_not_use_gold_or_scorer() -> None:
    root = Path(__file__).resolve().parents[1] / "core"
    for name in ("query_group.py", "group_case_escape.py", "group_consensus.py"):
        text = (root / name).read_text()
        assert "load_ground_truth" not in text
        assert "score_with_rewrites" not in text
        assert "gold_name" not in text
    source = apply_live_group_policy.__code__.co_names
    assert "all_else_escape" not in source
    assert "unknown_else_escape" not in source or "inspect_votes" in source


def test_live_policy_writes_are_query_local(tmp_path: Path) -> None:
    dest = _file_db(tmp_path)
    conn = sqlite3.connect(str(dest))
    state = eval_case_state(conn, SEARCHED_SQL, SEARCHED_SQL, SEARCHED, "1")
    conn.close()
    assert state["selected"] == "ELSE"
    expr_id = extract_group_expressions(SEARCHED_SQL)[0].expr_id
    vote = {
        "query_id": "site_q",
        "expr_id": expr_id,
        "witness_key": "1",
        "group_value": "known_manufacturer",
        "old_label": "manufacturer_unknown",
        "resolved": True,
        "agreement": "majority",
        "direct_decision": "known_manufacturer",
        "branch_decision": "known_manufacturer",
        "raw": {"direct": {"label": "known_manufacturer"}, "branch": [{"truth": "unknown"}]},
    }
    queries = [{"query_id": "site_q", "sql": SEARCHED_SQL}, {"query_id": "other_q", "sql": SEARCHED_SQL}]
    report = apply_live_group_policy(dest, queries, [], [vote])
    bags = group_bags(dest, {"site_q": SEARCHED_SQL, "other_q": SEARCHED_SQL}, [], site_local=True)
    before = official_bags(dest, {"site_q": SEARCHED_SQL, "other_q": SEARCHED_SQL}, [])
    assert report["n_isolation_fail"] == 0
    assert bags["other_q"] == before["other_q"]
    assert bags["site_q"] != before["site_q"]
