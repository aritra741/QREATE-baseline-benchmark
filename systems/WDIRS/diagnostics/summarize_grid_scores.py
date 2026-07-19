"""Report actual error/score numbers from a Phase-2 config-grid run.

`run_config_grid.py` writes `viable_config_search_space.json`, which only
reports *which* configs are ever tied-best for some query -- not their
absolute error/score. This script reads the sibling `config_grid_results.json`
(the `per_config[config_id]["mean_query_error"]` field) and reports:

  - the best (lowest mean error) config and its score,
  - the worst config and its score,
  - the mean/median across all evaluated configs,
  - per-query best achievable error (oracle), restricted to config-sensitive
    queries, since config-insensitive queries are an extraction floor no
    PopulationConfig axis can move.

Usage:
    python diagnostics/summarize_grid_scores.py results/spp_config_grid_Player/config_grid_results.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List


def _score(err: float) -> float:
    """Convert error (0=perfect, 1=worst) into a score (1=perfect, 0=worst)."""
    return 1.0 - err


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_json", type=str, help="Path to config_grid_results.json")
    parser.add_argument(
        "--top-k", type=int, default=5, help="How many best/worst configs to show"
    )
    args = parser.parse_args()

    path = Path(args.results_json).expanduser().resolve()
    data: Dict[str, Any] = json.loads(path.read_text())
    per_config: Dict[str, Any] = data["per_config"]

    scored: List[Dict[str, Any]] = []
    for cid, entry in per_config.items():
        mean_err = entry.get("mean_query_error")
        if mean_err is None:
            continue
        scored.append({"config_id": cid, "mean_query_error": mean_err, "score": _score(mean_err)})

    if not scored:
        print("No configs with a valid mean_query_error -- every query failed to execute?")
        return

    scored.sort(key=lambda r: r["mean_query_error"])
    errors = [r["mean_query_error"] for r in scored]

    print(f"dataset={data.get('dataset')} model={data.get('model')}")
    print(f"configs evaluated: {len(scored)}")
    print(
        f"mean_query_error across configs: mean={statistics.mean(errors):.4f} "
        f"median={statistics.median(errors):.4f} "
        f"min={min(errors):.4f} max={max(errors):.4f} stdev={statistics.pstdev(errors):.4f}"
    )
    print(
        f"=> as a score (1 - error, higher is better): "
        f"best={_score(min(errors)):.4f} worst={_score(max(errors)):.4f} "
        f"mean={_score(statistics.mean(errors)):.4f}"
    )

    print(f"\nTop {args.top_k} configs (lowest mean_query_error = best):")
    for row in scored[: args.top_k]:
        print(f"  {row['config_id']}  error={row['mean_query_error']:.4f}  score={row['score']:.4f}")

    print(f"\nBottom {args.top_k} configs (highest mean_query_error = worst):")
    for row in scored[-args.top_k :]:
        print(f"  {row['config_id']}  error={row['mean_query_error']:.4f}  score={row['score']:.4f}")

    # Per-query oracle (best achievable error per query, across evaluated configs).
    by_query: Dict[str, List[float]] = {}
    for entry in per_config.values():
        for row in entry.get("per_query", []):
            if row["query_error"] is not None:
                by_query.setdefault(row["query_id"], []).append(row["query_error"])

    oracle_errors = [min(v) for v in by_query.values()]
    if oracle_errors:
        print(
            f"\nPer-query oracle (best config chosen per query): "
            f"mean_error={statistics.mean(oracle_errors):.4f} "
            f"=> mean_score={_score(statistics.mean(oracle_errors)):.4f}"
        )
        print(
            "(This is the ceiling if you could route each query to its own best "
            "config; the single-best-config numbers above are the realistic "
            "one-config-for-everything score.)"
        )


if __name__ == "__main__":
    main()
