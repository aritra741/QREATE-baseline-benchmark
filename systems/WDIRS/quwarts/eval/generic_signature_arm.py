"""Generic signature arm. Thin wrapper around the live populate path."""

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


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def snapshot_nonsig(path: Path) -> dict:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        payload = {}
        for (table,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
        ):
            cols = [row[1] for row in conn.execute(f"PRAGMA table_info({_q(table)})")]
            kept = [name for name in cols if not str(name).startswith("sig_")]
            rows = [dict(row) for row in conn.execute(f"SELECT * FROM {_q(table)}")]
            payload[table] = {
                "n": len(rows),
                "keys": [row.get("doc_id") for row in rows],
                "nonsig": [{name: row.get(name) for name in kept} for row in rows],
            }
        return payload
    finally:
        conn.close()


def main() -> int:
    from diagnostics.run_config_grid import load_ground_truth

    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    statements = {row["query_id"]: row["sql"] for row in queries}
    logical, workload = analyze_workload(statements)
    attach_amplification(workload)
    report = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    docs = documents_for("Med")
    dest = OUT / "artifacts" / "aprime_generic_sig.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(APRIME, dest)
    before = snapshot_nonsig(APRIME)

    ledger = TokenLedger(theta=BUDGET, seed=42)
    caller = make_caller(ledger, model=DEFAULT_MODEL, max_tokens=280)
    print(
        f"generic arm predicates={len(predicates)} "
        f"presence={sum(1 for pred in predicates if is_presence(pred))} "
        f"membership={sum(1 for pred in predicates if is_membership(pred))} "
        f"theta={BUDGET}",
        flush=True,
    )
    pop = populate_signatures(
        dest, predicates, docs, caller, workload, workers=WORKERS,
    )
    after = snapshot_nonsig(dest)
    preserved = before == after

    gold = load_ground_truth(gold_name("Med"))
    rewrites = {row["query_id"]: rewrite_sql(row["sql"], predicates) for row in test}
    test_report = score_with_rewrites(test, rewrites, dest, gold, "Med")
    aprime = json.loads(APRIME_REPORT.read_text()) if APRIME_REPORT.is_file() else {}

    payload = {
        "arm": "generic_all_eligible",
        "n_predicates": len(predicates),
        "n_presence": sum(1 for pred in predicates if is_presence(pred)),
        "n_membership": sum(1 for pred in predicates if is_membership(pred)),
        "full_value_required": report.full_value_required,
        "budget": BUDGET,
        "tokens_spent": ledger.spent,
        "presence": {
            "jobs": pop.n_presence_jobs,
            "true": pop.n_presence_true,
            "null": pop.n_presence_null,
            "tokens": pop.tokens_presence,
        },
        "membership": {
            "jobs": pop.n_membership_jobs,
            "true": pop.n_membership_true,
            "false": pop.n_membership_false,
            "null": pop.n_membership_null,
            "tokens": pop.tokens_membership,
        },
        "n_conflicts": pop.n_conflicts,
        "n_closed": pop.n_closed,
        "closed": pop.closed,
        "aprime_nonsig_preserved": preserved,
        "mean_structure_f2": float(test_report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(test_report),
        "mean_per_query_product": mean_per_query_product(test_report),
        "vs_aprime": {
            "structure_f2": float(test_report.get("mean_structure_f2") or 0.0)
            - float(aprime.get("mean_structure_f2") or 0.0),
            "cell_f1_20": mean_cell_f1_20(test_report)
            - float(aprime.get("mean_cell_f1_at_0.20") or 0.0),
            "product": mean_per_query_product(test_report)
            - float(aprime.get("mean_per_query_product") or 0.0),
        },
        "sqlite_path": str(dest),
        "model": DEFAULT_MODEL,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "generic_arm.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
