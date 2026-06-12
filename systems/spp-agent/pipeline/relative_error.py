"""Relative error reporting for numeric aggregate cells in query evaluation."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from evaluation.query_manifest import QueryManifest
from evaluation.row_matcher import MatchResult

HISTOGRAM_BUCKETS: list[tuple[str, float, float | None]] = [
    ("0-20%", 0.0, 20.0),
    ("20-40%", 20.0, 40.0),
    ("40-60%", 40.0, 60.0),
    ("60-80%", 60.0, 80.0),
    ("80-100%", 80.0, 100.0),
    (">100%", 100.0, None),
]


def cell_relative_error_pct(pred: object, gold: object) -> float:
    """|pred - gold| / |gold| * 100; gold=0 uses exact-match rule from AggComparator."""
    try:
        pred_val = float(pred) if not isinstance(pred, str) else float(pred.strip())
        gold_val = float(gold) if not isinstance(gold, str) else float(gold.strip())
    except (TypeError, ValueError):
        return 100.0

    if not math.isfinite(pred_val) or not math.isfinite(gold_val):
        return 100.0

    if gold_val == 0:
        return 0.0 if pred_val == gold_val else 100.0

    return abs(pred_val - gold_val) / abs(gold_val) * 100.0


def _aggregate_column_names(manifest: QueryManifest) -> list[str]:
    cols: list[str] = []
    for item in manifest.parsed.select_items:
        if not item.is_agg:
            continue
        if item.output_name in manifest.stop_columns:
            continue
        cols.append(item.output_name)
    return cols


def query_relative_error_pct(match_result: MatchResult, manifest: QueryManifest) -> float | None:
    """
    Average relative error (%) across numeric aggregate cells on aligned rows.
    Unmatched gold/pred rows each contribute 100%.
    """
    agg_cols = _aggregate_column_names(manifest)
    if not agg_cols:
        return None

    gold_df = match_result.gold_aligned
    pred_df = match_result.pred_aligned
    errors: list[float] = []

    for col in agg_cols:
        if col not in gold_df.columns or col not in pred_df.columns:
            continue
        for pred_cell, gold_cell in zip(pred_df[col], gold_df[col]):
            errors.append(cell_relative_error_pct(pred_cell, gold_cell))

    unmatched_gold = max(0, match_result.len_gold - match_result.matched_rows)
    unmatched_pred = max(0, match_result.len_pred - match_result.matched_rows)
    errors.extend([100.0] * (unmatched_gold + unmatched_pred))

    if not errors:
        return None
    return float(sum(errors) / len(errors))


def summarize_relative_errors(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "max": 0.0, "min": 0.0, "std": 0.0}
    if len(values) == 1:
        return {
            "mean": float(values[0]),
            "max": float(values[0]),
            "min": float(values[0]),
            "std": 0.0,
        }
    return {
        "mean": float(statistics.mean(values)),
        "max": float(max(values)),
        "min": float(min(values)),
        "std": float(statistics.stdev(values)),
    }


def _histogram_bucket_label(value: float) -> str:
    if value > 100:
        return ">100%"
    if value >= 80:
        return "80-100%"
    if value >= 60:
        return "60-80%"
    if value >= 40:
        return "40-60%"
    if value >= 20:
        return "20-40%"
    return "0-20%"


def histogram_bucket_counts(values: list[float]) -> dict[str, int]:
    counts = {label: 0 for label, _, _ in HISTOGRAM_BUCKETS}
    for value in values:
        counts[_histogram_bucket_label(value)] += 1
    return counts


def save_relative_error_histogram(
    slice_name: str,
    values: list[float],
    output_path: Path,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [label for label, _, _ in HISTOGRAM_BUCKETS]
    counts = [histogram_bucket_counts(values).get(label, 0) for label in labels]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(labels, counts, color="#4C78A8", edgecolor="white")
    ax.set_title(f"Relative error distribution — {slice_name}")
    ax.set_xlabel("Relative error bucket")
    ax.set_ylabel("Number of queries")
    ax.set_ylim(bottom=0)
    for idx, count in enumerate(counts):
        if count:
            ax.text(idx, count, str(count), ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def build_slice_relative_error_report(
    slice_name: str,
    per_query: list[dict],
    *,
    results_dir: Path,
    histogram_suffix: str = "",
) -> dict[str, Any]:
    """Build slice report, save histogram PNG, return JSON-serializable dict."""
    entries: list[dict[str, Any]] = []
    values: list[float] = []

    for row in per_query:
        rel = row.get("relative_error_pct")
        if rel is None:
            continue
        rel_f = float(rel)
        values.append(rel_f)
        entries.append(
            {
                "query_id": row.get("query_id"),
                "macro_f1": row.get("macro_f1"),
                "relative_error_pct": rel_f,
                "corpus_infeasible": bool(row.get("corpus_infeasible", False)),
            }
        )

    stats = summarize_relative_errors(values)
    histogram = histogram_bucket_counts(values)
    histogram_path = results_dir / f"relative_error_histogram_{slice_name}{histogram_suffix}.png"
    if values:
        save_relative_error_histogram(slice_name, values, histogram_path)

    return {
        "slice": slice_name,
        "relative_error_pct_per_query": [round(v, 4) for v in values],
        "per_query": entries,
        "statistics": {k: round(v, 4) for k, v in stats.items()},
        "histogram": histogram,
        "histogram_path": str(histogram_path) if values else None,
        "n_queries_with_aggregate": len(values),
    }


def print_slice_relative_error_report(report: dict[str, Any]) -> None:
    slice_name = report["slice"]
    values = report["relative_error_pct_per_query"]
    stats = report["statistics"]
    histogram = report["histogram"]

    formatted = ", ".join(f"{v:.1f}%" for v in values) if values else "(none)"
    print(f"\n### {slice_name} — relative error")
    print(f"Per-query: [{formatted}]")
    if values:
        print(
            f"Statistics: mean={stats['mean']:.2f}% "
            f"max={stats['max']:.2f}% min={stats['min']:.2f}% std={stats['std']:.2f}%"
        )
        hist_line = ", ".join(f"{bucket}: {count}" for bucket, count in histogram.items())
        print(f"Histogram: {hist_line}")
        if report.get("histogram_path"):
            print(f"Chart: {report['histogram_path']}")
    else:
        print("No numeric aggregate queries to report.")


def write_relative_error_report(
    slice_reports: list[dict[str, Any]],
    output_path: Path,
) -> Path:
    payload = {"slices": {r["slice"]: r for r in slice_reports}}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return output_path
