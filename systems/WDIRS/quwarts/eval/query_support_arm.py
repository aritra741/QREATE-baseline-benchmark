"""Query-level support-set arm. Gold is loaded only after outputs are frozen."""

from __future__ import annotations

import hashlib
import json
import os
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
from quwarts.core.query_plans import run_query_arm
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


def _write_outputs(outputs: dict[str, list[dict]], dest: Path) -> dict[str, str]:
    if dest.exists():
        dest.unlink()
    conn = sqlite3.connect(str(dest))
    rewrites = {}
    try:
        for qid, rows in outputs.items():
            table = "r_" + hashlib.sha256(qid.encode()).hexdigest()[:16]
            if not rows:
                conn.execute(f'CREATE TABLE "{table}" (placeholder INTEGER)')
                rewrites[qid] = f'SELECT * FROM "{table}" WHERE 0'
                continue
            cols = list(rows[0].keys())
            quoted = ", ".join('"' + name.replace('"', '""') + '"' for name in cols)
            conn.execute(f'CREATE TABLE "{table}" ({quoted})')
            marks = ", ".join("?" for _ in cols)
            for row in rows:
                conn.execute(
                    f'INSERT INTO "{table}" VALUES ({marks})',
                    [
                        json.dumps(row.get(name), default=str)
                        if isinstance(row.get(name), (list, tuple, dict))
                        else row.get(name)
                        for name in cols
                    ],
                )
            rewrites[qid] = f"SELECT {quoted} FROM \"{table}\""
        conn.commit()
    finally:
        conn.close()
    return rewrites


def _diag(test, gold, predicates, aprime_db, pred_report, outputs):
    from spp.config_grid import _build_in_memory_db

    gold_conn = _build_in_memory_db(gold)
    aprime_conn = sqlite3.connect(str(aprime_db))
    by_q = {item["query_id"]: item for item in pred_report}
    out = []
    for row in test:
        qid = row["query_id"]
        gold_rows = execute(gold_conn, row["sql"])
        aprime_rows = execute(aprime_conn, official_sql(row["sql"], aprime_db, predicates))
        pred_rows = outputs.get(qid) or []
        def _group_key(item):
            return tuple(
                sorted(
                    (str(key), json.dumps(value, default=str))
                    for key, value in item.items()
                    if not str(key).lower().endswith("count")
                )
            )

        gold_groups = [_group_key(item) for item in gold_rows]
        pred_groups = [_group_key(item) for item in pred_rows]
        gold_n = sum(int(next((v for k, v in item.items() if str(k).lower().endswith("count") and v not in (None, "")), 0) or 0) for item in gold_rows)
        pred_n = sum(int(next((v for k, v in item.items() if str(k).lower().endswith("count") and v not in (None, "")), 0) or 0) for item in pred_rows)
        scored = by_q.get(qid) or {}
        meta = next((item for item in [] ), {})
        out.append(
            {
                "query_id": qid,
                "gold_groups": gold_rows,
                "aprime_groups": aprime_rows,
                "pred_groups": pred_rows,
                "gold_n": gold_n,
                "pred_n": pred_n,
                "undercount": max(0, gold_n - pred_n),
                "overcount": max(0, pred_n - gold_n),
                "group_key_errors": len(set(pred_groups) - set(gold_groups)),
                "structure_f2": scored.get("structure_f2"),
                "cell_f1_20": scored.get("cell_f1_20"),
                "product": (float(scored.get("structure_f2") or 0.0) * float(scored.get("cell_f1_20") or 0.0))
                if scored.get("cell_f1_20") is not None
                else None,
            }
        )
    gold_conn.close()
    aprime_conn.close()
    return out


