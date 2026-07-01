from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from llm.client import chat_completion, ensure_model_available, estimate_tokens
from pipeline.extraction_context import (
    align_tuples_to_schema,
    bucket_extraction_for_doc,
    build_extraction_task_context,
    build_workload_aware_extraction_prompt,
    gold_schema_leaks_in_prompt,
    resolve_demand_profile,
    entity_hint_from_doc,
)
from pipeline.schema import Schema
from utils.config import load_config
from utils.logging import setup_logger

logger = setup_logger("spp.extraction")


@dataclass
class ExtractionResult:
    tuples_by_table: dict[str, list[dict]]
    token_cost: float
    per_doc_signals: list[dict] = field(default_factory=list)
    demand_profile: dict | None = None


def _build_legacy_schema_prompt(doc: dict, schema: Schema) -> str:
    entity = entity_hint_from_doc(doc)
    table_names = (
        [entity]
        if entity and entity in schema.tables
        else sorted(schema.tables)
    )
    table_specs = []
    for table in table_names:
        cols = schema.tables[table]
        col_types = schema.column_types.get(table, {})
        col_desc = ", ".join(
            f"{c} ({col_types.get(c, 'str')})" for c in cols if c.lower() not in {"id", "unnamed: 0"}
        )
        table_specs.append(f'  "{table}": [{col_desc}]')

    return (
        "Extract structured tuples from the document below according to the schema.\n"
        "Return ONLY valid JSON with this exact structure:\n"
        '{\n  "tables": {\n'
        + "\n".join(table_specs)
        + '\n  }\n}\n'
        "Each table value must be a list of objects with column names as keys.\n"
        "Do not invent values not supported by the text. Use null for missing fields.\n\n"
        f"Schema description: {schema.description}\n\n"
        f"Document ID: {doc['doc_id']}\n"
        f"Document:\n{doc['text']}\n"
    )


def _parse_extraction_json(raw: str) -> tuple[dict[str, list[dict]] | None, bool]:
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None, False

    if not isinstance(payload, dict):
        return None, False
    tables = payload.get("tables", payload)
    if not isinstance(tables, dict):
        return None, False

    parsed: dict[str, list[dict]] = {}
    for table_name, rows in tables.items():
        if isinstance(rows, list):
            parsed[table_name] = [r for r in rows if isinstance(r, dict)]
        else:
            parsed[table_name] = []
    return parsed, True


def _workload_aware_enabled(cfg: dict) -> bool:
    extraction_cfg = cfg.get("extraction", {})
    if "workload_aware" in extraction_cfg:
        return bool(extraction_cfg["workload_aware"])
    return True


def _extraction_max_workers(cfg: dict) -> int:
    return max(1, int(cfg.get("extraction", {}).get("max_workers", 1)))


def _chunk_size(cfg: dict, dataset_name: str | None = None) -> int:
    """Return chunk size. Dataset-level config overrides global extraction.chunk_size.
    0 means no chunking (default).
    """
    if dataset_name:
        ds_cfg = cfg.get("datasets", {}).get(dataset_name, {})
        if isinstance(ds_cfg, dict) and "extraction_chunk_size" in ds_cfg:
            return max(0, int(ds_cfg["extraction_chunk_size"]))
    return max(0, int(cfg.get("extraction", {}).get("chunk_size", 0)))


def _max_doc_chars(cfg: dict, dataset_name: str | None = None) -> int:
    """Return maximum characters to use per document before chunking.
    0 means no cap (use full document). Dataset-level setting wins.
    """
    if dataset_name:
        ds_cfg = cfg.get("datasets", {}).get(dataset_name, {})
        if isinstance(ds_cfg, dict) and "extraction_max_doc_chars" in ds_cfg:
            return max(0, int(ds_cfg["extraction_max_doc_chars"]))
    return max(0, int(cfg.get("extraction", {}).get("max_doc_chars", 0)))


def _parse_doc_anchor(text: str) -> dict[str, str]:
    """Extract entity-level identifiers from a document's structured header.

    Handles both key-value headers (e.g. Finance: 'Company Name: Apple Inc.')
    and falls back to an empty dict when no recognisable header is found.
    """
    anchor: dict[str, str] = {}
    for line in text[:1500].splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower().replace(" ", "_")
        val = val.strip()
        if not val:
            continue
        # Map recognised header keys to canonical anchor field names
        _MAP = {
            "company_name": "company_name",
            "company": "company_name",
            "name": "company_name",
            "ticker": "ticker",
            "symbol": "ticker",
            "form_type": "form_type",
            "filing_date": "filing_date",
            "report_date": "report_date",
            "fiscal_year": "fiscal_year",
            "document_id": "document_id",
        }
        canonical = _MAP.get(key)
        if canonical and canonical not in anchor:
            anchor[canonical] = val
    return anchor


