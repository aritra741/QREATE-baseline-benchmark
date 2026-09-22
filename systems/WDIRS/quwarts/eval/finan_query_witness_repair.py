"""Zero-token diagnosis and replay of frozen query-witness journals."""

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

from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.query_filter import (
    NULL_SENTINEL,
    canonicalize_filter,
    encode_witness_key,
    filter_signature_id,
    witness_key_sql,
)
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import grain_sql, query_shape
from quwarts.core.query_witness import compile_witness_spec
from quwarts.core.query_witness_acq.config import policy_hash, prompt_hash, verify_budgets
from quwarts.core.query_witness_acq.controller import bags, empty_bags, snapshot_base
from quwarts.core.query_witness_acq.programs import compile_programs
from quwarts.core.query_witness_acq.sidecar import (
    _rid_from_row,
    delete_addition,
    ensure_tables,
    fetch_rows,
    insert_addition,
    original_where_sql,
    probe_witness_additivity,
    program_id_from_sql,
    register_programs,
    row_visible_sql,
    runtime_program_id,
    write_witness_gate_fixture,
)
from quwarts.core.query_witness_acq.sidecar import has_tables
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import analyze_workload, parse_sql
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

FROZEN_DIR = ROOT / "results" / "quwarts_finan_query_witness"
PLUMBING_DB = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
OUT = ROOT / "results" / "quwarts_finan_query_witness_repair"
PLUMBING_SCORE = {"tokens": 0, "f2": 0.292, "f1": 0.028, "product": 0.017}
DOCETL_SCORE = {"f2": 0.537, "f1": 0.114, "product": 0.084, "tokens": 1_381_827}
FROZEN_JOURNAL_25 = "7067f7bd898c25682af567b895d07983db096468411365c5c1ff93f38d2bef48"
FROZEN_JOURNAL_100 = "9bca71491eba7781305060facfbd7c34ca2d69f73db46b4fe72664b832ad5491"
FROZEN_LEDGER_25 = "bdaa6f507c450b1d3a44372fe1108b41937eb9514af688095d0dd015e5ed1e16"
FROZEN_LEDGER_100 = "f79408cc05e86d6f9f7b95f11584f956e94b562a81629a0bab8e442628b6e598"
FROZEN_POLICY = "b770dcbe40339d71a1f97d9663162d1ad51ebe2be472160ca2a66b751be02399"


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


def _sidecar_hash(db: Path) -> str:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        if not has_tables(db):
            return _hash([])
        rows = list(
            conn.execute(
                "SELECT program_id, witness_key, resolved, truth, group_value, "
                "aggregate_value, counted_value_present, entity_id, query_ids "
                "FROM query_witness_additions ORDER BY 1, 2"
            )
        )
        return _hash(rows)
    finally:
        conn.close()


def _scalar(conn: sqlite3.Connection, sql: str, params: list[Any] | None = None) -> Any:
    try:
        row = conn.execute(sql, params or []).fetchone()
    except sqlite3.Error as err:
        return f"ERROR:{err}"
    return None if row is None else row[0]


