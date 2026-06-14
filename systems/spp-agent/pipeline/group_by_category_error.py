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


TOP_WORST_QUERIES_DEFAULT = 5


def _value_column_reports(report: dict[str, Any]) -> list[dict[str, Any]]:
    by_column = report.get("by_value_column")
    if by_column:
        return by_column
    if report.get("gold_categories") is not None:
        return [report]
    return []


def _report_has_gold_zero(report: dict[str, Any]) -> bool:
    for value_report in _value_column_reports(report):
        for value in (value_report.get("gold_categories") or {}).values():
            if value == 0.0:
                return True
    return False


def _compact_per_category_summary(value_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    gold_map = value_report.get("gold_categories") or {}
    pred_map = value_report.get("predicted_categories") or {}
    summary: dict[str, dict[str, Any]] = {}
    for category, error_term in (value_report.get("per_category_error") or {}).items():
        if category in gold_map and category in pred_map:
            status = "matched"
        elif category in gold_map:
            status = "missing"
        else:
            status = "extra"
        summary[category] = {"status": status, "error": float(error_term)}
    return summary


def compact_worst_query_audit(
    report: dict[str, Any],
    *,
    include_category_details: bool = False,
) -> dict[str, Any]:
    """Compact audit for one query; optional full per-category rows for worst queries."""
    audit = audit_group_by_category_error_report(report)
    per_column_summary = {
        str(col_audit.get("value_column") or "value"): _compact_per_category_summary(
            {
                "gold_categories": col_audit.get("gold_categories"),
                "predicted_categories": col_audit.get("predicted_categories"),
                "per_category_error": {
                    row["category"]: row["error_term"]
                    for row in col_audit.get("category_details", [])
                },
            }
        )
        for col_audit in audit.get("value_column_audits", [])
    }
    compact: dict[str, Any] = {
        "query_id": audit.get("query_id"),
        "gold_categories": report.get("gold_categories"),
        "predicted_categories": report.get("predicted_categories"),
        "per_category_error_summary": per_column_summary,
        "query_error": audit.get("query_error"),
        "query_accuracy": audit.get("query_accuracy"),
        "primary_failure_mode": audit.get("primary_failure_mode"),
    }
    if include_category_details:
        compact["category_details_by_column"] = audit.get("value_column_audits", [])
    return compact


def diagnose_category_error_config(summary: dict[str, Any]) -> list[str]:
    """Short diagnosis of what is driving high query error for one config."""
    n_audited = int(summary.get("n_queries_audited") or 0)
    if n_audited == 0:
        return ["no scored queries"]

    diagnoses: list[str] = []
    zero_denom_share = float(summary.get("zero_denom_error_share") or 0.0)
    n_zero_denom = int(summary.get("n_zero_denom_categories") or 0)
    if n_zero_denom > 0 and zero_denom_share >= 0.25:
        diagnoses.append(
            "zero denominators (gold=0 categories use epsilon and inflate relative error)"
        )

    missing_frac = float(summary.get("n_queries_with_missing_categories") or 0) / n_audited
    extra_frac = float(summary.get("n_queries_with_extra_categories") or 0) / n_audited
    if missing_frac >= 0.4:
        diagnoses.append("missing categories (union penalties on gold-only keys)")
    if extra_frac >= 0.4:
        diagnoses.append("extra categories (union penalties on pred-only keys)")

    avg_err = float(summary.get("avg_per_category_error") or 0.0)
    max_err = float(summary.get("max_per_category_error") or 0.0)
    outlier_threshold = max(10.0, 5.0 * avg_err) if avg_err > 0 else 10.0
    if max_err >= outlier_threshold and float(summary.get("outlier_error_share") or 0.0) >= 0.25:
        diagnoses.append("a few extreme outliers dominate the per-category error mass")

    if not diagnoses:
        if missing_frac >= extra_frac and missing_frac > 0.15:
            diagnoses.append("moderate missing-category penalties across queries")
        elif extra_frac > 0.15:
            diagnoses.append("moderate extra-category penalties across queries")
        else:
            diagnoses.append("value errors on matched categories without a single dominant cause")

    return diagnoses


def build_config_compact_audit(
    config_id: str,
    entry: dict[str, Any],
    *,
    worst_query_limit: int = TOP_WORST_QUERIES_DEFAULT,
) -> dict[str, Any]:
    """Build compact per-config audit from cached per_query category_error blocks."""
    per_query = entry.get("per_query") or []
    scored_rows = [row for row in per_query if row.get("category_error")]

    all_category_errors: list[float] = []
    n_zero_denom_categories = 0
    zero_denom_error_sum = 0.0
    outlier_error_sum = 0.0
    n_queries_with_missing = 0
    n_queries_with_extra = 0
    n_queries_with_gold_zero = 0

    for row in scored_rows:
        report = row["category_error"]
        if report.get("missing_categories"):
            n_queries_with_missing += 1
        if report.get("extra_categories"):
            n_queries_with_extra += 1
        if _report_has_gold_zero(report):
            n_queries_with_gold_zero += 1

        for value_report in _value_column_reports(report):
            gold_map = value_report.get("gold_categories") or {}
            pred_map = value_report.get("predicted_categories") or {}
            matched = set(value_report.get("matched_categories") or [])
            for category, error_term in (value_report.get("per_category_error") or {}).items():
                err = float(error_term)
                all_category_errors.append(err)
                if category in matched and gold_map.get(category) == 0.0 and pred_map.get(category) != 0.0:
                    n_zero_denom_categories += 1
                    zero_denom_error_sum += err

    query_errors = [float(row["category_error"]["query_error"]) for row in scored_rows]
    query_accuracies = [float(row["category_error"]["query_accuracy"]) for row in scored_rows]

    ranked_rows = sorted(
        scored_rows,
        key=lambda row: float(row["category_error"]["query_error"]),
        reverse=True,
    )
    worst_rows = ranked_rows[:worst_query_limit]

    avg_per_category_error = (
        float(sum(all_category_errors) / len(all_category_errors))
        if all_category_errors
        else 0.0
    )
    max_per_category_error = max(all_category_errors) if all_category_errors else 0.0
    total_category_error = float(sum(all_category_errors))
    outlier_threshold = max(10.0, 5.0 * avg_per_category_error) if avg_per_category_error > 0 else 10.0
    outlier_error_sum = float(sum(err for err in all_category_errors if err >= outlier_threshold))

    summary: dict[str, Any] = {
        "config_id": config_id,
        "mean_query_error": float(sum(query_errors) / len(query_errors)) if query_errors else 0.0,
        "mean_query_accuracy": float(sum(query_accuracies) / len(query_accuracies))
        if query_accuracies
        else 0.0,
        "n_queries_audited": len(scored_rows),
        "n_queries_with_missing_categories": n_queries_with_missing,
        "n_queries_with_extra_categories": n_queries_with_extra,
        "n_queries_with_gold_zero": n_queries_with_gold_zero,
        "avg_per_category_error": avg_per_category_error,
        "max_per_category_error": max_per_category_error,
        "n_zero_denom_categories": n_zero_denom_categories,
        "zero_denom_error_share": (
            zero_denom_error_sum / total_category_error if total_category_error > 0 else 0.0
        ),
        "outlier_error_share": (
            outlier_error_sum / total_category_error if total_category_error > 0 else 0.0
        ),
        "top_worst_queries": [
            compact_worst_query_audit(row["category_error"], include_category_details=False)
            for row in worst_rows
        ],
        "top_worst_queries_detailed": [
            compact_worst_query_audit(row["category_error"], include_category_details=True)
            for row in worst_rows
        ],
    }
    summary["diagnosis"] = diagnose_category_error_config(summary)
    return summary


def build_workload_compact_audit(
    per_config: dict[str, Any],
    *,
    config_ids: list[str] | None = None,
    worst_query_limit: int = TOP_WORST_QUERIES_DEFAULT,
) -> dict[str, Any]:
    """Compact audit across configs using cached evaluation results."""
    configs: list[dict[str, Any]] = []
    for config_id, entry in sorted(per_config.items()):
        if config_ids is not None and config_id not in config_ids:
            continue
        if not entry.get("per_query"):
            continue
        configs.append(
            build_config_compact_audit(
                config_id,
                entry,
                worst_query_limit=worst_query_limit,
            )
        )

    return {
        "metric": "group_by_category_error",
        "report_type": "compact_audit",
        "n_configs": len(configs),
        "configs": configs,
    }


def _format_worst_query_lines(query: dict[str, Any], *, detailed: bool) -> list[str]:
    lines = [
        f"  Query: {query.get('query_id')}",
        f"    gold_categories: {query.get('gold_categories')}",
        f"    predicted_categories: {query.get('predicted_categories')}",
        "    per_category_error_summary:",
    ]
    for value_column, categories in (query.get("per_category_error_summary") or {}).items():
        lines.append(f"      [{value_column}]")
        for category, info in sorted(
            categories.items(),
            key=lambda item: float(item[1].get("error") or 0.0),
            reverse=True,
        ):
            lines.append(
                f"        {category!r}: {info.get('status')} error={info.get('error')}"
            )
    lines.append(f"    query_error={query.get('query_error')}")
    lines.append(f"    query_accuracy={query.get('query_accuracy')}")

    if detailed:
        for col_audit in query.get("category_details_by_column") or []:
            lines.append(f"    --- full detail: {col_audit.get('value_column')} ---")
            for row in col_audit.get("category_details") or []:
                lines.append(
                    f"      [{row.get('status')}] {row.get('category')!r}: "
                    f"gold={row.get('gold_value')!r} pred={row.get('predicted_value')!r} "
                    f"error={row.get('error_term')} "
                    f"denom={row.get('relative_error_denominator')!r} "
                    f"({row.get('formula')})"
                )
    return lines


def format_compact_category_error_audit(report: dict[str, Any]) -> str:
    """Human-readable compact audit: summary per config, full detail for worst queries only."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("CATEGORY ERROR COMPACT AUDIT")
    lines.append("=" * 72)

    for config in report.get("configs", []):
        lines.append("")
        lines.append(f"Config: {config.get('config_id')}")
        lines.append(f"  mean_query_error={config.get('mean_query_error')}")
        lines.append(f"  mean_query_accuracy={config.get('mean_query_accuracy')}")
        lines.append(f"  n_queries_audited={config.get('n_queries_audited')}")
        lines.append(
            "  n_queries_with_missing_categories="
            f"{config.get('n_queries_with_missing_categories')}"
        )
        lines.append(
            f"  n_queries_with_extra_categories={config.get('n_queries_with_extra_categories')}"
        )
        lines.append(f"  n_queries_with_gold_zero={config.get('n_queries_with_gold_zero')}")
        lines.append(f"  avg_per_category_error={config.get('avg_per_category_error')}")
        lines.append(f"  max_per_category_error={config.get('max_per_category_error')}")
        lines.append("  diagnosis:")
        for item in config.get("diagnosis") or []:
            lines.append(f"    - {item}")

        lines.append("  top worst queries:")
        detailed_by_id = {
            str(query.get("query_id")): query
            for query in config.get("top_worst_queries_detailed") or []
        }
        for query in config.get("top_worst_queries") or []:
            qid = str(query.get("query_id"))
            lines.extend(
                _format_worst_query_lines(
                    detailed_by_id.get(qid, query),
                    detailed=True,
                )
            )
            lines.append("")

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
