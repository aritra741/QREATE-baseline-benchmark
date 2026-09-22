"""Zero-token semantic-accuracy and completion-schedule diagnostic.

Phase 1 writes and hashes schedules with no gold. Phase 2 loads gold.
No Qwen calls. Frozen journals, ledgers, and checkpoint DBs are read-only.
"""

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

from quwarts.core.pipeline import official_sql
from quwarts.core.query_filter import encode_witness_key
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import grain_sql, query_shape
from quwarts.core.query_witness import compile_witness_spec
from quwarts.core.query_witness_acq.config import POLICY, THETA_25, THETA_100, policy_hash
from quwarts.core.query_witness_acq.controller import empty_bags, snapshot_base
from quwarts.core.query_witness_acq.programs import compile_programs
from quwarts.core.query_witness_acq.sidecar import (
    ensure_tables,
    insert_addition,
    register_programs,
)
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import analyze_workload, parse_sql
from quwarts.experiments.player_case80 import execute, split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

FROZEN = ROOT / "results" / "quwarts_finan_query_witness"
PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
OUT = ROOT / "results" / "quwarts_finan_query_witness_semantic"
COMPLETION_COST = int(POLICY["reserved_completion_tokens"])
FROZEN_JOURNAL_100 = "9bca71491eba7781305060facfbd7c34ca2d69f73db46b4fe72664b832ad5491"
DOCETL = {"f2": 0.537, "f1": 0.114, "product": 0.084, "tokens": 1_381_827}


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _norm_bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(key), json.dumps(row.get(key), default=str)) for key in row)))
    return tuple(sorted(frozen))


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


def load_inventory() -> dict[str, Any]:
    journal = json.loads((FROZEN / "theta100_journal.json").read_text())
    if _hash(journal) != FROZEN_JOURNAL_100:
        raise SystemExit("frozen 100% journal hash mismatch")
    preflight = json.loads((FROZEN / "preflight.json").read_text())
    block_log = json.loads((FROZEN / "block_log.json").read_text())
    queries = queries_for("Finan")
    statements = {row["query_id"]: row["sql"] for row in queries}
    _, workload = analyze_workload(statements)
    programs = compile_programs(queries, workload)
    return {
        "journal": journal,
        "preflight": preflight,
        "block_log": block_log,
        "queries": queries,
        "statements": statements,
        "programs": programs,
    }


