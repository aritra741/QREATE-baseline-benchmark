from __future__ import annotations

import random
import re
from dataclasses import replace

from pipeline.schema import Schema

from data.instance_builder import Instance
from data.aggregation_slices import queries_for_aggregation_slice


def tables_referenced_by_queries(queries: list[dict], schema: Schema) -> set[str]:
    """
    Parse SQL queries and return referenced table names.
    For this smoke test, simple string/regex matching against schema table names is enough.
    """
    referenced: set[str] = set()
    for query in queries:
        sql = query.get("sql_query", "").lower()
        for table in schema.tables:
            if re.search(rf"\b{re.escape(table.lower())}\b", sql):
                referenced.add(table)
    return referenced


def filter_docs_for_tables(corpus: list[dict], required_tables: set[str]) -> list[dict]:
    """
    Keep documents whose doc_id prefix matches one of the required tables.
    Example: required_tables={"player"} keeps docs like "player/player_1".
    """
    if not required_tables:
        raise ValueError("required_tables must not be empty")

    normalized = {t.lower() for t in required_tables}
    matched: list[dict] = []

    for doc in corpus:
        doc_id = doc.get("doc_id", "")
        prefix = doc_id.split("/")[0].lower() if "/" in doc_id else doc_id.split("_")[0].lower()
        hint = str(doc.get("metadata", {}).get("table_hint", "")).lower()
        if prefix in normalized or hint in normalized:
            matched.append(doc)

    if not matched:
        raise RuntimeError(
            f"No corpus documents match required tables {sorted(required_tables)}. "
            "Check doc_id prefixes (e.g. player/player_1)."
        )
    return matched


def filter_queries_for_tables(queries: list[dict], schema: Schema, required_tables: set[str]) -> list[dict]:
    """Keep queries that reference at least one of the required tables."""
    if not required_tables:
        return queries
    kept: list[dict] = []
    for query in queries:
        sql = query.get("sql_query", "").lower()
        for table in required_tables:
            if re.search(rf"\b{re.escape(table.lower())}\b", sql):
                kept.append(query)
                break
    if not kept:
        raise RuntimeError(
            f"No queries reference required tables {sorted(required_tables)}."
        )
    return kept


def corpus_entity_types(corpus: list[dict]) -> set[str]:
    """Entity types present in the text corpus (doc_id prefix / table_hint)."""
    types: set[str] = set()
    for doc in corpus:
        doc_id = doc.get("doc_id", "")
        prefix = doc_id.split("/")[0].lower() if "/" in doc_id else doc_id.split("_")[0].lower()
        if prefix:
            types.add(prefix)
        hint = str(doc.get("metadata", {}).get("table_hint", "")).lower()
        if hint:
            types.add(hint)
    return types


def filter_queries_by_corpus_coverage(
    queries: list[dict],
    schema: Schema,
    corpus_types: set[str],
) -> list[dict]:
    """Keep queries whose referenced tables all have text corpus coverage."""
    kept: list[dict] = []
    for query in queries:
        refs = tables_referenced_by_queries([query], schema)
        if refs and refs.issubset(corpus_types):
            kept.append(query)
    return kept


