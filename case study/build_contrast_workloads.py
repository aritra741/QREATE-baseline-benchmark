#!/usr/bin/env python3
"""Author and validate contrast workloads for every non-Player UDA-Bench dataset.

Usage:
  python3 "case study/build_contrast_workloads.py"
  python3 "case study/build_contrast_workloads.py" --only art,legal
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

CASE = Path(__file__).resolve().parent
if str(CASE) not in sys.path:
    sys.path.insert(0, str(CASE))

from contrast_lib.common import LOADERS, validate, write_workloads  # noqa: E402

DATASETS = {
    "art": "contrast_lib.art",
    "cspaper": "contrast_lib.cspaper",
    "finan": "contrast_lib.finan",
    "legal": "contrast_lib.legal",
    "med": "contrast_lib.med",
    "sec": "contrast_lib.sec",
}


def build_one(key: str) -> None:
    module = importlib.import_module(DATASETS[key])
    dataset = module.DATASET
    conn = LOADERS[dataset]()
    errors = validate(conn, module.WORKLOADS)
    if errors:
        print(f"VALIDATION FAILED for {dataset}")
        for err in errors:
            print(err)
        raise SystemExit(1)
    write_workloads(
        dataset,
        module.WORKLOADS,
        join_notes=getattr(module, "JOIN_NOTES", None),
    )
    print(f"{dataset}: all workloads validated and written")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated dataset keys: art,cspaper,finan,legal,med,sec",
    )
    args = parser.parse_args()
    keys = [k.strip().lower() for k in args.only.split(",") if k.strip()] or list(DATASETS)
    unknown = [k for k in keys if k not in DATASETS]
    if unknown:
        raise SystemExit(f"Unknown dataset keys: {unknown}. Expected {sorted(DATASETS)}")
    for key in keys:
        build_one(key)


if __name__ == "__main__":
    main()
