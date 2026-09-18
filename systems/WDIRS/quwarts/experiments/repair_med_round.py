"""Repair round: rewrite-missing, LIKE vocab, join profile, join repair.

Gold is read only in score_step, after each step. Not inside the loop.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.extract import EvidenceStore, StagedExtractor
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import load_env_file, make_caller
from quwarts.core.logical import extend_logical_schema
from quwarts.core.materialize import refresh_coverage_from_sqlite, refresh_schema_from_sqlite
from quwarts.core.models import FrozenPortfolio
from quwarts.core.pipeline import rematerialize_databases, serve_plans
from quwarts.core.repair.detectors import detect_coercion, detect_empty_queries
from quwarts.core.repair.diagnose import diagnose_empty_queries
from quwarts.core.repair.join_profile import profile_join_edges
from quwarts.core.repair.join_repair import repair_join_edges
from quwarts.core.repair.like_vocab import apply_like_vocabulary
from quwarts.core.repair.rewrite_diag import diagnose_rewrite_failures
from quwarts.core.workload import analyze_workload
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import documents_for, gold_name, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

THETA = 7_859_201
RESERVE_FRACTION = 0.10


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def load_portfolio(src: Path, db_dir: Path | None = None) -> FrozenPortfolio:
    manifest = json.loads((src / "artifacts" / "runs" / "manifest.json").read_text())
    fields = {name: manifest[name] for name in FrozenPortfolio.model_fields if name in manifest}
    portfolio = FrozenPortfolio.model_validate(fields)
    if db_dir is not None:
        db = next(db_dir.glob("*.db"), None)
        if db is not None:
            for item in portfolio.databases:
                item.sqlite_path = str(db)
    return portfolio


def publish_sql_and_db(portfolio: FrozenPortfolio, statements: dict[str, str]) -> None:
    portfolio.logical_schema = extend_logical_schema(portfolio.logical_schema, statements.values())
    for config, db in zip(portfolio.configurations, portfolio.databases):
        refresh_schema_from_sqlite(config.schema_, db.sqlite_path)
        db.coverage = refresh_coverage_from_sqlite(db.coverage, db.sqlite_path)


def empty_causes(portfolio, statements, store, workload) -> dict[str, Any]:
    empty = detect_empty_queries(portfolio, statements)
    plans = serve_plans(portfolio, statements)
    diagnoses = diagnose_empty_queries(empty, statements, plans, store=store, workload=workload)
    causes: dict[str, int] = {}
    for item in diagnoses:
        causes[item.cause] = causes.get(item.cause, 0) + 1
    return {"n": len(empty), "ids": empty, "causes": causes}


def score_step(
    label: str,
    portfolio,
    train_rows,
    test_rows,
    train_sql,
    gold,
    ledger,
    detectors_before,
    detectors_after,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    train_plans = serve_plans(portfolio, train_sql)
    test_sql = {row["query_id"]: row["sql"] for row in test_rows}
    test_plans = serve_plans(portfolio, test_sql)
    pred = Path(portfolio.databases[0].sqlite_path)
    test_report = score_with_rewrites(test_rows, test_plans, pred, gold, "Med")
    train_report = score_with_rewrites(train_rows, train_plans, pred, gold, "Med")
    row = {
        "step": label,
        "mean_structure_f2": float(test_report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(test_report),
        "mean_per_query_product": mean_per_query_product(test_report),
        "tokens_spent": ledger.spent,
        "theta": ledger.theta,
        "train_empty": sum(1 for item in train_report.get("per_query") or [] if int(item.get("pred_rows") or 0) == 0),
        "test_empty": sum(1 for item in test_report.get("per_query") or [] if int(item.get("pred_rows") or 0) == 0),
        "detectors_before": detectors_before,
        "detectors_after": detectors_after,
        "train_rewrite_failures": train_report.get("rewrite_failures"),
        "test_rewrite_failures": test_report.get("rewrite_failures"),
    }
    if extra:
        row.update(extra)
    print(json.dumps({k: row[k] for k in row if k not in {"detectors_before", "detectors_after"}}, indent=2), flush=True)
    return {**row, "test_report": test_report, "train_report": train_report}


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "quwarts_med_repair80_diag"
    typed = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "results" / "quwarts_med_typefix80"
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "results" / "quwarts_med_repair_round"
    out.mkdir(parents=True, exist_ok=True)
    db_dir = out / "artifacts" / "databases"
    db_dir.mkdir(parents=True, exist_ok=True)

    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    train_sql = {row["query_id"]: row["sql"] for row in train}
    documents = documents_for("Med")
    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Med"))

    spent0 = int(json.loads((src / "report.json").read_text()).get("tokens_spent") or 0)
    ledger = TokenLedger(theta=THETA, seed=42)
    ledger.spent = min(spent0, ledger.theta)
    reserve = max(2000, int(ledger.theta * RESERVE_FRACTION))
    caller = make_caller(ledger)
    store = EvidenceStore(src / "artifacts" / "evidence")
    portfolio = load_portfolio(src, typed / "artifacts" / "databases")
    logical, workload = analyze_workload(train_sql, portfolio.logical_schema)

    # --- Step 1: rewrite-missing diagnosis, then publish AST/DB columns ---
    plans = serve_plans(portfolio, train_sql)
    missing = [qid for qid in train_sql if not (plans.get(qid) or {}).get("sql")]
    rewrite_diag = diagnose_rewrite_failures(missing, train_sql, portfolio, workload)
    genuine = [row for row in rewrite_diag if "coverage_rejected" in row.get("reasons", []) and "absent_from_L" not in row.get("reasons", [])]
    false_neg = [row for row in rewrite_diag if "absent_from_L" in row.get("reasons", []) or "identifier_unbound" in row.get("reasons", [])]
    (out / "step1_rewrite_diag.json").write_text(json.dumps({
        "n_missing": len(missing),
        "genuine_coverage": len(genuine),
        "false_negative_L": len(false_neg),
        "rows": rewrite_diag,
        "containment": "interval; LIKE/string presence is not literal lookup",
    }, indent=2, default=str))
    print(json.dumps({
        "step": "1-diagnose",
        "n_missing": len(missing),
        "false_negative_L": len(false_neg),
        "genuine_coverage": len(genuine),
        "reasons": [row.get("reasons") for row in rewrite_diag],
    }, indent=2), flush=True)

    publish_sql_and_db(portfolio, train_sql)
    logical, workload = analyze_workload(train_sql, portfolio.logical_schema)
    before = empty_causes(portfolio, train_sql, store, workload)
    after_s1 = empty_causes(portfolio, train_sql, store, workload)
    scores = []
    scores.append(score_step(
        "1-publish", portfolio, train, test, train_sql, gold, ledger, before, after_s1,
        extra={"rewrite_diag": {"false_negative_L": len(false_neg), "genuine_coverage": len(genuine)}},
    ))

    if ledger.remaining() <= reserve:
        _write(out, scores, after_s1, stopped="reserve")
        return 0

    # --- Step 2: LIKE vocabulary ---
    like_report = apply_like_vocabulary(list(store.records.values()), workload, caller)
    extractor = StagedExtractor(store=store, ledger=ledger, caller=caller, seed=42, workers=4)
    databases = rematerialize_databases(
        store=store, workload=workload, documents=documents,
        configs=portfolio.configurations, db_dir=db_dir, ledger=ledger,
        identity_report={}, overwrite=True,
    )
    portfolio.databases[:] = databases
    publish_sql_and_db(portfolio, train_sql)
    after_s2 = empty_causes(portfolio, train_sql, store, workload)
    scores.append(score_step(
        "2-like", portfolio, train, test, train_sql, gold, ledger, after_s1, after_s2,
        extra={"like": like_report},
    ))
    (out / "step2_like.json").write_text(json.dumps(like_report, indent=2, default=str))

    # --- Step 3: join profile, no repair ---
    profile = profile_join_edges(
        workload, portfolio.databases[0].sqlite_path, train_sql, after_s2["ids"],
    )
    (out / "step3_join_profile.json").write_text(json.dumps(profile, indent=2, default=str))
    print(json.dumps({
        "step": "3-profile",
        "n_edges": len(profile),
        "top": [
            {
                "left": row["left"], "right": row["right"],
                "n_empty": row["n_empty"], "exact_yield": row["exact_yield"],
                "canonical_yield": row["canonical_yield"],
                "n_left": row["n_left"], "n_right": row["n_right"],
                "functions": row["functions"],
            }
            for row in profile[:6]
        ],
    }, indent=2), flush=True)
    scores.append(score_step(
        "3-profile", portfolio, train, test, train_sql, gold, ledger, after_s2, after_s2,
        extra={"n_edges": len(profile)},
    ))

    if ledger.remaining() <= reserve:
        _write(out, scores, after_s2, stopped="reserve", profile=profile)
        return 0

    # --- Step 4: join repair ---
    join_report = repair_join_edges(
        list(store.records.values()), workload, caller, profile,
        extractor=extractor, documents=documents, logical=logical,
    )
    databases = rematerialize_databases(
        store=store, workload=workload, documents=documents,
        configs=portfolio.configurations, db_dir=db_dir, ledger=ledger,
        identity_report=join_report, overwrite=True,
    )
    portfolio.databases[:] = databases
    publish_sql_and_db(portfolio, train_sql)
    after_s4 = empty_causes(portfolio, train_sql, store, workload)
    scores.append(score_step(
        "4-join", portfolio, train, test, train_sql, gold, ledger, after_s2, after_s4,
        extra={"join_repair": {k: join_report.get(k) for k in ("n_aligned", "n_reextracted", "shared_er")}},
    ))
    _write(out, scores, after_s4, stopped="done", profile=profile)
    return 0


def _write(out: Path, scores: list[dict[str, Any]], empties: dict[str, Any], **extra: Any) -> None:
    slim = []
    for row in scores:
        slim.append({k: v for k, v in row.items() if k not in {"test_report", "train_report"}})
        (out / f"{row['step']}_test_report.json").write_text(
            json.dumps(row.get("test_report") or {}, indent=2, default=str)
        )
    payload = {"steps": slim, "final_empty": empties, **extra}
    (out / "round_report.json").write_text(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
