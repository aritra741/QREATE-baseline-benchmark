#!/usr/bin/env python3
"""Evaluate a sealed native-SPP bundle behind the ground-truth firewall."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

WDIRS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WDIRS_ROOT.parent.parent
for import_root in (WDIRS_ROOT, PROJECT_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from diagnostics.run_config_grid import (  # noqa: E402
    load_attributes,
    load_ground_truth,
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score a sealed SPP deployment using reference SQL."
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--reference-workload", type=Path, required=True)
    parser.add_argument("--dataset", default="Player")
    parser.add_argument("--output", type=Path, required=True)
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

    ground_truth = load_ground_truth(args.dataset)
    attributes = load_attributes(args.dataset)
    connection = _build_in_memory_db(ground_truth)
    per_query: dict[str, dict] = {}
    try:
        for query_id in frozen_ids:
            reference_sql = references[query_id]
            gold_rows = _execute_sql(connection, reference_sql)
            predicted_rows = server.execute(query_id)
            error = float(
                official_query_error(
                    reference_sql,
                    gold_rows,
                    predicted_rows,
                    attributes,
                )
            )
            per_query[query_id] = {
                "query_error": error,
                "accuracy": 1.0 - error,
                "gold_row_count": len(gold_rows),
                "predicted_row_count": len(predicted_rows),
            }
    finally:
        connection.close()

    ledger = json.loads((bundle / "token_ledger.json").read_text())
    errors = [row["query_error"] for row in per_query.values()]
    report = {
        "method": "native_spp",
        "dataset": args.dataset,
        "query_count": len(per_query),
        "mean_query_error": statistics.mean(errors),
        "mean_accuracy": 1.0 - statistics.mean(errors),
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
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
