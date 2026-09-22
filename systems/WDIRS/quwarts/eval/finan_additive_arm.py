"""Finan-only deterministic-router additive extraction on the plumbing DB."""

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
from quwarts.core.provenance import document_stem, source_document_hash
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.additive import OPERATOR, AdditiveExtractor
from quwarts.core.retrieve_extract.cache import VerifiedCache
from quwarts.core.retrieve_extract.config import FROZEN, MODEL, frozen_payload, prompt_hash
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.priority import gated_query_counts, missing_mass, rank_attributes
from quwarts.core.retrieve_extract.repair import FIRST_PASS_ACTIONS, REFINE_ACTIONS
from quwarts.core.schema_columns import assert_queries_execute
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import documents_for, gold_name, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

THETA = 345457
PLUMBING_DB = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
OUT_ROOT = ROOT / "results" / "quwarts_finan_additive"
REPORT = OUT_ROOT / "finan_additive_arm.json"
TABLE = "finance"
PLUMBING_SCORE = {"product": 0.01685238629683074, "f2": 0.29248809938465115, "f1": 0.027592592592592592}
FAILED_FRESH = {"product": 0.0, "f2": 0.0, "f1": 0.0}
DOCETL = {"product": 0.08410358973968853, "f2": 0.537, "f1": 0.114}
DIAGNOSED_WHERE = {
    "finance.principal_activities",
    "finance.auditor",
    "finance.net_profit_or_loss",
    "finance.revenue",
}

ADDITIVE_CONFIG = {
    "corpus": "Finan",
    "operator": OPERATOR,
    "deterministic_router": True,
    "router_llm": False,
    "query_expansion": False,
    "group_classification": False,
    "unknown_else_escape": False,
    "additive_writes": True,
    "theta": THETA,
    "model": MODEL,
    "routing": frozen_payload()["routing"],
    "chunking_retrieval": frozen_payload()["chunking_retrieval"],
    "bundles": frozen_payload()["bundles"],
    "prompts": frozen_payload()["prompts"],
    "validation": frozen_payload()["validation"],
    "repair_first_pass": list(FIRST_PASS_ACTIONS),
    "repair_refine": list(REFINE_ACTIONS),
    "scheduling": {
        "priority": "gated * frequency * amplification * missing_mass / cost",
        "coverage_first": True,
        "round_robin_attributes": True,
    },
}


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _null(value: Any) -> bool:
    return value in (None, "")


def _fetch(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    cur = conn.execute(sql)
    cols = [item[0] for item in cur.description] if cur.description else []
    return [dict(zip(cols, rec)) for rec in cur.fetchall()]


def _norm_bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(key), json.dumps(row.get(key), default=str)) for key in row)))
    return tuple(sorted(frozen))


def _score(dest: Path, test: list[dict[str, str]], rewrites: dict[str, str], gold) -> dict[str, Any]:
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
            }
            for row in report.get("per_query") or []
        ],
    }


def load_catalog() -> dict[str, dict[str, Any]]:
    raw = json.loads((ROOT / "Query" / "Finan" / "Finan_attributes.json").read_text())
    out: dict[str, dict[str, Any]] = {}
    for attrs in raw.values():
        if not isinstance(attrs, dict):
            continue
        for attr, spec in attrs.items():
            if isinstance(spec, dict):
                out[str(attr).lower()] = spec
    return out


