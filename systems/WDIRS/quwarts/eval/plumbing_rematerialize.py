"""Plumbing-only rematerialize of frozen Legal/Finan evidence. No model calls."""

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

from quwarts.core.extract import EvidenceStore
from quwarts.core.materialize import file_sha256, write_sqlite
from quwarts.core.models import Configuration, ModuleConfig, PreprocessPolicy, SourceDocument
from quwarts.core.pipeline import official_sql
from quwarts.core.population import apply_population, policy_from_demands
from quwarts.core.provenance import (
    PROVENANCE_COL,
    document_stem,
    dropped_rows,
    identity_collisions,
)
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.schema import canonical_schema
from quwarts.core.schema_columns import (
    MissingColumnError,
    assert_queries_execute,
    complete_physical_schema,
    referenced_columns,
)
from quwarts.core.search import config_id
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_populate import populate_signatures
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import (
    documents_for,
    gold_name,
    queries_for,
    score_with_rewrites,
)

OLD = {
    "Finan": {
        "db": ROOT / "results" / "quwarts_finan_compiler80" / "artifacts" / "databases" / "dd4a7e27fc9a7d08.db",
        "evidence": ROOT / "results" / "quwarts_finan_compiler80" / "artifacts" / "evidence",
        "product": 0.03302469135802469,
        "f2": 0.14074074074074075,
        "f1": 0.05277777777777778,
        "rows": 68,
    },
    "Legal": {
        "db": ROOT / "results" / "quwarts_legal_compiler80" / "artifacts" / "databases" / "24310a52370ec2c0.db",
        "evidence": ROOT / "results" / "quwarts_legal_compiler80" / "artifacts" / "evidence",
        "product": 0.022128851540616248,
        "f2": 0.16228991596638656,
        "f1": 0.03333333333333334,
        "rows": 258,
    },
}
DOCETL = {
    "Finan": {"product": 0.08410358973968853, "f2": 0.537, "f1": 0.114},
    "Legal": {"product": 0.12350932750098194, "f2": 0.789, "f1": 0.129},
}
OUT = ROOT / "results" / "quwarts_holdout_group" / "plumbing_rematerialize.json"


def _hash_dir(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.glob("*.json")):
        digest.update(item.name.encode())
        digest.update(item.read_bytes())
    return digest.hexdigest()


def _norm_bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(key), json.dumps(row.get(key), default=str)) for key in row)))
    return tuple(sorted(frozen))


