from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from quwarts.core.ledger import BudgetedCaller, TokenLedger
from quwarts.core.query_residual import (
    DECOMPOSE_PROMPT,
    INCLUDE_PROMPT,
    ConditionDecision,
    EntityDecision,
    apply_addition,
    decision_list,
    excluded_candidates,
    normalize_group,
    probe_edge_additivity,
    propose_direct,
    proposed_union,
    query_bags,
    query_conditions,
    run_residual_arm,
    validate_addition,
    write_gate_fixture,
)
from quwarts.core.join_block import block_join_pairs
from quwarts.core.query_witness import compile_witness_spec
from quwarts.core.signature_views import (
    add_edge,
    ensure_edge_table,
    ensure_group_columns,
    snapshot_edges,
    write_group,
)
from quwarts.core.query_support import (
    SupportRow,
    aprime_support,
    excluded_universe,
    query_shape,
    union_support,
    universe,
)
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_populate import ensure_signature_columns
from quwarts.core.signature_realize import live_predicates

CORE = Path(__file__).resolve().parents[1] / "core"
FORBIDDEN = (
    "disease_type",
    "research_fields",
    "prescription_status",
    "institution_type",
    "administration_route",
    "pharmaceutical_form",
    "queries_for(\"Med\")",
    "gold_name",
    "DocETL",
)


def _preds(sql: str = "SELECT g, COUNT(*) AS n FROM item WHERE form != '' GROUP BY g"):
    report = audit_workload([{"query_id": "q0", "sql": sql}])
    return live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT, g TEXT)")
    conn.execute("INSERT INTO item VALUES ('a', 'tablet', 'has_form')")
    conn.execute("INSERT INTO item VALUES ('b', 'capsule', 'has_form')")
    conn.execute("INSERT INTO item VALUES ('c', '', NULL)")
    conn.commit()
    conn.close()
    return db


def _caller(payload: str, tokens: int = 3):
    def client(prompt: str, metadata: dict) -> tuple[str, int]:
        return payload, tokens

    ledger = TokenLedger(10_000, 0)
    return BudgetedCaller(ledger, client), ledger


def test_prompts_do_not_ask_for_a_support_set() -> None:
    for text in (INCLUDE_PROMPT, DECOMPOSE_PROMPT):
        low = text.lower()
        assert "do not list" in low or "do not emit" in low
        assert "med" not in low
        assert "docetl" not in low
    body = (CORE / "query_residual.py").read_text()
    for name in FORBIDDEN:
        assert name not in body, name
    assert "S_Qwen" not in body


def test_missing_entity_output_is_unknown_not_exclusion() -> None:
    parsed = decision_list('{"decisions": [{"entity_id": "a", "include": "true", "group": "x"}]}')
    assert [row["entity_id"] for row in parsed] == ["a"]
    assert decision_list("") == []
    assert decision_list("not json") == []


def test_union_keeps_incumbent_and_adds() -> None:
    left = [SupportRow("a", 1, "true", {"g": "x"}), SupportRow("b", 2, "true", {"g": "y"})]
    extra = [SupportRow("c", 3, "true", {"g": "z"}), SupportRow("a", 1, "true", {"g": "other"})]
    merged = union_support(left, extra)
    ids = [row.entity_id for row in merged]
    assert ids == ["a", "b", "c"]
    assert merged[0].group_key == {"g": "x"}


def test_excluded_universe_drops_incumbent_only() -> None:
    entities = [{"entity_id": "a"}, {"entity_id": "b"}, {"entity_id": "c"}]
    support = [SupportRow("a", 1, "true", {}), SupportRow("b", 2, "false", {})]
    assert [row["entity_id"] for row in excluded_universe(entities, support)] == ["b", "c"]


