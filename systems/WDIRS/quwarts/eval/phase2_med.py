"""Phase 2 A/B. Gold is read only here. Repair and vote stay off."""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.contracts import abstention, compile_contracts
from quwarts.core.extract import EvidenceStore
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.core.models import FrozenPortfolio
from quwarts.core.pipeline import compile_workload, serve_plans
from quwarts.core.repair.detectors import snapshot
from quwarts.core.workload import analyze_workload
from quwarts.eval.cell_errors import classify_cells, is_null, load_sqlite_rows
from quwarts.experiments.player_case80 import execute, split_80_20
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import (
    documents_for,
    gold_name,
    queries_for,
    score_with_rewrites,
)

load_env_file(ROOT / ".env")

THETA = 7_859_201
COMPILE_DIR = ROOT / "results" / "quwarts_med_repair80_diag"
SCORE_DB = next((ROOT / "results" / "quwarts_med_repair_round" / "artifacts" / "databases").glob("*.db"))
MANIFEST = COMPILE_DIR / "artifacts" / "runs" / "manifest.json"
OUT = ROOT / "results" / "quwarts_med_phase2"


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def is_id_name(name: str) -> bool:
    return str(name).split(".")[-1].lower() == "id"


def drop_id_table(table):
    keep = tuple(col for col in table.columns if not is_id_name(col.name))
    if keep == table.columns:
        return table
    rows = tuple(
        {key: value for key, value in row.items() if not is_id_name(key)}
        for row in table.rows
    )
    return replace(table, columns=keep, rows=rows)


def load_arm_a_portfolio(statements: dict[str, str]) -> FrozenPortfolio:
    from quwarts.core.logical import extend_logical_schema
    from quwarts.core.materialize import refresh_coverage_from_sqlite, refresh_schema_from_sqlite

    manifest = json.loads(MANIFEST.read_text())
    fields = {
        name: manifest[name]
        for name in FrozenPortfolio.model_fields
        if name in manifest
    }
    portfolio = FrozenPortfolio.model_validate(fields)
    for item in portfolio.databases:
        item.sqlite_path = str(SCORE_DB)
    portfolio.logical_schema = extend_logical_schema(portfolio.logical_schema, statements.values())
    for config, item in zip(portfolio.configurations, portfolio.databases):
        refresh_schema_from_sqlite(config.schema_, item.sqlite_path)
        item.coverage = refresh_coverage_from_sqlite(item.coverage, item.sqlite_path)
    return portfolio


def score_excluding_ids(
    rows: list[dict[str, str]],
    plans: dict[str, Any],
    pred_db: Path,
    gold_tables: dict[str, list[dict[str, Any]]],
    dataset: str,
) -> dict[str, Any]:
    from spp.aggregation_metrics import (
        MetricConfig,
        evaluate_aggregation_tables,
        gold_table_from_sql,
        predicted_table_from_rows,
        schema_from_sql,
    )
    from spp.config_grid import _build_in_memory_db

    official = score_with_rewrites(rows, plans, pred_db, gold_tables, dataset)
    gold_conn = _build_in_memory_db(gold_tables)
    config = MetricConfig()
    structure: list[float] = []
    cell20: list[float] = []
    products: list[float] = []
    per_query = []
    try:
        for row in rows:
            plan = plans.get(row["query_id"]) or {}
            pred_sql = plan.get("sql") if isinstance(plan, dict) else plan
            path = (plan.get("sqlite_path") if isinstance(plan, dict) else None) or str(pred_db)
            gold_rows = execute(gold_conn, row["sql"])
            pred_rows = []
            if pred_sql:
                local = sqlite3.connect(path)
                try:
                    pred_rows = execute(local, pred_sql)
                finally:
                    local.close()
            schema = schema_from_sql(row["sql"])
            item = {
                "query_id": row["query_id"],
                "gold_rows": len(gold_rows),
                "pred_rows": len(pred_rows),
            }
            if schema.get("is_aggregation") and gold_rows:
                gold = drop_id_table(gold_table_from_sql(gold_rows, row["sql"]))
                pred = drop_id_table(predicted_table_from_rows(pred_rows, gold=gold))
                if gold.columns:
                    metrics = evaluate_aggregation_tables(pred, gold, config=config)
                    f2 = float(metrics["rank"]["structure_fbeta_score"])
                    cmap = metrics["rank"]["cell_f1"]
                    c20 = float(cmap.get(0.2) or cmap.get(0.20) or 0.0)
                    item["structure_f2"] = f2
                    item["cell_f1_20"] = c20
                    item["product"] = f2 * c20
                    structure.append(f2)
                    cell20.append(c20)
                    products.append(f2 * c20)
            per_query.append(item)
    finally:
        gold_conn.close()
    return {
        "official": {
            "mean_structure_f2": float(official.get("mean_structure_f2") or 0.0),
            "mean_cell_f1_at_0.20": mean_cell_f1_20(official),
            "mean_per_query_product": mean_per_query_product(official),
            "empty_query_count": sum(
                1 for row in official.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0
            ),
            "per_query": official.get("per_query"),
        },
        "exclude_id": {
            "mean_structure_f2": _mean(structure),
            "mean_cell_f1_at_0.20": _mean(cell20),
            "mean_per_query_product": _mean(products),
            "n": len(products),
            "per_query": per_query,
        },
        "loss": loss_factors(per_query),
    }