def _build_anchor_header(anchor: dict[str, str]) -> str:
    """Format anchor dict as a compact context header injected into later chunks."""
    if not anchor:
        return ""
    parts = ", ".join(f"{k.replace('_', ' ').title()}={v}" for k, v in anchor.items())
    return f"[DOCUMENT CONTEXT: {parts}]\n\n"


def _split_into_chunks(doc: dict, chunk_size: int) -> list[dict]:
    """Split a document into fixed-size text chunks preserving doc metadata."""
    text = doc.get("text", "")
    if not text or chunk_size <= 0 or len(text) <= chunk_size:
        return [doc]
    chunks = []
    for i, start in enumerate(range(0, len(text), chunk_size)):
        chunk_text = text[start : start + chunk_size]
        chunk_doc = {
            **doc,
            "doc_id": f"{doc['doc_id']}_chunk{i}",
            "text": chunk_text,
            "_chunk_index": i,
            "_parent_doc_id": doc["doc_id"],
        }
        chunks.append(chunk_doc)
    return chunks


def _merge_chunk_tuples(
    chunks_results: list[dict[str, list[dict]]],
) -> dict[str, list[dict]]:
    """Merge extracted rows from all chunks of one document."""
    merged: dict[str, list[dict]] = {}
    for chunk_rows in chunks_results:
        for table, rows in chunk_rows.items():
            merged.setdefault(table, []).extend(rows)
    return merged