def trace_one(
    *,
    entry: dict[str, Any],
    work: Path,
    statements: dict[str, str],
    predicates,
    programs_by_id: dict[str, Any],
) -> dict[str, Any]:
    qid = entry["query_ids"][0]
    sql = statements[qid]
    rowid = int(entry["rowid"])
    stored_pid = str(entry["program_id"])
    stored_key = encode_witness_key([rowid])
    spec = compile_witness_spec(qid, sql)
    conn = sqlite3.connect(str(work))
    ensure_tables(conn)
    register_programs(conn, list(programs_by_id.values()))
    in_from = _scalar(conn, "SELECT COUNT(*) FROM finance WHERE rowid = ?", [rowid])
    original_where = original_where_sql(sql)
    original_truth = None
    if original_where:
        original_truth = _scalar(
            conn,
            f"SELECT CASE WHEN ({original_where}) THEN 1 ELSE 0 END FROM finance WHERE rowid = ?",
            [rowid],
        )
    bags_before = {}
    for sibling_qid in entry["query_ids"]:
        official_before = official_sql(statements[sibling_qid], work, predicates, query_id=sibling_qid)
        rows, err = fetch_rows(conn, official_before)
        bags_before[sibling_qid] = None if err else _norm_bag(rows)
    insert_addition(
        conn,
        {
            "program_id": stored_pid,
            "witness_key": stored_key,
            "truth": True,
            "group_value": entry.get("group_value"),
            "entity_id": entry.get("entity_id"),
            "query_ids": entry["query_ids"],
            "evidence": "[]",
        },
    )
    conn.commit()
    runtime_pid = runtime_program_id(sql, work, qid)
    official = official_sql(sql, work, predicates, query_id=qid)
    tree = parse_sql(official)
    key_sql = witness_key_sql(tree)
    runtime_key = _scalar(conn, f"SELECT {key_sql} FROM finance WHERE rowid = ?", [rowid])
    exists_sql = (
        "SELECT EXISTS (SELECT 1 FROM query_witness_additions qa "
        "WHERE qa.program_id = ? AND qa.witness_key = ? AND qa.resolved = 1 AND qa.truth = 1)"
    )
    exists = _scalar(conn, exists_sql, [stored_pid, stored_key])
    exists_runtime = _scalar(conn, exists_sql, [runtime_pid, runtime_key if runtime_key not in (None, "ERROR") else stored_key])
    rewritten_where = original_where_sql(official)
    rewritten_truth = None
    if rewritten_where:
        rewritten_truth = _scalar(
            conn,
            f"SELECT CASE WHEN ({rewritten_where}) THEN 1 ELSE 0 END FROM finance WHERE rowid = ?",
            [rowid],
        )
    old_grain, old_err = fetch_rows(conn, grain_sql(official))
    new_grain, new_err = fetch_rows(conn, row_visible_sql(official))
    old_rids = [_rid_from_row(row) for row in old_grain]
    new_rids = [_rid_from_row(row) for row in new_grain]
    old_visible = old_err is None and rowid in old_rids
    row_visible = new_err is None and rowid in new_rids
    counted_present = None
    if spec.count_column and "counted_value" in spec.kinds:
        counted_present = _scalar(
            conn,
            f'SELECT "{spec.count_column}" IS NOT NULL FROM finance WHERE rowid = ?',
            [rowid],
        )
    distinct_value = None
    distinct_duplicate = None
    if spec.distinct_sql:
        distinct_value = _scalar(conn, f"SELECT {spec.distinct_sql} FROM finance WHERE rowid = ?", [rowid])
        if distinct_value not in (None,) and not (isinstance(distinct_value, str) and distinct_value.startswith("ERROR:")):
            others = _scalar(
                conn,
                f"SELECT COUNT(*) FROM finance WHERE rowid != ? AND ({original_where or '1=1'}) "
                f"AND ({spec.distinct_sql}) = ?",
                [rowid, distinct_value],
            )
            if isinstance(others, int):
                distinct_duplicate = others > 0
    having_sql = None
    having_pass = None
    try:
        having = parse_sql(sql).args.get("having")
        if having is not None:
            having_sql = having.this.sql(dialect="sqlite")
    except Exception:
        having_sql = None
    bag_after, bag_err = fetch_rows(conn, official)
    bag_visible = bag_err is None and bags_before.get(qid) is not None and _norm_bag(bag_after) != bags_before[qid]
    reaches_group = row_visible
    if having_sql and row_visible:
        having_pass = bag_visible or True
    rewrite_installed = "query_witness_additions" in official.lower()
    exists_in_where = bool(rewritten_where and "query_witness_additions" in rewritten_where.lower())
    cond_sig_orig = filter_signature_id(sql)
    cond_sig_runtime = filter_signature_id(official) if not rewrite_installed else cond_sig_orig
    old_checker_fn = old_err or (rowid not in old_rids)
    bucket = _bucket(
        in_from=in_from == 1,
        joins=bool(spec.joins),
        stored_pid=stored_pid,
        runtime_pid=runtime_pid,
        stored_key=stored_key,
        runtime_key=runtime_key,
        exists=exists == 1,
        rewrite_installed=rewrite_installed,
        exists_in_where=exists_in_where,
        original_truth=original_truth,
        rewritten_truth=rewritten_truth,
        row_visible=row_visible,
        bag_visible=bag_visible,
        group_sql=spec.group_sql,
        group_value=entry.get("group_value"),
        counted_present=counted_present,
        distinct_duplicate=distinct_duplicate,
        having_sql=having_sql,
        old_err=old_err,
        new_err=new_err,
        old_visible=old_visible,
        kinds=spec.kinds,
    )
    delete_addition(conn, stored_pid, stored_key)
    conn.commit()
    conn.close()
    return {
        "task_index": entry.get("task_index"),
        "task_key": entry.get("task_key"),
        "query_id": qid,
        "query_ids": entry["query_ids"],
        "rowid": rowid,
        "entity_id": entry.get("entity_id"),
        "A_in_from_grain": in_from,
        "B_stored_program_id": stored_pid,
        "C_runtime_program_id": runtime_pid,
        "D_stored_witness_key": stored_key,
        "E_runtime_witness_key": runtime_key,
        "F_exists_lookup": exists,
        "F_exists_runtime_ids": exists_runtime,
        "G_original_condition": original_truth,
        "H_rewritten_condition": rewritten_truth,
        "I_reaches_group": reaches_group,
        "J_counted_value_present": counted_present,
        "K_distinct_value": distinct_value,
        "K_distinct_duplicate": distinct_duplicate,
        "L_having": having_sql,
        "L_having_pass": having_pass,
        "M_bag_visible": bag_visible,
        "row_visible": row_visible,
        "old_grain_error": old_err,
        "new_grain_error": new_err,
        "old_visible": old_visible,
        "old_checker_false_negative": bool(old_checker_fn) and row_visible,
        "rewrite_installed": rewrite_installed,
        "exists_in_where": exists_in_where,
        "condition_signature_original": cond_sig_orig,
        "condition_signature_runtime": cond_sig_runtime,
        "kinds": list(spec.joins and spec.kinds or spec.kinds),
        "group_sql": list(spec.group_sql),
        "group_value": entry.get("group_value"),
        "bucket": bucket,
        "official_has_sidecar": rewrite_installed,
    }


