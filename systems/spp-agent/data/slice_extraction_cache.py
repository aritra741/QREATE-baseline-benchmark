"""Persist and reload per-slice LLM extraction for benchmark reruns without API calls."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from data.instance_builder import Instance
from data.query_alignment import corpus_alignment_metadata
from optimizer.config_space import parse_config_id
from pipeline.extraction import ExtractionResult, extract_documents
from pipeline.population import apply_population


def slice_extraction_cache_path(results_dir: Path, slice_name: str) -> Path:
    return results_dir / "slice_extraction_cache" / f"{slice_name}.json"


def _extraction_to_payload(extraction: ExtractionResult) -> dict[str, Any]:
    return {
        "tuples_by_table": extraction.tuples_by_table,
        "token_cost": extraction.token_cost,
        "per_doc_signals": extraction.per_doc_signals,
    }


def _extraction_from_payload(payload: dict[str, Any]) -> ExtractionResult:
    return ExtractionResult(
        tuples_by_table=dict(payload.get("tuples_by_table", {})),
        token_cost=float(payload.get("token_cost", 0.0)),
        per_doc_signals=list(payload.get("per_doc_signals", [])),
    )


def save_slice_extraction_cache(
    path: Path,
    *,
    slice_name: str,
    seed: int,
    config_id: str,
    corpus: list[dict],
    extraction: ExtractionResult,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "slice": slice_name,
        "seed": seed,
        "config_id": config_id,
        "corpus": corpus,
        "extraction": _extraction_to_payload(extraction),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_slice_extraction_cache(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "extraction" not in payload or "corpus" not in payload:
        raise ValueError(f"Slice extraction cache at {path} is missing corpus or extraction.")
    return payload


def _materialize_db(extraction: ExtractionResult, config_id: str, schema) -> dict:
    config = parse_config_id(config_id)
    db, _ = apply_population(extraction, config, schema)
    return db


def _instance_from_cached_corpus(
    slice_pool: Instance,
    *,
    slice_name: str,
    queries: list[dict],
    corpus: list[dict],
) -> Instance:
    return replace(
        slice_pool,
        corpus=corpus,
        queries=queries,
        metadata={
            **(slice_pool.metadata or {}),
            **corpus_alignment_metadata(corpus),
            "aggregation_slice": slice_name,
            "extraction_cache_hit": True,
        },
    )


def _try_load_legacy_agg_only_cache(legacy_path: Path) -> dict[str, Any] | None:
    if not legacy_path.exists():
        return None
    from agent.tools import load_agent_cache, lock_toolkit_corpus_to_probe

    toolkit = load_agent_cache(legacy_path)
    lock_toolkit_corpus_to_probe(toolkit)
    extraction = toolkit.probe_data.extraction
    if extraction is None:
        return None
    return {
        "slice": "agg_only",
        "seed": None,
        "config_id": None,
        "corpus": list(toolkit.corpus),
        "extraction": _extraction_to_payload(extraction),
    }


def resolve_slice_extraction(
    *,
    slice_name: str,
    slice_pool: Instance,
    queries: list[dict],
    seed: int,
    config_id: str,
    cache_path: Path,
    legacy_agg_only_cache: Path | None,
    fresh_extraction: bool,
    extraction_model: str,
) -> tuple[Instance, ExtractionResult, dict, str]:
    """
    Load cached extraction or run LLM extraction once, then materialize DB.

    Returns (instance, extraction, db, source) where source is
    ``slice_cache``, ``legacy_agg_only``, or ``fresh_extraction``.
    """
    if not fresh_extraction and cache_path.exists():
        payload = load_slice_extraction_cache(cache_path)
        extraction = _extraction_from_payload(payload["extraction"])
        corpus = list(payload["corpus"])
        instance = _instance_from_cached_corpus(
            slice_pool,
            slice_name=slice_name,
            queries=queries,
            corpus=corpus,
        )
        db = _materialize_db(extraction, config_id, instance.schema)
        return instance, extraction, db, "slice_cache"

    if (
        not fresh_extraction
        and slice_name == "agg_only"
        and legacy_agg_only_cache is not None
    ):
        legacy = _try_load_legacy_agg_only_cache(legacy_agg_only_cache)
        if legacy is not None:
            extraction = _extraction_from_payload(legacy["extraction"])
            corpus = list(legacy["corpus"])
            instance = _instance_from_cached_corpus(
                slice_pool,
                slice_name=slice_name,
                queries=queries,
                corpus=corpus,
            )
            save_slice_extraction_cache(
                cache_path,
                slice_name=slice_name,
                seed=seed,
                config_id=config_id,
                corpus=corpus,
                extraction=extraction,
            )
            db = _materialize_db(extraction, config_id, instance.schema)
            return instance, extraction, db, "legacy_agg_only"

    instance = replace(
        slice_pool,
        queries=queries,
        metadata={
            **(slice_pool.metadata or {}),
            **corpus_alignment_metadata(slice_pool.corpus),
            "aggregation_slice": slice_name,
            "extraction_cache_hit": False,
        },
    )
    extraction = extract_documents(instance.corpus, instance.schema, extraction_model)
    save_slice_extraction_cache(
        cache_path,
        slice_name=slice_name,
        seed=seed,
        config_id=config_id,
        corpus=list(instance.corpus),
        extraction=extraction,
    )
    db = _materialize_db(extraction, config_id, instance.schema)
    return instance, extraction, db, "fresh_extraction"
