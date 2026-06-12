#!/usr/bin/env python3
"""Verify workload-aware extraction prompts contain no gold-schema leakage."""

from __future__ import annotations

import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from data.instance_builder import build_instance
from data.workload_splits import load_split_queries
from pipeline.extraction_context import (
    build_extraction_task_context,
    build_workload_aware_extraction_prompt,
    extract_demand_profile_sql_only,
    gold_schema_leaks_in_prompt,
    resolve_demand_profile,
)
from pipeline.schema import load_fixed_schema


def main() -> None:
    queries = load_split_queries("test")
    schema = load_fixed_schema("Player")
    instance = build_instance("Player", include_ground_truth=False)

    demand_sql = extract_demand_profile_sql_only(queries)
    demand_resolved = resolve_demand_profile(queries)
    assert demand_sql == demand_resolved, "resolve_demand_profile must equal SQL-only parse"

    ctx = build_extraction_task_context(queries, demand_resolved)
    sample_docs = [
        next(d for d in instance.corpus if d["doc_id"].startswith("player/")),
        next(d for d in instance.corpus if d["doc_id"].startswith("team/")),
        next(d for d in instance.corpus if d["doc_id"].startswith("city/")),
    ]

    print(f"Test queries: {len(queries)}")
    print(f"Demand columns (SQL-only): {len(demand_resolved['columns'])}")
    print(f"has_join={demand_resolved['has_join']} has_temporal={demand_resolved['has_temporal']}")
    print()

    failed = False
    for doc in sample_docs:
        prompt = build_workload_aware_extraction_prompt(doc, task_context=ctx)
        leaks = gold_schema_leaks_in_prompt(prompt, schema)
        status = "OK" if not leaks else f"LEAK {leaks}"
        print(f"  {doc['doc_id']}: {status}")
        if leaks:
            failed = True

    if failed:
        print("\nFAILED: gold schema material found in workload-aware prompts")
        sys.exit(1)

    print("\nPASSED: demand is SQL-only; prompts are free of gold schema fields")


if __name__ == "__main__":
    main()
