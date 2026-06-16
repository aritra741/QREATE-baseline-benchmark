from __future__ import annotations

import random
import re
from dataclasses import replace

import pandas as pd

from data.dataset_registry import (
    default_table_filter,
    normalize_dataset_name,
    schema_tables_from_corpus,
    table_to_corpus_folder,
)
from data.aggregation_slices import (
    AGGREGATION_SLICE_ORDER,
    UNIFIED_WORKLOAD_NAME,
    classify_aggregation_slice,
    queries_for_aggregation_slice,
    unified_aggregation_queries,
)
from data.instance_builder import Instance
from data.workload_selection import dedupe_queries, select_balanced_queries, stable_slice_seed
from pipeline.schema import Schema

_SPLIT_ALLOWED = frozenset({"train", "dev", "test"})

_PLAYER_ID_RE = re.compile(r"player[_/](\d+)", re.IGNORECASE)


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


def filter_docs_for_tables(
    corpus: list[dict],
    required_tables: set[str],
    *,
    dataset: str = "Player",
) -> list[dict]:
    """
    Keep documents whose doc_id prefix / table_hint matches one of the required tables.
    """
    if not required_tables:
        raise ValueError("required_tables must not be empty")

    dataset_key = normalize_dataset_name(dataset)
    normalized = {t.lower() for t in required_tables}
    corpus_prefixes = {table_to_corpus_folder(dataset_key, t) for t in normalized} | normalized
    matched: list[dict] = []

    for doc in corpus:
        doc_id = doc.get("doc_id", "")
        prefix = doc_id.split("/")[0].lower() if "/" in doc_id else doc_id.split("_")[0].lower()
        hint = str(doc.get("metadata", {}).get("table_hint", "")).lower()
        folder = str(doc.get("metadata", {}).get("corpus_folder", "")).lower()
        if prefix in corpus_prefixes or hint in normalized or folder in corpus_prefixes:
            matched.append(doc)

    if not matched:
        raise RuntimeError(
            f"No corpus documents match required tables {sorted(required_tables)}. "
            "Check doc_id prefixes and table_hint metadata."
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


def player_ids_from_corpus(corpus: list[dict]) -> set[int]:
    """Infer ground-truth player.id values from sampled corpus doc_ids (e.g. player/player_16)."""
    ids: set[int] = set()
    for doc in corpus:
        doc_id = doc.get("doc_id", "")
        match = _PLAYER_ID_RE.search(doc_id)
        if match:
            ids.add(int(match.group(1)))
            continue
        parts = doc_id.replace("/", "_").split("_")
        if parts and parts[-1].isdigit():
            ids.add(int(parts[-1]))
    return ids


def restrict_ground_truth_tables(
    gt: dict[str, pd.DataFrame],
    corpus: list[dict],
    *,
    restrict_related: bool = True,
) -> dict[str, pd.DataFrame]:
    """Restrict GT to rows for entities present in the sampled corpus."""
    player_ids = player_ids_from_corpus(corpus)
    if not player_ids:
        return {k: v.copy() for k, v in gt.items()}

    restricted: dict[str, pd.DataFrame] = {k: v.copy() for k, v in gt.items()}
    if "player" in restricted and "id" in restricted["player"].columns:
        restricted["player"] = restricted["player"][
            restricted["player"]["id"].isin(player_ids)
        ].copy()

    if restrict_related and "player" in restricted and not restricted["player"].empty:
        pdf = restricted["player"]
        if "team" in restricted and "team" in pdf.columns:
            team_col = "team_name" if "team_name" in restricted["team"].columns else restricted["team"].columns[0]
            teams = {str(v).strip() for v in pdf["team"].dropna().unique()}
            tdf = restricted["team"]
            if team_col in tdf.columns:
                restricted["team"] = tdf[tdf[team_col].astype(str).str.strip().isin(teams)].copy()

    return restricted


def doc_ids_from_probe_extraction(extraction) -> list[str]:
    """Document IDs that were sent through the probe extraction stage."""
    if extraction is None:
        return []
    return [str(sig["doc_id"]) for sig in extraction.per_doc_signals if sig.get("doc_id")]


def corpus_for_probe_extraction(
    extraction,
    *,
    cached_corpus: list[dict] | None = None,
    full_corpus: list[dict] | None = None,
) -> list[dict]:
    """
    Rebuild the probe corpus from extraction doc IDs.

    Eval must use exactly these documents — never an independently resampled slice.
    """
    doc_ids = doc_ids_from_probe_extraction(extraction)
    if not doc_ids:
        raise RuntimeError("Probe extraction has no per_doc_signals; cannot lock eval corpus.")

    by_id: dict[str, dict] = {}
    for source in (cached_corpus or []), (full_corpus or []):
        for doc in source:
            by_id[doc["doc_id"]] = doc

    missing = [doc_id for doc_id in doc_ids if doc_id not in by_id]
    if missing:
        raise RuntimeError(
            f"Probe extraction references {len(missing)} doc(s) missing from corpus lookup: "
            f"{missing[:5]}{'...' if len(missing) > 5 else ''}"
        )
    return [by_id[doc_id] for doc_id in doc_ids]


def corpus_alignment_metadata(corpus: list[dict], *, restrict_gt: bool = True) -> dict:
    """Metadata fields to attach when corpus is a pilot sample."""
    pids = sorted(player_ids_from_corpus(corpus))
    return {
        "sampled_player_ids": pids,
        "restrict_gt_to_corpus": restrict_gt and bool(pids),
    }


def corpus_entity_types(corpus: list[dict], *, dataset: str = "Player") -> set[str]:
    """Schema table names present in the text corpus."""
    return schema_tables_from_corpus(corpus, dataset=dataset)


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
    *,
    dataset: str = "Player",
) -> list[dict]:
    """Sample docs evenly across required entity types present in the corpus."""
    rng = random.Random(seed)
    if not required_tables:
        raise ValueError("required_tables must not be empty")

    per_table = max(1, num_docs // len(required_tables))
    sampled: list[dict] = []
    seen_ids: set[str] = set()

    for table in sorted(required_tables):
        table_docs = filter_docs_for_tables(corpus, {table}, dataset=dataset)
        rng.shuffle(table_docs)
        for doc in table_docs[:per_table]:
            if doc["doc_id"] not in seen_ids:
                sampled.append(doc)
                seen_ids.add(doc["doc_id"])

    if len(sampled) < num_docs:
        pool = filter_docs_for_tables(corpus, required_tables, dataset=dataset)
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
    queries_per_slice: int | None = None,
    workload_split: str | None = None,
    dataset: str | None = None,
) -> tuple[Instance, set[str]]:
    """Build an aligned instance for an aggregation workload slice."""
    schema = instance.schema
    dataset_key = normalize_dataset_name(dataset or instance.dataset_name)
    table_filter = query_table_filter or default_table_filter(dataset_key)
    corpus_types = corpus_entity_types(instance.corpus, dataset=dataset_key)

    if workload_split:
        if workload_split not in _SPLIT_ALLOWED:
            raise ValueError(f"workload_split must be one of {sorted(_SPLIT_ALLOWED)}")
        from data.workload_splits import load_split_queries

        slice_queries = [
            q
            for q in load_split_queries(workload_split, results_dir=None, dataset=dataset_key)
            if classify_aggregation_slice(q.get("sql_query", "")) == slice_name
        ]
    else:
        slice_queries = queries_for_aggregation_slice(instance.queries, slice_name)
    slice_queries = filter_queries_for_tables(slice_queries, schema, table_filter)
    slice_queries = filter_queries_by_corpus_coverage(slice_queries, schema, corpus_types)
    if not slice_queries:
        raise RuntimeError(
            f"Slice '{slice_name}' has no corpus-feasible queries. "
            f"Corpus entity types: {sorted(corpus_types)}. "
            "Queries referencing tables without text docs (e.g. owner) are excluded."
        )

    slice_queries, _ = dedupe_queries(slice_queries)
    if workload_split:
        eval_queries = list(slice_queries)
    else:
        cap = queries_per_slice if queries_per_slice is not None else num_eval_queries
        cap = min(cap, num_eval_queries)
        target = min(len(slice_queries), cap)
        eval_queries = select_balanced_queries(
            slice_queries,
            slice_name=slice_name,
            target_count=target,
            seed=stable_slice_seed(seed, slice_name),
        )
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
        dataset=dataset_key,
    )

    trimmed = replace(
        instance,
        corpus=sampled_corpus,
        queries=eval_queries,
        metadata={
            **(instance.metadata or {}),
            **corpus_alignment_metadata(sampled_corpus),
            "aggregation_slice": slice_name,
            "dataset": dataset_key,
            "num_docs": len(sampled_corpus),
            "num_eval_queries": len(eval_queries),
            "num_queries_in_slice": len(slice_queries),
            "required_tables": sorted(required_tables),
            "corpus_entity_types": sorted(corpus_types),
        },
    )
    return trimmed, required_tables


