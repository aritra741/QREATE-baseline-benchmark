#!/usr/bin/env python3
"""Print exact calculation path for the largest category_error terms."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))

from pipeline.group_by_category_error import (
    build_top_category_error_audit,
    format_top_category_error_calculations,
    write_top_category_error_audit,
)
from utils.config import load_config


def _load_per_config(output_dir: Path) -> dict:
    grid_path = output_dir / "grid_results.json"
    checkpoint_path = output_dir / "checkpoint.json"
    if grid_path.is_file():
        payload = json.loads(grid_path.read_text(encoding="utf-8"))
        per_config = payload.get("per_config")
        if per_config:
            return per_config
    if checkpoint_path.is_file():
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        per_config = payload.get("per_config")
        if per_config:
            return per_config
    raise FileNotFoundError(
        f"No per_config in {grid_path} or {checkpoint_path}. Run test_config_grid with evaluation first."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show numerator/denominator for the largest category_error terms."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Config grid output directory (default: results/config_grid_test)",
    )
    parser.add_argument(
        "--config-id",
        default=None,
        help="Limit to one config (default: all evaluated configs)",
    )
    parser.add_argument(
        "--top-errors",
        type=int,
        default=10,
        help="How many largest category errors to print (default: 10)",
    )
    args = parser.parse_args()

    cfg = load_config()
    output_dir = args.output_dir or (Path(cfg["paths"]["results_dir"]) / "config_grid_test")
    per_config = _load_per_config(output_dir)
    config_ids = [args.config_id] if args.config_id else None

    payload = build_top_category_error_audit(
        per_config,
        config_ids=config_ids,
        limit=args.top_errors,
    )
    out_path = output_dir / "category_error_top_calculations.json"
    write_top_category_error_audit(payload, out_path)
    print(format_top_category_error_calculations(payload.get("top_errors") or []))
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
