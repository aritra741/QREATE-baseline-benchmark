from __future__ import annotations

import sqlite3
from pathlib import Path

from quwarts.core.component_oracle import base_checksums
from quwarts.core.query_group import (
    apply_branch_votes,
    compile_group_expr,
    ensure_group_table,
    extract_group_expressions,
    fill_gold_group_labels,
    group_bags,
    official_bags,
    reaggregate_sql,
    rewrite_group_sql,
    rewrite_sites,
    same_sidecar_rewrite,
    traces_reaggregate_ok,
    wrap_group_sql,
)
from quwarts.core.query_witness import compile_witness_spec


CASE_SQL = (
    "SELECT CASE WHEN LOWER(d.prognosis) LIKE '%high%' THEN 'high' ELSE 'other' END AS g, "
    "COUNT(*) AS n FROM disease d WHERE d.prognosis != '' GROUP BY g"
)


def test_case_is_eligible_plain_column_is_not() -> None:
    exprs = extract_group_expressions(CASE_SQL)
    assert len(exprs) == 1
    assert exprs[0].eligible
    assert "high" in exprs[0].allowed
    assert "other" in exprs[0].allowed
    open_ended = compile_group_expr("g", "d.prognosis")
    assert open_ended.eligible is False
    assert open_ended.reason == "open_ended_projection"


def test_branch_compiler_uses_case_order() -> None:
    expr = extract_group_expressions(CASE_SQL)[0]
    assert apply_branch_votes(expr, ["true"]) == "high"
    assert apply_branch_votes(expr, ["false"]) == "other"
    assert apply_branch_votes(expr, ["unknown"]) == "other"


def test_rewrite_is_identity_when_sidecar_empty(tmp_path: Path) -> None:
    dest = tmp_path / "qw.db"
    conn = sqlite3.connect(str(dest))
    conn.executescript(
        """
        CREATE TABLE disease (doc_id TEXT, id TEXT, prognosis TEXT);
        INSERT INTO disease VALUES ('disease/1.txt', NULL, 'high_mortality'),
                                   ('disease/2.txt', NULL, 'low');
        """
    )
    ensure_group_table(conn)
    conn.commit()
    exprs = extract_group_expressions(CASE_SQL)
    rewritten = rewrite_group_sql(CASE_SQL, exprs)
    assert "group_labels" in rewritten
    assert "resolved" in rewritten
    before = list(conn.execute(CASE_SQL))
    after = list(conn.execute(rewritten))
    assert before == after
    assert traces_reaggregate_ok(conn, rewritten)
    conn.close()


def test_select_and_group_use_same_sidecar() -> None:
    exprs = extract_group_expressions(CASE_SQL)
    sql = (
        "SELECT CASE WHEN LOWER(d.prognosis) LIKE '%high%' THEN 'high' ELSE 'other' END AS g, "
        "COUNT(*) AS n FROM disease d "
        "GROUP BY CASE WHEN LOWER(d.prognosis) LIKE '%high%' THEN 'high' ELSE 'other' END "
        "ORDER BY CASE WHEN LOWER(d.prognosis) LIKE '%high%' THEN 'high' ELSE 'other' END"
    )
    rewritten = rewrite_group_sql(sql, exprs)
    sites = rewrite_sites(sql, exprs)
    clauses = {item["clause"] for item in sites}
    assert "select" in clauses
    assert "group" in clauses
    assert "order" in clauses
    assert same_sidecar_rewrite(sql, exprs)
    assert wrap_group_sql("x", exprs[0].expr_id, "'1'").count("group_labels") >= 2


def test_gold_sidecar_and_poison(tmp_path: Path) -> None:
    dest = tmp_path / "qw.db"
    qw = sqlite3.connect(str(dest))
    qw.executescript(
        """
        CREATE TABLE disease (doc_id TEXT, id TEXT, prognosis TEXT, pharmaceutical_form TEXT);
        INSERT INTO disease VALUES ('disease/1.txt', NULL, 'mild', 'tablet'),
                                   ('disease/2.txt', NULL, 'mild', 'capsule');
        """
    )
    ensure_group_table(qw)
    before = base_checksums(qw)
    qw.commit()
    qw.close()
    gold = sqlite3.connect(":memory:")
    gold.executescript(
        """
        CREATE TABLE disease (id TEXT, prognosis TEXT, pharmaceutical_form TEXT);
        INSERT INTO disease VALUES ('1', 'high_mortality', 'tablet'),
                                   ('2', 'low', 'capsule');
        """
    )
    queries = [{"query_id": "q", "sql": CASE_SQL}]
    filled = fill_gold_group_labels(dest, gold, queries, [])
    assert filled["checksums_ok"]
    conn = sqlite3.connect(str(dest))
    assert base_checksums(conn) == before
    rewritten = rewrite_group_sql(CASE_SQL, extract_group_expressions(CASE_SQL))
    bags = list(conn.execute(rewritten))
    gold.execute("UPDATE disease SET pharmaceutical_form = 'POISONED'")
    gold.commit()
    dest2 = tmp_path / "qw2.db"
    dest2.write_bytes(dest.read_bytes())
    # reset sidecar on dest2
    c2 = sqlite3.connect(str(dest2))
    c2.execute("DELETE FROM group_labels")
    c2.commit()
    c2.close()
    fill_gold_group_labels(dest2, gold, queries, [])
    conn2 = sqlite3.connect(str(dest2))
    bags2 = list(conn2.execute(rewritten))
    assert bags == bags2
    assert traces_reaggregate_ok(conn, rewritten)
    conn.close()
    conn2.close()
    gold.close()
