"""Rebuild A' from existing evidence. No new LLM calls."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.extract import EvidenceStore
from quwarts.core.ledger import TokenLedger
from quwarts.core.logical import extend_logical_schema
from quwarts.core.materialize import refresh_coverage_from_sqlite, refresh_schema_from_sqlite
from quwarts.core.models import FrozenPortfolio
from quwarts.core.pipeline import rematerialize_databases, serve_plans
from quwarts.core.population import merge_audit
from quwarts.core.repair.diagnose import diagnose_empty_queries
from quwarts.core.repair.detectors import detect_empty_queries
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import (
    documents_for,
    gold_name,
    queries_for,
    score_with_rewrites,
)

SRC = ROOT / "results" / "quwarts_med_repair80_diag"
SCORE_PORTFOLIO = ROOT / "results" / "quwarts_med_repair_round"
OUT = ROOT / "results" / "quwarts_med_aprime"
UNIQUE_STEMS = {"institution": 99, "drug": 98, "disease": 100}


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_sha(path: Path) -> str:
    con = sqlite3.connect(path)
    digest = hashlib.sha256()
    try:
        for (table,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%' ORDER BY 1"
        ):
            digest.update(table.encode())
            cols = [info[1] for info in con.execute(f"PRAGMA table_info({_q(table)})")]
            digest.update("|".join(cols).encode())
            for row in con.execute(f"SELECT * FROM {_q(table)} ORDER BY 1"):
                digest.update(repr(row).encode())
    finally:
        con.close()
    return digest.hexdigest()


def load_portfolio() -> FrozenPortfolio:
    manifest = json.loads((SRC / "artifacts" / "runs" / "manifest.json").read_text())
    fields = {name: manifest[name] for name in FrozenPortfolio.model_fields if name in manifest}
    return FrozenPortfolio.model_validate(fields)


def publish(portfolio: FrozenPortfolio, statements: dict[str, str]) -> None:
    portfolio.logical_schema = extend_logical_schema(portfolio.logical_schema, statements.values())
    for config, db in zip(portfolio.configurations, portfolio.databases):
        refresh_schema_from_sqlite(config.schema_, db.sqlite_path)
        db.coverage = refresh_coverage_from_sqlite(db.coverage, db.sqlite_path)


def table_counts(db: Path) -> dict[str, int]:
    con = sqlite3.connect(db)
    try:
        return {
            name: con.execute(f"SELECT COUNT(*) FROM {_q(name)}").fetchone()[0]
            for (name,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
            )
        }
    finally:
        con.close()


def empty_causes(portfolio, statements, store, workload) -> dict:
    empty = detect_empty_queries(portfolio, statements)
    plans = serve_plans(portfolio, statements)
    diagnoses = diagnose_empty_queries(empty, statements, plans, store=store, workload=workload)
    causes: dict[str, int] = {}
    for item in diagnoses:
        causes[item.cause] = causes.get(item.cause, 0) + 1
    return {"n": len(empty), "causes": causes}


def rematerialize_once(dest: Path, portfolio, store, workload, documents, ledger):
    dest.mkdir(parents=True, exist_ok=True)
    dbs = rematerialize_databases(
        store=store,
        workload=workload,
        documents=documents,
        configs=portfolio.configurations,
        db_dir=dest,
        ledger=ledger,
        identity_report={},
        overwrite=True,
    )
    return dbs, list(merge_audit())


def main() -> int:
    from diagnostics.run_config_grid import load_ground_truth

    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    train_sql = {row["query_id"]: row["sql"] for row in train}
    test_sql = {row["query_id"]: row["sql"] for row in test}
    documents = documents_for("Med")
    gold = load_ground_truth(gold_name("Med"))
    store = EvidenceStore(SRC / "artifacts" / "evidence")
    portfolio = load_portfolio()
    _, workload = analyze_workload(train_sql, portfolio.logical_schema)
    spent0 = int(json.loads((SRC / "artifacts" / "runs" / "manifest.json").read_text()).get("tokens_spent") or 0)
    ledger = TokenLedger(theta=spent0 or 1, seed=42)
    ledger.spent = spent0

    first_dir = OUT / "artifacts" / "databases"
    second_dir = OUT / "artifacts" / "databases_repeat"
    dbs, audits = rematerialize_once(first_dir, portfolio, store, workload, documents, ledger)
    portfolio.databases[:] = dbs
    publish(portfolio, {**train_sql, **test_sql})
    spent_after = ledger.spent
    repeat_dbs, _ = rematerialize_once(second_dir, portfolio, store, workload, documents, ledger)
    det = {
        "dump_sha_first": dump_sha(Path(dbs[0].sqlite_path)),
        "dump_sha_second": dump_sha(Path(repeat_dbs[0].sqlite_path)),
        "file_sha_first": file_sha(Path(dbs[0].sqlite_path)),
        "file_sha_second": file_sha(Path(repeat_dbs[0].sqlite_path)),
    }
    det["byte_identical_rows"] = det["dump_sha_first"] == det["dump_sha_second"]

    pred = Path(dbs[0].sqlite_path)
    counts = table_counts(pred)
    base = {
        table: {
            "gold_unique_stems": UNIQUE_STEMS[table],
            "aprime": counts.get(table),
            "recall": (counts.get(table) or 0) / UNIQUE_STEMS[table],
        }
        for table in UNIQUE_STEMS
    }
    test_report = score_with_rewrites(test, serve_plans(portfolio, test_sql), pred, gold, "Med")
    train_report = score_with_rewrites(train, serve_plans(portfolio, train_sql), pred, gold, "Med")
    payload = {
        "tokens_spent_new": spent_after - spent0,
        "tokens_spent_ledger": spent_after,
        "base_relation_counts": base,
        "mean_structure_f2": float(test_report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(test_report),
        "mean_per_query_product": mean_per_query_product(test_report),
        "train_empty": empty_causes(portfolio, train_sql, store, workload),
        "test_empty": empty_causes(portfolio, test_sql, store, analyze_workload(test_sql)[1]),
        "merges": {
            "n": len(audits),
            "justification_counts": {
                row["justification"]: sum(1 for item in audits if item["justification"] == row["justification"])
                for row in audits
            },
            "rows": audits,
        },
        "determinism": det,
        "sqlite_path": str(pred),
        "test_empty_query_count": sum(
            1 for row in test_report.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "aprime_report.json").write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({k: payload[k] for k in payload if k != "merges" or True}, indent=2, default=str)[:4000])
    print(json.dumps({
        "wrote": str(OUT / "aprime_report.json"),
        "base": base,
        "structure_f2": payload["mean_structure_f2"],
        "cell_f1_20": payload["mean_cell_f1_at_0.20"],
        "product": payload["mean_per_query_product"],
        "train_empty": payload["train_empty"],
        "test_empty": payload["test_empty"],
        "merges_n": payload["merges"]["n"],
        "tokens_new": payload["tokens_spent_new"],
        "determinism": det,
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
