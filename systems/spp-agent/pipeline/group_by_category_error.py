"""GROUP BY category error metric for aggregation query evaluation."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from data.aggregation_slices import AGGREGATION_SLICE_ORDER

DEFAULT_EPSILON = 1e-9
MISSING_CATEGORY_PENALTY = 1.0
GOLD_ZERO_MATCHED_PENALTY = 1.0


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


def _matched_category_error(pred: float, gold: float, *, epsilon: float = DEFAULT_EPSILON) -> float:
    """
    Matched-category error.

    - gold == 0: 0 if pred == 0 else fixed penalty (bounded, no epsilon division)
    - gold > 0: |pred - gold| / |gold|
    """
    del epsilon  # retained for API compatibility; not used for gold == 0
    if gold == 0.0:
        if pred == 0.0:
            return 0.0
        return GOLD_ZERO_MATCHED_PENALTY
    return abs(pred - gold) / abs(gold)


def _matched_relative_error(pred: float, gold: float, *, epsilon: float) -> float:
    """Backward-compatible alias."""
    return _matched_category_error(pred, gold, epsilon=epsilon)


def _relative_error_denominator(gold: float, *, epsilon: float) -> float | None:
    if gold == 0.0:
        return None
    return abs(gold)


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
            assert gold_val is not None and pred_val is not None
            error_term = scored["per_category_error"][category]
            if gold_val == 0.0:
                status = "matched_gold_zero"
                denominator = None
                if pred_val == 0.0:
                    formula = "gold=0 and pred=0 -> error=0"
                else:
                    formula = (
                        f"gold=0 and pred!={pred_val} -> "
                        f"penalty={GOLD_ZERO_MATCHED_PENALTY}"
                    )
            else:
                status = "matched"
                denominator = _relative_error_denominator(gold_val, epsilon=epsilon)
                formula = f"|{pred_val} - {gold_val}| / |{gold_val}|"
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
DETAIL_CONFIG_LIMIT_DEFAULT = 10
TOP_CATEGORY_ERRORS_JSON_DEFAULT = 5
CATEGORY_LABEL_MAX_LEN = 64


def _round_json_float(value: float) -> float:
    if not math.isfinite(value):
        return value
    if value == 0.0:
        return 0.0
    if abs(value) >= 1_000_000 or abs(value) < 1e-4:
        return float(f"{value:.4g}")
    return round(value, 6)


def _truncate_category_label(category: object) -> str:
    text = "" if category is None else str(category)
    if len(text) <= CATEGORY_LABEL_MAX_LEN:
        return text
    return f"{text[: CATEGORY_LABEL_MAX_LEN - 3]}..."


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


def summarize_worst_query_for_json(
    report: dict[str, Any],
    *,
    top_category_errors: int = TOP_CATEGORY_ERRORS_JSON_DEFAULT,
) -> dict[str, Any]:
    """Small worst-query record for JSON detail section (no full category maps)."""
    n_gold = 0
    n_pred = 0
    error_rows: list[dict[str, Any]] = []

    for value_report in _fresh_value_reports(report):
        gold_map = value_report.get("gold_categories") or {}
        pred_map = value_report.get("predicted_categories") or {}
        n_gold += len(gold_map)
        n_pred += len(pred_map)
        value_column = value_report.get("value_column")
        for category, error_term in (value_report.get("per_category_error") or {}).items():
            if category in gold_map and category in pred_map:
                status = (
                    "matched_gold_zero"
                    if gold_map.get(category) == 0.0
                    else "matched"
                )
            elif category in gold_map:
                status = "missing"
            else:
                status = "extra"
            row: dict[str, Any] = {
                "category": _truncate_category_label(category),
                "status": status,
                "error": _round_json_float(float(error_term)),
            }
            if value_column is not None:
                row["value_column"] = value_column
            error_rows.append(row)

    error_rows.sort(key=lambda row: float(row["error"]), reverse=True)

    return {
        "query_id": report.get("query_id"),
        "query_error": _round_json_float(float(report.get("query_error", 0.0))),
        "query_accuracy": _round_json_float(
            float(report.get("query_accuracy", 1.0 - float(report.get("query_error", 0.0))))
        ),
        "primary_failure_mode": report.get("primary_failure_mode"),
        "n_gold_categories": n_gold,
        "n_predicted_categories": n_pred,
        "n_missing_categories": len(report.get("missing_categories") or []),
        "n_extra_categories": len(report.get("extra_categories") or []),
        "top_category_errors": error_rows[:top_category_errors],
    }


def build_config_scalar_summary(
    config_id: str,
    entry: dict[str, Any],
    *,
    worst_query_limit: int = TOP_WORST_QUERIES_DEFAULT,
) -> dict[str, Any]:
    """Per-config scalar audit row for JSON (no per-category error lists)."""
    per_query = entry.get("per_query") or []
    scored_rows = [row for row in per_query if row.get("category_error")]

    all_category_errors: list[float] = []
    n_zero_denom_categories = 0
    zero_denom_error_sum = 0.0
    n_queries_with_missing = 0
    n_queries_with_extra = 0
    n_queries_with_gold_zero = 0
    refreshed_reports: list[dict[str, Any]] = []

    for row in scored_rows:
        report = refresh_category_error_block(row["category_error"])
        refreshed_reports.append(report)
        if report.get("missing_categories"):
            n_queries_with_missing += 1
        if report.get("extra_categories"):
            n_queries_with_extra += 1
        if _report_has_gold_zero(report):
            n_queries_with_gold_zero += 1

        for value_report in _fresh_value_reports(report):
            gold_map = value_report.get("gold_categories") or {}
            pred_map = value_report.get("predicted_categories") or {}
            for category, error_term in (value_report.get("per_category_error") or {}).items():
                err = float(error_term)
                all_category_errors.append(err)
                if (
                    category in gold_map
                    and category in pred_map
                    and gold_map.get(category) == 0.0
                    and pred_map.get(category) != 0.0
                ):
                    n_zero_denom_categories += 1
                    zero_denom_error_sum += err

    query_errors = [float(report["query_error"]) for report in refreshed_reports]
    query_accuracies = [float(report["query_accuracy"]) for report in refreshed_reports]

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
        "mean_query_error": _round_json_float(
            float(sum(query_errors) / len(query_errors)) if query_errors else 0.0
        ),
        "mean_query_accuracy": _round_json_float(
            float(sum(query_accuracies) / len(query_accuracies)) if query_accuracies else 0.0
        ),
        "n_queries_audited": len(scored_rows),
        "n_queries_with_missing_categories": n_queries_with_missing,
        "n_queries_with_extra_categories": n_queries_with_extra,
        "n_queries_with_gold_zero": n_queries_with_gold_zero,
        "avg_per_category_error": _round_json_float(avg_per_category_error),
        "max_per_category_error": _round_json_float(max_per_category_error),
        "n_zero_denom_categories": n_zero_denom_categories,
        "gold_zero_mismatch_penalty": GOLD_ZERO_MATCHED_PENALTY,
        "zero_denom_error_share": _round_json_float(
            zero_denom_error_sum / total_category_error if total_category_error > 0 else 0.0
        ),
        "outlier_error_share": _round_json_float(
            outlier_error_sum / total_category_error if total_category_error > 0 else 0.0
        ),
    }
    summary["diagnosis"] = diagnose_category_error_config(summary)
    return summary


def build_config_ranking(scalar_configs: list[dict[str, Any]]) -> dict[str, Any]:
    """Compact config leaderboard for JSON (two parallel arrays, sorted by error desc)."""
    ranked = sorted(
        scalar_configs,
        key=lambda cfg: float(cfg["mean_query_error"]),
        reverse=True,
    )
    return {
        "config_ids": [str(cfg["config_id"]) for cfg in ranked],
        "mean_query_errors": [cfg["mean_query_error"] for cfg in ranked],
    }


def build_config_query_details(
    config_id: str,
    entry: dict[str, Any],
    *,
    worst_query_limit: int = TOP_WORST_QUERIES_DEFAULT,
    top_category_errors: int = TOP_CATEGORY_ERRORS_JSON_DEFAULT,
) -> dict[str, Any]:
    """Per-query breakdown for the JSON detail section (worst configs only)."""
    per_query = entry.get("per_query") or []
    scored_rows = [row for row in per_query if row.get("category_error")]
    ranked_rows = sorted(
        scored_rows,
        key=lambda row: float(refresh_category_error_block(row["category_error"])["query_error"]),
        reverse=True,
    )[:worst_query_limit]
    scalar = build_config_scalar_summary(
        config_id,
        entry,
        worst_query_limit=worst_query_limit,
    )
    return {
        **scalar,
        "queries": [
            summarize_worst_query_for_json(
                refresh_category_error_block(row["category_error"]),
                top_category_errors=top_category_errors,
            )
            for row in ranked_rows
        ],
    }


def build_config_compact_audit(
    config_id: str,
    entry: dict[str, Any],
    *,
    worst_query_limit: int = TOP_WORST_QUERIES_DEFAULT,
) -> dict[str, Any]:
    """Backward-compatible alias for scalar config summary."""
    return build_config_scalar_summary(
        config_id,
        entry,
        worst_query_limit=worst_query_limit,
    )


def build_workload_audit_summary(
    per_config: dict[str, Any],
    *,
    config_ids: list[str] | None = None,
    worst_query_limit: int = TOP_WORST_QUERIES_DEFAULT,
    detail_config_limit: int = DETAIL_CONFIG_LIMIT_DEFAULT,
    top_category_errors: int = TOP_CATEGORY_ERRORS_JSON_DEFAULT,
    include_all_config_scalars: bool = False,
) -> dict[str, Any]:
    """Summarized audit for JSON: ranking for all configs, detail only for worst N."""
    scalar_configs: list[dict[str, Any]] = []
    entries_by_id: dict[str, dict[str, Any]] = {}

    for config_id, entry in sorted(per_config.items()):
        if config_ids is not None and config_id not in config_ids:
            continue
        if not entry.get("per_query"):
            continue
        entries_by_id[config_id] = entry
        scalar_configs.append(
            build_config_scalar_summary(
                config_id,
                entry,
                worst_query_limit=worst_query_limit,
            )
        )

    mean_errors = [float(cfg["mean_query_error"]) for cfg in scalar_configs]
    ranked_for_detail = sorted(
        scalar_configs,
        key=lambda cfg: float(cfg["mean_query_error"]),
        reverse=True,
    )[:detail_config_limit]

    payload: dict[str, Any] = {
        "metric": "group_by_category_error",
        "report_type": "compact_audit_summary",
        "n_configs": len(scalar_configs),
        "detail_config_limit": detail_config_limit,
        "worst_query_limit": worst_query_limit,
        "workload_summary": {
            "mean_of_mean_query_error": _round_json_float(
                float(sum(mean_errors) / len(mean_errors)) if mean_errors else 0.0
            ),
            "max_mean_query_error": _round_json_float(max(mean_errors) if mean_errors else 0.0),
            "configs_with_zero_denom_issues": sum(
                1 for cfg in scalar_configs if int(cfg.get("n_zero_denom_categories") or 0) > 0
            ),
            "configs_with_missing_category_queries": sum(
                1
                for cfg in scalar_configs
                if int(cfg.get("n_queries_with_missing_categories") or 0) > 0
            ),
            "configs_with_extra_category_queries": sum(
                1
                for cfg in scalar_configs
                if int(cfg.get("n_queries_with_extra_categories") or 0) > 0
            ),
        },
        "config_ranking": build_config_ranking(scalar_configs),
        "worst_config_details": [
            build_config_query_details(
                str(cfg["config_id"]),
                entries_by_id[str(cfg["config_id"])],
                worst_query_limit=worst_query_limit,
                top_category_errors=top_category_errors,
            )
            for cfg in ranked_for_detail
        ],
    }
    if include_all_config_scalars:
        payload["configs"] = scalar_configs
    return payload


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
            "gold=0 matched categories with nonzero predictions "
            f"(fixed penalty={GOLD_ZERO_MATCHED_PENALTY} each)"
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


def build_workload_compact_audit(
    per_config: dict[str, Any],
    *,
    config_ids: list[str] | None = None,
    worst_query_limit: int = TOP_WORST_QUERIES_DEFAULT,
    detail_config_limit: int = DETAIL_CONFIG_LIMIT_DEFAULT,
    top_category_errors: int = TOP_CATEGORY_ERRORS_JSON_DEFAULT,
    include_all_config_scalars: bool = False,
) -> dict[str, Any]:
    """Alias for summarized audit payload."""
    return build_workload_audit_summary(
        per_config,
        config_ids=config_ids,
        worst_query_limit=worst_query_limit,
        detail_config_limit=detail_config_limit,
        top_category_errors=top_category_errors,
        include_all_config_scalars=include_all_config_scalars,
    )


def _lookup_category_error_report(
    per_config: dict[str, Any],
    config_id: str,
    query_id: str,
) -> dict[str, Any] | None:
    entry = per_config.get(config_id) or {}
    for row in entry.get("per_query") or []:
        if str(row.get("query_id")) == str(query_id):
            report = row.get("category_error")
            if report:
                return report
    return None


def format_compact_category_error_audit(
    report: dict[str, Any],
    *,
    per_config: dict[str, Any] | None = None,
) -> str:
    """Human-readable audit: workload summary, scalar config rows, detail for worst configs."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("CATEGORY ERROR COMPACT AUDIT")
    lines.append("=" * 72)

    workload = report.get("workload_summary") or {}
    lines.append("")
    lines.append("Workload:")
    for key, value in workload.items():
        lines.append(f"  {key}={value}")
    lines.append(f"  n_configs={report.get('n_configs')}")

    ranking = report.get("config_ranking") or {}
    lines.append("")
    lines.append("Config ranking (mean query error, highest first):")
    for config_id, mean_error in zip(
        ranking.get("config_ids") or [],
        ranking.get("mean_query_errors") or [],
    ):
        lines.append(f"  {config_id}: {mean_error}")

    if report.get("configs"):
        lines.append("")
        lines.append("All configs (full scalar summary):")
        for config in report["configs"]:
            lines.append(
                f"  {config.get('config_id')}: "
                f"mean_error={config.get('mean_query_error')} "
                f"missing_q={config.get('n_queries_with_missing_categories')} "
                f"extra_q={config.get('n_queries_with_extra_categories')} "
                f"gold_zero_q={config.get('n_queries_with_gold_zero')}"
            )

    lines.append("")
    lines.append(
        f"Worst config details (top {report.get('detail_config_limit', DETAIL_CONFIG_LIMIT_DEFAULT)}):"
    )
    for config in report.get("worst_config_details", []):
        config_id = str(config.get("config_id"))
        lines.append("")
        lines.append(f"Config: {config_id}")
        lines.append(f"  mean_query_error={config.get('mean_query_error')}")
        lines.append("  diagnosis:")
        for item in config.get("diagnosis") or []:
            lines.append(f"    - {item}")

        for query in config.get("queries") or []:
            qid = str(query.get("query_id"))
            lines.append(f"  Query: {qid}")
            lines.append(f"    query_error={query.get('query_error')}")
            lines.append(f"    primary_failure_mode={query.get('primary_failure_mode')}")
            lines.append(
                "    category_counts: "
                f"gold={query.get('n_gold_categories')} "
                f"pred={query.get('n_predicted_categories')} "
                f"missing={query.get('n_missing_categories')} "
                f"extra={query.get('n_extra_categories')}"
            )
            lines.append("    top_category_errors:")
            for row in query.get("top_category_errors") or []:
                vc = row.get("value_column")
                vc_suffix = f" [{vc}]" if vc else ""
                lines.append(
                    f"      {row.get('category')!r}{vc_suffix}: "
                    f"{row.get('status')} error={row.get('error')}"
                )

            if per_config is not None:
                report_block = _lookup_category_error_report(per_config, config_id, qid)
                if report_block is not None:
                    detailed = compact_worst_query_audit(
                        report_block,
                        include_category_details=True,
                    )
                    lines.append(f"    gold_categories: {detailed.get('gold_categories')}")
                    lines.append(
                        f"    predicted_categories: {detailed.get('predicted_categories')}"
                    )
                    for col_audit in detailed.get("category_details_by_column") or []:
                        lines.append(f"    --- full detail: {col_audit.get('value_column')} ---")
                        for row in col_audit.get("category_details") or []:
                            lines.append(
                                f"      [{row.get('status')}] {row.get('category')!r}: "
                                f"gold={row.get('gold_value')!r} pred={row.get('predicted_value')!r} "
                                f"error={row.get('error_term')} "
                                f"denom={row.get('relative_error_denominator')!r} "
                                f"({row.get('formula')})"
                            )
            lines.append("")

    lines.append("")
    return "\n".join(lines)


