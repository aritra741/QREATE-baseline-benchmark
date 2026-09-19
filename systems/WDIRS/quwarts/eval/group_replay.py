"""Zero-token selective replay of frozen group-classification decisions."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.component_oracle import base_checksums
from quwarts.core.group_replay import (
    OFFICIAL_RULE,
    RULES,
    direct_branch_agree,
    is_sql_null,
    load_group_votes,
    official_row_bags,
    replay_group_rule,
    strategy_ran,
    vote_resolved,
)
from quwarts.core.pipeline import official_sql
from quwarts.core.query_group import apply_official_group, extract_group_expressions, fill_gold_group_labels
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
FOCUS = ("med_agg20:q13", "med_multiagg20:q17")
DOCETL_PRODUCT = 0.16564255550190216


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


def _uses_expr(queries, dest, predicates) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for row in queries:
        official = official_sql(row["sql"], dest, predicates)
        for expr in extract_group_expressions(official) or extract_group_expressions(row["sql"]):
            if expr.eligible:
                out[expr.expr_id].add(row["query_id"])
    return out


def _cohorts(vote: dict[str, Any], empty_queries: set[str]) -> list[str]:
    names = []
    if direct_branch_agree(vote):
        names.append("direct_branch")
    if vote.get("agreement") == "majority" or strategy_ran(vote, "adjudicator"):
        names.append("adjudicator_resolved")
    if is_sql_null(vote.get("group_value")):
        names.append("model_null")
    else:
        names.append("non_null")
    if str(vote.get("query_id") or "") in empty_queries:
        names.append("incumbent_empty")
    else:
        names.append("incumbent_nonempty")
    return names


def _label_accuracy(
    votes: list[dict[str, Any]],
    gold_map: dict[tuple[str, str], Any],
    empty_queries: set[str],
) -> dict[str, Any]:
    buckets: dict[str, list[bool]] = defaultdict(list)
    for vote in votes:
        if not vote_resolved(vote):
            continue
        key = (str(vote.get("expr_id")), str(vote.get("witness_key")))
        gold = gold_map.get(key)
        if key not in gold_map:
            continue
        match = normalize_group(vote.get("group_value")) == normalize_group(gold)
        for name in _cohorts(vote, empty_queries):
            buckets[name].append(match)
    return {
        name: {
            "n": len(rows),
            "match": sum(rows),
            "accuracy": (sum(rows) / len(rows)) if rows else None,
        }
        for name, rows in buckets.items()
    }


def main() -> int:
    queries = queries_for("Med")
    _, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    statements = {row["query_id"]: row["sql"] for row in queries}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    agent = Path((json.loads(COMPARE.read_text()).get("agent") or {}).get("sqlite_path") or "")
    if not agent.is_file():
        raise SystemExit(f"agent incumbent missing: {agent}")
    if not VOTES.is_file():
        raise SystemExit(f"group votes missing: {VOTES}")
    agent_digest = file_digest(agent)
    votes = load_group_votes(VOTES)
    print(f"group replay incumbent={agent} votes={len(votes)} tokens=0", flush=True)

    incumbent = official_row_bags(agent, statements, predicates)
    empty_queries = {qid for qid, row in incumbent.items() if row["empty"]}
    focus = {qid: {"empty": qid in empty_queries, "n_rows": incumbent[qid]["n_rows"]} for qid in FOCUS}
    print(json.dumps({"incumbent_empty_queries": sorted(empty_queries), "focus": focus}), flush=True)

    uses = _uses_expr(queries, agent, predicates)
    agent_conn = sqlite3.connect(f"file:{agent}?mode=ro", uri=True)
    agent_checksums = base_checksums(agent_conn)
    agent_conn.close()

    frozen: dict[str, dict[str, Any]] = {}
    for rule in RULES:
        dest = OUT / "artifacts" / f"aprime_group_{rule}.db"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.unlink()
        shutil.copy2(agent, dest)
        assert file_digest(dest) == agent_digest
        report = replay_group_rule(dest, statements, predicates, votes, rule, empty_queries, uses)
        dest_conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
        checksum_ok = base_checksums(dest_conn) == agent_checksums
        dest_conn.close()
        changed = [qid for qid, bag in report["bags"].items() if bag != report["before_bags"].get(qid)]
        filled_empty = [
            qid for qid in empty_queries if len(report["bags"].get(qid) or ()) > 0
        ]
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
            "site_local": report["site_local"],
            "changed_queries": changed,
            "n_changed_queries": len(changed),
            "empty_bags_filled": filled_empty,
            "n_empty_bags_filled": len(filled_empty),
            "n_count_mass_changed": len(changed),
            "accepted": [
                {
                    "query_id": vote.get("query_id"),
                    "expr_id": vote.get("expr_id"),
                    "witness_key": str(vote.get("witness_key")),
                    "group_value": vote.get("group_value"),
                    "old_label": vote.get("old_label"),
                    "agreement": vote.get("agreement"),
                }
                for vote in report["accepted"]
            ],
        }
        print(
            f"frozen {rule} attempted={report['n_attempted']} visible={report['n_sql_visible']} "
            f"changed={len(changed)} filled={len(filled_empty)} checksums={checksum_ok}",
            flush=True,
        )

    print("loading gold after freeze", flush=True)
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    gold_conn = _build_in_memory_db(gold)
    gold_tmp = OUT / "artifacts" / "aprime_group_gold_fill.db"
    if gold_tmp.exists():
        gold_tmp.unlink()
    shutil.copy2(agent, gold_tmp)
    filled = fill_gold_group_labels(gold_tmp, gold_conn, queries, predicates)
    gconn = sqlite3.connect(f"file:{gold_tmp}?mode=ro", uri=True)
    gold_rows = gconn.execute(
        "SELECT expr_id, witness_key, group_value FROM group_labels WHERE resolved = 1"
    ).fetchall()
    gconn.close()
    gold_map = {(str(expr), str(key)): value for expr, key, value in gold_rows}
    gold_needed = set(gold_map)

    arm = json.loads(ARM.read_text()) if ARM.is_file() else {}
    inc_score = (arm.get("incumbent_score") or {})
    docetl = json.loads(DOCETL_EVAL.read_text()) if DOCETL_EVAL.is_file() else {}
    docetl_product = (
        (docetl.get("mean_query_score") or {}).get("0.2")
        or docetl.get("mean_per_query_product")
        or DOCETL_PRODUCT
    )

    scored = {}
    for rule in RULES:
        dest = Path(frozen[rule]["dest"])
        site_local = frozen[rule]["site_local"]
        rewrites = _rewrites(test_count, dest, predicates, site_local)
        score = _score(test_count, dest, gold, rewrites)
        per_query = []
        for row in score["per_query"]:
            before = next(
                (item for item in (inc_score.get("per_query") or []) if item["query_id"] == row["query_id"]),
                {},
            )
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
                    "incumbent_empty": row["query_id"] in empty_queries,
                    "changed": row["query_id"] in frozen[rule]["changed_queries"],
                }
            )
        gold_no_change = 0
        for vote in frozen[rule]["accepted"]:
            key = (str(vote["expr_id"]), str(vote["witness_key"]))
            if key not in gold_needed:
                gold_no_change += 1
        scored[rule] = {
            **{k: v for k, v in frozen[rule].items() if k != "accepted"},
            "n_accepted": len(frozen[rule]["accepted"]),
            "writes_on_gold_stable_keys": gold_no_change,
            "score": {
                "mean_structure_f2": score["mean_structure_f2"],
                "mean_cell_f1_at_0.20": score["mean_cell_f1_at_0.20"],
                "mean_per_query_product": score["mean_per_query_product"],
            },
            "per_query": per_query,
            "test_changed": [row["query_id"] for row in per_query if row["changed"]],
            "focus": {
                qid: next((row for row in per_query if row["query_id"] == qid), {"query_id": qid})
                for qid in FOCUS
            },
        }

    payload = {
        "tokens_spent": 0,
        "qwen_calls": 0,
        "classifier_modified": False,
        "incumbent": str(agent),
        "votes": str(VOTES),
        "n_votes": len(votes),
        "official_rule": OFFICIAL_RULE,
        "focus_incumbent_empty": focus,
        "n_incumbent_empty": len(empty_queries),
        "incumbent_empty_queries": sorted(empty_queries),
        "incumbent_empty_test": [row["query_id"] for row in test_count if row["query_id"] in empty_queries],
        "gold_fill_writes": filled.get("n_writes"),
        "gold_unique_keys": len(gold_map),
        "label_accuracy_by_cohort": _label_accuracy(votes, gold_map, empty_queries),
        "incumbent_score": {
            "mean_structure_f2": inc_score.get("mean_structure_f2"),
            "mean_cell_f1_at_0.20": inc_score.get("mean_cell_f1_at_0.20"),
            "mean_per_query_product": inc_score.get("mean_per_query_product"),
        },
        "docetl_product": docetl_product,
        "frozen_arm_product": (arm.get("arm_score") or {}).get("mean_per_query_product"),
        "replays": scored,
        "official": scored[OFFICIAL_RULE],
    }
    official = scored[OFFICIAL_RULE]
    q13 = official["focus"]["med_agg20:q13"]
    q17 = official["focus"]["med_multiagg20:q17"]
    nonempty_regressed = [
        row
        for row in official["per_query"]
        if not row["incumbent_empty"] and float(row["delta"] or 0) < -1e-12
    ]
    preserved_gains = (
        focus["med_agg20:q13"]["empty"]
        and focus["med_multiagg20:q17"]["empty"]
        and float(q13.get("delta") or 0) > 0
        and float(q17.get("delta") or 0) > 0
        and not nonempty_regressed
    )
    payload["official_preserves_q13_q17_without_nonempty_regression"] = preserved_gains
    payload["official_vs_docetl"] = (
        {
            "official_product": official["score"]["mean_per_query_product"],
            "docetl_product": docetl_product,
            "delta": official["score"]["mean_per_query_product"] - float(docetl_product),
        }
        if preserved_gains
        else None
    )
    out = OUT / "group_replay.json"
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "official": OFFICIAL_RULE,
                "product": official["score"]["mean_per_query_product"],
                "incumbent": inc_score.get("mean_per_query_product"),
                "docetl": docetl_product,
                "visible": official["n_sql_visible"],
                "changed": official["n_changed_queries"],
                "q13_empty": focus["med_agg20:q13"]["empty"],
                "q17_empty": focus["med_multiagg20:q17"]["empty"],
                "preserved_gains": preserved_gains,
            },
            indent=2,
        )
    )
    print("wrote", out)
    gold_conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
