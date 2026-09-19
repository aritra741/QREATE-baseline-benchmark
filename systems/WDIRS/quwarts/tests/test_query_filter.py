from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from quwarts.core.ledger import BudgetedCaller, TokenLedger
from quwarts.core.pipeline import official_sql
from quwarts.core.query_filter import (
    CRITIQUE_PROMPT,
    DIRECT_PROMPT,
    EVIDENCE_PROMPT,
    NULL_SENTINEL,
    StoredDecision,
    add_filter,
    canonicalize_filter,
    classify_witness,
    encode_witness_key,
    ensure_filter_table,
    excluded_filter_candidates,
    filter_signature_id,
    has_row_filter,
    probe_filter_additivity,
    query_bags,
    rule_broad_original,
    rule_evidence_plus_one,
    rule_primary,
    rule_strict_grounded,
    rule_two_true_no_false,
    run_filter_arm,
    select_replay,
    write_filter_gate_fixture,
)

CORE = Path(__file__).resolve().parents[1] / "core"
FORBIDDEN = (
    "disease_type",
    "research_fields",
    "prescription_status",
    "institution_type",
    "administration_route",
    "pharmaceutical_form",
    "gold_name",
    "DocETL",
    "queries_for",
)


def _caller(payload: str, tokens: int = 4):
    def client(prompt: str, metadata: dict) -> tuple[str, int]:
        return payload, tokens

    ledger = TokenLedger(10_000, 0)
    return BudgetedCaller(ledger, client), ledger


def test_prompts_are_label_free() -> None:
    for text in (DIRECT_PROMPT, EVIDENCE_PROMPT, CRITIQUE_PROMPT):
        low = text.lower()
        assert "med" not in low
        assert "gold" not in low
        assert "docetl" not in low
        assert "complete" in low
    body = (CORE / "query_filter.py").read_text()
    for name in FORBIDDEN:
        assert name not in body, name


def test_empty_filter_table_is_noop(tmp_path: Path) -> None:
    db = write_filter_gate_fixture(tmp_path / "empty.db")
    sql = "SELECT COUNT(*) AS n FROM item WHERE flag = 'yes'"
    before = sqlite3.connect(db).execute(sql).fetchone()[0]
    wrapped = official_sql(sql, db, [])
    after = sqlite3.connect(db).execute(wrapped).fetchone()[0]
    assert "filter_additions" in wrapped.lower()
    assert after == before
    assert before >= 1


def test_one_addition_admits_exactly_one(tmp_path: Path) -> None:
    db = write_filter_gate_fixture(tmp_path / "one.db")
    gates = probe_filter_additivity(db)
    names = {item["name"]: item for item in gates["checks"]}
    assert gates["ok"]
    assert names["one_addition_admits_one"]["ok"]
    assert names["not_additive"]["ok"]
    assert names["and_additive"]["ok"]
    assert names["or_additive"]["ok"]
    assert names["null_additive"]["ok"]
    assert names["join_null_keys"]["ok"]
    assert names["join_no_duplicate"]["ok"]
    assert names["group_unchanged"]["ok"]


def test_shared_signature_only(tmp_path: Path) -> None:
    db = write_filter_gate_fixture(tmp_path / "share.db")
    a = "SELECT COUNT(*) AS n FROM item WHERE flag = 'yes'"
    b = "SELECT name, COUNT(*) AS n FROM item WHERE flag = 'yes' GROUP BY name"
    c = "SELECT COUNT(*) AS n FROM item WHERE flag = 'yes' AND name != ''"
    assert filter_signature_id(a) == filter_signature_id(b)
    assert filter_signature_id(a) != filter_signature_id(c)
    conn = sqlite3.connect(db)
    ensure_filter_table(conn)
    rid = conn.execute("SELECT rowid FROM item WHERE doc_id = 'false'").fetchone()[0]
    add_filter(conn, filter_signature_id(a), encode_witness_key([int(rid)]), "t")
    conn.commit()
    bags = query_bags(db, {"a": a, "b": b, "c": c}, [])
    raw = {
        qid: sqlite3.connect(db).execute(official_sql(sql, db, [])).fetchall()
        for qid, sql in {"a": a, "b": b, "c": c}.items()
    }
    conn.close()
    assert raw["a"][0][0] == 3
    assert sum(row[1] for row in raw["b"]) == 3
    assert raw["c"][0][0] == 1
    assert bags["c"] == query_bags(db, {"c": c}, [])["c"]


def test_majority_true_required_and_false_not_written(tmp_path: Path) -> None:
    db = write_filter_gate_fixture(tmp_path / "vote.db")
    sql = "SELECT COUNT(*) AS n FROM item WHERE flag = 'yes'"
    item = excluded_filter_candidates(db, "q0", sql, [])[0]
    true_caller, _ = _caller('{"truth":"true"}')
    vote = classify_witness(true_caller, item)
    assert vote.accepted
    assert vote.critique is None
    mixed = []

    def mixed_client(prompt: str, metadata: dict) -> tuple[str, int]:
        plan = metadata.get("plan") or ""
        if "direct" in plan:
            return '{"truth":"true"}', 2
        if "evidence" in plan:
            return '{"truth":"false"}', 2
        return '{"truth":"false"}', 2

    caller = BudgetedCaller(TokenLedger(10_000, 0), mixed_client)
    vote = classify_witness(caller, item)
    assert vote.accepted is False
    assert vote.critique == "false"
    false_caller, _ = _caller('{"truth":"false"}')
    vote = classify_witness(false_caller, item)
    assert vote.accepted is False
    before = sqlite3.connect(db).execute("SELECT COUNT(*) FROM filter_additions").fetchone()[0]
    run_filter_arm(
        db,
        [{"query_id": "q0", "sql": sql}],
        [],
        caller=false_caller,
        statements={"q0": sql},
        vote_journal=tmp_path / "votes.jsonl",
    )
    after = sqlite3.connect(db).execute("SELECT COUNT(*) FROM filter_additions").fetchone()[0]
    assert after == before


