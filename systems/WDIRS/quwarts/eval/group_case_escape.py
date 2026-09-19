"""Zero-token CASE-fallback replay of stored group votes. Gold after freeze."""

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

from quwarts.core.component_oracle import base_checksums
from quwarts.core.group_case_escape import inspect_votes
from quwarts.core.group_consensus import replay_consensus
from quwarts.core.group_replay import is_sql_null, load_group_votes
from quwarts.core.query_group import apply_official_group, fill_gold_group_labels, group_bags
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.query_witness import normalize_group
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites
from spp.config_grid import _build_in_memory_db

COMPARE = ROOT / "results" / "quwarts_med_signatures" / "acquisition_compare.json"
DOCETL_EVAL = ROOT / "results" / "docetl_med_case80" / "evaluation.json"
OUT = ROOT / "results" / "quwarts_med_signatures"
VOTES = OUT / "group_votes.jsonl"
ARM = OUT / "group_classify.json"
ARM_DB = OUT / "artifacts" / "aprime_group.db"
PRIOR_FULL = OUT / "artifacts" / "aprime_group_full_original.db"
FOCUS = ("med_agg20:q13", "med_multiagg20:q17")
FROZEN_ARM_PRODUCT = 0.1443894647019647
INCUMBENT_PRODUCT = 0.12439887110939743
OFFICIAL_RULE = "unknown_else_escape"


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _score(test, dest, gold, rewrites):
    report = score_with_rewrites(test, rewrites, dest, gold, "Med")
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


def _rewrites(rows, dest, predicates, site_local: bool):
    return {
        row["query_id"]: apply_official_group(
            row["sql"], dest, predicates, site_id=row["query_id"] if site_local else None
        )[0]
        for row in rows
    }


def _write_from_inspect(item: dict[str, Any]) -> dict[str, Any]:
    vote = item["vote"]
    return {
        "query_id": item["query_id"],
        "expr_id": item["expr_id"],
        "witness_key": item["witness_key"],
        "group_value": vote.get("group_value"),
        "old_label": vote.get("old_label"),
        "resolved": True,
        "agreement": vote.get("agreement"),
        "direct_decision": vote.get("direct_decision"),
        "branch_decision": vote.get("branch_decision"),
        "adjudicator_decision": vote.get("adjudicator_decision"),
        "raw": vote.get("raw") or {},
        "context_hash": vote.get("context_hash") or "",
        "token_cost": 0,
    }