def loss_factors(per_query: list[dict[str, Any]]) -> dict[str, float]:
    struct = [1.0 - float(row.get("structure_f2") or 0.0) for row in per_query if "structure_f2" in row]
    cell = [1.0 - float(row.get("cell_f1_20") or 0.0) for row in per_query if "cell_f1_20" in row]
    interaction = [
        (1.0 - float(row.get("structure_f2") or 0.0)) * (1.0 - float(row.get("cell_f1_20") or 0.0))
        for row in per_query
        if "structure_f2" in row
    ]
    total = [1.0 - float(row.get("product") or 0.0) for row in per_query if "product" in row]
    return {
        "mean_1_minus_structure_f2": _mean(struct),
        "mean_1_minus_cell_f1": _mean(cell),
        "mean_interaction": _mean(interaction),
        "mean_1_minus_product": _mean(total),
    }


def _pred_index(pred_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in pred_rows:
        keys = [row.get("id"), row.get("doc_id")]
        for raw in keys:
            if raw in (None, ""):
                continue
            stem = Path(str(raw)).stem
            index[str(stem)] = row
            try:
                index[str(int(stem))] = row
            except (TypeError, ValueError):
                pass
    return index


def cell_f1_per_attribute(
    gold: dict[str, list[dict[str, Any]]],
    db: Path,
    contracts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    from diagnostics.run_config_grid import load_attributes

    schema = load_attributes(gold_name("Med"))
    per_attr: dict[str, Any] = {}
    totals: dict[str, int] = defaultdict(int)
    con = sqlite3.connect(db)
    try:
        tables = {
            name
            for (name,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
            )
        }
        for table, columns in schema.items():
            names = [col for col in columns if not is_id_name(col)]
            gold_rows = [
                {str(key).lower(): value for key, value in row.items()}
                for row in gold.get(table, [])
            ]
            pred_rows: list[dict[str, Any]] = []
            if table in tables:
                cols = [info[1] for info in con.execute(f"PRAGMA table_info({_q(table)})")]
                for row in con.execute(f"SELECT * FROM {_q(table)}"):
                    pred_rows.append({str(col).lower(): value for col, value in zip(cols, row)})
            index = _pred_index(pred_rows)
            gold_nonnull = defaultdict(int)
            buckets = {name: defaultdict(int) for name in names}
            for grow in gold_rows:
                prow = None
                gid = grow.get("id")
                if gid not in (None, ""):
                    prow = index.get(str(gid)) or index.get(str(gid).lstrip("0") or str(gid))
                    try:
                        prow = prow or index.get(str(int(gid)))
                    except (TypeError, ValueError):
                        pass
                for name in names:
                    gv = grow.get(name)
                    if not is_null(gv):
                        gold_nonnull[name] += 1
                    if prow is None:
                        buckets[name]["entity_miss"] += 1
                    elif is_null(gv):
                        buckets[name][
                            "gold_null_pred_null" if is_null(prow.get(name)) else "gold_null_pred_filled"
                        ] += 1
                    elif is_null(prow.get(name)):
                        buckets[name]["not_found"] += 1
                    else:
                        from quwarts.eval.cell_errors import exact_match, _near_norm

                        if exact_match(gv, prow.get(name)):
                            buckets[name]["exact"] += 1
                        elif _near_norm(gv) == _near_norm(prow.get(name)) and _near_norm(gv):
                            buckets[name]["near_miss"] += 1
                        else:
                            buckets[name]["wrong"] += 1
            for name in names:
                counts = dict(buckets[name])
                counts["gold_nonnull"] = gold_nonnull[name]
                for key, value in counts.items():
                    totals[key] += value
                qualified = f"{table}.{name}"
                gold_n = gold_nonnull[name]
                exact = counts.get("exact") or 0
                near = counts.get("near_miss") or 0
                per_attr[qualified] = {
                    **counts,
                    "exact_rate": exact / gold_n if gold_n else None,
                    "exact_or_near_rate": (exact + near) / gold_n if gold_n else None,
                    "contract_kind": (contracts.get(qualified) or contracts.get(name) or {}).get("kind"),
                }
    finally:
        con.close()
    return {"per_attribute": per_attr, "totals": dict(totals)}


def filled_cells(db: Path) -> dict[str, set[str]]:
    found: dict[str, set[str]] = defaultdict(set)
    con = sqlite3.connect(db)
    try:
        for (table,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
        ):
            cols = [info[1] for info in con.execute(f"PRAGMA table_info({_q(table)})")]
            if "doc_id" not in cols:
                continue
            for col in cols:
                if col == "doc_id" or col.endswith("__surface") or col.endswith("__like"):
                    continue
                if col.endswith("__vocab") or col.endswith("__canonical") or col.endswith("__unit"):
                    continue
                if is_id_name(col):
                    continue
                for doc_id, value in con.execute(
                    f"SELECT doc_id, {_q(col)} FROM {_q(table)}"
                ):
                    if is_null(value):
                        continue
                    found[f"{table}.{col}"].add(str(doc_id))
    finally:
        con.close()
    return found


def empty_causes(portfolio, statements, store, workload) -> dict[str, Any]:
    from quwarts.core.repair.diagnose import diagnose_empty_queries
    from quwarts.core.repair.detectors import detect_empty_queries

    empty = detect_empty_queries(portfolio, statements)
    plans = serve_plans(portfolio, statements)
    diagnoses = diagnose_empty_queries(empty, statements, plans, store=store, workload=workload)
    causes: dict[str, int] = {}
    for item in diagnoses:
        causes[item.cause] = causes.get(item.cause, 0) + 1
    return {"n": len(empty), "causes": causes, "ids": empty}


def scored_cell_names(test_rows: list[dict[str, str]], workload) -> list[str]:
    by_stmt = {
        stmt_id: template
        for template in workload.templates
        for stmt_id in template.statement_ids
    }
    names: list[str] = []
    for row in test_rows:
        template = by_stmt.get(row["query_id"])
        if template is None:
            continue
        for name in set(template.aggregated_attributes) | set(template.group_attributes):
            if not is_id_name(name):
                names.append(name)
    return names


def report_arm(
    label: str,
    portfolio: FrozenPortfolio,
    store: EvidenceStore,
    train,
    test,
    train_sql: dict[str, str],
    gold,
    workload,
    tokens: int,
) -> dict[str, Any]:
    test_sql = {row["query_id"]: row["sql"] for row in test}
    _, test_workload = analyze_workload(test_sql)
    contracts = compile_contracts(workload)
    test_contracts = compile_contracts(test_workload)
    merged = {**contracts, **test_contracts}
    plans = serve_plans(portfolio, {**train_sql, **test_sql})
    pred = Path(portfolio.databases[0].sqlite_path)
    scored = score_excluding_ids(test, plans, pred, gold, "Med")
    attr_names = [name for name in workload.requirements if not is_id_name(name)]
    cell_names = scored_cell_names(test, test_workload)
    detectors = snapshot(store, workload, portfolio, train_sql, serve_plans(portfolio, train_sql))
    return {
        "arm": label,
        "tokens_spent": tokens,
        "abstention_attributes": abstention(merged, attr_names),
        "abstention_scored_cells": abstention(merged, cell_names),
        "detectors": detectors.as_dict(),
        "train_empty": empty_causes(portfolio, train_sql, store, workload),
        "test_empty": empty_causes(portfolio, test_sql, store, test_workload),
        "scores": scored,
        "cell_f1_per_attribute": cell_f1_per_attribute(gold, pred, merged),
        "sqlite_path": str(pred),
    }


def compare_filled(a_db: Path, b_db: Path) -> dict[str, Any]:
    a = filled_cells(a_db)
    b = filled_cells(b_db)
    names = sorted(set(a) | set(b))
    a_only = 0
    b_only = 0
    both = 0
    per = {}
    for name in names:
        left = a.get(name, set())
        right = b.get(name, set())
        only_a = len(left - right)
        only_b = len(right - left)
        shared = len(left & right)
        a_only += only_a
        b_only += only_b
        both += shared
        if only_a or only_b:
            per[name] = {"a_not_b": only_a, "b_not_a": only_b, "both": shared}
    return {
        "cells_populated_a_not_b": a_only,
        "cells_populated_b_not_a": b_only,
        "cells_populated_both": both,
        "attributes_that_moved": per,
    }


def run_arm_a(train, test, train_sql, gold, workload) -> dict[str, Any]:
    portfolio = load_arm_a_portfolio({**train_sql, **{row["query_id"]: row["sql"] for row in test}})
    store = EvidenceStore(COMPILE_DIR / "artifacts" / "evidence")
    spent = int(json.loads(MANIFEST.read_text()).get("tokens_spent") or 1_543_790)
    return report_arm("A", portfolio, store, train, test, train_sql, gold, workload, spent)


def run_arm_b(train, test, train_sql, gold, workload, documents) -> dict[str, Any]:
    out = OUT / "arm_b"
    out.mkdir(parents=True, exist_ok=True)
    ledger = TokenLedger(theta=THETA, seed=42)
    caller = make_caller(ledger, model=DEFAULT_MODEL, max_tokens=1200)
    portfolio = compile_workload(
        documents,
        train_sql,
        THETA,
        seed=42,
        artifact_root=out / "artifacts",
        caller=caller,
        extract=True,
        workers=16,
        use_contracts=True,
    )
    store = EvidenceStore(out / "artifacts" / "evidence")
    return report_arm("B", portfolio, store, train, test, train_sql, gold, workload, ledger.spent)


def main(argv: list[str] | None = None) -> int:
    from diagnostics.run_config_grid import load_ground_truth

    arm = (argv or sys.argv[1:] or ["both"])[0]
    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    train_sql = {row["query_id"]: row["sql"] for row in train}
    _, workload = analyze_workload(train_sql)
    gold = load_ground_truth(gold_name("Med"))
    documents = documents_for("Med")
    OUT.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "vote_retired": True,
        "headline_note": (
            "0.126 is pre-vote. Vote is not on that record. "
            "Matched-tolerance gap is 0.108 vs 0.166 (1.54x), not 1.9-4x."
        ),
        "theta": THETA,
    }
    if arm in {"a", "both", "A"}:
        payload["A"] = run_arm_a(train, test, train_sql, gold, workload)
        (OUT / "arm_a.json").write_text(json.dumps(payload["A"], indent=2, default=str))
        print(json.dumps({
            "arm": "A",
            "exclude_id": payload["A"]["scores"]["exclude_id"],
            "official": payload["A"]["scores"]["official"],
            "loss": payload["A"]["scores"]["loss"],
            "abstention_attributes": payload["A"]["abstention_attributes"],
            "abstention_scored_cells": payload["A"]["abstention_scored_cells"],
            "train_empty": payload["A"]["train_empty"],
            "tokens": payload["A"]["tokens_spent"],
        }, indent=2, default=str), flush=True)
    if arm in {"b", "both", "B"}:
        payload["B"] = run_arm_b(train, test, train_sql, gold, workload, documents)
        (OUT / "arm_b.json").write_text(json.dumps(payload["B"], indent=2, default=str))
        print(json.dumps({
            "arm": "B",
            "exclude_id": payload["B"]["scores"]["exclude_id"],
            "official": payload["B"]["scores"]["official"],
            "loss": payload["B"]["scores"]["loss"],
            "abstention_attributes": payload["B"]["abstention_attributes"],
            "abstention_scored_cells": payload["B"]["abstention_scored_cells"],
            "train_empty": payload["B"]["train_empty"],
            "tokens": payload["B"]["tokens_spent"],
        }, indent=2, default=str), flush=True)
    if "A" in payload and "B" in payload:
        payload["filled_swap"] = compare_filled(
            Path(payload["A"]["sqlite_path"]),
            Path(payload["B"]["sqlite_path"]),
        )
        payload["cell_f1_per_attribute_delta"] = {
            name: {
                "A": (payload["A"]["cell_f1_per_attribute"]["per_attribute"].get(name) or {}).get("exact_rate"),
                "B": (payload["B"]["cell_f1_per_attribute"]["per_attribute"].get(name) or {}).get("exact_rate"),
            }
            for name in sorted(
                set(payload["A"]["cell_f1_per_attribute"]["per_attribute"])
                | set(payload["B"]["cell_f1_per_attribute"]["per_attribute"])
            )
        }
    (OUT / "phase2_report.json").write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT / "phase2_report.json")}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
