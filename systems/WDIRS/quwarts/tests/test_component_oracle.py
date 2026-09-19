"""Isolation gates for query-local component oracles. No gold-column overlay."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from quwarts.core.component_oracle import (
    apply_component_sql,
    base_checksums,
    ensure_oracle_tables,
    sidecar_counts,
    table_schemas,
    uses_component,
    write_set_ok,
)
from quwarts.core.query_witness import compile_witness_spec
from quwarts.eval.component_oracles import _bags, _fetch, _norm_bag, populate

POISON = ("prognosis", "pharmaceutical_form", "administration_route")
UNRELATED = {
    "base_row": POISON,
    "filter": POISON,
    "join": POISON,
    "group": ("pharmaceutical_form", "administration_route"),
    "presence": POISON,
    "distinct": ("pharmaceutical_form", "administration_route"),
}

QUERIES = [
    {
        "query_id": "q_filter",
        "sql": "SELECT COUNT(*) AS n FROM drug dr WHERE dr.generic_name = 'alpha'",
    },
    {
        "query_id": "q_join",
        "sql": (
            "SELECT COUNT(*) AS n FROM drug dr JOIN disease d "
            "ON dr.disease_name = d.disease_name"
        ),
    },
    {
        "query_id": "q_group",
        "sql": (
            "SELECT CASE WHEN LOWER(d.prognosis) LIKE '%high%' THEN 'high' ELSE 'other' END "
            "AS g, COUNT(*) AS n FROM disease d GROUP BY g"
        ),
    },
    {
        "query_id": "q_presence",
        "sql": "SELECT COUNT(dr.generic_name) AS n FROM drug dr",
    },
    {
        "query_id": "q_distinct",
        "sql": (
            "SELECT COUNT(DISTINCT CASE WHEN dr.prognosis = 'good' THEN dr.id END) AS n "
            "FROM drug dr"
        ),
    },
    {
        "query_id": "q_base",
        "sql": "SELECT COUNT(*) AS n FROM drug dr",
    },
]


def _build(tmp: Path) -> tuple[Path, sqlite3.Connection]:
    dest = tmp / "qw.db"
    qw = sqlite3.connect(str(dest))
    qw.executescript(
        """
        CREATE TABLE drug (
          doc_id TEXT, id TEXT, generic_name TEXT, disease_name TEXT,
          prognosis TEXT, pharmaceutical_form TEXT, administration_route TEXT
        );
        CREATE TABLE disease (
          doc_id TEXT, id TEXT, disease_name TEXT, prognosis TEXT,
          pharmaceutical_form TEXT, administration_route TEXT
        );
        INSERT INTO drug VALUES
          ('drug/1.txt', NULL, 'alpha', 'flu', 'good', 'tablet', 'oral'),
          ('drug/2.txt', NULL, 'beta', 'flu', 'bad', 'capsule', 'iv');
        INSERT INTO disease VALUES
          ('disease/10.txt', NULL, 'flu', 'high', 'x', 'y'),
          ('disease/11.txt', NULL, 'cold', 'low', 'x', 'y');
        """
    )
    qw.commit()
    gold = sqlite3.connect(":memory:")
    gold.executescript(
        """
        CREATE TABLE drug (
          id TEXT, generic_name TEXT, disease_name TEXT,
          prognosis TEXT, pharmaceutical_form TEXT, administration_route TEXT
        );
        CREATE TABLE disease (
          id TEXT, disease_name TEXT, prognosis TEXT,
          pharmaceutical_form TEXT, administration_route TEXT
        );
        INSERT INTO drug VALUES
          ('1', 'alpha', 'flu', 'good', 'tablet', 'oral'),
          ('2', 'gamma', 'flu', 'good', 'tablet', 'oral'),
          ('3', 'delta', 'cold', 'bad', 'syrup', 'oral');
        INSERT INTO disease VALUES
          ('10', 'flu', 'high_mortality', 'x', 'y'),
          ('12', 'measles', 'low', 'x', 'y');
        """
    )
    gold.commit()
    return dest, gold


def _poison(gold: sqlite3.Connection, columns: tuple[str, ...] = POISON) -> None:
    for table in ("drug", "disease"):
        cols = {row[1] for row in gold.execute(f'PRAGMA table_info("{table}")')}
        for col in columns:
            if col in cols:
                gold.execute(f'UPDATE "{table}" SET "{col}" = "POISONED"')
    gold.commit()


def test_uses_component_matches_ast() -> None:
    assert uses_component(QUERIES[0]["sql"], "filter")
    assert not uses_component(QUERIES[0]["sql"], "join")
    assert uses_component(QUERIES[1]["sql"], "join")
    assert uses_component(QUERIES[2]["sql"], "group")
    assert uses_component(QUERIES[3]["sql"], "presence")
    assert uses_component(QUERIES[4]["sql"], "distinct")
    assert uses_component(QUERIES[5]["sql"], "base_row")


def test_poisoned_gold_columns_do_not_change_component_bags(tmp_path: Path) -> None:
    dest, gold = _build(tmp_path)
    qw = sqlite3.connect(str(dest))
    before = {row["query_id"]: row["sql"] for row in QUERIES}
    try:
        for component in ("base_row", "filter", "join", "group", "presence", "distinct"):
            copy = tmp_path / f"{component}.db"
            copy.write_bytes(dest.read_bytes())
            filled = populate(component, copy, gold, QUERIES, [])
            assert filled["gates"]["ok"]
            assert not filled["gates"]["changed_base"]
            allowed = {
                "base_row": "oracle_base",
                "filter": "oracle_filter",
                "join": "oracle_join",
                "group": "oracle_group",
                "presence": "oracle_presence",
                "distinct": "oracle_distinct",
            }[component]
            counts = filled["gates"]["sidecar_counts"]
            extras = [name for name, n in counts.items() if n and name != allowed]
            assert extras == []
            conn = sqlite3.connect(str(copy))
            schemas = table_schemas(conn)
            rewrites = {}
            for row in QUERIES:
                spec = compile_witness_spec(row["query_id"], row["sql"])
                rewrites[row["query_id"]] = apply_component_sql(
                    row["sql"],
                    row["query_id"],
                    component,
                    joins=spec.joins,
                    group_aliases=spec.group_aliases,
                    tables=spec.tables,
                    schemas=schemas,
                )
            clean_bags = _bags(conn, rewrites)
            checksums = base_checksums(conn)
            drug_vals = conn.execute(
                "SELECT prognosis, pharmaceutical_form, administration_route FROM drug ORDER BY rowid"
            ).fetchall()
            conn.close()

            poisoned = tmp_path / f"{component}_poison.db"
            poisoned.write_bytes(dest.read_bytes())
            _poison(gold, UNRELATED[component])
            filled2 = populate(component, poisoned, gold, QUERIES, [])
            conn2 = sqlite3.connect(str(poisoned))
            schemas2 = table_schemas(conn2)
            rewrites2 = {}
            for row in QUERIES:
                spec = compile_witness_spec(row["query_id"], row["sql"])
                rewrites2[row["query_id"]] = apply_component_sql(
                    row["sql"],
                    row["query_id"],
                    component,
                    joins=spec.joins,
                    group_aliases=spec.group_aliases,
                    tables=spec.tables,
                    schemas=schemas2,
                )
            poison_bags = _bags(conn2, rewrites2)
            unused = [
                row["query_id"]
                for row in QUERIES
                if not uses_component(row["sql"], component)
            ]
            unused_rewrites = {qid: before[qid] for qid in unused}
            # unused queries stay bag-identical to the original SQL on the copy
            orig = sqlite3.connect(str(copy))
            for qid in unused:
                assert _norm_bag(_fetch(orig, before[qid])) == _norm_bag(_fetch(conn2, rewrites2[qid]))
            orig.close()
            after_drug = conn2.execute(
                "SELECT prognosis, pharmaceutical_form, administration_route FROM drug ORDER BY rowid"
            ).fetchall()
            assert after_drug == drug_vals
            assert base_checksums(conn2) == checksums
            assert poison_bags == clean_bags
            conn2.close()
            # restore gold for the next component
            gold.execute("DELETE FROM drug")
            gold.execute("DELETE FROM disease")
            gold.executescript(
                """
                INSERT INTO drug VALUES
                  ('1', 'alpha', 'flu', 'good', 'tablet', 'oral'),
                  ('2', 'gamma', 'flu', 'good', 'tablet', 'oral'),
                  ('3', 'delta', 'cold', 'bad', 'syrup', 'oral');
                INSERT INTO disease VALUES
                  ('10', 'flu', 'high_mortality', 'x', 'y'),
                  ('12', 'measles', 'low', 'x', 'y');
                """
            )
            gold.commit()
            assert filled2["gates"]["ok"]
    finally:
        qw.close()
        gold.close()


def test_distinct_does_not_copy_case_inputs(tmp_path: Path) -> None:
    dest, gold = _build(tmp_path)
    filled = populate("distinct", dest, gold, QUERIES, [])
    conn = sqlite3.connect(str(dest))
    try:
        assert write_set_ok(conn, "distinct", filled["checksums"])["ok"]
        assert sidecar_counts(conn)["oracle_distinct"] == filled["gates"]["sidecar_counts"]["oracle_distinct"]
        assert sidecar_counts(conn)["oracle_group"] == 0
        assert sidecar_counts(conn)["oracle_filter"] == 0
        rows = conn.execute("SELECT prognosis, pharmaceutical_form, administration_route FROM drug").fetchall()
        assert rows == [("good", "tablet", "oral"), ("bad", "capsule", "iv")]
        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name='drug'").fetchone()[0]
        assert "POISON" not in str(ddl)
    finally:
        conn.close()
        gold.close()


def test_write_set_abort_on_extra_sidecar(tmp_path: Path) -> None:
    dest, gold = _build(tmp_path)
    conn = sqlite3.connect(str(dest))
    try:
        ensure_oracle_tables(conn)
        before = base_checksums(conn)
        conn.execute(
            "INSERT INTO oracle_filter(query_id, witness_key, admit) VALUES ('q', '1', 1)"
        )
        conn.execute(
            "INSERT INTO oracle_join(query_id, join_id, left_key, right_key, admit) "
            "VALUES ('q', 'j', '1', '2', 1)"
        )
        conn.commit()
        gates = write_set_ok(conn, "filter", before)
        assert gates["ok"] is False
        assert "oracle_join" in gates["extra_sidecars"]
    finally:
        conn.close()
        gold.close()


def test_unused_query_rewrite_is_identity() -> None:
    sql = "SELECT COUNT(*) AS n FROM drug dr"
    spec = compile_witness_spec("q", sql)
    assert apply_component_sql(sql, "q", "filter", tables=spec.tables) == sql
    assert apply_component_sql(sql, "q", "join", joins=spec.joins, tables=spec.tables) == sql
    assert apply_component_sql(sql, "q", "distinct", tables=spec.tables) == sql
