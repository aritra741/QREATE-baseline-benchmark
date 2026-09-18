"""Label-free candidate-validation arm. Gold is loaded only after the database is frozen."""

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

from quwarts.core.amplify import attach_amplification
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.core.signature import audit_workload, enumerate_predicates, rewrite_sql
from quwarts.core.signature_candidates import count_resolved, run_candidate_arm
from quwarts.core.signature_populate import ensure_signature_columns
from quwarts.core.signature_realize import is_membership, is_presence, live_predicates
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
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
OUT = ROOT / "results" / "quwarts_med_signatures"
BUDGET = 1_543_790


def _score(test, predicates, dest, gold):
    rewrites = {row["query_id"]: rewrite_sql(row["sql"], predicates) for row in test}
    report = score_with_rewrites(test, rewrites, dest, gold, "Med")
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "per_query": [
            {
                "query_id": row.get("query_id"),
                "product": row.get("product") or row.get("per_query_product"),
                "structure_f2": row.get("structure_f2") or row.get("f2"),
                "cell_f1": row.get("cell_f1") or row.get("cell_f1_at_0.20"),
            }
            for row in report.get("per_query") or []
        ],
        "test_empty_query_count": sum(
            1 for row in report.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0
        ),
    }


def _product(row: dict) -> float | None:
    value = row.get("product")
    if value is None:
        return None
    return float(value)


def _plan_query_map(predicates, accepted: list[dict]) -> dict[str, list[dict]]:
    by_attr = {}
    for pred in predicates:
        by_attr.setdefault(pred.attribute, set()).update(pred.query_ids)
    mapping: dict[str, list[dict]] = {}
    for item in accepted:
        plan = item.get("plan") or {}
        attr = plan.get("attribute")
        for qid in by_attr.get(attr, ()):
            mapping.setdefault(qid, []).append(
                {
                    "strategy": plan.get("strategy"),
                    "operator": plan.get("operator"),
                    "attribute": attr,
                }
            )
    return mapping


def main() -> int:
    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    statements = {row["query_id"]: row["sql"] for row in queries}
    _logical, workload = analyze_workload(statements)
    attach_amplification(workload)
    report = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    docs = documents_for("Med")
    dest = OUT / "artifacts" / "aprime_candidates.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(APRIME, dest)
    ledger = TokenLedger(theta=BUDGET, seed=42)
    caller = make_caller(ledger, model=DEFAULT_MODEL, temperature=0.1, max_tokens=280)
    print(f"candidates start model={DEFAULT_MODEL} theta={BUDGET}", flush=True)
    arm = run_candidate_arm(
        dest,
        predicates,
        documents=docs,
        caller=caller,
        workload=workload,
        statements=statements,
        max_cohorts=20,
    )
    print(f"candidates frozen spent={ledger.spent} accepted={arm.n_cohorts_accepted}", flush=True)
    resolved = count_resolved(dest, predicates)
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    abstain_dest = OUT / "artifacts" / "aprime_abstain.db"
    if abstain_dest.exists():
        abstain_dest.unlink()
    shutil.copy2(APRIME, abstain_dest)
    conn = sqlite3.connect(abstain_dest)
    try:
        ensure_signature_columns(conn, predicates)
        conn.commit()
    finally:
        conn.close()
    abstain = _score(test, predicates, abstain_dest, gold)
    scored = _score(test, predicates, dest, gold)
    aprime = json.loads(APRIME_REPORT.read_text()) if APRIME_REPORT.is_file() else {}
    stored = json.loads(COMPARE.read_text()) if COMPARE.is_file() else {}
    plan_map = _plan_query_map(predicates, arm.accepted)
    base = {row["query_id"]: _product(row) for row in abstain.get("per_query") or []}
    query_changes = []
    for row in scored.get("per_query") or []:
        qid = row["query_id"]
        before = base.get(qid)
        after = _product(row)
        if before is None and after is None:
            continue
        if before == after:
            continue
        delta = None if before is None or after is None else after - before
        query_changes.append(
            {
                "query_id": qid,
                "aprime_product": before,
                "candidate_product": after,
                "delta": delta,
                "direction": "improved" if delta is not None and delta > 0 else "worsened" if delta is not None and delta < 0 else "changed",
                "accepted_plans": plan_map.get(qid, []),
            }
        )
    validator_n = arm.validator_agree + arm.validator_tie
    payload = {
        "budget": BUDGET,
        "model": DEFAULT_MODEL,
        "temperature": 0.1,
        "max_tokens": 280,
        "n_predicates": len(predicates),
        "n_presence": sum(1 for pred in predicates if is_presence(pred)),
        "n_membership": sum(1 for pred in predicates if is_membership(pred)),
        "candidates": {
            "tokens_spent": ledger.spent,
            "tokens_planner": arm.tokens_planner,
            "tokens_executor": arm.tokens_executor,
            "tokens_refiner": arm.tokens_refiner,
            "tokens_validator": arm.tokens_validator,
            "tokens_other": ledger.spent
            - (arm.tokens_planner + arm.tokens_executor + arm.tokens_refiner + arm.tokens_validator),
            "n_cohorts_attempted": arm.n_cohorts_attempted,
            "n_cohorts_accepted": arm.n_cohorts_accepted,
            "validator_agree": arm.validator_agree,
            "validator_tie": arm.validator_tie,
            "validator_agreement_rate": (arm.validator_agree / validator_n) if validator_n else None,
            "validator_tie_rate": (arm.validator_tie / validator_n) if validator_n else None,
            "grounded_ok": arm.grounded_ok,
            "grounded_n": arm.grounded_n,
            "grounded_span_rate": (arm.grounded_ok / arm.grounded_n) if arm.grounded_n else None,
            "resolved": resolved,
            "sample_true_false_null": {"true": arm.n_true, "false": arm.n_false, "null": arm.n_null},
            "n_conflicts": arm.n_conflicts,
            "cache_hits": arm.cache_hits,
            "cache_misses": arm.cache_misses,
            "accepted": arm.accepted,
            "query_deltas": arm.query_deltas,
            "sqlite_path": str(dest),
            **scored,
        },
        "abstain_all": {
            "tokens_spent": 0,
            "n_cohorts_accepted": 0,
            "sqlite_path": str(abstain_dest),
            **abstain,
        },
        "aprime_product": aprime.get("mean_per_query_product"),
        "aprime_structure_f2": aprime.get("mean_structure_f2"),
        "aprime_cell_f1_at_0.20": aprime.get("mean_cell_f1_at_0.20"),
        "fixed": {
            k: stored.get("fixed", {}).get(k)
            for k in (
                "tokens_spent",
                "mean_structure_f2",
                "mean_cell_f1_at_0.20",
                "mean_per_query_product",
            )
        },
        "agent": {
            k: stored.get("agent", {}).get(k)
            for k in (
                "tokens_spent",
                "mean_structure_f2",
                "mean_cell_f1_at_0.20",
                "mean_per_query_product",
            )
        },
        "query_product_changes": query_changes,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "candidate_validation.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "spent": ledger.spent,
                "attempted": arm.n_cohorts_attempted,
                "accepted": arm.n_cohorts_accepted,
                "product": scored["mean_per_query_product"],
                "structure_f2": scored["mean_structure_f2"],
                "cell_f1": scored["mean_cell_f1_at_0.20"],
                "abstain_product": abstain["mean_per_query_product"],
                "fixed_product": payload["fixed"].get("mean_per_query_product"),
                "agent_product": payload["agent"].get("mean_per_query_product"),
                "n_query_changes": len(query_changes),
            },
            indent=2,
        )
    )
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
