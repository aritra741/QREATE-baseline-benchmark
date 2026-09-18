from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

from quwarts.core.models import SourceDocument
from quwarts.core.pipeline import compile_workload
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_populate import (
    apply_row_operators,
    deterministic_labels,
    populate_nonempty,
    populate_signatures,
)
from quwarts.core.signature_realize import is_membership, is_presence, live_predicates
from quwarts.core.truth import PredicateLabel, merge, merge_atoms


CORE_FILES = [
    Path(__file__).resolve().parents[1] / "core" / name
    for name in (
        "signature.py",
        "signature_populate.py",
        "signature_classify.py",
        "signature_realize.py",
        "truth.py",
    )
]
FORBIDDEN = (
    "disease_type",
    "research_fields",
    "prescription_status",
    "institution_type",
    "administration_route",
    "pharmaceutical_form",
)
REPO = Path(__file__).resolve().parents[3]


def _q(query_id: str, sql: str) -> dict[str, str]:
    return {"query_id": query_id, "sql": sql}


def _presence_membership():
    report = audit_workload(
        [
            _q(
                "q0",
                "SELECT COUNT(*) FROM item WHERE LOWER(form) LIKE '%tab%' AND form != ''",
            )
        ]
    )
    preds = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    return (
        next(p for p in preds if is_presence(p)),
        next(p for p in preds if is_membership(p)),
        preds,
    )


def test_core_has_no_dataset_or_attribute_allowlist() -> None:
    for path in CORE_FILES:
        text = path.read_text()
        for name in FORBIDDEN:
            assert name not in text, f"{name} in {path.name}"
        assert "queries_for(\"Med\")" not in text
        assert "gold_name(\"Med\")" not in text


def test_eligibility_is_ast_only() -> None:
    report = audit_workload(
        [_q("q0", "SELECT COUNT(*) FROM widget WHERE LOWER(color) LIKE '%red%' AND color != ''")]
    )
    assert "widget.color" in report.signature_eligible
    assert "widget.color" not in report.full_value_required


def test_unsupported_forms_are_not_membership() -> None:
    report = audit_workload(
        [
            _q("q0", "SELECT COUNT(*) FROM item WHERE item.n > 3"),
            _q("q1", "SELECT COUNT(*) FROM item WHERE item.form IS NULL"),
        ]
    )
    preds = enumerate_predicates(report.occurrences, report.signature_eligible)
    assert live_predicates(preds) == []
    assert all(not is_membership(pred) for pred in preds)


def test_abstention_cannot_overwrite_truth() -> None:
    old = PredicateLabel("TRUE", "known", provenance=("cell",))
    for status in ("uncertain", "failed", "grounding-abstained"):
        kept = merge(old, PredicateLabel("NULL", status))
        assert kept is not None
        assert kept.sql_truth == "TRUE"
    kept = merge(old, PredicateLabel("FALSE", "failed"))
    assert kept is not None
    assert kept.sql_truth == "TRUE"
    conflict = merge(old, PredicateLabel("FALSE", "known"))
    assert conflict is not None
    assert conflict.conflict is True
    assert conflict.sql_truth == "TRUE"
    assert conflict.alt_sql_truth == "FALSE"


def test_operators_cannot_overwrite_each_others_atoms() -> None:
    presence, member, preds = _presence_membership()
    established = {
        presence.pred_id: PredicateLabel("TRUE", "known", provenance=("cell",)),
    }
    crossed = apply_row_operators(
        established,
        preds,
        attribute="item.form",
        cell=None,
        document="",
        entity_name="x",
        surfaces=[],
        caller=None,
        run_presence=False,
        run_membership=True,
    )
    assert crossed[presence.pred_id].sql_truth == "TRUE"
    leaked = merge_atoms(
        established,
        {
            presence.pred_id: PredicateLabel("FALSE", "known"),
            member.pred_id: PredicateLabel("TRUE", "known"),
        },
        {member.pred_id},
    )
    assert leaked[presence.pred_id].sql_truth == "TRUE"
    assert leaked[member.pred_id].sql_truth == "TRUE"