def test_residual_cannot_drop_or_reassign_incumbent(tmp_path: Path) -> None:
    db = _db(tmp_path)
    sql = "SELECT g, COUNT(*) AS n FROM item WHERE form != '' GROUP BY g"
    shape = query_shape("q0", sql)
    preds = _preds(sql)
    conn = sqlite3.connect(db)
    ensure_signature_columns(conn, preds)
    conn.commit()
    entities = universe(db, shape)
    rid_map = {item["rowid"]: item["entity_id"] for item in entities}
    before = aprime_support(db, shape, preds, rid_map)
    before_ids = {row.entity_id for row in before if row.included == "true"}
    assert before_ids == {"a", "b"}
    reject = EntityDecision("a", 1, "true", "other", source="direct")
    assert apply_addition(conn, db, entities[0], reject, shape, preds, {1, 2}) is False
    wipe = '{"decisions":[{"entity_id":"a","include":"false","group":"x"},{"entity_id":"b","include":"false","group":"x"},{"entity_id":"c","include":"false","group":"x"}]}'
    caller, _ = _caller(wipe)
    run_residual_arm(db, [{"query_id": "q0", "sql": sql}], preds, caller=caller)
    after = aprime_support(db, shape, preds, rid_map)
    after_ids = {row.entity_id for row in after if row.included == "true"}
    assert before_ids <= after_ids
    groups = {row.entity_id: row.group_key for row in after if row.included == "true"}
    assert groups["a"] == next(row.group_key for row in before if row.entity_id == "a")
    conn.close()


def test_new_group_requires_two_strategies() -> None:
    shape = query_shape("q0", "SELECT g, COUNT(*) AS n FROM item WHERE form != '' GROUP BY g")
    preds = _preds(shape.sql)
    conditions = query_conditions(shape, preds)
    entity = {"entity_id": "c", "rowid": 3, "label": "c", "cells": {"form": ""}, "document": "form: tablet"}
    one = {
        "direct": EntityDecision("c", 3, "true", "new_band", source="direct"),
    }
    caller, _ = _caller('{"truth": true}')
    assert validate_addition(caller, entity, shape, conditions, preds, one, {"has_form"}) is None
    two = {
        "direct": EntityDecision("c", 3, "true", "New_Band", source="direct"),
        "decompose": EntityDecision("c", 3, "true", "new_band", source="decompose"),
    }
    accepted = validate_addition(caller, entity, shape, conditions, preds, two, {"has_form"})
    assert accepted is not None
    assert normalize_group(accepted.group) == "new_band"


def test_direct_does_not_replace_support_set() -> None:
    shape = query_shape("q0", "SELECT COUNT(*) AS n FROM item WHERE form != ''")
    entities = [
        {"entity_id": "c", "rowid": 3, "label": "c", "cells": {"form": ""}, "document": "tablet"},
    ]
    caller, _ = _caller('{"decisions":[{"entity_id":"c","include":"true","group":"unknown"}]}')
    found = propose_direct(caller, shape, entities, [])
    assert found["c"].include == "true"
    empty, _ = _caller("{}")
    missing = propose_direct(empty, shape, entities, [])
    assert missing["c"].include == "unknown"


def test_proposed_union_is_positive_only() -> None:
    plans = {
        "direct": {"c": EntityDecision("c", 3, "true", "x"), "d": EntityDecision("d", 4, "false", "x")},
        "decompose": {"c": EntityDecision("c", 3, "unknown", "x"), "e": EntityDecision("e", 5, "true", "x")},
    }
    union = proposed_union(plans)
    assert set(union) == {"c", "e"}
    assert set(union["c"]) == {"direct"}