def build_program_stats(inv: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    programs = inv["programs"]
    block_log = inv["block_log"]
    journal = inv["journal"]
    blocked: dict[str, set[int]] = defaultdict(set)
    blocked_cond: dict[str, set[int]] = defaultdict(set)
    for row in block_log:
        if not row.get("include"):
            continue
        blocked[row["program_id"]].add(int(row["rowid"]))
        blocked_cond[row["condition_id"]].add(int(row["rowid"]))
    attempted: dict[str, set[int]] = defaultdict(set)
    accepted: dict[str, int] = Counter()
    spend: dict[str, int] = Counter()
    seen_task: set[str] = set()
    unique_attempted: set[tuple[str, int]] = set()
    for row in journal:
        pid = row["program_id"]
        rid = int(row["rowid"])
        attempted[pid].add(rid)
        unique_attempted.add((row["condition_id"], rid))
        if row.get("accepted"):
            accepted[pid] += 1
        key = row["task_key"]
        if key not in seen_task:
            seen_task.add(key)
            spend[pid] += int(row.get("tokens") or 0)
    rows = []
    for program in programs:
        n_block = len(blocked.get(program.program_id, set()))
        n_att = len(attempted.get(program.program_id, set()))
        rem = max(0, n_block - n_att)
        rows.append(
            {
                "program_id": program.program_id,
                "condition_id": program.condition_id,
                "query_ids": program.query_ids,
                "frequency": program.frequency,
                "blocked_candidates": n_block,
                "attempted_tasks": n_att,
                "coverage_fraction": (n_att / n_block) if n_block else 1.0,
                "accepted_trues": int(accepted.get(program.program_id, 0)),
                "actual_spend": int(spend.get(program.program_id, 0)),
                "remaining_completion_cost": rem * COMPLETION_COST,
                "completely_covered": n_att >= n_block and n_block > 0,
            }
        )
    meta = {
        "unique_blocked_condition_row": sum(len(v) for v in blocked_cond.values()),
        "unique_attempted_condition_row": len(unique_attempted),
        "model_tasks": len(seen_task),
        "deduplicated_inventory": int(inv["preflight"]["deduplicated_tasks"]),
        "blocked_after_blocking": int(inv["preflight"]["candidates_after_blocking"]),
        "completion_cost_unit": COMPLETION_COST,
    }
    return rows, meta


def _clusters(inv: dict[str, Any], stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_cond: dict[str, dict[str, Any]] = {}
    for row in stats:
        item = by_cond.setdefault(
            row["condition_id"],
            {
                "condition_id": row["condition_id"],
                "program_ids": [],
                "query_ids": [],
                "frequency": 0.0,
                "universe": 0,
                "tasks": [],
            },
        )
        item["program_ids"].append(row["program_id"])
        item["query_ids"].extend(row["query_ids"])
        item["frequency"] += float(row["frequency"])
        item["universe"] += int(row["blocked_candidates"])
    blocked_cond: dict[str, set[int]] = defaultdict(set)
    for row in inv["block_log"]:
        if row.get("include"):
            blocked_cond[row["condition_id"]].add(int(row["rowid"]))
    clusters = []
    for cid, item in by_cond.items():
        tasks = sorted(blocked_cond.get(cid, set()))
        item["tasks"] = tasks
        item["universe"] = len(tasks)
        clusters.append(item)
    return clusters


def completion_schedule(clusters: list[dict[str, Any]], theta: int) -> list[dict[str, Any]]:
    """Greedy: finish reuse clusters that fit; never shallow-round-robin."""

    remaining = {c["condition_id"]: list(c["tasks"]) for c in clusters}
    info = {c["condition_id"]: c for c in clusters}
    selected: list[dict[str, Any]] = []
    spent = 0
    covered: set[str] = set()

    def finishable() -> list[tuple]:
        found = []
        for cid, tasks in remaining.items():
            if cid in covered or not tasks:
                continue
            cost = len(tasks) * COMPLETION_COST
            if spent + cost > theta:
                continue
            cluster = info[cid]
            n_prog = len(cluster["program_ids"])
            score = (n_prog * max(cluster["frequency"], 1.0)) / cost
            found.append((-score, -n_prog, -cluster["frequency"], cluster["universe"], cid, cost, list(tasks)))
        found.sort()
        return found

    while True:
        options = finishable()
        if options:
            _score, _n, _f, _u, cid, cost, tasks = options[0]
            for rowid in tasks:
                selected.append({"condition_id": cid, "rowid": rowid, "cost": COMPLETION_COST})
            spent += cost
            covered.add(cid)
            remaining[cid] = []
            continue
        partials = []
        leftover = theta - spent
        take_n = leftover // COMPLETION_COST
        if take_n <= 0:
            break
        for cid, tasks in remaining.items():
            if cid in covered or not tasks:
                continue
            cluster = info[cid]
            n_prog = len(cluster["program_ids"])
            # prefer almost-complete large-frequency clusters
            frac = take_n / len(tasks)
            score = n_prog * max(cluster["frequency"], 1.0) * frac / (len(tasks) * COMPLETION_COST)
            partials.append((-score, cluster["universe"], cid, tasks[:take_n]))
        if not partials:
            break
        partials.sort()
        _s, _u, cid, tasks = partials[0]
        for rowid in tasks:
            selected.append({"condition_id": cid, "rowid": rowid, "cost": COMPLETION_COST})
        spent += len(tasks) * COMPLETION_COST
        remaining[cid] = remaining[cid][len(tasks) :]
        if not remaining[cid]:
            covered.add(cid)
        break
    return selected


def freeze_schedules(inv: dict[str, Any], stats: list[dict[str, Any]]) -> dict[str, Any]:
    clusters = _clusters(inv, stats)
    sched_100 = completion_schedule(clusters, THETA_100)
    sched_25 = [row for row in sched_100 if sum(item["cost"] for item in sched_100[: sched_100.index(row) + 1]) <= THETA_25]
    # exact prefix by cost
    spent = 0
    sched_25 = []
    for row in sched_100:
        if spent + row["cost"] > THETA_25:
            break
        sched_25.append(row)
        spent += row["cost"]
    payload = {
        "completion_cost_unit": COMPLETION_COST,
        "theta_25": THETA_25,
        "theta_100": THETA_100,
        "features": [
            "completion_cost",
            "shared_task_reuse",
            "candidate_universe_size",
            "query_frequency",
            "current_coverage",
        ],
        "gold_used": False,
        "clusters": [
            {
                "condition_id": c["condition_id"],
                "program_ids": c["program_ids"],
                "query_ids": c["query_ids"],
                "frequency": c["frequency"],
                "universe": c["universe"],
            }
            for c in clusters
        ],
        "schedule_25": sched_25,
        "schedule_100": sched_100,
        "n_25": len(sched_25),
        "n_100": len(sched_100),
        "cost_25": len(sched_25) * COMPLETION_COST,
        "cost_100": len(sched_100) * COMPLETION_COST,
        "prefix": sched_25 == sched_100[: len(sched_25)],
    }
    payload["sha256"] = _hash({k: payload[k] for k in payload if k != "sha256"})
    (OUT / "completion_schedules.json").write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({"schedules_frozen": True, "sha256": payload["sha256"], "n_25": payload["n_25"], "n_100": payload["n_100"]}, indent=2), flush=True)
    return payload


def plumbing_maps() -> tuple[dict[int, str], dict[str, int], dict[int, dict[str, Any]]]:
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute("SELECT rowid AS __rowid, * FROM finance")]
    conn.close()
    rid_to_gold: dict[int, str] = {}
    gold_to_rid: dict[str, int] = {}
    by_rid = {}
    for row in rows:
        rid = int(row["__rowid"])
        label = str(row.get("__provenance_label") or "").strip()
        stem = str(Path(str(row.get("doc_id") or "")).stem)
        gid = label or stem
        rid_to_gold[rid] = gid
        gold_to_rid[gid] = rid
        by_rid[rid] = row
    return rid_to_gold, gold_to_rid, by_rid