def category_error_metric_formula(*, epsilon: float = DEFAULT_EPSILON) -> dict[str, str]:
    """Document the exact category_error formulas (for audit output only)."""
    del epsilon
    return {
        "matched_gold_positive": "error = |predicted - gold| / |gold| when gold > 0",
        "matched_gold_zero": (
            f"error = 0 when pred=0; else fixed penalty={GOLD_ZERO_MATCHED_PENALTY}"
        ),
        "missing_or_extra": f"error = {MISSING_CATEGORY_PENALTY} (category in union but only one side)",
        "query_error": "mean(per_category_error over union of gold and predicted categories)",
        "query_accuracy": "1 - query_error",
    }


def build_category_calculation_record(
    *,
    config_id: str,
    query_id: str,
    value_column: str | None,
    category: str,
    status: str,
    gold_value: float | None,
    predicted_value: float | None,
    error_term: float,
    epsilon: float = DEFAULT_EPSILON,
) -> dict[str, Any]:
    """One category's exact calculation path."""
    row: dict[str, Any] = {
        "config_id": config_id,
        "query_id": query_id,
        "value_column": value_column,
        "category": category,
        "status": status,
        "gold_value": gold_value,
        "predicted_value": predicted_value,
        "error_term": error_term,
        "epsilon": epsilon,
    }
    if status == "matched":
        assert gold_value is not None and predicted_value is not None
        numerator = abs(predicted_value - gold_value)
        denominator = abs(gold_value)
        row.update(
            {
                "numerator": numerator,
                "denominator": denominator,
                "uses_epsilon_denominator": False,
                "formula": "matched_relative_error",
                "expression": (
                    f"|predicted - gold| / |gold| = "
                    f"|{predicted_value} - {gold_value}| / |{gold_value}|"
                ),
                "substitution": f"{numerator} / {denominator} = {error_term}",
            }
        )
    elif status == "matched_gold_zero":
        assert gold_value is not None and predicted_value is not None
        row.update(
            {
                "numerator": abs(predicted_value - gold_value),
                "denominator": None,
                "uses_epsilon_denominator": False,
                "formula": "matched_gold_zero_penalty",
                "expression": (
                    "gold=0: error=0 if pred=0 "
                    f"else penalty={GOLD_ZERO_MATCHED_PENALTY}"
                ),
                "substitution": (
                    f"0 (both zero)"
                    if predicted_value == 0.0
                    else f"penalty={GOLD_ZERO_MATCHED_PENALTY}"
                ),
            }
        )
    else:
        row.update(
            {
                "numerator": MISSING_CATEGORY_PENALTY,
                "denominator": None,
                "uses_epsilon_denominator": False,
                "formula": "missing_or_extra_penalty",
                "expression": f"penalty = {MISSING_CATEGORY_PENALTY}",
                "substitution": str(error_term),
            }
        )
    return row


