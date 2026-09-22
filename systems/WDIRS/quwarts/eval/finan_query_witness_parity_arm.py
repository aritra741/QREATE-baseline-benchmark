"""Query-set-parity Finan query-witness arm: DocETL's 16 eval queries only."""

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

from quwarts.core.ledger import BudgetedCaller, SpendRecord, TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.provenance import document_stem
from quwarts.core.query_filter import encode_witness_key
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import grain_sql, query_shape
from quwarts.core.query_witness_acq.config import (
    MODEL,
    POLICY,
    THETA_25,
    THETA_100,
    WITNESS_SYSTEM,
    policy_hash,
    prompt_hash,
    verify_budgets,
)
from quwarts.core.query_witness_acq.controller import (
    WitnessController,
    bags,
    empty_bags,
    incumbents_for,
    load_finance_rows,
    snapshot_base,
    _fetch,
    _hash,
    _norm_bag,
    _rid,
)
from quwarts.core.query_witness_acq.decide import build_prompt, decide_witness
from quwarts.core.query_witness_acq.programs import compile_programs
from quwarts.core.query_witness_acq.sidecar import (
    delete_addition,
    ensure_tables,
    fetch_rows,
    insert_addition,
    register_programs,
    row_visible_sql,
    _rid_from_row,
)
from quwarts.core.retrieve_extract.cache import VerifiedCache
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.schema_columns import assert_queries_execute
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import documents_for, gold_name, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

PLUMBING_DB = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
COST_DISTS = ROOT / "results" / "quwarts_finan_query_witness_cost_schedule" / "cost_distributions.json"
OUT = ROOT / "results" / "quwarts_finan_query_witness_parity"
DOCETL_SCORE = {"f2": 0.537, "f1": 0.114, "product": 0.084, "tokens": 1_381_827}


def load_docetl_manifest() -> list[dict[str, str]]:
    path = DOCETL_DIR / "query_manifest.json"
    if not path.is_file():
        shim = json.loads((DOCETL_DIR / "docetl_shim.json").read_text())
        rows = next(iter(shim["per_config"].values()))["per_query"]
        return [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in rows]
    return [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads(path.read_text())]


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


def shape_of(program) -> str:
    return "|".join(
        [
            "g" if program.group_sql else "-",
            "a" if "aggregate_value" in program.requested_fields else "-",
            "c" if "counted_value_present" in program.requested_fields else "-",
            "d" if "distinct" in program.kinds else "-",
        ]
    )


def expected_cost(program, packed: dict[str, Any], dists: dict[str, Any]) -> int:
    prompt = build_prompt(program, "0", packed["context"], packed["source_ids"])
    input_tokens = count_tokens(WITNESS_SYSTEM) + count_tokens(prompt)
    spec = dists.get(shape_of(program)) or dists.get("*") or {
        "completion_mean": 132,
        "retry_p": 0.0708,
        "retry_mean": 1578,
    }
    return int(round(input_tokens + float(spec["completion_mean"]) + float(spec["retry_p"]) * float(spec["retry_mean"])))


