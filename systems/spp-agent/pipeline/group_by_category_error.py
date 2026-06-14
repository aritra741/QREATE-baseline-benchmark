"""GROUP BY category error metric for aggregation query evaluation."""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_EPSILON = 1e-9
MISSING_CATEGORY_PENALTY = 1.0


def _serialize_category(key: object) -> str:
    if isinstance(key, tuple):
        return "|".join("" if v is None else str(v) for v in key)
    return "" if key is None else str(key)


def _category_key_from_row(row: pd.Series, group_keys: list[str]) -> str:
    from evaluation.utils import format_primary_key

    if not group_keys:
        return "__global__"
    return _serialize_category(format_primary_key(row, group_keys))


def _to_float(value: object) -> float | None:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        if isinstance(value, float) and np.isnan(value):
            return None
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        out = float(value) if not isinstance(value, str) else float(value.strip())
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _matched_relative_error(pred: float, gold: float, *, epsilon: float) -> float:
    denom = max(abs(gold), epsilon)
    return abs(pred - gold) / denom


def _relative_error_denominator(gold: float, *, epsilon: float) -> float:
    return max(abs(gold), epsilon)


def audit_category_errors(
    gold_map: dict[str, float],
    pred_map: dict[str, float],
    *,
    epsilon: float = DEFAULT_EPSILON,
    value_column: str | None = None,
) -> dict[str, Any]:
    """Exact score decomposition for one aggregate column (does not change the metric)."""
    scored = compute_category_errors(gold_map, pred_map, epsilon=epsilon)
    categories = scored["categories_union"]
    category_details: list[dict[str, Any]] = []
    n_gold_zero = 0

    for category in categories:
        in_gold = category in gold_map
        in_pred = category in pred_map
        gold_val = gold_map.get(category) if in_gold else None
        pred_val = pred_map.get(category) if in_pred else None

        if in_gold and gold_val is not None and gold_val == 0.0:
            n_gold_zero += 1

        if in_gold and in_pred:
            status = "matched"
            assert gold_val is not None and pred_val is not None
            denominator = _relative_error_denominator(gold_val, epsilon=epsilon)
            error_term = scored["per_category_error"][category]
            formula = f"|{pred_val} - {gold_val}| / max(|{gold_val}|, {epsilon})"
        elif in_gold:
            status = "missing"
            denominator = None
            error_term = MISSING_CATEGORY_PENALTY
            formula = f"penalty (missing from prediction) = {MISSING_CATEGORY_PENALTY}"
        else:
            status = "extra"
            denominator = None
            error_term = MISSING_CATEGORY_PENALTY
            formula = f"penalty (extra in prediction) = {MISSING_CATEGORY_PENALTY}"

        category_details.append(
            {
                "category": category,
                "status": status,
                "gold_value": gold_val,
                "predicted_value": pred_val,
                "error_term": error_term,
                "relative_error_denominator": denominator,
                "formula": formula,
            }
        )

    sum_category_errors = float(sum(scored["per_category_error"].values()))
    n_union = len(categories)

    return {
        "value_column": value_column,
        "epsilon": epsilon,
        "gold_categories": dict(gold_map),
        "predicted_categories": dict(pred_map),
        "categories_union": categories,
        "category_details": category_details,
        "n_categories_union": n_union,
        "n_gold_zero": n_gold_zero,
        "n_missing": len(scored["missing_categories"]),
        "n_extra": len(scored["extra_categories"]),
        "n_matched": len(scored["matched_categories"]),
        "sum_category_errors": sum_category_errors,
        "query_error": scored["query_error"],
        "query_accuracy": scored["query_accuracy"],
        "average_formula": (
            f"({sum_category_errors}) / {n_union} = {scored['query_error']}"
            if n_union
            else f"empty union -> query_error={scored['query_error']}"
        ),
    }


def audit_group_by_category_error_report(report: dict[str, Any]) -> dict[str, Any]:
    """Attach per-value-column audit blocks to an existing category_error report."""
    if not report:
        return {}
    epsilon = float(report.get("epsilon", DEFAULT_EPSILON))
    by_column = report.get("by_value_column")
    if not by_column:
        return {"query_id": report.get("query_id"), "value_column_audits": []}

    audits = [
        audit_category_errors(
            vr["gold_categories"],
            vr["predicted_categories"],
            epsilon=epsilon,
            value_column=vr.get("value_column"),
        )
        for vr in by_column
    ]

    query_error = float(report.get("query_error", 0.0))
    return {
        "query_id": report.get("query_id"),
        "group_keys": report.get("group_keys"),
        "value_columns": report.get("value_columns"),
        "epsilon": epsilon,
        "value_column_audits": audits,
        "query_error": query_error,
        "query_accuracy": float(report.get("query_accuracy", 1.0 - query_error)),
        "query_error_average_formula": (
            " + ".join(f"{a['query_error']}" for a in audits)
            + f" / {len(audits)} = {query_error}"
            if len(audits) > 1
            else audits[0]["average_formula"] if audits else ""
        ),
        "primary_failure_mode": report.get("primary_failure_mode"),
    }