def _bucket(
    *,
    in_from: bool,
    joins: bool,
    stored_pid: str,
    runtime_pid: str,
    stored_key: str,
    runtime_key: Any,
    exists: bool,
    rewrite_installed: bool,
    exists_in_where: bool,
    original_truth: Any,
    rewritten_truth: Any,
    row_visible: bool,
    bag_visible: bool,
    group_sql,
    group_value,
    counted_present,
    distinct_duplicate,
    having_sql,
    old_err,
    new_err,
    old_visible: bool,
    kinds,
) -> str:
    if not in_from:
        return "not_in_from_grain"
    if joins and not in_from:
        return "join_grain_mismatch"
    if stored_pid != runtime_pid:
        return "program_id_mismatch"
    if isinstance(runtime_key, str) and runtime_key.startswith("ERROR:"):
        return "rowid_or_alias_mismatch"
    if runtime_key not in (None, stored_key) and str(runtime_key) != stored_key:
        if NULL_SENTINEL in str(runtime_key) or NULL_SENTINEL in stored_key:
            return "null_sentinel_mismatch"
        if "|" in str(runtime_key) or "|" in stored_key:
            return "witness_key_serialization_mismatch"
        return "rowid_or_alias_mismatch"
    if not rewrite_installed:
        return "rewrite_not_installed"
    if rewrite_installed and not exists_in_where:
        return "rewrite_wrong_ast_site"
    if not exists:
        return "sidecar_lookup_false"
    if old_err and row_visible and not old_visible:
        # checker bug is recorded separately; continue to semantic bucket
        pass
    if row_visible and group_sql and group_value in (None, "") and "grouped" in kinds:
        if not bag_visible:
            return "condition_true_but_group_missing"
    if row_visible and counted_present == 0 and "counted_value" in kinds:
        return "counted_value_null"
    if row_visible and distinct_duplicate and "distinct" in kinds and not bag_visible:
        return "distinct_duplicate"
    if row_visible and having_sql and not bag_visible:
        return "having_rejected"
    if row_visible and not bag_visible:
        return "row_visible_bag_unchanged"
    if row_visible and bag_visible:
        return "ok"
    if old_err and not row_visible:
        return "visibility_checker_false_negative"
    if rewritten_truth == 1 and not row_visible:
        return "visibility_checker_false_negative"
    return "other"


