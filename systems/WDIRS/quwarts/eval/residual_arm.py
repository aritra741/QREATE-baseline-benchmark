"""Residual inclusion on the single-action agent incumbent. Gold after freeze."""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.core.pipeline import official_sql
from quwarts.core.query_residual import run_residual_arm
from quwarts.core.schema_columns import assert_queries_execute, ensure_referenced_columns
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_populate import ensure_signature_columns
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.player_case80 import execute, split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import (
    documents_for,
    gold_name,
    queries_for,
    score_with_rewrites,
)

load_env_file(ROOT / ".env")

APRIME = next((ROOT / "results" / "quwarts_med_aprime" / "artifacts" / "databases").glob("*.db"))
APRIME_REPORT = ROOT / "results" / "quwarts_med_aprime" / "aprime_report.json"
COMPARE = ROOT / "results" / "quwarts_med_signatures" / "acquisition_compare.json"
PRED_ARM = ROOT / "results" / "quwarts_med_signatures" / "candidate_validation.json"
QUERY_ARM = ROOT / "results" / "quwarts_med_signatures" / "query_support.json"
OUT = ROOT / "results" / "quwarts_med_signatures"
BUDGET = 1_543_790


def _score(test, dest, gold, rewrites):
    report = score_with_rewrites(test, rewrites, dest, gold, "Med")
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "per_query": report.get("per_query") or [],
        "test_empty_query_count": sum(
            1 for row in report.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0
        ),
    }


def _official_rewrites(rows, dest, predicates):
    return {row["query_id"]: official_sql(row["sql"], dest, predicates) for row in rows}


def _diag(test, gold, predicates, incumbent_db, residual_db, pred_report, meta):
    from spp.config_grid import _build_in_memory_db

    gold_conn = _build_in_memory_db(gold)
    inc_conn = sqlite3.connect(str(incumbent_db))
    res_conn = sqlite3.connect(str(residual_db))
    by_q = {item["query_id"]: item for item in pred_report}
    by_meta = {item["query_id"]: item for item in meta}
    out = []
    for row in test:
        qid = row["query_id"]
        gold_rows = execute(gold_conn, row["sql"])
        inc_rows = execute(inc_conn, official_sql(row["sql"], incumbent_db, predicates))
        pred_rows = execute(res_conn, official_sql(row["sql"], residual_db, predicates))

        def _count(items):
            return sum(
                int(next((v for k, v in item.items() if str(k).lower().endswith("count") and v not in (None, "")), 0) or 0)
                for item in items
            )

        scored = by_q.get(qid) or {}
        extra = by_meta.get(qid) or {}
        out.append(
            {
                "query_id": qid,
                "gold_groups": gold_rows,
                "incumbent_groups": inc_rows,
                "pred_groups": pred_rows,
                "gold_n": _count(gold_rows),
                "pred_n": _count(pred_rows),
                "incumbent_n": _count(inc_rows),
                "undercount": max(0, _count(gold_rows) - _count(pred_rows)),
                "overcount": max(0, _count(pred_rows) - _count(gold_rows)),
                "n_added": extra.get("n_added"),
                "n_proposed": extra.get("n_proposed"),
                "n_excluded": extra.get("n_excluded"),
                "structure_f2": scored.get("structure_f2"),
                "cell_f1_20": scored.get("cell_f1_20"),
                "product": (
                    float(scored.get("structure_f2") or 0.0) * float(scored.get("cell_f1_20") or 0.0)
                    if scored.get("cell_f1_20") is not None
                    else None
                ),
            }
        )
    gold_conn.close()
    inc_conn.close()
    res_conn.close()
    return out


