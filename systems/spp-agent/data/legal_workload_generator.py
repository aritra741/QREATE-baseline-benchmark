"""Programmatic aggregation query generator for the Legal dataset.

The legal table has a single-table schema with:
  - Numeric aggregation targets: fine_amount, legal_basis_num, hearing_year,
    judgment_year
  - Fixed-vocabulary categorical columns: case_type, verdict, evidence,
    first_judge, judge_name
  - Free-text columns: plaintiff, defendant, charges, counsel_for_applicant,
    counsel_for_respondent, url (not useful for GROUP BY)

This dataset was chosen as a *whole-document* numeric control alongside
Player: unlike Finan/CSPaper, Legal documents (median ~19K chars) fit in a
single LLM context window without chunking, so it uses the exact same
extraction pipeline as Player/Med/Art/CSPaper — isolating "numeric vs.
text-heavy" as the variable of interest rather than confounding it with a
different (chunked) extraction pipeline.

Query slices generated:
  - agg_only:   GROUP BY categorical, AGG(numeric)
  - agg_filter: agg_only + WHERE on categorical or numeric range
"""

from __future__ import annotations

import itertools
from typing import Iterator

TABLE = "legal"

# Categorical columns safe for GROUP BY (fixed or near-fixed vocabulary,
# no pipe-separated multi-value cells).
GROUP_COLS = [
    "case_type",
    "verdict",
    "judge_name",
    "hearing_year",
    "judgment_year",
    "evidence",
    "first_judge",
]

# Numeric columns safe for aggregation
NUMERIC_COLS = [
    "fine_amount",
    "legal_basis_num",
    "hearing_year",
    "judgment_year",
]

AGG_FUNCS = ["SUM", "AVG", "MIN", "MAX", "COUNT"]

# Representative filter predicates (predicate, referenced_col) pairs for WHERE clauses
FILTER_SPECS: list[tuple[str, str]] = [
    ("case_type = 'Commercial Case'",      "case_type"),
    ("case_type = 'Civil Case'",           "case_type"),
    ("case_type = 'Criminal Case'",        "case_type"),
    ("case_type = 'Administrative Case'",  "case_type"),
    ("verdict = 'Dismissed'",              "verdict"),
    ("verdict = 'Approved'",               "verdict"),
    ("verdict = 'Guilty'",                 "verdict"),
    ("verdict = 'Not Guilty'",             "verdict"),
    ("evidence = 1",                       "evidence"),
    ("evidence = 0",                       "evidence"),
    ("first_judge = 1",                    "first_judge"),
    ("first_judge = 0",                    "first_judge"),
    ("fine_amount > 0",                    "fine_amount"),
    ("fine_amount > 10000",                "fine_amount"),
    ("legal_basis_num > 1",                "legal_basis_num"),
    ("legal_basis_num > 3",                "legal_basis_num"),
    ("hearing_year >= 2005",               "hearing_year"),
    ("judgment_year >= 2005",              "judgment_year"),
]


def _agg_expr(func: str, col: str) -> str:
    return f"{func}({col}) AS {func.lower()}_{col}"


def _is_numeric_col(col: str) -> bool:
    return col in set(NUMERIC_COLS)


def generate_agg_only() -> Iterator[str]:
    """GROUP BY categorical, AGG(numeric)."""
    for grp in GROUP_COLS:
        yield (
            f"SELECT {grp}, COUNT(ID) AS count_cases "
            f"FROM {TABLE} GROUP BY {grp};"
        )
        for num, func in itertools.product(NUMERIC_COLS, ["SUM", "AVG", "MIN", "MAX"]):
            if num == grp:
                continue
            yield (
                f"SELECT {grp}, {_agg_expr(func, num)} "
                f"FROM {TABLE} GROUP BY {grp};"
            )


def generate_agg_filter() -> Iterator[str]:
    """GROUP BY + WHERE filter on a column different from GROUP BY col."""
    for grp, num, func in itertools.product(GROUP_COLS, NUMERIC_COLS, ["SUM", "AVG", "MIN", "MAX"]):
        if num == grp:
            continue
        for pred, pred_col in FILTER_SPECS:
            if pred_col == grp:
                continue
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


def generate_all_candidates_legal() -> list[dict]:
    """Return all candidate queries as workload dicts with query_id and slice label."""
    candidates: list[dict] = []
    counter = 0

    agg_only = _dedupe(list(generate_agg_only()))
    for sql in agg_only:
        candidates.append({
            "query_id": f"agg_only_legal_gen_{counter}",
            "sql_query": sql,
            "category": "Agg",
            "slice": "agg_only",
        })
        counter += 1

    agg_filter = _dedupe(list(generate_agg_filter()))
    for sql in agg_filter:
        candidates.append({
            "query_id": f"agg_filter_legal_gen_{counter}",
            "sql_query": sql,
            "category": "Agg",
            "slice": "agg_filter",
        })
        counter += 1

    return candidates


if __name__ == "__main__":
    candidates = generate_all_candidates_legal()
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
