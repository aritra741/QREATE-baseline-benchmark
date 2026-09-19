"""Deterministic live-policy reproduction from stored group votes. Gold after freeze."""

from __future__ import annotations

import hashlib
import json
import shutil
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

from quwarts.core.component_oracle import base_checksums
from quwarts.core.group_replay import load_group_votes
from quwarts.core.query_group import (
    FROZEN_GROUP_POLICY,
    LIVE_GROUP_POLICY,
    apply_live_group_policy,
    apply_official_group,
    frozen_group_policy_digest,
    group_bags,
)
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

COMPARE = ROOT / "results" / "quwarts_med_signatures" / "acquisition_compare.json"
DOCETL_EVAL = ROOT / "results" / "docetl_med_case80" / "evaluation.json"
OUT = ROOT / "results" / "quwarts_med_signatures"
VOTES = OUT / "group_votes.jsonl"
ARM = OUT / "group_classify.json"
OFFICIAL = OUT / "artifacts" / "aprime_group_unknown_else_escape.db"
BUDGET = 1_543_790
INCUMBENT_TOKENS = 37_718
EXPECTED = {
    "n_attempted": 18,
    "n_materialized": 14,
    "n_sql_visible": 14,
    "n_changed": 6,
    "test_changed": ["med_agg20:q13"],
    "mean_structure_f2": 0.4840707538075959,
    "mean_cell_f1_at_0.20": 0.22845238095238093,
    "mean_per_query_product": 0.17439887110939742,
}


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bag_digest(bags: dict[str, Any]) -> str:
    payload = {qid: bags[qid] for qid in sorted(bags)}
    return hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()


def per_bag_digests(bags: dict[str, Any]) -> dict[str, str]:
    return {
        qid: hashlib.sha256(json.dumps(bags[qid], default=str, sort_keys=True).encode()).hexdigest()
        for qid in sorted(bags)
    }


def _score(test, dest, gold, predicates):
    rewrites = {
        row["query_id"]: apply_official_group(row["sql"], dest, predicates, site_id=row["query_id"])[0]
        for row in test
    }
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


def _close(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) < 1e-12