def reconstruct_gold(statements: dict[str, str], gold_tables: dict[str, list]) -> dict[str, Any]:
    from spp.config_grid import _build_in_memory_db

    gold_conn = _build_in_memory_db(gold_tables)
    valid = {}
    invalid = []
    for qid, sql in statements.items():
        spec = compile_witness_spec(qid, sql)
        try:
            official = execute(gold_conn, sql)
        except Exception as err:
            invalid.append({"query_id": qid, "reason": f"official_sql:{err}"})
            continue
        grain = grain_sql(sql)
        try:
            grain_rows = execute(gold_conn, grain)
        except Exception as err:
            invalid.append({"query_id": qid, "reason": f"grain:{err}"})
            continue
        ids = []
        for row in grain_rows:
            rid = None
            for key, value in row.items():
                if str(key).endswith("__rid") and value not in (None, ""):
                    rid = int(value)
                    break
            if rid is None:
                continue
            ident = gold_conn.execute("SELECT id FROM finance WHERE rowid = ?", [rid]).fetchone()
            if ident is None:
                continue
            ids.append(str(ident[0]))
        id_set = set(ids)
        finance_rows = gold_tables.get("finance") or []
        filtered = {
            "finance": [row for row in finance_rows if str(row.get("id") or "") in id_set]
        }
        tmp = _build_in_memory_db(filtered)
        try:
            reagg = execute(tmp, sql)
        except Exception as err:
            invalid.append({"query_id": qid, "reason": f"reagg:{err}", "n_support": len(ids)})
            tmp.close()
            continue
        tmp.close()
        if _norm_bag(official) != _norm_bag(reagg):
            invalid.append(
                {
                    "query_id": qid,
                    "reason": "reaggregate_mismatch",
                    "n_support": len(ids),
                    "official_n": len(official),
                    "reagg_n": len(reagg),
                }
            )
            continue
        groups = {}
        aggs = {}
        counted = {}
        distincts = {}
        for gid in ids:
            if spec.group_sql:
                expr = spec.group_sql[0]
                try:
                    val = gold_conn.execute(
                        f"SELECT ({expr}) FROM finance WHERE CAST(id AS TEXT) = ?",
                        [gid],
                    ).fetchone()
                    groups[gid] = None if val is None else val[0]
                except sqlite3.Error:
                    groups[gid] = None
            if spec.count_column:
                try:
                    val = gold_conn.execute(
                        f'SELECT "{spec.count_column}" FROM finance WHERE CAST(id AS TEXT) = ?',
                        [gid],
                    ).fetchone()
                    counted[gid] = val[0] if val else None
                except sqlite3.Error:
                    counted[gid] = None
            if spec.distinct_sql:
                try:
                    val = gold_conn.execute(
                        f"SELECT ({spec.distinct_sql}) FROM finance WHERE CAST(id AS TEXT) = ?",
                        [gid],
                    ).fetchone()
                    distincts[gid] = None if val is None else val[0]
                except sqlite3.Error:
                    distincts[gid] = None
        valid[qid] = {
            "ids": ids,
            "id_set": set(ids),
            "groups": groups,
            "counted": counted,
            "distincts": distincts,
            "kinds": spec.kinds,
            "group_sql": spec.group_sql,
            "count_column": spec.count_column,
            "distinct_sql": spec.distinct_sql,
            "bag_n": len(official),
        }
    gold_conn.close()
    return {"valid": valid, "invalid": invalid}