def build_completion_schedule(tasks: list[dict[str, Any]], theta: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_cond: dict[str, dict[str, Any]] = {}
    for task in tasks:
        program = task["program"]
        item = by_cond.setdefault(
            program.condition_id,
            {
                "condition_id": program.condition_id,
                "tasks": [],
                "program_ids": set(),
                "query_ids": set(),
                "frequency": 0.0,
            },
        )
        item["tasks"].append(task)
        item["program_ids"].add(program.program_id)
        item["query_ids"].update(program.query_ids)
    for item in by_cond.values():
        freqs = {task["program"].program_id: float(task["program"].frequency) for task in item["tasks"]}
        item["frequency"] = sum(freqs.values())
        item["universe"] = len(item["tasks"])
        item["complete_cost"] = sum(int(task["cost_expected"]) for task in item["tasks"])
        item["tasks"] = sorted(item["tasks"], key=lambda task: (int(task["rowid"]), task["task_key"]))
        item["program_ids"] = sorted(item["program_ids"])
        item["query_ids"] = sorted(item["query_ids"])
    selected: list[dict[str, Any]] = []
    clusters: list[dict[str, Any]] = []
    spent = 0
    leftover = set(by_cond)
    while leftover:
        options = []
        for cid in leftover:
            item = by_cond[cid]
            cost = item["complete_cost"]
            if spent + cost > theta:
                continue
            n_prog = len(item["program_ids"])
            n_q = len(item["query_ids"])
            score = (n_q * n_prog * max(item["frequency"], 1.0)) / max(1, cost)
            options.append((-score, -n_q, -n_prog, -item["frequency"], item["universe"], cid, cost))
        if not options:
            break
        options.sort()
        _s, _nq, _np, _f, _u, cid, cost = options[0]
        item = by_cond[cid]
        clusters.append(
            {
                "condition_id": cid,
                "program_ids": item["program_ids"],
                "query_ids": item["query_ids"],
                "universe": item["universe"],
                "complete_cost": cost,
                "frequency": item["frequency"],
                "task_keys": [task["task_key"] for task in item["tasks"]],
            }
        )
        selected.extend(item["tasks"])
        spent += cost
        leftover.remove(cid)
    return selected, clusters


def grain_rids(db: Path, sql: str, predicates) -> set[int]:
    grain = official_sql(grain_sql(sql), db, predicates)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {rid for row in _fetch(conn, grain) if (rid := _rid(row)) is not None}
    finally:
        conn.close()


def apply_addition(dest: Path, program, task: dict[str, Any], validated: dict[str, Any], predicates, statements) -> dict[str, Any]:
    if not validated.get("accepted"):
        return {"accepted": False, "materialized": False, "row_visible": False, "bag_visible": False, "rolled_back": False}
    key = encode_witness_key([task["rowid"]])
    conn = sqlite3.connect(str(dest))
    ensure_tables(conn)
    bags_before = {
        qid: _norm_bag(_fetch(conn, official_sql(statements[qid], dest, predicates, query_id=qid)))
        for qid in program.query_ids
    }
    insert_addition(
        conn,
        {
            "program_id": program.program_id,
            "witness_key": key,
            "truth": True,
            "group_value": validated.get("group_value"),
            "aggregate_value": validated.get("aggregate_value"),
            "counted_value_present": validated.get("counted_value_present"),
            "entity_id": task["entity_id"],
            "query_ids": program.query_ids,
            "evidence": json.dumps(validated.get("grounded_evidence") or []),
        },
    )
    conn.commit()
    row_visible = False
    bag_visible = False
    for qid in program.query_ids:
        official = official_sql(statements[qid], dest, predicates, query_id=qid)
        grain, grain_err = fetch_rows(conn, row_visible_sql(official))
        if grain_err is None and any(_rid_from_row(row) == task["rowid"] for row in grain):
            row_visible = True
        bag_after, bag_err = fetch_rows(conn, official)
        if bag_err is None and _norm_bag(bag_after) != bags_before.get(qid):
            bag_visible = True
    if not row_visible:
        delete_addition(conn, program.program_id, key)
        conn.commit()
        conn.close()
        return {"accepted": True, "materialized": False, "row_visible": False, "bag_visible": False, "rolled_back": True}
    conn.close()
    return {"accepted": True, "materialized": True, "row_visible": True, "bag_visible": bag_visible, "rolled_back": False}


def freeze_db(
    dest: Path,
    plumbing: Path,
    complete_programs,
    additions: list[dict[str, Any]],
    statements: dict[str, str],
    predicates,
    before: dict[str, Any],
) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(plumbing, dest)
    conn = sqlite3.connect(str(dest))
    ensure_tables(conn)
    register_programs(conn, complete_programs)
    conn.commit()
    conn.close()
    visible = {"row": 0, "bag": 0, "rollback": 0, "kept": 0}
    by_prog = {item.program_id: item for item in complete_programs}
    seen = set()
    outcomes = []
    for row in additions:
        program = row["program"]
        if program.program_id not in by_prog:
            continue
        key = (program.program_id, int(row["task"]["rowid"]))
        if key in seen:
            continue
        seen.add(key)
        outcome = apply_addition(dest, program, row["task"], row["validated"], predicates, statements)
        outcomes.append({**row["meta"], **outcome})
        if outcome["rolled_back"]:
            visible["rollback"] += 1
        if outcome["row_visible"]:
            visible["row"] += 1
        if outcome["bag_visible"]:
            visible["bag"] += 1
        if outcome["materialized"]:
            visible["kept"] += 1
    conn = sqlite3.connect(str(dest))
    assert_queries_execute(
        conn,
        {qid: official_sql(sql, dest, predicates, query_id=qid) for qid, sql in statements.items()},
        any_error=True,
    )
    conn.close()
    after = snapshot_base(dest)
    if after["n"] != before["n"] or after["identity_values"] != before["identity_values"]:
        raise SystemExit("plumbing identity/values were mutated")
    return {"visible": visible, "outcomes": outcomes, "after": after}


def sidecar_payload(dest: Path) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        additions = []
        programs = []
        if "query_witness_additions" in names:
            additions = [dict(row) for row in conn.execute("SELECT * FROM query_witness_additions ORDER BY program_id, witness_key")]
        if "query_witness_programs" in names:
            programs = [dict(row) for row in conn.execute("SELECT * FROM query_witness_programs ORDER BY query_id")]
        return {"additions": additions, "programs": programs}
    finally:
        conn.close()


def _ledger_fp(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()


def main() -> int:
    if DEFAULT_MODEL != MODEL:
        raise SystemExit(f"model lock failed: {DEFAULT_MODEL} != {MODEL}")
    budgets = verify_budgets()
    if THETA_25 != 345457 or THETA_100 != 1381827:
        raise SystemExit(f"budget lock failed: {THETA_25} {THETA_100}")
    OUT.mkdir(parents=True, exist_ok=True)
    cache_dir = OUT / "cache"
    resume_25 = (OUT / "theta25_frozen.json").is_file() and (OUT / "theta25_journal.json").is_file() and (OUT / "theta25_ledger.json").is_file()
    if cache_dir.exists() and not resume_25:
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    full = queries_for("Finan")
    train, _test = split_80_20(full, 42)
    train_ids = {row["query_id"] for row in train}
    manifest = load_docetl_manifest()
    if len(manifest) != 16:
        raise SystemExit(f"DocETL manifest has {len(manifest)} queries, expected 16")
    full_by_id = {row["query_id"]: row for row in full}
    missing = [row["query_id"] for row in manifest if row["query_id"] not in full_by_id]
    if missing:
        raise SystemExit(f"manifest IDs not in Finan workload: {missing}")
    train_hit = [row["query_id"] for row in manifest if row["query_id"] in train_ids]
    if train_hit:
        raise SystemExit(f"manifest includes train queries: {train_hit}")
    queries = [{"query_id": row["query_id"], "sql": full_by_id[row["query_id"]]["sql"], "pack": full_by_id[row["query_id"]].get("pack")} for row in manifest]
    query_list = [{"query_id": row["query_id"], "sql": row["sql"]} for row in queries]
    query_list_hash = _hash(query_list)
    (OUT / "query_list.json").write_text(json.dumps({"sha256": query_list_hash, "n": len(query_list), "queries": query_list}, indent=2))
    print(json.dumps({"query_list_frozen": True, "n": 16, "sha256": query_list_hash, "ids": [row["query_id"] for row in query_list]}, indent=2), flush=True)

    locked = {"policy": POLICY, "policy_sha256": policy_hash(), "prompt_sha256": prompt_hash(), "budgets": budgets, "query_list_sha256": query_list_hash}
    (OUT / "locked_policy.json").write_text(json.dumps(locked, indent=2))

    statements = {row["query_id"]: row["sql"] for row in queries}
    _, workload = analyze_workload(statements)
    programs = compile_programs(queries, workload)
    compiled_ids = {qid for program in programs for qid in program.query_ids}
    if compiled_ids != {row["query_id"] for row in queries}:
        raise SystemExit(f"compile leaked extra/missing queries: {compiled_ids ^ {row['query_id'] for row in queries}}")
    if compiled_ids & train_ids:
        raise SystemExit("compile included train queries")
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    work = OUT / "_work.db"
    if work.exists():
        work.unlink()
    shutil.copy2(PLUMBING_DB, work)
    before = snapshot_base(work)
    plumbing_rids = {qid: grain_rids(work, sql, predicates) for qid, sql in statements.items()}
    plumbing_bags = bags(work, statements, predicates)
    empty_before = empty_bags(work, statements, predicates)
    rows = load_finance_rows(work)
    documents = documents_for("Finan")
    entity_by_rowid = {int(row["__rowid"]): str(row["__entity_id"]) for row in rows}
    docs_by_stem = {document_stem(doc.doc_id) or doc.doc_id: doc for doc in documents}
    doc_by_entity = {}
    for row in rows:
        stem = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        doc = docs_by_stem.get(stem)
        if doc is not None:
            doc_by_entity[str(row["__entity_id"])] = doc

    dummy = BudgetedCaller(TokenLedger(10**12, int(POLICY["seed"])), lambda prompt, meta: ("{}", 0))
    controller = WitnessController(
        work=work,
        documents=documents,
        programs=programs,
        statements=statements,
        predicates=predicates,
        caller=dummy,
        cache=VerifiedCache(cache_dir),
        artifact_dir=OUT,
        entity_by_rowid=entity_by_rowid,
        doc_by_entity=doc_by_entity,
        finance_rows=rows,
    )
    print("index start", flush=True)
    controller.index()
    print("block start", flush=True)
    tasks, preflight = controller.build_tasks()
    dists = json.loads(COST_DISTS.read_text()) if COST_DISTS.is_file() else {"*": {"completion_mean": 132, "retry_p": 0.0708, "retry_mean": 1578}}
    for task in tasks:
        task["cost_expected"] = expected_cost(task["program"], task["packed"], dists)
    scheduled, clusters = build_completion_schedule(tasks, THETA_100)
    spent_exp = 0
    clusters_25 = []
    for cluster in clusters:
        if spent_exp + int(cluster["complete_cost"]) > THETA_25:
            break
        clusters_25.append(cluster)
        spent_exp += int(cluster["complete_cost"])
    n_25 = sum(len(cluster["task_keys"]) for cluster in clusters_25)
    schedule_payload = {
        "gold_used": False,
        "docetl_answers_used": False,
        "query_list_sha256": query_list_hash,
        "theta_25": THETA_25,
        "theta_100": THETA_100,
        "features": ["query_frequency", "full_expected_task_cost", "condition_reuse", "candidate_universe_size", "plumbing_coverage"],
        "unique_programs": preflight["unique_programs"],
        "unique_conditions": preflight["unique_conditions"],
        "blocked_after": preflight["candidates_after_blocking"],
        "deduplicated_tasks": preflight["deduplicated_tasks"],
        "scheduled_100": len(scheduled),
        "scheduled_25": n_25,
        "expected_spend_25": spent_exp,
        "expected_spend_100": sum(int(cluster["complete_cost"]) for cluster in clusters),
        "clusters_25": clusters_25,
        "clusters_100": clusters,
        "prefix": clusters_25 == clusters[: len(clusters_25)],
        "task_keys_25": [task["task_key"] for task in scheduled[:n_25]],
        "task_keys_100": [task["task_key"] for task in scheduled],
    }
    schedule_payload["sha256"] = _hash({k: schedule_payload[k] for k in schedule_payload if k != "sha256"})
    (OUT / "preflight.json").write_text(json.dumps(preflight, indent=2, default=str))
    (OUT / "block_log.json").write_text(json.dumps(controller.block_log, indent=2, default=str))
    (OUT / "completion_schedule.json").write_text(json.dumps(schedule_payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "schedule_frozen": True,
                "sha256": schedule_payload["sha256"],
                "programs": preflight["unique_programs"],
                "conditions": preflight["unique_conditions"],
                "blocked": preflight["candidates_after_blocking"],
                "deduped": preflight["deduplicated_tasks"],
                "scheduled_25": n_25,
                "scheduled_100": len(scheduled),
                "clusters_25": len(clusters_25),
                "clusters_100": len(clusters),
                "expected_spend_25": schedule_payload["expected_spend_25"],
                "expected_spend_100": schedule_payload["expected_spend_100"],
            },
            indent=2,
        ),
        flush=True,
    )

    ledger = TokenLedger(theta=THETA_100, seed=int(POLICY["seed"]))
    if resume_25:
        snap25 = json.loads((OUT / "theta25_ledger.json").read_text())
        ledger.spent = 0
        ledger.records.clear()
        for rec in snap25.get("records") or []:
            ledger.records.append(
                SpendRecord(purpose=rec["purpose"], tokens=int(rec["tokens"]), metadata=dict(rec.get("metadata") or {}))
            )
            ledger.spent += int(rec["tokens"])
        print(json.dumps({"resume_25": True, "restored_spent": ledger.spent}, indent=2), flush=True)
    caller = make_caller(
        ledger,
        model=MODEL,
        temperature=float(POLICY["temperature"]),
        max_tokens=int(POLICY["max_tokens"]),
    )
    cache = VerifiedCache(cache_dir)
    journal: list[dict[str, Any]] = json.loads((OUT / "theta25_journal.json").read_text()) if resume_25 else []
    additions: list[dict[str, Any]] = []
    decided: dict[str, dict[str, Any]] = {}
    counts = Counter()
    by_cond_programs = defaultdict(list)
    for program in programs:
        by_cond_programs[program.condition_id].append(program)
    blocked_by_program: dict[str, set[str]] = defaultdict(set)
    for task in tasks:
        blocked_by_program[task["program"].program_id].add(task["task_key"])
    resolved_keys: set[str] = set()
    completed_cids: list[str] = []
    frozen_25 = bool(resume_25)
    checkpoint_25 = json.loads((OUT / "theta25_frozen.json").read_text()) if resume_25 else None
    dest_25 = OUT / "databases" / "finan_query_witness_parity_25.db"
    dest_100 = OUT / "databases" / "finan_query_witness_parity_100.db"

    def complete_program_ids(done_keys: set[str]) -> list:
        done = []
        for program in programs:
            need = blocked_by_program[program.program_id]
            if need and need <= done_keys:
                done.append(program)
        return done

    def freeze(
        dest: Path,
        label: str,
        done_cids: list[str],
        journal_cut: list[dict[str, Any]],
        ledger_snap: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        done_keys = {key for cluster in clusters if cluster["condition_id"] in set(done_cids) for key in cluster["task_keys"]}
        complete = complete_program_ids(done_keys)
        kept_adds = [row for row in additions if row["program"].program_id in {item.program_id for item in complete} and row["task"]["task_key"] in done_keys]
        meta = freeze_db(dest, PLUMBING_DB, complete, kept_adds, statements, predicates, before)
        after_bags = bags(dest, statements, predicates)
        incomplete_qids = []
        for program in programs:
            if program in complete:
                continue
            incomplete_qids.extend(program.query_ids)
        fallback_ok = all(after_bags[qid] == plumbing_bags[qid] for qid in incomplete_qids)
        incumbents_ok = all(plumbing_rids[qid] <= grain_rids(dest, statements[qid], predicates) for qid in statements)
        sidecar = sidecar_payload(dest)
        snap = ledger_snap or ledger.snapshot()
        payload = {
            "label": label,
            "spent": snap["spent"],
            "theta_25": THETA_25,
            "theta_100": THETA_100,
            "db_path": str(dest),
            "db_sha256": file_sha256(dest),
            "ledger_sha256": _ledger_fp(snap),
            "journal_sha256": _hash(journal_cut),
            "sidecar_sha256": _hash(sidecar),
            "bag_sha256": hashlib.sha256(repr(sorted(after_bags.items())).encode()).hexdigest(),
            "policy_sha256": policy_hash(),
            "prompt_sha256": prompt_hash(),
            "query_list_sha256": query_list_hash,
            "schedule_sha256": schedule_payload["sha256"],
            "complete_program_ids": [item.program_id for item in complete],
            "complete_query_ids": sorted({qid for item in complete for qid in item.query_ids}),
            "complete_clusters": list(done_cids),
            "empty_bags": empty_bags(dest, statements, predicates),
            "n_journal": len(journal_cut),
            "visible": meta["visible"],
            "incomplete_plumbing_fallback": fallback_ok,
            "incumbents_retained": incumbents_ok,
            "counts": dict(counts),
        }
        (OUT / f"{label}_frozen.json").write_text(json.dumps(payload, indent=2, default=str))
        (OUT / f"{label}_ledger.json").write_text(json.dumps(snap, indent=2, default=str))
        (OUT / f"{label}_journal.json").write_text(json.dumps(journal_cut, indent=2, default=str))
        (OUT / f"{label}_sidecar.json").write_text(json.dumps(sidecar, indent=2, default=str))
        (OUT / f"{label}_program_states.json").write_text(
            json.dumps(
                {
                    "complete": payload["complete_program_ids"],
                    "complete_queries": payload["complete_query_ids"],
                    "incomplete_queries": sorted(set(statements) - set(payload["complete_query_ids"])),
                },
                indent=2,
            )
        )
        print(json.dumps({"frozen": label, "spent": payload["spent"], "db": payload["db_sha256"], "complete_programs": len(complete)}, indent=2), flush=True)
        if not fallback_ok:
            raise SystemExit(f"{label}: incomplete programs are not plumbing fallback")
        if not incumbents_ok:
            raise SystemExit(f"{label}: incumbent support disappeared")
        leaked = {qid for row in journal_cut for qid in row["query_ids"] if qid in train_ids}
        if leaked:
            raise SystemExit(f"{label}: train query work leaked {leaked}")
        cap = THETA_25 if label == "theta25" else THETA_100
        if payload["spent"] > cap:
            raise SystemExit(f"{label} spend {payload['spent']} exceeds {cap}")
        return payload

    by_key = {task["task_key"]: task for task in scheduled}
    cluster_of = {}
    for cluster in clusters:
        for key in cluster["task_keys"]:
            cluster_of[key] = cluster["condition_id"]

    last_good_25: dict[str, Any] | None = None
    completed_25: list[str] = []
    for cluster in clusters:
        cid = cluster["condition_id"]
        if not frozen_25 and ledger.spent + int(cluster["complete_cost"]) > THETA_25:
            if last_good_25:
                checkpoint_25 = freeze(
                    dest_25,
                    "theta25",
                    list(last_good_25["cids"]),
                    list(last_good_25["journal"]),
                    last_good_25["ledger"],
                )
            else:
                empty_snap = {"theta": THETA_100, "seed": int(POLICY["seed"]), "spent": 0, "records": []}
                checkpoint_25 = freeze(dest_25, "theta25", [], [], empty_snap)
            frozen_25 = True
        cluster_ok = True
        for key in cluster["task_keys"]:
            task = by_key[key]
            if ledger.spent + 64 > THETA_100:
                cluster_ok = False
                break
            packed = task["packed"]
            program = task["program"]
            result = decided.get(key)
            if result is None:
                result = decide_witness(
                    caller,
                    cache,
                    program,
                    witness_id=str(task["rowid"]),
                    context=packed["context"],
                    source_ids=packed["source_ids"],
                    context_hashes=packed["context_hashes"],
                    source_text=task["doc"].text,
                )
                if result is None:
                    cluster_ok = False
                    break
                decided[key] = result
                counts[result["condition"]] += 1
                counts["attempted"] += 1
                if result.get("retried"):
                    counts["retry"] += 1
                counts["tokens"] += int(result.get("tokens") or 0)
            resolved_keys.add(key)
            already = any(row["task_key"] == key for row in journal)
            for sibling in by_cond_programs[program.condition_id]:
                accepted = bool(result.get("accepted"))
                if accepted:
                    if not already:
                        counts["accepted"] += 1
                    additions.append(
                        {
                            "program": sibling,
                            "task": {**task, "program": sibling},
                            "validated": result,
                            "meta": {
                                "program_id": sibling.program_id,
                                "rowid": task["rowid"],
                                "entity_id": task["entity_id"],
                                "task_key": key,
                            },
                        }
                    )
                if already:
                    continue
                journal.append(
                    {
                        "task_index": len(resolved_keys) - 1,
                        "task_key": key,
                        "program_id": sibling.program_id,
                        "condition_id": sibling.condition_id,
                        "query_ids": sibling.query_ids,
                        "rowid": task["rowid"],
                        "entity_id": task["entity_id"],
                        "condition": result.get("condition"),
                        "group_value": result.get("group_value"),
                        "accepted": accepted,
                        "from_cache": result.get("from_cache"),
                        "tokens": result.get("tokens") or 0,
                        "spent_after": ledger.spent,
                    }
                )
            if len(resolved_keys) == 1 or len(resolved_keys) % 25 == 0:
                print(
                    f"witness {len(resolved_keys)}/{len(scheduled)} spent={ledger.spent} accepted={counts['accepted']}",
                    flush=True,
                )
        if cluster_ok and set(cluster["task_keys"]) <= resolved_keys:
            completed_cids.append(cid)
            if not frozen_25 and ledger.spent <= THETA_25:
                completed_25.append(cid)
                last_good_25 = {
                    "cids": list(completed_25),
                    "journal": list(journal),
                    "ledger": ledger.snapshot(),
                }
            elif not frozen_25 and ledger.spent > THETA_25:
                if last_good_25:
                    checkpoint_25 = freeze(
                        dest_25,
                        "theta25",
                        list(last_good_25["cids"]),
                        list(last_good_25["journal"]),
                        last_good_25["ledger"],
                    )
                else:
                    empty_snap = {"theta": THETA_100, "seed": int(POLICY["seed"]), "spent": 0, "records": []}
                    checkpoint_25 = freeze(dest_25, "theta25", [], [], empty_snap)
                frozen_25 = True
        else:
            break
    if not frozen_25:
        if last_good_25:
            checkpoint_25 = freeze(
                dest_25,
                "theta25",
                list(last_good_25["cids"]),
                list(last_good_25["journal"]),
                last_good_25["ledger"],
            )
        else:
            checkpoint_25 = freeze(dest_25, "theta25", list(completed_cids), list(journal))
        frozen_25 = True
    checkpoint_100 = freeze(dest_100, "theta100", list(completed_cids), list(journal))
    j25 = json.loads((OUT / "theta25_journal.json").read_text())
    if j25 != journal[: len(j25)]:
        raise SystemExit("25% journal is not a prefix of 100% journal")
    if schedule_payload["task_keys_25"] != schedule_payload["task_keys_100"][: len(schedule_payload["task_keys_25"])]:
        raise SystemExit("25% schedule is not a prefix of 100% schedule")
    if ledger.spent > THETA_100:
        raise SystemExit(f"exceeded theta_100 {THETA_100} with {ledger.spent}")
    gates = {
        "exact_16_query_manifest": len(queries) == 16 and query_list_hash == json.loads((OUT / "query_list.json").read_text())["sha256"],
        "zero_train_work": not ({qid for row in journal for qid in row["query_ids"]} & train_ids),
        "all_16_execute": True,
        "plumbing_rows_preserved": snapshot_base(dest_100)["n"] == 100,
        "base_columns_unchanged": snapshot_base(dest_100)["identity_values"] == before["identity_values"],
        "incumbents_retained": checkpoint_100["incumbents_retained"],
        "incomplete_plumbing_fallback": checkpoint_100["incomplete_plumbing_fallback"] and checkpoint_25["incomplete_plumbing_fallback"],
        "theta25_within": checkpoint_25["spent"] <= THETA_25,
        "theta100_within": ledger.spent <= THETA_100,
        "prefix_journal": True,
        "zero_gold_before_freeze": True,
    }
    if not all(gates.values()):
        raise SystemExit(f"gate failure: {gates}")
    frozen = {
        "budgets": budgets,
        "query_list_sha256": query_list_hash,
        "schedule_sha256": schedule_payload["sha256"],
        "policy_sha256": policy_hash(),
        "prompt_sha256": prompt_hash(),
        "plumbing_sha256": file_sha256(PLUMBING_DB),
        "preflight": preflight,
        "theta25": checkpoint_25,
        "theta100": checkpoint_100,
        "counts": dict(counts),
        "gates": gates,
    }
    (OUT / "frozen.json").write_text(json.dumps(frozen, indent=2, default=str))
    print(json.dumps({"both_frozen": True, "spent": ledger.spent, "gates": gates}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.eval.finan_query_witness_semantic import classify_accepted, plumbing_maps, reconstruct_gold

    gold = load_ground_truth(gold_name("Finan"))
    count_rows = [row for row in queries if is_count_query(query_shape(row["query_id"], row["sql"]))]
    rewrites_plumb_16 = {row["query_id"]: official_sql(row["sql"], PLUMBING_DB, predicates, query_id=row["query_id"]) for row in queries}
    rewrites_plumb_15 = {row["query_id"]: official_sql(row["sql"], PLUMBING_DB, predicates, query_id=row["query_id"]) for row in count_rows}
    rewrites_25_16 = {row["query_id"]: official_sql(row["sql"], dest_25, predicates, query_id=row["query_id"]) for row in queries}
    rewrites_25_15 = {row["query_id"]: official_sql(row["sql"], dest_25, predicates, query_id=row["query_id"]) for row in count_rows}
    rewrites_100_16 = {row["query_id"]: official_sql(row["sql"], dest_100, predicates, query_id=row["query_id"]) for row in queries}
    rewrites_100_15 = {row["query_id"]: official_sql(row["sql"], dest_100, predicates, query_id=row["query_id"]) for row in count_rows}
    plumbing_16 = _score(PLUMBING_DB, queries, rewrites_plumb_16, gold)
    plumbing_15 = _score(PLUMBING_DB, count_rows, rewrites_plumb_15, gold)
    scored_25_16 = _score(dest_25, queries, rewrites_25_16, gold)
    scored_25_15 = _score(dest_25, count_rows, rewrites_25_15, gold)
    scored_100_16 = _score(dest_100, queries, rewrites_100_16, gold)
    scored_100_15 = _score(dest_100, count_rows, rewrites_100_15, gold)
    gold_sets = reconstruct_gold(statements, gold)
    rid_to_gold, _, _ = plumbing_maps()
    accepted_rows = [row for row in journal if row.get("accepted")]
    labeled = classify_accepted(accepted_rows, programs, gold_sets, rid_to_gold)
    labels = Counter(row["label"] for row in labeled)
    support_ok = [row for row in labeled if row["label"] not in {"false-positive support", "untraceable"}]
    correct = [row for row in labeled if row["label"] == "correct gold support witness"]
    report = {
        "model": MODEL,
        "query_list_sha256": query_list_hash,
        "schedule_sha256": schedule_payload["sha256"],
        "policy_sha256": policy_hash(),
        "prompt_sha256": prompt_hash(),
        "budgets": budgets,
        "preflight": {k: preflight[k] for k in preflight if k != "program_priorities"},
        "schedule": {
            "n_25": n_25,
            "n_100": len(scheduled),
            "clusters_25": len(clusters_25),
            "clusters_100": len(clusters),
            "complete_programs_25": len(checkpoint_25["complete_program_ids"]),
            "complete_programs_100": len(checkpoint_100["complete_program_ids"]),
            "complete_queries_25": checkpoint_25["complete_query_ids"],
            "complete_queries_100": checkpoint_100["complete_query_ids"],
        },
        "counts": dict(counts),
        "decisions": {
            "true": counts.get("true", 0),
            "false": counts.get("false", 0),
            "unknown": counts.get("unknown", 0),
            "attempted": counts.get("attempted", 0),
            "resolved": len(resolved_keys),
            "accepted": counts.get("accepted", 0),
        },
        "visibility": {"theta25": checkpoint_25["visible"], "theta100": checkpoint_100["visible"]},
        "empty_bags": {
            "before": empty_before,
            "theta25": checkpoint_25["empty_bags"],
            "theta100": checkpoint_100["empty_bags"],
            "filled_25": sorted(set(empty_before) - set(checkpoint_25["empty_bags"])),
            "filled_100": sorted(set(empty_before) - set(checkpoint_100["empty_bags"])),
        },
        "accuracy_after_freeze": {
            "accepted": len(labeled),
            "labels": dict(labels),
            "support_condition_accuracy": (len(support_ok) / len(labeled)) if labeled else None,
            "direct_group_label_accuracy": (len(correct) / len(labeled)) if labeled else None,
            "group_accuracy_among_support": (len(correct) / len(support_ok)) if support_ok else None,
        },
        "score": {
            "plumbing_16": {"tokens": 0, **{k: plumbing_16[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}},
            "plumbing_15": {"tokens": 0, **{k: plumbing_15[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}},
            "parity_25_16": {"tokens": checkpoint_25["spent"], **{k: scored_25_16[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}},
            "parity_25_15": {"tokens": checkpoint_25["spent"], **{k: scored_25_15[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}},
            "parity_100_16": {"tokens": ledger.spent, **{k: scored_100_16[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}},
            "parity_100_15": {"tokens": ledger.spent, **{k: scored_100_15[k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}},
            "docetl_16": DOCETL_SCORE,
        },
        "per_query_25_16": scored_25_16["per_query"],
        "per_query_100_16": scored_100_16["per_query"],
        "per_query_25_15": scored_25_15["per_query"],
        "per_query_100_15": scored_100_15["per_query"],
        "hashes": {
            "query_list": query_list_hash,
            "schedule": schedule_payload["sha256"],
            "policy": policy_hash(),
            "prompt": prompt_hash(),
            "theta25_db": checkpoint_25["db_sha256"],
            "theta100_db": checkpoint_100["db_sha256"],
            "theta25_journal": checkpoint_25["journal_sha256"],
            "theta100_journal": checkpoint_100["journal_sha256"],
            "theta25_ledger": checkpoint_25["ledger_sha256"],
            "theta100_ledger": checkpoint_100["ledger_sha256"],
            "theta25_sidecar": checkpoint_25["sidecar_sha256"],
            "theta100_sidecar": checkpoint_100["sidecar_sha256"],
            "theta25_bags": checkpoint_25["bag_sha256"],
            "theta100_bags": checkpoint_100["bag_sha256"],
        },
        "gates": gates,
        "decision": {
            "closes_gap_at_25": scored_25_16["mean_per_query_product"] > DOCETL_SCORE["product"],
            "closes_gap_at_100": scored_100_16["mean_per_query_product"] > DOCETL_SCORE["product"],
        },
    }
    (OUT / "finan_query_witness_parity_arm.json").write_text(json.dumps(report, indent=2, default=str))
    print(
        json.dumps(
            {
                "wrote": str(OUT / "finan_query_witness_parity_arm.json"),
                "product_25_16": scored_25_16["mean_per_query_product"],
                "product_100_16": scored_100_16["mean_per_query_product"],
                "product_25_15": scored_25_15["mean_per_query_product"],
                "product_100_15": scored_100_15["mean_per_query_product"],
                "docetl": DOCETL_SCORE["product"],
                "spent_25": checkpoint_25["spent"],
                "spent_100": ledger.spent,
                "closes_25": report["decision"]["closes_gap_at_25"],
                "closes_100": report["decision"]["closes_gap_at_100"],
            },
            indent=2,
        ),
        flush=True,
    )
    work.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
