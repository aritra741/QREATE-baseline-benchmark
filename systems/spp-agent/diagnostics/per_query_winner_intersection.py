#!/usr/bin/env python3
"""Does a single config win every query, or is a *set* of configs required?

This answers the core question behind the SPP premise: given the per-query
macro-F1 of every config (from a config-grid run), is there ONE config that is
(tied-)best on every query simultaneously?

  - If the intersection of per-query tied-best config sets is NON-EMPTY, then a
    single config covers the whole workload  ->  SPP* = {that config}  ->  the
    per-query search is vacuous for this dataset.
  - If the intersection is EMPTY, no single config wins everywhere: different
    queries need different configs  ->  a set SPP of size > 1 is required  ->
    the search is justified.

We also compute the minimum-size portfolio (greedy set cover): the smallest
number of configs such that every query has at least one of them in its
tied-best set.  That is the effective |SPP*| under this scoring rule.

Reads grid_results.json (top-level "per_config" -> config_id -> "per_query"
list of {query_id, macro_f1}).  Standalone: only stdlib imports, so it runs
anywhere without the spp-agent environment.

Usage:
  python -m diagnostics.per_query_winner_intersection \
      --results-file results/Finan/config_grid_test_Finan/grid_results.json

  # or point at a dataset's default results dir:
  python -m diagnostics.per_query_winner_intersection --dataset Finan
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def _load_per_config(results_file: Path) -> dict:
    data = json.loads(results_file.read_text(encoding="utf-8"))
    per_config = data.get("per_config")
    if not per_config:
        raise SystemExit(f"No 'per_config' block found in {results_file}")
    return per_config


def _build_score_matrix(per_config: dict, *, metric: str) -> dict[str, dict[str, float]]:
    """Return {query_id: {config_id: metric_value}}.

    metric is a key in each per_query row, e.g. 'macro_f1' (higher=better) or
    'mean_relative_error_pct' / 'query_error' (lower=better).
    """
    matrix: dict[str, dict[str, float]] = defaultdict(dict)
    for cid, entry in per_config.items():
        for row in entry.get("per_query", []) or []:
            qid = str(row.get("query_id", ""))
            val = row.get(metric)
            if qid and val is not None:
                matrix[qid][cid] = float(val)
    return matrix


def _tied_best_sets(
    matrix: dict[str, dict[str, float]],
    *,
    tolerance: float,
    lower_is_better: bool,
) -> dict[str, set[str]]:
    """For each query, the set of configs within `tolerance` of the best score.

    'Best' is min(scores) if lower_is_better else max(scores). Tolerance is an
    absolute gap on the metric's own scale (e.g. percentage points for
    mean_relative_error_pct, or 0-1 units for macro_f1).
    """
    best: dict[str, set[str]] = {}
    for qid, scores in matrix.items():
        if not scores:
            continue
        top = min(scores.values()) if lower_is_better else max(scores.values())
        if lower_is_better:
            best[qid] = {cid for cid, s in scores.items() if s - top <= tolerance}
        else:
            best[qid] = {cid for cid, s in scores.items() if top - s <= tolerance}
    return best


def _greedy_set_cover(best_sets: dict[str, set[str]]) -> list[str]:
    """Smallest set of configs so every query has >=1 of them in its tied-best set."""
    uncovered = set(best_sets.keys())
    # config -> set of queries it is tied-best on
    config_to_queries: dict[str, set[str]] = defaultdict(set)
    for qid, configs in best_sets.items():
        for cid in configs:
            config_to_queries[cid].add(qid)

    portfolio: list[str] = []
    while uncovered:
        # pick the config covering the most currently-uncovered queries
        best_cid = max(
            config_to_queries,
            key=lambda c: len(config_to_queries[c] & uncovered),
        )
        covered_now = config_to_queries[best_cid] & uncovered
        if not covered_now:
            break  # no progress possible (shouldn't happen if data is consistent)
        portfolio.append(best_cid)
        uncovered -= covered_now
    return portfolio


# Metrics known to be "lower is better" (errors). Everything else defaults to
# "higher is better" (scores like macro_f1, query_accuracy).
_LOWER_IS_BETTER_METRICS = {
    "mean_relative_error_pct",
    "query_error",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-file", type=Path, default=None,
                    help="Path to grid_results.json")
    ap.add_argument("--dataset", default=None,
                    help="Dataset name; used to locate default results dir")
    ap.add_argument("--metric", default="macro_f1",
                    help="Per-query field to rank configs on. Common choices: "
                         "'macro_f1' (higher=better, 0-1 scale), "
                         "'mean_relative_error_pct' (lower=better, percentage "
                         "points -- the right metric for aggregation-only "
                         "workloads), 'query_error' (lower=better, 0-1 scale).")
    ap.add_argument("--tolerance", type=float, default=None,
                    help="Absolute gap on the metric's own scale counted as a "
                         "tie. Default: 1e-9 for macro_f1/query_error (0-1 "
                         "scale), 1.0 (percentage point) for "
                         "mean_relative_error_pct.")
    args = ap.parse_args()

    results_file = args.results_file
    if results_file is None:
        if not args.dataset:
            raise SystemExit("Provide --results-file or --dataset")
        results_file = Path(
            f"results/{args.dataset}/config_grid_test_{args.dataset}/grid_results.json"
        )
    if not results_file.is_file():
        raise SystemExit(f"Results file not found: {results_file}")

    lower_is_better = args.metric in _LOWER_IS_BETTER_METRICS
    if args.tolerance is not None:
        tolerance = args.tolerance
    elif args.metric == "mean_relative_error_pct":
        tolerance = 1.0  # 1 percentage point
    else:
        tolerance = 1e-9

    per_config = _load_per_config(results_file)
    matrix = _build_score_matrix(per_config, metric=args.metric)
    n_queries = len(matrix)
    n_configs = len(per_config)

    if n_queries == 0:
        raise SystemExit(
            f"No per-query values found for metric '{args.metric}' "
            "(per_query lists are empty or missing this field)."
        )

    best_sets = _tied_best_sets(matrix, tolerance=tolerance, lower_is_better=lower_is_better)

    # Intersection across all queries.
    intersection: set[str] | None = None
    for configs in best_sets.values():
        intersection = configs if intersection is None else (intersection & configs)
    intersection = intersection or set()

    portfolio = _greedy_set_cover(best_sets)

    print("=" * 72)
    print(f"Per-query winner analysis  |  {results_file}")
    print("=" * 72)
    print(f"Queries scored          : {n_queries}")
    print(f"Configs evaluated       : {n_configs}")
    print(f"Metric                  : {args.metric} "
          f"({'lower' if lower_is_better else 'higher'}=better)")
    print(f"Tie tolerance           : {tolerance}")
    print()

    sizes = sorted(len(s) for s in best_sets.values())
    print("Per-query tied-best set sizes (how many configs share the best score):")
    print(f"  min={sizes[0]}  median={sizes[len(sizes)//2]}  max={sizes[-1]}")
    print()

    print(">>> KEY RESULT")
    if intersection:
        print(f"  Intersection is NON-EMPTY: {len(intersection)} config(s) are "
              f"tied-best on ALL {n_queries} queries.")
        print("  => A single config covers the whole workload; per-query search "
              "is VACUOUS for this dataset (under this scoring rule).")
        for cid in sorted(intersection)[:10]:
            print(f"     - {cid}")
    else:
        print("  Intersection is EMPTY: NO single config is tied-best on every "
              "query.")
        print(f"  => A SET of configs is required. Minimum portfolio size "
              f"(greedy set cover) = {len(portfolio)}.")
        print("  => The per-query search is JUSTIFIED for this dataset.")
    print()

    print(f"Minimum portfolio to cover all queries ({len(portfolio)} configs):")
    # queries covered per portfolio member
    config_to_queries: dict[str, set[str]] = defaultdict(set)
    for qid, configs in best_sets.items():
        for cid in configs:
            config_to_queries[cid].add(qid)
    remaining = set(best_sets.keys())
    for cid in portfolio:
        covered = config_to_queries[cid] & remaining
        print(f"  - {cid}  (covers {len(covered)} queries)")
        remaining -= covered
    print("=" * 72)


if __name__ == "__main__":
    main()
