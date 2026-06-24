"""Programmatic aggregation query generator for the CSPaper dataset.

The cspaper table has no numeric columns, so all aggregations are COUNT-based.
Grouping columns cover low-to-medium cardinality categorical attributes.

Query slices:
  - agg_only:   GROUP BY categorical, COUNT(paper_name)
  - agg_filter: agg_only + WHERE on a different categorical column
"""

from __future__ import annotations

import itertools
from typing import Iterator

TABLE = "cspaper"

GROUP_COLS = [
    "topic",
    "uses_knowledge_graph",
    "reasoning_depth",
    "retrieval_method",
    "uses_reranker",
    "data_modality",
    "application_domain",
    "use_agent",
    "multi_turn_retrieval",
]

FILTER_SPECS: list[tuple[str, str]] = [
    ("topic = 'Retrieval-Augmented Generation'",   "topic"),
    ("topic = 'Question Answering'",               "topic"),
    ("topic = 'Information Retrieval'",            "topic"),
    ("uses_knowledge_graph = 'Yes'",               "uses_knowledge_graph"),
    ("uses_knowledge_graph = 'No'",                "uses_knowledge_graph"),
    ("reasoning_depth = 'single-hop'",             "reasoning_depth"),
    ("reasoning_depth = 'multi-hop'",              "reasoning_depth"),
    ("uses_reranker = 'Yes'",                      "uses_reranker"),
    ("uses_reranker = 'No'",                       "uses_reranker"),
    ("use_agent = 'Yes'",                          "use_agent"),
    ("use_agent = 'No'",                           "use_agent"),
    ("multi_turn_retrieval = 'Yes'",               "multi_turn_retrieval"),
    ("multi_turn_retrieval = 'No'",                "multi_turn_retrieval"),
    ("application_domain = 'General'",             "application_domain"),
    ("application_domain = 'Healthcare'",          "application_domain"),
    ("application_domain = 'Finance'",             "application_domain"),
    ("application_domain = 'Education'",           "application_domain"),
    ("data_modality = 'Text'",                     "data_modality"),
    ("retrieval_method = 'Dense Retrieval'",       "retrieval_method"),
    ("retrieval_method = 'Sparse Retrieval'",      "retrieval_method"),
    ("retrieval_method = 'Hybrid Retrieval'",      "retrieval_method"),
]


def generate_agg_only() -> Iterator[str]:
    for grp in GROUP_COLS:
        yield f"SELECT {grp}, COUNT(paper_name) AS count_papers FROM {TABLE} GROUP BY {grp};"


def generate_agg_filter() -> Iterator[str]:
    for grp, (pred, pred_col) in itertools.product(GROUP_COLS, FILTER_SPECS):
        if pred_col == grp:
            continue
        yield (
            f"SELECT {grp}, COUNT(paper_name) AS count_papers "
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


def generate_all_candidates_cspaper() -> list[dict]:
    candidates: list[dict] = []
    counter = 0
    for sql in _dedupe(list(generate_agg_only())):
        candidates.append({
            "query_id": f"agg_only_cspaper_gen_{counter}",
            "sql_query": sql,
            "category": "Agg",
            "slice": "agg_only",
            "metadata": {"generated": True},
        })
        counter += 1
    for sql in _dedupe(list(generate_agg_filter())):
        candidates.append({
            "query_id": f"agg_filter_cspaper_gen_{counter}",
            "sql_query": sql,
            "category": "Agg",
            "slice": "agg_filter",
            "metadata": {"generated": True},
        })
        counter += 1
    return candidates


if __name__ == "__main__":
    candidates = generate_all_candidates_cspaper()
    agg_only = [q for q in candidates if q["slice"] == "agg_only"]
    agg_filter = [q for q in candidates if q["slice"] == "agg_filter"]
    print(f"agg_only:   {len(agg_only)}")
    print(f"agg_filter: {len(agg_filter)}")
    print(f"total:      {len(candidates)}")
    print("\nSample agg_only:")
    for q in agg_only[:4]:
        print(" ", q["sql_query"])
    print("\nSample agg_filter:")
    for q in agg_filter[:4]:
        print(" ", q["sql_query"])
