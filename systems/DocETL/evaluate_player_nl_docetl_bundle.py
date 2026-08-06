#!/usr/bin/env python3
"""Evaluate a sealed NL-only DocETL bundle against reference data."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
WDIRS_ROOT = PROJECT_ROOT / "systems" / "WDIRS"
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_bundle(bundle: Path) -> dict:
    """Verify the complete synthesis seal before opening evaluation inputs."""

    bundle = bundle.expanduser().resolve()
    manifest_path = bundle / "manifest.json"
    sealed_path = bundle / "SEALED"
    if not manifest_path.is_file() or not sealed_path.is_file():
        raise ValueError("refusing to evaluate an unsealed DocETL bundle")
    if _sha256(manifest_path) != sealed_path.read_text().strip():
        raise ValueError("DocETL serving manifest checksum mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("method") != "docetl_independent_nl":
        raise ValueError("bundle is not an independent NL-only DocETL run")
    for relative, expected in manifest.get("artifacts", {}).items():
        path = bundle / relative
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"sealed DocETL artifact mismatch: {relative}")
    return manifest


def _reference_queries(path: Path) -> Dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("queries", []) if isinstance(payload, Mapping) else payload
    references = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError("reference workload rows must be objects")
        query_id = str(row.get("query_id", f"q{index}"))
        sql = str(row.get("sql_query") or row.get("sql") or "").strip()
        if not sql or query_id in references:
            raise ValueError(f"invalid reference query {query_id!r}")
        references[query_id] = sql
    if not references:
        raise ValueError("reference workload is empty")
    return references


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
    row: Dict[str, Any] = {
        "official_query_error": official_error,
        "official_accuracy": 1.0 - official_error,
        "gold_row_count": len(gold_rows),
        "predicted_row_count": len(predicted_rows),
        "gold_rows": gold_rows,
        "predicted_rows": predicted_rows,
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
    ready = json_ready_metrics(
        evaluate_aggregation_tables(pred, gold, config=config)
    )
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


def _mean_tau_map(
    per_query: Mapping[str, Mapping[str, Any]],
    field: str,
) -> Dict[str, float]:
    sample = next(iter(per_query.values()), None)
    if sample is None:
        return {}
    result = {}
    for tau in sample.get(field, {}):
        values = [
            float(row[field][tau])
            for row in per_query.values()
            if tau in row.get(field, {})
        ]
        if values:
            result[str(tau)] = statistics.mean(values)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--reference-workload", type=Path, required=True)
    parser.add_argument("--dataset", default="Player")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--tau",
        type=float,
        nargs="+",
        default=list(MetricConfig().tau_sweep),
    )
    parser.add_argument(
        "--structure-beta",
        type=float,
        default=MetricConfig().structure_beta,
        help="Recall weight for structure F-beta (default: 2.0).",
    )
    args = parser.parse_args()

    # This must remain the first operation involving either side of the
    # synthesis/evaluation boundary.
    bundle = args.bundle.expanduser().resolve()
    manifest = verify_bundle(bundle)

    references = _reference_queries(args.reference_workload.expanduser().resolve())
    frozen_ids = [row["query_id"] for row in manifest["queries"]]
    if set(frozen_ids) != set(references):
        raise ValueError(
            "reference/frozen query IDs differ: "
            f"frozen_only={sorted(set(frozen_ids) - set(references))}, "
            f"reference_only={sorted(set(references) - set(frozen_ids))}"
        )

    config = MetricConfig(
        tau_sweep=tuple(float(tau) for tau in args.tau),
        structure_beta=float(args.structure_beta),
    )
    ground_truth = load_ground_truth(args.dataset)
    attributes = load_attributes(args.dataset)
    connection = _build_in_memory_db(ground_truth)
    per_query = {}
    try:
        for row in manifest["queries"]:
            query_id = row["query_id"]
            reference_sql = references[query_id]
            gold_rows = _execute_sql(connection, reference_sql)
            predicted_path = bundle / row["result_path"]
            predicted_rows = json.loads(
                predicted_path.read_text(encoding="utf-8")
            )
            per_query[query_id] = _score_query(
                reference_sql,
                gold_rows,
                predicted_rows,
                attributes,
                config=config,
            )
    finally:
        connection.close()

    aggregation_rows = {
        query_id: row
        for query_id, row in per_query.items()
        if "query_score" in row
    }
    official_errors = [
        float(row["official_query_error"]) for row in per_query.values()
    ]
    structure_scores = [
        float(row["structure_score"]) for row in aggregation_rows.values()
    ]
    structure_f1_scores = [
        float(row["structure_f1_score"])
        for row in aggregation_rows.values()
    ]
    report = {
        "method": "docetl_independent_nl",
        "dataset": args.dataset,
        "query_count": len(per_query),
        "aggregation_query_count": len(aggregation_rows),
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
        "mean_cell_f1": _mean_tau_map(aggregation_rows, "cell_f1"),
        "mean_query_score": _mean_tau_map(aggregation_rows, "query_score"),
        "mean_official_query_error": statistics.mean(official_errors),
        "mean_official_accuracy": 1.0 - statistics.mean(official_errors),
        "structure_beta": config.structure_beta,
        "construction_tokens": int(manifest["construction_tokens"]),
        "per_query": per_query,
        "bundle_manifest_sha256": _sha256(bundle / "manifest.json"),
        "reference_workload_sha256": _sha256(
            args.reference_workload.expanduser().resolve()
        ),
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str))
    print(
        json.dumps(
            {
                "mean_structure_score": report["mean_structure_score"],
                "mean_structure_fbeta_score": report[
                    "mean_structure_fbeta_score"
                ],
                "mean_structure_f1_score": report[
                    "mean_structure_f1_score"
                ],
                "structure_beta": report["structure_beta"],
                "mean_cell_f1": report["mean_cell_f1"],
                "mean_query_score": report["mean_query_score"],
                "mean_official_accuracy": report[
                    "mean_official_accuracy"
                ],
                "construction_tokens": report["construction_tokens"],
                "output": str(output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
