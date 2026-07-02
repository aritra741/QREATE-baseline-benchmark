#!/usr/bin/env python3
"""Rank all configs in a grid_results.json by a chosen metric and print the
top-N. Useful quick "who's actually winning" check, independent of the
per-query set-cover analysis.

Usage:
  python -m diagnostics.rank_configs --dataset Legal --metric mean_relative_error_pct
  python -m diagnostics.rank_configs --results-file results/config_grid_test/grid_results.json --metric macro_f1 --top 15
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _config_metric(entry: dict, *, metric: str) -> float | None:
    if metric in entry:
        return entry.get(metric)
    alt = f"mean_{metric}"
    if alt in entry:
        return entry.get(alt)
    rows = entry.get("per_query") or []
    vals = [
        r.get(metric) for r in rows
        if r.get(metric) is not None and r.get("pred_rows", 0) >= 0 and r.get("gold_rows", 0) >= 0
    ]
    if not vals:
        return None
    return sum(vals) / len(vals)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-file", type=Path, default=None)
    ap.add_argument("--dataset", default=None)
    ap.add_argument("--metric", default="mean_relative_error_pct",
                    help="'mean_relative_error_pct' (lower=better, aggregation "
                         "queries) or 'macro_f1' (higher=better).")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--max-relative-error-pct", type=float, default=None,
                    help="Exclude configs whose mean value exceeds this cap "
                         "(filters degenerate near-zero-denominator blowups).")
    args = ap.parse_args()

    results_file = args.results_file
    if results_file is None:
        if not args.dataset:
            raise SystemExit("Provide --results-file or --dataset")
        results_file = Path(f"results/{args.dataset}/config_grid_test_{args.dataset}/grid_results.json")
    if not results_file.is_file():
        raise SystemExit(f"Results file not found: {results_file}")

    lower_is_better = args.metric in {"mean_relative_error_pct", "query_error"}
    per_config = json.loads(results_file.read_text(encoding="utf-8")).get("per_config", {})
    if not per_config:
        raise SystemExit("No 'per_config' block found.")

    rows = []
    for cid, entry in per_config.items():
        val = _config_metric(entry, metric=args.metric)
        if val is None:
            continue
        if (
            args.max_relative_error_pct is not None
            and args.metric == "mean_relative_error_pct"
            and val > args.max_relative_error_pct
        ):
            continue
        rows.append((cid, val))

    rows.sort(key=lambda r: r[1], reverse=not lower_is_better)

    print(f"Ranked by {args.metric} ({'lower' if lower_is_better else 'higher'}=better), "
          f"{len(rows)}/{len(per_config)} configs scored:\n")
    for i, (cid, val) in enumerate(rows[: args.top], start=1):
        print(f"{i:>3}. {val:>12.4f}  {cid}")

    if len(rows) > args.top:
        print(f"\n... ({len(rows) - args.top} more)")

    print(f"\nWorst: {rows[-1][1]:.4f}  {rows[-1][0]}")


if __name__ == "__main__":
    main()