def classify_accepted(
    accepted: list[dict[str, Any]],
    programs,
    gold_sets: dict[str, Any],
    rid_to_gold: dict[int, str],
) -> list[dict[str, Any]]:
    prog = {p.program_id: p for p in programs}
    valid = gold_sets["valid"]
    out = []
    for row in accepted:
        program = prog.get(row["program_id"])
        gid = rid_to_gold.get(int(row["rowid"]))
        qids = [qid for qid in (program.query_ids if program else row["query_ids"]) if qid in valid]
        if gid in (None, "") or not qids:
            out.append({**row, "gold_id": gid, "label": "untraceable"})
            continue
        support = any(gid in valid[qid]["id_set"] for qid in qids)
        if not support:
            out.append({**row, "gold_id": gid, "label": "false-positive support"})
            continue
        gold_group = next((valid[qid]["groups"].get(gid) for qid in qids if valid[qid]["groups"]), None)
        need_group = any(valid[qid]["group_sql"] for qid in qids)
        pred_group = row.get("group_value")
        if need_group and pred_group not in (None, "") and gold_group not in (None, "") and str(pred_group) != str(gold_group):
            out.append({**row, "gold_id": gid, "gold_group": gold_group, "label": "correct support but wrong group"})
            continue
        if need_group and pred_group in (None, "") and gold_group not in (None, ""):
            out.append({**row, "gold_id": gid, "gold_group": gold_group, "label": "correct support but wrong group"})
            continue
        need_count = any(valid[qid]["count_column"] for qid in qids)
        if need_count and all(valid[qid]["counted"].get(gid) in (None, "") for qid in qids if valid[qid]["count_column"]):
            out.append({**row, "gold_id": gid, "label": "counted value should be NULL"})
            continue
        need_dist = any(valid[qid]["distinct_sql"] for qid in qids)
        if need_dist:
            for qid in qids:
                val = valid[qid]["distincts"].get(gid)
                others = [other for other, item in valid[qid]["distincts"].items() if other != gid and item == val and val not in (None, "")]
                if others:
                    out.append({**row, "gold_id": gid, "label": "duplicate distinct identity", "distinct_value": val})
                    break
            else:
                out.append({**row, "gold_id": gid, "gold_group": gold_group, "label": "correct gold support witness"})
            continue
        out.append({**row, "gold_id": gid, "gold_group": gold_group, "label": "correct gold support witness"})
    return out


