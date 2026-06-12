"""Balanced aggregation workload selection with deduplication."""

from __future__ import annotations

from typing import Any

from data.aggregation_slices import classify_aggregation_slice
from data.corpus_feasibility import missing_corpus_literals
from data.query_alignment import (
    corpus_entity_types,
    filter_queries_by_corpus_coverage,
    filter_queries_for_tables,
    tables_referenced_by_queries,
)
from data.workload_selection import dedupe_queries, select_balanced_queries
from pipeline.schema import Schema


def is_query_table_feasible(
    query: dict,
    schema: Schema,
    corpus: list[dict],
    table_filter: set[str],
) -> tuple[bool, str]:
    sql = query.get("sql_query", "")
    corpus_types = corpus_entity_types(corpus)
    refs = tables_referenced_by_queries([query], schema)
    if table_filter and not any(t in refs for t in table_filter):
        return False, "missing_required_table_filter"
    if refs and not refs.issubset(corpus_types):
        return False, f"missing_corpus_tables:{sorted(refs - corpus_types)}"
    missing = missing_corpus_literals(sql, corpus)
    if missing:
        return False, f"missing_where_literals:{missing[:3]}"
    return True, "ok"


def filter_feasible_queries(
    queries: list[dict],
    schema: Schema,
    corpus: list[dict],
    table_filter: set[str],
) -> tuple[list[dict], list[dict]]:
    feasible: list[dict] = []
    removed: list[dict] = []
    for query in queries:
        ok, reason = is_query_table_feasible(query, schema, corpus, table_filter)
        if ok:
            feasible.append(query)
        else:
            removed.append(
                {
                    "query_id": query.get("query_id"),
                    "reason": reason,
                    "sql": query.get("sql_query"),
                }
            )
    return feasible, removed


def build_balanced_slice_pool(
    queries: list[dict],
    *,
    slice_name: str,
    schema: Schema,
    corpus: list[dict],
    table_filter: set[str],
    target_count: int,
    seed: int,
) -> dict[str, Any]:
    slice_queries = [
        q
        for q in queries
        if classify_aggregation_slice(q.get("sql_query", "")) == slice_name
    ]
    slice_queries = filter_queries_for_tables(slice_queries, schema, table_filter)
    slice_queries = filter_queries_by_corpus_coverage(
        slice_queries, schema, corpus_entity_types(corpus)
    )
    feasible, infeasible = filter_feasible_queries(
        slice_queries, schema, corpus, table_filter
    )
    deduped, dupes = dedupe_queries(feasible)
    selected = select_balanced_queries(
        deduped,
        slice_name=slice_name,
        target_count=target_count,
        seed=seed,
    )
    return {
        "slice": slice_name,
        "target_count": target_count,
        "selected_count": len(selected),
        "pool_after_dedupe": len(deduped),
        "pool_before_dedupe": len(feasible),
        "selected_queries": selected,
        "removed_infeasible": infeasible,
        "removed_duplicates": dupes,
        "max_feasible": len(deduped),
        "reached_target": len(selected) >= target_count,
    }


def build_feasible_slice_pool(
    queries: list[dict],
    *,
    slice_name: str,
    schema: Schema,
    corpus: list[dict],
    table_filter: set[str],
) -> dict[str, Any]:
    """Return deduplicated feasible queries for a slice (no count cap)."""
    slice_queries = [
        q
        for q in queries
        if classify_aggregation_slice(q.get("sql_query", "")) == slice_name
    ]
    slice_queries = filter_queries_for_tables(slice_queries, schema, table_filter)
    slice_queries = filter_queries_by_corpus_coverage(
        slice_queries, schema, corpus_entity_types(corpus)
    )
    feasible, infeasible = filter_feasible_queries(
        slice_queries, schema, corpus, table_filter
    )
    deduped, dupes = dedupe_queries(feasible)
    return {
        "slice": slice_name,
        "pool_after_dedupe": len(deduped),
        "pool_before_dedupe": len(feasible),
        "queries": deduped,
        "removed_infeasible": infeasible,
        "removed_duplicates": dupes,
        "max_feasible": len(deduped),
    }


def summarize_workload_balance(
    slice_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    per_slice = {
        report["slice"]: {
            "target": report["target_count"],
            "selected": report["selected_count"],
            "max_feasible": report["max_feasible"],
            "reached_target": report["reached_target"],
        }
        for report in slice_reports
    }
    total_selected = sum(r["selected_count"] for r in slice_reports)
    total_target = sum(r["target_count"] for r in slice_reports)
    return {
        "per_slice": per_slice,
        "total_target": total_target,
        "total_selected": total_selected,
        "all_slices_balanced": all(r["reached_target"] for r in slice_reports),
    }
