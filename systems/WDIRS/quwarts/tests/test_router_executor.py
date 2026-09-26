from __future__ import annotations

import sqlite3

from quwarts.core.router.context_probe import FieldSpec
from quwarts.core.router.executor import commit_value, materialize_plan, reads_from_plan
from quwarts.core.router.facility import INCUMBENT
from quwarts.core.router.needs import CANONICAL

from tests.test_router_probes import toy_spec

FIELDS = {"c.verdict": FieldSpec("verdict", "str", ""), "c.hearing_year": FieldSpec("hearing_year", "int", "")}


def plan():
    return {"decisions": [
        {"query_id": "q1", "table": "c", "attribute": "verdict", "provider": "q1"},
        {"query_id": "q2", "table": "c", "attribute": "verdict", "provider": CANONICAL},
        {"query_id": "q1", "table": "c", "attribute": "hearing_year", "provider": CANONICAL},
        {"query_id": "q2", "table": "c", "attribute": "hearing_year", "provider": INCUMBENT},
    ]}


def values():
    docs = [f"{i}.txt" for i in range(1, 9)]
    return {
        ("c", "q1"): {d: {"verdict": "Dismissed"} for d in docs},
        ("c", CANONICAL): {d: {"verdict": "rejected", "hearing_year": "2,008"} for d in docs},
    }


def column(db, attr):
    conn = sqlite3.connect(db)
    out = {row[0]: row[1] for row in conn.execute(f'SELECT doc_id, "{attr}" FROM c')}
    conn.close()
    return out


def test_reads_from_plan_groups_attributes_per_context():
    reads = {(r.table, r.context): r.attributes for r in reads_from_plan(plan())}
    assert reads == {("c", CANONICAL): ("hearing_year", "verdict"), ("c", "q1"): ("verdict",)}


def test_context_split_columns_without_incumbent(tmp_path):
    spec = toy_spec(tmp_path)
    dbs = materialize_plan(spec, plan(), values(), FIELDS, None, tmp_path / "db")
    assert set(column(dbs["q1"]["db"], "verdict").values()) == {"Dismissed"}
    assert set(column(dbs["q2"]["db"], "verdict").values()) == {"rejected"}  # same column, other context
    assert set(column(dbs["q1"]["db"], "hearing_year").values()) == {2008}  # unit-normalized number
    assert set(column(dbs["q2"]["db"], "hearing_year").values()) == {None}  # incumbent (empty)


def test_fill_never_overwrites_incumbent(tmp_path):
    spec = toy_spec(tmp_path)
    inc = tmp_path / "inc.db"
    conn = sqlite3.connect(inc)
    conn.execute("CREATE TABLE c (doc_id TEXT, __entity_id TEXT, verdict TEXT, hearing_year TEXT)")
    conn.executemany("INSERT INTO c VALUES (?,?,?,?)", [(f"{i}.txt", str(i), "Approved" if i == 1 else None, None) for i in range(1, 9)])
    conn.commit()
    conn.close()
    dbs = materialize_plan(spec, plan(), values(), FIELDS, inc, tmp_path / "db")
    col = column(dbs["q1"]["db"], "verdict")
    assert col["1.txt"] == "Approved" and col["2.txt"] == "Dismissed"
    assert dbs["q1"]["blocked"] == 1
    dbs = materialize_plan(spec, plan(), values(), FIELDS, inc, tmp_path / "db2", policy="replace")
    assert column(dbs["q1"]["db"], "verdict")["1.txt"] == "Dismissed" and dbs["q1"]["overwritten"] == 1


def test_commit_value():
    assert commit_value("$1.2 million", FieldSpec("x", "int", "")) == 1_200_000
    assert commit_value("n/a", FieldSpec("x", "int", "")) is None
    assert commit_value(["A", "B"], FieldSpec("x", "multi_str", "")) == "A || B"
