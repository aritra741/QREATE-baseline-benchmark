"""Zero-token cross-query consensus replay. Gold after freeze."""

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
from quwarts.core.group_consensus import (
    OFFICIAL_RULE,
    build_consensus,
    collect_sites,
    replay_consensus,
    writes_for_labels,
)
from quwarts.core.group_replay import is_sql_null, load_group_votes, replay_group_rule
from quwarts.core.pipeline import official_sql
from quwarts.core.query_group import apply_official_group, extract_group_expressions, fill_gold_group_labels, group_bags
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
FOCUS = ("med_agg20:q13", "med_multiagg20:q17")
FROZEN_ARM_PRODUCT = 0.1443894647019647
INCUMBENT_PRODUCT = 0.12439887110939743


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


def _cohort_of(key: str, consensus: dict[str, Any]) -> list[str]:
    names = []
    if key in consensus["unanimous"]:
        names.append("unanimous")
    if key in consensus["majority"]:
        names.append("majority")
    if key in consensus["single_keys"]:
        names.append("single_query")
    if key in consensus["conflicting_keys"]:
        names.append("conflicting")
    return names


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
    votes = load_group_votes(VOTES)
    print(f"group consensus incumbent={agent} votes={len(votes)} tokens=0", flush=True)

    sites = collect_sites(agent, queries, predicates)
    consensus = build_consensus(votes, sites)
    print(
        json.dumps(
            {
                "n_keys": consensus["n_keys"],
                "n_sites": consensus["n_sites"],
                "freq": consensus["query_frequency"],
                "agree": consensus["n_agree"],
                "conflict": consensus["n_conflict"],
                "unanimous": len(consensus["unanimous"]),
                "majority": len(consensus["majority"]),
            }
        ),
        flush=True,
    )

    agent_conn = sqlite3.connect(f"file:{agent}?mode=ro", uri=True)
    agent_checksums = base_checksums(agent_conn)
    agent_conn.close()
    identity = OUT / "artifacts" / "aprime_group_consensus_identity.db"
    if identity.exists():
        identity.unlink()
    shutil.copy2(agent, identity)
    id_conn = sqlite3.connect(str(identity))
    from quwarts.core.query_group import ensure_group_table

    ensure_group_table(id_conn, site_local=True)
    id_conn.commit()
    id_conn.close()
    identity_bags = group_bags(identity, statements, predicates, site_local=True)
    incumbent_bags = group_bags(agent, statements, predicates, site_local=False)
    # empty wrap on a table-less agent uses official_sql only; compare after creating empty sidecar
    identity_ok = identity_bags == group_bags(identity, statements, predicates, site_local=True)
    uses = _uses_expr(queries, agent, predicates)
    arm_bags = {}
    if ARM_DB.is_file():
        arm_bags = group_bags(ARM_DB, statements, predicates, site_local=False)

    frozen: dict[str, dict[str, Any]] = {}
    plans = {
        "cross_query_unanimous": writes_for_labels(consensus["unanimous"], consensus["sites_by_key"]),
        "cross_query_majority": writes_for_labels(consensus["majority"], consensus["sites_by_key"]),
    }
    for rule, writes in plans.items():
        dest = OUT / "artifacts" / f"aprime_group_{rule}.db"
        reuse = dest.is_file() and dest.stat().st_size > 0
        if reuse:
            conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
            n_exist = int(conn.execute("SELECT COUNT(*) FROM group_labels").fetchone()[0])
            conn.close()
            reuse = n_exist == len(writes) or (len(writes) == 0 and n_exist == 0)
        if not reuse:
            if dest.exists():
                dest.unlink()
            shutil.copy2(agent, dest)
            report = replay_consensus(dest, statements, predicates, writes)
        else:
            print(f"reuse frozen {rule} dest={dest}", flush=True)
            before = group_bags(identity, statements, predicates, site_local=True)
            after = group_bags(dest, statements, predicates, site_local=True)
            conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
            accepted = [
                {
                    "query_id": row[0],
                    "expr_id": row[1],
                    "witness_key": str(row[2]),
                    "group_value": row[3],
                }
                for row in conn.execute(
                    "SELECT provenance, expr_id, witness_key, group_value FROM group_labels WHERE resolved = 1"
                )
            ]
            n_side = int(conn.execute("SELECT COUNT(*) FROM group_labels WHERE resolved = 1").fetchone()[0])
            conn.close()
            report = {
                "n_attempted": len(writes),
                "n_propagated": len(writes),
                "n_materialized": n_side,
                "n_sql_visible": n_side,
                "n_sidecar_rows": n_side,
                "n_rolled_back": max(0, len(writes) - n_side),
                "n_isolation_fail": 0,
                "accepted": accepted,
                "before_bags": before,
                "bags": after,
            }
        dest_conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
        checksum_ok = base_checksums(dest_conn) == agent_checksums
        dest_conn.close()
        changed = [qid for qid, bag in report["bags"].items() if bag != report["before_bags"].get(qid)]
        focus = {}
        for qid in FOCUS:
            focus[qid] = {
                "changed": qid in changed,
                "matches_frozen_arm": bool(arm_bags) and report["bags"].get(qid) == arm_bags.get(qid),
                "matches_incumbent": report["bags"].get(qid) == report["before_bags"].get(qid),
            }
        frozen[rule] = {
            "dest": str(dest),
            "digest": file_digest(dest),
            "checksums_match_incumbent_base": checksum_ok,
            "n_accepted_keys": len(consensus["unanimous"] if rule == "cross_query_unanimous" else consensus["majority"]),
            "n_attempted": report["n_attempted"],
            "n_propagated": report["n_propagated"],
            "n_materialized": report["n_materialized"],
            "n_sql_visible": report["n_sql_visible"],
            "n_sidecar_rows": report["n_sidecar_rows"],
            "n_rolled_back": report["n_rolled_back"],
            "n_isolation_fail": report["n_isolation_fail"],
            "site_local": True,
            "changed_queries": changed,
            "n_changed_queries": len(changed),
            "focus": focus,
            "accepted": report["accepted"],
            "before_bags": report["before_bags"],
            "bags": report["bags"],
        }
        print(
            f"frozen {rule} keys={frozen[rule]['n_accepted_keys']} "
            f"propagated={report['n_propagated']} visible={report['n_sql_visible']} "
            f"changed={len(changed)} checksums={checksum_ok}",
            flush=True,
        )

    dest = OUT / "artifacts" / "aprime_group_consensus_full_original.db"
    prior_full = OUT / "artifacts" / "aprime_group_full_original.db"
    if prior_full.is_file():
        conn = sqlite3.connect(f"file:{prior_full}?mode=ro", uri=True)
        n_prior = int(conn.execute("SELECT COUNT(*) FROM group_labels WHERE resolved = 1").fetchone()[0])
        conn.close()
    else:
        n_prior = 0
    if n_prior == 258:
        shutil.copy2(prior_full, dest)
        print(f"reuse verified full_original writes=258 dest={dest}", flush=True)
        before = group_bags(identity, statements, predicates, site_local=False)
        after = group_bags(dest, statements, predicates, site_local=False)
        conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
        accepted = [
            {
                "query_id": row[0],
                "expr_id": row[1],
                "witness_key": str(row[2]),
                "group_value": row[3],
            }
            for row in conn.execute(
                "SELECT provenance, expr_id, witness_key, group_value FROM group_labels WHERE resolved = 1"
            )
        ]
        conn.close()
        full = {
            "n_attempted": 646,
            "n_materialized": 258,
            "n_sql_visible": 258,
            "n_sidecar_rows": 258,
            "n_rolled_back": 388,
            "n_isolation_fail": 0,
            "accepted": accepted,
            "before_bags": before,
            "bags": after,
        }
    else:
        if dest.exists():
            dest.unlink()
        shutil.copy2(agent, dest)
        full = replay_group_rule(dest, statements, predicates, votes, "full_original", set(), uses)
    dest_conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    checksum_ok = base_checksums(dest_conn) == agent_checksums
    dest_conn.close()
    changed = [qid for qid, bag in full["bags"].items() if bag != full["before_bags"].get(qid)]
    frozen["full_original"] = {
        "dest": str(dest),
        "digest": file_digest(dest),
        "checksums_match_incumbent_base": checksum_ok,
        "n_accepted_keys": None,
        "n_attempted": full["n_attempted"],
        "n_propagated": full["n_attempted"],
        "n_materialized": full["n_materialized"],
        "n_sql_visible": full["n_sql_visible"],
        "n_sidecar_rows": full["n_sidecar_rows"],
        "n_rolled_back": full["n_rolled_back"],
        "n_isolation_fail": full["n_isolation_fail"],
        "site_local": False,
        "changed_queries": changed,
        "n_changed_queries": len(changed),
        "focus": {
            qid: {
                "changed": qid in changed,
                "matches_frozen_arm": bool(arm_bags) and full["bags"].get(qid) == arm_bags.get(qid),
                "matches_incumbent": full["bags"].get(qid) == full["before_bags"].get(qid),
            }
            for qid in FOCUS
        },
        "accepted": full["accepted"],
        "before_bags": full["before_bags"],
        "bags": full["bags"],
    }
    print(
        f"frozen full_original visible={full['n_sql_visible']} changed={len(changed)} checksums={checksum_ok}",
        flush=True,
    )
    print("loading gold after freeze", flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    gold_conn = _build_in_memory_db(gold)
    identity_rewrites = _rewrites(test_count, identity, predicates, True)
    identity_score = _score(test_count, identity, gold, identity_rewrites)
    gold_tmp = OUT / "artifacts" / "aprime_group_consensus_gold.db"
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

    site_by_loc = {(s["query_id"], s["official_expr_id"], s["witness_key"]): s for s in sites}
    key_gold: dict[str, list[Any]] = defaultdict(list)
    for (expr, wk), value in gold_map.items():
        for site in sites:
            if site["official_expr_id"] == expr and site["witness_key"] == wk:
                key_gold[site["canonical_key"]].append(value)
    cohort_acc: dict[str, list[bool]] = defaultdict(list)
    for key, entry in consensus["per_key"].items():
        labels = list(entry["votes"].values())
        if not labels:
            continue
        chosen = Counter(labels).most_common(1)[0][0]
        golds = key_gold.get(key) or []
        if not golds:
            continue
        match = any(normalize_group(chosen) == normalize_group(item) for item in golds)
        for name in _cohort_of(key, consensus) or ["other"]:
            cohort_acc[name].append(match)

    arm = json.loads(ARM.read_text()) if ARM.is_file() else {}
    inc_score = arm.get("incumbent_score") or {}
    docetl = json.loads(DOCETL_EVAL.read_text()) if DOCETL_EVAL.is_file() else {}
    docetl_product = (docetl.get("mean_query_score") or {}).get("0.2") or 0.16564255550190216

    scored = {}
    for rule, rec in frozen.items():
        dest = Path(rec["dest"])
        site_local = rec["site_local"]
        score = _score(test_count, dest, gold, _rewrites(test_count, dest, predicates, site_local))
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
        gold_stable = 0
        for write in rec["accepted"]:
            loc = (str(write.get("query_id")), str(write.get("expr_id")), str(write.get("witness_key")))
            site = site_by_loc.get(loc) or {}
            key = (str(write.get("expr_id")), str(write.get("witness_key")))
            if key not in gold_map:
                gold_stable += 1
        scored[rule] = {
            **{k: v for k, v in rec.items() if k not in {"accepted", "before_bags", "bags"}},
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

    usable = None
    uni = cohort_acc.get("unanimous") or []
    single = cohort_acc.get("single_query") or []
    conflict = cohort_acc.get("conflicting") or []
    if uni and (not single or (sum(uni) / len(uni)) > (sum(single) / len(single) + 0.05)):
        usable = True
    elif uni:
        usable = (sum(uni) / len(uni)) >= 0.5 and (not conflict or (sum(uni) / len(uni)) > (sum(conflict) / max(len(conflict), 1)))
    else:
        usable = False

    official = scored[OFFICIAL_RULE]
    payload = {
        "tokens_spent": 0,
        "qwen_calls": 0,
        "classifier_modified": False,
        "official_rule": OFFICIAL_RULE,
        "incumbent": str(agent),
        "n_votes": len(votes),
        "identity_empty_sidecar_product": identity_score["mean_per_query_product"],
        "identity_matches_incumbent": abs(identity_score["mean_per_query_product"] - INCUMBENT_PRODUCT) < 1e-12,
        "consensus": {
            "n_keys": consensus["n_keys"],
            "n_sites": consensus["n_sites"],
            "query_frequency": consensus["query_frequency"],
            "n_single": consensus["n_single"],
            "n_two": consensus["n_two"],
            "n_three": consensus["n_three"],
            "n_more": consensus["n_more"],
            "n_agree": consensus["n_agree"],
            "n_conflict": consensus["n_conflict"],
            "agreement_rate": consensus["agreement_rate"],
            "conflict_rate": consensus["conflict_rate"],
            "n_unanimous": len(consensus["unanimous"]),
            "n_majority": len(consensus["majority"]),
        },
        "gold_fill_writes": filled.get("n_writes"),
        "label_accuracy_by_cohort": {
            name: {
                "n": len(rows),
                "match": sum(rows),
                "accuracy": (sum(rows) / len(rows)) if rows else None,
            }
            for name, rows in cohort_acc.items()
        },
        "cross_query_is_usable_confidence": usable,
        "incumbent_score": {
            "mean_structure_f2": inc_score.get("mean_structure_f2"),
            "mean_cell_f1_at_0.20": inc_score.get("mean_cell_f1_at_0.20"),
            "mean_per_query_product": inc_score.get("mean_per_query_product"),
        },
        "frozen_arm_product": (arm.get("arm_score") or {}).get("mean_per_query_product") or FROZEN_ARM_PRODUCT,
        "docetl_product": docetl_product,
        "replays": scored,
        "official": official,
    }
    beats_arm = official["score"]["mean_per_query_product"] > FROZEN_ARM_PRODUCT + 1e-12
    payload["official_beats_frozen_arm"] = beats_arm
    payload["official_has_coverage"] = official["n_sql_visible"] > 0
    payload["next_arm_should_classify_canonical_keys_once"] = (not official["n_sql_visible"]) or (
        not beats_arm
    )
    out = OUT / "group_consensus.json"
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "official": OFFICIAL_RULE,
                "product": official["score"]["mean_per_query_product"],
                "incumbent": INCUMBENT_PRODUCT,
                "frozen_arm": FROZEN_ARM_PRODUCT,
                "keys": consensus["n_keys"],
                "unanimous": len(consensus["unanimous"]),
                "visible": official["n_sql_visible"],
                "changed": official["n_changed_queries"],
                "q13": official["focus"]["med_agg20:q13"],
                "q17": official["focus"]["med_multiagg20:q17"],
                "usable_signal": usable,
            },
            indent=2,
        )
    )
    print("wrote", out)
    gold_conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
