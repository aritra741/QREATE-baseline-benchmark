from __future__ import annotations

import inspect
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from quwarts.core.ledger import BudgetedCaller, TokenLedger
from quwarts.core.signature import audit_workload, enumerate_predicates, rewrite_sql
from quwarts.core.signature_acquire import AcquisitionAction, parse_action, validate_action
from quwarts.core.signature_controller import (
    CONTROLLER_PROMPT,
    execute_action,
    fixed_policy_action,
    observe,
)
from quwarts.core.signature_populate import ensure_signature_columns, populate_signatures
from quwarts.core.signature_realize import is_membership, is_presence, live_predicates
from quwarts.core.truth import PredicateLabel, merge_atoms


REPO = Path(__file__).resolve().parents[3]
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


def _q(query_id: str, sql: str) -> dict[str, str]:
    return {"query_id": query_id, "sql": sql}


def _preds():
    report = audit_workload(
        [_q("q0", "SELECT COUNT(*) FROM item WHERE LOWER(form) LIKE '%tab%' AND form != ''")]
    )
    return live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))


def _bags(path: Path, queries: list[dict[str, str]], predicates=None) -> list[Counter]:
    conn = sqlite3.connect(path)
    try:
        out = []
        for row in queries:
            sql = rewrite_sql(row["sql"], predicates) if predicates else row["sql"]
            out.append(Counter(conn.execute(sql).fetchall()))
        return out
    finally:
        conn.close()


def test_all_unresolved_reproduces_aprime() -> None:
    aprime_dir = REPO / "results" / "quwarts_med_aprime" / "artifacts" / "databases"
    matches = list(aprime_dir.glob("*.db"))
    if not matches:
        return
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from quwarts.experiments.synthesize_case80 import queries_for

    src = matches[0]
    dest = Path(src).parent / "_unresolved_copy.db"
    shutil.copy2(src, dest)
    queries = queries_for("Med")
    report = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    conn = sqlite3.connect(dest)
    try:
        ensure_signature_columns(conn, predicates)
        conn.commit()
    finally:
        conn.close()
    try:
        assert _bags(src, queries) == _bags(dest, queries, predicates)
    finally:
        dest.unlink(missing_ok=True)


def test_resolved_null_differs_from_unresolved(tmp_path: Path) -> None:
    preds = _preds()
    like = next(p for p in preds if is_membership(p))
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (form TEXT)")
    conn.execute("INSERT INTO item VALUES ('tablet')")
    ensure_signature_columns(conn, preds)
    conn.commit()
    sql = "SELECT COUNT(*) FROM item WHERE LOWER(form) LIKE '%tab%'"
    unresolved = conn.execute(rewrite_sql(sql, preds)).fetchone()[0]
    conn.execute(f'UPDATE item SET "{like.resolved_name}" = 1, "{like.sig_name}" = NULL')
    conn.commit()
    resolved_null = conn.execute(rewrite_sql(sql, preds)).fetchone()[0]
    conn.close()
    assert unresolved == 1
    assert resolved_null == 0


def test_abstention_cannot_alter_query_results(tmp_path: Path) -> None:
    preds = _preds()
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT)")
    conn.execute("INSERT INTO item VALUES ('d1', 'tablet')")
    conn.commit()
    conn.close()
    queries = [_q("q0", "SELECT COUNT(*) FROM item WHERE LOWER(form) LIKE '%tab%' AND form != ''")]
    populate_signatures(db, preds, caller=None)
    before = _bags(db, queries, preds)
    action = AcquisitionAction(
        predicate_ids=tuple(p.pred_id for p in preds),
        attribute="item.form",
        entity_cohort="unresolved",
        operator="abstain",
        context="document",
        model="",
        max_tokens=0,
        reason="test",
    )
    execute_action(db, action, preds)
    assert _bags(db, queries, preds) == before


