#!/usr/bin/env python3
"""Validate train/dev/test workload split integrity."""

from __future__ import annotations

import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from data.aggregation_slices import AGGREGATION_SLICE_ORDER
from data.workload_splits import create_train_dev_test_split, load_split_queries
from utils.config import load_config


def test_split_counts_and_disjointness() -> None:
    report = create_train_dev_test_split()
    assert report["totals"]["train"] >= 100
    assert report["totals"]["dev"] == 25
    assert report["totals"]["test"] == 25
    for slice_name in AGGREGATION_SLICE_ORDER:
        counts = report["counts_per_slice"][slice_name]
        assert counts == {"train": 20, "dev": 5, "test": 5}, counts

    train_ids = {q["query_id"] for q in report["splits"]["train"]}
    dev_ids = {q["query_id"] for q in report["splits"]["dev"]}
    test_ids = {q["query_id"] for q in report["splits"]["test"]}
    assert train_ids.isdisjoint(dev_ids)
    assert train_ids.isdisjoint(test_ids)
    assert dev_ids.isdisjoint(test_ids)
    assert report["test_held_out"] is True


def test_manifest_roundtrip() -> None:
    cfg = load_config()
    results_dir = Path(cfg["paths"]["results_dir"])
    train = load_split_queries("train", results_dir=results_dir)
    assert len(train) == 100
    assert all((q.get("metadata") or {}).get("split") == "train" for q in train)


def main() -> None:
    test_split_counts_and_disjointness()
    test_manifest_roundtrip()
    print("workload split tests passed")


if __name__ == "__main__":
    main()