def iter_category_calculation_records(
    per_config: dict[str, Any],
    *,
    config_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Flatten all per-category calculations from cached evaluation results."""
    rows: list[dict[str, Any]] = []
    for config_id, entry in sorted(per_config.items()):
        if config_ids is not None and config_id not in config_ids:
            continue
        for per_query_row in entry.get("per_query") or []:
            report = per_query_row.get("category_error")
            if not report:
                continue
            report = refresh_category_error_block(report)
            query_id = str(per_query_row.get("query_id", report.get("query_id", "")))
            epsilon = float(report.get("epsilon", DEFAULT_EPSILON))
            for value_report in _fresh_value_reports(report):
                gold_map = value_report.get("gold_categories") or {}
                pred_map = value_report.get("predicted_categories") or {}
                value_column = value_report.get("value_column")
                for category, error_term in (value_report.get("per_category_error") or {}).items():
                    if category in gold_map and category in pred_map:
                        gold_value = float(gold_map[category])
                        predicted_value = float(pred_map[category])
                        status = "matched_gold_zero" if gold_value == 0.0 else "matched"
                    elif category in gold_map:
                        status = "missing"
                        gold_value = float(gold_map[category])
                        predicted_value = None
                    else:
                        status = "extra"
                        gold_value = None
                        predicted_value = float(pred_map[category])
                    rows.append(
                        build_category_calculation_record(
                            config_id=config_id,
                            query_id=query_id,
                            value_column=value_column,
                            category=category,
                            status=status,
                            gold_value=gold_value,
                            predicted_value=predicted_value,
                            error_term=float(error_term),
                            epsilon=epsilon,
                        )
                    )
    return rows


def top_category_error_calculations(
    per_config: dict[str, Any],
    *,
    config_ids: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Largest per-category error terms with full calculation path."""
    rows = iter_category_calculation_records(per_config, config_ids=config_ids)
    rows.sort(key=lambda row: float(row["error_term"]), reverse=True)
    return rows[:limit]


def format_top_category_error_calculations(
    rows: list[dict[str, Any]],
    *,
    epsilon: float = DEFAULT_EPSILON,
) -> str:
    """Human-readable report of the largest category errors and how they were computed."""
    formulas = category_error_metric_formula(epsilon=epsilon)
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("TOP CATEGORY ERROR CALCULATIONS (exact metric path)")
    lines.append("=" * 72)
    lines.append("")
    lines.append("Metric formulas:")
    for key, value in formulas.items():
        lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append(
        "Gold=0 matched categories use a fixed penalty (not epsilon division). "
        f"Example: gold=0, pred=17 -> error={GOLD_ZERO_MATCHED_PENALTY}."
    )
    lines.append("")

    for rank, row in enumerate(rows, start=1):
        lines.append(f"#{rank} error_term={row.get('error_term')}")
        lines.append(f"  config_id: {row.get('config_id')}")
        lines.append(f"  query_id: {row.get('query_id')}")
        lines.append(f"  value_column: {row.get('value_column')}")
        lines.append(f"  category: {row.get('category')!r}")
        lines.append(f"  status: {row.get('status')}")
        lines.append(f"  gold_value: {row.get('gold_value')!r}")
        lines.append(f"  predicted_value: {row.get('predicted_value')!r}")
        lines.append(f"  numerator: {row.get('numerator')!r}")
        lines.append(f"  denominator: {row.get('denominator')!r}")
        lines.append(f"  epsilon: {row.get('epsilon')}")
        lines.append(f"  uses_epsilon_denominator: {row.get('uses_epsilon_denominator')}")
        lines.append(f"  formula: {row.get('formula')}")
        lines.append(f"  expression: {row.get('expression')}")
        lines.append(f"  substitution: {row.get('substitution')}")
        lines.append("")

    return "\n".join(lines)


def build_top_category_error_audit(
    per_config: dict[str, Any],
    *,
    config_ids: list[str] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    top_rows = top_category_error_calculations(
        per_config,
        config_ids=config_ids,
        limit=limit,
    )
    epsilon = float(top_rows[0]["epsilon"]) if top_rows else DEFAULT_EPSILON
    return {
        "metric": "group_by_category_error",
        "report_type": "top_category_error_calculations",
        "limit": limit,
        "formulas": category_error_metric_formula(epsilon=epsilon),
        "zero_denominator_note": (
            "When gold=0 and pred!=0, error is a fixed penalty "
            f"({GOLD_ZERO_MATCHED_PENALTY}), not relative error / epsilon."
        ),
        "top_errors": top_rows,
    }


def write_top_category_error_audit(payload: dict[str, Any], path) -> None:
    from pathlib import Path

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_category_error_audit_summary(payload: dict[str, Any], path) -> None:
    from pathlib import Path

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
            rel = _matched_category_error(pred_map[category], gold_map[category], epsilon=epsilon)
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


def _fresh_value_reports(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Recompute per-value-column errors from cached gold/pred maps."""
    epsilon = float(report.get("epsilon", DEFAULT_EPSILON))
    fresh: list[dict[str, Any]] = []
    for value_report in _value_column_reports(report):
        gold_map = value_report.get("gold_categories") or {}
        pred_map = value_report.get("predicted_categories") or {}
        scored = compute_category_errors(gold_map, pred_map, epsilon=epsilon)
        fresh.append(
            {
                "value_column": value_report.get("value_column"),
                "gold_categories": gold_map,
                "predicted_categories": pred_map,
                **scored,
            }
        )
    return fresh


def refresh_category_error_block(report: dict[str, Any]) -> dict[str, Any]:
    """Recompute query-level category_error fields from cached category maps."""
    value_reports = _fresh_value_reports(report)
    if not value_reports:
        return report

    query_error = float(sum(r["query_error"] for r in value_reports) / len(value_reports))
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
        **report,
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
        "query_accuracy": 1.0 - query_error,
        "primary_failure_mode": _primary_failure_mode(merged_missing, merged_extra, matched_errors),
        "by_value_column": value_reports,
    }


def refresh_per_query_row_scores(row: dict[str, Any]) -> dict[str, Any]:
    """Recompute query_error/query_accuracy from cached category maps (current metric)."""
    block = row.get("category_error")
    if not block:
        return row
    refreshed = refresh_category_error_block(block)
    return {
        **row,
        "category_error": refreshed,
        "query_error": refreshed.get("query_error"),
        "query_accuracy": refreshed.get("query_accuracy"),
        "primary_failure_mode": refreshed.get("primary_failure_mode"),
    }


def refresh_per_config_scores(per_config: dict[str, Any]) -> dict[str, Any]:
    """Refresh all per_query category_error scores and config-level summaries."""
    for entry in per_config.values():
        per_query = entry.get("per_query")
        if not per_query:
            continue
        entry["per_query"] = [refresh_per_query_row_scores(row) for row in per_query]
        errors = [
            float(row["query_error"])
            for row in entry["per_query"]
            if row.get("query_error") is not None
        ]
        accuracies = [
            float(row["query_accuracy"])
            for row in entry["per_query"]
            if row.get("query_accuracy") is not None
        ]
        if errors:
            entry["mean_query_error"] = float(sum(errors) / len(errors))
            entry["mean_query_accuracy"] = float(sum(accuracies) / len(accuracies))
    return per_config


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
            block = refresh_category_error_block(block)
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


def _leaderboard_rows_from_win_counts(
    per_config: dict[str, Any],
    win_counts: dict[str, float],
    *,
    n_queries: int,
    config_mean_error: dict[str, float | None],
) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "config_id": config_id,
                "wins": round(float(win_counts.get(config_id, 0.0)), 4),
                "win_rate": (
                    round(float(win_counts.get(config_id, 0.0)) / n_queries, 6)
                    if n_queries
                    else 0.0
                ),
                "mean_query_error": config_mean_error.get(config_id),
                "mean_query_accuracy": (
                    None
                    if config_mean_error.get(config_id) is None
                    else 1.0 - float(config_mean_error[config_id])
                ),
            }
            for config_id in per_config
        ],
        key=lambda row: (
            -float(row["wins"]),
            float(row["mean_query_error"] if row["mean_query_error"] is not None else float("inf")),
            str(row["config_id"]),
        ),
    )


def _winners_for_query_subset(
    query_scores: dict[str, dict[str, float]],
    query_ids: list[str],
    query_slices: dict[str, str],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Return fractional win counts and per-query winner records.

    When multiple configs tie for the lowest query_error on a query, each tied
    config receives 1/n_tied of a win rather than giving all credit to the
    alphabetically first config.  This removes alphabetical tie-break bias and
    makes the wins column a true measure of how often each config is optimal.
    """
    win_counts: dict[str, float] = defaultdict(float)
    per_query_winners: list[dict[str, Any]] = []

    for qid in sorted(query_ids):
        scores = query_scores.get(qid)
        if not scores:
            continue
        best_error = min(scores.values())
        tied = sorted(cid for cid, err in scores.items() if err == best_error)
        share = 1.0 / len(tied)
        for cid in tied:
            win_counts[cid] += share
        per_query_winners.append(
            {
                "query_id": qid,
                "query_type": query_slices.get(qid, "unknown"),
                # best_config_id is still reported for reference (alphabetically first
                # tied config), but wins are shared fractionally across all tied configs.
                "best_config_id": tied[0],
                "best_query_error": best_error,
                "n_tied_at_best": len(tied),
                "tied_config_ids": tied,
                "win_share_per_config": share,
            }
        )

    return dict(win_counts), per_query_winners


def build_config_leaderboard(
    per_config: dict[str, Any],
    *,
    query_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Count how often each config achieves the best (lowest) query_error per query.

    Uses refreshed category_error scores from cached gold/pred maps.
    """
    query_scores: dict[str, dict[str, float]] = {}
    query_slices: dict[str, str] = {}
    config_mean_error: dict[str, float | None] = {}
    config_mean_error_by_slice: dict[str, dict[str, float]] = defaultdict(dict)

    for config_id, entry in sorted(per_config.items()):
        config_mean_error[config_id] = entry.get("mean_query_error")
        slice_errors: dict[str, list[float]] = defaultdict(list)
        for row in entry.get("per_query") or []:
            qid = str(row.get("query_id", ""))
            if query_ids is not None and qid not in query_ids:
                continue
            slice_name = str(row.get("aggregation_slice") or "unknown")
            query_slices[qid] = slice_name
            refreshed = refresh_per_query_row_scores(row)
            if refreshed.get("query_error") is None:
                continue
            err = float(refreshed["query_error"])
            query_scores.setdefault(qid, {})[config_id] = err
            slice_errors[slice_name].append(err)
        for slice_name, errors in slice_errors.items():
            config_mean_error_by_slice[slice_name][config_id] = float(sum(errors) / len(errors))

    scored_query_ids = sorted(query_scores)
    n_queries = len(scored_query_ids)
    win_counts, per_query_winners = _winners_for_query_subset(
        query_scores,
        scored_query_ids,
        query_slices,
    )
    for config_id in per_config:
        win_counts.setdefault(config_id, 0)

    leaderboard = _leaderboard_rows_from_win_counts(
        per_config,
        win_counts,
        n_queries=n_queries,
        config_mean_error=config_mean_error,
    )

    top_wins = leaderboard[0]["wins"] if leaderboard else 0
    leaders_at_top = [row for row in leaderboard if row["wins"] == top_wins and top_wins > 0]

    slice_names = sorted(
        {query_slices[qid] for qid in scored_query_ids},
        key=lambda name: (
            AGGREGATION_SLICE_ORDER.index(name)
            if name in AGGREGATION_SLICE_ORDER
            else len(AGGREGATION_SLICE_ORDER)
        ),
    )
    by_query_type: dict[str, dict[str, Any]] = {}
    for slice_name in slice_names:
        slice_qids = [qid for qid in scored_query_ids if query_slices.get(qid) == slice_name]
        slice_wins, slice_per_query = _winners_for_query_subset(
            query_scores,
            slice_qids,
            query_slices,
        )
        for config_id in per_config:
            slice_wins.setdefault(config_id, 0)
        slice_leaderboard = _leaderboard_rows_from_win_counts(
            per_config,
            slice_wins,
            n_queries=len(slice_qids),
            config_mean_error=config_mean_error_by_slice.get(slice_name, {}),
        )
        slice_top = slice_leaderboard[0]["wins"] if slice_leaderboard else 0
        by_query_type[slice_name] = {
            "query_type": slice_name,
            "n_queries": len(slice_qids),
            "query_ids": slice_qids,
            "leaderboard": slice_leaderboard,
            "per_query_winners": slice_per_query,
            "top_win_count": slice_top,
            "configs_at_top_win_count": [
                row for row in slice_leaderboard if row["wins"] == slice_top and slice_top > 0
            ],
        }

    return {
        "metric": "group_by_category_error",
        "report_type": "config_leaderboard",
        "scoring_rule": (
            "fractional wins: each tied config at lowest query_error gets 1/n_tied of a win; "
            "leaderboard sorted by wins desc then mean_query_error asc"
        ),
        "n_queries": n_queries,
        "n_configs": len(per_config),
        "per_query_winners": per_query_winners,
        "leaderboard": leaderboard,
        "top_win_count": top_wins,
        "configs_at_top_win_count": leaders_at_top,
        "by_query_type": by_query_type,
    }


def format_config_leaderboard(
    leaderboard_report: dict[str, Any],
    *,
    top_n: int = 15,
    top_n_per_query_type: int = 5,
) -> str:
    """Human-readable config win-count table."""
    lines: list[str] = []
    n_queries = int(leaderboard_report.get("n_queries") or 0)
    lines.append("=" * 72)
    lines.append("CONFIG LEADERBOARD (query wins = lowest category error)")
    lines.append("=" * 72)
    lines.append(f"Queries scored: {n_queries} | Configs: {leaderboard_report.get('n_configs')}")
    lines.append(f"Rule: {leaderboard_report.get('scoring_rule')}")
    lines.append("")
    lines.append("Overall:")
    lines.append(f"{'wins':>7}  {'win%':>6}  {'mean_err':>10}  config_id")
    for row in (leaderboard_report.get("leaderboard") or [])[:top_n]:
        wins = float(row.get("wins") or 0.0)
        win_rate = float(row.get("win_rate") or 0.0)
        mean_err = row.get("mean_query_error")
        mean_err_s = f"{float(mean_err):.4f}" if mean_err is not None else "n/a"
        wins_s = f"{wins:.2f}" if wins != int(wins) else f"{int(wins)}"
        lines.append(f"{wins_s:>7}  {win_rate:6.1%}  {mean_err_s:>10}  {row.get('config_id')}")
    if len(leaderboard_report.get("leaderboard") or []) > top_n:
        lines.append(f"... ({len(leaderboard_report['leaderboard']) - top_n} more configs in JSON)")

    by_query_type = leaderboard_report.get("by_query_type") or {}
    if by_query_type:
        lines.append("")
        lines.append("By query type (aggregation slice):")
        for slice_name, slice_report in by_query_type.items():
            n_slice = int(slice_report.get("n_queries") or 0)
            lines.append("")
            lines.append(f"  [{slice_name}] {n_slice} queries")
            lines.append(f"  {'wins':>7}  {'win%':>6}  {'mean_err':>10}  config_id")
            for row in (slice_report.get("leaderboard") or [])[:top_n_per_query_type]:
                wins = float(row.get("wins") or 0.0)
                win_rate = float(row.get("win_rate") or 0.0)
                mean_err = row.get("mean_query_error")
                mean_err_s = f"{float(mean_err):.4f}" if mean_err is not None else "n/a"
                wins_s = f"{wins:.2f}" if wins != int(wins) else f"{int(wins)}"
                lines.append(
                    f"  {wins_s:>7}  {win_rate:6.1%}  {mean_err_s:>10}  {row.get('config_id')}"
                )
            rest = len(slice_report.get("leaderboard") or []) - top_n_per_query_type
            if rest > 0:
                lines.append(f"  ... ({rest} more configs in JSON)")

    lines.append("")
    return "\n".join(lines)


CONFIG_DIMENSION_FIELDS: tuple[tuple[str, str], ...] = (
    ("er", "er_strategy"),
    ("norm", "norm_strategy"),
    ("unit", "unit_strategy"),
    ("miss", "miss_strategy"),
    ("coerce", "type_coercion"),
)


def _dimension_value_counts(per_query_winners: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Count how many queries had their best result achieved by a config with each dimension value.

    For each query, if ANY of the tied-best configs has dimension value V, that
    query is counted once for V.  A query can count toward multiple values of the
    same dimension when configs with different values are equally good — this is
    intentional: both values produced the best result.

    The count for each value is therefore the number of queries (out of n_queries)
    for which that value was present in at least one best config.  The total
    across all values in a dimension can exceed n_queries when multiple values
    tie, but each individual bar is always a whole number ≤ n_queries.
    """
    from collections import defaultdict

    from optimizer.config_space import parse_config_id

    counters: dict[str, dict[str, int]] = {dim: defaultdict(int) for dim, _ in CONFIG_DIMENSION_FIELDS}
    for row in per_query_winners:
        tied_ids = row.get("tied_config_ids") or [str(row.get("best_config_id") or "")]
        # Collect which dimension values appear in the tied-best set for this query
        seen: dict[str, set[str]] = {dim: set() for dim, _ in CONFIG_DIMENSION_FIELDS}
        for config_id in tied_ids:
            if not config_id:
                continue
            cfg = parse_config_id(config_id)
            for dim, field in CONFIG_DIMENSION_FIELDS:
                seen[dim].add(str(getattr(cfg, field)))
        # Add 1 per dimension value that appears (integer count, not fractional)
        for dim, values in seen.items():
            for value in values:
                counters[dim][value] += 1

    out: dict[str, dict[str, int]] = {}
    for dim, counter in counters.items():
        positive = {value: count for value, count in counter.items() if count > 0}
        out[dim] = dict(sorted(positive.items(), key=lambda kv: (-kv[1], kv[0])))
    return out


def build_config_winner_dimension_histograms(
    leaderboard_report: dict[str, Any],
) -> dict[str, Any]:
    """
  Count how often each config-dimension value appears among per-query winners.

  Only values with at least one win are included (zero counts omitted).
  """
    overall_winners = list(leaderboard_report.get("per_query_winners") or [])
    by_scope: dict[str, dict[str, Any]] = {
        "overall": {
            "scope": "overall",
            "n_queries": int(leaderboard_report.get("n_queries") or len(overall_winners)),
            "dimension_counts": _dimension_value_counts(overall_winners),
        }
    }

    for slice_name, slice_report in sorted(
        (leaderboard_report.get("by_query_type") or {}).items(),
        key=lambda item: (
            AGGREGATION_SLICE_ORDER.index(item[0])
            if item[0] in AGGREGATION_SLICE_ORDER
            else len(AGGREGATION_SLICE_ORDER)
        ),
    ):
        slice_winners = list(slice_report.get("per_query_winners") or [])
        by_scope[slice_name] = {
            "scope": slice_name,
            "query_type": slice_name,
            "n_queries": int(slice_report.get("n_queries") or len(slice_winners)),
            "dimension_counts": _dimension_value_counts(slice_winners),
        }

    return {
        "report_type": "config_winner_dimension_histograms",
        "scoring_rule": leaderboard_report.get("scoring_rule"),
        "n_queries": leaderboard_report.get("n_queries"),
        "dimensions": [dim for dim, _ in CONFIG_DIMENSION_FIELDS],
        "by_scope": by_scope,
    }


def save_config_winner_dimension_histogram_chart(
    *,
    scope: str,
    dimension: str,
    counts: dict[str, int],
    output_path,
) -> str | None:
    if not counts:
        return None

    from pathlib import Path

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = list(counts.keys())
    values = [counts[label] for label in labels]

    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.1), 5))
    bars = ax.bar(labels, values, color="#4C78A8", edgecolor="white")
    ax.set_title(f"Winning config values — {dimension} ({scope})")
    ax.set_xlabel(dimension)
    ax.set_ylabel("Query wins")
    ax.set_ylim(bottom=0)
    plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
    for bar, count in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            str(int(count)) if isinstance(count, (int, float)) and count == int(count) else f"{count:.2f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    fig.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return str(out.resolve())


def write_config_winner_dimension_histograms(
    histogram_report: dict[str, Any],
    output_dir,
    *,
    charts_subdir: str = "config_winner_dimension_charts",
) -> dict[str, Any]:
    from pathlib import Path

    root = Path(output_dir)
    chart_dir = root / charts_subdir
    chart_paths: dict[str, dict[str, str | None]] = {}

    for scope_name, scope_report in (histogram_report.get("by_scope") or {}).items():
        scope_paths: dict[str, str | None] = {}
        for dimension, counts in (scope_report.get("dimension_counts") or {}).items():
            chart_name = f"config_winner_{scope_name}_{dimension}.png"
            scope_paths[dimension] = save_config_winner_dimension_histogram_chart(
                scope=scope_name,
                dimension=dimension,
                counts=counts,
                output_path=chart_dir / chart_name,
            )
        chart_paths[scope_name] = scope_paths

    payload = {
        **histogram_report,
        "chart_paths": chart_paths,
        "charts_dir": str(chart_dir.resolve()),
    }
    out_json = root / "config_winner_dimension_histograms.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def analyze_viable_config_search_space(
    leaderboard_report: dict[str, Any],
    *,
    full_config_space_size: int | None = None,
) -> dict[str, Any]:
    """Identify which configs are ever tied-best on at least one query.

    Uses the tied_config_ids from per_query_winners so that configs are counted
    as 'viable' whenever they achieve the lowest query_error on a query — even
    if they share that position with other configs.  This avoids the misleading
    result where alphabetical tie-breaking makes 286/288 configs look 'prunable'
    when they are actually tied-best.

    A config is 'never optimal' only if it never achieves the minimum error on
    any query, regardless of ties.
    """
    if full_config_space_size is None:
        from optimizer.config_space import generate_config_space

        full_config_space_size = len(generate_config_space())

    leaderboard = list(leaderboard_report.get("leaderboard") or [])
    n_evaluated = len(leaderboard)
    n_queries = int(leaderboard_report.get("n_queries") or 0)

    # Collect which configs ever appear in the tied-best set for any query
    ever_optimal_ids: set[str] = set()
    for row in leaderboard_report.get("per_query_winners") or []:
        for cid in row.get("tied_config_ids") or [str(row.get("best_config_id") or "")]:
            if cid:
                ever_optimal_ids.add(cid)

    ever_winning = [row for row in leaderboard if str(row["config_id"]) in ever_optimal_ids]
    never_winning = [row for row in leaderboard if str(row["config_id"]) not in ever_optimal_ids]

    by_query_type: dict[str, dict[str, Any]] = {}
    union_ever_winning: set[str] = set()
    for slice_name, slice_report in (leaderboard_report.get("by_query_type") or {}).items():
        slice_optimal: set[str] = set()
        for row in slice_report.get("per_query_winners") or []:
            for cid in row.get("tied_config_ids") or [str(row.get("best_config_id") or "")]:
                if cid:
                    slice_optimal.add(cid)
        union_ever_winning.update(slice_optimal)
        slice_leaderboard = list(slice_report.get("leaderboard") or [])
        slice_ever = [row for row in slice_leaderboard if str(row["config_id"]) in slice_optimal]
        slice_never = [row for row in slice_leaderboard if str(row["config_id"]) not in slice_optimal]
        by_query_type[slice_name] = {
            "query_type": slice_name,
            "n_queries": int(slice_report.get("n_queries") or 0),
            "n_evaluated_configs": len(slice_leaderboard),
            "n_ever_optimal": len(slice_ever),
            "n_never_optimal": len(slice_never),
            "ever_optimal_fraction_of_evaluated": (
                float(len(slice_ever)) / len(slice_leaderboard) if slice_leaderboard else 0.0
            ),
            "ever_optimal_config_ids": sorted(str(row["config_id"]) for row in slice_ever),
            "never_optimal_config_ids": sorted(str(row["config_id"]) for row in slice_never),
        }

    n_ever_global = len(ever_winning)
    n_never_global = len(never_winning)
    n_unevaluated = max(0, full_config_space_size - n_evaluated)

    return {
        "report_type": "viable_config_search_space",
        "scoring_rule": leaderboard_report.get("scoring_rule"),
        "tie_handling": "configs are ever_optimal if they appear in the tied-best set for any query",
        "full_config_space_size": full_config_space_size,
        "n_evaluated_configs": n_evaluated,
        "n_unevaluated_configs": n_unevaluated,
        "n_queries": n_queries,
        "n_ever_optimal": n_ever_global,
        "n_never_optimal": n_never_global,
        "ever_optimal_fraction_of_evaluated": (
            float(n_ever_global) / n_evaluated if n_evaluated else 0.0
        ),
        "never_optimal_fraction_of_evaluated": (
            float(n_never_global) / n_evaluated if n_evaluated else 0.0
        ),
        "ever_optimal_fraction_of_full_space": (
            float(n_ever_global) / full_config_space_size if full_config_space_size else 0.0
        ),
        "never_optimal_fraction_of_full_space": (
            float(n_never_global) / full_config_space_size if full_config_space_size else 0.0
        ),
        "n_ever_optimal_union_across_slices": len(union_ever_winning),
        "ever_optimal_union_fraction_of_evaluated": (
            float(len(union_ever_winning)) / n_evaluated if n_evaluated else 0.0
        ),
        "ever_optimal_config_ids": sorted(str(row["config_id"]) for row in ever_winning),
        "never_optimal_config_ids": sorted(str(row["config_id"]) for row in never_winning),
        "ever_optimal_union_across_slices_config_ids": sorted(union_ever_winning),
        "by_query_type": by_query_type,
        "pruning_note": (
            "never_optimal_config_ids never appear in the tied-best set for any scored query "
            "and are safe to deprioritize in search under the same scoring rule."
        ),
    }


