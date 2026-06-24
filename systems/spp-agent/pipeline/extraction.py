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


def _workload_aware_enabled(cfg: dict) -> bool:
    extraction_cfg = cfg.get("extraction", {})
    if "workload_aware" in extraction_cfg:
        return bool(extraction_cfg["workload_aware"])
    return True


def _extraction_max_workers(cfg: dict) -> int:
    return max(1, int(cfg.get("extraction", {}).get("max_workers", 1)))


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
        task_context = build_extraction_task_context(queries, resolved_demand)
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

    tuples_by_table: dict[str, list[dict]] = {t: [] for t in schema.tables}
    per_doc_signals: list[dict] = []
    total_cost = 0.0
    max_workers = min(_extraction_max_workers(cfg), max(1, len(docs)))

    def _run_one(idx_doc: tuple[int, dict]) -> tuple[int, dict[str, list[dict]], dict[str, Any], float]:
        idx, doc = idx_doc
        return _extract_one_document(
            doc,
            idx=idx,
            n_docs=len(docs),
            schema=schema,
            model_name=model_name,
            base_url=base_url,
            temperature=temperature,
            llm_cfg=llm_cfg,
            task_context=task_context,
            verify_model=False,
        )

    indexed_docs = list(enumerate(docs, start=1))
    if max_workers == 1:
        results = [_run_one(item) for item in indexed_docs]
    else:
        logger.info("Parallel extraction with %d workers", max_workers)
        results: list[tuple[int, dict[str, list[dict]], dict[str, Any], float]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_run_one, item): item[0] for item in indexed_docs}
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda r: r[0])

    for _idx, doc_tuples, signal, cost in results:
        total_cost += cost
        per_doc_signals.append(signal)
        for table_name, rows in doc_tuples.items():
            if table_name in tuples_by_table:
                tuples_by_table[table_name].extend(rows)

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