def gold_true_for_task(
    condition_id: str,
    rowid: int,
    programs,
    gold_sets: dict[str, Any],
    rid_to_gold: dict[int, str],
) -> list[dict[str, Any]]:
    gid = rid_to_gold.get(int(rowid))
    if gid in (None, ""):
        return []
    valid = gold_sets["valid"]
    additions = []
    for program in programs:
        if program.condition_id != condition_id:
            continue
        qids = [qid for qid in program.query_ids if qid in valid]
        if not qids:
            continue
        if not any(gid in valid[qid]["id_set"] for qid in qids):
            continue
        group = next((valid[qid]["groups"].get(gid) for qid in qids if valid[qid]["groups"]), None)
        counted = next((valid[qid]["counted"].get(gid) for qid in qids if valid[qid]["count_column"]), None)
        if program.group_sql and group in (None, ""):
            continue
        if "counted_value" in program.kinds and counted in (None, ""):
            continue
        additions.append(
            {
                "program_id": program.program_id,
                "rowid": int(rowid),
                "group_value": None if group in (None, "") else str(group),
                "query_ids": program.query_ids,
                "entity_gold_id": gid,
            }
        )
    return additions


def materialize(dest: Path, additions: list[dict[str, Any]], programs, statements, predicates) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(PLUMBING, dest)
    conn = sqlite3.connect(str(dest))
    ensure_tables(conn)
    register_programs(conn, programs)
    seen = set()
    kept = 0
    for row in additions:
        key = (row["program_id"], encode_witness_key([row["rowid"]]))
        if key in seen:
            continue
        seen.add(key)
        insert_addition(
            conn,
            {
                "program_id": row["program_id"],
                "witness_key": key[1],
                "truth": True,
                "group_value": row.get("group_value"),
                "query_ids": row.get("query_ids") or [],
            },
        )
        kept += 1
    conn.commit()
    from quwarts.core.schema_columns import assert_queries_execute

    assert_queries_execute(
        conn,
        {qid: official_sql(sql, dest, predicates, query_id=qid) for qid, sql in statements.items()},
        any_error=True,
    )
    conn.close()
    return {"db": str(dest), "n": kept, "empty": empty_bags(dest, statements, predicates)}