def write_viable_config_search_space(payload: dict[str, Any], path) -> None:
    from pathlib import Path

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_config_wins_histogram(
    leaderboard_report: dict[str, Any],
    output_path,
    *,
    scope: str = "overall",
    top_n: int = 30,
    min_wins: float = 0.0,
) -> str | None:
    """Bar chart: fractional wins per config, sorted descending.

    Shows only configs with wins > min_wins (default: all configs with any wins).
    Configs are labelled by a short hash of their config_id to keep x-axis readable;
    full config_ids are printed in the legend / title tooltip.
    """
    from pathlib import Path

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    leaderboard = list(leaderboard_report.get("leaderboard") or [])
    # Filter and sort
    rows = sorted(
        [r for r in leaderboard if float(r.get("wins") or 0) > min_wins],
        key=lambda r: -float(r.get("wins") or 0),
    )[:top_n]

    if not rows:
        return None

    labels = [str(r["config_id"]) for r in rows]
    wins = [float(r.get("wins") or 0) for r in rows]
    mean_errs = [
        float(r["mean_query_error"]) if r.get("mean_query_error") is not None else float("nan")
        for r in rows
    ]

    # Shorten labels: keep only values (strip keys like "er=", "norm=", …)
    short_labels = [
        "|".join(v.split("=", 1)[1] if "=" in v else v for v in lbl.split("|"))
        for lbl in labels
    ]

    fig, ax = plt.subplots(figsize=(max(10, len(rows) * 0.55), 6))
    bars = ax.bar(range(len(rows)), wins, color="#4C78A8", edgecolor="white")
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(short_labels, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("Fractional wins (sum = n_queries for ties)")
    ax.set_title(
        f"Config wins — {scope} "
        f"({leaderboard_report.get('n_queries')} queries, "
        f"{leaderboard_report.get('n_configs')} configs evaluated)"
    )
    ax.set_ylim(bottom=0)
    for bar, w in zip(bars, wins):
        label = f"{w:.2f}" if w != int(w) else str(int(w))
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.02,
            label,
            ha="center",
            va="bottom",
            fontsize=7,
        )
    fig.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return str(out.resolve())


