#!/usr/bin/env python3
"""Is the SPP search space budget-constrained: does token cost change which
config is "best"?

Every pipeline config has a token cost:
  cost(config) = extraction_token_cost (shared/fixed, same for all configs in
                 a run since extraction is cached and reused) +
                 population_token_cost (config-specific: only LLM-backed
                 population steps -- norm_llm, miss_llm, coerce_llm, er_llm --
                 spend tokens; dictionary/embedding/heuristic strategies cost 0)

If accuracy is roughly flat across configs (as seen for several datasets),
but LLM-backed configs cost meaningfully more tokens than non-LLM configs for
the same or worse accuracy, then under a real budget constraint the cheap
configs dominate on a cost-adjusted basis, and picking the "best" config
without accounting for budget is misleading.

This script:
  1. Loads grid_results.json (manifest.extraction_token_cost +
     per_config[cid].population_token_cost).
  2. Computes total cost per config = extraction_token_cost + population_token_cost.
  3. Ranks configs by accuracy metric (default macro_f1) and separately by
     cost, and reports the accuracy-vs-cost Pareto frontier: configs that are
     not dominated (no other config is both cheaper AND at least as accurate).
  4. Simulates budget caps: for a range of token budgets B, reports the best
     achievable accuracy using only configs with cost <= B ("what if we
     couldn't afford anything above token budget B").

Usage:
  python -m diagnostics.config_budget_analysis --dataset Player
  python -m diagnostics.config_budget_analysis \
      --results-file results/Player/config_grid_test_Player/grid_results.json \
      --metric macro_f1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(results_file: Path) -> tuple[dict, dict]:
    data = json.loads(results_file.read_text(encoding="utf-8"))
    per_config = data.get("per_config")
    manifest = data.get("manifest", {})
    if not per_config:
        raise SystemExit(f"No 'per_config' block found in {results_file}")
    return per_config, manifest


def _config_accuracy(entry: dict, *, metric: str) -> float | None:
    if metric in entry:
        return entry.get(metric)
    # per-query aggregate fallbacks (e.g. mean_macro_f1 computed by _summarize_per_config)
    alt = f"mean_{metric}"
    if alt in entry:
        return entry.get(alt)
    rows = entry.get("per_query") or []
    vals = [r.get(metric) for r in rows if r.get(metric) is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _config_cost(entry: dict, *, extraction_token_cost: float) -> tuple[float, float, int]:
    """Return (total_cost, population_token_cost, population_llm_calls)."""
    pop_cost = float(entry.get("population_token_cost", 0.0) or 0.0)
    pop_calls = int(entry.get("population_llm_calls", 0) or 0)
    return extraction_token_cost + pop_cost, pop_cost, pop_calls


def _pareto_frontier(
    points: list[tuple[str, float, float]],
    *,
    lower_is_better: bool,
) -> list[tuple[str, float, float]]:
    """points: (config_id, cost, accuracy). Returns non-dominated points,
    sorted by cost ascending. A point is dominated if another point has
    cost <= its cost AND accuracy at least as good (better if tie on cost)."""
    def better_or_equal(a_acc: float, b_acc: float) -> bool:
        return a_acc <= b_acc if lower_is_better else a_acc >= b_acc

    frontier: list[tuple[str, float, float]] = []
    for cid, cost, acc in points:
        dominated = False
        for cid2, cost2, acc2 in points:
            if cid2 == cid:
                continue
            if cost2 <= cost and better_or_equal(acc, acc2) and (cost2 < cost or acc2 != acc):
                dominated = True
                break
        if not dominated:
            frontier.append((cid, cost, acc))
    frontier.sort(key=lambda t: t[1])
    return frontier


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-file", type=Path, default=None)
    ap.add_argument("--dataset", default=None)
    ap.add_argument("--metric", default="macro_f1",
                    help="Accuracy metric to trade off against cost. "
                         "'macro_f1' (higher=better) or 'mean_relative_error_pct' "
                         "(lower=better).")
    ap.add_argument("--budget-steps", type=int, default=10,
                    help="Number of simulated budget caps between min and max cost.")
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

    lower_is_better = args.metric in {"mean_relative_error_pct", "query_error"}
    per_config, manifest = _load(results_file)
    extraction_token_cost = float(manifest.get("extraction_token_cost", 0.0) or 0.0)

    rows: list[tuple[str, float, float, float, int]] = []  # cid, cost, acc, pop_cost, pop_calls
    missing_acc = 0
    for cid, entry in per_config.items():
        acc = _config_accuracy(entry, metric=args.metric)
        if acc is None:
            missing_acc += 1
            continue
        cost, pop_cost, pop_calls = _config_cost(entry, extraction_token_cost=extraction_token_cost)
        rows.append((cid, cost, float(acc), pop_cost, pop_calls))

    if not rows:
        raise SystemExit(f"No configs with metric '{args.metric}' found.")

    n_llm_configs = sum(1 for _, _, _, pop_cost, _ in rows if pop_cost > 0)
    n_free_configs = len(rows) - n_llm_configs

    print("=" * 72)
    print(f"Budget / cost analysis  |  {results_file}")
    print("=" * 72)
    print(f"Configs scored               : {len(rows)}  (missing metric: {missing_acc})")
    print(f"Shared extraction token cost : {extraction_token_cost:,.0f} (fixed, all configs)")
    print(f"Configs with LLM population steps (extra cost > 0): {n_llm_configs}")
    print(f"Configs with zero-cost population (dictionary/embedding/heuristic): {n_free_configs}")
    print()

    costs = [r[1] for r in rows]
    print(f"Total cost per config  min={min(costs):,.0f}  median={sorted(costs)[len(costs)//2]:,.0f}  "
          f"max={max(costs):,.0f}")
    print()

    # Best config ignoring cost.
    best_ignoring_cost = (min if lower_is_better else max)(rows, key=lambda r: r[2])
    # Cheapest config.
    cheapest = min(rows, key=lambda r: r[1])
    print(">>> Best config ignoring cost:")
    print(f"    {best_ignoring_cost[0]}  metric={best_ignoring_cost[2]:.4f}  "
          f"cost={best_ignoring_cost[1]:,.0f}")
    print(">>> Cheapest config:")
    print(f"    {cheapest[0]}  metric={cheapest[2]:.4f}  cost={cheapest[1]:,.0f}")
    print()

    points = [(cid, cost, acc) for cid, cost, acc, _, _ in rows]
    frontier = _pareto_frontier(points, lower_is_better=lower_is_better)
    print(f">>> Pareto frontier (cost vs. {args.metric}, {len(frontier)} non-dominated configs):")
    for cid, cost, acc in frontier:
        print(f"    cost={cost:>10,.0f}  {args.metric}={acc:.4f}  {cid}")
    print()

    if max(costs) == min(costs):
        print(">>> KEY RESULT: every config has IDENTICAL cost "
              f"({costs[0]:,.0f} tokens) -- no LLM-backed population steps were "
              "used, or extraction cost dominates and population steps are "
              "free (dictionary/embedding/heuristic strategies).")
        print("    => Cost cannot differentiate configs here; the accuracy "
              "comparison is unconfounded by budget.")
    elif best_ignoring_cost[0] == cheapest[0]:
        print(">>> KEY RESULT: the cheapest config is ALSO the best config.")
        print("    => No budget trade-off exists for this dataset/config space; "
              "cost is not a confound for the accuracy comparison.")
    elif len(frontier) <= 1:
        print(">>> KEY RESULT: one config dominates all others on both cost and "
              "accuracy.")
        print("    => Cost is irrelevant here; that config is simply best.")
    else:
        print(">>> KEY RESULT: cost and accuracy trade off -- no single config "
              "is best on both axes.")
        print("    => The 'best' config depends on the token budget available. "
              "See the budget simulation below.")
    print()

    # Budget simulation.
    lo, hi = min(costs), max(costs)
    if hi == lo:
        print(">>> Budget simulation skipped: all configs cost the same "
              f"({lo:,.0f} tokens); no budget cap can differentiate them.")
        print("=" * 72)
        return
    print(f">>> Budget simulation ({args.budget_steps} steps from {lo:,.0f} to {hi:,.0f}):")
    print(f"{'budget':>12}  {'affordable':>10}  {'best_'+args.metric:>16}  best_config")
    seen_best: set[str] = set()
    if hi == lo:
        steps = [lo]
    else:
        step_size = (hi - lo) / (args.budget_steps - 1) if args.budget_steps > 1 else (hi - lo)
        steps = [lo + i * step_size for i in range(args.budget_steps)]
    for budget in steps:
        affordable = [r for r in rows if r[1] <= budget]
        if not affordable:
            print(f"{budget:>12,.0f}  {0:>10}  {'--':>16}  (nothing affordable)")
            continue
        best = (min if lower_is_better else max)(affordable, key=lambda r: r[2])
        seen_best.add(best[0])
        print(f"{budget:>12,.0f}  {len(affordable):>10}  {best[2]:>16.4f}  {best[0]}")

    print()
    print(f"Distinct configs that were 'best under some budget': {len(seen_best)}")
    if len(seen_best) > 1:
        print("    => The optimal config CHANGES as budget changes -- budget-aware "
              "config selection matters for this dataset.")
    else:
        print("    => The same config wins regardless of budget -- budget does not "
              "change the answer here.")
    print("=" * 72)


if __name__ == "__main__":
    main()