def test_agent_cannot_modify_compiler_invariants(tmp_path: Path) -> None:
    preds = _preds()
    presence = next(p for p in preds if is_presence(p))
    member = next(p for p in preds if is_membership(p))
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT, extra TEXT)")
    conn.execute("INSERT INTO item VALUES ('d1', 'tablet', 'keep')")
    conn.commit()
    conn.close()
    populate_signatures(db, preds, caller=None)
    bad = parse_action(
        {
            "scope": {
                "predicate_ids": [presence.pred_id, member.pred_id],
                "attribute": "item.form",
                "entity_cohort": "unresolved",
            },
            "operator": "semantic_membership",
            "context": "document",
            "model": "",
            "max_tokens": 0,
            "reason": "cross",
        }
    )
    checked = validate_action(bad, preds)
    assert presence.pred_id not in checked.predicate_ids
    assert member.pred_id in checked.predicate_ids
    execute_action(db, checked, preds, caller=None)
    conn = sqlite3.connect(db)
    extra = conn.execute("SELECT extra FROM item").fetchone()[0]
    conn.close()
    assert extra == "keep"
    rewritten = rewrite_sql("SELECT COUNT(*) FROM item WHERE LOWER(form) LIKE '%tab%'", preds)
    assert member.resolved_name in rewritten
    assert "LIKE" in rewritten.upper()
    assert inspect.getsource(rewrite_sql).find("default") >= 0


def test_operators_cannot_write_each_others_atoms_via_action() -> None:
    preds = _preds()
    presence = next(p for p in preds if is_presence(p))
    member = next(p for p in preds if is_membership(p))
    established = {presence.pred_id: PredicateLabel("TRUE", "known")}
    leaked = merge_atoms(
        established,
        {presence.pred_id: PredicateLabel("FALSE", "known"), member.pred_id: PredicateLabel("TRUE", "known")},
        {member.pred_id},
    )
    assert leaked[presence.pred_id].sql_truth == "TRUE"


def test_budget_exhaustion_leaves_fallback_active(tmp_path: Path) -> None:
    preds = _preds()
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT)")
    conn.execute("INSERT INTO item VALUES ('d1', NULL)")
    conn.commit()
    conn.close()
    ledger = TokenLedger(theta=0, seed=0)

    def client(_prompt: str, _meta: dict) -> tuple[str, int]:
        return '{"value": "tablet", "span": "tablet"}', 10

    caller = BudgetedCaller(ledger, client)
    action = AcquisitionAction(
        predicate_ids=tuple(p.pred_id for p in preds if is_presence(p)),
        attribute="item.form",
        entity_cohort="unresolved",
        operator="grounded_existence",
        context="document",
        model="",
        max_tokens=120,
        reason="budget",
    )
    execute_action(db, action, preds, documents={"d1": "a tablet"}, caller=caller)
    conn = sqlite3.connect(db)
    presence = next(p for p in preds if is_presence(p))
    resolved = conn.execute(f'SELECT "{presence.resolved_name}" FROM item').fetchone()[0]
    conn.close()
    sql = "SELECT COUNT(*) FROM item WHERE form != ''"
    assert (resolved or 0) == 0
    conn = sqlite3.connect(db)
    n = conn.execute(rewrite_sql(sql, preds)).fetchone()[0]
    orig = conn.execute(sql).fetchone()[0]
    conn.close()
    assert n == orig


def test_controller_policy_has_no_dataset_or_attribute_names() -> None:
    source = Path(__file__).resolve().parents[1] / "core"
    for name in ("signature_controller.py", "signature_acquire.py"):
        text = (source / name).read_text()
        for item in FORBIDDEN:
            assert item not in text, f"{item} in {name}"
    for item in FORBIDDEN:
        assert item not in CONTROLLER_PROMPT


def test_gold_bag_equivalence_with_fallback_rewrite() -> None:
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
    assert not [item for item in bags if not item["pass"]]


def test_fixed_policy_abstains_when_nothing_unresolved() -> None:
    action = fixed_policy_action({"attributes": []})
    assert action.operator == "abstain"


def test_observe_has_no_gold_keys(tmp_path: Path) -> None:
    preds = _preds()
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT)")
    conn.execute("INSERT INTO item VALUES ('d1', 'tablet')")
    conn.commit()
    conn.close()
    state = observe(db, preds)
    blob = json_keys(state)
    assert "gold" not in blob
    assert "docetl" not in blob
    assert "f1" not in blob


def json_keys(payload) -> str:
    import json

    return json.dumps(payload, default=str).lower()
