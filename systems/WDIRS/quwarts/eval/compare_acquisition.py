"""Matched-budget fixed vs agent acquisition. Gold only after both runs."""

from __future__ import annotations

import json
import shutil
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
from quwarts.core.signature_controller import run_acquisition
from quwarts.core.signature_populate import populate_signatures
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
OUT = ROOT / "results" / "quwarts_med_signatures"
BUDGET = 1_543_790
WORKERS = 8


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


def _run_arm(name: str, policy: str, predicates, docs, workload, statements, test, gold) -> dict:
    dest = OUT / "artifacts" / f"aprime_{name}.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(APRIME, dest)
    ledger = TokenLedger(theta=BUDGET, seed=42)
    caller = make_caller(ledger, model=DEFAULT_MODEL, max_tokens=280)
    print(f"{name} start theta={BUDGET}", flush=True)
    if policy == "fixed":
        pop = populate_signatures(dest, predicates, docs, caller, workload, workers=WORKERS)
        ctrl = None
        tokens_controller = 0
        extra = {
            "presence_true": pop.n_presence_true,
            "presence_null": pop.n_presence_null,
            "membership_true": pop.n_membership_true,
            "membership_false": pop.n_membership_false,
            "membership_null": pop.n_membership_null,
            "n_conflicts": pop.n_conflicts,
            "n_closed": pop.n_closed,
        }
    else:
        ctrl = run_acquisition(
            dest,
            predicates,
            policy="agent",
            documents=docs,
            caller=caller,
            workload=workload,
            statements=statements,
            max_steps=40,
        )
        extra = {
            "n_actions": len(ctrl.outcomes),
            "n_resolved": ctrl.n_resolved,
            "n_conflicts": ctrl.n_conflicts,
            "n_abstentions": ctrl.n_abstentions,
            "actions": [item.action.as_json() | {"tokens": item.tokens, "error": item.error} for item in ctrl.outcomes],
        }
        tokens_controller = ctrl.tokens_controller
    scored = _score(test, predicates, dest, gold)
    payload = {
        "policy": name,
        "tokens_spent": ledger.spent,
        "tokens_controller": tokens_controller,
        "tokens_operators": ledger.spent - tokens_controller,
        "sqlite_path": str(dest),
        **extra,
        **scored,
    }
    print(
        f"{name} spent={ledger.spent} product={payload['mean_per_query_product']:.4f}",
        flush=True,
    )
    return payload


def main() -> int:
    from diagnostics.run_config_grid import load_ground_truth

    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    statements = {row["query_id"]: row["sql"] for row in queries}
    _logical, workload = analyze_workload(statements)
    attach_amplification(workload)
    report = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    docs = documents_for("Med")
    gold = load_ground_truth(gold_name("Med"))
    aprime = json.loads(APRIME_REPORT.read_text()) if APRIME_REPORT.is_file() else {}
    fixed = _run_arm("fixed", "fixed", predicates, docs, workload, statements, test, gold)
    agent = _run_arm("agent", "agent", predicates, docs, workload, statements, test, gold)
    payload = {
        "budget": BUDGET,
        "model": DEFAULT_MODEL,
        "n_predicates": len(predicates),
        "n_presence": sum(1 for pred in predicates if is_presence(pred)),
        "n_membership": sum(1 for pred in predicates if is_membership(pred)),
        "aprime_product": aprime.get("mean_per_query_product"),
        "fixed": fixed,
        "agent": agent,
        "delta_product_agent_minus_fixed": (
            agent["mean_per_query_product"] - fixed["mean_per_query_product"]
        ),
        "delta_tokens_agent_minus_fixed": agent["tokens_spent"] - fixed["tokens_spent"],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "acquisition_compare.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({k: payload[k] for k in payload if k not in {"fixed", "agent"}}, indent=2))
    print("fixed", {k: fixed[k] for k in fixed if k != "per_query"})
    print("agent", {k: agent[k] for k in agent if k not in {"per_query", "actions"}})
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
