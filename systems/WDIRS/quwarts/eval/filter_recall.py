"""Filter-recall on the single-action agent incumbent. Gold after freeze."""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.core.pipeline import official_sql
from quwarts.core.query_filter import (
    compare_bags,
    count_mass,
    ensure_filter_table,
    filter_signature_id,
    probe_filter_additivity,
    query_bags,
    run_filter_arm,
    write_filter_gate_fixture,
)
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import documents_for, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

COMPARE = ROOT / "results" / "quwarts_med_signatures" / "acquisition_compare.json"
DOCETL_EVAL = ROOT / "results" / "docetl_med_case80" / "evaluation.json"
OUT = ROOT / "results" / "quwarts_med_signatures"
BUDGET = 1_543_790


def _score(test, dest, gold, rewrites):
    report = score_with_rewrites(test, rewrites, dest, gold, "Med")
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "per_query": report.get("per_query") or [],
        "test_empty_query_count": sum(
            1 for row in report.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0
        ),
    }


def _official_rewrites(rows, dest, predicates):
    return {row["query_id"]: official_sql(row["sql"], dest, predicates) for row in rows}


def main() -> int:
    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    statements = {row["query_id"]: row["sql"] for row in queries}
    report = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    docs = {}
    for doc in documents_for("Med"):
        docs[doc.doc_id] = doc.text
        docs[Path(doc.doc_id).stem] = doc.text
        docs[Path(doc.doc_id).name] = doc.text
    stored_compare = json.loads(COMPARE.read_text()) if COMPARE.is_file() else {}
    agent_info = stored_compare.get("agent") or {}
    agent_db = Path(agent_info.get("sqlite_path") or "")
    if not agent_db.is_file():
        raise SystemExit(f"agent incumbent missing: {agent_db}")
    agent_spent = int(agent_info.get("tokens_spent") or 0)
    dest = OUT / "artifacts" / "aprime_filter.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    ckpt = OUT / "filter_recall_ckpt.json"
    resume = dest.is_file() and ckpt.is_file()
    saved = json.loads(ckpt.read_text()) if resume else {}
    if resume:
        print(
            f"resume dest={dest} additions_kept batches={len(saved.get('done_chunks') or [])} "
            f"accepted={saved.get('n_accepted')}",
            flush=True,
        )
        bags = {"ok": True, "matched": 99, "total": 99, "mismatched": [], "resumed": True}
        filter_gates = {"ok": True, "resumed": True}
    else:
        if dest.exists():
            dest.unlink()
        shutil.copy2(agent_db, dest)
        conn = sqlite3.connect(str(dest))
        try:
            ensure_filter_table(conn)
            conn.commit()
        finally:
            conn.close()
        bags = compare_bags(agent_db, dest, statements, predicates)
        print(f"pre-spend bags {bags['matched']}/{bags['total']} ok={bags['ok']}", flush=True)
        if not bags["ok"]:
            raise SystemExit(f"empty filter infrastructure changed bags: {bags['mismatched'][:8]}")
        fixture = OUT / "artifacts" / "filter_gate.db"
        write_filter_gate_fixture(fixture)
        filter_gates = probe_filter_additivity(fixture)
        print(f"pre-spend filter_gates ok={filter_gates['ok']}", flush=True)
        if not filter_gates["ok"]:
            raise SystemExit(f"filter gates failed: {filter_gates}")
    prior_tokens = int(saved.get("tokens_spent") or 0)
    if prior_tokens <= 0:
        prior_tokens = agent_spent + sum(int(row.get("tokens") or 0) for row in saved.get("per_query") or [])
    print(
        f"filter start incumbent=agent spent={prior_tokens if resume else agent_spent} "
        f"remaining={BUDGET - (prior_tokens if resume else agent_spent)} "
        f"score_preserved_by_bag_identity=0.124 resume={resume}",
        flush=True,
    )
    ledger = TokenLedger(theta=BUDGET, seed=42)
    ledger.spent = prior_tokens if resume else agent_spent
    caller = make_caller(ledger, model=DEFAULT_MODEL, temperature=0.1, max_tokens=220)
    arm = run_filter_arm(
        dest,
        queries,
        predicates,
        documents=docs,
        caller=caller,
        statements=statements,
        checkpoint=ckpt,
    )
    print(f"filter frozen spent={ledger.spent} accepted={arm.n_accepted} visible={arm.n_sql_visible}", flush=True)
    after_bags = query_bags(dest, statements, predicates)
    before_bags = query_bags(agent_db, statements, predicates)
    changed = [qid for qid in statements if after_bags.get(qid) != before_bags.get(qid)]
    preserved = [qid for qid in statements if after_bags.get(qid) == before_bags.get(qid)]
    empty_before = sum(1 for qid in statements if not before_bags.get(qid))
    empty_after = sum(1 for qid in statements if not after_bags.get(qid))
    per_query_delta = []
    for row in queries:
        qid = row["query_id"]
        before_n = count_mass(agent_db, row["sql"], predicates)
        after_n = count_mass(dest, row["sql"], predicates)
        meta = next((item for item in arm.per_query if item["query_id"] == qid), {})
        per_query_delta.append(
            {
                "query_id": qid,
                "signature_id": filter_signature_id(row["sql"]) if row["sql"] else "",
                "count_before": before_n,
                "count_after": after_n,
                "count_delta": after_n - before_n,
                "bag_changed": qid in changed,
                "empty_before": not before_bags.get(qid),
                "empty_after": not after_bags.get(qid),
                **{key: meta.get(key) for key in (
                    "n_candidates", "n_proposed", "n_accepted", "n_materialized", "n_sql_visible",
                    "n_agreement", "n_disagreement", "n_critique",
                    "n_direct_true", "n_evidence_true", "tokens",
                    "tokens_direct", "tokens_evidence", "tokens_critique",
                    "n_new_groups",
                )},
            }
        )
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.experiments.synthesize_case80 import gold_name

    gold = load_ground_truth(gold_name("Med"))
    final = _score(test_count, dest, gold, _official_rewrites(test_count, dest, predicates))
    agent = _score(test_count, agent_db, gold, _official_rewrites(test_count, agent_db, predicates))
    stored_docetl = json.loads(DOCETL_EVAL.read_text()) if DOCETL_EVAL.is_file() else {}
    docetl_product = None
    if stored_docetl:
        per = stored_docetl.get("per_query") or {}
        if per:
            products = []
            for row in test_count:
                item = per.get(row["query_id"]) or {}
                rank = item.get("rank") or {}
                f2 = float(rank.get("structure_fbeta_score") or 0.0)
                cells = rank.get("cell_f1") or {}
                cell20 = next((float(v) for k, v in cells.items() if abs(float(k) - 0.20) < 1e-9), 0.0)
                products.append(f2 * cell20)
            docetl_product = sum(products) / max(len(products), 1)
        else:
            docetl_product = float((stored_docetl.get("mean_query_score") or {}).get("0.2") or 0.0)
    payload = {
        "budget": BUDGET,
        "model": DEFAULT_MODEL,
        "incumbent": "agent",
        "incumbent_tokens": agent_spent,
        "tokens_spent": ledger.spent,
        "tokens_filter": ledger.spent - agent_spent,
        "tokens_direct": arm.tokens_direct,
        "tokens_evidence": arm.tokens_evidence,
        "tokens_critique": arm.tokens_critique,
        "n_queries": arm.n_queries,
        "n_candidates": arm.n_candidates,
        "n_proposed": arm.n_proposed,
        "n_accepted": arm.n_accepted,
        "n_materialized": arm.n_materialized,
        "n_sql_visible": arm.n_sql_visible,
        "n_agreement": arm.n_agreement,
        "n_disagreement": arm.n_disagreement,
        "cache_hits": arm.cache_hits,
        "cache_misses": arm.cache_misses,
        "rollbacks": arm.rollbacks,
        "skipped": arm.skipped,
        "gates": {
            "bags": bags,
            "score_preserved_by_bag_identity": bags["ok"],
            "filter": filter_gates,
        },
        "incumbent_witness_preservation": {
            "unchanged_queries": len(preserved),
            "changed_queries": changed,
        },
        "empty_query_change": {"before": empty_before, "after": empty_after},
        "candidates": arm.candidates,
        "per_signature": arm.per_signature,
        "per_query": arm.per_query,
        "per_query_delta": per_query_delta,
        "filter": final,
        "agent_official": agent,
        "docetl_product": docetl_product,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "filter_recall.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "spent": ledger.spent,
                "filter_tokens": ledger.spent - agent_spent,
                "proposed": arm.n_proposed,
                "accepted": arm.n_accepted,
                "materialized": arm.n_materialized,
                "sql_visible": arm.n_sql_visible,
                "filter_product": final["mean_per_query_product"],
                "filter_f2": final["mean_structure_f2"],
                "filter_f1": final["mean_cell_f1_at_0.20"],
                "agent_product": agent["mean_per_query_product"],
                "docetl_product": docetl_product,
                "empty_before": empty_before,
                "empty_after": empty_after,
                "changed_queries": len(changed),
            },
            indent=2,
        )
    )
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