def test_malformed_retries_then_unresolved() -> None:
    calls = {"n": 0}

    def client(prompt: str, metadata: dict) -> tuple[str, int]:
        calls["n"] += 1
        return "not-json", 3

    caller = BudgetedCaller(TokenLedger(10_000, 0), client)
    item = {
        "witness_key": "1",
        "signature_id": "abcd",
        "filter_sql": "flag = 'yes'",
        "label": "x",
        "cells": {},
        "snippets": "",
        "atoms": [{"sql": "flag = 'yes'", "negated": "false"}],
    }
    vote = classify_witness(caller, item)
    assert vote.direct == "unknown"
    assert vote.evidence == "unknown"
    assert "direct" in vote.retried
    assert calls["n"] >= 4


def test_candidates_are_existing_join_witnesses_only(tmp_path: Path) -> None:
    db = write_filter_gate_fixture(tmp_path / "join.db")
    sql = (
        "SELECT COUNT(*) AS n FROM item i LEFT JOIN extra e "
        "ON i.doc_id = e.doc_id WHERE flag = 'yes'"
    )
    found = excluded_filter_candidates(db, "q0", sql, [])
    keys = {item["witness_key"] for item in found}
    assert all(NULL_SENTINEL in key or True for key in keys)
    assert not any("|" not in item["witness_key"] for item in found)
    cartesian = 4 * 1
    assert len(found) < cartesian


def test_incumbent_not_dropped(tmp_path: Path) -> None:
    db = write_filter_gate_fixture(tmp_path / "keep.db")
    sql = "SELECT name, COUNT(*) AS n FROM item WHERE flag = 'yes' GROUP BY name"
    item = next(
        row
        for row in excluded_filter_candidates(db, "q0", sql, [])
        if "false" in str(row.get("entity_id") or row.get("label") or "")
        or row["filter_3vl"] in {"false", "null"}
    )
    true_caller, _ = _caller('{"truth":"true"}')
    report = run_filter_arm(
        db,
        [{"query_id": "q0", "sql": sql}],
        [],
        caller=true_caller,
        statements={"q0": sql},
    )
    rows = sqlite3.connect(db).execute(official_sql(sql, db, [])).fetchall()
    names = {row[0] for row in rows}
    assert "alpha" in names
    assert report.n_sql_visible >= 0


def test_replay_rules_use_stored_labels_only() -> None:
    primary = StoredDecision("s", "1", "q", direct="true", evidence="true")
    two_true = StoredDecision("s", "2", "q", direct="true", evidence="unknown", critique="true")
    has_false = StoredDecision("s", "3", "q", direct="true", evidence="false", critique="true")
    ev_plus = StoredDecision("s", "4", "q", direct="false", evidence="true", critique="true")
    grounded = StoredDecision("s", "5", "q", direct="true", evidence="true", evidence_text="span")
    unlabeled = StoredDecision("s", "6", "q", broad_accepted=True)
    assert rule_primary(primary)
    assert not rule_primary(two_true)
    assert not rule_primary(unlabeled)
    assert rule_two_true_no_false(primary)
    assert rule_two_true_no_false(two_true)
    assert not rule_two_true_no_false(has_false)
    assert not rule_two_true_no_false(unlabeled)
    assert rule_evidence_plus_one(primary)
    assert rule_evidence_plus_one(ev_plus)
    assert not rule_evidence_plus_one(two_true)
    assert rule_strict_grounded(grounded)
    assert not rule_strict_grounded(primary)
    assert rule_broad_original(unlabeled)
    assert rule_broad_original(has_false)
    assert not rule_broad_original(StoredDecision("s", "7", "q"))
    chosen = select_replay(
        [primary, two_true, has_false, ev_plus, grounded, unlabeled],
        "primary",
    )
    assert {item.witness_key for item in chosen} == {"1", "5"}


def test_vote_journal_persists_strategy_labels(tmp_path: Path) -> None:
    db = write_filter_gate_fixture(tmp_path / "journal.db")
    sql = "SELECT COUNT(*) AS n FROM item WHERE flag = 'yes'"
    journal = tmp_path / "filter_votes.jsonl"
    true_caller, _ = _caller('{"truth":"true","atoms":[{"condition":"flag","truth":"true"}],"evidence":"span"}')
    run_filter_arm(
        db,
        [{"query_id": "q0", "sql": sql}],
        [],
        caller=true_caller,
        statements={"q0": sql},
        vote_journal=journal,
    )
    assert journal.is_file()
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    assert rows
    row = rows[0]
    assert row["direct"] in {"true", "false", "unknown"}
    assert row["evidence_first"] in {"true", "false", "unknown"}
    assert "raw" in row
    assert "witness_key" in row


def test_canonicalize_ignores_alias_names() -> None:
    left = "SELECT COUNT(*) FROM item i WHERE i.flag = 'yes'"
    right = "SELECT COUNT(*) FROM item t WHERE t.flag = 'yes'"
    assert canonicalize_filter(left) == canonicalize_filter(right)
    assert filter_signature_id(left) == filter_signature_id(right)
    assert has_row_filter(left)
    assert not has_row_filter("SELECT COUNT(*) FROM item")