def test_witness_kinds_from_ast() -> None:
    row = compile_witness_spec("q0", "SELECT g, COUNT(*) AS n FROM item GROUP BY g")
    assert "row" in row.kinds and "grouped" in row.kinds
    counted = compile_witness_spec("q1", "SELECT COUNT(form) AS n FROM item")
    assert "counted_value" in counted.kinds
    distinct = compile_witness_spec("q2", "SELECT COUNT(DISTINCT form) AS n FROM item")
    assert "distinct" in distinct.kinds
    joined = compile_witness_spec(
        "q3",
        "SELECT COUNT(DISTINCT i.doc_id) AS n FROM item i JOIN extra e ON i.doc_id = e.doc_id "
        "OR '|' || i.form || '|' LIKE '%|' || e.doc_id || '|%'",
    )
    assert "join_tuple" in joined.kinds
    assert "entity_edge" in joined.kinds
    assert joined.joins


def test_join_edge_is_query_observable(tmp_path: Path) -> None:
    db = tmp_path / "j.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT)")
    conn.execute("CREATE TABLE extra (doc_id TEXT)")
    conn.execute("INSERT INTO item VALUES ('a', 'tablet')")
    conn.execute("INSERT INTO extra VALUES ('a')")
    conn.execute("INSERT INTO extra VALUES ('z')")
    ensure_edge_table(conn)
    conn.commit()
    sql = "SELECT COUNT(*) AS n FROM item i JOIN extra e ON i.doc_id = e.doc_id"
    spec = compile_witness_spec("q0", sql)
    before = snapshot_edges(conn)
    join = spec.joins[0]
    left_rid, right_rid = (2, 1) if join.left_table == "extra" else (1, 2)
    add_edge(conn, join.join_id, left_rid, right_rid, provenance="q0")
    conn.commit()
    assert snapshot_edges(conn) > before
    add_edge(conn, join.join_id, left_rid, right_rid, provenance="again")
    assert snapshot_edges(conn) > before
    from quwarts.core.pipeline import official_sql

    n = conn.execute(official_sql(sql, db, [])).fetchone()[0]
    assert n == 2
    conn.close()


def test_empty_edges_do_not_remove_on_support(tmp_path: Path) -> None:
    db = tmp_path / "e.db"
    write_gate_fixture(db)
    sql = "SELECT COUNT(*) AS n FROM item i JOIN extra e ON i.doc_id = e.doc_id"
    from quwarts.core.pipeline import official_sql

    conn = sqlite3.connect(db)
    assert conn.execute(sql).fetchone()[0] == 1
    assert conn.execute(official_sql(sql, db, [])).fetchone()[0] == 1
    conn.close()


def test_matching_edge_does_not_duplicate(tmp_path: Path) -> None:
    db = tmp_path / "d.db"
    write_gate_fixture(db)
    sql = "SELECT COUNT(*) AS n FROM item i JOIN extra e ON i.doc_id = e.doc_id"
    spec = compile_witness_spec("q0", sql)
    conn = sqlite3.connect(db)
    add_edge(conn, spec.joins[0].join_id, 1, 1, provenance="q0")
    conn.commit()
    from quwarts.core.pipeline import official_sql

    assert conn.execute(official_sql(sql, db, [])).fetchone()[0] == 1
    conn.close()


