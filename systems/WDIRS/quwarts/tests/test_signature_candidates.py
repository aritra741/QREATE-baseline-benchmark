from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

from quwarts.core.ledger import BudgetedCaller, TokenLedger
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_cache import ResponseCache
from quwarts.core.signature_candidates import (
    PAIR_PROMPT,
    PLANNER_PROMPT,
    CandidatePlan,
    CandidateReport,
    default_plans,
    drop_ungrounded,
    execute_plan_row,
    parse_plans,
    prefer_pair,
    rank_cohorts,
    run_candidate_arm,
    select_plan,
    stratify_sample,
    verify_span,
)
from quwarts.core.signature_classify import parse_nonempty
from quwarts.core.signature_populate import ensure_signature_columns
from quwarts.core.signature_realize import is_membership, is_presence, live_predicates
from quwarts.core.truth import PredicateLabel


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


def _q(query_id: str, sql: str) -> dict[str, str]:
    return {"query_id": query_id, "sql": sql}


def _preds():
    report = audit_workload(
        [_q("q0", "SELECT COUNT(*) FROM item WHERE LOWER(form) LIKE '%tab%' AND form != ''")]
    )
    return live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))


def _caller(script: list[str] | None = None, default: str = '{"winner": "tie"}'):
    replies = list(script or [])
    ledger = TokenLedger(theta=100_000, seed=1)

    def client(prompt: str, metadata: dict) -> tuple[str, int]:
        text = replies.pop(0) if replies else default
        return text, 4

    return BudgetedCaller(ledger, client), ledger


def test_cache_hits_do_not_spend() -> None:
    calls = []

    def client(prompt: str, metadata: dict) -> tuple[str, int]:
        calls.append(prompt)
        return '{"note": "x"}', 10

    ledger = TokenLedger(theta=1000, seed=0)
    caller = BudgetedCaller(ledger, client)
    cache = ResponseCache()
    cache.complete(caller, "same", "sig_executor", plan="direct")
    cache.complete(caller, "same", "sig_executor", plan="direct")
    assert len(calls) == 1
    assert cache.hits == 1
    assert cache.misses == 1
    assert ledger.spent == 10


def test_cache_key_includes_plan() -> None:
    calls = []

    def client(prompt: str, metadata: dict) -> tuple[str, int]:
        calls.append(metadata.get("plan"))
        return "ok", 3

    ledger = TokenLedger(theta=1000, seed=0)
    caller = BudgetedCaller(ledger, client)
    cache = ResponseCache()
    cache.complete(caller, "same", "sig_executor", plan="direct")
    cache.complete(caller, "same", "sig_executor", plan="gleaning")
    assert calls == ["direct", "gleaning"]
    assert cache.misses == 2


def test_span_rejects_ungrounded() -> None:
    label = parse_nonempty('{"value": "invented", "span": "invented"}', "the document has tablets")
    assert label.sql_truth == "NULL"
    assert "nonempty_ungrounded" in label.provenance
    assert verify_span(label, "the document has tablets")
    fake = PredicateLabel("TRUE", "known", provenance=("invented",))
    assert verify_span(fake, "the document has tablets") is False
    dropped = drop_ungrounded({"p": fake}, "the document has tablets")
    assert dropped["p"].sql_truth == "NULL"


def test_pairwise_requires_both_orders() -> None:
    preds = [p for p in _preds() if is_membership(p)]
    left = {preds[0].pred_id: PredicateLabel("TRUE", "known")}
    right = {preds[0].pred_id: PredicateLabel("FALSE", "known")}
    always_a, _ = _caller(default='{"winner": "A"}')
    pick = prefer_pair(always_a, preds, "tablet form", left, right, random.Random(0))
    assert pick in {"left", "right", ""}
    prefer_true = []

    def client(prompt: str, metadata: dict) -> tuple[str, int]:
        prefer_true.append(prompt)
        a_true = '"TRUE"' in prompt.split("ANSWER A:")[1].split("ANSWER B:")[0]
        return ('{"winner": "A"}' if a_true else '{"winner": "B"}'), 4

    caller = BudgetedCaller(TokenLedger(10_000, 0), client)
    agreed = prefer_pair(caller, preds, "tablet form", left, right, random.Random(1))
    assert agreed == "left"
    assert len(prefer_true) >= 2


