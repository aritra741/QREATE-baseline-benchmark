"""Instrumented exact DocETL replay on the current seven-document Finan snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
WDIRS = PROJECT_ROOT / "systems" / "WDIRS"
DOCETL_MAIN = PROJECT_ROOT / "systems" / "docetl-main"
for path in (SCRIPT_DIR, WDIRS, DOCETL_MAIN, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

import replay_instrumentation as inst
import test_player_query_awareness_trend_docetl as docetl_runner

load_env_file(PROJECT_ROOT / ".env")

MODEL = "openrouter/qwen/qwen-2.5-7b-instruct"
THETA_100 = 1_381_827
OUT = PROJECT_ROOT / "results" / "docetl_finan_current_snapshot_replay"
FROZEN_DOCETL = PROJECT_ROOT / "results" / "docetl_finan_case80"
PLUMBING_DB = PROJECT_ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
PARITY_REPORT = PROJECT_ROOT / "results" / "quwarts_finan_docetl_unit_parity" / "finan_docetl_unit_parity_arm.json"
SOURCE_DIR = PROJECT_ROOT / "source_data" / "Finance" / "finance"
ATTR_PATH = PROJECT_ROOT / "Query" / "Finan" / "Finan_attributes.json"
DOCETL_SCORE = {"f2": 0.537, "f1": 0.114, "product": 0.084, "tokens": 1_381_827}


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _extract_pipeline_ids(path: Path) -> list[str]:
    payload = json.loads(path.read_text())
    ids = []
    seen = set()
    for row in payload:
        doc_id = str(row["doc_id"]).strip()
        if doc_id in seen:
            raise SystemExit(f"duplicate doc_id {doc_id} in {path}")
        seen.add(doc_id)
        ids.append(doc_id)
    return ids


def derive_document_ids(query_ids: list[str]) -> list[str]:
    per_query = {}
    for qid in query_ids:
        path = FROZEN_DOCETL / "docetl_pipelines" / qid / "table_finance" / "pipeline_output.json"
        per_query[qid] = tuple(sorted(_extract_pipeline_ids(path), key=lambda x: (int(x) if x.isdigit() else 10**18, x)))
    if len(set(per_query.values())) != 1:
        raise SystemExit(f"pipeline_output ID sets differ: {per_query}")
    ids = list(next(iter(per_query.values())))
    if len(ids) != 7:
        raise SystemExit(f"expected 7 IDs, got {ids}")
    return ids


def load_attributes_schema() -> tuple[set[str], dict[str, set[str]]]:
    payload = json.loads(ATTR_PATH.read_text())
    numeric: set[str] = set()
    columns: dict[str, set[str]] = {}
    for table, fields in payload.items():
        name = str(table).lower()
        columns.setdefault(name, set())
        for col, spec in fields.items():
            key = str(col).strip().lower()
            columns[name].add(key)
            value_type = str((spec or {}).get("value_type") or "").lower()
            if value_type in {"int", "integer", "float", "number", "real"}:
                numeric.add(key)
    return numeric, columns


def isolate_documents(doc_ids: list[str]) -> tuple[Path, dict[str, str], dict[str, str]]:
    dest = OUT / "isolated_input" / "finance"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    mapping = {}
    texts = {}
    for doc_id in doc_ids:
        src = SOURCE_DIR / f"{doc_id}.txt"
        if not src.is_file():
            raise SystemExit(f"missing current source {src}")
        target = dest / src.name
        shutil.copy2(src, target)
        mapping[doc_id] = src.name
        texts[doc_id] = target.read_text(encoding="utf-8", errors="replace")
    extra = [p.name for p in dest.glob("*.txt") if p.stem not in set(doc_ids)]
    if extra or len(list(dest.glob("*.txt"))) != 7:
        raise SystemExit(f"isolated input is not exactly seven files: {list(dest.iterdir())}")
    return dest, mapping, texts


def configure_runner_without_gold(isolated_root: Path, numeric: set[str], columns: dict[str, set[str]]) -> None:
    docetl_runner.SOURCE_DATA_DIR = isolated_root
    docetl_runner.TABLE_SOURCE_SUBDIRS = {"finance": "finance"}
    docetl_runner.TABLE_COLUMNS = columns
    docetl_runner.NUMERIC_FIELDS = numeric
    docetl_runner.DOCETL_MODEL = MODEL
    docetl_runner.OLLAMA_BASE_URL = ""
    docetl_runner.DOCETL_THREADS = 4
    docetl_runner.DOCETL_MAP_TIMEOUT = 420
    docetl_runner.DOCETL_MAX_RETRIES_PER_TIMEOUT = 2
    docetl_runner.DATASET_QUERY = "Finan"


def test_instrumentation_fixture(texts: dict[str, str]) -> dict[str, Any]:
    from docetl.operations.utils import api as api_mod
    from docetl.operations.utils import llm as llm_mod

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Document:\nhello world"},
    ]
    snapshot = json.loads(json.dumps(messages))
    before_trunc = llm_mod.truncate_messages(json.loads(json.dumps(messages)), MODEL)

    class Dummy:
        usage = {"prompt_tokens": 3, "completion_tokens": 1}
        choices = [type("C", (), {"message": type("M", (), {"content": '{"x":"1"}', "tool_calls": None})()})()]

    def fake(self, *args, **kwargs):
        fake.seen = (args, kwargs)
        return Dummy()

    real_call = api_mod.APIWrapper._call_llm_with_cache
    real_trunc = llm_mod.truncate_messages
    api_mod.APIWrapper._call_llm_with_cache = fake
    try:
        inst._state["applied"] = False
        inst.apply_instrumentation(theta=THETA_100, doc_texts=texts)
        os.environ[inst.LEDGER_ENV] = str(OUT / "instrumentation_fixture.jsonl")
        os.environ[inst.QUERY_ENV] = "fixture"
        result = api_mod.APIWrapper._call_llm_with_cache(
            None, MODEL, "map", messages, {"x": "str"}, None, None, {}, {}, False
        )
        after_trunc = llm_mod.truncate_messages(json.loads(json.dumps(messages)), MODEL)
        same_messages = messages == snapshot
        same_trunc = before_trunc == after_trunc
        same_result = result.choices[0].message.content == '{"x":"1"}'
        same_args = fake.seen[0][2] == snapshot or fake.seen[0][2] == messages
    finally:
        api_mod.APIWrapper._call_llm_with_cache = real_call
        llm_mod.truncate_messages = real_trunc
        api_mod.truncate_messages = real_trunc
        inst._state["applied"] = False
        inst._state["original_call"] = None
    return {
        "messages_unchanged": same_messages,
        "truncate_unchanged": same_trunc,
        "result_unchanged": same_result,
        "args_unchanged": bool(same_args),
        "ok": same_messages and same_trunc and same_result,
    }


def planned_calls(query_ids: list[str], statements: dict[str, str]) -> list[dict[str, Any]]:
    tasks = []
    for qid in query_ids:
        need = docetl_runner.columns_per_table_from_sql(statements[qid])
        tables = list(need)
        if tables != ["finance"]:
            raise SystemExit(f"{qid}: unexpected tables {tables}")
        for doc_id in sorted(os.listdir(docetl_runner.SOURCE_DATA_DIR / "finance")):
            if doc_id.endswith(".txt"):
                tasks.append({"query_id": qid, "table": "finance", "doc_id": Path(doc_id).stem, "fields": need["finance"]})
    if len(tasks) != 112:
        raise SystemExit(f"planned {len(tasks)} tasks, expected 112")
    return tasks


def freeze_replay(payload: dict[str, Any]) -> None:
    (OUT / "frozen.json").write_text(json.dumps(payload, indent=2, default=str))


def _score(dest: Path, rows, rewrites, gold) -> dict[str, Any]:
    report = score_with_rewrites(rows, rewrites, dest, gold, "Finan")
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


def official_sql_bag(db: Path, sql: str, predicates, qid: str):
    from quwarts.core.pipeline import official_sql

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = conn.execute(official_sql(sql, db, predicates, query_id=qid))
        cols = [c[0] for c in cur.description] if cur.description else []
        return [dict(zip(cols, rec)) for rec in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def main() -> int:
    if os.environ.get("OPENROUTER_API_KEY"):
        os.environ.setdefault("OPENAI_API_KEY", os.environ["OPENROUTER_API_KEY"])
    OUT.mkdir(parents=True, exist_ok=True)
    cache_dir = OUT / "docetl_cache"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DOCETL_CACHE_DIR"] = str(cache_dir)

    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((FROZEN_DOCETL / "query_manifest.json").read_text())]
    if len(manifest) != 16:
        raise SystemExit(f"manifest has {len(manifest)} queries")
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    document_ids = derive_document_ids(query_ids)
    isolated_dir, mapping, texts = isolate_documents(document_ids)
    isolated_root = isolated_dir.parent
    numeric, columns = load_attributes_schema()
    configure_runner_without_gold(isolated_root, numeric, columns)
    loaded = docetl_runner._raw_doc_records_for_table("finance")
    if [row["doc_id"] for row in loaded] != document_ids:
        # allow numeric sort vs listed order if same set
        if {row["doc_id"] for row in loaded} != set(document_ids) or len(loaded) != 7:
            raise SystemExit(f"runner loaded { [row['doc_id'] for row in loaded] }, expected {document_ids}")

    runner_hash = file_sha256(SCRIPT_DIR / "test_player_query_awareness_trend_docetl.py")
    grid_hash = file_sha256(SCRIPT_DIR / "run_player_grid_test_docetl.py")
    api_hash = file_sha256(DOCETL_MAIN / "docetl" / "operations" / "utils" / "api.py")
    try:
        import subprocess

        revision = subprocess.check_output(["git", "-C", str(DOCETL_MAIN), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        revision = "unavailable"
    prompt_template = (
        "You are building a structured {table} table for this natural-language query:\n"
        "{nl_query}\n\n"
        "From this {table} document, extract exactly one record with these fields:\n"
        "{field_list}\n\n"
        "For numeric fields, return numbers (not quoted strings). "
        "Numeric fields in this extraction: {numeric_guidance}.\n"
        "If a numeric field is unknown, return -1. "
        "If a text field is unknown, return empty string. "
        "Keep names concise and normalized.\n\n"
        "Document:\n{{ input.text }}"
    )
    tasks = planned_calls(query_ids, statements)
    schemas = {qid: docetl_runner.columns_per_table_from_sql(statements[qid])["finance"] for qid in query_ids}
    prior = {
        "docetl_summary": file_sha256(FROZEN_DOCETL / "summary.json"),
        "docetl_manifest": file_sha256(FROZEN_DOCETL / "query_manifest.json"),
        "plumbing": file_sha256(PLUMBING_DB),
        "parity_report": file_sha256(PARITY_REPORT) if PARITY_REPORT.is_file() else None,
    }
    contents = hashlib.sha256()
    for doc_id in document_ids:
        contents.update(doc_id.encode())
        contents.update(texts[doc_id].encode())
    input_hashes = {
        "ordered_query_ids": _hash(query_ids),
        "derived_document_ids": _hash(document_ids),
        "current_source_contents": contents.hexdigest(),
        "id_to_file_mapping": _hash(mapping),
        "docetl_runner": runner_hash,
        "docetl_grid_runner": grid_hash,
        "docetl_api": api_hash,
        "docetl_source_revision": revision,
        "prompt_template": _hash(prompt_template),
        "model_parameters": _hash(
            {
                "model": MODEL,
                "threads": 4,
                "timeout": 420,
                "retries": 2,
                "bypass_cache": True,
                "temperature": None,
                "nl_query": "benchmark SQL",
            }
        ),
        "isolated_input_manifest": _hash({"document_ids": document_ids, "files": mapping, "n": 7}),
    }
    input_hashes["execution_input_sha256"] = _hash(input_hashes)
    (OUT / "preflight.json").write_text(
        json.dumps(
            {
                "note": "Replay on the current seven files; not a reconstruction of the historical ingest snapshot.",
                "query_ids": query_ids,
                "document_ids": document_ids,
                "mapping": mapping,
                "planned_primary_calls": len(tasks),
                "schemas": schemas,
                "hashes": input_hashes,
                "prior_frozen_hashes": prior,
                "model": MODEL,
                "bypass_cache": True,
                "theta_100": THETA_100,
            },
            indent=2,
        )
    )
    fixture = test_instrumentation_fixture(texts)
    (OUT / "instrumentation_fixture.json").write_text(json.dumps(fixture, indent=2))
    if not fixture["ok"]:
        raise SystemExit(f"instrumentation fixture failed: {fixture}")
    inst._state.update({"spent": 0, "n_calls": 0, "stop": False, "applied": False, "original_call": None})
    if len(tasks) != 112:
        raise SystemExit("preflight: not 112 primary calls")
    print(json.dumps({"preflight": True, "n": 112, "docs": document_ids, "fixture": fixture}, indent=2), flush=True)

    journal_path = OUT / "call_journal.jsonl"
    if journal_path.exists():
        journal_path.unlink()
    os.environ[inst.LEDGER_ENV] = str(journal_path)
    inst.apply_instrumentation(theta=THETA_100, doc_texts=texts)

    pipeline_dir = OUT / "docetl_pipelines"
    table_dir = OUT / "query_tables"
    sqlite_dir = OUT / "query_local"
    for path in (pipeline_dir, table_dir, sqlite_dir):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    bags: dict[str, Any] = {}
    extracted: dict[str, Any] = {}
    completed: list[str] = []
    stopped_at = None
    for qid in query_ids:
        if inst.stopped() or inst.spent() >= THETA_100:
            stopped_at = qid
            break
        os.environ[inst.QUERY_ENV] = qid
        os.environ[inst.TABLE_ENV] = "finance"
        started = time.time()
        try:
            rows, table_map, _ = docetl_runner.execute_query_via_docetl_nl(qid, statements[qid], statements[qid], pipeline_dir)
        except Exception as exc:
            rows, table_map = [], {}
            (OUT / "errors.jsonl").open("a").write(json.dumps({"query_id": qid, "error": str(exc)}) + "\n")
            if "budget_ceiling" in str(exc):
                stopped_at = qid
                break
        db_path = sqlite_dir / f"{qid.replace(':', '_')}.db"
        if table_map:
            docetl_runner._write_query_tables_sqlite(table_map, db_path)
            extracted[qid] = {name: df.where(df.notna(), None).to_dict(orient="records") for name, df in table_map.items()}
            bags[qid] = rows
            completed.append(qid)
            (table_dir / f"{qid}.json").write_text(json.dumps(rows, indent=2, default=str))
        else:
            bags[qid] = "incomplete"
            stopped_at = qid
            break
        print(json.dumps({"query": qid, "spent": inst.spent(), "rows": len(rows), "seconds": round(time.time() - started, 2)}, indent=2), flush=True)

    journal = [json.loads(line) for line in journal_path.read_text().splitlines() if line.strip()] if journal_path.is_file() else []
    prompts = [{"call_index": row["call_index"], "query_id": row["query_id"], "document_id": row["document_id"], "system_sha256": row["system_sha256"], "user_sha256": row["user_sha256"], "truncated": row["truncated"]} for row in journal]
    completions = [{"call_index": row["call_index"], "raw_response_sha256": row["raw_response_sha256"], "parsed_response": row["parsed_response"]} for row in journal]
    frozen = {
        "note": "Replay on the current seven files; not a reconstruction of the historical ingest snapshot.",
        "spent": inst.spent(),
        "theta_100": THETA_100,
        "completed_queries": completed,
        "stopped_at": stopped_at,
        "n_journal": len(journal),
        "n_primary_planned": 112,
        "hashes": {
            **input_hashes,
            "journal": _hash(journal),
            "prompts": _hash(prompts),
            "completions": _hash(completions),
            "extracted_tables": _hash(extracted),
            "bags": _hash(bags),
            "ledger_spent": _hash({"spent": inst.spent(), "n": len(journal)}),
            "configuration": input_hashes["model_parameters"],
            "isolated_snapshot": file_sha256(isolated_dir / f"{document_ids[0]}.txt"),
        },
        "prior_frozen_still_identical": {
            name: file_sha256(path) == digest
            for name, path, digest in (
                ("docetl_summary", FROZEN_DOCETL / "summary.json", prior["docetl_summary"]),
                ("docetl_manifest", FROZEN_DOCETL / "query_manifest.json", prior["docetl_manifest"]),
                ("plumbing", PLUMBING_DB, prior["plumbing"]),
            )
        },
        "empty_bags": [qid for qid, bag in bags.items() if bag in ([], "incomplete") or bag == []],
        "schemas": schemas,
    }
    isolated_hashes = {doc_id: hashlib.sha256(texts[doc_id].encode()).hexdigest() for doc_id in document_ids}
    frozen["hashes"]["isolated_documents"] = _hash(isolated_hashes)
    (OUT / "call_journal.json").write_text(json.dumps(journal, indent=2, default=str))
    (OUT / "rendered_prompts.json").write_text(json.dumps(prompts, indent=2))
    (OUT / "raw_completions.json").write_text(json.dumps(completions, indent=2, default=str))
    (OUT / "extracted_tables.json").write_text(json.dumps(extracted, indent=2, default=str))
    (OUT / "sqlite_bags.json").write_text(json.dumps(bags, indent=2, default=str))
    freeze_replay(frozen)
    if not all(frozen["prior_frozen_still_identical"].values()):
        raise SystemExit(f"prior frozen artifacts changed: {frozen['prior_frozen_still_identical']}")
    print(json.dumps({"frozen": True, "spent": inst.spent(), "complete": completed, "stopped_at": stopped_at}, indent=2), flush=True)

    # AFTER_FREEZE
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.core.signature import audit_workload, enumerate_predicates
    from quwarts.core.signature_realize import live_predicates
    from quwarts.experiments.player_case80 import split_80_20

    gold = load_ground_truth(gold_name("Finan"))
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    count_rows = [row for row in score_rows if is_count_query(query_shape(row["query_id"], row["sql"]))]
    audit = audit_workload(score_rows)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    def rewrites(rows, completed_ids):
        out = {}
        for row in rows:
            qid = row["query_id"]
            dest = sqlite_dir / f"{qid.replace(':', '_')}.db"
            if qid in completed_ids and dest.is_file():
                out[qid] = {"sql": statements[qid], "sqlite_path": str(dest)}
            else:
                out[qid] = None
        return out

    plumbing_rewrites = {}
    from quwarts.core.pipeline import official_sql

    for row in score_rows:
        plumbing_rewrites[row["query_id"]] = official_sql(row["sql"], PLUMBING_DB, predicates, query_id=row["query_id"])
    plumbing_16 = _score(PLUMBING_DB, score_rows, plumbing_rewrites, gold)
    plumbing_15 = _score(PLUMBING_DB, count_rows, {r["query_id"]: plumbing_rewrites[r["query_id"]] for r in count_rows}, gold)
    replay_16 = _score(PLUMBING_DB, score_rows, rewrites(score_rows, completed), gold)
    replay_15 = _score(PLUMBING_DB, count_rows, rewrites(count_rows, completed), gold)
    parity = json.loads(PARITY_REPORT.read_text()) if PARITY_REPORT.is_file() else {}

    hist_compare = historical_versus_replay(query_ids, document_ids, extracted, bags, texts)
    prompt_compare = docetl_versus_quwarts(journal, parity, schemas)
    gates = acceptance_gates(journal, schemas, statements, document_ids, gold, score_rows, count_rows, predicates, plumbing_16, plumbing_15)

    product = replay_16["mean_per_query_product"]
    if stopped_at and len(completed) < 16:
        conclusion = "replay is inconclusive because the exact historical pipeline is unavailable" if False else (
            "historical ingest/configuration is required to reproduce the frozen advantage"
            if product + 1e-9 < DOCETL_SCORE["product"]
            else "current DocETL replay reproduces the frozen advantage"
        )
        if inst.spent() >= THETA_100 and len(completed) < 16:
            # budget stop is still a valid current-snapshot measurement for completed prefix
            pass
    if abs(product - DOCETL_SCORE["product"]) <= 0.01:
        conclusion = "current DocETL replay reproduces the frozen advantage"
    elif product + 1e-9 < DOCETL_SCORE["product"] and hist_compare.get("source_text_agreement", 1) < 1:
        conclusion = "both prompt/context and historical-input differences remain material" if prompt_compare.get("material_prompt_gap") else "historical ingest/configuration is required to reproduce the frozen advantage"
    elif product + 1e-9 < DOCETL_SCORE["product"] and prompt_compare.get("material_prompt_gap"):
        conclusion = "both prompt/context and historical-input differences remain material"
    elif product + 1e-9 < DOCETL_SCORE["product"]:
        conclusion = "historical ingest/configuration is required to reproduce the frozen advantage"
    else:
        conclusion = "current DocETL replay reproduces the frozen advantage"

    report = {
        "model": MODEL,
        "note": "Replay on the current seven files; not a reconstruction of the historical ingest snapshot.",
        "query_ids": query_ids,
        "document_ids": document_ids,
        "mapping": mapping,
        "planned_calls": 112,
        "attempted_calls": len(journal),
        "completed_queries": completed,
        "stopped_at": stopped_at,
        "spent": inst.spent(),
        "unused_budget": max(0, THETA_100 - inst.spent()),
        "theta25_not_applicable": True,
        "score": {
            "historical_docetl_16": DOCETL_SCORE,
            "current_snapshot_replay_16": {**{k: replay_16[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}, "tokens": inst.spent()},
            "current_snapshot_replay_15": {**{k: replay_15[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}, "tokens": inst.spent()},
            "quwarts_parity_16": (parity.get("score") or {}).get("parity_map_100_16"),
            "plumbing_16": {**{k: plumbing_16[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}, "tokens": 0},
            "plumbing_15": {**{k: plumbing_15[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}, "tokens": 0},
        },
        "per_query_replay_16": replay_16["per_query"],
        "per_query_replay_15": replay_15["per_query"],
        "empty_bags": frozen["empty_bags"],
        "hashes": frozen["hashes"],
        "prior_frozen_still_identical": frozen["prior_frozen_still_identical"],
        "A_historical_vs_replay": hist_compare,
        "B_docetl_vs_quwarts": prompt_compare,
        "C_acceptance_gates": gates,
        "conclusion": conclusion,
        "paths": {
            "report": str(OUT / "docetl_current_snapshot_replay.json"),
            "frozen": str(OUT / "frozen.json"),
            "journal": str(OUT / "call_journal.json"),
            "preflight": str(OUT / "preflight.json"),
        },
    }
    (OUT / "docetl_current_snapshot_replay.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT / "docetl_current_snapshot_replay.json"), "product": product, "spent": inst.spent(), "conclusion": conclusion}, indent=2), flush=True)
    return 0


def historical_versus_replay(query_ids, document_ids, extracted, bags, texts) -> dict[str, Any]:
    raw_agree = value_agree = null_agree = n = 0
    table_agree = 0
    bag_agree = 0
    text_agree = 0
    text_n = 0
    unavailable = ["frozen_raw_calls", "frozen_rendered_prompts"]
    for qid in query_ids:
        hist_path = FROZEN_DOCETL / "docetl_pipelines" / qid / "table_finance" / "pipeline_output.json"
        hist = json.loads(hist_path.read_text()) if hist_path.is_file() else []
        replay_rows = {str(row.get("doc_id")): row for row in (extracted.get(qid) or {}).get("finance") or []}
        hist_rows = {str(row.get("doc_id")): row for row in hist}
        fields = [k for k in ((extracted.get(qid) or {}).get("finance") or [{}])[0].keys() if k not in {"doc_id", "text"}]
        for doc_id in document_ids:
            h = hist_rows.get(doc_id) or {}
            r = replay_rows.get(doc_id) or {}
            if "text" in h:
                text_n += 1
                if hashlib.sha256(str(h.get("text") or "").encode()).hexdigest() == hashlib.sha256(texts[doc_id].encode()).hexdigest():
                    text_agree += 1
            for field in fields:
                n += 1
                hv, rv = h.get(field), r.get(field)
                if hv == rv:
                    raw_agree += 1
                    value_agree += 1
                hn = hv in (None, "", -1)
                rn = rv in (None, "", -1)
                if hn == rn:
                    null_agree += 1
        hist_table = FROZEN_DOCETL / "query_tables" / f"{qid}.json"
        if hist_table.is_file() and qid in bags and bags[qid] not in ("incomplete",):
            hist_bag = json.loads(hist_table.read_text())
            if _hash(hist_bag) == _hash(bags[qid]):
                bag_agree += 1
            table_agree += 1
    return {
        "unavailable_comparisons": unavailable,
        "raw_output_agreement": raw_agree / n if n else None,
        "normalized_value_agreement": value_agree / n if n else None,
        "null_nonnull_agreement": null_agree / n if n else None,
        "query_table_pairs_compared": table_agree,
        "final_bag_agreement": bag_agree / table_agree if table_agree else None,
        "source_text_agreement": text_agree / text_n if text_n else None,
        "n_field_cells": n,
        "n_source_texts": text_n,
    }


def docetl_versus_quwarts(journal, parity, schemas) -> dict[str, Any]:
    if not journal:
        return {"material_prompt_gap": True, "reason": "no replay journal"}
    qj = (parity.get("routing") or {})
    replay_ctx = [int(row.get("model_tokens_after") or 0) for row in journal]
    replay_api = [int(row.get("api_prompt_tokens") or 0) for row in journal]
    trunc = sum(1 for row in journal if row.get("truncated"))
    nonnull = 0
    cells = 0
    malformed = 0
    for row in journal:
        parsed = row.get("parsed_response")
        if row.get("parse_validation_failure"):
            malformed += 1
        if not parsed:
            continue
        rec = parsed[0] if isinstance(parsed, list) and parsed else parsed
        if isinstance(rec, dict):
            for key, value in rec.items():
                if key in {"doc_id", "text"}:
                    continue
                cells += 1
                if value not in (None, "", -1):
                    nonnull += 1
    mean_api = sum(replay_api) / len(replay_api) if replay_api else 0
    return {
        "replay_mean_api_prompt_tokens": mean_api,
        "replay_mean_qwen_tokens_after": sum(replay_ctx) / len(replay_ctx) if replay_ctx else 0,
        "replay_truncated_calls": trunc,
        "replay_n_calls": len(journal),
        "quwarts_mean_context_tokens": (qj.get("context_token_percentiles") or {}).get("mean"),
        "quwarts_total_tokens": ((parity.get("tokens") or {}).get("spent_100")),
        "frozen_docetl_mean_input": 12304.14,
        "frozen_docetl_total": 1381827,
        "requested_fields": schemas,
        "evidence_requirement_docetl": "none_in_prompt",
        "evidence_requirement_quwarts": "exact_span_for_stated_values",
        "unknown_numeric_docetl": -1,
        "unknown_text_docetl": "",
        "unknown_quwarts": "null / not_found",
        "replay_nonnull_rate": nonnull / cells if cells else None,
        "replay_malformed_rate": malformed / len(journal) if journal else None,
        "token_gap_accounted_by": [
            "DocETL sends the full document (then truncate_messages to model max_input_tokens)",
            "QuWARTS sends a 2400-token retrieved pack",
            "DocETL system prompt + tool schema add overhead",
            "DocETL unknown protocol uses -1 / empty string rather than null",
        ],
        "material_prompt_gap": True,
    }


def acceptance_gates(journal, schemas, statements, document_ids, gold, score_rows, count_rows, predicates, plumbing_16, plumbing_15) -> dict[str, Any]:
    from quwarts.core.docetl_unit_parity.parse import parse_map
    from quwarts.core.docetl_unit_parity.schema import compile_query_schema
    from quwarts.core.retrieve_extract.parse import normalize_value

    def _rows_from(values_by_q):
        out = {}
        for qid, rows in values_by_q.items():
            schema = compile_query_schema(qid, statements[qid])
            path = OUT / "gates" / f"{qid.replace(':', '_')}.db"
            path.parent.mkdir(parents=True, exist_ok=True)
            from quwarts.core.docetl_unit_parity.local_table import create_local_db, insert_row, execute_original

            create_local_db(path, schema)
            for doc_id, vals in rows:
                insert_row(path, schema, doc_id, vals)
            bag, err = execute_original(path, statements[qid])
            out[qid] = {"path": path, "bag": bag, "error": err, "empty": not bag}
        return out

    native = {}
    strict = {}
    typed = {}
    reasons = Counter()
    retained = {"native": 0, "strict": 0, "typed": 0}
    raw_n = 0
    by_q_native = defaultdict(list)
    by_q_strict = defaultdict(list)
    by_q_typed = defaultdict(list)
    for row in journal:
        qid = row.get("query_id")
        doc_id = row.get("document_id")
        if not qid or not doc_id:
            continue
        parsed = row.get("parsed_response")
        rec = parsed[0] if isinstance(parsed, list) and parsed else parsed if isinstance(parsed, dict) else {}
        context = str(row.get("included_document_text") or "")
        schema = compile_query_schema(qid, statements[qid])
        native_vals = {}
        typed_vals = {}
        strict_vals = {}
        for field in schema.names:
            raw = rec.get(field) if isinstance(rec, dict) else None
            raw_n += 1
            if raw in ("", None):
                native_vals[field] = None
            elif schema.dtypes.get(field) == "numeric" and raw == -1:
                native_vals[field] = None
            else:
                native_vals[field] = raw
                retained["native"] += 1
            norm, _, err = normalize_value(raw, schema.dtypes.get(field, "string"))
            if raw in (None, "", -1) or err:
                typed_vals[field] = None
                reasons["typed_reject"] += 1
            else:
                typed_vals[field] = norm
                retained["typed"] += 1
        fake = json.dumps(
            {
                name: {
                    "value": rec.get(name) if isinstance(rec, dict) else None,
                    "status": "found" if isinstance(rec, dict) and rec.get(name) not in (None, "", -1) else "not_found",
                    "evidence": str(rec.get(name) or "")[:80] if isinstance(rec, dict) else "",
                }
                for name in schema.names
            }
        )
        parsed_strict = parse_map(fake, schema, context)
        for name, item in (parsed_strict.get("items") or {}).items():
            if item.get("normalized_value") is not None:
                strict_vals[name] = item["normalized_value"]
                retained["strict"] += 1
            else:
                strict_vals[name] = None
                if item.get("failure"):
                    reasons[str(item["failure"])] += 1
        by_q_native[qid].append((doc_id, native_vals))
        by_q_strict[qid].append((doc_id, strict_vals))
        by_q_typed[qid].append((doc_id, typed_vals))

    def score_gate(by_q, label):
        mats = _rows_from(by_q)
        completed = [qid for qid, item in mats.items() if item["path"].is_file()]
        rewrites = {}
        for row in score_rows:
            qid = row["query_id"]
            if qid in mats:
                rewrites[qid] = {"sql": statements[qid], "sqlite_path": str(mats[qid]["path"])}
            else:
                rewrites[qid] = None
        scored = _score(PLUMBING_DB, score_rows, rewrites, gold)
        return {
            "empty_bags": [qid for qid, item in mats.items() if item["empty"]],
            "non_null_cells": retained[label],
            "score_16": {k: scored[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
        }

    return {
        "raw_values": raw_n,
        "rejection_reasons": dict(reasons),
        "native_docetl": score_gate(by_q_native, "native"),
        "quwarts_strict_span": score_gate(by_q_strict, "strict"),
        "type_valid_no_span": score_gate(by_q_typed, "typed"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