def _coalesce_rows_by_doc(tuples_by_table: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """After chunked extraction, collapse all rows from the same parent document
    into a single row per document by taking the first non-null value per column.

    Rows that have a '_source_doc_id' containing '_chunk' are grouped by their
    parent doc id. Without that marker, rows are returned unchanged.
    """
    result: dict[str, list[dict]] = {}
    for table, rows in tuples_by_table.items():
        # Separate chunked rows from normal rows
        chunked: dict[str, list[dict]] = {}
        normal: list[dict] = []
        for row in rows:
            src = str(row.get("_source_doc_id", ""))
            if "_chunk" in src:
                parent = src.rsplit("_chunk", 1)[0]
                chunked.setdefault(parent, []).append(row)
            else:
                normal.append(row)

        coalesced: list[dict] = list(normal)
        for parent_id, chunk_rows in chunked.items():
            # Collect all column keys across all chunks for this doc
            all_keys = {k for r in chunk_rows for k in r if k != "_source_doc_id"}
            merged_row: dict = {}
            for col in all_keys:
                for r in chunk_rows:
                    v = r.get(col)
                    if v is not None and v != "" and str(v).lower() != "null":
                        merged_row[col] = v
                        break
            merged_row["_source_doc_id"] = parent_id
            coalesced.append(merged_row)

        result[table] = coalesced
    return result


def _extract_one_document(
    doc: dict,
    *,
    idx: int,
    n_docs: int,
    schema: Schema,
    model_name: str,
    base_url: str,
    temperature: float,
    llm_cfg: dict[str, Any],
    task_context: dict[str, Any] | None,
    verify_model: bool,
) -> tuple[int, dict[str, list[dict]], dict[str, Any], float]:
    """Extract a single document. Returns (idx, tuples_by_table, signal, token_cost)."""
    doc_id = doc["doc_id"]
    text_len = len(doc.get("text", ""))
    logger.info(
        "Doc %d/%d id=%s chars=%d table_hint=%s",
        idx,
        n_docs,
        doc_id,
        text_len,
        doc.get("metadata", {}).get("table_hint"),
    )

    if task_context is not None:
        prompt = build_workload_aware_extraction_prompt(doc, task_context=task_context)
        leaks = gold_schema_leaks_in_prompt(prompt, schema)
        if leaks:
            raise RuntimeError(
                f"Gold schema leaked into workload-aware extraction prompt: {leaks}"
            )
    else:
        prompt = _build_legacy_schema_prompt(doc, schema)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a precise information extraction assistant for analytics workloads. "
                "Output strict JSON only."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    refusal_markers = ("cannot", "unable", "sorry", "i can't")
    raw_output = ""
    json_parse_success = False
    extraction_refusal = False
    empty_output = True
    token_cost = 0.0
    doc_tuples: dict[str, list[dict]] = {t: [] for t in schema.tables}

    try:
        logger.debug("Calling LLM for doc=%s prompt_chars=%d", doc_id, len(prompt))
        raw_output, token_cost = chat_completion(
            model_name,
            messages,
            base_url=base_url,
            temperature=temperature,
            llm_cfg=llm_cfg,
            verify_model=verify_model,
        )
        logger.info(
            "Doc %s LLM returned tokens=%.0f response_chars=%d",
            doc_id,
            token_cost,
            len(raw_output),
        )
    except Exception as exc:
        raw_output = str(exc)
        logger.error("Doc %s extraction failed: %s", doc_id, exc)
        return (
            idx,
            doc_tuples,
            {
                "doc_id": doc_id,
                "tuple_count": 0,
                "json_parse_success": False,
                "extraction_refusal": False,
                "empty_output": True,
                "raw_output": raw_output,
            },
            0.0,
        )

    parsed, json_parse_success = _parse_extraction_json(raw_output)
    lower = raw_output.lower()
    extraction_refusal = any(m in lower for m in refusal_markers) and not json_parse_success

    tuple_count = 0
    if parsed:
        parsed = bucket_extraction_for_doc(parsed, schema, doc)
        for table_name, rows in parsed.items():
            if table_name in doc_tuples:
                for row in rows:
                    row_with_meta = dict(row)
                    row_with_meta["_source_doc_id"] = doc_id
                    doc_tuples[table_name].append(row_with_meta)
                    tuple_count += 1
        empty_output = tuple_count == 0
    else:
        empty_output = True

    logger.info(
        "Doc %s parsed json_ok=%s tuples=%d refusal=%s empty=%s",
        doc_id,
        json_parse_success,
        tuple_count,
        extraction_refusal,
        empty_output,
    )
    if not json_parse_success:
        logger.debug("Doc %s raw_output preview: %s", doc_id, raw_output[:300])

    return (
        idx,
        doc_tuples,
        {
            "doc_id": doc_id,
            "tuple_count": tuple_count,
            "json_parse_success": json_parse_success,
            "extraction_refusal": extraction_refusal,
            "empty_output": empty_output,
            "raw_output": raw_output,
        },
        token_cost,
    )


def extract_documents(
    docs: list[dict],
    schema: Schema,
    model_name: str,
    *,
    queries: list[dict] | None = None,
    demand_profile: dict | None = None,
    schema_value_hints: dict[str, list[str]] | None = None,
    dataset_name: str | None = None,
) -> ExtractionResult:
    cfg = load_config()
    llm_cfg = cfg["llm"]
    base_url = llm_cfg.get("base_url", "http://localhost:8000/v1")
    temperature = float(llm_cfg.get("temperature", 0.0))
    workload_aware = _workload_aware_enabled(cfg)

    if workload_aware and not queries:
        raise ValueError(
            "workload_aware extraction requires queries= (SQL workload). "
            "Set extraction.workload_aware: false to use the legacy schema prompt."
        )

    resolved_demand = None
    task_context = None
    if workload_aware:
        resolved_demand = resolve_demand_profile(queries, demand_profile=demand_profile)
        task_context = build_extraction_task_context(
            queries, resolved_demand, schema_value_hints=schema_value_hints
        )
        logger.info(
            "Workload-aware extraction: %d demand columns has_join=%s has_temporal=%s",
            len(resolved_demand.get("columns", [])),
            resolved_demand.get("has_join"),
            resolved_demand.get("has_temporal"),
        )

    logger.info(
        "Extracting %d docs with model=%s provider=%s base_url=%s mode=%s workers=%d",
        len(docs),
        model_name,
        llm_cfg.get("provider"),
        base_url,
        "workload_aware" if task_context else "legacy_schema",
        _extraction_max_workers(cfg),
    )

    ensure_model_available(model_name, base_url, llm_cfg=llm_cfg)

    chunk_size = _chunk_size(cfg, dataset_name)
    max_chars = _max_doc_chars(cfg, dataset_name)
    if chunk_size > 0:
        logger.info(
            "Chunked extraction: chunk_size=%d max_doc_chars=%s",
            chunk_size,
            max_chars if max_chars > 0 else "unlimited",
        )

    # Expand each document into chunks (or keep as-is when chunk_size=0).
    # Each entry: (global_idx, chunk_doc, parent_doc_id)
    all_chunks: list[tuple[int, dict, str]] = []
    for doc in docs:
        parent_id = str(doc["doc_id"])
        if chunk_size > 0:
            # Optionally cap document length before chunking to limit LLM calls.
            if max_chars > 0 and len(doc.get("text", "")) > max_chars:
                doc = {**doc, "text": doc["text"][:max_chars]}
            chunks = _split_into_chunks(doc, chunk_size)
            anchor = _parse_doc_anchor(doc.get("text", ""))
            if anchor:
                anchor_header = _build_anchor_header(anchor)
                for chunk in chunks:
                    if chunk.get("_chunk_index", 0) > 0:
                        chunk = {**chunk, "text": anchor_header + chunk["text"]}
                    all_chunks.append((len(all_chunks) + 1, chunk, parent_id))
                logger.debug(
                    "Doc %s → %d chunks, anchor=%s", parent_id, len(chunks), list(anchor.keys())
                )
            else:
                for chunk in chunks:
                    all_chunks.append((len(all_chunks) + 1, chunk, parent_id))
        else:
            all_chunks.append((len(all_chunks) + 1, doc, parent_id))

    tuples_by_table: dict[str, list[dict]] = {t: [] for t in schema.tables}
    per_doc_signals: list[dict] = []
    total_cost = 0.0
    max_workers = min(_extraction_max_workers(cfg), max(1, len(all_chunks)))
    n_total = len(all_chunks)

    def _run_one(item: tuple[int, dict, str]) -> tuple[int, dict[str, list[dict]], dict[str, Any], float, str]:
        idx, chunk_doc, parent_id = item
        result_idx, doc_tuples, signal, cost = _extract_one_document(
            chunk_doc,
            idx=idx,
            n_docs=n_total,
            schema=schema,
            model_name=model_name,
            base_url=base_url,
            temperature=temperature,
            llm_cfg=llm_cfg,
            task_context=task_context,
            verify_model=False,
        )
        return result_idx, doc_tuples, signal, cost, parent_id

    if max_workers == 1:
        results = [_run_one(item) for item in all_chunks]
    else:
        logger.info("Parallel extraction with %d workers over %d chunks", max_workers, n_total)
        results: list[tuple[int, dict[str, list[dict]], dict[str, Any], float, str]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_run_one, item): item[0] for item in all_chunks}
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda r: r[0])

    for _idx, doc_tuples, signal, cost, _parent_id in results:
        total_cost += cost
        per_doc_signals.append(signal)
        for table_name, rows in doc_tuples.items():
            if table_name in tuples_by_table:
                tuples_by_table[table_name].extend(rows)

    # When chunking was used, collapse all chunks of the same document into one row.
    if chunk_size > 0:
        tuples_by_table = _coalesce_rows_by_doc(tuples_by_table)
        logger.info(
            "Coalesced chunked rows: %s",
            {t: len(rows) for t, rows in tuples_by_table.items()},
        )

    table_counts = {t: len(rows) for t, rows in tuples_by_table.items()}
    logger.info(
        "Extraction complete docs=%d total_tokens=%.0f tuples_by_table=%s",
        len(docs),
        total_cost,
        table_counts,
    )

    # Detect total LLM failure (e.g. server down) before returning silent zeros.
    failed_docs = [s for s in per_doc_signals if not s.get("json_parse_success") and s.get("tuple_count", 0) == 0]
    if len(failed_docs) == len(docs) and docs:
        sample_err = (failed_docs[0].get("raw_output", "") or "")[:200]
        conn_refused = "connection refused" in sample_err.lower() or "errno 111" in sample_err.lower()
        hint = (
            " LLM server appears to be unreachable (Connection refused). "
            "Start the vLLM / Ollama server and retry."
            if conn_refused
            else f" Sample error: {sample_err}"
        )
        raise RuntimeError(
            f"Extraction returned 0 tuples across all {len(docs)} documents.{hint}"
        )

    if total_cost == 0.0:
        total_cost = float(sum(estimate_tokens(d["text"]) for d in docs))

    return ExtractionResult(
        tuples_by_table=tuples_by_table,
        token_cost=total_cost,
        per_doc_signals=per_doc_signals,
        demand_profile=resolved_demand,
    )
