#!/usr/bin/env python3
"""Build exact evaluation-only oracle references from exhaustive results."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WDIRS_ROOT = Path(__file__).resolve().parents[1]
if str(WDIRS_ROOT) not in sys.path:
    sys.path.insert(0, str(WDIRS_ROOT))

from spp.oracle_evaluation import (  # noqa: E402
    OracleConfigResult,
    build_oracle_references,
    save_oracle_references,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exhaustive-results", type=Path, required=True)
    parser.add_argument("--deployment-manifest", type=Path, required=True)
    parser.add_argument("--token-budget", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.exhaustive_results.read_text())
    rows = payload.get("configs", payload) if isinstance(payload, dict) else payload
    results = [
        OracleConfigResult(
            config_id=str(row["config_id"]),
            construction_tokens=int(row["construction_tokens"]),
            per_query_error={
                str(query_id): float(error)
                for query_id, error in row["per_query_error"].items()
            },
            enumeration_tokens=int(row.get("enumeration_tokens", 0)),
            enumeration_seconds=float(row.get("enumeration_seconds", 0.0)),
        )
        for row in rows
    ]
    references = build_oracle_references(
        results,
        token_budget=args.token_budget,
        frozen_deployment_manifest=args.deployment_manifest,
    )
    save_oracle_references(references, args.output)
    print(json.dumps(references.__dict__, indent=2, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
