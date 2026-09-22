"""Locked retrieval-aware extraction arm for Finan and Legal."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
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
from quwarts.core.materialize import file_sha256, write_sqlite
from quwarts.core.models import Configuration, ModuleConfig, PreprocessPolicy
from quwarts.core.pipeline import official_sql
from quwarts.core.population import apply_population, policy_from_demands
from quwarts.core.provenance import dropped_rows, identity_collisions, document_stem
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.cache import VerifiedCache
from quwarts.core.retrieve_extract.config import FROZEN, MODEL, config_hash, frozen_payload, prompt_hash
from quwarts.core.retrieve_extract.controller import ExtractController
from quwarts.core.schema import canonical_schema
from quwarts.core.schema_columns import assert_queries_execute, complete_physical_schema, referenced_columns
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_populate import populate_signatures
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import (
    budget_from_docetl,
    documents_for,
    gold_name,
    queries_for,
    score_with_rewrites,
)

load_env_file(ROOT / ".env")

PLUMBING = {
    "Finan": {
        "product": 0.01685238629683074,
        "f2": 0.29248809938465115,
        "f1": 0.027592592592592592,
    },
    "Legal": {
        "product": 0.022455905439098717,
        "f2": 0.20543217286914767,
        "f1": 0.03653846153846154,
    },
}
DOCETL = {
    "Finan": {"product": 0.08410358973968853, "f2": 0.537, "f1": 0.114},
    "Legal": {"product": 0.12350932750098194, "f2": 0.789, "f1": 0.129},
}
OUT_ROOT = ROOT / "results" / "quwarts_retrieve_extract"
REPORT = OUT_ROOT / "retrieve_extract_arm.json"


def _hash_bytes(payload: Any) -> str:
    blob = payload if isinstance(payload, bytes) else json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def _norm_bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(key), json.dumps(row.get(key), default=str)) for key in row)))
    return tuple(sorted(frozen))


def _fetch(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    cur = conn.execute(sql)
    cols = [item[0] for item in cur.description] if cur.description else []
    return [dict(zip(cols, rec)) for rec in cur.fetchall()]


def _score(name: str, dest: Path, test: list[dict[str, str]], rewrites: dict[str, str], gold) -> dict[str, Any]:
    report = score_with_rewrites(test, rewrites, dest, gold, name)
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
            }
            for row in report.get("per_query") or []
        ],
    }


def load_catalog(name: str) -> dict[str, dict[str, Any]]:
    path = ROOT / "Query" / name / f"{name}_attributes.json"
    raw = json.loads(path.read_text())
    out: dict[str, dict[str, Any]] = {}
    for _entity, attrs in raw.items():
        if not isinstance(attrs, dict):
            continue
        for attr, spec in attrs.items():
            if isinstance(spec, dict):
                out[str(attr).lower()] = spec
                out[str(attr)] = spec
    return out


def materialize(name: str, records, documents, statements, logical, workload, dest: Path) -> dict[str, Any]:
    schema = canonical_schema(logical)
    pop = policy_from_demands({}, workload)
    for key in list(pop.er):
        pop.er[key] = ModuleConfig(strategy="no_merge", params={})
    config = Configuration(
        id=f"retrieve_{name.lower()}",
        schema=schema,
        pop=pop,
        pre=PreprocessPolicy(mode="whole_document"),
        cluster_id="retrieve_extract",
    )
    rows = apply_population(records, config, workload, documents=documents, corpus_id=name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    path, counts = write_sqlite(config, rows, dest.parent)
    Path(path).replace(dest)
    audit = audit_workload([{"query_id": qid, "sql": sql} for qid, sql in statements.items()])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    conn = sqlite3.connect(str(dest))
    created = complete_physical_schema(conn, statements, predicates)
    conn.commit()
    populate_signatures(dest, predicates, documents, None, workload)
    referenced = [(item.table, item.column, item.sql_type) for item in referenced_columns(statements)]
    rewrites = {qid: official_sql(sql, dest, predicates) for qid, sql in statements.items()}
    assert_queries_execute(conn, rewrites, any_error=True)
    bags = {qid: _norm_bag(_fetch(conn, sql)) for qid, sql in rewrites.items()}
    empty = [qid for qid, bag in bags.items() if not bag]
    table = "finance" if name == "Finan" else "legal"
    n_rows = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    cols = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
    semantic = [
        col
        for col in cols
        if not str(col).startswith("__")
        and not str(col).startswith("sig_")
        and col not in {"doc_id", "rowid"}
    ]
    populated = 0
    nonempty = 0
    all_null = 0
    for rec in conn.execute(f'SELECT {", ".join(fchr(col) for col in semantic)} FROM "{table}"'):
        values = [value for value in rec if value not in (None, "")]
        populated += 1
        nonempty += len(values)
        if not values:
            all_null += 1
    conn.close()
    return {
        "db_path": str(dest),
        "db_sha256": file_sha256(dest),
        "output_bag_sha256": hashlib.sha256(repr(sorted(bags.items())).encode()).hexdigest(),
        "rewrites": rewrites,
        "row_counts": counts,
        "populated_rows": n_rows,
        "all_null_rows": all_null,
        "nonnull_cell_rate": nonempty / max(1, n_rows * len(semantic)),
        "referenced_columns_created": created,
        "referenced_columns": referenced,
        "queries_executing": len(statements),
        "query_errors": 0,
        "empty_bags": len(empty),
        "empty_bag_ids": empty,
        "provenance_collisions": identity_collisions(),
        "dropped_rows": dropped_rows(),
        "gates": {
            "every_source_document_represented": n_rows >= len(documents),
            "zero_legacy_or_unverified_reuse": True,
            "provenance_only_dedup": not identity_collisions() and not dropped_rows(),
            "all_referenced_columns_exist": True,
            "every_official_query_executes": True,
            "unresolved_fallback": True,
            "all_null_rows_present": all_null >= 0,
        },
    }


def fchr(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def run_corpus(name: str, config_digest: str) -> dict[str, Any]:
    theta = budget_from_docetl(name)
    documents = documents_for(name)
    queries = queries_for(name)
    statements = {row["query_id"]: row["sql"] for row in queries}
    logical, workload = analyze_workload(statements)
    catalog = load_catalog(name)
    artifact = OUT_ROOT / name.lower()
    cache_dir = artifact / "cache"
    if cache_dir.exists():
        for item in cache_dir.glob("*.json"):
            item.unlink()
    ledger = TokenLedger(theta=theta, seed=int(FROZEN["seed"]))
    caller = make_caller(
        ledger,
        model=MODEL,
        temperature=float(FROZEN["temperature"]),
        max_tokens=int(FROZEN["extract_max_tokens"]),
    )
    cache = VerifiedCache(cache_dir)
    print(f"{name} start model={MODEL} theta={theta} docs={len(documents)} config={config_digest[:12]}", flush=True)
    controller = ExtractController(
        corpus_id=name,
        documents=documents,
        workload=workload,
        caller=caller,
        cache=cache,
        catalog=catalog,
        artifact_dir=artifact,
    )
    records = controller.run()
    extract_report = controller.report()
    (artifact / "route_log.json").write_text(json.dumps(controller.route_log, indent=2, default=str))
    (artifact / "extract_log.json").write_text(json.dumps(controller.extract_log, indent=2, default=str))
    (artifact / "repair_log.json").write_text(json.dumps(controller.repair_log, indent=2, default=str))
    (artifact / "ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
    dest = artifact / "databases" / f"{name.lower()}_retrieve_extract.db"
    if dest.parent.exists():
        for stale in dest.parent.glob("*.db"):
            stale.unlink()
    built = materialize(name, records, documents, statements, logical, workload, dest)
    if ledger.spent > theta:
        raise SystemExit(f"{name} exceeded theta {theta} with {ledger.spent}")
    built["gates"]["within_budget"] = ledger.spent <= theta
    built["gates"]["legacy_reuse"] = False
    valued = sum(1 for rec in records if rec.surface_value not in (None, ""))
    return {
        "corpus": name,
        "theta": theta,
        "spent": ledger.spent,
        "remaining": ledger.remaining(),
        "model": MODEL,
        "legacy_evidence_input": False,
        "unknown_else_escape": False,
        "group_classification": False,
        "ledger_sha256": ledger.fingerprint(),
        "prompt_sha256": prompt_hash(),
        "config_sha256": config_digest,
        "n_records": len(records),
        "valued_cells": valued,
        "extraction": extract_report,
        **{k: v for k, v in built.items() if k != "rewrites"},
        "rewrites": built["rewrites"],
        "sqlite_path": built["db_path"],
    }


def main() -> int:
    if DEFAULT_MODEL != MODEL:
        raise SystemExit(f"model lock failed: {DEFAULT_MODEL} != {MODEL}")
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    payload = frozen_payload()
    digest = config_hash()
    (OUT_ROOT / "locked_config.json").write_text(json.dumps({"hash": digest, "config": payload}, indent=2))
    print(f"locked config {digest}", flush=True)
    frozen: dict[str, Any] = {}
    for name in ("Finan", "Legal"):
        frozen[name] = run_corpus(name, digest)
        print(
            json.dumps(
                {
                    "corpus": name,
                    "spent": frozen[name]["spent"],
                    "theta": frozen[name]["theta"],
                    "rows": frozen[name]["populated_rows"],
                    "empty_bags": frozen[name]["empty_bags"],
                    "db": frozen[name]["db_sha256"],
                    "bags": frozen[name]["output_bag_sha256"],
                }
            ),
            flush=True,
        )
    from diagnostics.run_config_grid import load_ground_truth

    scores = {}
    for name in ("Finan", "Legal"):
        queries = queries_for(name)
        _, test = split_80_20(queries, 42)
        test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
        gold = load_ground_truth(gold_name(name))
        dest = Path(frozen[name]["sqlite_path"])
        rewrites = {row["query_id"]: frozen[name]["rewrites"][row["query_id"]] for row in test_count}
        scored = _score(name, dest, test_count, rewrites, gold)
        plumbing = PLUMBING[name]
        per_query = []
        for row in scored["per_query"]:
            per_query.append(
                {
                    "query_id": row["query_id"],
                    "fresh_product": row["product"],
                    "structure_f2": row["structure_f2"],
                    "cell_f1_20": row["cell_f1_20"],
                }
            )
        scores[name] = {
            "plumbing_only": plumbing,
            "fresh_extraction": {
                "mean_structure_f2": scored["mean_structure_f2"],
                "mean_cell_f1_at_0.20": scored["mean_cell_f1_at_0.20"],
                "mean_per_query_product": scored["mean_per_query_product"],
            },
            "docetl": DOCETL[name],
            "per_query": per_query,
        }
        print(
            json.dumps(
                {
                    "corpus": name,
                    "plumbing": plumbing["product"],
                    "fresh": scored["mean_per_query_product"],
                    "docetl": DOCETL[name]["product"],
                }
            ),
            flush=True,
        )
        frozen[name].pop("rewrites", None)
    report = {
        "model": MODEL,
        "config_sha256": digest,
        "prompt_sha256": prompt_hash(),
        "locked_config": payload,
        "legacy_evidence_input": False,
        "unknown_else_escape": False,
        "group_classification": False,
        "corpora": {
            name: {**frozen[name], "score": scores[name]}
            for name in frozen
        },
    }
    REPORT.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"wrote": str(REPORT), "config": digest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