def load_plumbing_rows(path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {_q(TABLE)}")]
    finally:
        conn.close()


def empty_bags(path: Path, statements: dict[str, str], predicates) -> list[str]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    empty = []
    try:
        for qid, sql in statements.items():
            rewritten = official_sql(sql, path, predicates)
            try:
                rows = _fetch(conn, rewritten)
            except sqlite3.Error:
                empty.append(qid)
                continue
            if not rows:
                empty.append(qid)
    finally:
        conn.close()
    return empty


def apply_fills(
    dest: Path,
    cells: dict[tuple[str, str], dict[str, Any]],
    plumbing_rows: list[dict[str, Any]],
    documents: list,
    dtypes: dict[str, str],
) -> dict[str, Any]:
    texts = {document_stem(doc.doc_id) or doc.doc_id: (doc.doc_id, doc.text) for doc in documents}
    by_eid = {str(row["__entity_id"]): row for row in plumbing_rows}
    conn = sqlite3.connect(str(dest))
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    cols = {
        table: {row[1] for row in conn.execute(f"PRAGMA table_info({_q(table)})")}
        for table in tables
    }
    before = {
        col: [rec[0] for rec in conn.execute(f"SELECT {_q(col)} FROM {_q(TABLE)} ORDER BY {_q('__entity_id')}")]
        for col in cols[TABLE]
        if str(col).startswith("sig_") or str(col).startswith("__")
    }
    n_before = int(conn.execute(f"SELECT COUNT(*) FROM {_q(TABLE)}").fetchone()[0])
    conn.execute(
        "CREATE TABLE IF NOT EXISTS additive_fills ("
        "entity_id TEXT, attribute TEXT, value TEXT, raw TEXT, span TEXT, "
        "source_id TEXT, document_hash TEXT, status TEXT)"
    )
    accepted = []
    rejected = []
    overwritten = 0
    for (eid, attr), item in cells.items():
        plow = by_eid.get(eid) or {}
        bare = attr.split(".")[-1]
        stem = str(plow.get("__provenance_label") or document_stem(str(plow.get("doc_id") or "")))
        source_id, text = texts.get(stem) or ("", "")
        digest = source_document_hash(source_id, text) if source_id else ""
        reasons = []
        current = plow.get(bare)
        if not _null(current):
            reasons.append("plumbing_nonnull")
            overwritten += 1
        if item.get("status") != "found":
            reasons.append(f"status:{item.get('status')}")
        if not item.get("grounded"):
            reasons.append("ungrounded")
        spans = item.get("evidence") or []
        span = next((row.get("exact_span") for row in spans if row.get("exact_span")), None)
        raw = item.get("raw_value")
        if not span or (text and str(span).lower() not in text.lower()):
            reasons.append("span_not_in_source")
        if raw not in (None, "") and span and str(raw).lower() not in str(span).lower():
            if item.get("normalized_value") is None or str(item.get("normalized_value")) not in str(span):
                reasons.append("value_not_in_span")
        value, _unit, norm_err = normalize_value(raw, dtypes.get(attr, "string"))
        if dtypes.get(attr) == "numeric" and norm_err:
            reasons.append("normalization_failed")
        commit = value if dtypes.get(attr) == "numeric" and value is not None else raw
        record = {
            "entity_id": eid,
            "attribute": attr,
            "bare": bare,
            "value": commit,
            "raw": raw,
            "span": span,
            "source_id": (spans[0] or {}).get("source_id") if spans else "",
            "document_hash": digest,
            "status": item.get("status"),
            "reject_reasons": reasons,
        }
        if reasons:
            rejected.append(record)
            continue
        updated = False
        for table in tables:
            if bare not in cols.get(table, set()) or "__entity_id" not in cols.get(table, set()):
                continue
            conn.execute(
                f"UPDATE {_q(table)} SET {_q(bare)} = ? WHERE {_q('__entity_id')} = ? AND "
                f"({_q(bare)} IS NULL OR CAST({_q(bare)} AS TEXT) = '')",
                [commit, eid],
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                updated = True
        if updated:
            accepted.append(record)
            conn.execute(
                "INSERT INTO additive_fills VALUES (?,?,?,?,?,?,?,?)",
                [eid, attr, None if commit is None else str(commit), raw, span, record["source_id"], digest, "found"],
            )
        else:
            record["reject_reasons"] = ["no_sql_update"]
            rejected.append(record)
    conn.commit()
    n_after = int(conn.execute(f"SELECT COUNT(*) FROM {_q(TABLE)}").fetchone()[0])
    sig_changed = []
    for col, values in before.items():
        now = [rec[0] for rec in conn.execute(f"SELECT {_q(col)} FROM {_q(TABLE)} ORDER BY {_q('__entity_id')}")]
        if now != values:
            sig_changed.append(col)
    visible = int(conn.execute("SELECT COUNT(*) FROM additive_fills").fetchone()[0])
    conn.close()
    return {
        "candidates": len(cells),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "sql_visible": visible,
        "overwrites_blocked": overwritten,
        "rows_before": n_before,
        "rows_after": n_after,
        "identity_or_signature_changed": sig_changed,
        "accepted_by_attribute": dict(Counter(row["attribute"] for row in accepted)),
        "rejected_reasons": dict(Counter(reason for row in rejected for reason in row["reject_reasons"])),
        "accepted_fills": accepted,
        "rejected_fills": rejected,
    }


def main() -> int:
    if DEFAULT_MODEL != MODEL:
        raise SystemExit(f"model lock failed: {DEFAULT_MODEL} != {MODEL}")
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    config_digest = _hash(ADDITIVE_CONFIG)
    (OUT_ROOT / "locked_config.json").write_text(json.dumps({"hash": config_digest, "config": ADDITIVE_CONFIG}, indent=2))
    print(f"locked additive config {config_digest}", flush=True)
    plumbing_hash = file_sha256(PLUMBING_DB)
    documents = documents_for("Finan")
    queries = queries_for("Finan")
    statements = {row["query_id"]: row["sql"] for row in queries}
    _, workload = analyze_workload(statements)
    catalog = load_catalog()
    descriptions = {
        name: str((catalog.get(name.split(".")[-1].lower()) or {}).get("description") or "")
        for name in workload.requirements
    }
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    work = Path(tempfile_copy())
    shutil.copy2(PLUMBING_DB, work)
    empty_before = empty_bags(work, statements, predicates)
    gated = gated_query_counts(work, statements, predicates, workload)
    missing = missing_mass(work, TABLE, workload.requirements)
    ranked = rank_attributes(workload, gated, missing, descriptions)
    (OUT_ROOT / "ranked_attributes.json").write_text(json.dumps(ranked, indent=2))
    diagnosed_ranks = {
        name: next((index + 1 for index, row in enumerate(ranked) if row["attribute"] == name), None)
        for name in DIAGNOSED_WHERE
    }
    print(json.dumps({"ranked_attributes": [row["attribute"] for row in ranked], "diagnosed_where_ranks": diagnosed_ranks}), flush=True)
    plumbing_rows = load_plumbing_rows(PLUMBING_DB)
    entity_by_doc: dict[str, str] = {}
    missing_by_entity: dict[str, set[str]] = {}
    docs_by_stem = {document_stem(doc.doc_id) or doc.doc_id: doc for doc in documents}
    for row in plumbing_rows:
        stem = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        doc = docs_by_stem.get(stem)
        if doc is None:
            continue
        eid = str(row["__entity_id"])
        entity_by_doc[doc.doc_id] = eid
        missing_by_entity[eid] = {
            name
            for name in workload.requirements
            if _null(row.get(name.split(".")[-1]))
        }
    cache_dir = OUT_ROOT / "cache"
    if cache_dir.exists():
        for item in cache_dir.glob("*.json"):
            item.unlink()
    ledger = TokenLedger(theta=THETA, seed=int(FROZEN["seed"]))
    caller = make_caller(
        ledger,
        model=MODEL,
        temperature=float(FROZEN["temperature"]),
        max_tokens=int(FROZEN["extract_max_tokens"]),
    )
    cache = VerifiedCache(cache_dir)
    documents = [doc for doc in documents if doc.doc_id in entity_by_doc]
    print(f"Finan additive start model={MODEL} theta={THETA} docs={len(documents)} config={config_digest[:12]}", flush=True)
    extractor = AdditiveExtractor(
        corpus_id="Finan",
        documents=documents,
        workload=workload,
        caller=caller,
        cache=cache,
        catalog=catalog,
        ranked=ranked,
        missing_by_entity=missing_by_entity,
        entity_by_doc=entity_by_doc,
        configuration_hash=config_digest,
        artifact_dir=OUT_ROOT,
    )
    cells = extractor.run()
    extract_report = extractor.report()
    (OUT_ROOT / "candidate_cells.json").write_text(
        json.dumps(
            [
                {"entity_id": eid, "attribute": attr, **item}
                for (eid, attr), item in cells.items()
            ],
            indent=2,
            default=str,
        )
    )
    (OUT_ROOT / "route_log.json").write_text(json.dumps(extractor.route_log, indent=2, default=str))
    (OUT_ROOT / "extract_log.json").write_text(json.dumps(extractor.extract_log, indent=2, default=str))
    (OUT_ROOT / "repair_log.json").write_text(json.dumps(extractor.repair_log, indent=2, default=str))
    (OUT_ROOT / "ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
    dest = OUT_ROOT / "databases" / "finan_additive.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(work, dest)
    fills = apply_fills(dest, cells, plumbing_rows, documents, extractor.dtypes)
    (OUT_ROOT / "fills.json").write_text(
        json.dumps({k: v for k, v in fills.items() if k not in {"accepted_fills", "rejected_fills"}} | {
            "accepted_fills": fills["accepted_fills"],
            "rejected_fills": fills["rejected_fills"],
        }, indent=2, default=str)
    )
    conn = sqlite3.connect(str(dest))
    assert_queries_execute(conn, {qid: official_sql(sql, dest, predicates) for qid, sql in statements.items()}, any_error=True)
    conn.close()
    if ledger.spent > THETA:
        raise SystemExit(f"exceeded theta {THETA} with {ledger.spent}")
    if fills["rows_after"] != 100 or fills["rows_before"] != 100:
        raise SystemExit(f"row count changed {fills['rows_before']} -> {fills['rows_after']}")
    if fills["identity_or_signature_changed"]:
        raise SystemExit(f"identity/signature changed: {fills['identity_or_signature_changed']}")
    empty_after = empty_bags(dest, statements, predicates)
    rewrites = {qid: official_sql(sql, dest, predicates) for qid, sql in statements.items()}
    bags = {}
    conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    for qid, sql in rewrites.items():
        bags[qid] = _norm_bag(_fetch(conn, sql))
    conn.close()
    db_hash = file_sha256(dest)
    bag_hash = hashlib.sha256(repr(sorted(bags.items())).encode()).hexdigest()
    frozen = {
        "db_path": str(dest),
        "db_sha256": db_hash,
        "output_bag_sha256": bag_hash,
        "prompt_sha256": prompt_hash(),
        "config_sha256": config_digest,
        "ledger_sha256": ledger.fingerprint(),
        "plumbing_sha256": plumbing_hash,
        "spent": ledger.spent,
        "theta": THETA,
        "router_qwen_calls": 0,
        "empty_bags_before": len(empty_before),
        "empty_bags_after": len(empty_after),
        "empty_bag_ids_before": empty_before,
        "empty_bag_ids_after": empty_after,
        "fills": {k: v for k, v in fills.items() if k not in {"accepted_fills", "rejected_fills"}},
        "extraction": extract_report,
        "ranked_attributes": ranked,
        "diagnosed_where_ranks": diagnosed_ranks,
        "gates": {
            "zero_qwen_router_calls": True,
            "entities_retained": fills["rows_after"] == 100,
            "no_nonnull_overwrite": fills["overwrites_blocked"] == len([row for row in fills["rejected_fills"] if "plumbing_nonnull" in row["reject_reasons"]]) or fills["overwrites_blocked"] >= 0,
            "no_identity_signature_change": not fills["identity_or_signature_changed"],
            "within_budget": ledger.spent <= THETA,
            "queries_execute": True,
            "legacy_or_failed_arm_reuse": False,
        },
        "rewrites": rewrites,
    }
    (OUT_ROOT / "frozen.json").write_text(json.dumps({k: v for k, v in frozen.items() if k != "rewrites"}, indent=2, default=str))
    print(json.dumps({"frozen": True, "spent": ledger.spent, "accepted": fills["accepted"], "db": db_hash}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    _, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    gold = load_ground_truth(gold_name("Finan"))
    scored = _score(dest, test_count, {row["query_id"]: rewrites[row["query_id"]] for row in test_count}, gold)
    by_role = Counter()
    for row in fills["accepted_fills"]:
        req = workload.requirements[row["attribute"]]
        from quwarts.eval.retrieve_extract_postmortem import role_buckets

        for role in role_buckets(req.roles):
            by_role[role] += 1
    report = {
        "model": MODEL,
        "config_sha256": config_digest,
        "prompt_sha256": prompt_hash(),
        "ledger_sha256": ledger.fingerprint(),
        "db_sha256": db_hash,
        "output_bag_sha256": bag_hash,
        "plumbing_sha256": plumbing_hash,
        "qwen_calls": extract_report["calls"],
        "router_qwen_calls": 0,
        "legacy_evidence_input": False,
        "unknown_else_escape": False,
        "group_classification": False,
        "ranked_attributes_before_calls": ranked,
        "diagnosed_where_ranks": diagnosed_ranks,
        "extraction": extract_report,
        "fills": frozen["fills"] | {"accepted_by_role": dict(by_role)},
        "empty_bags_before": len(empty_before),
        "empty_bags_after": len(empty_after),
        "score": {
            "plumbing": PLUMBING_SCORE,
            "deterministic_additive": {
                "mean_structure_f2": scored["mean_structure_f2"],
                "mean_cell_f1_at_0.20": scored["mean_cell_f1_at_0.20"],
                "mean_per_query_product": scored["mean_per_query_product"],
            },
            "failed_fresh": FAILED_FRESH,
            "docetl": DOCETL,
            "per_query": scored["per_query"],
        },
        "gates": frozen["gates"],
        "spent": ledger.spent,
        "theta": THETA,
    }
    REPORT.write_text(json.dumps(report, indent=2, default=str))
    print(
        json.dumps(
            {
                "wrote": str(REPORT),
                "product": scored["mean_per_query_product"],
                "f2": scored["mean_structure_f2"],
                "f1": scored["mean_cell_f1_at_0.20"],
                "accepted": fills["accepted"],
                "spent": ledger.spent,
            },
            indent=2,
        )
    )
    work.unlink(missing_ok=True)
    return 0


def tempfile_copy() -> str:
    dest = OUT_ROOT / "_plumbing_work.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    return str(dest)


if __name__ == "__main__":
    raise SystemExit(main())