def test_self_join_rowids_use_aliases(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    write_gate_fixture(db)
    sql = "SELECT COUNT(*) AS n FROM item a JOIN item b ON a.doc_id = b.form"
    spec = compile_witness_spec("q0", sql)
    assert spec.joins[0].left_alias == "a"
    assert spec.joins[0].right_alias == "b"
    conn = sqlite3.connect(db)
    before = conn.execute(sql).fetchone()[0]
    add_edge(conn, spec.joins[0].join_id, 1, 2, provenance="q0")
    conn.commit()
    from quwarts.core.pipeline import official_sql

    after = conn.execute(official_sql(sql, db, [])).fetchone()[0]
    assert after == before + 1
    conn.close()


def test_edge_gates_on_fixture(tmp_path: Path) -> None:
    db = write_gate_fixture(tmp_path / "g.db")
    result = probe_edge_additivity(db, [])
    assert result["ok"], result


def test_join_blocking_is_not_cartesian() -> None:
    sql = (
        "SELECT COUNT(*) FROM item i JOIN extra e ON LOWER(TRIM(i.form)) = LOWER(TRIM(e.doc_id)) "
        "OR '|' || i.form || '|' LIKE '%|' || e.doc_id || '|%'"
    )
    spec = compile_witness_spec("q0", sql)
    left = [
        {"rowid": 1, "table": "item", "cells": {"form": "alpha || beta"}, "label": "a", "document": ""},
        {"rowid": 2, "table": "item", "cells": {"form": ""}, "label": "gamma", "document": "mentions gamma"},
    ]
    right = [
        {"rowid": 1, "table": "extra", "cells": {"doc_id": "beta"}, "label": "b", "document": ""},
        {"rowid": 2, "table": "extra", "cells": {"doc_id": "gamma"}, "label": "g", "document": ""},
        {"rowid": 3, "table": "extra", "cells": {"doc_id": "zzz"}, "label": "z", "document": ""},
    ]
    pairs, reason, signal = block_join_pairs(left, right, spec.joins[0], per_left=2, per_query=4)
    assert reason == ""
    assert signal
    assert len(pairs) < len(left) * len(right)
    assert all(right_row["cells"]["doc_id"] != "zzz" for _l, right_row, _s in pairs)


def test_no_blocking_signal_skips(tmp_path: Path) -> None:
    db = _db(tmp_path)
    sql = "SELECT COUNT(*) AS n FROM item"
    spec = compile_witness_spec("q0", sql)
    support = []
    found = excluded_candidates(db, spec, support, {})
    assert found.stats is not None
    assert found.stats.skip_reason == "" or not spec.joins
    sql = "SELECT COUNT(*) AS n FROM item i JOIN item j ON 1 = 1"
    spec = compile_witness_spec("q1", sql)
    found = excluded_candidates(db, spec, support, {})
    assert found.rows == []
    assert found.stats and found.stats.skip_reason == "no useful blocking signal"


def test_group_signature_does_not_write_base_column(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT)")
    conn.execute("INSERT INTO item VALUES ('a', 'tablet')")
    conn.execute("INSERT INTO item VALUES ('c', '')")
    conn.commit()
    sql = "SELECT CASE WHEN form != '' THEN 'has' ELSE 'empty' END AS g, COUNT(*) AS n FROM item GROUP BY g"
    spec = compile_witness_spec("q0", sql)
    ensure_group_columns(conn, [spec])
    write_group(conn, "item", 2, spec.group_sql[0], "has", incumbent_rowids={1})
    conn.commit()
    form = conn.execute("SELECT form FROM item WHERE doc_id = 'c'").fetchone()[0]
    assert form == ""
    from quwarts.core.pipeline import official_sql

    rows = conn.execute(official_sql(sql, db, [])).fetchall()
    assert any(row[0] == "has" for row in rows)
    conn.close()


def test_unrelated_query_bag_unchanged(tmp_path: Path) -> None:
    db = tmp_path / "u.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT, note TEXT)")
    conn.execute("INSERT INTO item VALUES ('a', 'tablet', 'x')")
    conn.execute("INSERT INTO item VALUES ('c', '', '')")
    conn.commit()
    conn.close()
    statements = {
        "q0": "SELECT COUNT(*) AS n FROM item WHERE form != ''",
        "q1": "SELECT COUNT(*) AS n FROM item WHERE note != ''",
    }
    preds = _preds(statements["q0"])
    before = query_bags(db, statements, preds)
    shape = query_shape("q0", statements["q0"])
    conn = sqlite3.connect(db)
    ensure_signature_columns(conn, preds)
    conn.commit()
    decision = EntityDecision(
        "c",
        2,
        "true",
        "",
        conditions=[ConditionDecision(preds[0].pred_id, "true", "", "filter")],
        source="validated",
    )
    apply_addition(conn, db, {"entity_id": "c", "rowid": 2, "rowids": {"item": 2}}, decision, shape, preds, {1})
    conn.commit()
    conn.close()
    after = query_bags(db, statements, preds)
    assert after["q1"] == before["q1"]