def prepare_unified_aggregation_instance(
    instance: Instance,
    *,
    num_docs: int,
    num_eval_queries: int,
    seed: int,
    query_table_filter: set[str] | None = None,
    slice_names: list[str] | None = None,
    queries_per_slice: int | None = None,
    dataset: str | None = None,
) -> tuple[Instance, set[str]]:
    """Build one instance whose workload contains all aggregation-slice queries."""
    schema = instance.schema
    dataset_key = normalize_dataset_name(dataset or instance.dataset_name)
    table_filter = query_table_filter or default_table_filter(dataset_key)
    corpus_types = corpus_entity_types(instance.corpus, dataset=dataset_key)
    order = slice_names or list(AGGREGATION_SLICE_ORDER)

    eval_queries: list[dict] = []
    pool_total = 0
    for slice_name in order:
        slice_pool = queries_for_aggregation_slice(instance.queries, slice_name)
        slice_pool = filter_queries_for_tables(slice_pool, schema, table_filter)
        slice_pool = filter_queries_by_corpus_coverage(slice_pool, schema, corpus_types)
        slice_pool, _ = dedupe_queries(slice_pool)
        pool_total += len(slice_pool)
        cap = queries_per_slice if queries_per_slice is not None else num_eval_queries
        cap = min(cap, num_eval_queries)
        target = min(len(slice_pool), cap)
        if target > 0:
            eval_queries.extend(
                select_balanced_queries(
                    slice_pool,
                    slice_name=slice_name,
                    target_count=target,
                    seed=stable_slice_seed(seed, slice_name),
                )
            )

    slice_queries = eval_queries
    if not slice_queries:
        raise RuntimeError(
            "Unified aggregation workload has no corpus-feasible queries. "
            f"Corpus entity types: {sorted(corpus_types)}."
        )
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
        dataset=dataset_key,
    )

    trimmed = replace(
        instance,
        corpus=sampled_corpus,
        queries=eval_queries,
        metadata={
            **(instance.metadata or {}),
            **corpus_alignment_metadata(sampled_corpus),
            "aggregation_slice": UNIFIED_WORKLOAD_NAME,
            "workload_mode": "unified",
            "num_docs": len(sampled_corpus),
            "num_eval_queries": len(eval_queries),
            "num_queries_in_slice": len(slice_queries),
            "required_tables": sorted(required_tables),
            "corpus_entity_types": sorted(corpus_types),
            "included_slices": slice_names or list(AGGREGATION_SLICE_ORDER),
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
    dataset: str | None = None,
) -> tuple[Instance, set[str]]:
    """Build an aligned instance for a workload slice (e.g. Agg, Select, Filter)."""
    schema = instance.schema
    dataset_key = normalize_dataset_name(dataset or instance.dataset_name)
    table_filter = query_table_filter or default_table_filter(dataset_key)

    slice_queries = filter_queries_by_category(instance.queries, categories)
    slice_queries = filter_queries_for_tables(slice_queries, schema, table_filter)
    eval_queries = slice_queries[:num_eval_queries]
    required_tables = tables_referenced_by_queries(eval_queries, schema)

    aligned_corpus = filter_docs_for_tables(instance.corpus, required_tables, dataset=dataset_key)
    rng = random.Random(seed)
    rng.shuffle(aligned_corpus)
    sampled_corpus = aligned_corpus[: min(num_docs, len(aligned_corpus))]

    trimmed = replace(
        instance,
        corpus=sampled_corpus,
        queries=eval_queries,
        metadata={
            **(instance.metadata or {}),
            **corpus_alignment_metadata(sampled_corpus),
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
    dataset: str | None = None,
) -> tuple[Instance, set[str]]:
    """Align corpus docs and eval queries to the same required tables."""
    schema = instance.schema
    dataset_key = normalize_dataset_name(dataset or instance.dataset_name)
    table_filter = query_table_filter or default_table_filter(dataset_key)

    aligned_queries = filter_queries_for_tables(instance.queries, schema, table_filter)
    eval_queries = aligned_queries[:num_eval_queries]
    required_tables = tables_referenced_by_queries(eval_queries, schema)

    aligned_corpus = filter_docs_for_tables(instance.corpus, required_tables, dataset=dataset_key)
    rng = random.Random(seed)
    rng.shuffle(aligned_corpus)
    sampled_corpus = aligned_corpus[: min(num_docs, len(aligned_corpus))]

    trimmed = replace(
        instance,
        corpus=sampled_corpus,
        queries=eval_queries,
        metadata={
            **(instance.metadata or {}),
            **corpus_alignment_metadata(sampled_corpus),
            "num_docs": len(sampled_corpus),
            "num_eval_queries": len(eval_queries),
            "required_tables": sorted(required_tables),
            "corpus_entity_types": sorted(
                corpus_entity_types(sampled_corpus, dataset=dataset_key)
            ),
        },
    )
    return trimmed, required_tables
