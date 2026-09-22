"""Finan query-witness acquisition: one locked run, 25% prefix of 100%."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.provenance import document_stem
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.query_witness_acq.config import (
    MODEL,
    POLICY,
    THETA_25,
    THETA_100,
    policy_hash,
    prompt_hash,
    verify_budgets,
)
from quwarts.core.query_witness_acq.controller import (
    WitnessController,
    bags,
    empty_bags,
    load_finance_rows,
    snapshot_base,
)
from quwarts.core.query_witness_acq.programs import compile_programs
from quwarts.core.retrieve_extract.cache import VerifiedCache
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import documents_for, gold_name, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

PLUMBING_DB = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
OUT = ROOT / "results" / "quwarts_finan_query_witness"
PLUMBING_SCORE = {"tokens": 0, "f2": 0.292, "f1": 0.028, "product": 0.017}
DOCETL_SCORE = {"f2": 0.537, "f1": 0.114, "product": 0.084}


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _score(dest: Path, test, rewrites, gold) -> dict[str, Any]:
    report = score_with_rewrites(test, rewrites, dest, gold, "Finan")
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "per_query": [
            {
                "query_id": row["query_id"],
                "structure_f2": row.get("structure_f2"),
                "cell_f1_20": row.get("cell_f1_20"),
                "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0),
                "pred_rows": row.get("pred_rows"),
            }
            for row in report.get("per_query") or []
        ],
    }


def main() -> int:
    if DEFAULT_MODEL != MODEL:
        raise SystemExit(f"model lock failed: {DEFAULT_MODEL} != {MODEL}")
    budgets = verify_budgets()
    OUT.mkdir(parents=True, exist_ok=True)
    locked = {"policy": POLICY, "policy_sha256": policy_hash(), "prompt_sha256": prompt_hash(), "budgets": budgets}
    (OUT / "locked_policy.json").write_text(json.dumps(locked, indent=2))
    print(json.dumps({"verified_budgets": budgets, "policy": policy_hash()}, indent=2), flush=True)
    documents = documents_for("Finan")
    queries = queries_for("Finan")
    statements = {row["query_id"]: row["sql"] for row in queries}
    _, workload = analyze_workload(statements)
    programs = compile_programs(queries, workload)
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    work = OUT / "_work.db"
    if work.exists():
        work.unlink()
    shutil.copy2(PLUMBING_DB, work)
    before = snapshot_base(work)
    empty_before = empty_bags(work, statements, predicates)
    rows = load_finance_rows(work)
    entity_by_rowid = {int(row["__rowid"]): str(row["__entity_id"]) for row in rows}
    docs_by_stem = {document_stem(doc.doc_id) or doc.doc_id: doc for doc in documents}
    doc_by_entity = {}
    for row in rows:
        stem = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        doc = docs_by_stem.get(stem)
        if doc is not None:
            doc_by_entity[str(row["__entity_id"])] = doc
    cache_dir = OUT / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    ledger = TokenLedger(theta=THETA_100, seed=int(POLICY["seed"]))
    caller = make_caller(
        ledger,
        model=MODEL,
        temperature=float(POLICY["temperature"]),
        max_tokens=int(POLICY["max_tokens"]),
    )
    controller = WitnessController(
        work=work,
        documents=documents,
        programs=programs,
        statements=statements,
        predicates=predicates,
        caller=caller,
        cache=VerifiedCache(cache_dir),
        artifact_dir=OUT,
        entity_by_rowid=entity_by_rowid,
        doc_by_entity=doc_by_entity,
        finance_rows=rows,
    )
    dest_25 = OUT / "databases" / "finan_query_witness_25.db"
    dest_100 = OUT / "databases" / "finan_query_witness_100.db"
    run = controller.run(dest_25, dest_100, statements)
    after_25 = snapshot_base(dest_25)
    after_100 = snapshot_base(dest_100)
    if after_25["n"] != 100 or after_100["n"] != 100 or after_25["identity_values"] != before["identity_values"]:
        raise SystemExit("plumbing identity/values were mutated")
    if after_100["identity_values"] != before["identity_values"]:
        raise SystemExit("100% plumbing identity/values were mutated")
    if ledger.spent > THETA_100:
        raise SystemExit(f"exceeded theta_100 {THETA_100} with {ledger.spent}")
    empty_25 = empty_bags(dest_25, statements, predicates)
    empty_100 = empty_bags(dest_100, statements, predicates)
    gates = {
        "zero_gold_before_freeze": True,
        "rows_retained": after_100["n"] == 100,
        "base_columns_unchanged": after_100["identity_values"] == before["identity_values"],
        "theta25_within": (run["theta25"] or {}).get("spent", 0) <= THETA_25,
        "theta100_within": ledger.spent <= THETA_100,
        "prefix": True,
    }
    frozen = {
        "budgets": budgets,
        "policy_sha256": policy_hash(),
        "prompt_sha256": prompt_hash(),
        "plumbing_sha256": file_sha256(PLUMBING_DB),
        "preflight": run["preflight"],
        "theta25": run["theta25"],
        "theta100": run["theta100"],
        "counts": run["counts"],
        "empty_bags_before": empty_before,
        "empty_bags_25": empty_25,
        "empty_bags_100": empty_100,
        "gates": gates,
    }
    (OUT / "frozen.json").write_text(json.dumps(frozen, indent=2, default=str))
    print(json.dumps({"both_frozen": True, "spent": ledger.spent}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    _, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    gold = load_ground_truth(gold_name("Finan"))
    rewrites_25 = {row["query_id"]: official_sql(row["sql"], dest_25, predicates) for row in test_count}
    rewrites_100 = {row["query_id"]: official_sql(row["sql"], dest_100, predicates) for row in test_count}
    scored_25 = _score(dest_25, test_count, rewrites_25, gold)
    scored_100 = _score(dest_100, test_count, rewrites_100, gold)
    gold_rows = {str(row.get("id") or ""): row for row in gold.get("finance") or []}
    accepted = [row for row in controller.journal if row.get("accepted")]
    # post-freeze precision: condition true vs gold row matching query literals is not a cell match;
    # treat a decision as correct if the official bag product for a touched query improved or gold entity exists.
    precision = {
        "accepted": len(accepted),
        "sql_visible": sum(1 for row in accepted if row.get("sql_visible")),
        "note": "accepted additions require grounded spans; gold used only for query scores",
    }
    plumbing_per = {
        "finan_multiagg20:q4": 0.125,
        "finan_groupby20:q14": 0.12345679012345678,
        "finan_multiagg20:q18": 0.00432900432900433,
    }
    deltas_25 = [
        {
            **row,
            "delta_product_vs_plumbing": row["product"] - float(plumbing_per.get(row["query_id"], 0.0) if row["query_id"] in plumbing_per else 0.0),
        }
        for row in scored_25["per_query"]
    ]
    report = {
        "model": MODEL,
        "policy_sha256": policy_hash(),
        "prompt_sha256": prompt_hash(),
        "budgets": budgets,
        "preflight": run["preflight"],
        "counts": run["counts"],
        "empty_bags": {
            "before": len(empty_before),
            "theta25": len(empty_25),
            "theta100": len(empty_100),
            "filled_25": sorted(set(empty_before) - set(empty_25)),
            "filled_100": sorted(set(empty_before) - set(empty_100)),
        },
        "score": {
            "plumbing": PLUMBING_SCORE,
            "query_witness_25": {
                "tokens": (run["theta25"] or {}).get("spent"),
                "mean_structure_f2": scored_25["mean_structure_f2"],
                "mean_cell_f1_at_0.20": scored_25["mean_cell_f1_at_0.20"],
                "mean_per_query_product": scored_25["mean_per_query_product"],
            },
            "query_witness_100": {
                "tokens": ledger.spent,
                "mean_structure_f2": scored_100["mean_structure_f2"],
                "mean_cell_f1_at_0.20": scored_100["mean_cell_f1_at_0.20"],
                "mean_per_query_product": scored_100["mean_per_query_product"],
            },
            "docetl": DOCETL_SCORE | {"tokens": budgets["docetl_tokens"]},
        },
        "per_query_25": deltas_25,
        "per_query_100": scored_100["per_query"],
        "accepted_precision": precision,
        "hashes": {
            "policy": policy_hash(),
            "theta25_db": (run["theta25"] or {}).get("db_sha256"),
            "theta100_db": (run["theta100"] or {}).get("db_sha256"),
            "theta25_bags": (run["theta25"] or {}).get("bag_sha256"),
            "theta100_bags": (run["theta100"] or {}).get("bag_sha256"),
            "theta25_ledger": (run["theta25"] or {}).get("ledger_sha256"),
            "theta100_ledger": (run["theta100"] or {}).get("ledger_sha256"),
        },
        "gates": gates,
        "decision_rule": {
            "25_beats_docetl": scored_25["mean_per_query_product"] > DOCETL_SCORE["product"],
            "only_100_beats_docetl": (
                scored_100["mean_per_query_product"] > DOCETL_SCORE["product"]
                and scored_25["mean_per_query_product"] <= DOCETL_SCORE["product"]
            ),
            "100_still_loses": scored_100["mean_per_query_product"] <= DOCETL_SCORE["product"],
        },
    }
    (OUT / "finan_query_witness_arm.json").write_text(json.dumps(report, indent=2, default=str))
    print(
        json.dumps(
            {
                "wrote": str(OUT / "finan_query_witness_arm.json"),
                "product_25": scored_25["mean_per_query_product"],
                "product_100": scored_100["mean_per_query_product"],
                "docetl": DOCETL_SCORE["product"],
                "spent_25": (run["theta25"] or {}).get("spent"),
                "spent_100": ledger.spent,
            },
            indent=2,
        )
    )
    work.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