def main() -> int:
    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    statements = {row["query_id"]: row["sql"] for row in queries}
    report = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    docs = {}
    for doc in documents_for("Med"):
        docs[doc.doc_id] = doc.text
        docs[Path(doc.doc_id).stem] = doc.text
        docs[Path(doc.doc_id).name] = doc.text
    stored_compare = json.loads(COMPARE.read_text()) if COMPARE.is_file() else {}
    agent_info = stored_compare.get("agent") or {}
    agent_db = Path(agent_info.get("sqlite_path") or "")
    if not agent_db.is_file():
        raise SystemExit(f"agent incumbent missing: {agent_db}")
    agent_spent = int(agent_info.get("tokens_spent") or 0)
    dest = OUT / "artifacts" / "aprime_residual.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(agent_db, dest)
    conn = sqlite3.connect(str(dest))
    try:
        added_cols = ensure_referenced_columns(conn, statements)
        ensure_signature_columns(conn, predicates)
        conn.commit()
        rewritten = _official_rewrites(queries, dest, predicates)
        assert_queries_execute(conn, rewritten)
    finally:
        conn.close()
    print(
        f"residual start incumbent=agent spent={agent_spent} remaining={BUDGET - agent_spent} "
        f"added_columns={added_cols}",
        flush=True,
    )
    ledger = TokenLedger(theta=BUDGET, seed=42)
    ledger.spent = agent_spent
    caller = make_caller(ledger, model=DEFAULT_MODEL, temperature=0.1, max_tokens=280)
    ckpt = OUT / "residual_ckpt.json"
    arm = run_residual_arm(
        dest,
        test,
        predicates,
        documents=docs,
        caller=caller,
        statements=statements,
        checkpoint=ckpt,
    )
    print(f"residual frozen spent={ledger.spent} added={arm.n_added}", flush=True)
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    residual = _score(test, dest, gold, _official_rewrites(test, dest, predicates))
    aprime = _score(test, APRIME, gold, _official_rewrites(test, APRIME, predicates))
    agent = _score(test, agent_db, gold, _official_rewrites(test, agent_db, predicates))
    stored_aprime = json.loads(APRIME_REPORT.read_text()) if APRIME_REPORT.is_file() else {}
    stored_pred = json.loads(PRED_ARM.read_text()) if PRED_ARM.is_file() else {}
    stored_query = json.loads(QUERY_ARM.read_text()) if QUERY_ARM.is_file() else {}
    pred_db_old = Path((stored_pred.get("candidates") or {}).get("sqlite_path") or "")
    predicate_arm = None
    if pred_db_old.is_file():
        predicate_arm = _score(test, pred_db_old, gold, _official_rewrites(test, pred_db_old, predicates))
    diag = _diag(test, gold, predicates, agent_db, dest, residual["per_query"], arm.per_query)
    payload = {
        "budget": BUDGET,
        "model": DEFAULT_MODEL,
        "incumbent": "agent",
        "incumbent_tokens": agent_spent,
        "tokens_spent": ledger.spent,
        "tokens_residual": ledger.spent - agent_spent,
        "tokens_executor": arm.tokens_executor,
        "tokens_refiner": arm.tokens_refiner,
        "tokens_validator": arm.tokens_validator,
        "added_columns": added_cols,
        "n_queries": arm.n_queries,
        "n_proposed": arm.n_proposed,
        "n_added": arm.n_added,
        "n_unknown": arm.n_unknown,
        "n_new_groups": arm.n_new_groups,
        "n_existing_groups": arm.n_existing_groups,
        "cache_hits": arm.cache_hits,
        "cache_misses": arm.cache_misses,
        "residual": residual,
        "aprime_official": aprime,
        "agent_official": agent,
        "predicate_arm_official": predicate_arm,
        "query_replacement_product": (stored_query.get("query_level") or {}).get("mean_per_query_product"),
        "stored_aprime_product": stored_aprime.get("mean_per_query_product"),
        "per_query": arm.per_query,
        "per_query_debug": diag,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "residual_repair.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "spent": ledger.spent,
                "residual_tokens": ledger.spent - agent_spent,
                "added": arm.n_added,
                "proposed": arm.n_proposed,
                "residual_product": residual["mean_per_query_product"],
                "residual_f2": residual["mean_structure_f2"],
                "agent_product": agent["mean_per_query_product"],
                "aprime_product": aprime["mean_per_query_product"],
                "predicate_product": None if predicate_arm is None else predicate_arm["mean_per_query_product"],
                "replacement_product": payload["query_replacement_product"],
            },
            indent=2,
        )
    )
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
