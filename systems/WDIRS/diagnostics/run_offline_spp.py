#!/usr/bin/env python3
"""Run the deployable offline SPP track on a SQL workload manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

WDIRS_ROOT = Path(__file__).resolve().parents[1]
if str(WDIRS_ROOT) not in sys.path:
    sys.path.insert(0, str(WDIRS_ROOT))

from spp.nl2sql import make_nl2sql_compiler  # noqa: E402
from spp.system import OfflineSynthesisSystem  # noqa: E402
from spp.wdirs_backend import WDIRSPrimitiveBackend  # noqa: E402
from spp.workload_intent import make_budgeted_intent_analyzer  # noqa: E402
from wdirs_runner import WDIRSRunner  # noqa: E402


def _load_queries(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        payload = payload.get("queries", [])
    if not isinstance(payload, list):
        raise ValueError("workload manifest must be a list or {'queries': [...]}")
    queries = []
    for index, row in enumerate(payload):
        if isinstance(row, str):
            queries.append({"query_id": f"q{index}", "sql": row})
        else:
            queries.append(
                {
                    "query_id": str(row.get("query_id", f"q{index}")),
                    "sql": str(row.get("sql") or row.get("text") or ""),
                }
            )
    if any(not row["sql"].strip() for row in queries):
        raise ValueError("every workload entry must contain SQL/text")
    return queries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token-budget", type=int, required=True)
    parser.add_argument("--quality-floor", type=float, default=0.0)
    parser.add_argument("--beta", type=float, default=1.0)
    args = parser.parse_args()

    output = args.output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    scratch = output.parent / f".{output.name}_backend"
    scratch.mkdir(parents=True, exist_ok=False)
    os.environ["WDIRS_DB_PATH"] = str(scratch / "shared_extraction.sqlite")

    runner = WDIRSRunner(
        args.dataset,
        cache_dir=scratch / "cache",
    )
    try:
        original_client = runner.llm_client
        backend = WDIRSPrimitiveBackend(runner)
        system = OfflineSynthesisSystem(
            backend,
            make_nl2sql_compiler(original_client),
            intent_analyzer=make_budgeted_intent_analyzer(original_client),
            beta=args.beta,
            quality_floor=args.quality_floor,
        )
        result = system.synthesize(
            queries=_load_queries(args.workload),
            token_budget=args.token_budget,
            output_dir=output,
        )
        run_manifest = {
            "dataset": args.dataset,
            "workload": str(args.workload.resolve()),
            "token_budget": args.token_budget,
            "candidate_count": result.candidate_count,
            "selected_config_ids": list(result.portfolio.selected_config_ids),
            "serving_manifest": str(result.serving_manifest),
            "token_summary": result.token_summary,
            "backend_scratch": str(scratch),
        }
        (output / "run_manifest.json").write_text(
            json.dumps(run_manifest, indent=2)
        )
        print(json.dumps(run_manifest, indent=2))
    finally:
        runner.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
