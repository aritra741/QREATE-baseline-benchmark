from __future__ import annotations

from collections import Counter

from llm.client import estimate_tokens


def compute_tier0(
    *,
    corpus: list[dict],
    queries: list[dict],
    schema,
    config_space_size: int,
    budget: float,
) -> dict:
    token_counts = [estimate_tokens(doc["text"]) for doc in corpus]
    avg_tokens = sum(token_counts) / len(token_counts) if token_counts else 0.0
    max_tokens = max(token_counts) if token_counts else 0.0
    std_tokens = (
        (sum((t - avg_tokens) ** 2 for t in token_counts) / len(token_counts)) ** 0.5
        if token_counts
        else 0.0
    )

    categories = [q.get("category") or "unknown" for q in queries]
    query_type_mix = dict(Counter(categories))

    schema_cols = {f"{t}.{c}" for t, cols in schema.tables.items() for c in cols}
    referenced = set()
    for q in queries:
        sql = q.get("sql_query", "").lower()
        for col_ref in schema_cols:
            table, col = col_ref.split(".", 1)
            if col.lower() in sql or table.lower() in sql:
                referenced.add(col_ref)

    coverage = len(referenced) / len(schema_cols) if schema_cols else 0.0

    return {
        "num_docs": len(corpus),
        "avg_doc_tokens": avg_tokens,
        "max_doc_tokens": max_tokens,
        "doc_token_std": std_tokens,
        "num_queries": len(queries),
        "query_type_mix": query_type_mix,
        "referenced_attribute_coverage": coverage,
        "estimated_extraction_cost": avg_tokens * len(corpus),
        "config_space_size": config_space_size,
        "budget": budget,
    }
