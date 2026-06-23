#!/usr/bin/env python3
"""Diagnose whether config grid scores actually vary across configs.

Run from systems/spp-agent/:
  PYTHONPATH=. python diagnostics/inspect_config_score_variance.py \
    --output-dir results/Med/config_grid_test_Med
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))

from pipeline.group_by_category_error import refresh_per_query_row_scores
from optimizer.config_space import parse_config_id
from utils.config import load_config


def _load_per_config(output_dir: Path) -> dict:
    for name in ("grid_results.json", "checkpoint.json"):
        p = output_dir / name
        if p.is_file():
            payload = json.loads(p.read_text(encoding="utf-8"))
            pc = payload.get("per_config")
            if pc:
                return pc
    raise FileNotFoundError(f"No per_config found in {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--n-queries", type=int, default=5,
                        help="Number of queries to inspect in detail")
    args = parser.parse_args()

    per_config = _load_per_config(args.output_dir)
    print(f"Configs loaded: {len(per_config)}")

    # Build query_scores: {qid: {config_id: error}}
    query_scores: dict[str, dict[str, float]] = {}
    for config_id, entry in per_config.items():
        for row in entry.get("per_query") or []:
            qid = str(row.get("query_id", ""))
            refreshed = refresh_per_query_row_scores(row)
            err = refreshed.get("query_error")
            if err is not None:
                query_scores.setdefault(qid, {})[config_id] = float(err)

    print(f"Queries scored: {len(query_scores)}")
    print()

    # For each query: how many unique error values exist across configs?
    print("=== Score variance per query ===")
    print(f"{'query_id':<45} {'n_configs':>9} {'n_unique_errors':>15} {'min_err':>8} {'max_err':>8} {'range':>8}")
    print("-" * 100)
    for qid in sorted(query_scores):
        scores = query_scores[qid]
        values = list(scores.values())
        unique = set(round(v, 6) for v in values)
        mn, mx = min(values), max(values)
        print(f"{qid:<45} {len(values):>9} {len(unique):>15} {mn:>8.4f} {mx:>8.4f} {mx-mn:>8.4f}")

    print()

    # For the first N queries, show the full error distribution across configs
    print(f"=== Detailed error distribution for first {args.n_queries} queries ===")
    for qid in sorted(query_scores)[:args.n_queries]:
        scores = query_scores[qid]
        from collections import Counter
        error_counts = Counter(round(v, 6) for v in scores.values())
        print(f"\nQuery: {qid}")
        print(f"  Unique error values ({len(error_counts)} distinct):")
        for err_val, count in sorted(error_counts.items()):
            pct = count / len(scores) * 100
            sample_configs = [c for c, e in scores.items() if round(e, 6) == err_val][:3]
            print(f"    error={err_val:.6f}  n_configs={count} ({pct:.1f}%)  e.g. {sample_configs[0]}")

    print()

    # Show dimension-level variance: for each dimension value, what's the best achievable error?
    print("=== Dimension-level best-achievable error per query (first 5 queries) ===")
    dims = [("er", "er_strategy"), ("norm", "norm_strategy"), ("miss", "miss_strategy"),
            ("coerce", "type_coercion"), ("unit", "unit_strategy")]
    for qid in sorted(query_scores)[:5]:
        scores = query_scores[qid]
        print(f"\nQuery: {qid}")
        for dim, field in dims:
            best_per_value: dict[str, float] = {}
            for cid, err in scores.items():
                val = str(getattr(parse_config_id(cid), field))
                if val not in best_per_value or err < best_per_value[val]:
                    best_per_value[val] = err
            overall_best = min(best_per_value.values())
            parts = []
            for val, best in sorted(best_per_value.items(), key=lambda x: x[1]):
                marker = " <-- BEST" if best == overall_best else ""
                parts.append(f"{val}={best:.4f}{marker}")
            print(f"  {dim}: {' | '.join(parts)}")


if __name__ == "__main__":
    main()