def test_nonempty_never_returns_false() -> None:
    assert populate_nonempty("item.form", "tablet", "", None).sql_truth == "TRUE"
    empty = populate_nonempty("item.form", None, "", None)
    assert empty.sql_truth == "NULL"
    assert empty.classifier_status != "known"


def test_closure_runs_during_live_populate(tmp_path: Path) -> None:
    presence, member, preds = _presence_membership()
    db = tmp_path / "live.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT)")
    conn.execute("INSERT INTO item VALUES ('d1', NULL)")
    conn.commit()
    conn.close()
    populate_signatures(db, preds, documents={"d1": "film-coated tablet"}, caller=None)
    conn = sqlite3.connect(db)
    conn.execute(f'UPDATE item SET "{member.sig_name}" = 1')
    conn.commit()
    conn.close()
    report = populate_signatures(db, preds, documents={"d1": "film-coated tablet"}, caller=None)
    assert report.closed is True
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM item").fetchone())
    conn.close()
    assert row[member.sig_name] == 1
    assert row[presence.sig_name] == 1


def test_compile_rewrites_signatures_and_closes(tmp_path: Path) -> None:
    portfolio = compile_workload(
        [SourceDocument(doc_id="d1", text="a tablet form")],
        {"q0": "SELECT COUNT(*) FROM item WHERE LOWER(item.form) LIKE '%tab%' AND item.form != ''"},
        theta=0,
        artifact_root=tmp_path,
        extract=False,
    )
    assert portfolio.rewrites
    sql = next(iter(portfolio.rewrites.values()))
    assert "sig_" in sql
    path = portfolio.databases[0].sqlite_path
    conn = sqlite3.connect(path)
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    sigs = []
    for table in tables:
        for col in conn.execute(f'PRAGMA table_info("{table}")'):
            if str(col[1]).startswith("sig_"):
                sigs.append(col[1])
    conn.close()
    assert sigs


def test_gold_bag_equivalence() -> None:
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from quwarts.eval.oracle_b import gold_conn, query_bag_check
    from quwarts.core.signature import materialize_signatures
    from quwarts.experiments.synthesize_case80 import queries_for

    queries = queries_for("Med")
    report = audit_workload(queries)
    predicates = enumerate_predicates(report.occurrences, report.signature_eligible)
    conn = gold_conn()
    try:
        materialize_signatures(conn, predicates)
        bags = query_bag_check(conn, queries, predicates)
    finally:
        conn.close()
    assert len(bags) == 99
    failed = [item for item in bags if not item["pass"]]
    assert not failed


def test_aprime_rows_keys_and_nonsig_unchanged(tmp_path: Path) -> None:
    aprime_dir = REPO / "results" / "quwarts_med_aprime" / "artifacts" / "databases"
    matches = list(aprime_dir.glob("*.db"))
    if not matches:
        return
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from quwarts.experiments.synthesize_case80 import queries_for

    src = matches[0]
    dest = tmp_path / "aprime_copy.db"
    shutil.copy2(src, dest)
    queries = queries_for("Med")
    report = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    before = _snapshot(src)
    populate_signatures(dest, predicates, caller=None)
    after = _snapshot(dest)
    assert before["row_counts"] == after["row_counts"]
    assert before["keys"] == after["keys"]
    assert before["nonsig"] == after["nonsig"]


def _snapshot(path: Path) -> dict:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        counts = {}
        keys = {}
        nonsig = {}
        for (table,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
        ):
            cols = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
            kept = [name for name in cols if not str(name).startswith("sig_")]
            rows = [dict(row) for row in conn.execute(f'SELECT * FROM "{table}"')]
            counts[table] = len(rows)
            keys[table] = [row.get("doc_id") for row in rows]
            nonsig[table] = [{name: row.get(name) for name in kept} for row in rows]
        return {"row_counts": counts, "keys": keys, "nonsig": nonsig}
    finally:
        conn.close()


def test_deterministic_cell_does_not_false_membership() -> None:
    _, member, preds = _presence_membership()
    labels = deterministic_labels(preds, "capsule")
    assert member.pred_id not in labels
    labels = deterministic_labels(preds, "tablet")
    assert labels[member.pred_id].sql_truth == "TRUE"