def _focus_rows(inspected: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out = {qid: [] for qid in FOCUS}
    for item in inspected:
        if item["query_id"] not in out:
            continue
        state = item["state"]
        out[item["query_id"]].append(
            {
                "witness_key": item["witness_key"],
                "truths": state["truths"],
                "selected": state["selected"],
                "original_result": state["original_result"],
                "else_value": state["else_value"],
                "proposed": item["proposed"],
                "unknown_else_escape": item["unknown_else_escape"],
                "all_else_escape": item["all_else_escape"],
            }
        )
    return out


def main() -> int:
    queries = queries_for("Med")
    _, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    statements = {row["query_id"]: row["sql"] for row in queries}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    agent = Path((json.loads(COMPARE.read_text()).get("agent") or {}).get("sqlite_path") or "")
    if not agent.is_file() or not VOTES.is_file():
        raise SystemExit("incumbent or votes missing")
    votes = load_group_votes(VOTES)
    print(f"case escape incumbent={agent} votes={len(votes)} tokens=0", flush=True)
    inspected = inspect_votes(agent, queries, predicates, votes)
    n_unknown = sum(1 for item in inspected if item["state"]["selected"] == "ELSE" and item["state"]["n_null"] >= 1)
    n_all_false = sum(1 for item in inspected if item["state"]["selected"] == "ELSE" and item["state"]["n_null"] == 0 and item["state"]["n_true"] == 0)
    n_branch = sum(1 for item in inspected if item["state"]["selected"] == "branch")
    print(
        json.dumps(
            {
                "inspected": len(inspected),
                "else_unknown": n_unknown,
                "else_all_false": n_all_false,
                "branch_selected": n_branch,
                "unknown_else_escape": sum(1 for item in inspected if item["unknown_else_escape"]),
                "all_else_escape": sum(1 for item in inspected if item["all_else_escape"]),
            }
        ),
        flush=True,
    )
    focus = _focus_rows(inspected)
    print(json.dumps({"focus": {qid: {"n": len(rows), "pass_unknown": sum(1 for row in rows if row["unknown_else_escape"]), "rows": rows} for qid, rows in focus.items()}}, default=str), flush=True)

    agent_conn = sqlite3.connect(f"file:{agent}?mode=ro", uri=True)
    agent_checksums = base_checksums(agent_conn)
    agent_conn.close()
    arm_bags = group_bags(ARM_DB, statements, predicates, site_local=False) if ARM_DB.is_file() else {}

    plans = {
        "unknown_else_escape": [_write_from_inspect(item) for item in inspected if item["unknown_else_escape"]],
        "all_else_escape": [_write_from_inspect(item) for item in inspected if item["all_else_escape"]],
    }
    frozen: dict[str, dict[str, Any]] = {}
    for rule, writes in plans.items():
        dest = OUT / "artifacts" / f"aprime_group_{rule}.db"
        if dest.exists():
            dest.unlink()
        shutil.copy2(agent, dest)
        report = replay_consensus(dest, statements, predicates, writes)
        dest_conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
        checksum_ok = base_checksums(dest_conn) == agent_checksums
        dest_conn.close()
        changed = [qid for qid, bag in report["bags"].items() if bag != report["before_bags"].get(qid)]
        frozen[rule] = {
            "dest": str(dest),
            "digest": file_digest(dest),
            "checksums_match_incumbent_base": checksum_ok,
            "n_attempted": report["n_attempted"],
            "n_materialized": report["n_materialized"],
            "n_sql_visible": report["n_sql_visible"],
            "n_sidecar_rows": report["n_sidecar_rows"],
            "n_rolled_back": report["n_rolled_back"],
            "n_isolation_fail": report["n_isolation_fail"],
            "site_local": True,
            "changed_queries": changed,
            "n_changed_queries": len(changed),
            "focus": {
                qid: {
                    "changed": qid in changed,
                    "matches_frozen_arm": bool(arm_bags) and report["bags"].get(qid) == arm_bags.get(qid),
                    "matches_incumbent": report["bags"].get(qid) == report["before_bags"].get(qid),
                    "n_pass": sum(1 for row in focus[qid] if row["unknown_else_escape" if rule == "unknown_else_escape" else "all_else_escape"]),
                }
                for qid in FOCUS
            },
            "accepted": report["accepted"],
        }
        print(
            f"frozen {rule} attempted={report['n_attempted']} visible={report['n_sql_visible']} "
            f"changed={len(changed)} checksums={checksum_ok}",
            flush=True,
        )

    dest = OUT / "artifacts" / "aprime_group_case_full_original.db"
    if PRIOR_FULL.is_file():
        conn = sqlite3.connect(f"file:{PRIOR_FULL}?mode=ro", uri=True)
        n_prior = int(conn.execute("SELECT COUNT(*) FROM group_labels WHERE resolved = 1").fetchone()[0])
        conn.close()
    else:
        n_prior = 0
    if n_prior == 258:
        shutil.copy2(PRIOR_FULL, dest)
        before = group_bags(agent, statements, predicates, site_local=False)
        after = group_bags(dest, statements, predicates, site_local=False)
        conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
        accepted = [
            {"query_id": row[0], "expr_id": row[1], "witness_key": str(row[2]), "group_value": row[3]}
            for row in conn.execute(
                "SELECT provenance, expr_id, witness_key, group_value FROM group_labels WHERE resolved = 1"
            )
        ]
        conn.close()
        changed = [qid for qid, bag in after.items() if bag != before.get(qid)]
        dest_conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
        checksum_ok = base_checksums(dest_conn) == agent_checksums
        dest_conn.close()
        frozen["full_original"] = {
            "dest": str(dest),
            "digest": file_digest(dest),
            "checksums_match_incumbent_base": checksum_ok,
            "n_attempted": 646,
            "n_materialized": 258,
            "n_sql_visible": 258,
            "n_sidecar_rows": 258,
            "n_rolled_back": 388,
            "n_isolation_fail": 0,
            "site_local": False,
            "changed_queries": changed,
            "n_changed_queries": len(changed),
            "focus": {
                qid: {
                    "changed": qid in changed,
                    "matches_frozen_arm": bool(arm_bags) and after.get(qid) == arm_bags.get(qid),
                    "matches_incumbent": after.get(qid) == before.get(qid),
                }
                for qid in FOCUS
            },
            "accepted": accepted,
        }
        print(f"frozen full_original visible=258 changed={len(changed)} checksums={checksum_ok}", flush=True)
    else:
        raise SystemExit("verified full_original artifact missing")

    print("loading gold after freeze", flush=True)
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    gold_conn = _build_in_memory_db(gold)
    gold_tmp = OUT / "artifacts" / "aprime_group_case_gold.db"
    if gold_tmp.exists():
        gold_tmp.unlink()
    shutil.copy2(agent, gold_tmp)
    filled = fill_gold_group_labels(gold_tmp, gold_conn, queries, predicates)
    gconn = sqlite3.connect(f"file:{gold_tmp}?mode=ro", uri=True)
    gold_map = {
        (str(expr), str(key)): value
        for expr, key, value in gconn.execute(
            "SELECT expr_id, witness_key, group_value FROM group_labels WHERE resolved = 1"
        )
    }
    gconn.close()

    cohort_acc: dict[str, list[bool]] = defaultdict(list)
    for item in inspected:
        key = (item["expr_id"], item["witness_key"])
        if key not in gold_map:
            continue
        match = normalize_group(item["proposed"]) == normalize_group(gold_map[key])
        cohort_acc[item["kind"]].append(match)

    arm = json.loads(ARM.read_text()) if ARM.is_file() else {}
    inc_score = arm.get("incumbent_score") or {}
    docetl = json.loads(DOCETL_EVAL.read_text()) if DOCETL_EVAL.is_file() else {}
    docetl_product = (docetl.get("mean_query_score") or {}).get("0.2") or 0.16564255550190216

    scored = {}
    for rule, rec in frozen.items():
        dest = Path(rec["dest"])
        score = _score(test_count, dest, gold, _rewrites(test_count, dest, predicates, rec["site_local"]))
        gold_stable = 0
        for write in rec["accepted"]:
            if (str(write.get("expr_id")), str(write.get("witness_key"))) not in gold_map:
                gold_stable += 1
        per_query = []
        for row in score["per_query"]:
            before = next((item for item in (inc_score.get("per_query") or []) if item["query_id"] == row["query_id"]), {})
            per_query.append(
                {
                    "query_id": row["query_id"],
                    "inc_product": before.get("product"),
                    "arm_product": row["product"],
                    "delta": float(row["product"] or 0) - float(before.get("product") or 0),
                    "inc_f2": before.get("structure_f2"),
                    "arm_f2": row["structure_f2"],
                    "inc_f1": before.get("cell_f1_20"),
                    "arm_f1": row["cell_f1_20"],
                    "changed": row["query_id"] in rec["changed_queries"],
                }
            )
        scored[rule] = {
            **{k: v for k, v in rec.items() if k != "accepted"},
            "n_accepted": len(rec["accepted"]),
            "writes_on_gold_stable_keys": gold_stable,
            "score": {
                "mean_structure_f2": score["mean_structure_f2"],
                "mean_cell_f1_at_0.20": score["mean_cell_f1_at_0.20"],
                "mean_per_query_product": score["mean_per_query_product"],
            },
            "per_query": per_query,
            "test_changed": [row["query_id"] for row in per_query if row["changed"]],
            "focus": rec["focus"],
        }

    official = scored[OFFICIAL_RULE]
    payload = {
        "tokens_spent": 0,
        "qwen_calls": 0,
        "classifier_modified": False,
        "official_rule": OFFICIAL_RULE,
        "n_votes": len(votes),
        "n_inspected": len(inspected),
        "else_unknown": n_unknown,
        "else_all_false": n_all_false,
        "branch_selected": n_branch,
        "n_unknown_else_escape": sum(1 for item in inspected if item["unknown_else_escape"]),
        "n_all_else_escape": sum(1 for item in inspected if item["all_else_escape"]),
        "focus_before_gold": focus,
        "gold_fill_writes": filled.get("n_writes"),
        "label_accuracy_by_cohort": {
            name: {
                "n": len(rows),
                "match": sum(rows),
                "accuracy": (sum(rows) / len(rows)) if rows else None,
            }
            for name, rows in cohort_acc.items()
        },
        "incumbent_score": {
            "mean_structure_f2": inc_score.get("mean_structure_f2"),
            "mean_cell_f1_at_0.20": inc_score.get("mean_cell_f1_at_0.20"),
            "mean_per_query_product": inc_score.get("mean_per_query_product"),
        },
        "frozen_arm_product": FROZEN_ARM_PRODUCT,
        "docetl_product": docetl_product,
        "replays": scored,
        "official": official,
        "official_beats_frozen_arm": official["score"]["mean_per_query_product"] > FROZEN_ARM_PRODUCT + 1e-12,
        "next_arm_should_classify_canonical_keys_once": official["score"]["mean_per_query_product"]
        <= FROZEN_ARM_PRODUCT + 1e-12,
    }
    out = OUT / "group_case_escape.json"
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "official": OFFICIAL_RULE,
                "product": official["score"]["mean_per_query_product"],
                "incumbent": INCUMBENT_PRODUCT,
                "frozen_arm": FROZEN_ARM_PRODUCT,
                "visible": official["n_sql_visible"],
                "changed": official["n_changed_queries"],
                "else_unknown": n_unknown,
                "else_all_false": n_all_false,
                "q13": official["focus"]["med_agg20:q13"],
                "q17": official["focus"]["med_multiagg20:q17"],
                "beats_arm": payload["official_beats_frozen_arm"],
            },
            indent=2,
        )
    )
    print("wrote", out)
    gold_conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
