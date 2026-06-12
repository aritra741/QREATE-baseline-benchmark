from __future__ import annotations

import re
from collections import defaultdict

_AGG_FUNCS_RE = re.compile(r"\b(count|sum|avg|min|max)\s*\(", re.IGNORECASE)
_GROUP_BY_RE = re.compile(r"\bgroup\s+by\b", re.IGNORECASE)
_JOIN_RE = re.compile(r"\bjoin\b", re.IGNORECASE)
_WHERE_RE = re.compile(r"\bwhere\b", re.IGNORECASE)
_TEMPORAL_RE = re.compile(
    r"\b(birth_date|draft_year|founded_year|death_date|year|date)\b|"
    r"\b(year|date)\s*\(|extract\s*\(",
    re.IGNORECASE,
)

AGGREGATION_SLICE_ORDER = [
    "agg_only",
    "agg_filter",
    "agg_join",
    "agg_filter_join",
    "agg_temporal",
]

# Single workload containing every aggregation slice query (benchmark mode).
UNIFIED_WORKLOAD_NAME = "all_queries"


def is_aggregation_query(sql: str) -> bool:
    """Query is eligible if it contains aggregation functions or GROUP BY."""
    return bool(_AGG_FUNCS_RE.search(sql) or _GROUP_BY_RE.search(sql))


def classify_aggregation_slice(sql: str) -> str | None:
    """
    Classify an aggregation query by additional operators.

    Returns None if the query is not aggregation-bearing.
    """
    if not is_aggregation_query(sql):
        return None

    has_join = bool(_JOIN_RE.search(sql))
    has_where = bool(_WHERE_RE.search(sql))
    has_temporal = bool(_TEMPORAL_RE.search(sql))

    if has_temporal:
        return "agg_temporal"
    if has_join and has_where:
        return "agg_filter_join"
    if has_join:
        return "agg_join"
    if has_where:
        return "agg_filter"
    return "agg_only"


def filter_aggregation_queries(queries: list[dict]) -> list[dict]:
    kept = [q for q in queries if is_aggregation_query(q.get("sql_query", ""))]
    if not kept:
        raise RuntimeError("No aggregation queries found in workload.")
    return kept


def group_queries_by_aggregation_slice(queries: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for query in queries:
        slice_name = classify_aggregation_slice(query.get("sql_query", ""))
        if slice_name:
            buckets[slice_name].append(query)
    return dict(buckets)


def available_aggregation_slices(
    queries: list[dict],
    *,
    min_queries: int = 1,
    preferred_order: list[str] | None = None,
) -> list[str]:
    buckets = group_queries_by_aggregation_slice(filter_aggregation_queries(queries))
    order = preferred_order or AGGREGATION_SLICE_ORDER
    available = [name for name in order if len(buckets.get(name, [])) >= min_queries]
    return available


def queries_for_aggregation_slice(queries: list[dict], slice_name: str) -> list[dict]:
    buckets = group_queries_by_aggregation_slice(filter_aggregation_queries(queries))
    if slice_name not in buckets:
        raise RuntimeError(
            f"No aggregation queries for slice '{slice_name}'. "
            f"Available: {sorted(buckets)}"
        )
    return buckets[slice_name]


def unified_aggregation_queries(
    queries: list[dict],
    *,
    slice_names: list[str] | None = None,
) -> list[dict]:
    """Union of aggregation queries across slices, deduplicated by query_id."""
    order = slice_names or AGGREGATION_SLICE_ORDER
    buckets = group_queries_by_aggregation_slice(filter_aggregation_queries(queries))
    seen: set[str] = set()
    unified: list[dict] = []
    for slice_name in order:
        for query in buckets.get(slice_name, []):
            qid = str(query.get("query_id", query.get("sql_query", "")))
            if qid in seen:
                continue
            seen.add(qid)
            unified.append(query)
    if not unified:
        raise RuntimeError(
            f"No aggregation queries for unified workload. "
            f"Requested slices: {order}. Available: {sorted(buckets)}"
        )
    return unified