def format_category_error_audit_log(
    *,
    config_id: str,
    audits: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"CATEGORY ERROR AUDIT — config: {config_id}")
    lines.append("=" * 72)

    for audit in audits:
        lines.append("")
        lines.append(f"Query: {audit.get('query_id')}")
        lines.append(f"  group_keys: {audit.get('group_keys')}")
        lines.append(f"  value_columns: {audit.get('value_columns')}")
        lines.append(f"  epsilon: {audit.get('epsilon')}")
        lines.append(f"  primary_failure_mode: {audit.get('primary_failure_mode')}")

        for col_audit in audit.get("value_column_audits", []):
            lines.append("")
            lines.append(f"  --- value_column: {col_audit.get('value_column')} ---")
            lines.append(
                f"  gold categories ({len(col_audit.get('gold_categories', {}))}): "
                f"{col_audit.get('gold_categories')}"
            )
            lines.append(
                f"  predicted categories ({len(col_audit.get('predicted_categories', {}))}): "
                f"{col_audit.get('predicted_categories')}"
            )
            lines.append(
                f"  union for scoring ({col_audit.get('n_categories_union')}): "
                f"{col_audit.get('categories_union')}"
            )
            lines.append(
                f"  counts: matched={col_audit.get('n_matched')} "
                f"missing={col_audit.get('n_missing')} "
                f"extra={col_audit.get('n_extra')} "
                f"gold_zero={col_audit.get('n_gold_zero')}"
            )
            lines.append(
                f"  sum(category_errors)={col_audit.get('sum_category_errors')} "
                f"-> {col_audit.get('average_formula')}"
            )
            lines.append("  per-category breakdown:")
            for row in col_audit.get("category_details", []):
                lines.append(
                    f"    [{row['status']}] {row['category']!r}: "
                    f"gold={row['gold_value']!r} pred={row['predicted_value']!r} "
                    f"error={row['error_term']} "
                    f"denom={row['relative_error_denominator']!r} "
                    f"({row['formula']})"
                )

        lines.append("")
        lines.append(
            f"  FINAL query_error={audit.get('query_error')} "
            f"query_accuracy={audit.get('query_accuracy')}"
        )
        if audit.get("query_error_average_formula"):
            lines.append(f"  ({audit['query_error_average_formula']})")

    lines.append("")
    return "\n".join(lines)


def build_category_value_map(
    df: pd.DataFrame,
    *,
    group_keys: list[str],
    value_column: str,
) -> dict[str, float]:
    """Map GROUP BY category key -> aggregate value."""
    if value_column not in df.columns:
        return {}
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        category = _category_key_from_row(row, group_keys)
        val = _to_float(row[value_column])
        if val is None:
            continue
        out[category] = val
    return out


def compute_category_errors(
    gold_map: dict[str, float],
    pred_map: dict[str, float],
    *,
    epsilon: float = DEFAULT_EPSILON,
) -> dict[str, Any]:
    categories = sorted(set(gold_map) | set(pred_map))
    matched: list[str] = []
    missing: list[str] = []
    extra: list[str] = []
    per_category_error: dict[str, float] = {}
    per_category_relative_error: dict[str, float | None] = {}
    penalty_count = 0

    for category in categories:
        in_gold = category in gold_map
        in_pred = category in pred_map
        if in_gold and in_pred:
            matched.append(category)
            rel = _matched_relative_error(pred_map[category], gold_map[category], epsilon=epsilon)
            per_category_error[category] = rel
            per_category_relative_error[category] = rel
        else:
            if in_gold:
                missing.append(category)
            if in_pred:
                extra.append(category)
            per_category_error[category] = MISSING_CATEGORY_PENALTY
            per_category_relative_error[category] = None
            penalty_count += 1

    if not categories:
        query_error = 0.0 if not gold_map and not pred_map else MISSING_CATEGORY_PENALTY
    else:
        query_error = float(sum(per_category_error[c] for c in categories) / len(categories))

    return {
        "categories_union": categories,
        "matched_categories": matched,
        "missing_categories": missing,
        "extra_categories": extra,
        "per_category_error": per_category_error,
        "per_category_relative_error": per_category_relative_error,
        "category_penalty_count": penalty_count,
        "query_error": query_error,
        "query_accuracy": 1.0 - query_error,
    }


def _primary_failure_mode(missing: list[str], extra: list[str], matched_errors: list[float]) -> str:
    if missing and extra:
        return "missing_and_extra_categories"
    if missing:
        return "missing_categories"
    if extra:
        return "extra_categories"
    if any(err > 0.0 for err in matched_errors):
        return "value_error"
    return "ok"


