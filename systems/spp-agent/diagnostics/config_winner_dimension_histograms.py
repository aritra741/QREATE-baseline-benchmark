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
    grid_per_config: dict = {}
    checkpoint_per_config: dict = {}
    if grid_path.is_file():
        payload = json.loads(grid_path.read_text(encoding="utf-8"))
        grid_per_config = payload.get("per_config") or {}
    if checkpoint_path.is_file():
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        checkpoint_per_config = payload.get("per_config") or {}
    # Prefer whichever source has more completed configs.
    if len(checkpoint_per_config) > len(grid_per_config):
        if checkpoint_per_config:
            return checkpoint_per_config
    if grid_per_config:
        return grid_per_config
    if checkpoint_per_config:
        return checkpoint_per_config
    raise FileNotFoundError(
        f"No per_config in {grid_path} or {checkpoint_path}. "
        "Run test_config_grid with evaluation first."
    )


def _load_query_ids(output_dir: Path, per_config: dict) -> list[str] | None:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    n_queries = int(manifest.get("n_test_queries") or 0)
    if not n_queries:
        return None
    query_ids: list[str] = []
    for entry in per_config.values():
        for row in entry.get("per_query") or []:
            qid = str(row.get("query_id", ""))
            if qid and qid not in query_ids:
                query_ids.append(qid)
    return sorted(query_ids)[:n_queries] if query_ids else None


def _load_leaderboard(output_dir: Path) -> dict:
    """Always rebuild leaderboard from per_config raw scores.

    Loading cached config_leaderboard.json is intentionally avoided because
    the cached version may pre-date the fractional-wins logic and will produce
    incorrect dimension counts (missing win_share_per_config field).
    """
    per_config = _load_per_config(output_dir)
    query_ids = _load_query_ids(output_dir, per_config)
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
        help="Config grid output directory (default: results/<dataset>/config_grid_test_<dataset>)",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Dataset name (e.g. Art, Med, Player). Used to resolve default output-dir.",
    )
    args = parser.parse_args()

    cfg = load_config()
    results_dir = Path(cfg["paths"]["results_dir"])

    if args.output_dir:
        output_dir = args.output_dir
    elif args.dataset:
        from data.dataset_registry import normalize_dataset_name, config_grid_output_dir, results_dir_for_dataset
        ds = normalize_dataset_name(args.dataset)
        ds_results = results_dir_for_dataset(ds)
        output_dir = ds_results / config_grid_output_dir(ds_results, ds)
    else:
        output_dir = results_dir / "config_grid_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    leaderboard = _load_leaderboard(output_dir)
    analysis = build_and_write_config_winner_analysis(leaderboard, output_dir)

    print(format_config_winner_dimension_histograms(analysis["dimension_histograms"]))
    print()
    print(format_viable_config_search_space(analysis["viable_search_space"]))
    print()
    print(f"Dimension histogram JSON: {output_dir / 'config_winner_dimension_histograms.json'}")
    print(f"Dimension charts dir: {analysis['dimension_histograms'].get('charts_dir')}")
    print(f"Viable search space: {output_dir / 'viable_config_search_space.json'}")
    wins_charts = analysis.get("config_wins_charts") or {}
    for scope, path in wins_charts.items():
        if path:
            print(f"Config wins chart [{scope}]: {path}")


if __name__ == "__main__":
    main()