def build_and_write_config_winner_analysis(
    leaderboard_report: dict[str, Any],
    output_dir,
) -> dict[str, Any]:
    from pathlib import Path

    root = Path(output_dir)

    histograms = build_config_winner_dimension_histograms(leaderboard_report)
    histogram_payload = write_config_winner_dimension_histograms(histograms, output_dir)
    viability = analyze_viable_config_search_space(leaderboard_report)
    write_viable_config_search_space(
        viability,
        root / "viable_config_search_space.json",
    )

    # Per-config wins histogram (overall + per slice)
    wins_chart_paths: dict[str, str | None] = {}
    wins_chart_paths["overall"] = save_config_wins_histogram(
        leaderboard_report,
        root / "config_wins_overall.png",
        scope="overall",
    )
    for slice_name, slice_report in (leaderboard_report.get("by_query_type") or {}).items():
        # Build a minimal leaderboard_report-shaped dict for the slice
        slice_lb_report = {
            "leaderboard": slice_report.get("leaderboard"),
            "n_queries": slice_report.get("n_queries"),
            "n_configs": leaderboard_report.get("n_configs"),
        }
        wins_chart_paths[slice_name] = save_config_wins_histogram(
            slice_lb_report,
            root / f"config_wins_{slice_name}.png",
            scope=slice_name,
        )

    return {
        "dimension_histograms": histogram_payload,
        "viable_search_space": viability,
        "config_wins_charts": wins_chart_paths,
    }


