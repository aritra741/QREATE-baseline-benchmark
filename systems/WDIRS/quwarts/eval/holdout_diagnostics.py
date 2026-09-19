"""Zero-token Finan waterfall + isolated Legal/Finan oracles. No frozen writes."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.component_oracle import COMPONENTS, base_checksums, uses_component
from quwarts.core.extract import EvidenceStore, evidence_key
from quwarts.core.pipeline import official_sql
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.component_oracles import (
    _bags,
    _component_state,
    _fetch,
    _non_target_ok,
    _python_reagg,
    _rewrites,
    _score,
    file_digest,
    populate,
)
from quwarts.core.query_witness import compile_witness_spec
from quwarts.core.workload import parse_sql
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.single_table_case80 import DATASETS
from quwarts.experiments.synthesize_case80 import documents_for, gold_name, queries_for, score_with_rewrites
from spp.config_grid import _build_in_memory_db
from sqlglot import exp

FINAN_INC = ROOT / "results" / "quwarts_finan_compiler80" / "artifacts" / "databases" / "dd4a7e27fc9a7d08.db"
LEGAL_INC = ROOT / "results" / "quwarts_legal_compiler80" / "artifacts" / "databases" / "24310a52370ec2c0.db"
FINAN_GROUP_INC = ROOT / "results" / "quwarts_finan_group" / "artifacts" / "incumbent.db"
LEGAL_GROUP_INC = ROOT / "results" / "quwarts_legal_group" / "artifacts" / "incumbent.db"
FINAN_EV = ROOT / "results" / "quwarts_finan_compiler80" / "artifacts" / "evidence"
LEGAL_EV = ROOT / "results" / "quwarts_legal_compiler80" / "artifacts" / "evidence"
MED_EV = ROOT / "results" / "quwarts_med_aprime" / "artifacts" / "evidence"
FINAN_CASE_EV = ROOT / "results" / "quwarts_finan_case80" / "artifacts" / "evidence"
FINAN_2X_EV = ROOT / "results" / "quwarts_finan_compiler80_2x" / "artifacts" / "evidence"
FINAN_SRC = ROOT / "source_data" / "Finance" / "finance"
OUT = ROOT / "results" / "quwarts_holdout_group" / "holdout_diagnostics.json"
DOCETL = {
    "Finan": 0.08410358973968853,
    "Legal": 0.12350932750098194,
}
HOLD_INC = {
    "Finan": 0.03302469135802469,
    "Legal": 0.022128851540616248,
}


FROZEN_PATHS = {
    "finan_compiler": FINAN_INC,
    "legal_compiler": LEGAL_INC,
    "finan_group_incumbent": FINAN_GROUP_INC,
    "legal_group_incumbent": LEGAL_GROUP_INC,
}


def _digest_frozen() -> dict[str, str]:
    return {name: file_digest(path) for name, path in FROZEN_PATHS.items() if path.is_file()}


def _copy_incumbent(src: Path) -> tuple[Path, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="holdout_ro_"))
    dest = tmp / src.name
    shutil.copy2(src, dest)
    return dest, tmp


def _sql_columns(sql: str) -> set[str]:
    try:
        tree = parse_sql(sql)
    except Exception:
        return set()
    return {(col.name or "").lower() for col in tree.find_all(exp.Column) if col.name}


def _user_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%' "
            "AND name NOT LIKE 'oracle_%' AND name NOT LIKE 'group_labels' "
            "AND name NOT LIKE 'filter_additions' AND name NOT LIKE 'sig_%'"
        )
    ]


def finan_waterfall() -> dict[str, Any]:
    src_files = sorted(FINAN_SRC.glob("*.txt")) if FINAN_SRC.is_dir() else []
    docs = documents_for("Finan")
    store = EvidenceStore(FINAN_EV)
    records = list(store.records.values())
    other_keys = {
        "med": {path.stem for path in MED_EV.glob("*.json")} if MED_EV.is_dir() else set(),
        "legal": {path.stem for path in LEGAL_EV.glob("*.json")} if LEGAL_EV.is_dir() else set(),
        "finan_case80": {path.stem for path in FINAN_CASE_EV.glob("*.json")} if FINAN_CASE_EV.is_dir() else set(),
        "finan_2x": {path.stem for path in FINAN_2X_EV.glob("*.json")} if FINAN_2X_EV.is_dir() else set(),
    }
    src_names = {path.name for path in src_files}
    src_stems = {path.stem for path in src_files}
    ev_docs = {record.doc_id for record in records}
    ev_stems = {Path(doc).stem for doc in ev_docs}
    reasons = Counter(
        record.null_reason or ("value" if record.surface_value not in (None, "") else "empty")
        for record in records
    )
    tiers = Counter(record.quality_tier for record in records)
    stages = Counter(record.stage for record in records)
    hashes = Counter(record.extractor_cfg_hash for record in records)
    tokens = Counter()
    by_attr: dict[str, dict[str, Any]] = {}
    for record in records:
        tokens["evidence_tokens_spent"] += int(record.tokens_spent or 0)
        if record.tokens_spent == 0:
            tokens["zero_token_records"] += 1
        bag = by_attr.setdefault(
            record.attribute,
            {"n": 0, "value": 0, "null": 0, "reasons": Counter(), "tokens": 0, "docs": set()},
        )
        bag["n"] += 1
        bag["tokens"] += int(record.tokens_spent or 0)
        bag["docs"].add(record.doc_id)
        if record.surface_value not in (None, ""):
            bag["value"] += 1
        else:
            bag["null"] += 1
            bag["reasons"][record.null_reason or "empty"] += 1
    rebuilt = 0
    mismatch = 0
    for record in records:
        expect = evidence_key(record.segment_id, record.attribute, record.extractor_cfg_hash, record.quality_tier)
        rebuilt += 1
        if expect != record.key:
            mismatch += 1
    key_overlap = {name: len({record.key for record in records} & keys) for name, keys in other_keys.items()}
    foreign_attr = [record.attribute for record in records if not str(record.attribute).startswith("finance.")]
    foreign_doc = [
        record.doc_id
        for record in records
        if Path(record.doc_id).name not in src_names and Path(record.doc_id).stem not in src_stems
    ]
    conn = sqlite3.connect(f"file:{FINAN_INC}?mode=ro", uri=True)
    tables = {}
    missing_cols = []
    for table in _user_tables(conn):
        cols = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
        n = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        col_stats = {}
        for col in cols:
            filled = int(conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" IS NOT NULL AND CAST("{col}" AS TEXT) <> \'\'').fetchone()[0])
            col_stats[col] = {"non_null": filled, "rate": filled / n if n else 0.0}
        tables[table] = {"n_rows": n, "columns": col_stats}
    pk_stats = {}
    if "finance" in {t.lower() for t in tables}:
        cols = {c.lower() for c in tables["finance"]["columns"]}
        for col in ("auditor", "doc_id", "id"):
            if col not in cols:
                continue
            nuniq = int(conn.execute(f'SELECT COUNT(DISTINCT "{col}") FROM finance WHERE "{col}" IS NOT NULL').fetchone()[0])
            pk_stats[col] = {"distinct": nuniq, "rows": tables["finance"]["n_rows"]}
    conn.close()
    queries = queries_for("Finan")
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    copy_db, copy_dir = _copy_incumbent(FINAN_INC)
    exec_err = []
    empty = []
    copy_conn = sqlite3.connect(f"file:{copy_db}?mode=ro", uri=True)
    for row in queries:
        sql = official_sql(row["sql"], copy_db, predicates)
        try:
            cur = copy_conn.execute(sql)
            cols = [item[0] for item in cur.description] if cur.description else []
            rows = [dict(zip(cols, rec)) for rec in cur.fetchall()]
        except Exception as exc:
            exec_err.append({"query_id": row["query_id"], "error": str(exc)})
            continue
        if not rows:
            empty.append(row["query_id"])
    copy_conn.close()
    shutil.rmtree(copy_dir, ignore_errors=True)
    referenced: set[str] = set()
    for row in queries:
        referenced |= _sql_columns(row["sql"])
    present = {col.lower() for spec in tables.values() for col in spec["columns"]}
    reserved = {"count", "sum", "avg", "min", "max"}
    missing_ref = sorted(name for name in referenced if name and name not in present and name not in reserved)
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    gold_ids = {str(row.get("id") or "") for row in gold.get("finance") or []}
    gold_ids.discard("")
    qw_stems = set()
    qconn = sqlite3.connect(f"file:{FINAN_INC}?mode=ro", uri=True)
    if "finance" in {t.lower() for t in _user_tables(qconn)}:
        cols = {row[1].lower() for row in qconn.execute('PRAGMA table_info("finance")')}
        if "doc_id" in cols:
            qw_stems = {Path(str(row[0])).stem for row in qconn.execute("SELECT doc_id FROM finance") if row[0]}
        elif "id" in cols:
            qw_stems = {str(row[0]) for row in qconn.execute("SELECT id FROM finance") if row[0]}
    qconn.close()
    report = json.loads((ROOT / "results" / "quwarts_finan_compiler80" / "report.json").read_text())
    case80 = json.loads((ROOT / "results" / "quwarts_finan_case80" / "report.json").read_text()) if (ROOT / "results" / "quwarts_finan_case80" / "report.json").is_file() else {}
    sample_keys = [
        {
            "key": rec.key,
            "segment_id": rec.segment_id,
            "doc_id": rec.doc_id,
            "attribute": rec.attribute,
            "extractor_cfg_hash": rec.extractor_cfg_hash,
            "quality_tier": rec.quality_tier,
            "null_reason": rec.null_reason,
            "tokens_spent": rec.tokens_spent,
            "surface_value": rec.surface_value,
            "key_formula": "sha256(segment_id|attribute|extractor_cfg_hash|quality_tier)",
            "includes_corpus": False,
            "includes_prompt_hash": False,
            "includes_model": False,
        }
        for rec in records[:5]
    ]
    lookups_zero = store.lookups == 0
    n_value = sum(bag["value"] for bag in by_attr.values())
    n_provider = int(reasons.get("provider_error") or 0)
    if report.get("mode") == "rematerialize" and lookups_zero and n_provider and tokens["evidence_tokens_spent"] == 0:
        root_cause = (
            "plumbing_defect: rematerialize skipped extract; cache_hit_rate=1.0 is the "
            "empty-lookup default; on-disk evidence is provider_error/0-token stubs, not "
            "verified corpus-scoped cache hits; 595 tokens are post-extract signature/"
            "domain calls, not extraction"
        )
    elif report.get("mode") == "rematerialize" and lookups_zero:
        root_cause = "rematerialize_reused_on_disk_evidence_lookups_never_ran"
    else:
        root_cause = "unclassified"
    return {
        "mode": report.get("mode"),
        "manifest_mode": "compile",
        "tokens_spent": report.get("tokens_spent"),
        "cache_hit_rate_reported": report.get("cache_hit_rate"),
        "store_lookups": store.lookups,
        "store_hits": store.hits,
        "cache_hit_rate_is_empty_lookup_default": lookups_zero and bool(records),
        "prior_finan_case80_tokens": case80.get("tokens_spent"),
        "source_documents_discovered": len(src_files),
        "documents_opened": len(docs),
        "expected_documents": 100,
        "evidence_records": len(records),
        "evidence_docs": len(ev_docs),
        "docs_missing_from_evidence": sorted(src_stems - ev_stems)[:20],
        "n_docs_missing_from_evidence": len(src_stems - ev_stems),
        "evidence_docs_not_in_source": sorted(foreign_doc)[:20],
        "n_evidence_docs_not_in_source": len(foreign_doc),
        "foreign_attributes": sorted(set(foreign_attr)),
        "null_reasons": dict(reasons),
        "tiers": dict(tiers),
        "stages": dict(stages),
        "extractor_cfg_hashes": dict(hashes),
        "evidence_tokens_spent": tokens["evidence_tokens_spent"],
        "zero_token_records": tokens["zero_token_records"],
        "key_rebuilds": rebuilt,
        "key_mismatches": mismatch,
        "key_overlap_other_runs": key_overlap,
        "cache_key_samples": sample_keys,
        "pk_stats": pk_stats,
        "skipped_extraction_jobs": {
            "reason": "compile_workload(extract=False) because mode=rematerialize",
            "n_jobs_skipped": len(docs) * max(1, len(by_attr)),
            "model_calls_attempted": 0,
            "budget_refusals": 0,
            "retries": 0,
        },
        "attributes": {
            name: {
                "n": bag["n"],
                "value": bag["value"],
                "null": bag["null"],
                "reasons": dict(bag["reasons"]),
                "tokens": bag["tokens"],
                "n_docs": len(bag["docs"]),
            }
            for name, bag in sorted(by_attr.items())
        },
        "populated_tables": tables,
        "query_execution_errors": exec_err,
        "empty_official_bags": empty,
        "n_empty_official_bags": len(empty),
        "missing_referenced_columns": missing_ref[:40],
        "gold_entities": len(gold_ids),
        "incumbent_entities": len(qw_stems),
        "gold_recall": (len(gold_ids & qw_stems) / len(gold_ids)) if gold_ids else None,
        "gold_overlap": len(gold_ids & qw_stems),
        "gold_missing": len(gold_ids - qw_stems),
        "root_cause": root_cause,
        "waterfall": {
            "source_documents_discovered": len(src_files),
            "documents_opened": len(docs),
            "extraction_jobs_planned": len(docs) * len(by_attr),
            "extraction_jobs_skipped": len(docs) * len(by_attr),
            "skip_reason": "extract=False rematerialize; StagedExtractor never ran",
            "model_calls_attempted": 0,
            "cache_hits_verified": 0,
            "cache_hit_rate_reported": report.get("cache_hit_rate"),
            "cache_hits": "unverified: lookups=0 so cache_hit_rate defaulted to 1.0",
            "model_calls_completed": 0,
            "evidence_records_emitted": len(records),
            "entities_emitted": len(ev_docs),
            "candidate_rows": sum(spec["n_rows"] for spec in tables.values()),
            "validation_accepted": sum(bag["value"] for bag in by_attr.values()),
            "dedup_survived": len({(rec.doc_id, rec.attribute) for rec in records}),
            "populated_rows": sum(spec["n_rows"] for spec in tables.values()),
            "official_queries_executed": len(queries),
        },
    }


def run_oracles(name: str, incumbent: Path) -> dict[str, Any]:
    queries = queries_for(name)
    _, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    statements = {row["query_id"]: row["sql"] for row in queries}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    frozen = file_digest(incumbent)
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name(name))
    gold_conn = _build_in_memory_db(gold)
    ro_db, ro_dir = _copy_incumbent(incumbent)
    inc_conn = sqlite3.connect(f"file:{ro_db}?mode=ro", uri=True)
    inc_official = {row["query_id"]: official_sql(row["sql"], ro_db, predicates) for row in queries}
    # score_with_rewrites needs dataset name; wrap local
    def score(test_rows, dest, rewrites):
        report = score_with_rewrites(test_rows, rewrites, dest, gold, name)
        from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product

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

    incumbent_score = score(test_count, ro_db, {r["query_id"]: inc_official[r["query_id"]] for r in test_count})
    incumbent_prod = incumbent_score["mean_per_query_product"]
    incumbent_bags = _bags(inc_conn, inc_official)
    oracles = {}
    print(f"{name} oracles incumbent={incumbent} product={incumbent_prod}", flush=True)
    for component in COMPONENTS:
        tmp = Path(tempfile.mkdtemp(prefix=f"holdout_{name}_{component}_"))
        dest = tmp / "oracle.db"
        shutil.copy2(incumbent, dest)
        assert dest.resolve() != incumbent.resolve()
        try:
            filled = populate(component, dest, gold_conn, queries, predicates)
            dest_conn = sqlite3.connect(str(dest))
            rewrites = _rewrites(queries, dest, predicates, component, filled["schemas"])
            after_bags = _bags(dest_conn, rewrites)
            unused = [
                qid
                for qid, sql in statements.items()
                if not uses_component(sql, component) and after_bags.get(qid) != incumbent_bags.get(qid)
            ]
            if unused:
                dest_conn.close()
                raise RuntimeError(f"{component} moved unused queries: {unused[:8]}")
            changed = [qid for qid in statements if after_bags.get(qid) != incumbent_bags.get(qid)]
            test_changed = [r["query_id"] for r in test_count if r["query_id"] in changed]
            invalid = []
            nontarget = []
            for row in queries:
                if component != "full_witness" and not uses_component(row["sql"], component):
                    continue
                spec = compile_witness_spec(row["query_id"], row["sql"])
                inc_state = _component_state(inc_conn, row["sql"], spec, incumbent, predicates, "incumbent", {})
                ora_state = _component_state(dest_conn, row["sql"], spec, dest, predicates, component, filled["schemas"])
                bad = _non_target_ok(component, inc_state, ora_state)
                if bad:
                    nontarget.append({"query_id": row["query_id"], "fields": bad})
                cf = _fetch(dest_conn, rewrites[row["query_id"]])
                reagg = _python_reagg(ora_state["grain"], spec, row["sql"])
                if _norm_safe(reagg) != _norm_safe(cf):
                    invalid.append(row["query_id"])
            scored = score(test_count, dest, {r["query_id"]: rewrites[r["query_id"]] for r in test_count})
            dest_conn.close()
            product = scored["mean_per_query_product"]
            oracles[component] = {
                "score": {
                    "mean_structure_f2": scored["mean_structure_f2"],
                    "mean_cell_f1_at_0.20": scored["mean_cell_f1_at_0.20"],
                    "mean_per_query_product": product,
                },
                "lift": product - incumbent_prod,
                "docetl_gap": DOCETL[name] - product,
                "n_writes": filled["n_writes"],
                "sidecar_counts": filled["gates"]["sidecar_counts"],
                "changed_queries": changed,
                "n_changed_queries": len(changed),
                "test_changed": test_changed,
                "n_test_changed": len(test_changed),
                "unused_moved": unused,
                "invalid_traces": invalid,
                "n_invalid_traces": len(invalid),
                "nontarget_failures": nontarget[:20],
                "n_nontarget_failures": len(nontarget),
                "gates": {k: v for k, v in filled["gates"].items() if k != "checksums"},
                "checksums_unchanged": filled["gates"]["ok"] and filled["gates"].get("base_checksums"),
            }
            print(
                json.dumps(
                    {
                        "corpus": name,
                        "oracle": component,
                        "f2": scored["mean_structure_f2"],
                        "f1": scored["mean_cell_f1_at_0.20"],
                        "product": product,
                        "lift": product - incumbent_prod,
                        "writes": filled["n_writes"],
                        "changed": len(changed),
                        "test_changed": len(test_changed),
                        "invalid": len(invalid),
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            oracles[component] = {"aborted": True, "error": str(exc), "lift": None}
            print(json.dumps({"corpus": name, "oracle": component, "aborted": True, "error": str(exc)}), flush=True)
        finally:
            dest.unlink(missing_ok=True)
            shutil.rmtree(tmp, ignore_errors=True)
    after = file_digest(incumbent)
    gold_conn.close()
    inc_conn.close()
    shutil.rmtree(ro_dir, ignore_errors=True)
    live = [(k, v) for k, v in oracles.items() if k != "full_witness" and not v.get("aborted")]
    best = max(live, key=lambda item: (item[1].get("score") or {}).get("mean_per_query_product") or 0.0) if live else ("", {})
    return {
        "incumbent": str(incumbent),
        "frozen_digest": frozen,
        "frozen_db_written": after != frozen,
        "incumbent_score": incumbent_score,
        "oracles": oracles,
        "highest_component": {
            "name": best[0],
            **((best[1] or {}).get("score") or {}),
            "lift": (best[1] or {}).get("lift"),
        },
    }


def _norm_safe(rows: list[dict[str, Any]]) -> tuple:
    from quwarts.eval.component_oracles import _norm_bag

    return _norm_bag(rows)


def main() -> int:
    before_frozen = _digest_frozen()
    print("finan waterfall", flush=True)
    waterfall = finan_waterfall()
    print(json.dumps({"root_cause": waterfall["root_cause"], "tokens": waterfall["tokens_spent"], "lookups": waterfall["store_lookups"]}, indent=2), flush=True)
    results = {}
    for name, path in (("Finan", FINAN_INC), ("Legal", LEGAL_INC)):
        results[name] = run_oracles(name, path)
    after_frozen = _digest_frozen()
    highest = {name: results[name]["highest_component"]["name"] for name in results}
    shared = highest["Finan"] == highest["Legal"] and bool(highest["Finan"])
    ranked = sorted(
        (
            (corpus, rec["highest_component"]["name"], rec["highest_component"].get("lift") or 0.0)
            for corpus, rec in results.items()
        ),
        key=lambda item: item[2],
        reverse=True,
    )
    next_target = highest["Finan"] if shared else (ranked[0][1] if ranked else None)
    payload = {
        "tokens_spent": 0,
        "qwen_calls": 0,
        "frozen_db_written": after_frozen != before_frozen,
        "frozen_hashes_before": before_frozen,
        "frozen_hashes_after": after_frozen,
        "finan_waterfall": waterfall,
        "oracles": results,
        "shared_highest_component": shared,
        "highest_by_corpus": highest,
        "next_implementation_target": next_target,
        "justification": (
            f"Highest isolated ceiling is {next_target}; "
            + ("shared by Legal and Finan." if shared else "largest isolated lift across the two incumbents.")
        ),
        "docetl_products": DOCETL,
        "holdout_live_products": HOLD_INC,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT), "highest": highest, "next": next_target, "frozen_written": payload["frozen_db_written"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
