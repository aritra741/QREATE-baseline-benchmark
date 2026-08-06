#!/usr/bin/env python3
"""Evaluate a sealed native-SPP bundle behind the ground-truth firewall."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

WDIRS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WDIRS_ROOT.parent.parent
for import_root in (WDIRS_ROOT, PROJECT_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from diagnostics.run_config_grid import (  # noqa: E402
    load_attributes,
    load_ground_truth,
)
from spp.aggregation_metrics import (  # noqa: E402
    MetricConfig,
    evaluate_aggregation_tables,
    gold_table_from_sql,
    json_ready_metrics,
    predicted_table_from_rows,
    schema_from_sql,
)
from spp.config_grid import (  # noqa: E402
    _build_in_memory_db,
    _execute_sql,
    official_query_error,
)
from spp.serving import OfflineQueryServer  # noqa: E402


def _reference_queries(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text())
    rows = payload.get("queries", []) if isinstance(payload, dict) else payload
    references: dict[str, str] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("reference workload rows must be JSON objects")
        query_id = str(row.get("query_id", f"q{index}"))
        sql = str(row.get("sql_query") or row.get("sql") or "").strip()
        if not sql:
            raise ValueError(f"reference query {query_id!r} has no SQL")
        if query_id in references:
            raise ValueError(f"duplicate reference query ID: {query_id}")
        references[query_id] = sql
    if not references:
        raise ValueError("reference workload is empty")
    return references


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mean_tau_map(
    per_query: Mapping[str, Mapping[str, Any]], field: str
) -> Dict[str, float]:
    means: Dict[str, float] = {}
    sample = next(iter(per_query.values()), None)
    if sample is None:
        return means
    taus = list(sample.get(field, {}).keys())
    for tau in taus:
        values = [
            float(row[field][tau])
            for row in per_query.values()
            if field in row and tau in row[field]
        ]
        if values:
            means[str(tau)] = statistics.mean(values)
    return means


def _score_query(
    reference_sql: str,
    gold_rows: List[dict],
    predicted_rows: List[dict],
    attributes: Mapping[str, Mapping[str, Mapping[str, Any]]],
    *,
    config: MetricConfig,
) -> dict:
    official_error = float(
        official_query_error(
            reference_sql,
            gold_rows,
            predicted_rows,
            attributes,
        )
    )
    row: dict[str, Any] = {
        "official_query_error": official_error,
        "official_accuracy": 1.0 - official_error,
        "gold_row_count": len(gold_rows),
        "predicted_row_count": len(predicted_rows),
    }

    schema = schema_from_sql(reference_sql)
    row["schema"] = {
        "key_columns": schema["key_columns"],
        "measure_columns": schema["measure_columns"],
        "operators": schema["operators"],
        "is_aggregation": schema["is_aggregation"],
        "has_groupby": schema["has_groupby"],
    }
    if not schema["is_aggregation"]:
        row["reason"] = "not_aggregation"
        return row

    gold = gold_table_from_sql(gold_rows, reference_sql)
    pred = predicted_table_from_rows(predicted_rows, gold=gold)
    metrics = evaluate_aggregation_tables(pred, gold, config=config)
    ready = json_ready_metrics(metrics)
    row["rank"] = ready["rank"]
    row["structure"] = ready["structure"]
    row["value"] = ready["value"]
    row["grouping"] = ready["grouping"]
    row["structure_score"] = ready["rank"]["structure_score"]
    row["structure_fbeta_score"] = ready["rank"][
        "structure_fbeta_score"
    ]
    row["structure_f1_score"] = ready["rank"]["structure_f1_score"]
    row["structure_beta"] = ready["rank"]["structure_beta"]
    row["cell_f1"] = ready["rank"]["cell_f1"]
    row["query_score"] = ready["rank"]["query_score"]
    return row


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Score a sealed SPP deployment with aggregation metrics "
            "(structure × cell_f1) plus official macro-F1."
        )
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--reference-workload", type=Path, required=True)
    parser.add_argument("--dataset", default="Player")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--tau",
        type=float,
        nargs="+",
        default=list(MetricConfig().tau_sweep),
        help="Cell-F1 / query_score thresholds (default: 0.01 0.05 0.20)",
    )
    parser.add_argument(
        "--structure-beta",
        type=float,
        default=MetricConfig().structure_beta,
        help="Recall weight for structure F-beta (default: 2.0).",
    )
    args = parser.parse_args()

    bundle = args.bundle.expanduser().resolve()
    if not (bundle / "SEALED").is_file():
        raise ValueError("refusing to evaluate an unsealed SPP bundle")

    # Constructing the server verifies the manifest seal, database hashes, and
    # precompiled SQL hashes before ground truth is loaded.
    server = OfflineQueryServer(bundle)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    frozen_ids = [row["query_id"] for row in manifest["queries"]]
    references = _reference_queries(args.reference_workload)
    if set(frozen_ids) != set(references):
        missing = sorted(set(frozen_ids) - set(references))
        extra = sorted(set(references) - set(frozen_ids))
        raise ValueError(
            f"reference/frozen query IDs differ; missing={missing}, extra={extra}"
        )

    config = MetricConfig(
        tau_sweep=tuple(float(tau) for tau in args.tau),
        structure_beta=float(args.structure_beta),
    )
    ground_truth = load_ground_truth(args.dataset)
    attributes = load_attributes(args.dataset)
    connection = _build_in_memory_db(ground_truth)
    per_query: dict[str, dict] = {}
    try:
        for query_id in frozen_ids:
            reference_sql = references[query_id]
            gold_rows = _execute_sql(connection, reference_sql)
            predicted_rows = server.execute(query_id)
            per_query[query_id] = _score_query(
                reference_sql,
                gold_rows,
                predicted_rows,
                attributes,
                config=config,
            )
    finally:
        connection.close()

    ledger = json.loads((bundle / "token_ledger.json").read_text())
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

    report = {
        "method": "native_spp",
        "dataset": args.dataset,
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
            statistics.mean(structure_f1_scores)
            if structure_f1_scores
            else None
        ),
        "mean_cell_f1": _mean_tau_map(agg_rows, "cell_f1"),
        "mean_query_score": _mean_tau_map(agg_rows, "query_score"),
        "mean_official_query_error": statistics.mean(official_errors),
        "mean_official_accuracy": 1.0 - statistics.mean(official_errors),
        # Backward-compatible aliases (official macro-F1 path).
        "mean_query_error": statistics.mean(official_errors),
        "mean_accuracy": 1.0 - statistics.mean(official_errors),
        "tau_sweep": [float(tau) for tau in config.tau_sweep],
        "structure_beta": config.structure_beta,
        "per_query": per_query,
        "selected_database_count": len(manifest["databases"]),
        "storage_bytes": sum(
            int(database["size_bytes"]) for database in manifest["databases"]
        ),
        "construction_tokens": int(
            manifest["portfolio"]["construction_tokens"]
        ),
        "total_token_budget": int(ledger["total_budget"]),
        "unused_tokens": max(
            int(ledger["total_budget"])
            - int(manifest["portfolio"]["construction_tokens"]),
            0,
        ),
        "manifest_sha256": _sha256(manifest_path),
        "reference_workload_sha256": _sha256(args.reference_workload),
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))

    summary = {
        "mean_structure_score": report["mean_structure_score"],
        "mean_structure_fbeta_score": report[
            "mean_structure_fbeta_score"
        ],
        "mean_structure_f1_score": report["mean_structure_f1_score"],
        "structure_beta": report["structure_beta"],
        "mean_cell_f1": report["mean_cell_f1"],
        "mean_query_score": report["mean_query_score"],
        "mean_official_accuracy": report["mean_official_accuracy"],
        "aggregation_query_count": report["aggregation_query_count"],
        "output": str(output),
    }
    print(json.dumps(summary, indent=2))
    print(f"\nFull report written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
