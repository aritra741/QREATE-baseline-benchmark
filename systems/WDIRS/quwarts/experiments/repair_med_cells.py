"""Canonical/blocking checks, then amp-weighted multi-route cell repair."""

from __future__ import annotations

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

from quwarts.core.amplify import attach_amplification
from quwarts.core.extract import EvidenceStore, StagedExtractor
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import load_env_file, make_caller
from quwarts.core.logical import extend_logical_schema
from quwarts.core.materialize import refresh_coverage_from_sqlite, refresh_schema_from_sqlite
from quwarts.core.models import FrozenPortfolio
from quwarts.core.pilot import estimate_stats
from quwarts.core.pipeline import rematerialize_databases, serve_plans, _canonical_columns, _join_aware_sql
from quwarts.core.quality import high_amp_cell_attributes, vote_amplified
from quwarts.core.repair.er import resolve_shared_ids, stamp_shared_ids
from quwarts.core.repair.join_profile import blocking_admission, profile_join_edges
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import documents_for, gold_name, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

THETA = 7_859_201
RESERVE_FRACTION = 0.10


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def cell_f1_by_attribute(report: dict[str, Any], workload) -> dict[str, float]:
    by_stmt = {
        stmt_id: template
        for template in workload.templates
        for stmt_id in template.statement_ids
    }
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in report.get("per_query") or []:
        cell = row.get("cell_f1_20")
        if cell is None:
            continue
        template = by_stmt.get(row.get("query_id"))
        if template is None:
            continue
        names = set(template.aggregated_attributes) | set(template.group_attributes)
        for name in names:
            buckets[name].append(float(cell))
    return {name: _mean(values) for name, values in sorted(buckets.items())}


