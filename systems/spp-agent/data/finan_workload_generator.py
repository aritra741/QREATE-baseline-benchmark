"""Programmatic aggregation query generator for the Finan (Finance) dataset.

The finance table has a single-table schema with:
  - Numeric columns: revenue, net_profit_or_loss, total_Debt, total_assets,
    cash_reserves, net_assets, earnings_per_share, dividend_per_share,
    the_highest_ownership_stake, bussiness_sales, bussiness_profit,
    bussiness_cost, business_segments_num
  - Fixed-vocabulary categorical columns: exchange_code, principal_activities,
    major_equity_changes, major_events, business_risks, remuneration_policy,
    auditor
  - Free-text columns: company_name, registered_office, largest_shareholder
    (not useful for GROUP BY)

Query slices generated:
  - agg_only:   GROUP BY categorical, AGG(numeric)
  - agg_filter: agg_only + WHERE on categorical or numeric range
"""

from __future__ import annotations

import itertools
from typing import Iterator

TABLE = "finance"

# Categorical columns safe for GROUP BY (fixed or near-fixed vocabulary)
GROUP_COLS = [
    "exchange_code",
    "principal_activities",
    "major_equity_changes",
    "major_events",
    "business_risks",
    "remuneration_policy",
    "auditor",
]

# Numeric columns safe for aggregation
NUMERIC_COLS = [
    "revenue",
    "net_profit_or_loss",
    "total_Debt",
    "total_assets",
    "cash_reserves",
    "net_assets",
    "earnings_per_share",
    "dividend_per_share",
    "the_highest_ownership_stake",
    "bussiness_sales",
    "bussiness_profit",
    "bussiness_cost",
    "business_segments_num",
]

AGG_FUNCS = ["SUM", "AVG", "MIN", "MAX", "COUNT"]

# Representative filter predicates (value, col) pairs for WHERE clauses
FILTER_SPECS: list[tuple[str, str]] = [
    ("exchange_code = 'ASX'",          "exchange_code"),
    ("exchange_code = 'NYSE'",         "exchange_code"),
    ("exchange_code = 'LSE'",          "exchange_code"),
    ("major_equity_changes = 'Yes'",   "major_equity_changes"),
    ("major_equity_changes = 'No'",    "major_equity_changes"),
    ("remuneration_policy = 'Fixed'",               "remuneration_policy"),
    ("remuneration_policy = 'Performance-based'",   "remuneration_policy"),
    ("remuneration_policy = 'Mixed'",               "remuneration_policy"),
    ("principal_activities LIKE '%Mining%'",        "principal_activities"),
    ("principal_activities LIKE '%Technology%'",    "principal_activities"),
    ("principal_activities LIKE '%Healthcare%'",    "principal_activities"),
    ("principal_activities LIKE '%Finance%'",       "principal_activities"),
    ("principal_activities LIKE '%Energy%'",        "principal_activities"),
    ("major_events LIKE '%M&A%'",                   "major_events"),
    ("major_events LIKE '%Litigation%'",            "major_events"),
    ("major_events LIKE '%Restructuring%'",         "major_events"),
    ("business_risks LIKE '%Market Risk%'",         "business_risks"),
    ("business_risks LIKE '%Credit Risk%'",         "business_risks"),
    ("business_risks LIKE '%Operational Risk%'",    "business_risks"),
    ("revenue > 0",                    "revenue"),
    ("net_profit_or_loss > 0",         "net_profit_or_loss"),
    ("net_profit_or_loss < 0",         "net_profit_or_loss"),
    ("total_assets > 0",               "total_assets"),
    ("earnings_per_share > 0",         "earnings_per_share"),
    ("business_segments_num > 1",      "business_segments_num"),
    ("business_segments_num > 3",      "business_segments_num"),
    ("the_highest_ownership_stake > 50", "the_highest_ownership_stake"),
]


def _agg_expr(func: str, col: str) -> str:
    return f"{func}({col}) AS {func.lower()}_{col}"


def _is_numeric_col(col: str) -> bool:
    return col in set(NUMERIC_COLS)


def generate_agg_only() -> Iterator[str]:
    """GROUP BY categorical, AGG(numeric)."""
    for grp in GROUP_COLS:
        # One COUNT per group column
        yield (
            f"SELECT {grp}, COUNT(company_name) AS count_companies "
            f"FROM {TABLE} GROUP BY {grp};"
        )
        # SUM/AVG/MIN/MAX on each numeric column
        for num, func in itertools.product(NUMERIC_COLS, ["SUM", "AVG", "MIN", "MAX"]):
            yield (
                f"SELECT {grp}, {_agg_expr(func, num)} "
                f"FROM {TABLE} GROUP BY {grp};"
            )


def generate_agg_filter() -> Iterator[str]:
    """GROUP BY + WHERE filter on a column different from GROUP BY col."""
    for grp, num, func in itertools.product(GROUP_COLS, NUMERIC_COLS, ["SUM", "AVG", "MIN", "MAX"]):
        for pred, pred_col in FILTER_SPECS:
            # Avoid trivial filters on the same column being grouped
            if pred_col == grp:
                continue
            # Avoid filtering on the agg column when it is the same as pred_col
            # (creates odd but technically valid queries — keep for variety)
            yield (
                f"SELECT {grp}, {_agg_expr(func, num)} "
                f"FROM {TABLE} WHERE {pred} GROUP BY {grp};"
            )


def _dedupe(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        norm = " ".join(q.lower().split())
        if norm not in seen:
            seen.add(norm)
            out.append(q)
    return out


def generate_all_candidates_finan() -> list[dict]:
    """Return all candidate queries as workload dicts with query_id and slice label."""
    candidates: list[dict] = []
    counter = 0

    agg_only = _dedupe(list(generate_agg_only()))
    for sql in agg_only:
        candidates.append({
            "query_id": f"agg_only_finan_gen_{counter}",
            "sql_query": sql,
            "category": "Agg",
            "slice": "agg_only",
        })
        counter += 1

    agg_filter = _dedupe(list(generate_agg_filter()))
    for sql in agg_filter:
        candidates.append({
            "query_id": f"agg_filter_finan_gen_{counter}",
            "sql_query": sql,
            "category": "Agg",
            "slice": "agg_filter",
        })
        counter += 1

    return candidates


if __name__ == "__main__":
    candidates = generate_all_candidates_finan()
    agg_only = [q for q in candidates if q["slice"] == "agg_only"]
    agg_filter = [q for q in candidates if q["slice"] == "agg_filter"]
    print(f"agg_only:   {len(agg_only)} queries")
    print(f"agg_filter: {len(agg_filter)} queries")
    print(f"total:      {len(candidates)} queries")
    print("\nSample agg_only:")
    for q in agg_only[:5]:
        print(" ", q["sql_query"])
    print("\nSample agg_filter:")
    for q in agg_filter[:5]:
        print(" ", q["sql_query"])