def sample_corpus_stratified(
    corpus: list[dict],
    required_tables: set[str],
    num_docs: int,
    seed: int,
) -> list[dict]:
    """Sample docs evenly across required entity types present in the corpus."""
    rng = random.Random(seed)
    if not required_tables:
        raise ValueError("required_tables must not be empty")

    per_table = max(1, num_docs // len(required_tables))
    sampled: list[dict] = []
    seen_ids: set[str] = set()

    for table in sorted(required_tables):
        table_docs = filter_docs_for_tables(corpus, {table})
        rng.shuffle(table_docs)
        for doc in table_docs[:per_table]:
            if doc["doc_id"] not in seen_ids:
                sampled.append(doc)
                seen_ids.add(doc["doc_id"])

    if len(sampled) < num_docs:
        pool = filter_docs_for_tables(corpus, required_tables)
        rng.shuffle(pool)
        for doc in pool:
            if doc["doc_id"] in seen_ids:
                continue
            sampled.append(doc)
            seen_ids.add(doc["doc_id"])
            if len(sampled) >= num_docs:
                break

    return sampled[:num_docs]


def assert_required_table_coverage(
    rows_by_table: dict[str, int],
    required_tables: set[str],
    *,
    corpus_supported_tables: set[str] | None = None,
) -> None:
    check_tables = required_tables
    if corpus_supported_tables is not None:
        check_tables = {t for t in required_tables if t in corpus_supported_tables}
    missing = [t for t in check_tables if rows_by_table.get(t, 0) == 0]
    if missing:
        raise RuntimeError(
            f"Required tables have zero extracted rows: {missing}. "
            f"Rows by table: {rows_by_table}"
        )


def rows_by_table(db: dict) -> dict[str, int]:
    return {table: len(df) for table, df in db.items()}


def filter_queries_by_category(queries: list[dict], categories: list[str]) -> list[dict]:
    normalized = {c.lower() for c in categories}
    kept = [q for q in queries if (q.get("category") or "").lower() in normalized]
    if not kept:
        raise RuntimeError(f"No queries found for categories {categories}")
    return kept


def prepare_aggregation_slice_instance(
    instance: Instance,
    *,
    slice_name: str,
    num_docs: int,
    num_eval_queries: int,
    seed: int,
    query_table_filter: set[str] | None = None,
) -> tuple[Instance, set[str]]:
    """Build an aligned instance for an aggregation workload slice."""
    schema = instance.schema
    table_filter = query_table_filter or {"player"}
    corpus_types = corpus_entity_types(instance.corpus)

    slice_queries = queries_for_aggregation_slice(instance.queries, slice_name)
    slice_queries = filter_queries_for_tables(slice_queries, schema, table_filter)
    slice_queries = filter_queries_by_corpus_coverage(slice_queries, schema, corpus_types)
    if not slice_queries:
        raise RuntimeError(
            f"Slice '{slice_name}' has no corpus-feasible queries. "
            f"Corpus entity types: {sorted(corpus_types)}. "
            "Queries referencing tables without text docs (e.g. owner) are excluded."
        )

    eval_queries = slice_queries[:num_eval_queries]
    required_tables = tables_referenced_by_queries(eval_queries, schema)
    missing_corpus = required_tables - corpus_types
    if missing_corpus:
        raise RuntimeError(
            f"Eval queries reference tables without corpus coverage: {sorted(missing_corpus)}"
        )

    sampled_corpus = sample_corpus_stratified(
        instance.corpus,
        required_tables,
        num_docs,
        seed,
    )

    trimmed = replace(
        instance,
        corpus=sampled_corpus,
        queries=eval_queries,
        metadata={
            **(instance.metadata or {}),
            "aggregation_slice": slice_name,
            "num_docs": len(sampled_corpus),
            "num_eval_queries": len(eval_queries),
            "num_queries_in_slice": len(slice_queries),
            "required_tables": sorted(required_tables),
            "corpus_entity_types": sorted(corpus_types),
        },
    )
    return trimmed, required_tables


def prepare_slice_instance(
    instance: Instance,
    *,
    categories: list[str],
    num_docs: int,
    num_eval_queries: int,
    seed: int,
    query_table_filter: set[str] | None = None,
) -> tuple[Instance, set[str]]:
    """Build an aligned instance for a workload slice (e.g. Agg, Select, Filter)."""
    schema = instance.schema
    table_filter = query_table_filter or {"player"}

    slice_queries = filter_queries_by_category(instance.queries, categories)
    slice_queries = filter_queries_for_tables(slice_queries, schema, table_filter)
    eval_queries = slice_queries[:num_eval_queries]
    required_tables = tables_referenced_by_queries(eval_queries, schema)

    aligned_corpus = filter_docs_for_tables(instance.corpus, required_tables)
    rng = random.Random(seed)
    rng.shuffle(aligned_corpus)
    sampled_corpus = aligned_corpus[: min(num_docs, len(aligned_corpus))]

    trimmed = replace(
        instance,
        corpus=sampled_corpus,
        queries=eval_queries,
        metadata={
            **(instance.metadata or {}),
            "slice_categories": categories,
            "num_docs": len(sampled_corpus),
            "num_eval_queries": len(eval_queries),
            "required_tables": sorted(required_tables),
        },
    )
    return trimmed, required_tables


def prepare_aligned_instance(
    instance: Instance,
    *,
    num_docs: int,
    num_eval_queries: int,
    seed: int,
    query_table_filter: set[str] | None = None,
) -> tuple[Instance, set[str]]:
    """Align corpus docs and eval queries to the same required tables."""
    schema = instance.schema
    table_filter = query_table_filter or {"player"}

    player_queries = filter_queries_for_tables(instance.queries, schema, table_filter)
    eval_queries = player_queries[:num_eval_queries]
    required_tables = tables_referenced_by_queries(eval_queries, schema)

    aligned_corpus = filter_docs_for_tables(instance.corpus, required_tables)
    rng = random.Random(seed)
    rng.shuffle(aligned_corpus)
    sampled_corpus = aligned_corpus[: min(num_docs, len(aligned_corpus))]

    trimmed = replace(
        instance,
        corpus=sampled_corpus,
        queries=eval_queries,
        metadata={
            **(instance.metadata or {}),
            "num_docs": len(sampled_corpus),
            "num_eval_queries": len(eval_queries),
            "required_tables": sorted(required_tables),
        },
    )
    return trimmed, required_tables