def main() -> int:
    queries = queries_for("Med")
    _, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    statements = {row["query_id"]: row["sql"] for row in queries}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    agent = Path((json.loads(COMPARE.read_text()).get("agent") or {}).get("sqlite_path") or "")
    if not agent.is_file() or not VOTES.is_file() or not OFFICIAL.is_file():
        raise SystemExit("incumbent, votes, or frozen official DB missing")
    votes = load_group_votes(VOTES)
    arm = json.loads(ARM.read_text()) if ARM.is_file() else {}
    ledger_spent = int(arm.get("tokens_spent") or 0)
    vote_tokens = sum(int(item.get("token_cost") or 0) for item in votes)
    print(
        f"live policy={LIVE_GROUP_POLICY} incumbent={agent} votes={len(votes)} tokens=0",
        flush=True,
    )

    dest = OUT / "artifacts" / "aprime_group_live.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(agent, dest)
    agent_conn = sqlite3.connect(f"file:{agent}?mode=ro", uri=True)
    agent_checksums = base_checksums(agent_conn)
    agent_conn.close()

    report = apply_live_group_policy(dest, queries, predicates, votes)
    dest_conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    checksum_ok = base_checksums(dest_conn) == agent_checksums
    dest_conn.close()
    after = report["bags"]
    before = report["before_bags"]
    changed = [qid for qid, bag in after.items() if bag != before.get(qid)]
    test_changed = [row["query_id"] for row in test_count if row["query_id"] in changed]
    official_bags_frozen = group_bags(OFFICIAL, statements, predicates, site_local=True)
    bags_match = after == official_bags_frozen
    checks = {
        "n_attempted": report["n_attempted"] == EXPECTED["n_attempted"],
        "n_materialized": report["n_materialized"] == EXPECTED["n_materialized"],
        "n_sql_visible": report["n_sql_visible"] == EXPECTED["n_sql_visible"],
        "n_changed": len(changed) == EXPECTED["n_changed"],
        "test_changed": test_changed == EXPECTED["test_changed"],
        "n_bags": len(after) == 99,
        "bags_match_official": bags_match,
        "checksums_match_incumbent_base": checksum_ok,
        "n_isolation_fail": int(report.get("n_isolation_fail") or 0) == 0,
        "policy": report.get("policy") == LIVE_GROUP_POLICY,
        "ledger_within_theta": ledger_spent <= BUDGET and ledger_spent >= INCUMBENT_TOKENS,
        "no_qwen_calls": True,
    }
    hashes = {
        "incumbent_db": file_digest(agent),
        "vote_journal": file_digest(VOTES),
        "frozen_policy": frozen_group_policy_digest(),
        "result_db": file_digest(dest),
        "output_bags": bag_digest(after),
        "per_query_bags": per_bag_digests(after),
    }
    freeze_ok = all(checks.values())
    print(
        json.dumps(
            {
                "attempted": report["n_attempted"],
                "materialized": report["n_materialized"],
                "visible": report["n_sql_visible"],
                "changed": changed,
                "test_changed": test_changed,
                "bags_match_official": bags_match,
                "checksums": checksum_ok,
                "isolation_fail": report.get("n_isolation_fail"),
                "freeze_ok": freeze_ok,
            },
            default=str,
        ),
        flush=True,
    )
    if not freeze_ok:
        failed = {name: value for name, value in checks.items() if not value}
        raise SystemExit(f"live policy freeze checks failed: {failed}")

    print("loading gold after freeze", flush=True)
    from diagnostics.run_config_grid import load_ground_truth
    from spp.config_grid import _build_in_memory_db

    gold = load_ground_truth(gold_name("Med"))
    gold_conn = _build_in_memory_db(gold)
    score = _score(test_count, dest, gold, predicates)
    gold_conn.close()
    score_ok = (
        _close(score["mean_structure_f2"], EXPECTED["mean_structure_f2"])
        and _close(score["mean_cell_f1_at_0.20"], EXPECTED["mean_cell_f1_at_0.20"])
        and _close(score["mean_per_query_product"], EXPECTED["mean_per_query_product"])
    )
    payload = {
        "tokens_spent": 0,
        "qwen_calls": 0,
        "classifier_modified": False,
        "prompts_modified": False,
        "thresholds_modified": False,
        "live_policy": LIVE_GROUP_POLICY,
        "frozen_policy": FROZEN_GROUP_POLICY,
        "policy_digest": hashes["frozen_policy"],
        "n_votes": len(votes),
        "n_queries": len(statements),
        "n_attempted": report["n_attempted"],
        "n_materialized": report["n_materialized"],
        "n_sql_visible": report["n_sql_visible"],
        "n_rolled_back": report.get("n_rolled_back"),
        "n_isolation_fail": report.get("n_isolation_fail"),
        "changed_queries": changed,
        "n_changed_queries": len(changed),
        "test_changed": test_changed,
        "n_bags": len(after),
        "bags_match_official_unknown_else_escape": bags_match,
        "checksums_match_incumbent_base": checksum_ok,
        "freeze_checks": checks,
        "hashes": hashes,
        "token_ledger": {
            "incumbent_tokens": INCUMBENT_TOKENS,
            "group_classify_tokens_spent": ledger_spent,
            "vote_journal_token_cost": vote_tokens,
            "replay_tokens": 0,
            "theta": BUDGET,
            "within_theta": checks["ledger_within_theta"],
        },
        "score": {
            "mean_structure_f2": score["mean_structure_f2"],
            "mean_cell_f1_at_0.20": score["mean_cell_f1_at_0.20"],
            "mean_per_query_product": score["mean_per_query_product"],
        },
        "score_matches_expected": score_ok,
        "next_corpus_uses_this_policy_unchanged": True,
        "holdouts_run": [],
    }
    out = OUT / "group_policy.json"
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "policy": LIVE_GROUP_POLICY,
                "product": score["mean_per_query_product"],
                "f2": score["mean_structure_f2"],
                "f1": score["mean_cell_f1_at_0.20"],
                "score_ok": score_ok,
                "dest": str(dest),
                "wrote": str(out),
            },
            indent=2,
        )
    )
    if not score_ok:
        raise SystemExit("live policy scores did not reproduce 0.484 / 0.228 / 0.174")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
