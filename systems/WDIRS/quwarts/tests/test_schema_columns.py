from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from quwarts.core.pipeline import official_sql
from quwarts.core.schema_columns import (
    MissingColumnError,
    assert_queries_execute,
    ensure_and_assert,
    ensure_referenced_columns,
    referenced_columns,
)
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_populate import apply_live_signatures, ensure_signature_columns
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.synthesize_case80 import queries_for

REPO = Path(__file__).resolve().parents[4]
APRIME = REPO / "results" / "quwarts_med_aprime" / "artifacts" / "databases"
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


def test_referenced_attribute_becomes_typed_column(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT)")
    conn.execute("INSERT INTO item VALUES ('a', 'tablet')")
    conn.commit()
    sqls = {"q0": "SELECT COUNT(*) AS n FROM item WHERE note != '' AND mass > 0"}
    cols = referenced_columns(sqls)
    names = {(item.table, item.column, item.sql_type) for item in cols}
    assert ("item", "note", "TEXT") in names
    assert ("item", "mass", "REAL") in names
    added = ensure_referenced_columns(conn, sqls)
    assert ("item", "note", "TEXT") in added
    assert ("item", "mass", "REAL") in added
    have = {row[1] for row in conn.execute("PRAGMA table_info(item)")}
    assert "note" in have and "mass" in have
    assert conn.execute("SELECT COUNT(*) FROM item WHERE note != ''").fetchone()[0] == 0
    assert_queries_execute(conn, sqls)
    conn.close()


def test_missing_column_is_asserted(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT)")
    conn.commit()
    try:
        assert_queries_execute(conn, {"q0": "SELECT missing FROM item"})
        raise AssertionError("expected MissingColumnError")
    except MissingColumnError:
        pass
    finally:
        conn.close()


def test_select_aliases_are_not_physical_columns() -> None:
    sqls = {
        "q0": "SELECT CASE WHEN form != '' THEN 'has' ELSE 'empty' END AS band, COUNT(*) FROM item GROUP BY band"
    }
    names = {item.column for item in referenced_columns(sqls)}
    assert "form" in names
    assert "band" not in names


def test_apply_live_signatures_adds_missing_source_column(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT)")
    conn.execute("INSERT INTO item VALUES ('a', 'tablet')")
    conn.commit()
    conn.close()
    statements = {"q0": "SELECT COUNT(*) FROM item WHERE note != ''"}
    apply_live_signatures([db], statements, documents=None, caller=None)
    have = {row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(item)")}
    assert "note" in have


def test_aprime_rewritten_queries_have_no_missing_columns(tmp_path: Path) -> None:
    matches = list(APRIME.glob("*.db"))
    assert matches, f"stored A' artifact missing under {APRIME}"
    dest = tmp_path / "aprime.db"
    shutil.copy2(matches[0], dest)
    queries = queries_for("Med")
    statements = {row["query_id"]: row["sql"] for row in queries}
    report = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    conn = sqlite3.connect(dest)
    try:
        ensure_referenced_columns(conn, statements)
        ensure_signature_columns(conn, predicates)
        conn.commit()
        rewritten = {row["query_id"]: official_sql(row["sql"], dest, predicates) for row in queries}
        assert_queries_execute(conn, rewritten)
        q17 = next(row for row in queries if row["query_id"].endswith(":q17") and "unsuitable_population" in row["sql"])
        conn.execute(official_sql(q17["sql"], dest, predicates))
    finally:
        conn.close()


def test_schema_columns_module_is_generic() -> None:
    body = (CORE / "schema_columns.py").read_text()
    for name in FORBIDDEN:
        assert name not in body, name
    assert "unsuitable_population" not in body