def main() -> int:
    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    report = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    docs = {}
    for doc in documents_for("Med"):
        docs[doc.doc_id] = doc.text
        docs[Path(doc.doc_id).stem] = doc.text
        docs[Path(doc.doc_id).name] = doc.text
    dest = OUT / "artifacts" / "aprime_query_support.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(APRIME, dest)
    conn = sqlite3.connect(str(dest))
    try:
        ensure_signature_columns(conn, predicates)
        conn.commit()
    finally:
        conn.close()
    ckpt = OUT / "query_support_ckpt.json"
    if os.environ.get("QUERY_SUPPORT_SCORE_ONLY") and ckpt.is_file():
        saved = json.loads(ckpt.read_text())
        outputs = saved.get("outputs") or {}
        from quwarts.core.query_plans import PlanReport

        arm = PlanReport(
            tokens_spent=1_543_555,
            n_queries=int(saved.get("n_queries") or 0),
            n_accepted=int(saved.get("n_accepted") or 0),
            n_fallback=int(saved.get("n_fallback") or 0),
            per_query=list(saved.get("per_query") or []),
        )
        ledger = TokenLedger(theta=BUDGET, seed=42)
        ledger.spent = arm.tokens_spent
        print("score-only from", ckpt, flush=True)
    else:
        ledger = TokenLedger(theta=BUDGET, seed=42)
        caller = make_caller(ledger, model=DEFAULT_MODEL, temperature=0.1, max_tokens=280)
        print(f"query-support start model={DEFAULT_MODEL} theta={BUDGET} n_test={len(test)}", flush=True)
        arm, outputs = run_query_arm(
            dest,
            test,
            predicates,
            documents=docs,
            caller=caller,
            checkpoint=ckpt,
        )
    from quwarts.core.query_support import aprime_counts

    for row in test:
        if not outputs.get(row["query_id"]):
            outputs[row["query_id"]] = aprime_counts(dest, row["sql"], predicates)
    print(f"query-support frozen spent={ledger.spent} accepted={arm.n_accepted}", flush=True)
    pred_db = OUT / "artifacts" / "query_support_results.db"
    rewrites = _write_outputs(outputs, pred_db)
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    scored = _score(test, pred_db, gold, rewrites)
    aprime = _score(test, dest, gold, _official_rewrites(test, dest, predicates))
    stored_aprime = json.loads(APRIME_REPORT.read_text()) if APRIME_REPORT.is_file() else {}
    stored_compare = json.loads(COMPARE.read_text()) if COMPARE.is_file() else {}
    stored_pred = json.loads(PRED_ARM.read_text()) if PRED_ARM.is_file() else {}
    agent_db = Path(stored_compare.get("agent", {}).get("sqlite_path") or "")
    pred_db_old = Path((stored_pred.get("candidates") or {}).get("sqlite_path") or "")
    agent = None
    predicate_arm = None
    if agent_db.is_file():
        agent = _score(test, agent_db, gold, _official_rewrites(test, agent_db, predicates))
    if pred_db_old.is_file():
        predicate_arm = _score(test, pred_db_old, gold, _official_rewrites(test, pred_db_old, predicates))
    by_meta = {item["query_id"]: item for item in arm.per_query}
    diag = _diag(test, gold, predicates, dest, scored["per_query"], outputs)
    for item in diag:
        extra = by_meta.get(item["query_id"]) or {}
        item["winner"] = extra.get("winner")
        item["entity_ids"] = extra.get("entity_ids")
        item["filter_errors"] = None
        item["join_edge_errors"] = None
    payload = {
        "budget": BUDGET,
        "model": DEFAULT_MODEL,
        "tokens_spent": ledger.spent,
        "tokens_planner": arm.tokens_planner,
        "tokens_executor": arm.tokens_executor,
        "tokens_refiner": arm.tokens_refiner,
        "tokens_validator": arm.tokens_validator,
        "n_queries": arm.n_queries,
        "n_accepted": arm.n_accepted,
        "n_fallback": arm.n_fallback,
        "n_disputes": arm.n_disputes,
        "cache_hits": arm.cache_hits,
        "cache_misses": arm.cache_misses,
        "query_level": scored,
        "aprime_official": aprime,
        "stored_aprime_product": stored_aprime.get("mean_per_query_product"),
        "stored_aprime_structure_f2": stored_aprime.get("mean_structure_f2"),
        "agent_official": agent,
        "predicate_arm_official": predicate_arm,
        "per_query_debug": diag,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "query_support.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "spent": ledger.spent,
                "accepted": arm.n_accepted,
                "fallback": arm.n_fallback,
                "query_product": scored["mean_per_query_product"],
                "query_f2": scored["mean_structure_f2"],
                "aprime_product": aprime["mean_per_query_product"],
                "aprime_f2": aprime["mean_structure_f2"],
                "stored_aprime_product": payload["stored_aprime_product"],
                "agent_product": None if agent is None else agent["mean_per_query_product"],
                "predicate_product": None if predicate_arm is None else predicate_arm["mean_per_query_product"],
            },
            indent=2,
        )
    )
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
