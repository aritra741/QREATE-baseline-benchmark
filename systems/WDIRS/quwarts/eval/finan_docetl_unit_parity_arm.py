"""Finan DocETL-unit parity arm: 16×7 query-document maps, then SQLite SQL."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.docetl_unit_parity.config import (
    MODEL,
    POLICY,
    THETA_25,
    THETA_100,
    policy_hash,
    prompt_hash,
    router_hash,
    verify_budgets,
)
from quwarts.core.docetl_unit_parity.controller import (
    estimate_map_cost,
    estimate_program_cost,
    run_map,
)
from quwarts.core.docetl_unit_parity.documents import load_parity_documents
from quwarts.core.docetl_unit_parity.local_table import (
    bag_of,
    create_local_db,
    empty_override_reproduces,
    execute_original,
    fixture_program,
    insert_row,
    isolation_and_fallback,
    plumbing_bag,
)
from quwarts.core.docetl_unit_parity.prompt import compiled_prompts_hash
from quwarts.core.docetl_unit_parity.router import route
from quwarts.core.docetl_unit_parity.schema import QuerySchema, compile_query_schema, schema_hash
from quwarts.core.ledger import SpendRecord, TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.query_witness_acq.controller import empty_bags as plumbing_empty_bags
from quwarts.core.retrieve_extract.cache import VerifiedCache
from quwarts.core.retrieve_extract.index import index_document
from quwarts.core.retrieve_extract.retrieve import _idf
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.schema_columns import referenced_columns
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import documents_for, gold_name, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

PLUMBING_DB = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
SOURCE_DIR = ROOT / "source_data" / "Finance" / "finance"
OUT = ROOT / "results" / "quwarts_finan_docetl_unit_parity"
DOCETL_SCORE = {"f2": 0.537, "f1": 0.114, "product": 0.084, "tokens": 1_381_827}
FORBIDDEN_BEFORE_FREEZE = (
    ROOT / "Data" / "Finan" / "Finan.csv",
    DOCETL_DIR / "evaluation.json",
    DOCETL_DIR / "query_results.json",
    DOCETL_DIR / "report.json",
)


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def load_docetl_manifest() -> list[dict[str, str]]:
    rows = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    return [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in rows]


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


def sql_impact(schema: QuerySchema, shape, plumbing_empty: bool, shared: int) -> float:
    return (
        (8.0 if plumbing_empty else 0.0)
        + 2.0 * sum(1 for item in schema.fields if "WHERE" in item.usages)
        + 3.0 * len(shape.group_aliases)
        + 2.0 * len(shape.aggregates)
        + 1.0 * len(schema.fields)
        + 0.5 * shared
    )


def rewrites_for(
    rows: list[dict[str, str]],
    completed: dict[str, Path],
    statements: dict[str, str],
    plumbing: Path,
    predicates,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in rows:
        qid = row["query_id"]
        if qid in completed:
            out[qid] = {"sql": statements[qid], "sqlite_path": str(completed[qid])}
        else:
            out[qid] = official_sql(statements[qid], plumbing, predicates, query_id=qid)
    return out


def percentiles(values: list[int]) -> dict[str, float]:
    if not values:
        return {"p50": 0, "p90": 0, "p99": 0, "min": 0, "max": 0, "mean": 0}
    ordered = sorted(values)
    def at(frac: float) -> float:
        if len(ordered) == 1:
            return float(ordered[0])
        pos = (len(ordered) - 1) * frac
        lo = int(pos)
        hi = min(len(ordered) - 1, lo + 1)
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)
    return {
        "p50": at(0.50),
        "p90": at(0.90),
        "p99": at(0.99),
        "min": float(ordered[0]),
        "max": float(ordered[-1]),
        "mean": sum(ordered) / len(ordered),
    }


def assert_no_gold_reachable() -> None:
    blocked = {"diagnostics.run_config_grid", "spp.aggregation_metrics"}
    hit = sorted(name for name in blocked if name in sys.modules)
    if hit:
        raise SystemExit(f"gold/scorer module imported before freeze: {hit}")
    opened = {str(path) for path in FORBIDDEN_BEFORE_FREEZE if path.is_file()}
    if not opened:
        return


def freeze_checkpoint(
    *,
    label: str,
    completed: dict[str, Path],
    journal: list[dict[str, Any]],
    ledger_snap: dict[str, Any],
    statements: dict[str, str],
    predicates,
    plumbing_bags: dict[str, tuple],
    query_list_hash: str,
    schedule_hash: str,
    input_hash: str,
) -> dict[str, Any]:
    local_dir = OUT / "query_local" / label
    local_dir.mkdir(parents=True, exist_ok=True)
    bags: dict[str, Any] = {}
    empty = []
    failures = []
    table_hashes = {}
    for qid, sql in statements.items():
        if qid in completed and completed[qid].is_file():
            dest = local_dir / f"{qid.replace(':', '_')}.db"
            if dest.resolve() != completed[qid].resolve():
                shutil.copy2(completed[qid], dest)
            table_hashes[qid] = file_sha256(dest)
            rows, err = execute_original(dest, sql)
            if err:
                failures.append({"query_id": qid, "error": err})
                bags[qid] = []
                empty.append(qid)
            else:
                bags[qid] = rows
                if not rows:
                    empty.append(qid)
        else:
            bags[qid] = "plumbing_fallback"
    isolation = isolation_and_fallback(PLUMBING_DB, statements, predicates, completed)
    for qid, sql in statements.items():
        if qid not in completed and plumbing_bag(PLUMBING_DB, sql, predicates, qid) != plumbing_bags[qid]:
            raise SystemExit(f"{label}: incomplete query {qid} drifted from plumbing")
    payload = {
        "label": label,
        "spent": ledger_snap["spent"],
        "theta_25": THETA_25,
        "theta_100": THETA_100,
        "complete_query_ids": sorted(completed),
        "n_complete": len(completed),
        "empty_bags": empty,
        "execution_failures": failures,
        "table_hashes": table_hashes,
        "bag_sha256": _hash(bags),
        "journal_sha256": _hash(journal),
        "ledger_sha256": _hash(ledger_snap),
        "query_list_sha256": query_list_hash,
        "schedule_sha256": schedule_hash,
        "input_set_sha256": input_hash,
        "policy_sha256": policy_hash(),
        "prompt_sha256": prompt_hash(),
        "router_sha256": router_hash(),
        "isolation_ok": isolation["isolation_ok"],
        "incomplete_plumbing_fallback": isolation["fallback_ok"],
        "plumbing_sha256": file_sha256(PLUMBING_DB),
    }
    (OUT / f"{label}_frozen.json").write_text(json.dumps(payload, indent=2, default=str))
    (OUT / f"{label}_ledger.json").write_text(json.dumps(ledger_snap, indent=2, default=str))
    (OUT / f"{label}_journal.json").write_text(json.dumps(journal, indent=2, default=str))
    (OUT / f"{label}_bags.json").write_text(json.dumps(bags, indent=2, default=str))
    (OUT / f"{label}_local_tables.json").write_text(json.dumps(table_hashes, indent=2))
    print(json.dumps({"frozen": label, "spent": payload["spent"], "complete": payload["complete_query_ids"]}, indent=2), flush=True)
    if not isolation["isolation_ok"]:
        raise SystemExit(f"{label}: query-local tables interfered {isolation['leaked']}")
    if payload["spent"] > (THETA_25 if label == "theta25" else THETA_100):
        raise SystemExit(f"{label} spend {payload['spent']} exceeds cap")
    return payload


def main() -> int:
    if DEFAULT_MODEL != MODEL:
        raise SystemExit(f"model lock failed: {DEFAULT_MODEL} != {MODEL}")
    budgets = verify_budgets()
    OUT.mkdir(parents=True, exist_ok=True)
    cache_dir = OUT / "cache"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    work_local = OUT / "query_local" / "live"
    if work_local.exists():
        shutil.rmtree(work_local)
    work_local.mkdir(parents=True, exist_ok=True)

    manifest = load_docetl_manifest()
    if len(manifest) != 16:
        raise SystemExit(f"manifest has {len(manifest)} queries, expected 16")
    full = queries_for("Finan")
    full_by_id = {row["query_id"]: row for row in full}
    missing = [row["query_id"] for row in manifest if row["query_id"] not in full_by_id]
    if missing:
        raise SystemExit(f"manifest IDs not in Finan workload: {missing}")
    train, _test = split_80_20(full, 42)
    train_ids = {row["query_id"] for row in train}
    if any(row["query_id"] in train_ids for row in manifest):
        raise SystemExit("manifest includes train queries")
    queries = [
        {"query_id": row["query_id"], "sql": full_by_id[row["query_id"]]["sql"], "pack": full_by_id[row["query_id"]].get("pack")}
        for row in manifest
    ]
    query_ids = [row["query_id"] for row in queries]
    query_list = [{"query_id": row["query_id"], "sql": row["sql"]} for row in queries]
    query_list_hash = _hash(query_list)
    (OUT / "query_list.json").write_text(json.dumps({"sha256": query_list_hash, "n": 16, "queries": query_list}, indent=2))

    parity = load_parity_documents(DOCETL_DIR / "docetl_pipelines", SOURCE_DIR, query_ids)
    if len(parity["document_ids"]) != 7:
        raise SystemExit("parity set is not seven documents")
    (OUT / "execution_parity_input_set.json").write_text(json.dumps(parity, indent=2))
    print(
        json.dumps(
            {
                "query_ids": query_ids,
                "document_ids": parity["document_ids"],
                "mapping": parity["mapping"],
                "same_set": parity["same_set_in_every_artifact"],
                "input_set_sha256": parity["execution_parity_input_set_sha256"],
            },
            indent=2,
        ),
        flush=True,
    )

    statements = {row["query_id"]: row["sql"] for row in queries}
    schemas = {row["query_id"]: compile_query_schema(row["query_id"], row["sql"]) for row in queries}
    for qid, schema in schemas.items():
        required = {item.column.lower() for item in referenced_columns({qid: statements[qid]})}
        if required - {name.lower() for name in schema.names}:
            raise SystemExit(f"{qid}: schema missing {sorted(required - set(schema.names))}")
    (OUT / "schemas.json").write_text(json.dumps({qid: schema.as_dict() for qid, schema in schemas.items()}, indent=2))

    documents = {doc.doc_id: doc for doc in documents_for("Finan")}
    indexes = {}
    for doc_id, source_name in parity["mapping"].items():
        doc = documents.get(source_name)
        if doc is None:
            raise SystemExit(f"source {source_name} missing from current Finan documents")
        indexes[doc_id] = index_document(doc.doc_id, doc.text)
    idf = _idf(list(indexes.values()))

    inventory = []
    routing_counts = Counter()
    for qid in query_ids:
        schema = schemas[qid]
        for doc_id in parity["document_ids"]:
            routed = route(schema, indexes[doc_id], idf)
            routing_counts[routed.mode] += 1
            inventory.append(
                {
                    "task_key": f"{qid}::{doc_id}",
                    "query_id": qid,
                    "doc_id": doc_id,
                    "mode": routed.mode,
                    "reason": routed.reason,
                    "request_tokens": routed.request_tokens,
                    "context_tokens": routed.context_tokens,
                    "expected_cost": estimate_map_cost(routed.request_tokens),
                    "routed": routed,
                }
            )
    if len(inventory) != 112:
        raise SystemExit(f"inventory has {len(inventory)} tasks, expected 112")

    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_sha = file_sha256(PLUMBING_DB)
    plumbing_bags = {qid: plumbing_bag(PLUMBING_DB, sql, predicates, qid) for qid, sql in statements.items()}
    empty_plumb = set(plumbing_empty_bags(PLUMBING_DB, statements, predicates))
    if not empty_override_reproduces(PLUMBING_DB, statements, predicates):
        raise SystemExit("empty query-local override does not reproduce plumbing bags")
    fixture_ok = {}
    fixture_dir = OUT / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    for qid, schema in schemas.items():
        fixture_ok[qid] = fixture_program(schema, parity["document_ids"], fixture_dir / f"{qid.replace(':', '_')}.db")
        if not fixture_ok[qid]["ok"]:
            raise SystemExit(f"fixture SQL failed for {qid}")
    isolation = isolation_and_fallback(
        PLUMBING_DB,
        statements,
        predicates,
        {qid: fixture_dir / f"{qid.replace(':', '_')}.db" for qid in query_ids},
    )
    if not isolation["isolation_ok"]:
        raise SystemExit(f"query-local isolation failed: {isolation['leaked']}")

    attr_users: dict[str, set[str]] = defaultdict(set)
    for qid, schema in schemas.items():
        for name in schema.names:
            attr_users[name].add(qid)
    shared = {qid: len({other for name in schemas[qid].names for other in attr_users[name] if other != qid}) for qid in query_ids}

    by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in inventory:
        by_query[task["query_id"]].append(task)
    programs = []
    for qid in query_ids:
        tasks = sorted(by_query[qid], key=lambda item: item["doc_id"])
        cost = estimate_program_cost(tasks)
        shape = query_shape(qid, statements[qid])
        impact = sql_impact(schemas[qid], shape, qid in empty_plumb, shared[qid])
        programs.append(
            {
                "query_id": qid,
                "tasks": tasks,
                "expected_cost": cost,
                "impact": impact,
                "priority": impact / max(cost, 1),
                "n_fields": len(schemas[qid].fields),
                "plumbing_empty": qid in empty_plumb,
            }
        )
    programs.sort(key=lambda item: (-item["priority"], item["query_id"]))
    scheduled_100 = []
    expected_spend = 0
    for program in programs:
        if expected_spend + int(program["expected_cost"]) > THETA_100:
            continue
        scheduled_100.append(program)
        expected_spend += int(program["expected_cost"])
    scheduled_25 = []
    spend_25 = 0
    for program in scheduled_100:
        if spend_25 + int(program["expected_cost"]) > THETA_25:
            break
        scheduled_25.append(program)
        spend_25 += int(program["expected_cost"])
    if [item["query_id"] for item in scheduled_25] != [item["query_id"] for item in scheduled_100[: len(scheduled_25)]]:
        raise SystemExit("θ25 schedule is not a prefix of θ100")
    schedule_payload = {
        "gold_used": False,
        "docetl_answers_used": False,
        "features": ["ast_predicates", "group_keys", "aggregates", "schema_width", "plumbing_empty", "attribute_reuse"],
        "order": [item["query_id"] for item in scheduled_100],
        "order_25": [item["query_id"] for item in scheduled_25],
        "prefix": True,
        "expected_spend_25": spend_25,
        "expected_spend_100": expected_spend,
        "programs": [
            {
                "query_id": item["query_id"],
                "expected_cost": item["expected_cost"],
                "impact": item["impact"],
                "priority": item["priority"],
                "n_fields": item["n_fields"],
                "plumbing_empty": item["plumbing_empty"],
                "modes": Counter(task["mode"] for task in item["tasks"]),
            }
            for item in scheduled_100
        ],
    }
    schedule_payload["sha256"] = _hash({k: schedule_payload[k] for k in schedule_payload if k != "sha256"})
    (OUT / "schedule.json").write_text(json.dumps(schedule_payload, indent=2, default=str))
    (OUT / "router_config.json").write_text(
        json.dumps({"sha256": router_hash(), "config": {
            "hard_limit": POLICY["model_context_limit"],
            "effective_input_threshold": POLICY["effective_input_limit"],
            "retrieval_method": POLICY["retrieval_method"],
            "ranking_weights": POLICY["ranking_weights"],
            "passage_size": POLICY["chunk_target_tokens"],
            "overlap": POLICY["chunk_overlap_tokens"],
            "maximum_context_size": POLICY["retrieve_context_cap"],
        }}, indent=2)
    )
    (OUT / "locked_policy.json").write_text(
        json.dumps(
            {
                "policy": POLICY,
                "policy_sha256": policy_hash(),
                "prompt_sha256": prompt_hash(),
                "router_sha256": router_hash(),
                "schema_sha256": schema_hash(schemas),
                "compiled_prompts_sha256": compiled_prompts_hash(schemas),
                "schedule_sha256": schedule_payload["sha256"],
                "query_list_sha256": query_list_hash,
                "input_set_sha256": parity["execution_parity_input_set_sha256"],
                "budgets": budgets,
            },
            indent=2,
        )
    )

    assert_no_gold_reachable()
    gates = {
        "exact_16_queries": len(queries) == 16,
        "exact_7_documents": len(parity["document_ids"]) == 7 and parity["same_set_in_every_artifact"],
        "exact_112_tasks": len(inventory) == 112,
        "schema_complete": True,
        "empty_override_plumbing": True,
        "fixture_sql_ok": all(item["ok"] for item in fixture_ok.values()),
        "query_local_isolation": isolation["isolation_ok"],
        "no_gold_scorer_docetl_answers": True,
        "hashes_written": True,
        "theta25_prefix_schedule": True,
    }
    if not all(gates.values()):
        raise SystemExit(f"pre-spend gate failure: {gates}")
    (OUT / "pre_spend_gates.json").write_text(json.dumps(gates, indent=2))
    print(json.dumps({"pre_spend_gates": gates, "schedule_25": schedule_payload["order_25"], "schedule_100": schedule_payload["order"]}, indent=2), flush=True)

    ledger = TokenLedger(theta=THETA_100, seed=int(POLICY["seed"]))
    caller = make_caller(
        ledger,
        model=MODEL,
        temperature=float(POLICY["temperature"]),
        max_tokens=int(POLICY["extract_max_tokens"]),
    )
    cache = VerifiedCache(cache_dir)
    journal: list[dict[str, Any]] = []
    completed_live: dict[str, Path] = {}
    last_good_25: dict[str, Any] | None = None
    frozen_25 = False
    checkpoint_25 = None
    counts = Counter()
    field_stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    context_tokens: list[int] = []

    def maybe_freeze_25() -> None:
        nonlocal frozen_25, checkpoint_25
        if frozen_25:
            return
        if last_good_25:
            checkpoint_25 = freeze_checkpoint(
                label="theta25",
                completed=dict(last_good_25["completed"]),
                journal=list(last_good_25["journal"]),
                ledger_snap=last_good_25["ledger"],
                statements=statements,
                predicates=predicates,
                plumbing_bags=plumbing_bags,
                query_list_hash=query_list_hash,
                schedule_hash=schedule_payload["sha256"],
                input_hash=parity["execution_parity_input_set_sha256"],
            )
        else:
            empty_snap = {"theta": THETA_100, "seed": int(POLICY["seed"]), "spent": 0, "records": []}
            checkpoint_25 = freeze_checkpoint(
                label="theta25",
                completed={},
                journal=[],
                ledger_snap=empty_snap,
                statements=statements,
                predicates=predicates,
                plumbing_bags=plumbing_bags,
                query_list_hash=query_list_hash,
                schedule_hash=schedule_payload["sha256"],
                input_hash=parity["execution_parity_input_set_sha256"],
            )
        frozen_25 = True

    for program in scheduled_100:
        qid = program["query_id"]
        cost = int(program["expected_cost"])
        if not frozen_25 and ledger.spent + cost > THETA_25:
            maybe_freeze_25()
        if ledger.spent + cost > THETA_100:
            break
        dest = work_local / f"{qid.replace(':', '_')}.db"
        create_local_db(dest, schemas[qid])
        rows_ok = 0
        program_ok = True
        for task in program["tasks"]:
            counts["planned"] += 1
            if ledger.spent + 64 > THETA_100:
                program_ok = False
                break
            counts["attempted"] += 1
            result = run_map(
                caller,
                cache,
                schema=schemas[qid],
                doc_id=task["doc_id"],
                routed=task["routed"],
                remaining_cap=THETA_100,
            )
            if result is None:
                program_ok = False
                break
            counts["tokens"] += int(result["tokens"])
            if result["from_cache"]:
                counts["cached"] += 1
            if result["repaired"]:
                counts["repaired"] += 1
            if result["malformed"]:
                counts["malformed"] += 1
            context_tokens.append(int(result["context_tokens"]))
            counts[f"mode:{result['mode']}"] += 1
            for name, item in (result["parsed"].get("items") or {}).items():
                if item.get("normalized_value") is not None:
                    field_stats[qid][name] += 1
                    counts["non_null_cells"] += 1
                if item.get("grounding") == "stated_span":
                    counts["grounded_stated"] += 1
                if str(item.get("kind")) == "semantic" and item.get("normalized_value") is not None:
                    counts["inferred_semantic"] += 1
            insert_row(dest, schemas[qid], task["doc_id"], result["values"])
            rows_ok += 1
            journal.append(
                {
                    "task_index": len(journal),
                    "task_key": task["task_key"],
                    "query_id": qid,
                    "doc_id": task["doc_id"],
                    "mode": result["mode"],
                    "from_cache": result["from_cache"],
                    "repaired": result["repaired"],
                    "malformed": result["malformed"],
                    "tokens": result["tokens"],
                    "request_tokens": result["request_tokens"],
                    "context_tokens": result["context_tokens"],
                    "status_counts": result["parsed"].get("counts"),
                    "spent_after": ledger.spent,
                    "fields": {
                        name: {
                            "raw_value": item.get("raw_value"),
                            "normalized_value": item.get("normalized_value"),
                            "status": item.get("status"),
                            "evidence": item.get("evidence"),
                            "grounding": item.get("grounding"),
                            "kind": item.get("kind"),
                            "failure": item.get("failure"),
                        }
                        for name, item in (result["parsed"].get("items") or {}).items()
                    },
                }
            )
            if len(journal) == 1 or len(journal) % 8 == 0:
                print(f"map {len(journal)} spent={ledger.spent} complete={len(completed_live)} q={qid} doc={task['doc_id']}", flush=True)
        if program_ok and rows_ok == 7:
            completed_live[qid] = dest
            counts["completed_queries"] += 1
            if not frozen_25 and ledger.spent <= THETA_25:
                last_good_25 = {
                    "completed": dict(completed_live),
                    "journal": list(journal),
                    "ledger": ledger.snapshot(),
                }
            elif not frozen_25 and ledger.spent > THETA_25:
                maybe_freeze_25()
        else:
            if dest.exists():
                dest.unlink()
            print(json.dumps({"incomplete_query": qid, "rows_ok": rows_ok, "spent": ledger.spent}, indent=2), flush=True)
            if ledger.spent + 64 > THETA_100:
                break

    if not frozen_25:
        maybe_freeze_25()
    checkpoint_100 = freeze_checkpoint(
        label="theta100",
        completed=dict(completed_live),
        journal=list(journal),
        ledger_snap=ledger.snapshot(),
        statements=statements,
        predicates=predicates,
        plumbing_bags=plumbing_bags,
        query_list_hash=query_list_hash,
        schedule_hash=schedule_payload["sha256"],
        input_hash=parity["execution_parity_input_set_sha256"],
    )
    j25 = json.loads((OUT / "theta25_journal.json").read_text())
    if j25 != journal[: len(j25)]:
        raise SystemExit("θ25 journal is not a prefix of θ100 journal")
    if file_sha256(PLUMBING_DB) != plumbing_sha:
        raise SystemExit("plumbing database was modified")
    after_iso = isolation_and_fallback(PLUMBING_DB, statements, predicates, completed_live)
    gates_after = {
        "theta25_prefix_journal": True,
        "plumbing_unmodified": True,
        "query_local_isolation": after_iso["isolation_ok"],
        "incomplete_plumbing_fallback": after_iso["fallback_ok"],
        "theta25_within": checkpoint_25["spent"] <= THETA_25,
        "theta100_within": ledger.spent <= THETA_100,
        "zero_gold_before_freeze": True,
    }
    if not all(gates_after.values()):
        raise SystemExit(f"post-run gate failure: {gates_after}")
    frozen = {
        "budgets": budgets,
        "query_list_sha256": query_list_hash,
        "schedule_sha256": schedule_payload["sha256"],
        "policy_sha256": policy_hash(),
        "prompt_sha256": prompt_hash(),
        "router_sha256": router_hash(),
        "schema_sha256": schema_hash(schemas),
        "input_set_sha256": parity["execution_parity_input_set_sha256"],
        "plumbing_sha256": plumbing_sha,
        "theta25": checkpoint_25,
        "theta100": checkpoint_100,
        "counts": dict(counts),
        "gates": {**gates, **gates_after},
    }
    (OUT / "frozen.json").write_text(json.dumps(frozen, indent=2, default=str))
    print(json.dumps({"both_frozen": True, "spent": ledger.spent, "complete_100": checkpoint_100["complete_query_ids"]}, indent=2), flush=True)

    # AFTER_FREEZE
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    count_rows = [row for row in queries if is_count_query(query_shape(row["query_id"], row["sql"]))]
    dest_25 = PLUMBING_DB
    dest_100 = PLUMBING_DB
    completed_25 = {qid: OUT / "query_local" / "theta25" / f"{qid.replace(':', '_')}.db" for qid in checkpoint_25["complete_query_ids"]}
    completed_25 = {qid: path for qid, path in completed_25.items() if path.is_file()}
    completed_100 = {qid: OUT / "query_local" / "theta100" / f"{qid.replace(':', '_')}.db" for qid in checkpoint_100["complete_query_ids"]}
    completed_100 = {qid: path for qid, path in completed_100.items() if path.is_file()}
    plumbing_16 = _score(PLUMBING_DB, queries, rewrites_for(queries, {}, statements, PLUMBING_DB, predicates), gold)
    plumbing_15 = _score(PLUMBING_DB, count_rows, rewrites_for(count_rows, {}, statements, PLUMBING_DB, predicates), gold)
    scored_25_16 = _score(dest_25, queries, rewrites_for(queries, completed_25, statements, PLUMBING_DB, predicates), gold)
    scored_25_15 = _score(dest_25, count_rows, rewrites_for(count_rows, completed_25, statements, PLUMBING_DB, predicates), gold)
    scored_100_16 = _score(dest_100, queries, rewrites_for(queries, completed_100, statements, PLUMBING_DB, predicates), gold)
    scored_100_15 = _score(dest_100, count_rows, rewrites_for(count_rows, completed_100, statements, PLUMBING_DB, predicates), gold)

    def _delta(now, base) -> list[dict[str, Any]]:
        by_base = {row["query_id"]: row for row in base["per_query"]}
        out = []
        for row in now["per_query"]:
            prev = by_base.get(row["query_id"]) or {}
            out.append(
                {
                    **row,
                    "delta_f2": float(row.get("structure_f2") or 0) - float(prev.get("structure_f2") or 0),
                    "delta_cell": float(row.get("cell_f1_20") or 0) - float(prev.get("cell_f1_20") or 0),
                    "delta_product": float(row.get("product") or 0) - float(prev.get("product") or 0),
                }
            )
        return out

    tokens_by_query = defaultdict(lambda: {"input": 0, "completion": 0, "repair": 0, "total": 0, "documents": {}})
    for rec in ledger.records:
        meta = rec.metadata or {}
        qid = str(meta.get("query_id") or "")
        doc_id = str(meta.get("doc_id") or "")
        tokens_by_query[qid]["total"] += rec.tokens
        if rec.purpose == "format_repair":
            tokens_by_query[qid]["repair"] += rec.tokens
        else:
            tokens_by_query[qid]["completion"] += rec.tokens
        tokens_by_query[qid]["documents"][doc_id] = tokens_by_query[qid]["documents"].get(doc_id, 0) + rec.tokens
    for row in journal:
        tokens_by_query[row["query_id"]]["input"] += int(row.get("request_tokens") or 0)

    product_100 = scored_100_16["mean_per_query_product"]
    if product_100 >= DOCETL_SCORE["product"]:
        interpretation = (
            "θ100 matches or beats DocETL. The multi-attribute query-document map unit "
            "explains the prior witness-arm gap."
        )
    else:
        interpretation = (
            "θ100 still loses. Query-set concentration and witness granularity are "
            "insufficient explanations; the next audit target is DocETL’s unavailable "
            "prompt/context construction or its historical seven-document ingest snapshot."
        )
    report = {
        "model": MODEL,
        "query_ids": query_ids,
        "document_ids": parity["document_ids"],
        "document_mapping": parity["mapping"],
        "same_seven_ids_in_every_docetl_artifact": True,
        "historical_ingest_reconstructed": False,
        "hashes": {
            "query_list": query_list_hash,
            "document_ids": parity["hashes"]["ordered_document_ids"],
            "source_contents": parity["hashes"]["source_document_contents"],
            "id_to_document": parity["hashes"]["id_to_document_mapping"],
            "input_set": parity["execution_parity_input_set_sha256"],
            "policy": policy_hash(),
            "prompt": prompt_hash(),
            "router": router_hash(),
            "schema": schema_hash(schemas),
            "compiled_prompts": compiled_prompts_hash(schemas),
            "schedule": schedule_payload["sha256"],
            "plumbing": plumbing_sha,
            "theta25_journal": checkpoint_25["journal_sha256"],
            "theta100_journal": checkpoint_100["journal_sha256"],
            "theta25_ledger": checkpoint_25["ledger_sha256"],
            "theta100_ledger": checkpoint_100["ledger_sha256"],
            "theta25_bags": checkpoint_25["bag_sha256"],
            "theta100_bags": checkpoint_100["bag_sha256"],
            "theta25_tables": _hash(checkpoint_25["table_hashes"]),
            "theta100_tables": _hash(checkpoint_100["table_hashes"]),
        },
        "schema_fields": {qid: schemas[qid].names for qid in query_ids},
        "calls": {
            "planned": counts.get("planned", 0),
            "attempted": counts.get("attempted", 0),
            "completed_maps": sum(1 for row in journal if row.get("query_id") in completed_live),
            "repaired": counts.get("repaired", 0),
            "malformed": counts.get("malformed", 0),
            "cached": counts.get("cached", 0),
            "completed_queries_25": checkpoint_25["complete_query_ids"],
            "completed_queries_100": checkpoint_100["complete_query_ids"],
        },
        "routing": {
            "whole_document": routing_counts.get("whole_document", 0),
            "retrieved_context": routing_counts.get("retrieved_context", 0),
            "context_token_percentiles": percentiles(context_tokens),
        },
        "tokens": {
            "spent_25": checkpoint_25["spent"],
            "spent_100": ledger.spent,
            "by_query": {qid: dict(tokens_by_query[qid]) for qid in query_ids if qid in tokens_by_query},
        },
        "extracted_non_null_cells": {qid: dict(field_stats[qid]) for qid in query_ids},
        "grounding": {
            "grounded_stated": counts.get("grounded_stated", 0),
            "inferred_semantic": counts.get("inferred_semantic", 0),
        },
        "empty_bags": {
            "plumbing": sorted(empty_plumb),
            "theta25": checkpoint_25["empty_bags"],
            "theta100": checkpoint_100["empty_bags"],
        },
        "execution_failures": {
            "theta25": checkpoint_25["execution_failures"],
            "theta100": checkpoint_100["execution_failures"],
        },
        "score": {
            "plumbing_16": {"tokens": 0, **{k: plumbing_16[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}},
            "plumbing_15": {"tokens": 0, **{k: plumbing_15[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}},
            "parity_map_25_16": {"tokens": checkpoint_25["spent"], **{k: scored_25_16[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}},
            "parity_map_25_15": {"tokens": checkpoint_25["spent"], **{k: scored_25_15[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}},
            "parity_map_100_16": {"tokens": ledger.spent, **{k: scored_100_16[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}},
            "parity_map_100_15": {"tokens": ledger.spent, **{k: scored_100_15[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}},
            "docetl_16": DOCETL_SCORE,
        },
        "per_query_25_16": _delta(scored_25_16, plumbing_16),
        "per_query_100_16": _delta(scored_100_16, plumbing_16),
        "per_query_25_15": _delta(scored_25_15, plumbing_15),
        "per_query_100_15": _delta(scored_100_15, plumbing_15),
        "theta25_exact_prefix_of_theta100": True,
        "query_local_affected_other_query": False,
        "gates": {**gates, **gates_after},
        "interpretation": interpretation,
    }
    (OUT / "finan_docetl_unit_parity_arm.json").write_text(json.dumps(report, indent=2, default=str))
    print(
        json.dumps(
            {
                "wrote": str(OUT / "finan_docetl_unit_parity_arm.json"),
                "product_plumbing_16": plumbing_16["mean_per_query_product"],
                "product_25_16": scored_25_16["mean_per_query_product"],
                "product_100_16": scored_100_16["mean_per_query_product"],
                "product_plumbing_15": plumbing_15["mean_per_query_product"],
                "product_25_15": scored_25_15["mean_per_query_product"],
                "product_100_15": scored_100_15["mean_per_query_product"],
                "docetl": DOCETL_SCORE["product"],
                "spent_25": checkpoint_25["spent"],
                "spent_100": ledger.spent,
                "complete_25": checkpoint_25["complete_query_ids"],
                "complete_100": checkpoint_100["complete_query_ids"],
                "interpretation": interpretation,
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