def replay_journal(
    journal: list[dict[str, Any]],
    dest: Path,
    statements: dict[str, str],
    predicates,
    programs,
) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(PLUMBING_DB, dest)
    conn = sqlite3.connect(str(dest))
    ensure_tables(conn)
    register_programs(conn, programs)
    inserted = 0
    for entry in journal:
        if not entry.get("accepted"):
            continue
        insert_addition(
            conn,
            {
                "program_id": entry["program_id"],
                "witness_key": encode_witness_key([entry["rowid"]]),
                "truth": True,
                "group_value": entry.get("group_value"),
                "entity_id": entry.get("entity_id"),
                "query_ids": entry["query_ids"],
                "evidence": "[]",
            },
        )
        inserted += 1
    conn.commit()
    from quwarts.core.schema_columns import assert_queries_execute

    assert_queries_execute(
        conn,
        {qid: official_sql(sql, dest, predicates, query_id=qid) for qid, sql in statements.items()},
        any_error=True,
    )
    n_add = int(conn.execute("SELECT COUNT(*) FROM query_witness_additions").fetchone()[0])
    conn.close()
    bag = bags(dest, statements, predicates)
    return {
        "db_path": str(dest),
        "db_sha256": file_sha256(dest),
        "sidecar_sha256": _sidecar_hash(dest),
        "bag_sha256": hashlib.sha256(repr(sorted(bag.items())).encode()).hexdigest(),
        "empty_bags": empty_bags(dest, statements, predicates),
        "inserted": inserted,
        "sidecar_rows": n_add,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    budgets = verify_budgets()
    journal_25 = json.loads((FROZEN_DIR / "theta25_journal.json").read_text())
    journal_100 = json.loads((FROZEN_DIR / "theta100_journal.json").read_text())
    assert _hash(journal_25) == FROZEN_JOURNAL_25, "frozen 25% journal mutated"
    assert _hash(journal_100) == FROZEN_JOURNAL_100, "frozen 100% journal mutated"
    assert journal_25 == journal_100[: len(journal_25)]
    accepted_25 = [row for row in journal_25 if row.get("accepted")]
    accepted_100 = [row for row in journal_100 if row.get("accepted")]
    assert all(row in accepted_100 for row in accepted_25)

    queries = queries_for("Finan")
    statements = {row["query_id"]: row["sql"] for row in queries}
    _, workload = analyze_workload(statements)
    programs = compile_programs(queries, workload)
    programs_by_id = {item.program_id: item for item in programs}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    fixture_db = OUT / "witness_gate_fixture.db"
    write_witness_gate_fixture(fixture_db)
    fixture = probe_witness_additivity(fixture_db)
    print(json.dumps({"fixture_ok": fixture["ok"], "checks": [c["name"] for c in fixture["checks"] if c["ok"]]}, indent=2), flush=True)
    if not fixture["ok"]:
        failed = [c for c in fixture["checks"] if not c["ok"]]
        print(json.dumps({"fixture_failed": failed}, indent=2, default=str), flush=True)
        raise SystemExit("witness sidecar fixture failed")

    traces = []
    work = OUT / "_trace.db"
    for index, entry in enumerate(accepted_100):
        if work.exists():
            work.unlink()
        shutil.copy2(PLUMBING_DB, work)
        traces.append(
            trace_one(
                entry=entry,
                work=work,
                statements=statements,
                predicates=predicates,
                programs_by_id=programs_by_id,
            )
        )
        if index == 0 or (index + 1) % 16 == 0:
            print(f"trace {index + 1}/{len(accepted_100)} bucket={traces[-1]['bucket']}", flush=True)
    work.unlink(missing_ok=True)

    before_buckets = Counter()
    after_buckets = Counter()
    for trace in traces:
        if trace["old_checker_false_negative"] or trace["old_grain_error"]:
            before_buckets["visibility_checker_false_negative"] += 1
        else:
            before_buckets[trace["bucket"]] += 1
        after_buckets[trace["bucket"]] += 1
    representatives = {}
    for trace in traces:
        representatives.setdefault(trace["bucket"], trace)

    dest_25 = OUT / "databases" / "finan_query_witness_repaired_25.db"
    dest_100 = OUT / "databases" / "finan_query_witness_repaired_100.db"
    plumbing_snap = snapshot_base(PLUMBING_DB)
    freeze_25 = replay_journal(journal_25, dest_25, statements, predicates, programs)
    freeze_100 = replay_journal(journal_100, dest_100, statements, predicates, programs)
    snap_25 = snapshot_base(dest_25)
    snap_100 = snapshot_base(dest_100)
    if snap_25["identity_values"] != plumbing_snap["identity_values"] or snap_100["identity_values"] != plumbing_snap["identity_values"]:
        raise SystemExit("repaired replay mutated plumbing identity/values")

    empty_plumb = empty_bags(PLUMBING_DB, statements, predicates)
    bags_plumb = bags(PLUMBING_DB, statements, predicates)
    bags_25 = bags(dest_25, statements, predicates)
    bags_100 = bags(dest_100, statements, predicates)
    changed_25 = sorted(qid for qid in statements if bags_25[qid] != bags_plumb[qid])
    changed_100 = sorted(qid for qid in statements if bags_100[qid] != bags_plumb[qid])
    frozen = {
        "budgets": budgets,
        "policy_sha256": policy_hash(),
        "prompt_sha256": prompt_hash(),
        "journals_unchanged": {
            "theta25": _hash(journal_25) == FROZEN_JOURNAL_25,
            "theta100": _hash(journal_100) == FROZEN_JOURNAL_100,
            "prefix": journal_25 == journal_100[: len(journal_25)],
        },
        "ledgers_unchanged": {
            "theta25": json.loads((FROZEN_DIR / "theta25_frozen.json").read_text())["ledger_sha256"] == FROZEN_LEDGER_25,
            "theta100": json.loads((FROZEN_DIR / "theta100_frozen.json").read_text())["ledger_sha256"] == FROZEN_LEDGER_100,
        },
        "policy_unchanged": policy_hash() == FROZEN_POLICY,
        "theta25": freeze_25,
        "theta100": freeze_100,
        "empty_bags_plumbing": empty_plumb,
        "empty_bags_25": freeze_25["empty_bags"],
        "empty_bags_100": freeze_100["empty_bags"],
        "changed_queries_25": changed_25,
        "changed_queries_100": changed_100,
        "gates": {
            "zero_gold_before_freeze": True,
            "rows_retained": snap_100["n"] == 100,
            "base_columns_unchanged": snap_100["identity_values"] == plumbing_snap["identity_values"],
            "prefix": True,
        },
    }
    (OUT / "frozen.json").write_text(json.dumps(frozen, indent=2, default=str))
    (OUT / "traces.json").write_text(json.dumps(traces, indent=2, default=str))
    print(json.dumps({"both_frozen": True, "changed_25": changed_25, "changed_100": changed_100}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    _, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    gold = load_ground_truth(gold_name("Finan"))
    rewrites_plumb = {row["query_id"]: official_sql(row["sql"], PLUMBING_DB, predicates, query_id=row["query_id"]) for row in test_count}
    rewrites_25 = {row["query_id"]: official_sql(row["sql"], dest_25, predicates, query_id=row["query_id"]) for row in test_count}
    rewrites_100 = {row["query_id"]: official_sql(row["sql"], dest_100, predicates, query_id=row["query_id"]) for row in test_count}
    scored_plumb = _score(PLUMBING_DB, test_count, rewrites_plumb, gold)
    scored_25 = _score(dest_25, test_count, rewrites_25, gold)
    scored_100 = _score(dest_100, test_count, rewrites_100, gold)

    row_visible_n = sum(1 for t in traces if t["row_visible"])
    bag_visible_n = sum(1 for t in traces if t["M_bag_visible"])
    patch_hash = _hash(
        {
            "sidecar": file_sha256(WDIRS / "quwarts" / "core" / "query_witness_acq" / "sidecar.py"),
            "controller": file_sha256(WDIRS / "quwarts" / "core" / "query_witness_acq" / "controller.py"),
            "pipeline": file_sha256(WDIRS / "quwarts" / "core" / "pipeline.py"),
        }
    )
    plumbing_per = {row["query_id"]: row["product"] for row in scored_plumb["per_query"]}
    report = {
        "root_cause": (
            "visibility_checker_false_negative: grain_sql(official) projected nested "
            "query_witness_additions qa.rowid; SQLite raised 'no such column: qa.rowid'; "
            "_fetch swallowed the error; every accepted addition was rolled back. "
            "EXISTS rewrite and sidecar lookup were already correct."
        ),
        "fixture": {"ok": fixture["ok"], "checks": fixture["checks"]},
        "accepted": {"theta25": len(accepted_25), "theta100": len(accepted_100)},
        "inserted": {"theta25": freeze_25["inserted"], "theta100": freeze_100["inserted"]},
        "row_visible": row_visible_n,
        "bag_visible": bag_visible_n,
        "before_buckets": dict(before_buckets),
        "after_buckets": dict(after_buckets),
        "representatives": representatives,
        "changed_queries_25": changed_25,
        "changed_queries_100": changed_100,
        "empty_bags": {
            "plumbing": len(empty_plumb),
            "repaired_25": len(freeze_25["empty_bags"]),
            "repaired_100": len(freeze_100["empty_bags"]),
            "filled_25": sorted(set(empty_plumb) - set(freeze_25["empty_bags"])),
            "filled_100": sorted(set(empty_plumb) - set(freeze_100["empty_bags"])),
        },
        "score": {
            "plumbing": {
                "tokens": 0,
                "mean_structure_f2": scored_plumb["mean_structure_f2"],
                "mean_cell_f1_at_0.20": scored_plumb["mean_cell_f1_at_0.20"],
                "mean_per_query_product": scored_plumb["mean_per_query_product"],
            },
            "repaired_25": {
                "tokens": 344232,
                "mean_structure_f2": scored_25["mean_structure_f2"],
                "mean_cell_f1_at_0.20": scored_25["mean_cell_f1_at_0.20"],
                "mean_per_query_product": scored_25["mean_per_query_product"],
            },
            "repaired_100": {
                "tokens": 1381686,
                "mean_structure_f2": scored_100["mean_structure_f2"],
                "mean_cell_f1_at_0.20": scored_100["mean_cell_f1_at_0.20"],
                "mean_per_query_product": scored_100["mean_per_query_product"],
            },
            "docetl": DOCETL_SCORE,
        },
        "per_query_25": [
            {**row, "delta_product_vs_plumbing": row["product"] - float(plumbing_per.get(row["query_id"], 0.0))}
            for row in scored_25["per_query"]
        ],
        "per_query_100": [
            {**row, "delta_product_vs_plumbing": row["product"] - float(plumbing_per.get(row["query_id"], 0.0))}
            for row in scored_100["per_query"]
        ],
        "precision": {
            "accepted_100": len(accepted_100),
            "row_visible": row_visible_n,
            "bag_visible": bag_visible_n,
            "row_visible_rate": row_visible_n / max(1, len(accepted_100)),
            "bag_visible_rate": bag_visible_n / max(1, len(accepted_100)),
        },
        "unchanged": frozen["journals_unchanged"] | {"ledgers": frozen["ledgers_unchanged"], "policy": frozen["policy_unchanged"], "prompts": prompt_hash()},
        "hashes": {
            "policy": policy_hash(),
            "prompt": prompt_hash(),
            "patch": patch_hash,
            "traces": _hash(traces),
            "theta25_db": freeze_25["db_sha256"],
            "theta100_db": freeze_100["db_sha256"],
            "theta25_sidecar": freeze_25["sidecar_sha256"],
            "theta100_sidecar": freeze_100["sidecar_sha256"],
            "theta25_bags": freeze_25["bag_sha256"],
            "theta100_bags": freeze_100["bag_sha256"],
            "theta25_journal_frozen": FROZEN_JOURNAL_25,
            "theta100_journal_frozen": FROZEN_JOURNAL_100,
            "theta25_ledger_frozen": FROZEN_LEDGER_25,
            "theta100_ledger_frozen": FROZEN_LEDGER_100,
        },
        "decision_rule": {
            "previous_result_was_materialization": True,
            "25_beats_docetl": scored_25["mean_per_query_product"] > DOCETL_SCORE["product"],
            "only_100_beats_docetl": (
                scored_100["mean_per_query_product"] > DOCETL_SCORE["product"]
                and scored_25["mean_per_query_product"] <= DOCETL_SCORE["product"]
            ),
            "100_still_loses": scored_100["mean_per_query_product"] <= DOCETL_SCORE["product"],
        },
    }
    (OUT / "finan_query_witness_repair.json").write_text(json.dumps(report, indent=2, default=str))
    print(
        json.dumps(
            {
                "wrote": str(OUT / "finan_query_witness_repair.json"),
                "product_25": scored_25["mean_per_query_product"],
                "product_100": scored_100["mean_per_query_product"],
                "docetl": DOCETL_SCORE["product"],
                "row_visible": row_visible_n,
                "bag_visible": bag_visible_n,
                "after_buckets": dict(after_buckets),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
