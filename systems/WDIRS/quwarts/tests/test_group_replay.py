from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from quwarts.core.component_oracle import base_checksums
from quwarts.core.group_replay import (
    direct_branch_agree,
    is_sql_null,
    official_row_bags,
    replay_group_rule,
    rule_accepts,
)
from quwarts.core.query_group import ensure_group_table, extract_group_expressions, rewrite_group_sql, wrap_group_sql


CASE_SQL = (
    "SELECT CASE WHEN LOWER(d.prognosis) LIKE '%high%' THEN 'high' ELSE 'other' END AS g, "
    "COUNT(*) AS n FROM disease d WHERE d.prognosis != '' GROUP BY g"
)
EMPTY_SQL = (
    "SELECT CASE WHEN LOWER(d.prognosis) LIKE '%high%' THEN 'high' ELSE 'other' END AS g, "
    "COUNT(*) AS n FROM disease d WHERE d.prognosis = 'missing' GROUP BY g"
)


def _db(tmp_path: Path) -> Path:
    dest = tmp_path / "agent.db"
    conn = sqlite3.connect(str(dest))
    conn.executescript(
        """
        CREATE TABLE disease (doc_id TEXT, id TEXT, prognosis TEXT);
        INSERT INTO disease VALUES ('disease/1.txt', '1', 'high_mortality'),
                                   ('disease/2.txt', '2', 'low');
        """
    )
    conn.commit()
    conn.close()
    return dest


def test_missing_strategy_is_not_agreement() -> None:
    assert direct_branch_agree({"raw": {}, "direct_decision": "high", "branch_decision": "high"}) is False
    assert (
        direct_branch_agree(
            {
                "raw": {"direct": {"label": "high"}, "branch": [{"truth": "true"}]},
                "direct_decision": "High",
                "branch_decision": "high",
            }
        )
        is True
    )
    assert (
        direct_branch_agree(
            {
                "raw": {"direct": {"label": "high"}, "branch": [{"truth": "true"}]},
                "direct_decision": "high",
                "branch_decision": "other",
            }
        )
        is False
    )


def test_empty_only_ignores_nonempty_and_null_rules() -> None:
    vote = {
        "query_id": "empty_q",
        "resolved": True,
        "agreement": "majority",
        "group_value": "high",
        "old_label": None,
        "raw": {"direct": {"label": "high"}, "branch": [{"truth": "true"}]},
        "direct_decision": "high",
        "branch_decision": "other",
    }
    empty = {"empty_q"}
    assert rule_accepts(vote, "empty_only", empty)
    assert rule_accepts({**vote, "query_id": "full_q"}, "empty_only", empty) is False
    assert rule_accepts(vote, "empty_direct_branch", empty) is False
    assert rule_accepts(vote, "empty_nonnull", empty)
    assert rule_accepts({**vote, "group_value": None}, "empty_nonnull", empty) is False
    assert rule_accepts(vote, "fill_null_only", empty)
    assert rule_accepts({**vote, "old_label": "other"}, "fill_null_only", empty) is False
    assert is_sql_null(None)
    assert is_sql_null("NULL")
    assert not is_sql_null("high")


def test_site_local_write_does_not_change_sibling_query(tmp_path: Path) -> None:
    agent = _db(tmp_path)
    dest = tmp_path / "replay.db"
    dest.write_bytes(agent.read_bytes())
    exprs = extract_group_expressions(CASE_SQL)
    expr_id = exprs[0].expr_id
    statements = {"site_q": CASE_SQL, "full_q": CASE_SQL}
    vote = {
        "query_id": "site_q",
        "expr_id": expr_id,
        "witness_key": "1",
        "group_value": "other",
        "old_label": "high",
        "resolved": True,
        "agreement": "direct_branch",
        "direct_decision": "other",
        "branch_decision": "other",
        "raw": {"direct": {"label": "other"}, "branch": [{"truth": "false"}]},
        "context_hash": "x",
        "token_cost": 0,
    }
    report = replay_group_rule(
        dest,
        statements,
        [],
        [vote],
        "direct_branch_all",
        set(),
        {expr_id: {"site_q", "full_q"}},
    )
    conn = sqlite3.connect(str(dest))
    wrapped_full = rewrite_group_sql(CASE_SQL, exprs, site_id="full_q")
    wrapped_site = rewrite_group_sql(CASE_SQL, exprs, site_id="site_q")
    before_agent = sqlite3.connect(str(agent))
    ensure_group_table(before_agent)
    assert list(conn.execute(wrapped_full)) == list(before_agent.execute(CASE_SQL))
    assert list(conn.execute(wrapped_site)) != list(before_agent.execute(CASE_SQL))
    assert report["n_isolation_fail"] == 0
    assert report["n_sql_visible"] == 1
    conn.close()
    before_agent.close()


def test_site_wrap_filters_provenance() -> None:
    sql = wrap_group_sql("x", "abcd", "'1'", site_id="med_agg20:q13")
    assert "provenance = 'med_agg20:q13'" in sql
    assert "g.resolved" in sql and "= 1" in sql


def test_official_emptiness_is_row_count(tmp_path: Path) -> None:
    agent = _db(tmp_path)
    bags = official_row_bags(agent, {"empty_q": EMPTY_SQL, "full_q": CASE_SQL}, [])
    assert bags["empty_q"]["empty"] is True
    assert bags["empty_q"]["n_rows"] == 0
    assert bags["full_q"]["empty"] is False
    assert bags["full_q"]["n_rows"] > 0
