#!/usr/bin/env python3
"""Cross-workload QuWARTS transfer eval on already-built databases.

For each of the four Player contrast workloads used as TRAIN:
  - reuse that run's sealed ``serving_bundle`` databases (no re-extraction)
  - take each of the other three workloads as TEST
  - SQL-contract-compile the test queries onto the train schemas
  - execute compiled SQL on the train sqlite DBs
  - score against gold from the test reference SQL

That yields 12 train→test pairs. Runtime is compile + sqlite only.

Examples:
  python3 "case study/run_player_contrast_cross_eval.py" --dry-run
  python3 "case study/run_player_contrast_cross_eval.py" --run
  python3 "case study/run_player_contrast_cross_eval.py" --run \\
      --only-train player_join20 --only-test player_groupby20
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
CASE = Path(__file__).resolve().parent
WDIRS = ROOT / "systems" / "WDIRS"
WORKLOADS_DIR = CASE / "workloads"

WORKLOADS = (
    "player_join20",
    "player_groupby20",
    "player_multiagg20",
    "player_filterjoin20",
)

DEFAULT_QUWARTS_ROOT = (
    WORKLOADS_DIR / "runs" / "quwarts_forced_taxonomy_25pct_20260810"
)
DEFAULT_GROUPBY_ROOT = (
    WORKLOADS_DIR / "runs" / "quwarts_forced_taxonomy_25pct_20260809"
)

def _ensure_wdirs_imports() -> None:
    for import_root in (WDIRS, ROOT):
        if str(import_root) not in sys.path:
            sys.path.insert(0, str(import_root))


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _parse_ids(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    values = {item.strip() for item in raw.split(",") if item.strip()}
    unknown = sorted(values - set(WORKLOADS))
    if unknown:
        raise SystemExit(f"Unknown workload id(s): {', '.join(unknown)}")
    return values


def _train_root(
    workload_id: str, *, quwarts_root: Path, groupby_root: Path
) -> Path:
    return groupby_root if workload_id == "player_groupby20" else quwarts_root


def _result_dir(root: Path, workload_id: str) -> Path:
    return root / "results" / workload_id


def _load_manifest_rows(workload_id: str) -> list[dict[str, str]]:
    path = WORKLOADS_DIR / workload_id / "query_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("queries", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{workload_id}: empty query manifest")
    return [
        {
            "query_id": str(row.get("query_id", f"q{index}")),
            "sql": str(row.get("sql") or row.get("sql_query") or "").strip(),
        }
        for index, row in enumerate(rows)
    ]


def _selected_config_ids(manifest: Mapping[str, Any]) -> list[str]:
    portfolio = manifest.get("portfolio") or {}
    selected = portfolio.get("selected_config_ids")
    if isinstance(selected, list) and selected:
        return [str(item) for item in selected]
    databases = manifest.get("databases") or []
    return [str(item["config_id"]) for item in databases if item.get("config_id")]


def _database_map(bundle: Path, manifest: Mapping[str, Any]) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for item in manifest.get("databases") or []:
        config_id = str(item.get("config_id") or "")
        filename = str(item.get("filename") or "")
        if not config_id or not filename:
            continue
        path = bundle / filename
        if path.is_file():
            mapping[config_id] = path
    return mapping


def _compile_and_execute(
    *,
    plan: Any,
    configs: Mapping[str, Any],
    databases: Mapping[str, Path],
    config_order: Sequence[str],
    max_rows: int,
    compile_query_plan: Any,
    execute_readonly: Any,
    query_execution_error: Any,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    for config_id in config_order:
        config = configs.get(config_id)
        database_path = databases.get(config_id)
        if config is None or database_path is None:
            errors.append(
                {
                    "config_id": config_id,
                    "error": "missing config or database artifact",
                }
            )
            continue
        try:
            sql = compile_query_plan(plan, config)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({"config_id": config_id, "error": f"compile: {exc}"})
            continue
        if not sql:
            errors.append(
                {
                    "config_id": config_id,
                    "error": "compile returned None (plan cannot bind)",
                }
            )
            continue
        try:
            execution = execute_readonly(database_path, sql, max_rows=max_rows)
        except (query_execution_error, ValueError) as exc:
            errors.append(
                {
                    "config_id": config_id,
                    "error": f"exec: {exc}",
                    "sql": sql,
                }
            )
            continue
        return {
            "status": "ok",
            "config_id": config_id,
            "sql": sql,
            "rows": [dict(row) for row in execution.rows],
            "attempts": errors,
        }
    return {
        "status": "failed",
        "config_id": None,
        "sql": None,
        "rows": [],
        "attempts": errors,
        "error": "no train database could compile+execute this test query",
    }


def _aggregate_report(
    *,
    per_query: Mapping[str, Mapping[str, Any]],
    train_workload: str,
    test_workload: str,
    train_result_dir: Path,
    bundle: Path,
    manifest: Mapping[str, Any],
    reference_workload: Path,
    dataset: str,
    routing_policy: str,
    metric_config: Any,
    mean_tau_map: Any,
    sha256: Any,
) -> dict[str, Any]:
    agg_rows = {
        query_id: row
        for query_id, row in per_query.items()
        if "query_score" in row
    }
    official_errors = [
        float(row["official_query_error"]) for row in per_query.values()
    ]
    structure_scores = [
        float(row["structure_score"]) for row in agg_rows.values()
    ]
    structure_f1_scores = [
        float(row["structure_f1_score"]) for row in agg_rows.values()
    ]
    ledger_path = bundle / "token_ledger.json"
    construction_tokens = int(
        (manifest.get("portfolio") or {}).get("construction_tokens") or 0
    )
    total_budget = None
    if ledger_path.is_file():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        total_budget = int(ledger.get("total_budget") or 0)
    return {
        "method": "quwarts_cross_workload",
        "dataset": dataset,
        "train_workload": train_workload,
        "test_workload": test_workload,
        "train_result_dir": _rel(train_result_dir),
        "train_bundle": _rel(bundle),
        "routing_policy": routing_policy,
        "metric": "structure_x_cell_f1_range_error",
        "query_count": len(per_query),
        "aggregation_query_count": len(agg_rows),
        "mean_structure_score": (
            statistics.mean(structure_scores) if structure_scores else None
        ),
        "mean_structure_fbeta_score": (
            statistics.mean(structure_scores) if structure_scores else None
        ),
        "mean_structure_f1_score": (
            statistics.mean(structure_f1_scores) if structure_f1_scores else None
        ),
        "mean_cell_f1": mean_tau_map(agg_rows, "cell_f1"),
        "mean_query_score": mean_tau_map(agg_rows, "query_score"),
        "mean_official_query_error": (
            statistics.mean(official_errors) if official_errors else None
        ),
        "mean_official_accuracy": (
            1.0 - statistics.mean(official_errors) if official_errors else None
        ),
        "mean_query_error": (
            statistics.mean(official_errors) if official_errors else None
        ),
        "mean_accuracy": (
            1.0 - statistics.mean(official_errors) if official_errors else None
        ),
        "tau_sweep": [float(tau) for tau in metric_config.tau_sweep],
        "structure_beta": metric_config.structure_beta,
        "per_query": per_query,
        "selected_database_count": len(manifest.get("databases") or []),
        "storage_bytes": sum(
            int(database.get("size_bytes") or 0)
            for database in manifest.get("databases") or []
        ),
        "construction_tokens": construction_tokens,
        "total_token_budget": total_budget,
        "unused_tokens": (
            max(total_budget - construction_tokens, 0)
            if total_budget is not None
            else None
        ),
        "manifest_sha256": sha256(bundle / "manifest.json"),
        "reference_workload_sha256": sha256(reference_workload),
        "compiled_ok_count": sum(
            1
            for row in per_query.values()
            if row.get("cross_compile", {}).get("status") == "ok"
        ),
    }


def evaluate_pair(
    *,
    train_workload: str,
    test_workload: str,
    train_result_dir: Path,
    dataset: str,
    routing_policy: str,
    max_rows: int,
    metric_config: Any,
    ground_truth_connection: Any,
    attributes: Mapping[str, Any],
    deps: Mapping[str, Any],
) -> dict[str, Any]:
    OfflineQueryServer = deps["OfflineQueryServer"]
    configs_from_manifest = deps["_configs_from_manifest"]
    reference_queries = deps["_reference_queries"]
    analyze_sql_contract_workload = deps["analyze_sql_contract_workload"]
    execute_sql = deps["_execute_sql"]
    score_query = deps["_score_query"]
    sha256 = deps["_sha256"]
    mean_tau_map = deps["_mean_tau_map"]

    bundle = train_result_dir / "serving_bundle"
    synthesis_path = train_result_dir / "synthesis_manifest.json"
    if not (bundle / "SEALED").is_file():
        raise FileNotFoundError(f"missing sealed bundle: {bundle / 'SEALED'}")
    if not synthesis_path.is_file():
        raise FileNotFoundError(f"missing synthesis manifest: {synthesis_path}")

    # Verifies seal + DB hashes before any test SQL is compiled.
    OfflineQueryServer(bundle)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    expected_sha = str(manifest.get("synthesis_manifest_sha256") or "")
    if not expected_sha or sha256(synthesis_path) != expected_sha:
        raise ValueError(
            f"{train_workload}: synthesis_manifest.json does not match sealed bundle"
        )
    synthesis = json.loads(synthesis_path.read_text(encoding="utf-8"))
    configs = configs_from_manifest(synthesis)
    databases = _database_map(bundle, manifest)
    selected = _selected_config_ids(manifest)
    if routing_policy == "single":
        config_order = selected[:1]
    else:
        config_order = selected
    if not config_order:
        raise ValueError(f"{train_workload}: no selected databases in serving bundle")

    reference_path = WORKLOADS_DIR / test_workload / "query_manifest.json"
    references = reference_queries(reference_path)
    rows = _load_manifest_rows(test_workload)
    intent = analyze_sql_contract_workload(rows)
    requirements = {
        requirement.query_id: requirement for requirement in intent.requirements
    }

    compiled_queries: dict[str, Any] = {}
    per_query: dict[str, Any] = {}
    for query_id, reference_sql in references.items():
        requirement = requirements.get(query_id)
        gold_rows = execute_sql(ground_truth_connection, reference_sql)
        if requirement is None or requirement.plan is None:
            cross = {
                "status": "failed",
                "error": "test query has no SQL-contract plan",
                "config_id": None,
                "sql": None,
                "rows": [],
            }
        else:
            cross = _compile_and_execute(
                plan=requirement.plan,
                configs=configs,
                databases=databases,
                config_order=config_order,
                max_rows=max_rows,
                compile_query_plan=deps["compile_query_plan"],
                execute_readonly=deps["execute_readonly"],
                query_execution_error=deps["QueryExecutionError"],
            )
        scored = score_query(
            reference_sql,
            gold_rows,
            list(cross.get("rows") or []),
            attributes,
            config=metric_config,
        )
        scored["cross_compile"] = {
            "status": cross.get("status"),
            "config_id": cross.get("config_id"),
            "sql": cross.get("sql"),
            "error": cross.get("error"),
            "attempts": cross.get("attempts") or [],
        }
        if cross.get("status") != "ok":
            scored["reason"] = cross.get("error") or "cross_compile_or_exec_failed"
        per_query[query_id] = scored
        compiled_queries[query_id] = {
            "status": cross.get("status"),
            "config_id": cross.get("config_id"),
            "sql": cross.get("sql"),
            "error": cross.get("error"),
            "attempt_count": len(cross.get("attempts") or []),
        }

    report = _aggregate_report(
        per_query=per_query,
        train_workload=train_workload,
        test_workload=test_workload,
        train_result_dir=train_result_dir,
        bundle=bundle,
        manifest=manifest,
        reference_workload=reference_path,
        dataset=dataset,
        routing_policy=routing_policy,
        metric_config=metric_config,
        mean_tau_map=mean_tau_map,
        sha256=sha256,
    )
    report["compiled_queries"] = compiled_queries
    return report


def _load_deps() -> dict[str, Any]:
    _ensure_wdirs_imports()
    from diagnostics.analyze_spp_posthoc import _configs_from_manifest
    from diagnostics.evaluate_native_spp_bundle import (
        _mean_tau_map,
        _reference_queries,
        _score_query,
        _sha256,
    )
    from diagnostics.run_config_grid import load_attributes, load_ground_truth
    from spp.aggregation_metrics import MetricConfig
    from spp.config_grid import _build_in_memory_db, _execute_sql
    from spp.query_plan_compiler import compile_query_plan
    from spp.query_quality import QueryExecutionError, execute_readonly
    from spp.serving import OfflineQueryServer
    from spp.workload_intent import analyze_sql_contract_workload

    return {
        "_configs_from_manifest": _configs_from_manifest,
        "_mean_tau_map": _mean_tau_map,
        "_reference_queries": _reference_queries,
        "_score_query": _score_query,
        "_sha256": _sha256,
        "load_attributes": load_attributes,
        "load_ground_truth": load_ground_truth,
        "MetricConfig": MetricConfig,
        "_build_in_memory_db": _build_in_memory_db,
        "_execute_sql": _execute_sql,
        "compile_query_plan": compile_query_plan,
        "QueryExecutionError": QueryExecutionError,
        "execute_readonly": execute_readonly,
        "OfflineQueryServer": OfflineQueryServer,
        "analyze_sql_contract_workload": analyze_sql_contract_workload,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_index(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "train_workload",
        "test_workload",
        "mean_official_accuracy",
        "mean_structure_score",
        "mean_query_score_0.2",
        "compiled_ok_count",
        "query_count",
        "construction_tokens",
        "evaluation_json",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Leave-one-in QuWARTS cross-workload eval: train DBs × foreign test SQL."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--quwarts-root", type=Path, default=DEFAULT_QUWARTS_ROOT)
    parser.add_argument("--groupby-root", type=Path, default=DEFAULT_GROUPBY_ROOT)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Defaults to case study/workloads/runs/cross_eval_<utcstamp>",
    )
    parser.add_argument("--dataset", default="Player")
    parser.add_argument("--only-train", default=None)
    parser.add_argument("--only-test", default=None)
    parser.add_argument(
        "--routing",
        choices=("first-ok", "single"),
        default="first-ok",
        help=(
            "first-ok: try selected train DBs until compile+exec succeeds; "
            "single: use only the first selected DB."
        ),
    )
    parser.add_argument("--max-rows", type=int, default=100_000)
    parser.add_argument(
        "--tau",
        type=float,
        nargs="+",
        default=[0.01, 0.05, 0.2],
    )
    parser.add_argument(
        "--structure-beta",
        type=float,
        default=2.0,
    )
    args = parser.parse_args()

    train_ids = _parse_ids(args.only_train) or set(WORKLOADS)
    test_ids = _parse_ids(args.only_test) or set(WORKLOADS)
    pairs = [
        (train, test)
        for train in WORKLOADS
        if train in train_ids
        for test in WORKLOADS
        if test in test_ids and test != train
    ]
    if not pairs:
        raise SystemExit("No train/test pairs selected")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_root = (
        args.output_root
        if args.output_root is not None
        else WORKLOADS_DIR / "runs" / f"cross_eval_{stamp}"
    )

    print(f"pairs: {len(pairs)}")
    for train, test in pairs:
        root = _train_root(
            train, quwarts_root=args.quwarts_root, groupby_root=args.groupby_root
        )
        result_dir = _result_dir(root, train)
        print(
            f"  train={train} test={test}\n"
            f"    bundle={_rel(result_dir / 'serving_bundle')}\n"
            f"    test_sql={_rel(WORKLOADS_DIR / test / 'query_manifest.json')}"
        )

    if args.dry_run:
        print("\ndry-run only; no evaluation written")
        return 0

    deps = _load_deps()
    MetricConfig = deps["MetricConfig"]
    metric_config = MetricConfig(
        tau_sweep=tuple(float(tau) for tau in args.tau),
        structure_beta=float(args.structure_beta),
    )
    ground_truth = deps["load_ground_truth"](args.dataset)
    attributes = deps["load_attributes"](args.dataset)
    connection = deps["_build_in_memory_db"](ground_truth)
    index_rows: list[dict[str, Any]] = []
    batch = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "quwarts_cross_workload",
        "routing_policy": args.routing,
        "dataset": args.dataset,
        "quwarts_root": _rel(args.quwarts_root),
        "groupby_root": _rel(args.groupby_root),
        "pair_count": len(pairs),
        "pairs": [],
    }
    try:
        for train, test in pairs:
            root = _train_root(
                train,
                quwarts_root=args.quwarts_root,
                groupby_root=args.groupby_root,
            )
            train_result_dir = _result_dir(root, train)
            pair_dir = output_root / f"train={train}" / f"test={test}"
            print(f"\n=== train={train} → test={test} ===")
            report = evaluate_pair(
                train_workload=train,
                test_workload=test,
                train_result_dir=train_result_dir,
                dataset=args.dataset,
                routing_policy=args.routing,
                max_rows=args.max_rows,
                metric_config=metric_config,
                ground_truth_connection=connection,
                attributes=attributes,
                deps=deps,
            )
            evaluation_path = pair_dir / "evaluation.json"
            compiled_path = pair_dir / "compiled_queries.json"
            _write_json(evaluation_path, report)
            _write_json(compiled_path, report.get("compiled_queries") or {})
            summary = {
                "train_workload": train,
                "test_workload": test,
                "mean_official_accuracy": report.get("mean_official_accuracy"),
                "mean_structure_score": report.get("mean_structure_score"),
                "mean_query_score": report.get("mean_query_score"),
                "compiled_ok_count": report.get("compiled_ok_count"),
                "output": _rel(evaluation_path),
            }
            print(json.dumps(summary, indent=2))
            index_rows.append(
                {
                    "train_workload": train,
                    "test_workload": test,
                    "mean_official_accuracy": report.get("mean_official_accuracy"),
                    "mean_structure_score": report.get("mean_structure_score"),
                    "mean_query_score_0.2": (report.get("mean_query_score") or {}).get(
                        "0.2"
                    ),
                    "compiled_ok_count": report.get("compiled_ok_count"),
                    "query_count": report.get("query_count"),
                    "construction_tokens": report.get("construction_tokens"),
                    "evaluation_json": _rel(evaluation_path),
                }
            )
            batch["pairs"].append(summary)
            _write_index(output_root / "cross_eval_index.csv", index_rows)
    finally:
        connection.close()

    _write_json(output_root / "batch_manifest.json", batch)
    _write_index(output_root / "cross_eval_index.csv", index_rows)
    print(f"\nWrote {output_root / 'cross_eval_index.csv'}")
    print(f"Wrote {output_root / 'batch_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
