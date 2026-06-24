"""Programmatic aggregation query generator for the Art dataset.

The art table has a single-table schema with:
  - Numeric column: Age
  - Fixed/low-cardinality categorical columns: Birth_continent, Zodiac,
    Century, Tone, Teaching, Style, Nationality, Art_movement, Field, Genre,
    Color, Marriage, Image_Genre, Object, Composition

Query slices generated:
  - agg_only:   GROUP BY categorical, AGG(Age) or COUNT(Name)
  - agg_filter: agg_only + WHERE on a different categorical column
"""

from __future__ import annotations

import itertools
from typing import Iterator

TABLE = "art"

# Best GROUP BY columns (low-to-medium cardinality, meaningful groupings)
GROUP_COLS = [
    "birth_continent",
    "zodiac",
    "century",
    "tone",
    "teaching",
    "style",
    "nationality",
    "art_movement",
    "field",
    "color",
    "marriage",
]

# The only numeric column
NUMERIC_COL = "age"
AGG_FUNCS = ["MIN", "MAX", "AVG", "SUM"]

# Representative filter predicates for WHERE clauses
FILTER_SPECS: list[tuple[str, str]] = [
    ("birth_continent = 'Europe'",       "birth_continent"),
    ("birth_continent = 'North America'","birth_continent"),
    ("birth_continent = 'Asia'",         "birth_continent"),
    ("birth_continent = 'South America'","birth_continent"),
    ("birth_continent = 'Africa'",       "birth_continent"),
    ("zodiac = 'Aries'",                 "zodiac"),
    ("zodiac = 'Taurus'",                "zodiac"),
    ("zodiac = 'Gemini'",                "zodiac"),
    ("zodiac = 'Leo'",                   "zodiac"),
    ("zodiac = 'Virgo'",                 "zodiac"),
    ("zodiac = 'Scorpio'",               "zodiac"),
    ("century = '20th'",                 "century"),
    ("century = '19th-20th'",            "century"),
    ("century = '20th-21st'",            "century"),
    ("century = '19th'",                 "century"),
    ("tone = 'Warm'",                    "tone"),
    ("tone = 'Cool'",                    "tone"),
    ("tone = 'Neutral'",                 "tone"),
    ("tone = 'Dark'",                    "tone"),
    ("tone = 'Bright'",                  "tone"),
    ("teaching = 1",                     "teaching"),
    ("teaching = 0",                     "teaching"),
    ("marriage = 'Married'",             "marriage"),
    ("marriage = 'Unmarried'",           "marriage"),
    ("marriage = 'Widowed'",             "marriage"),
    ("marriage = 'Remarried'",           "marriage"),
    ("age > 0",                          "age"),
    ("age > 50",                         "age"),
    ("age > 70",                         "age"),
    ("age < 50",                         "age"),
]


def generate_agg_only() -> Iterator[str]:
    """GROUP BY categorical, AGG(age) or COUNT(name)."""
    for grp in GROUP_COLS:
        yield f"SELECT {grp}, COUNT(name) AS count_artists FROM {TABLE} GROUP BY {grp};"
        for func in AGG_FUNCS:
            yield (
                f"SELECT {grp}, {func}({NUMERIC_COL}) AS {func.lower()}_{NUMERIC_COL} "
                f"FROM {TABLE} GROUP BY {grp};"
            )


def generate_agg_filter() -> Iterator[str]:
    """GROUP BY + WHERE on a column different from GROUP BY col."""
    for grp, func in itertools.product(GROUP_COLS, AGG_FUNCS):
        for pred, pred_col in FILTER_SPECS:
            if pred_col == grp:
                continue
            yield (
                f"SELECT {grp}, {func}({NUMERIC_COL}) AS {func.lower()}_{NUMERIC_COL} "
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


def generate_all_candidates_art() -> list[dict]:
    """Return all candidate queries as workload dicts."""
    candidates: list[dict] = []
    counter = 0

    for sql in _dedupe(list(generate_agg_only())):
        candidates.append({
            "query_id": f"agg_only_art_gen_{counter}",
            "sql_query": sql,
            "category": "Agg",
            "slice": "agg_only",
            "metadata": {"generated": True},
        })
        counter += 1

    for sql in _dedupe(list(generate_agg_filter())):
        candidates.append({
            "query_id": f"agg_filter_art_gen_{counter}",
            "sql_query": sql,
            "category": "Agg",
            "slice": "agg_filter",
            "metadata": {"generated": True},
        })
        counter += 1

    return candidates


if __name__ == "__main__":
    candidates = generate_all_candidates_art()
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