def coverage_report(selected: list[tuple[str, int]], stats: list[dict[str, Any]], test_ids: set[str]) -> dict[str, Any]:
    by_cond = defaultdict(set)
    for cid, rid in selected:
        by_cond[cid].add(rid)
    complete = []
    test_q = 0
    nontest_q = 0
    for row in stats:
        needed = row["blocked_candidates"]
        have = len(by_cond.get(row["condition_id"], set()))
        # blocked_candidates is per-program; shared condition tasks cover the program if have >= needed
        done = needed > 0 and have >= needed
        if done:
            complete.append(row["program_id"])
        for qid in row["query_ids"]:
            if qid in test_ids:
                test_q += 1 if done else 0
            else:
                nontest_q += 1 if done else 0
    return {
        "completely_covered_programs": len(complete),
        "complete_program_ids": complete,
        "complete_test_queries": test_q,
        "complete_nontest_queries": nontest_q,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inv = load_inventory()
    stats, meta = build_program_stats(inv)
    (OUT / "program_coverage.json").write_text(json.dumps({"meta": meta, "programs": stats}, indent=2, default=str))
    schedules = freeze_schedules(inv, stats)

    # Gold is loaded only after schedules are hashed.
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    gold_sets = reconstruct_gold(inv["statements"], gold)
    (OUT / "gold_witness_validation.json").write_text(
        json.dumps(
            {
                "valid_queries": len(gold_sets["valid"]),
                "invalid": gold_sets["invalid"],
                "support_sizes": {qid: len(row["ids"]) for qid, row in gold_sets["valid"].items()},
            },
            indent=2,
            default=str,
        )
    )
    rid_to_gold, _gold_to_rid, _rows = plumbing_maps()
    accepted = [row for row in inv["journal"] if row.get("accepted")]
    labeled = classify_accepted(accepted, inv["programs"], gold_sets, rid_to_gold)
    labels = Counter(row["label"] for row in labeled)
    correct = [row for row in labeled if row["label"] == "correct gold support witness"]
    support_ok = [row for row in labeled if row["label"] not in {"false-positive support", "untraceable"}]
    group_ok = [row for row in labeled if row["label"] in {"correct gold support witness", "correct support/group but wrong aggregate contribution", "counted value should be NULL", "duplicate distinct identity"}]
    n = max(1, len(labeled))
    precision = {
        "accepted": len(labeled),
        "labels": dict(labels),
        "semantic_support_precision": len(correct) / n,
        "support_precision_allowing_group_errors": len(support_ok) / n,
        "group_accuracy_among_support": (len(group_ok) / max(1, len(support_ok))),
        "aggregate_accuracy": None,
    }

    audit = audit_workload(inv["queries"])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    _, test = split_80_20(inv["queries"], 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    test_ids = {row["query_id"] for row in test_count}
    plumbing_snap = snapshot_base(PLUMBING)

    attempted_pairs = {(row["condition_id"], int(row["rowid"])) for row in inv["journal"]}
    blocked_pairs = {(row["condition_id"], int(row["rowid"])) for row in inv["block_log"] if row.get("include")}
    sched25_pairs = [(row["condition_id"], int(row["rowid"])) for row in schedules["schedule_25"]]
    sched100_pairs = [(row["condition_id"], int(row["rowid"])) for row in schedules["schedule_100"]]

    def expand(pairs) -> list[dict[str, Any]]:
        found = []
        seen = set()
        for cid, rid in pairs:
            for item in gold_true_for_task(cid, rid, inv["programs"], gold_sets, rid_to_gold):
                key = (item["program_id"], item["rowid"])
                if key in seen:
                    continue
                seen.add(key)
                found.append(item)
        return found

    correct_adds = [
        {
            "program_id": row["program_id"],
            "rowid": row["rowid"],
            "group_value": row.get("gold_group") if row.get("gold_group") not in (None, "") else row.get("group_value"),
            "query_ids": row["query_ids"],
        }
        for row in correct
    ]
    counterfactuals = {
        "correct_subset_96": correct_adds,
        "gold_attempted_805": expand(attempted_pairs),
        "gold_schedule_25": expand(sched25_pairs),
        "gold_schedule_100": expand(sched100_pairs),
        "gold_all_blocked": expand(blocked_pairs),
    }
    scores = {}
    cov = {
        "correct_subset_96": coverage_report([(row["condition_id"], int(row["rowid"])) for row in correct], stats, test_ids),
        "gold_attempted_805": coverage_report(list(attempted_pairs), stats, test_ids),
        "gold_schedule_25": coverage_report(sched25_pairs, stats, test_ids),
        "gold_schedule_100": coverage_report(sched100_pairs, stats, test_ids),
        "gold_all_blocked": coverage_report(list(blocked_pairs), stats, test_ids),
    }
    dests = {}
    for name, adds in counterfactuals.items():
        dest = OUT / "databases" / f"{name}.db"
        dests[name] = materialize(dest, adds, inv["programs"], inv["statements"], predicates)
        if snapshot_base(dest)["identity_values"] != plumbing_snap["identity_values"]:
            raise SystemExit(f"{name} mutated plumbing identity")
        rewrites = {row["query_id"]: official_sql(row["sql"], dest, predicates, query_id=row["query_id"]) for row in test_count}
        scores[name] = _score(dest, test_count, rewrites, gold) | {
            "additions": dests[name]["n"],
            "empty_bags": len(dests[name]["empty"]),
            **cov[name],
        }
        print(json.dumps({"scored": name, "product": scores[name]["mean_per_query_product"], "f2": scores[name]["mean_structure_f2"], "additions": dests[name]["n"]}, indent=2), flush=True)

    rewrites_plumb = {row["query_id"]: official_sql(row["sql"], PLUMBING, predicates, query_id=row["query_id"]) for row in test_count}
    plumbing_score = _score(PLUMBING, test_count, rewrites_plumb, gold)

    def beats(name: str) -> bool:
        return scores[name]["mean_per_query_product"] > DOCETL["product"]

    ceiling = beats("gold_all_blocked")
    classifier_fail = (len(correct) / n) < 0.5 or not beats("gold_attempted_805")
    scheduler_fail = beats("gold_schedule_100") and not beats("gold_attempted_805")
    if not ceiling:
        conclusion = "query-witness ceiling insufficient"
    elif classifier_fail and scheduler_fail:
        conclusion = "both"
    elif classifier_fail:
        conclusion = "classifier failure"
    elif scheduler_fail:
        conclusion = "scheduler failure"
    else:
        conclusion = "query-witness ceiling insufficient"

    report = {
        "gold_reconstruction": {
            "valid_queries": len(gold_sets["valid"]),
            "invalid_queries": len(gold_sets["invalid"]),
            "invalid": gold_sets["invalid"],
        },
        "accepted_labels": dict(labels),
        "precision": precision,
        "program_stats": stats,
        "program_meta": meta,
        "schedules": {
            "sha256": schedules["sha256"],
            "n_25": schedules["n_25"],
            "n_100": schedules["n_100"],
            "cost_25": schedules["cost_25"],
            "cost_100": schedules["cost_100"],
            "prefix": schedules["prefix"],
            "gold_used": False,
        },
        "plumbing": plumbing_score,
        "counterfactuals": {
            name: {
                "tokens_budget": None,
                "additions": scores[name]["additions"],
                "mean_structure_f2": scores[name]["mean_structure_f2"],
                "mean_cell_f1_at_0.20": scores[name]["mean_cell_f1_at_0.20"],
                "mean_per_query_product": scores[name]["mean_per_query_product"],
                "completely_covered_programs": scores[name]["completely_covered_programs"],
                "complete_test_queries": scores[name]["complete_test_queries"],
                "complete_nontest_queries": scores[name]["complete_nontest_queries"],
                "empty_bags": scores[name]["empty_bags"],
            }
            for name in scores
        },
        "docetl": DOCETL,
        "conclusion": conclusion,
        "hashes": {
            "journal_100": FROZEN_JOURNAL_100,
            "schedules": schedules["sha256"],
            "labels": _hash(labeled),
            "policy": policy_hash(),
        },
    }
    (OUT / "finan_query_witness_semantic.json").write_text(json.dumps(report, indent=2, default=str))
    (OUT / "accepted_labels.json").write_text(json.dumps(labeled, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT / "finan_query_witness_semantic.json"), "conclusion": conclusion, "precision": precision, "products": {k: v["mean_per_query_product"] for k, v in scores.items()}}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