def test_ineffective_addition_rolls_back(tmp_path: Path) -> None:
    db = _db(tmp_path)
    sql = "SELECT COUNT(*) AS n FROM item WHERE form != ''"
    shape = query_shape("q0", sql)
    preds = _preds(sql)
    conn = sqlite3.connect(db)
    ensure_signature_columns(conn, preds)
    before = conn.execute("SELECT form FROM item WHERE doc_id = 'c'").fetchone()[0]
    decision = EntityDecision("c", 3, "true", "", source="validated")
    assert apply_addition(conn, db, {"entity_id": "c", "rowid": 3, "rowids": {"item": 3}}, decision, shape, preds, {1, 2}) is False
    after = conn.execute("SELECT form FROM item WHERE doc_id = 'c'").fetchone()[0]
    assert after == before
    conn.close()


def test_join_ids_include_aliases_and_on_ast() -> None:
    from quwarts.core.query_witness import join_signature_id

    self_ab = join_signature_id("item", "item", "a", "b", "a.doc_id = b.form")
    self_ba = join_signature_id("item", "item", "b", "a", "b.doc_id = a.form")
    assert self_ab != self_ba
    left = join_signature_id("item", "extra", "i", "e", "i.doc_id = e.doc_id")
    again = join_signature_id("item", "extra", "i", "e", "i.doc_id = e.doc_id")
    other_alias = join_signature_id("item", "extra", "x", "y", "x.doc_id = y.doc_id")
    other_on = join_signature_id("item", "extra", "i", "e", "i.form = e.doc_id")
    assert left == again
    assert left != other_alias
    assert left != other_on
    first = compile_witness_spec(
        "q0",
        "SELECT COUNT(*) FROM item i JOIN extra e ON i.doc_id = e.doc_id "
        "JOIN extra e2 ON i.form = e2.doc_id",
    )
    assert len(first.joins) == 2
    assert first.joins[0].join_id != first.joins[1].join_id


def test_multi_relation_group_fail_closed(tmp_path: Path) -> None:
    from quwarts.core.query_witness import group_owner_table, group_sig_names
    from quwarts.core.signature_views import rewrite_group_sql

    db = tmp_path / "m.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT)")
    conn.execute("CREATE TABLE extra (doc_id TEXT)")
    conn.execute("INSERT INTO item VALUES ('a', 'tablet')")
    conn.execute("INSERT INTO extra VALUES ('a')")
    conn.commit()
    sql = (
        "SELECT CASE WHEN i.form != '' THEN e.doc_id ELSE i.doc_id END AS g, "
        "COUNT(*) AS n FROM item i JOIN extra e ON i.doc_id = e.doc_id GROUP BY g"
    )
    spec = compile_witness_spec("q0", sql)
    assert group_owner_table(spec.group_sql[0], spec) is None
    added = ensure_group_columns(conn, [spec])
    assert added == []
    sig, resolved = group_sig_names(spec.group_sql[0])
    item_cols = {row[1] for row in conn.execute("PRAGMA table_info(item)")}
    extra_cols = {row[1] for row in conn.execute("PRAGMA table_info(extra)")}
    assert sig not in item_cols and resolved not in item_cols
    assert sig not in extra_cols and resolved not in extra_cols
    assert rewrite_group_sql(sql, db) == sql
    shape = query_shape("q0", sql)
    decision = EntityDecision("pair", 1, "true", "g1", source="validated")
    reasons: list[str] = []
    assert (
        apply_addition(
            conn,
            db,
            {"entity_id": "pair", "rowid": 1, "rowids": {"item": 1, "extra": 1}},
            decision,
            shape,
            [],
            set(),
            spec=spec,
            reasons=reasons,
        )
        is False
    )
    assert any("multi-relation group fail-closed" in item for item in reasons)
    conn.close()
