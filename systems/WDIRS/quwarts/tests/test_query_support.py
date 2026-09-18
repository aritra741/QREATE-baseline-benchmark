from __future__ import annotations

import sqlite3
from pathlib import Path

from quwarts.core.ledger import BudgetedCaller, TokenLedger
from quwarts.core.query_plans import DIRECT_PROMPT, FILTER_PROMPT, JUDGE_PROMPT, obligation_pred
from quwarts.core.query_support import (
    SupportRow,
    aprime_support,
    count_from_support,
    grain_sql,
    query_shape,
    symmetric_diff,
    universe,
)
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.signature_cache import ResponseCache


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


def test_prompts_are_generic() -> None:
    for text in (DIRECT_PROMPT, FILTER_PROMPT, JUDGE_PROMPT):
        low = text.lower()
        assert "med" not in low
        assert "docetl" not in low
        assert "gold" not in low or "do not use gold" in low
    for name in FORBIDDEN:
        for path in (
            CORE / "query_support.py",
            CORE / "query_plans.py",
            CORE / "query_residual.py",
            CORE / "query_witness.py",
            CORE / "signature_views.py",
        ):
            assert name not in path.read_text(), f"{name} in {path.name}"


def test_grain_and_count_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT)")
    conn.execute("INSERT INTO item VALUES ('a', 'tablet'), ('b', 'capsule'), ('c', '')")
    conn.commit()
    conn.close()
    sql = "SELECT CASE WHEN form != '' THEN 'has_form' ELSE 'empty' END AS g, COUNT(*) AS n FROM item WHERE form != '' GROUP BY g"
    shape = query_shape("q0", sql)
    assert shape.primary == "item"
    assert "g" in shape.group_aliases
    grain = grain_sql(sql)
    assert "COUNT(" not in grain.upper()
    assert "GROUP BY" not in grain.upper()
    entities = universe(db, shape)
    assert len(entities) == 3
    rid_map = {item["rowid"]: item["entity_id"] for item in entities}
    support = aprime_support(db, shape, [], rid_map)
    assert {row.entity_id for row in support} == {"a", "b"}
    counts = count_from_support(shape, support)
    assert counts == [{"g": "has_form", "n": 2}]


def test_count_from_support_accepts_list_groups() -> None:
    shape = query_shape("q0", "SELECT form AS g, COUNT(*) AS n FROM item GROUP BY g")
    rows = [SupportRow("a", 1, "true", {"g": ["x"]}), SupportRow("b", 2, "true", {"g": ["x"]})]
    out = count_from_support(shape, rows)
    assert out[0]["n"] == 2


def test_symmetric_diff_hashes_list_groups() -> None:
    left = [SupportRow("a", 1, "true", {"g": ["x", "y"]})]
    right = [SupportRow("a", 1, "true", {"g": ["x", "z"]})]
    assert symmetric_diff(left, right) == ["a"]


def test_symmetric_diff_is_entity_level() -> None:
    left = [SupportRow("a", 1, "true", {"g": "x"}), SupportRow("b", 2, "true", {"g": "y"})]
    right = [SupportRow("a", 1, "true", {"g": "x"}), SupportRow("c", 3, "true", {"g": "z"})]
    assert symmetric_diff(left, right) == ["b", "c"]


def test_obligation_cache_key_is_canonical() -> None:
    report = audit_workload(
        [{"query_id": "q0", "sql": "SELECT COUNT(*) FROM item WHERE LOWER(form) LIKE '%tab%'"}]
    )
    preds = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    assert preds
    key = obligation_pred("e1", preds[0])
    assert "e1" in key
    assert preds[0].pred_id in key


def test_cache_hits_do_not_spend() -> None:
    calls = []

    def client(prompt: str, metadata: dict) -> tuple[str, int]:
        calls.append(prompt)
        return '{"applies": false}', 5

    ledger = TokenLedger(1000, 0)
    caller = BudgetedCaller(ledger, client)
    cache = ResponseCache()
    cache.complete(caller, "p", "sig_executor", plan="decompose")
    cache.complete(caller, "p", "sig_executor", plan="decompose")
    assert len(calls) == 1
    assert ledger.spent == 5
