#!/usr/bin/env python3
"""Histogram winning config dimensions and summarize viable search space."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))

from pipeline.group_by_category_error import (
    build_and_write_config_winner_analysis,
    build_config_leaderboard,
    format_config_winner_dimension_histograms,
    format_viable_config_search_space,
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
        f"No per_config in {grid_path} or {checkpoint_path}. "
        "Run test_config_grid with evaluation first."
    )


def _load_leaderboard(output_dir: Path) -> dict:
    leaderboard_path = output_dir / "config_leaderboard.json"
    if leaderboard_path.is_file():
        return json.loads(leaderboard_path.read_text(encoding="utf-8"))

    per_config = _load_per_config(output_dir)
    manifest_path = output_dir / "manifest.json"
    query_ids = None
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        n_queries = int(manifest.get("n_test_queries") or 0)
        if n_queries:
            query_ids = []
            for entry in per_config.values():
                for row in entry.get("per_query") or []:
                    qid = str(row.get("query_id", ""))
                    if qid and qid not in query_ids:
                        query_ids.append(qid)
                if len(query_ids) >= n_queries:
                    break
            query_ids = sorted(query_ids)[:n_queries] if query_ids else None

    return build_config_leaderboard(per_config, query_ids=query_ids)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build per-dimension histograms of winning configs and summarize which "
            "configs ever win at least one query."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Config grid output directory (default: results/config_grid_test)",
    )
    args = parser.parse_args()

    cfg = load_config()
    results_dir = Path(cfg["paths"]["results_dir"])
    output_dir = args.output_dir or (results_dir / "config_grid_test")
    output_dir.mkdir(parents=True, exist_ok=True)

    leaderboard = _load_leaderboard(output_dir)
    analysis = build_and_write_config_winner_analysis(leaderboard, output_dir)

    print(format_config_winner_dimension_histograms(analysis["dimension_histograms"]))
    print()
    print(format_viable_config_search_space(analysis["viable_search_space"]))
    print()
    print(f"Histogram JSON: {output_dir / 'config_winner_dimension_histograms.json'}")
    print(f"Charts dir: {analysis['dimension_histograms'].get('charts_dir')}")
    print(f"Viable search space: {output_dir / 'viable_config_search_space.json'}")


if __name__ == "__main__":
    main()