def _fetch(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    cur = conn.execute(sql)
    cols = [item[0] for item in cur.description] if cur.description else []
    return [dict(zip(cols, rec)) for rec in cur.fetchall()]


def _user_count(path: Path, table: str) -> int:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    finally:
        conn.close()


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


def _old_query_errors(name: str, predicates) -> dict[str, Any]:
    import shutil
    import tempfile

    src = OLD[name]["db"]
    tmp = Path(tempfile.mkdtemp(prefix=f"old_{name}_"))
    path = tmp / src.name
    shutil.copy2(src, path)
    queries = queries_for(name)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    errors = []
    empty = []
    ok = 0
    for row in queries:
        sql = official_sql(row["sql"], path, predicates)
        try:
            rows = _fetch(conn, sql)
        except Exception as exc:
            errors.append({"query_id": row["query_id"], "error": str(exc)})
            continue
        ok += 1
        if not rows:
            empty.append(row["query_id"])
    conn.close()
    shutil.rmtree(tmp, ignore_errors=True)
    return {"n_ok": ok, "n_error": len(errors), "n_empty": len(empty), "errors": errors, "empty": empty}


def rematerialize(name: str) -> dict[str, Any]:
    spec = OLD[name]
    documents = [
        doc.model_copy(update={"metadata": {**doc.metadata, "corpus": name}})
        for doc in documents_for(name)
    ]
    queries = queries_for(name)
    statements = {row["query_id"]: row["sql"] for row in queries}
    logical, workload = analyze_workload(statements)
    evidence_digest = _hash_dir(spec["evidence"])
    store = EvidenceStore(spec["evidence"])
    records = list(store.records.values())
    valued_docs = {
        document_stem(rec.doc_id)
        for rec in records
        if rec.surface_value not in (None, "")
    }
    schema = canonical_schema(logical)
    pop = policy_from_demands({}, workload)
    for key in list(pop.er):
        pop.er[key] = ModuleConfig(strategy="no_merge", params={})
    config = Configuration(
        id=f"plumbing_{name.lower()}",
        schema=schema,
        pop=pop,
        pre=PreprocessPolicy(mode="whole_document"),
        cluster_id="plumbing",
    )
    rows = apply_population(records, config, workload, documents=documents, corpus_id=name)
    all_null = []
    for row in rows:
        semantic = [
            value
            for key, value in row.items()
            if not str(key).startswith("__") and key != "doc_id" and value not in (None, "")
        ]
        if not semantic:
            all_null.append(document_stem(str(row.get("doc_id") or "")))
    old_stems = set()
    old_conn = sqlite3.connect(f"file:{spec['db']}?mode=ro", uri=True)
    table = "finance" if name == "Finan" else "legal"
    if "doc_id" in {row[1] for row in old_conn.execute(f'PRAGMA table_info("{table}")')}:
        old_stems = {
            document_stem(str(row[0]))
            for row in old_conn.execute(f'SELECT doc_id FROM "{table}"')
            if row[0]
        }
    old_conn.close()
    recovered = sorted(valued_docs - old_stems)
    out_dir = ROOT / "results" / f"quwarts_{name.lower()}_plumbing" / "artifacts" / "databases"
    if out_dir.exists():
        for stale in out_dir.glob("*.db"):
            stale.unlink()
    path, counts = write_sqlite(config, rows, out_dir)
    dest = out_dir / f"{name.lower()}_plumbing.db"
    if dest.exists():
        dest.unlink()
    Path(path).replace(dest)
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    conn = sqlite3.connect(str(dest))
    created = complete_physical_schema(conn, statements, predicates)
    conn.commit()
    populate_signatures(dest, predicates, documents, None, workload)
    referenced = [(item.table, item.column, item.sql_type) for item in referenced_columns(statements)]
    sig_cols = sorted(
        {
            row[1]
            for table, in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            for row in conn.execute(f'PRAGMA table_info("{table}")')
            if str(row[1]).startswith("sig_")
        }
    )
    rewrites = {row["query_id"]: official_sql(row["sql"], dest, predicates) for row in queries}
    assert_queries_execute(conn, rewrites, any_error=True)
    bags = {qid: _norm_bag(_fetch(conn, sql)) for qid, sql in rewrites.items()}
    empty = [qid for qid, bag in bags.items() if not bag]
    new_rows = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    conn.close()
    db_hash = file_sha256(dest)
    bag_hash = hashlib.sha256(repr(sorted(bags.items())).encode()).hexdigest()
    old_exec = _old_query_errors(name, predicates)
    return {
        "corpus": name,
        "legacy_evidence_hash": evidence_digest,
        "legacy_evidence_n": len(records),
        "lookups": 0,
        "hit_rate": "not_applicable",
        "legacy_evidence_input": True,
        "documents": len(documents),
        "evidence_entities": len({document_stem(rec.doc_id) for rec in records}),
        "all_null_entities": len(all_null),
        "populated_rows": new_rows,
        "old_relation_rows": spec["rows"],
        "new_relation_rows": new_rows,
        "row_counts": counts,
        "provenance_collisions": identity_collisions(),
        "dropped_rows": dropped_rows(),
        "valued_previously_dropped_now_retained": recovered,
        "n_valued_recovered": len(recovered),
        "referenced_columns_created": created,
        "referenced_columns": referenced,
        "signature_columns": sig_cols,
        "n_signature_columns": len(sig_cols),
        "official_before": {"executing": old_exec["n_ok"], "erroring": old_exec["n_error"], "empty": old_exec["n_empty"]},
        "official_after": {"executing": len(queries), "erroring": 0, "empty": len(empty), "empty_ids": empty},
        "db_path": str(dest),
        "db_sha256": db_hash,
        "output_bag_sha256": bag_hash,
        "sqlite_path": str(dest),
        "rewrites": rewrites,
        "pks": schema.primary_keys,
    }


def main() -> int:
    print("plumbing rematerialize", flush=True)
    built = {}
    for name in ("Finan", "Legal"):
        print(f"build {name}", flush=True)
        built[name] = rematerialize(name)
        print(
            json.dumps(
                {
                    "corpus": name,
                    "rows": built[name]["new_relation_rows"],
                    "old_rows": built[name]["old_relation_rows"],
                    "sig_cols": built[name]["n_signature_columns"],
                    "errors_before": built[name]["official_before"]["erroring"],
                    "errors_after": built[name]["official_after"]["erroring"],
                    "empty_after": built[name]["official_after"]["empty"],
                    "collisions": len(built[name]["provenance_collisions"]),
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
        dest = Path(built[name]["sqlite_path"])
        rewrites = {row["query_id"]: built[name]["rewrites"][row["query_id"]] for row in test_count}
        scored = _score(name, dest, test_count, rewrites, gold)
        locked = OLD[name]
        changed = [
            {
                "query_id": row["query_id"],
                "new_product": row["product"],
                "structure_f2": row["structure_f2"],
                "cell_f1_20": row["cell_f1_20"],
            }
            for row in scored["per_query"]
        ]
        scores[name] = {
            "old_incumbent": {
                "mean_structure_f2": locked["f2"],
                "mean_cell_f1_at_0.20": locked["f1"],
                "mean_per_query_product": locked["product"],
            },
            "plumbing": {
                "mean_structure_f2": scored["mean_structure_f2"],
                "mean_cell_f1_at_0.20": scored["mean_cell_f1_at_0.20"],
                "mean_per_query_product": scored["mean_per_query_product"],
            },
            "docetl": DOCETL[name],
            "per_query": changed,
            "n_test": len(changed),
        }
        print(
            json.dumps(
                {
                    "corpus": name,
                    "old": scores[name]["old_incumbent"]["mean_per_query_product"],
                    "plumbing": scores[name]["plumbing"]["mean_per_query_product"],
                    "docetl": DOCETL[name]["product"],
                    "changed": len(changed),
                }
            ),
            flush=True,
        )
        built[name]["rewrites"] = {k: v for k, v in built[name]["rewrites"].items()}
    payload = {
        "tokens_spent": 0,
        "qwen_calls": 0,
        "lookups": 0,
        "hit_rate": "not_applicable",
        "legacy_evidence_input": True,
        "unknown_else_escape": False,
        "corpora": {
            name: {k: v for k, v in built[name].items() if k != "rewrites"} | {"score": scores[name]}
            for name in built
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT), "qwen_calls": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
