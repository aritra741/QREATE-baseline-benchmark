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


def _build_score_matrix(per_config: dict) -> dict[str, dict[str, float]]:
    """Return {query_id: {config_id: macro_f1}}."""
    matrix: dict[str, dict[str, float]] = defaultdict(dict)
    for cid, entry in per_config.items():
        for row in entry.get("per_query", []) or []:
            qid = str(row.get("query_id", ""))
            f1 = row.get("macro_f1")
            if qid and f1 is not None:
                matrix[qid][cid] = float(f1)
    return matrix


def _tied_best_sets(
    matrix: dict[str, dict[str, float]],
    *,
    tolerance: float,
) -> dict[str, set[str]]:
    """For each query, the set of configs within `tolerance` of the max score."""
    best: dict[str, set[str]] = {}
    for qid, scores in matrix.items():
        if not scores:
            continue
        top = max(scores.values())
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-file", type=Path, default=None,
                    help="Path to grid_results.json")
    ap.add_argument("--dataset", default=None,
                    help="Dataset name; used to locate default results dir")
    ap.add_argument("--tolerance", type=float, default=1e-9,
                    help="Score gap counted as a tie (default 1e-9 = exact). "
                         "Try 0.01 to treat near-ties as ties.")
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

    per_config = _load_per_config(results_file)
    matrix = _build_score_matrix(per_config)
    n_queries = len(matrix)
    n_configs = len(per_config)

    if n_queries == 0:
        raise SystemExit("No per-query scores found (per_query lists are empty).")

    best_sets = _tied_best_sets(matrix, tolerance=args.tolerance)

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
    print(f"Tie tolerance           : {args.tolerance}")
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