def test_inconclusive_keeps_fallback(tmp_path: Path) -> None:
    preds = _preds()
    member = next(p for p in preds if is_membership(p))
    plans = default_plans("item.form", "semantic_membership", (member.pred_id,))
    sample = [
        {"document": "abc", "labels": {}, "cell": None, "surfaces": [], "entity_name": "e"}
        for _ in range(3)
    ]
    results = [
        [{member.pred_id: PredicateLabel("TRUE", "known")} for _ in sample],
        [{member.pred_id: PredicateLabel("FALSE", "known")} for _ in sample],
        [{member.pred_id: PredicateLabel("NULL", "uncertain")} for _ in sample],
    ]
    caller, _ = _caller(default='{"winner": "tie"}')
    report = CandidateReport()
    winner = select_plan(plans, sample, results, preds, caller, ResponseCache(), report)
    assert winner is None
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE item (doc_id TEXT, form TEXT)")
    conn.execute("INSERT INTO item VALUES ('d1', 'tablet')")
    ensure_signature_columns(conn, preds)
    conn.commit()
    conn.close()
    before = sqlite3.connect(db).execute("SELECT form FROM item").fetchall()
    empty = run_candidate_arm(db, preds, caller=None)
    assert empty.n_cohorts_accepted == 0
    after = sqlite3.connect(db).execute("SELECT form FROM item").fetchall()
    assert before == after


def test_prompts_have_no_dataset_or_gold() -> None:
    for text in (PLANNER_PROMPT, PAIR_PROMPT):
        low = text.lower()
        assert "med" not in low
        assert "docetl" not in low
        assert "moar" not in low
        assert "queries_for" not in text
        assert "baseline" not in low or "baseline outputs" in low
    for name in FORBIDDEN:
        for path in (CORE / "signature_candidates.py", CORE / "signature_cache.py"):
            body = path.read_text()
            assert name not in body, f"{name} in {path.name}"


def test_parse_plans_requires_three_strategies() -> None:
    text = json.dumps(
        {
            "plans": [
                {"strategy": "direct", "operator": "semantic_membership", "context": "value", "n_passes": 1, "estimated_cost": 10, "prompt": "a"},
                {"strategy": "direct", "operator": "semantic_membership", "context": "document", "n_passes": 1, "estimated_cost": 10, "prompt": "b"},
            ]
        }
    )
    plans = parse_plans(text, "item.form", ("p1",), "semantic_membership")
    assert [p.strategy for p in plans] == ["direct", "decompose", "gleaning"]


def test_stratify_covers_surface_length_status() -> None:
    rows = [
        {"cell": "x", "document": "short", "labels": {}},
        {"cell": None, "document": "short", "labels": {}},
        {"cell": "x", "document": "a much longer document text", "labels": {"a": PredicateLabel("TRUE", "known")}},
        {"cell": None, "document": "a much longer document text", "labels": {}},
    ]
    sample = stratify_sample(rows, k=4, seed=0)
    assert len(sample) == 4


def test_rank_uses_freq_amp_mass_over_cost() -> None:
    ranked = rank_cohorts(
        {
            "attributes": [
                {"attribute": "a", "unresolved_atoms": 10, "query_frequency": 1, "amplification": 1},
                {"attribute": "b", "unresolved_atoms": 10, "query_frequency": 8, "amplification": 2},
                {"attribute": "c", "unresolved_atoms": 0, "query_frequency": 99, "amplification": 9},
            ]
        }
    )
    assert [row["attribute"] for row in ranked] == ["b", "a"]


def test_execute_abstain_writes_nothing() -> None:
    preds = _preds()
    plan = CandidatePlan("direct", "abstain", "document", 1, 1, "skip", "item.form", ())
    caller, _ = _caller()
    out = execute_plan_row(plan, {"document": "x", "cell": None, "surfaces": [], "entity_name": ""}, preds, caller)
    assert out == {}
