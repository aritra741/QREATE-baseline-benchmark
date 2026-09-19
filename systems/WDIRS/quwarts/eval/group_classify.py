"""Isolated group-classification arm. Gold and DocETL after freeze."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

from sqlglot import exp

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.component_oracle import base_checksums, table_schemas
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.core.pipeline import official_sql
from quwarts.core.query_group import (
    apply_official_group,
    extract_group_expressions,
    fill_gold_group_labels,
    group_bags,
    official_bags,
    reaggregate_sql,
    same_sidecar_rewrite,
    traces_reaggregate_ok,
    ensure_group_table,
    run_group_arm,
    _fetch,
)
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.core.workload import parse_sql
from quwarts.experiments.synthesize_case80 import documents_for, gold_name, queries_for, score_with_rewrites
from spp.config_grid import _build_in_memory_db

load_env_file(ROOT / ".env")

COMPARE = ROOT / "results" / "quwarts_med_signatures" / "acquisition_compare.json"
DOCETL_EVAL = ROOT / "results" / "docetl_med_case80" / "evaluation.json"
ORACLE = ROOT / "results" / "quwarts_med_signatures" / "component_oracles.json"
OUT = ROOT / "results" / "quwarts_med_signatures"
BUDGET = 1_543_790
GROUP_CEILING = 0.220496754707281
PRIOR_STEM_CEILING = 0.2355006105006105
POISON_COLS = ("pharmaceutical_form", "administration_route")


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


def _group_rewrites(rows, dest, predicates):
    return {row["query_id"]: apply_official_group(row["sql"], dest, predicates)[0] for row in rows}


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _eligible_report(queries, dest, predicates) -> dict[str, Any]:
    eligible = []
    ineligible = []
    for row in queries:
        official = official_sql(row["sql"], dest, predicates)
        exprs = extract_group_expressions(official) or extract_group_expressions(row["sql"])
        for item in exprs:
            payload = {
                "query_id": row["query_id"],
                "alias": item.alias,
                "expr_id": item.expr_id,
                "sql": item.sql,
                "reason": item.reason,
                "allowed": list(item.allowed),
            }
            if item.eligible:
                eligible.append(payload)
            else:
                ineligible.append(payload)
    return {"eligible": eligible, "ineligible": ineligible}


def pre_spend_gates(agent: Path, queries, test_count, predicates, gold, gold_conn) -> dict:
    statements = {row["query_id"]: row["sql"] for row in queries}
    tmp = Path(tempfile.mkdtemp(prefix="group_gate_"))
    empty = tmp / "empty.db"
    shutil.copy2(agent, empty)
    conn = sqlite3.connect(str(empty))
    ensure_group_table(conn)
    checksums = base_checksums(conn)
    conn.commit()
    conn.close()
    inc = official_bags(agent, statements, predicates)
    empty_bags = group_bags(empty, statements, predicates)
    unused_empty = [qid for qid in statements if inc.get(qid) != empty_bags.get(qid)]
    empty_ok = not unused_empty

    gold_db = tmp / "gold.db"
    shutil.copy2(agent, gold_db)
    gconn = sqlite3.connect(str(gold_db))
    ensure_group_table(gconn)
    gconn.commit()
    before_gold = base_checksums(gconn)
    gconn.close()
    filled = fill_gold_group_labels(gold_db, gold_conn, queries, predicates)
    gold_rewrites = _group_rewrites(test_count, gold_db, predicates)
    gold_score = _score(test_count, gold_db, gold, gold_rewrites)
    gold_product = gold_score["mean_per_query_product"]
    gold_ok = abs(gold_product - GROUP_CEILING) < 1e-9

    reagg_fail = []
    site_fail = []
    g2 = sqlite3.connect(str(gold_db))
    for row in queries:
        rewritten, exprs = apply_official_group(row["sql"], gold_db, predicates)
        if any(item.eligible for item in exprs) and not traces_reaggregate_ok(g2, rewritten):
            reagg_fail.append(row["query_id"])
        if any(item.eligible for item in exprs) and not same_sidecar_rewrite(
            official_sql(row["sql"], gold_db, predicates), exprs
        ):
            site_fail.append(row["query_id"])
    empty_conn = sqlite3.connect(str(empty))
    for row in queries:
        rewritten, exprs = apply_official_group(row["sql"], empty, predicates)
        if any(item.eligible for item in exprs) and not traces_reaggregate_ok(empty_conn, rewritten):
            if row["query_id"] not in reagg_fail:
                reagg_fail.append(row["query_id"] + ":empty")
    empty_conn.close()
    g2.close()

    poisoned = tmp / "poison.db"
    shutil.copy2(agent, poisoned)
    pconn = sqlite3.connect(str(poisoned))
    ensure_group_table(pconn)
    pconn.commit()
    pconn.close()
    used_cols = set()
    for row in queries:
        for item in extract_group_expressions(row["sql"]):
            try:
                for col in parse_sql(item.sql).find_all(exp.Column):
                    if col.name:
                        used_cols.add(col.name.lower())
            except Exception:
                continue
    for table in ("drug", "disease", "institution"):
        cols = [row[1] for row in gold_conn.execute(f'PRAGMA table_info("{table}")')]
        poison = [col for col in cols if col.lower() not in used_cols and col.lower() not in {"id", "doc_id"}]
        for col in poison[:3]:
            gold_conn.execute(f'UPDATE "{table}" SET "{col}" = "POISONED"')
    gold_conn.commit()
    fill_gold_group_labels(poisoned, gold_conn, queries, predicates)
    poison_bags = group_bags(poisoned, statements, predicates)
    gold_bags = group_bags(gold_db, statements, predicates)
    poison_ok = poison_bags == gold_bags
    # restore gold values for later freeze scoring by reloading is the caller's job

    checksum_ok = filled["checksums_ok"] and base_checksums(sqlite3.connect(str(gold_db))) == before_gold
    sqlite3.connect(str(gold_db)).close()
    gates = {
        "empty_identity": {"ok": empty_ok, "mismatched": unused_empty[:12], "matched": 99 - len(unused_empty)},
        "gold_product": {
            "ok": gold_ok,
            "product": gold_product,
            "expected": GROUP_CEILING,
            "score": gold_score,
        },
        "reaggregate": {"ok": not reagg_fail, "failed": reagg_fail[:20], "n_failed": len(reagg_fail)},
        "poison": {"ok": poison_ok},
        "checksums": {"ok": checksum_ok},
        "same_sites": {"ok": not site_fail, "failed": site_fail[:12]},
        "gold_writes": filled["n_writes"],
    }
    gates["ok"] = all(gates[name]["ok"] for name in ("empty_identity", "gold_product", "reaggregate", "poison", "checksums", "same_sites"))
    shutil.rmtree(tmp, ignore_errors=True)
    return gates


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
    agent_spent = int((json.loads(COMPARE.read_text()).get("agent") or {}).get("tokens_spent") or 37718)
    frozen_digest = file_digest(agent)
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    gold_conn = _build_in_memory_db(gold)
    print(f"group pre-spend incumbent={agent} spent={agent_spent}", flush=True)
    gates = pre_spend_gates(agent, queries, test_count, predicates, gold, gold_conn)
    print(json.dumps({k: (v if k != "gold_product" else {**v, "score": {sk: v["score"][sk] for sk in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")}}) for k, v in gates.items() if k != "ok"} | {"ok": gates["ok"]}, default=str), flush=True)
    if not gates["ok"]:
        gold_conn.close()
        raise SystemExit(f"pre-spend group gates failed: { {k: v.get('ok') for k, v in gates.items() if isinstance(v, dict)} }")

    # gold_conn was poisoned during gates; reload
    gold_conn.close()
    gold = load_ground_truth(gold_name("Med"))
    gold_conn = _build_in_memory_db(gold)

    dest = OUT / "artifacts" / "aprime_group.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(agent, dest)
    conn = sqlite3.connect(str(dest))
    ensure_group_table(conn)
    conn.commit()
    conn.close()
    docs = {}
    for doc in documents_for("Med"):
        docs[doc.doc_id] = doc.text
        docs[Path(doc.doc_id).stem] = doc.text
        docs[Path(doc.doc_id).name] = doc.text
    ledger = TokenLedger(theta=BUDGET, seed=42)
    ledger.spent = agent_spent
    caller = make_caller(ledger, model=DEFAULT_MODEL, temperature=0.1, max_tokens=220)
    ckpt = OUT / "group_classify_ckpt.json"
    journal = OUT / "group_votes.jsonl"
    eligibility = _eligible_report(queries, dest, predicates)
    print(
        f"group start eligible={len(eligibility['eligible'])} ineligible={len(eligibility['ineligible'])} "
        f"remaining={ledger.remaining()}",
        flush=True,
    )
    arm = run_group_arm(
        dest,
        queries,
        predicates,
        documents=docs,
        caller=caller,
        statements=statements,
        checkpoint=ckpt,
        vote_journal=journal,
    )
    print(f"group frozen spent={ledger.spent} resolved={arm.n_resolved} visible={arm.n_sql_visible}", flush=True)

    after_bags = group_bags(dest, statements, predicates)
    before_bags = official_bags(agent, statements, predicates)
    changed = [qid for qid in statements if after_bags.get(qid) != before_bags.get(qid)]
    test_changed = [row["query_id"] for row in test_count if row["query_id"] in changed]
    after_digest = file_digest(dest)
    inc_rewrites = {row["query_id"]: official_sql(row["sql"], agent, predicates) for row in test_count}
    inc_score = _score(test_count, agent, gold, inc_rewrites)
    arm_rewrites = _group_rewrites(test_count, dest, predicates)
    arm_score = _score(test_count, dest, gold, arm_rewrites)
    docetl = json.loads(DOCETL_EVAL.read_text()) if DOCETL_EVAL.is_file() else {}
    conn = sqlite3.connect(str(dest))
    visible = int(conn.execute("SELECT COUNT(*) FROM group_labels WHERE resolved = 1").fetchone()[0])
    checksums = base_checksums(conn)
    agent_conn = sqlite3.connect(f"file:{agent}?mode=ro", uri=True)
    agent_checksums = base_checksums(agent_conn)
    agent_conn.close()
    conn.close()

    per_query = []
    for row in arm_score.get("per_query") or []:
        before = next((item for item in inc_score.get("per_query") or [] if item["query_id"] == row["query_id"]), {})
        per_query.append(
            {
                "query_id": row["query_id"],
                "inc_f2": before.get("structure_f2"),
                "inc_f1": before.get("cell_f1_20"),
                "inc_product": before.get("product"),
                "arm_f2": row.get("structure_f2"),
                "arm_f1": row.get("cell_f1_20"),
                "arm_product": float(row.get("structure_f2") or 0) * float(row.get("cell_f1_20") or 0),
                "changed": row["query_id"] in changed,
            }
        )

    payload = {
        "tokens_spent": ledger.spent,
        "qwen_calls": sum(1 for rec in ledger.records),
        "tokens_by_strategy": {
            "direct": arm.tokens_direct,
            "branch": arm.tokens_branch,
            "adjudicator": arm.tokens_adjudicator,
        },
        "frozen_db_written": after_digest != frozen_digest,
        "incumbent": str(agent),
        "dest": str(dest),
        "gates": gates,
        "eligibility": {
            "n_eligible": len(eligibility["eligible"]),
            "n_ineligible": len(eligibility["ineligible"]),
            "ineligible_reasons": eligibility["ineligible"],
            "eligible_head": eligibility["eligible"][:20],
        },
        "arm": {
            "n_eligible_expressions": arm.n_eligible,
            "n_ineligible": arm.n_ineligible,
            "n_witnesses": arm.n_witnesses,
            "n_attempted": arm.n_attempted,
            "n_resolved": arm.n_resolved,
            "n_fallback": arm.n_fallback,
            "n_sql_visible": visible,
            "n_materialized": arm.n_materialized,
            "agreement": arm.agreement,
            "n_direct_branch_agree": arm.n_agreement_direct_branch,
            "n_disagreement": arm.n_disagreement,
            "n_adjudicator": arm.n_adjudicator,
            "labels": arm.labels,
            "cache_hits": arm.cache_hits,
            "cache_misses": arm.cache_misses,
            "retries": arm.retries,
            "rollbacks": arm.rollbacks[:40],
            "expressions": arm.expressions,
        },
        "changed_queries": changed,
        "n_changed_queries": len(changed),
        "test_changed": test_changed,
        "checksums_match_incumbent_base": checksums == agent_checksums,
        "incumbent_score": inc_score,
        "arm_score": {
            "mean_structure_f2": arm_score["mean_structure_f2"],
            "mean_cell_f1_at_0.20": arm_score["mean_cell_f1_at_0.20"],
            "mean_per_query_product": arm_score["mean_per_query_product"],
        },
        "comparators": {
            "incumbent": inc_score["mean_per_query_product"],
            "docetl": (
                docetl.get("mean_per_query_product")
                or (docetl.get("mean_query_score") or {}).get("0.2")
                or docetl.get("product")
                or 0.16564255550190216
            ),
            "isolated_group_ceiling": GROUP_CEILING,
            "prior_stem_key_ceiling": PRIOR_STEM_CEILING,
        },
        "per_query": per_query,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "group_classify.json"
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "product": arm_score["mean_per_query_product"],
                "incumbent": inc_score["mean_per_query_product"],
                "ceiling": GROUP_CEILING,
                "resolved": arm.n_resolved,
                "visible": visible,
                "changed": len(changed),
                "spent": ledger.spent,
                "frozen_written": payload["frozen_db_written"],
            },
            indent=2,
        )
    )
    print("wrote", out)
    gold_conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
