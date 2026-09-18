"""Fallback rewrite must match stored A' bags. Uses the real A' artifact."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from collections import Counter
from pathlib import Path

from quwarts.core.pipeline import official_sql
from quwarts.core.signature import audit_workload, enumerate_predicates, rewrite_sql
from quwarts.core.signature_populate import ensure_signature_columns
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import parse_sql
from quwarts.experiments.synthesize_case80 import queries_for

REPO = Path(__file__).resolve().parents[4]
APRIME_DIR = REPO / "results" / "quwarts_med_aprime" / "artifacts" / "databases"
STORED_SHA = "68e88d21fab042e5a2f0efbb29db86d8d7af26570c2b24d968c40ddb71f1bfdd"


def _aprime() -> Path:
    matches = list(APRIME_DIR.glob("*.db"))
    assert matches, f"stored A' artifact missing under {APRIME_DIR}"
    return matches[0]


def _rows(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    try:
        return [tuple(row) for row in conn.execute(sql).fetchall()]
    except sqlite3.Error:
        return []


def test_stored_aprime_artifact_hash() -> None:
    path = _aprime()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == STORED_SHA


def test_all_unresolved_bags_match_stored_aprime() -> None:
    src = _aprime()
    queries = queries_for("Med")
    assert len(queries) == 99
    report = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    dest = src.parent / "_fallback_test.db"
    shutil.copy2(src, dest)
    orig = sqlite3.connect(str(src))
    fb = sqlite3.connect(str(dest))
    ensure_signature_columns(fb, predicates)
    fb.commit()
    try:
        diffs = []
        join_diffs = []
        for row in queries:
            original = row["sql"]
            rewritten = rewrite_sql(original, predicates)
            served = official_sql(original, dest, predicates)
            join_only = official_sql(original, src, predicates=[])
            o = Counter(_rows(orig, original))
            r = Counter(_rows(fb, rewritten))
            s = Counter(_rows(fb, served))
            j = Counter(_rows(orig, join_only))
            if o != r:
                diffs.append(row["query_id"])
            if s != j:
                join_diffs.append(row["query_id"])
        assert diffs == [], diffs
        assert join_diffs == [], join_diffs
    finally:
        orig.close()
        fb.close()
        dest.unlink(missing_ok=True)


def test_rewrite_is_identity_without_replacements() -> None:
    sql = "SELECT COUNT(*) FROM item"
    assert rewrite_sql(sql, []) == sql
    parsed = parse_sql("SELECT 1").sql(dialect="sqlite")
    assert parsed