def compute_group_by_category_error_report(
    gold_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    *,
    group_keys: list[str],
    value_columns: list[str],
    query_id: str = "",
    epsilon: float = DEFAULT_EPSILON,
) -> dict[str, Any] | None:
    """
    Compare predicted vs gold GROUP BY results using union-of-categories error.

    Returns None when the query has no aggregate value columns to score.
    """
    if not value_columns:
        return None

    value_reports: list[dict[str, Any]] = []
    for value_column in value_columns:
        gold_map = build_category_value_map(gold_df, group_keys=group_keys, value_column=value_column)
        pred_map = build_category_value_map(pred_df, group_keys=group_keys, value_column=value_column)
        scored = compute_category_errors(gold_map, pred_map, epsilon=epsilon)
        value_reports.append(
            {
                "value_column": value_column,
                "gold_categories": gold_map,
                "predicted_categories": pred_map,
                **scored,
            }
        )

    # Average query error across aggregate columns when multiple are present.
    query_error = float(sum(r["query_error"] for r in value_reports) / len(value_reports))
    query_accuracy = 1.0 - query_error

    merged_missing = sorted({c for r in value_reports for c in r["missing_categories"]})
    merged_extra = sorted({c for r in value_reports for c in r["extra_categories"]})
    merged_matched = sorted({c for r in value_reports for c in r["matched_categories"]})
    matched_errors = [
        err
        for r in value_reports
        for cat, err in r["per_category_relative_error"].items()
        if err is not None
    ]

    return {
        "query_id": query_id,
        "metric": "group_by_category_error",
        "epsilon": epsilon,
        "group_keys": group_keys,
        "value_columns": value_columns,
        "gold_categories": value_reports[0]["gold_categories"] if len(value_reports) == 1 else {
            r["value_column"]: r["gold_categories"] for r in value_reports
        },
        "predicted_categories": value_reports[0]["predicted_categories"] if len(value_reports) == 1 else {
            r["value_column"]: r["predicted_categories"] for r in value_reports
        },
        "matched_categories": merged_matched,
        "missing_categories": merged_missing,
        "extra_categories": merged_extra,
        "per_category_relative_error": (
            value_reports[0]["per_category_relative_error"]
            if len(value_reports) == 1
            else {r["value_column"]: r["per_category_relative_error"] for r in value_reports}
        ),
        "per_category_error": (
            value_reports[0]["per_category_error"]
            if len(value_reports) == 1
            else {r["value_column"]: r["per_category_error"] for r in value_reports}
        ),
        "category_penalty_count": sum(r["category_penalty_count"] for r in value_reports),
        "query_error": query_error,
        "query_accuracy": query_accuracy,
        "primary_failure_mode": _primary_failure_mode(merged_missing, merged_extra, matched_errors),
        "by_value_column": value_reports,
    }


def summarize_query_errors(per_query: list[dict[str, Any]]) -> dict[str, float]:
    errors = [float(row["query_error"]) for row in per_query if row.get("query_error") is not None]
    accuracies = [float(row["query_accuracy"]) for row in per_query if row.get("query_accuracy") is not None]
    if not errors:
        return {"mean_query_error": 0.0, "mean_query_accuracy": 0.0}
    return {
        "mean_query_error": float(sum(errors) / len(errors)),
        "mean_query_accuracy": float(sum(accuracies) / len(accuracies)),
    }


def build_workload_category_error_report(
    per_config: dict[str, Any],
    *,
    query_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build workload-level report across configs.

    per_config maps config_id -> entry with per_query rows containing category_error blocks.
    """
    config_summaries: dict[str, dict[str, Any]] = {}
    score_table: dict[str, dict[str, float | None]] = {}

    for config_id, entry in sorted(per_config.items()):
        rows = entry.get("per_query") or []
        scored_rows: list[dict[str, Any]] = []
        config_scores: dict[str, float | None] = {}
        for row in rows:
            qid = str(row.get("query_id", ""))
            if query_ids is not None and qid not in query_ids:
                continue
            block = row.get("category_error")
            if not block:
                config_scores[qid] = None
                continue
            scored_rows.append(block)
            config_scores[qid] = float(block["query_error"])

        summary = summarize_query_errors(scored_rows)
        config_summaries[config_id] = {
            **summary,
            "per_query": scored_rows,
        }
        score_table[config_id] = config_scores

    ranked = sorted(
        config_summaries.items(),
        key=lambda kv: float(kv[1].get("mean_query_error", float("inf"))),
    )
    best_config_id = ranked[0][0] if ranked else None
    worst_config_id = ranked[-1][0] if ranked else None

    return {
        "metric": "group_by_category_error",
        "n_configs": len(config_summaries),
        "mean_query_error": (
            float(sum(v["mean_query_error"] for v in config_summaries.values()) / len(config_summaries))
            if config_summaries
            else 0.0
        ),
        "mean_query_accuracy": (
            float(sum(v["mean_query_accuracy"] for v in config_summaries.values()) / len(config_summaries))
            if config_summaries
            else 0.0
        ),
        "best_config": {
            "config_id": best_config_id,
            **(config_summaries.get(best_config_id) or {}),
        }
        if best_config_id
        else None,
        "worst_config": {
            "config_id": worst_config_id,
            **(config_summaries.get(worst_config_id) or {}),
        }
        if worst_config_id
        else None,
        "config_scores": score_table,
        "configs": config_summaries,
    }


def write_category_error_report(payload: dict[str, Any], path) -> None:
    from pathlib import Path

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
