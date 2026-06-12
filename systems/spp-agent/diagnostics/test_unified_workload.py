#!/usr/bin/env python3
"""Fast checks that unified workload preparation includes all slice queries."""

from __future__ import annotations

import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from data.aggregation_slices import AGGREGATION_SLICE_ORDER, UNIFIED_WORKLOAD_NAME
from data.instance_builder import build_instance
from data.query_alignment import (
    prepare_aggregation_slice_instance,
    prepare_unified_aggregation_instance,
)
from utils.config import load_config


def test_unified_query_union_matches_slices() -> None:
    base = build_instance("Player", include_ground_truth=False)
    table_filter = {"player"}
    seed = 42
    num_docs = 20
    queries_per_slice = 20

    per_slice_ids: set[str] = set()
    for slice_name in AGGREGATION_SLICE_ORDER:
        try:
            inst, _ = prepare_aggregation_slice_instance(
                base,
                slice_name=slice_name,
                num_docs=num_docs,
                num_eval_queries=9999,
                seed=seed,
                query_table_filter=table_filter,
                queries_per_slice=queries_per_slice,
            )
        except RuntimeError:
            continue
        for query in inst.queries:
            per_slice_ids.add(str(query.get("query_id")))

    unified, _ = prepare_unified_aggregation_instance(
        base,
        num_docs=num_docs,
        num_eval_queries=9999,
        seed=seed,
        query_table_filter=table_filter,
        queries_per_slice=queries_per_slice,
    )
    unified_ids = {str(q.get("query_id")) for q in unified.queries}
    assert len(unified_ids) == queries_per_slice * len(AGGREGATION_SLICE_ORDER)
    assert unified_ids == per_slice_ids, (
        f"unified workload query set mismatch: "
        f"only in slices={sorted(per_slice_ids - unified_ids)[:5]}, "
        f"only in unified={sorted(unified_ids - per_slice_ids)[:5]}"
    )


def test_unified_metadata_and_per_slice_counts() -> None:
    cfg = load_config()
    phase0 = cfg.get("phase0", {})
    num_docs = int(phase0.get("num_docs", 20))
    seed = int(cfg["experiment"]["seed"])
    table_filter = set(phase0.get("table_filter", ["player"]))
    queries_per_slice = int(phase0.get("queries_per_slice", 20))

    base = build_instance("Player", include_ground_truth=False)
    per_slice_total = 0
    for slice_name in AGGREGATION_SLICE_ORDER:
        inst, _ = prepare_aggregation_slice_instance(
            base,
            slice_name=slice_name,
            num_docs=num_docs,
            num_eval_queries=9999,
            seed=seed,
            query_table_filter=table_filter,
            queries_per_slice=queries_per_slice,
        )
        per_slice_total += len(inst.queries)
        assert len(inst.queries) == queries_per_slice

    unified, _ = prepare_unified_aggregation_instance(
        base,
        num_docs=num_docs,
        num_eval_queries=9999,
        seed=seed,
        query_table_filter=table_filter,
        queries_per_slice=queries_per_slice,
    )
    assert unified.metadata.get("workload_mode") == "unified"
    assert unified.metadata.get("aggregation_slice") == UNIFIED_WORKLOAD_NAME
    assert len(unified.queries) <= per_slice_total
    assert len(unified.queries) >= 1


def main() -> None:
    test_unified_query_union_matches_slices()
    test_unified_metadata_and_per_slice_counts()
    print("unified workload tests passed")


if __name__ == "__main__":
    main()
