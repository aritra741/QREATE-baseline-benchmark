"""Deduplication and balanced query selection (no query_alignment imports)."""

from __future__ import annotations

import re
from collections import defaultdict


def stable_slice_seed(base_seed: int, slice_name: str) -> int:
    return base_seed + sum(ord(c) for c in slice_name) % 1000

_AGG_FUNCS = ("count", "sum", "avg", "min", "max")
_TEMPORAL_COLS = frozenset(
    {"birth_date", "draft_year", "founded_year", "death_date", "own_year"}
)


def normalize_sql(sql: str) -> str:
    text = sql.strip().rstrip(";").lower()
    text = re.sub(r"\s+", " ", text)
    return text


def sql_signature(sql: str) -> str:
    norm = normalize_sql(sql)
    tables = sorted(set(re.findall(r"\b(player|team|city|owner)\b", norm)))
    group_cols = re.findall(r"group\s+by\s+([^;]+?)(?:\s+order\s+by|\s+limit|$)", norm)
    group_part = group_cols[0].strip() if group_cols else ""
    agg_exprs = re.findall(r"\b(count|sum|avg|min|max)\s*\(\s*([^)]*)\)", norm)
    aggs = ",".join(f"{func}({arg.strip()})" for func, arg in sorted(agg_exprs))
    joins = sorted(set(re.findall(r"\bjoin\b\s+(\w+)", norm)))
    where = ""
    where_match = re.search(r"\bwhere\b(.+?)(?:\bgroup\s+by\b|$)", norm)
    if where_match:
        where = re.sub(r"'[^']*'", "'?'", where_match.group(1))
        where = re.sub(r"\b\d+(?:\.\d+)?\b", "N", where)
        where = re.sub(r"\s+", " ", where).strip()
    return "|".join([",".join(tables), group_part, ",".join(aggs), ",".join(joins), where])


def dedupe_queries(queries: list[dict]) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    removed: list[dict] = []
    seen_sql: set[str] = set()
    seen_sig: set[str] = set()

    for query in queries:
        sql = query.get("sql_query", "")
        norm = normalize_sql(sql)
        sig = sql_signature(sql)
        qid = str(query.get("query_id", ""))
        if norm in seen_sql or sig in seen_sig:
            removed.append(
                {
                    "query_id": qid,
                    "reason": "duplicate_sql" if norm in seen_sql else "near_duplicate_signature",
                    "sql": sql,
                }
            )
            continue
        seen_sql.add(norm)
        seen_sig.add(sig)
        kept.append(query)
    return kept, removed


def _difficulty_bin(slice_name: str, sql: str) -> str:
    norm = normalize_sql(sql)
    if slice_name == "agg_only":
        group_match = re.search(r"group\s+by\s+([^;]+)", norm)
        group_col = group_match.group(1).strip().split(",")[0].strip() if group_match else "none"
        agg = next((f for f in _AGG_FUNCS if f"{f}(" in norm), "none")
        return f"{group_col}|{agg}"
    if slice_name == "agg_filter":
        n_preds = len(re.findall(r"\b(and|or)\b", norm))
        has_string = bool(re.search(r"=\s*'", norm))
        has_range = bool(re.search(r"[<>]=?", norm))
        pred_type = "string" if has_string else ("range" if has_range else "numeric")
        return f"{pred_type}|preds_{min(n_preds + 1, 4)}"
    if slice_name == "agg_join":
        n_joins = len(re.findall(r"\bjoin\b", norm))
        tables = sorted(set(re.findall(r"\b(player|team|city)\b", norm)))
        return f"joins_{n_joins}|{'_'.join(tables)}"
    if slice_name == "agg_filter_join":
        n_joins = len(re.findall(r"\bjoin\b", norm))
        n_preds = len(re.findall(r"\b(and|or)\b", norm))
        return f"joins_{n_joins}|preds_{min(n_preds + 1, 4)}"
    if slice_name == "agg_temporal":
        temporal_col = next((c for c in _TEMPORAL_COLS if c in norm), "year_expr")
        has_range = bool(
            re.search(r"birth_date\s*[<>]", norm) or re.search(r"draft_year\s*[<>]", norm)
        )
        mode = "range" if has_range else "equality"
        return f"{temporal_col}|{mode}"
    return "default"


def select_balanced_queries(
    queries: list[dict],
    *,
    slice_name: str,
    target_count: int,
    seed: int,
) -> list[dict]:
    import random

    if len(queries) <= target_count:
        return list(queries)

    bins: dict[str, list[dict]] = defaultdict(list)
    for query in queries:
        bins[_difficulty_bin(slice_name, query.get("sql_query", ""))].append(query)

    rng = random.Random(seed)
    for bucket in bins.values():
        rng.shuffle(bucket)

    bin_keys = sorted(bins.keys())
    selected: list[dict] = []
    idx = 0
    while len(selected) < target_count and bin_keys:
        key = bin_keys[idx % len(bin_keys)]
        if bins[key]:
            selected.append(bins[key].pop(0))
        else:
            bin_keys = [k for k in bin_keys if bins[k]]
            if not bin_keys:
                break
            idx = 0
            continue
        idx += 1
    return selected