def format_config_winner_dimension_histograms(
    histogram_report: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("CONFIG WINNER DIMENSION HISTOGRAMS")
    lines.append("=" * 72)
    lines.append(f"Rule: {histogram_report.get('scoring_rule')}")
    lines.append("")

    for scope_name, scope_report in (histogram_report.get("by_scope") or {}).items():
        n_queries = int(scope_report.get("n_queries") or 0)
        lines.append(f"{scope_name} ({n_queries} queries):")
        for dimension, counts in (scope_report.get("dimension_counts") or {}).items():
            if not counts:
                continue
            parts = ", ".join(f"{value}={count}" for value, count in counts.items())
            lines.append(f"  {dimension}: {parts}")
        lines.append("")

    return "\n".join(lines).rstrip()


def format_viable_config_search_space(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("VIABLE CONFIG SEARCH SPACE")
    lines.append("=" * 72)
    lines.append(f"Tie handling: {report.get('tie_handling', 'tied-best set membership')}")
    full = int(report.get("full_config_space_size") or 0)
    evaluated = int(report.get("n_evaluated_configs") or 0)
    ever = int(report.get("n_ever_optimal") or 0)
    never = int(report.get("n_never_optimal") or 0)
    union = int(report.get("n_ever_optimal_union_across_slices") or 0)
    lines.append(f"Full config space: {full}")
    lines.append(f"Evaluated in grid: {evaluated}")
    lines.append(
        f"Ever tied-best on ≥1 query (overall): {ever} "
        f"({float(report.get('ever_optimal_fraction_of_evaluated') or 0):.1%} of evaluated, "
        f"{float(report.get('ever_optimal_fraction_of_full_space') or 0):.1%} of full space)"
    )
    lines.append(
        f"Never optimal on any query: {never} "
        f"({float(report.get('never_optimal_fraction_of_evaluated') or 0):.1%} of evaluated)"
    )
    lines.append(
        f"Ever optimal in ≥1 slice (union): {union} "
        f"({float(report.get('ever_optimal_union_fraction_of_evaluated') or 0):.1%} of evaluated)"
    )
    lines.append("")
    lines.append(str(report.get("pruning_note") or ""))
    return "\n".join(lines)


def write_category_error_report(payload: dict[str, Any], path) -> None:
    from pathlib import Path

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