def score_bundle(portfolio, train, test, train_sql, gold, workload, ledger) -> dict[str, Any]:
    test_sql = {row["query_id"]: row["sql"] for row in test}
    test_report = score_with_rewrites(test, serve_plans(portfolio, test_sql), Path(portfolio.databases[0].sqlite_path), gold, "Med")
    train_report = score_with_rewrites(train, serve_plans(portfolio, train_sql), Path(portfolio.databases[0].sqlite_path), gold, "Med")
    _, test_workload = analyze_workload(test_sql, None)
    _ = workload
    return {
        "mean_structure_f2": float(test_report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(test_report),
        "mean_per_query_product": mean_per_query_product(test_report),
        "tokens_spent": ledger.spent,
        "train_empty": sum(1 for row in train_report.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0),
        "test_empty": sum(1 for row in test_report.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0),
        "cell_f1_by_attribute": cell_f1_by_attribute(test_report, test_workload),
        "test_report": test_report,
    }


def publish(portfolio, statements) -> None:
    portfolio.logical_schema = extend_logical_schema(portfolio.logical_schema, statements.values())
    for config, db in zip(portfolio.configurations, portfolio.databases):
        refresh_schema_from_sqlite(config.schema_, db.sqlite_path)
        db.coverage = refresh_coverage_from_sqlite(db.coverage, db.sqlite_path)


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "quwarts_med_repair80_diag"
    start_db = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "results" / "quwarts_med_repair_round"
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "results" / "quwarts_med_cells"
    out.mkdir(parents=True, exist_ok=True)

    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    train_sql = {row["query_id"]: row["sql"] for row in train}
    documents = documents_for("Med")
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))
    spent0 = int(json.loads((src / "report.json").read_text()).get("tokens_spent") or 0)
    round_path = start_db / "round_report.json"
    if round_path.exists():
        steps = json.loads(round_path.read_text()).get("steps") or []
        if steps:
            spent0 = max(spent0, int((steps[-1] or {}).get("tokens_spent") or 0))
    ledger = TokenLedger(theta=THETA, seed=42)
    ledger.spent = min(spent0, ledger.theta)
    reserve = max(2000, int(ledger.theta * RESERVE_FRACTION))
    caller = make_caller(ledger)
    evidence_dst = out / "artifacts" / "evidence"
    src_ev = src / "artifacts" / "evidence"
    if not evidence_dst.exists():
        shutil.copytree(src_ev, evidence_dst)
    store = EvidenceStore(evidence_dst)

    manifest = json.loads((src / "artifacts" / "runs" / "manifest.json").read_text())
    fields = {name: manifest[name] for name in FrozenPortfolio.model_fields if name in manifest}
    portfolio = FrozenPortfolio.model_validate(fields)
    db = next((start_db / "artifacts" / "databases").glob("*.db"))
    for item in portfolio.databases:
        item.sqlite_path = str(db)
    publish(portfolio, train_sql)
    logical, workload = analyze_workload(train_sql, portfolio.logical_schema)
    estimate_stats(documents, workload, store)
    attach_amplification(workload)

    # --- 1. Does the canonical ID reach the join predicate? ---
    plans = serve_plans(portfolio, train_sql)
    join_sqls = [plan.get("sql") or "" for plan in plans.values() if " join " in (plan.get("sql") or "").lower()]
    n_join = len(join_sqls)
    n_canon = sum(1 for sql in join_sqls if "__canonical" in sql.lower())
    raw = next((sql for sql in train_sql.values() if " join " in sql.lower()), "")
    rewritten = _join_aware_sql(raw, str(db))
    reach = {
        "canonical_columns_in_db": sorted(_canonical_columns(str(db))),
        "n_join_plans": n_join,
        "n_join_plans_with_canonical": n_canon,
        "rewriter_inserts_canonical": "__canonical" in rewritten.lower(),
        "example_on": _on_snippet(rewritten),
    }

    # IDs in the map vs IDs in the two tables
    shared = resolve_shared_ids(list(store.records.values()), workload, None)
    con = sqlite3.connect(db)
    try:
        drug = {row[0]: row[1] for row in con.execute(
            'SELECT disease_name, disease_name__canonical FROM drug WHERE disease_name IS NOT NULL'
        )}
        disease = {row[0]: row[1] for row in con.execute(
            'SELECT disease_name, disease_name__canonical FROM disease WHERE disease_name IS NOT NULL'
        )}
    finally:
        con.close()
    er_map = (shared.get("maps") or {}).get("disease.disease_name") or {}
    stamped_same = 0
    mapped_same = 0
    compared = 0
    for ls, lid in drug.items():
        for rs, rid in disease.items():
            em = er_map.get(ls)
            er = er_map.get(rs)
            if em and er and em == er:
                mapped_same += 1
                compared += 1
                if lid and rid and lid == rid:
                    stamped_same += 1
            elif em or er:
                compared += 1
    reach["er_same_id_pairs"] = mapped_same
    reach["db_same_id_among_er_pairs"] = stamped_same
    reach["stamp_reaches_both_sides"] = bool(mapped_same and stamped_same == mapped_same)
    (out / "step1_canonical_reach.json").write_text(json.dumps(reach, indent=2, default=str))
    print(json.dumps({"step": "1-canonical-reach", **{k: reach[k] for k in reach if k != "example_on"}, "example_on": reach["example_on"][:240]}, indent=2), flush=True)

    # --- 2. Blocking admission ---
    profile = profile_join_edges(workload, str(db), train_sql, [])
    edge = profile[0] if profile else {}
    con = sqlite3.connect(db)
    try:
        left_vals = [row[0] for row in con.execute(
            'SELECT DISTINCT disease_name FROM drug WHERE disease_name IS NOT NULL AND disease_name <> \'\''
        )]
        right_vals = [row[0] for row in con.execute(
            'SELECT DISTINCT disease_name FROM disease WHERE disease_name IS NOT NULL AND disease_name <> \'\''
        )]
    finally:
        con.close()
    admission = blocking_admission(left_vals, right_vals)
    admission["edge"] = {"left": edge.get("left"), "right": edge.get("right")}
    (out / "step2_blocking.json").write_text(json.dumps(admission, indent=2, default=str))
    print(json.dumps({"step": "2-blocking", **admission}, indent=2), flush=True)

    # --- before score ---
    before = score_bundle(portfolio, train, test, train_sql, gold, workload, ledger)
    (out / "before_test_report.json").write_text(json.dumps(before.get("test_report") or {}, indent=2, default=str))
    print(json.dumps({
        "step": "3-before",
        "mean_structure_f2": before["mean_structure_f2"],
        "mean_cell_f1_at_0.20": before["mean_cell_f1_at_0.20"],
        "mean_per_query_product": before["mean_per_query_product"],
        "cell_f1_by_attribute": before["cell_f1_by_attribute"],
        "high_amp": high_amp_cell_attributes(workload),
        "tokens_spent": ledger.spent,
    }, indent=2), flush=True)

    ceiling = max(0, ledger.remaining() - reserve)
    extractor = StagedExtractor(store=store, ledger=ledger, caller=caller, seed=42, workers=4)
    vote = vote_amplified(extractor, documents, workload, ceiling=ceiling)
    (out / "step3_vote.json").write_text(json.dumps(vote, indent=2, default=str))
    print(json.dumps({"step": "3-vote", **{k: vote[k] for k in vote if k != "per_attribute"}, "n_attrs": len(vote.get("per_attribute") or {})}, indent=2), flush=True)

    identity = stamp_shared_ids({}, resolve_shared_ids(list(store.records.values()), workload, None))
    db_dir = out / "artifacts" / "databases"
    db_dir.mkdir(parents=True, exist_ok=True)
    databases = rematerialize_databases(
        store=store, workload=workload, documents=documents,
        configs=portfolio.configurations, db_dir=db_dir, ledger=ledger,
        identity_report=identity, overwrite=True,
    )
    portfolio.databases[:] = databases
    publish(portfolio, train_sql)
    after = score_bundle(portfolio, train, test, train_sql, gold, workload, ledger)
    after_profile = profile_join_edges(workload, portfolio.databases[0].sqlite_path, train_sql, [])
    moved = {
        name: {
            "before": before["cell_f1_by_attribute"].get(name),
            "after": after["cell_f1_by_attribute"].get(name),
        }
        for name in sorted(set(before["cell_f1_by_attribute"]) | set(after["cell_f1_by_attribute"]))
    }
    payload = {
        "canonical_reach": reach,
        "blocking": admission,
        "before": {k: v for k, v in before.items() if k != "test_report"},
        "after": {k: v for k, v in after.items() if k != "test_report"},
        "cell_f1_moved": moved,
        "vote": vote,
        "join_yield_after": [
            {
                "left": row.get("left"),
                "right": row.get("right"),
                "exact_yield": row.get("exact_yield"),
                "canonical_yield": row.get("canonical_yield"),
            }
            for row in after_profile[:8]
        ],
        "tokens_spent": ledger.spent,
        "theta": THETA,
        "reserve": reserve,
    }
    (out / "cell_report.json").write_text(json.dumps(payload, indent=2, default=str))
    (out / "after_test_report.json").write_text(json.dumps(after.get("test_report") or {}, indent=2, default=str))
    print(json.dumps({
        "step": "4-after",
        "mean_structure_f2": after["mean_structure_f2"],
        "mean_cell_f1_at_0.20": after["mean_cell_f1_at_0.20"],
        "mean_per_query_product": after["mean_per_query_product"],
        "cell_f1_by_attribute": after["cell_f1_by_attribute"],
        "moved": {k: v for k, v in moved.items() if v["before"] != v["after"]},
        "tokens_spent": ledger.spent,
        "train_empty": after["train_empty"],
        "test_empty": after["test_empty"],
    }, indent=2), flush=True)
    _ = logical
    return 0


def _on_snippet(sql: str) -> str:
    idx = sql.upper().find(" ON ")
    if idx < 0:
        return sql[:240]
    return sql[idx: idx + 280]


if __name__ == "__main__":
    raise SystemExit(main())
