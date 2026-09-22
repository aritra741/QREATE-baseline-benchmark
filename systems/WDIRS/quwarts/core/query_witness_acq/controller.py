"""Single locked run to 100% with an exact 25% prefix checkpoint."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from quwarts.core.ledger import BudgetedCaller, TokenLedger
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.provenance import document_stem, source_document_hash
from quwarts.core.query_filter import encode_witness_key
from quwarts.core.query_support import grain_sql
from quwarts.core.query_witness_acq.block import block_witness, pack_context
from quwarts.core.query_witness_acq.config import POLICY, THETA_25, THETA_100, verify_budgets
from quwarts.core.query_witness_acq.decide import context_hash, decide_witness, task_key
from quwarts.core.query_witness_acq.programs import WitnessProgram
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
from quwarts.core.retrieve_extract.config import FROZEN
from quwarts.core.retrieve_extract.index import index_document
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.schema_columns import assert_queries_execute


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _fetch(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    try:
        cur = conn.execute(sql)
    except sqlite3.Error:
        return []
    cols = [item[0] for item in cur.description] if cur.description else []
    return [dict(zip(cols, rec)) for rec in cur.fetchall()]


def _norm_bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(key), json.dumps(row.get(key), default=str)) for key in row)))
    return tuple(sorted(frozen))


def _rid(row: dict[str, Any]) -> int | None:
    for key, value in row.items():
        if str(key).endswith("__rid") and value not in (None, ""):
            return int(value)
    if row.get("rowid") not in (None, ""):
        return int(row["rowid"])
    return None


def incumbents_for(db: Path, sql: str, predicates) -> set[int]:
    grain = official_sql(grain_sql(sql), db, predicates)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {rid for row in _fetch(conn, grain) if (rid := _rid(row)) is not None}
    finally:
        conn.close()


def load_finance_rows(db: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute("SELECT rowid AS __rowid, * FROM finance")]
    finally:
        conn.close()


def snapshot_base(db: Path) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(finance)")]
    keep = [col for col in cols if not str(col).startswith("sig_")]
    cur = conn.execute(
        f"SELECT {', '.join(_q(col) for col in keep)} FROM finance ORDER BY {_q('__entity_id')}"
    )
    rows = [tuple(rec) for rec in cur.fetchall()]
    n = int(conn.execute("SELECT COUNT(*) FROM finance").fetchone()[0])
    conn.close()
    return {"n": n, "identity_values": rows, "columns": keep}


def empty_bags(db: Path, statements: dict[str, str], predicates) -> list[str]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    empty = []
    try:
        for qid, sql in statements.items():
            try:
                rows = _fetch(conn, official_sql(sql, db, predicates, query_id=qid))
            except sqlite3.Error:
                empty.append(qid)
                continue
            if not rows:
                empty.append(qid)
    finally:
        conn.close()
    return empty


def bags(db: Path, statements: dict[str, str], predicates) -> dict[str, tuple]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = {}
    try:
        for qid, sql in statements.items():
            out[qid] = _norm_bag(_fetch(conn, official_sql(sql, db, predicates, query_id=qid)))
    finally:
        conn.close()
    return out


class WitnessController:
    def __init__(
        self,
        *,
        work: Path,
        documents,
        programs: list[WitnessProgram],
        statements: dict[str, str],
        predicates,
        caller: BudgetedCaller,
        cache: VerifiedCache,
        artifact_dir: Path,
        entity_by_rowid: dict[int, str],
        doc_by_entity: dict[str, Any],
        finance_rows: list[dict[str, Any]],
    ):
        self.work = Path(work)
        self.documents = documents
        self.programs = programs
        self.statements = statements
        self.predicates = predicates
        self.caller = caller
        self.cache = cache
        self.artifact_dir = Path(artifact_dir)
        self.entity_by_rowid = entity_by_rowid
        self.doc_by_entity = doc_by_entity
        self.finance_rows = {int(row["__rowid"]): row for row in finance_rows}
        self.indexes = {}
        self.journal: list[dict[str, Any]] = []
        self.block_log: list[dict[str, Any]] = []
        self.route_log: list[dict[str, Any]] = []
        self.decided: dict[str, dict[str, Any]] = {}
        self.counts = Counter()
        self.frozen_25 = False
        self.checkpoint_25: dict[str, Any] | None = None

    def index(self) -> None:
        with ThreadPoolExecutor(max_workers=min(6, len(self.documents))) as pool:
            futs = {pool.submit(index_document, doc.doc_id, doc.text): doc for doc in self.documents}
            for fut in as_completed(futs):
                index = fut.result()
                self.indexes[index.doc_id] = index

    def build_tasks(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        before_block = 0
        after_block = 0
        by_program = []
        descriptions = {"condition": "complete row-level WHERE condition"}
        for program in self.programs:
            incumbents: set[int] = set()
            for qid in program.query_ids:
                incumbents |= incumbents_for(self.work, self.statements[qid], self.predicates)
            blocked = []
            for rid, row in self.finance_rows.items():
                eid = self.entity_by_rowid.get(rid)
                doc = self.doc_by_entity.get(eid)
                if doc is None:
                    continue
                index = self.indexes[doc.doc_id]
                before_block += 1
                decision = block_witness(
                    program,
                    index,
                    incumbent=rid in incumbents,
                    plumbing_values=row,
                )
                self.block_log.append(
                    {
                        "program_id": program.program_id,
                        "condition_id": program.condition_id,
                        "rowid": rid,
                        "entity_id": eid,
                        "include": decision["include"],
                        "reason": decision["reason"],
                        "score": decision["score"],
                    }
                )
                if not decision["include"]:
                    continue
                after_block += 1
                packed = pack_context(index, decision["hits"], descriptions)
                ctx_h = context_hash(packed["context_hashes"] or [packed["context"][:80]])
                blocked.append(
                    {
                        "program": program,
                        "rowid": rid,
                        "entity_id": eid,
                        "doc": doc,
                        "index": index,
                        "packed": packed,
                        "task_key": task_key(program.condition_id, str(rid), ctx_h),
                        "incumbent": False,
                    }
                )
            excluded_mass = len(blocked)
            cost = max(1.0, float(POLICY["reserved_completion_tokens"]) + float(POLICY["retrieve_context_cap"]))
            priority = (program.frequency * program.amplification * excluded_mass) / cost
            by_program.append((priority, program, blocked, incumbents))
        by_program.sort(key=lambda item: (-item[0], item[1].program_id))
        tasks = []
        seen = set()
        depth = max((len(item[2]) for item in by_program), default=0)
        for index in range(depth):
            for _pri, program, blocked, _inc in by_program:
                if index >= len(blocked):
                    continue
                task = blocked[index]
                if task["task_key"] in seen:
                    continue
                seen.add(task["task_key"])
                task["priority"] = _pri
                tasks.append(task)
        est = int(POLICY["retrieve_context_cap"]) + int(POLICY["reserved_completion_tokens"]) + 400
        preflight = {
            "unique_programs": len(self.programs),
            "unique_conditions": len({item.condition_id for item in self.programs}),
            "reuse_ratio": 1 - (len({item.condition_id for item in self.programs}) / max(1, sum(len(p.query_ids) for p in self.programs))),
            "candidates_before_blocking": before_block,
            "candidates_after_blocking": after_block,
            "deduplicated_tasks": len(tasks),
            "expected_tokens_per_task": est,
            "coverage_at_theta_25": min(len(tasks), THETA_25 // est),
            "coverage_at_theta_100": min(len(tasks), THETA_100 // est),
            "program_priorities": [
                {
                    "program_id": program.program_id,
                    "query_ids": program.query_ids,
                    "priority": pri,
                    "blocked": len(blocked),
                    "incumbents": len(inc),
                }
                for pri, program, blocked, inc in by_program
            ],
        }
        return tasks, preflight

    def _programs_for_condition(self, condition_id: str) -> list[WitnessProgram]:
        return [item for item in self.programs if item.condition_id == condition_id]

    def _materialize(self, program: WitnessProgram, task: dict[str, Any], validated: dict[str, Any]) -> dict[str, Any]:
        if not validated.get("accepted"):
            return {"proposed": True, "accepted": False, "materialized": False, "sql_visible": False}
        key = encode_witness_key([task["rowid"]])
        conn = sqlite3.connect(str(self.work))
        ensure_tables(conn)
        bags_before = {
            qid: _norm_bag(_fetch(conn, official_sql(self.statements[qid], self.work, self.predicates, query_id=qid)))
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
            official = official_sql(self.statements[qid], self.work, self.predicates, query_id=qid)
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
            self.counts["rollback"] += 1
            return {
                "proposed": True,
                "accepted": True,
                "materialized": False,
                "sql_visible": False,
                "row_visible": False,
                "bag_visible": False,
                "rolled_back": True,
            }
        conn.close()
        if bag_visible:
            self.counts["bag_visible"] += 1
        return {
            "proposed": True,
            "accepted": True,
            "materialized": True,
            "sql_visible": True,
            "row_visible": True,
            "bag_visible": bag_visible,
        }

    def _freeze(self, dest: Path, label: str, statements: dict[str, str]) -> dict[str, Any]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.unlink()
        import shutil

        shutil.copy2(self.work, dest)
        conn = sqlite3.connect(str(dest))
        assert_queries_execute(
            conn,
            {qid: official_sql(sql, dest, self.predicates) for qid, sql in statements.items()},
            any_error=True,
        )
        conn.close()
        bag = bags(dest, statements, self.predicates)
        payload = {
            "label": label,
            "spent": self.caller.ledger.spent,
            "theta_25": THETA_25,
            "theta_100": THETA_100,
            "db_path": str(dest),
            "db_sha256": file_sha256(dest),
            "ledger_sha256": self.caller.ledger.fingerprint(),
            "journal_sha256": _hash(self.journal),
            "bag_sha256": hashlib.sha256(repr(sorted(bag.items())).encode()).hexdigest(),
            "policy_sha256": _hash(POLICY),
            "empty_bags": empty_bags(dest, statements, self.predicates),
            "n_journal": len(self.journal),
            "counts": dict(self.counts),
        }
        (self.artifact_dir / f"{label}_frozen.json").write_text(json.dumps(payload, indent=2, default=str))
        (self.artifact_dir / f"{label}_ledger.json").write_text(json.dumps(self.caller.ledger.snapshot(), indent=2, default=str))
        (self.artifact_dir / f"{label}_journal.json").write_text(json.dumps(self.journal, indent=2, default=str))
        print(json.dumps({"frozen": label, **{k: payload[k] for k in ("spent", "db_sha256")}}, indent=2), flush=True)
        return payload

    def run(self, dest_25: Path, dest_100: Path, statements: dict[str, str]) -> dict[str, Any]:
        conn = sqlite3.connect(str(self.work))
        ensure_tables(conn)
        register_programs(conn, self.programs)
        conn.commit()
        conn.close()
        print("index start", flush=True)
        self.index()
        tasks, preflight = self.build_tasks()
        (self.artifact_dir / "preflight.json").write_text(json.dumps(preflight, indent=2, default=str))
        (self.artifact_dir / "block_log.json").write_text(json.dumps(self.block_log, indent=2, default=str))
        print(json.dumps({"preflight": {k: preflight[k] for k in preflight if k != "program_priorities"}}, indent=2), flush=True)
        est = int(preflight["expected_tokens_per_task"])
        for index, task in enumerate(tasks):
            remaining_25 = THETA_25 - self.caller.ledger.spent
            if not self.frozen_25 and (remaining_25 < 64 or self.caller.ledger.spent + est > THETA_25):
                self.checkpoint_25 = self._freeze(dest_25, "theta25", statements)
                self.frozen_25 = True
            if self.caller.ledger.spent + 64 > THETA_100:
                break
            packed = task["packed"]
            self.route_log.append(
                {
                    "task_key": task["task_key"],
                    "mode": packed["mode"],
                    "reason": packed["reason"],
                    "measurements": packed["measurements"],
                    "estimated_cost": packed["estimated_cost"],
                    "router_tokens": 0,
                }
            )
            reused = self.decided.get(task["task_key"])
            program = task["program"]
            if reused is None:
                result = decide_witness(
                    self.caller,
                    self.cache,
                    program,
                    witness_id=str(task["rowid"]),
                    context=packed["context"],
                    source_ids=packed["source_ids"],
                    context_hashes=packed["context_hashes"],
                    source_text=task["doc"].text,
                )
                if result is None:
                    break
                self.decided[task["task_key"]] = result
                self.counts[result["condition"]] += 1
                self.counts["attempted"] += 1
                if result.get("retried"):
                    self.counts["retry"] += 1
                self.counts[f"tokens:{result.get('tokens') and 'witness'}"] += int(result.get("tokens") or 0)
            else:
                result = reused
                self.counts["reused"] += 1
            for sibling in self._programs_for_condition(program.condition_id):
                outcome = self._materialize(sibling, task, result)
                if outcome["accepted"]:
                    self.counts["accepted"] += 1
                if outcome.get("materialized"):
                    self.counts["materialized"] += 1
                if outcome.get("sql_visible"):
                    self.counts["sql_visible"] += 1
                self.journal.append(
                    {
                        "task_index": index,
                        "task_key": task["task_key"],
                        "program_id": sibling.program_id,
                        "condition_id": sibling.condition_id,
                        "query_ids": sibling.query_ids,
                        "rowid": task["rowid"],
                        "entity_id": task["entity_id"],
                        "condition": result.get("condition"),
                        "group_value": result.get("group_value"),
                        "accepted": outcome["accepted"],
                        "materialized": outcome.get("materialized"),
                        "sql_visible": outcome.get("sql_visible"),
                        "rolled_back": outcome.get("rolled_back"),
                        "from_cache": result.get("from_cache"),
                        "tokens": result.get("tokens") or 0,
                        "spent_after": self.caller.ledger.spent,
                    }
                )
            if index == 0 or (index + 1) % 25 == 0 or index + 1 == len(tasks):
                print(
                    f"witness {index + 1}/{len(tasks)} spent={self.caller.ledger.spent} accepted={self.counts['accepted']}",
                    flush=True,
                )
        if not self.frozen_25:
            self.checkpoint_25 = self._freeze(dest_25, "theta25", statements)
            self.frozen_25 = True
        checkpoint_100 = self._freeze(dest_100, "theta100", statements)
        (self.artifact_dir / "route_log.json").write_text(json.dumps(self.route_log, indent=2, default=str))
        return {"preflight": preflight, "theta25": self.checkpoint_25, "theta100": checkpoint_100, "counts": dict(self.counts)}
