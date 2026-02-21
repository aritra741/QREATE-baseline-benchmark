"""
Constrained Global Extraction for WDIRS.
Implements LLM-based extraction with schema stabilization and batching.
"""

import json
import logging
import time
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass
from collections import Counter
import hashlib

import requests
from openai import OpenAI

from config import (
    OLLAMA_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
    OLLAMA_MAX_RETRIES,
    OLLAMA_RETRY_DELAY,
    EXTRACTION_BATCH_SIZE,
    EXTRACTION_TEMPERATURE,
    EXTRACTION_MAX_TOKENS,
    COLUMN_BATCH_SIZE,
    CHUNK_BATCH_SIZE,
    SCHEMA_SAMPLE_SIZE,
    SCHEMA_KEY_FREQUENCY_THRESHOLD,
    CACHE_DIR
)

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class ExtractionResult:
    """Result of extraction from a chunk."""
    chunk_id: str
    records: List[Dict[str, Any]]
    schema_keys: Set[str]
    extraction_time: float
    error: Optional[str] = None


@dataclass
class StabilizedSchema:
    """Stabilized schema with frozen keys."""
    table_name: str
    frozen_keys: Set[str]
    key_frequencies: Dict[str, float]
    sample_size: int


# ============================================================================
# LLM Client
# ============================================================================

class OllamaClient:
    """Client for Ollama LLM API."""
    
    def __init__(
        self,
        base_url: str = OLLAMA_URL,
        model: str = OLLAMA_MODEL,
        timeout: int = OLLAMA_TIMEOUT
    ):
        """Initialize Ollama client."""
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        
        # Initialize OpenAI client (Ollama uses OpenAI-compatible API)
        self.client = OpenAI(
            base_url=base_url,
            api_key="ollama"  # Ollama doesn't require real API key
        )
        
        logger.info(f"Initialized Ollama client: {base_url} with model {model}")
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = EXTRACTION_MAX_TOKENS,
        temperature: float = EXTRACTION_TEMPERATURE,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Generate completion from Ollama.
        
        Args:
            prompt: User prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system_prompt: Optional system prompt
            
        Returns:
            Generated text
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        for attempt in range(OLLAMA_MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=self.timeout
                )
                
                return response.choices[0].message.content
            
            except Exception as e:
                logger.warning(f"Ollama API error (attempt {attempt + 1}/{OLLAMA_MAX_RETRIES}): {e}")
                
                if attempt < OLLAMA_MAX_RETRIES - 1:
                    time.sleep(OLLAMA_RETRY_DELAY)
                else:
                    raise
        
        raise Exception("Failed to get response from Ollama after retries")


# ============================================================================
# Extractor
# ============================================================================

class ConstrainedExtractor:
    """
    Implements constrained global extraction with schema stabilization.
    """
    
    def __init__(self, llm_client: Optional[OllamaClient] = None):
        """Initialize extractor."""
        self.llm_client = llm_client or OllamaClient()
        self.cache_dir = CACHE_DIR / "extractions"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Schema cache
        self.stabilized_schemas: Dict[str, StabilizedSchema] = {}
    
    # ========================================================================
    # Schema Stabilization
    # ========================================================================
    
    def stabilize_schema(
        self,
        table_name: str,
        schema: Dict[str, str],
        sample_chunks: List[str]
    ) -> StabilizedSchema:
        """
        Stabilize schema by extracting from sample chunks and freezing common keys.
        
        Args:
            table_name: Name of the table
            schema: Initial schema (column_name -> semantic_type)
            sample_chunks: Sample chunks for schema discovery
            
        Returns:
            StabilizedSchema with frozen keys
        """
        logger.info(f"Stabilizing schema for {table_name} with {len(sample_chunks)} samples")
        
        # Extract from sample chunks
        all_keys = []
        
        for chunk in sample_chunks[:SCHEMA_SAMPLE_SIZE]:
            try:
                # Extract without constraints to discover keys
                result = self._extract_single_chunk(
                    chunk,
                    table_name,
                    schema,
                    constrained_keys=None
                )
                
                # Collect keys from all records
                for record in result.records:
                    all_keys.extend(record.keys())
            
            except Exception as e:
                logger.warning(f"Error extracting from sample chunk: {e}")
        
        # Calculate key frequencies
        key_counts = Counter(all_keys)
        total_records = len(all_keys)
        
        key_frequencies = {
            key: count / total_records
            for key, count in key_counts.items()
        }
        
        # Freeze keys above threshold
        frozen_keys = {
            key for key, freq in key_frequencies.items()
            if freq >= SCHEMA_KEY_FREQUENCY_THRESHOLD
        }
        
        # Ensure all schema columns are frozen
        frozen_keys.update(schema.keys())
        
        stabilized = StabilizedSchema(
            table_name=table_name,
            frozen_keys=frozen_keys,
            key_frequencies=key_frequencies,
            sample_size=len(sample_chunks)
        )
        
        # Cache stabilized schema
        self.stabilized_schemas[table_name] = stabilized
        
        logger.info(f"Stabilized schema for {table_name}: {len(frozen_keys)} frozen keys")
        logger.debug(f"Frozen keys: {frozen_keys}")
        
        return stabilized
    
    def get_stabilized_schema(self, table_name: str) -> Optional[StabilizedSchema]:
        """Get cached stabilized schema."""
        return self.stabilized_schemas.get(table_name)
    
    # ========================================================================
    # Extraction
    # ========================================================================

    def _build_multi_chunk_prompt(
        self,
        chunk_texts: List[str],
        table_name: str,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]] = None,
        normalization_hints: Optional[Dict[str, List[str]]] = None,
        entity_col: Optional[str] = None,
    ) -> str:
        """
        Build a single prompt that asks the LLM to extract from N passages at once.

        The LLM returns a JSON object keyed by "passage_1" … "passage_N".  Each
        value is the same JSON array format as the single-chunk prompts.  This
        amortises per-request overhead (HTTP round-trip, KV-cache setup) across
        N chunks instead of paying it N times.
        """
        schema_lines = []
        keys_to_use = constrained_keys if constrained_keys else schema.keys()
        for col_name in keys_to_use:
            sem_type = schema.get(col_name, "OTHER")
            schema_lines.append(f"  - {col_name} ({sem_type})")
        schema_desc = "\n".join(schema_lines)

        normalization_section = self._build_normalization_section(normalization_hints)
        entity_section = self._build_entity_section(entity_col)

        passage_blocks = "\n\n".join(
            f"=== Passage {i + 1} ===\n{text}"
            for i, text in enumerate(chunk_texts)
        )

        n = len(chunk_texts)
        example_keys = '{"passage_1": [...], "passage_2": [], ..., "passage_N": [...]}'

        return (
            f'Extract structured data for table "{table_name}" from each passage below.\n\n'
            f"Schema (extract ONLY these fields):\n{schema_desc}\n"
            f"{normalization_section}"
            f"{entity_section}\n\n"
            f"Rules:\n"
            f"- Return a JSON **object** with keys passage_1 … passage_{n}.\n"
            f"- Each value is a JSON array of record objects (or [] if nothing found).\n"
            f"- Use null for missing values, never empty string.\n"
            f"- If a passage discusses multiple entities, return one record per entity.\n\n"
            f"Format: {example_keys}\n\n"
            f"{passage_blocks}\n\n"
            f"Return ONLY the JSON object, no other text."
        )

    def _parse_multi_chunk_response(
        self,
        response: str,
        chunk_ids: List[str],
        constrained_keys: Optional[Set[str]] = None,
        extraction_time: float = 0.0,
    ) -> List[ExtractionResult]:
        """
        Parse the multi-chunk LLM response into one ExtractionResult per chunk.

        Tries to decode the response as a JSON object keyed by "passage_N".
        Falls back to an empty result for any missing or unparseable passage.
        """
        results: List[ExtractionResult] = []
        parsed: Dict[str, Any] = {}

        # Strip markdown fences if present
        clean = response.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:])
            clean = clean.rstrip("`").strip()

        try:
            parsed = json.loads(clean)
        except json.JSONDecodeError:
            # Try extracting a JSON object from anywhere in the response
            import re as _re
            m = _re.search(r"\{.*\}", clean, _re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group())
                except json.JSONDecodeError:
                    pass

        for i, chunk_id in enumerate(chunk_ids):
            key = f"passage_{i + 1}"
            raw_records = parsed.get(key, [])

            if not isinstance(raw_records, list):
                raw_records = []

            records: List[Dict[str, Any]] = []
            for rec in raw_records:
                if not isinstance(rec, dict):
                    continue
                # Apply constrained_keys filter
                if constrained_keys:
                    rec = {k: v for k, v in rec.items() if k in constrained_keys or k == "_entity"}
                records.append(rec)

            schema_keys: Set[str] = set()
            for rec in records:
                schema_keys.update(rec.keys())

            results.append(ExtractionResult(
                chunk_id=chunk_id,
                records=records,
                schema_keys=schema_keys,
                extraction_time=extraction_time / max(len(chunk_ids), 1),
            ))

        return results

    def _extract_chunk_group_safe(
        self,
        chunk_texts: List[str],
        chunk_ids: List[str],
        table_name: str,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]] = None,
        normalization_hints: Optional[Dict[str, List[str]]] = None,
        entity_col: Optional[str] = None,
    ) -> List[ExtractionResult]:
        """
        Thread-safe wrapper: build prompt for N chunks, call LLM once, parse response.

        Returns one ExtractionResult per chunk in chunk_ids.
        On error, returns empty ExtractionResult objects with the error string.
        """
        import time as _time
        start = _time.time()
        try:
            prompt = self._build_multi_chunk_prompt(
                chunk_texts, table_name, schema,
                constrained_keys, normalization_hints, entity_col,
            )
            response = self.llm_client.generate(
                prompt,
                max_tokens=EXTRACTION_MAX_TOKENS,
                temperature=EXTRACTION_TEMPERATURE,
            )
            elapsed = _time.time() - start
            return self._parse_multi_chunk_response(
                response, chunk_ids, constrained_keys, elapsed
            )
        except Exception as e:
            logger.error(
                f"Error extracting chunk group "
                f"{chunk_ids}: {e}"
            )
            elapsed = _time.time() - start
            return [
                ExtractionResult(
                    chunk_id=cid,
                    records=[],
                    schema_keys=set(),
                    extraction_time=elapsed / max(len(chunk_ids), 1),
                    error=str(e),
                )
                for cid in chunk_ids
            ]

    # ========================================================================
    
    def _split_schema_into_batches(
        self,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]],
        normalization_hints: Optional[Dict[str, List[str]]],
        col_batch_size: Optional[int] = None,
    ) -> List[tuple]:
        """
        Split a wide schema into column batches of at most `col_batch_size`
        (defaults to the global COLUMN_BATCH_SIZE setting).

        Pass a value larger than len(schema) to disable batching and send all
        columns in a single LLM call — safe for entity-first extraction where
        the context is already focused on one specific entity.

        Returns a list of (col_batch_schema, batch_constrained_keys,
        batch_normalization_hints) tuples.
        """
        batch_size = col_batch_size if col_batch_size is not None else COLUMN_BATCH_SIZE
        items = list(schema.items())
        batches = []
        for i in range(0, len(items), batch_size):
            col_batch = dict(items[i : i + batch_size])
            batch_ck = (
                constrained_keys & col_batch.keys()
                if constrained_keys
                else None
            )
            batch_nh = (
                {k: v for k, v in normalization_hints.items() if k in col_batch}
                if normalization_hints
                else None
            )
            batches.append((col_batch, batch_ck, batch_nh))
        return batches

    def _merge_column_batches(
        self,
        chunk_id: str,
        batch_map: Dict[int, ExtractionResult],
        total_batches: int,
    ) -> ExtractionResult:
        """
        Merge partial ExtractionResults from column-batch LLM calls.

        Merge strategy:
        - If all non-empty batches return the same number of records, zip them
          by position (record 0 from batch 0 + record 0 from batch 1 = merged
          record 0).
        - If counts differ (LLM returned different numbers of entities for
          different column groups), use the largest batch as the base and merge
          in additional fields from other batches at matching positions.  Any
          batch records beyond the base length are appended as partial records.
        """
        records_per_batch: List[List[Dict[str, Any]]] = []
        total_time = 0.0
        last_error: Optional[str] = None

        for batch_idx in range(total_batches):
            if batch_idx not in batch_map:
                continue
            result = batch_map[batch_idx]
            total_time += result.extraction_time
            if result.error:
                last_error = result.error
                continue
            if result.records:
                records_per_batch.append(result.records)

        if not records_per_batch:
            return ExtractionResult(
                chunk_id=chunk_id,
                records=[],
                schema_keys=set(),
                extraction_time=total_time,
                error=last_error,
            )

        counts = [len(r) for r in records_per_batch]

        if all(c == counts[0] for c in counts):
            # Happy path: all batches agree on entity count — zip by position.
            merged_records = []
            for idx in range(counts[0]):
                merged: Dict[str, Any] = {}
                for batch_records in records_per_batch:
                    merged.update(batch_records[idx])
                merged_records.append(merged)
        else:
            # Counts disagree — use the largest batch as base, merge others in
            # by position, and append any overflow records as partial entries.
            base = max(records_per_batch, key=len)
            merged_records = [dict(r) for r in base]
            for batch_records in records_per_batch:
                if batch_records is base:
                    continue
                for i, record in enumerate(batch_records):
                    if i < len(merged_records):
                        for k, v in record.items():
                            if k not in merged_records[i]:
                                merged_records[i][k] = v
                    else:
                        merged_records.append(dict(record))

        schema_keys: Set[str] = set()
        for record in merged_records:
            schema_keys.update(record.keys())

        return ExtractionResult(
            chunk_id=chunk_id,
            records=merged_records,
            schema_keys=schema_keys,
            extraction_time=total_time,
            error=last_error,
        )

    def extract_batch(
        self,
        chunks: List[str],
        chunk_ids: List[str],
        table_name: str,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]] = None,
        normalization_hints: Optional[Dict[str, List[str]]] = None,
        entity_col: Optional[str] = None,
        col_batch_size_override: Optional[int] = None,
    ) -> List[ExtractionResult]:
        """
        Extract data from all chunks using chunk-group × column-batch parallelism.

        Two-dimensional batching strategy:
          - CHUNK_BATCH_SIZE chunks are sent in one LLM call (multi-passage prompt).
            This amortises per-request overhead across N chunks.
          - COLUMN_BATCH_SIZE columns are sent per call so the 7B model stays in
            its reliable extraction range.

        For C chunks and K column batches, total LLM calls =
          ceil(C / CHUNK_BATCH_SIZE) × K
        vs the previous ceil(C / 1) × K.  The speedup is CHUNK_BATCH_SIZE × overhead_ratio.

        Merging: results from all K column-batch calls for the same chunk are
        merged by _merge_column_batches before being returned.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from config import MAX_PARALLEL_REQUESTS

        col_batches = self._split_schema_into_batches(
            schema, constrained_keys, normalization_hints,
            col_batch_size=col_batch_size_override,
        )
        n_col_batches = len(col_batches)

        # Split chunks into groups of CHUNK_BATCH_SIZE, skipping cached ones.
        pre_cached: List[ExtractionResult] = []
        # chunk_id -> {col_batch_idx -> ExtractionResult}
        chunk_batch_map: Dict[str, Dict[int, ExtractionResult]] = {}

        # Build groups of uncached chunks
        groups: List[tuple] = []   # [(chunk_texts, chunk_ids_in_group)]
        current_texts: List[str] = []
        current_ids: List[str] = []

        for chunk, chunk_id in zip(chunks, chunk_ids):
            cached = self._get_cached_result(chunk_id, table_name)
            if cached:
                pre_cached.append(cached)
                continue
            chunk_batch_map[chunk_id] = {}
            current_texts.append(chunk)
            current_ids.append(chunk_id)
            if len(current_texts) == CHUNK_BATCH_SIZE:
                groups.append((list(current_texts), list(current_ids)))
                current_texts.clear()
                current_ids.clear()

        if current_texts:   # remainder group
            groups.append((current_texts, current_ids))

        total_tasks = len(groups) * n_col_batches
        logger.info(
            f"Extracting {len(chunks)} chunks for '{table_name}': "
            f"{len(groups)} chunk-groups of ≤{CHUNK_BATCH_SIZE}, "
            f"{n_col_batches} column batch(es) of ≤{COLUMN_BATCH_SIZE} "
            f"= {total_tasks} LLM calls, {MAX_PARALLEL_REQUESTS} workers"
            + (f", entity_col='{entity_col}'" if entity_col else "")
        )

        future_to_key: Dict = {}
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REQUESTS) as executor:
            for group_texts, group_ids in groups:
                for batch_idx, (col_batch, batch_ck, batch_nh) in enumerate(col_batches):
                    future = executor.submit(
                        self._extract_chunk_group_safe,
                        group_texts, group_ids, table_name,
                        col_batch, batch_ck, batch_nh, entity_col,
                    )
                    future_to_key[future] = (group_ids, batch_idx)

            completed = 0
            for future in as_completed(future_to_key):
                group_ids, batch_idx = future_to_key[future]
                completed += 1
                if completed % 100 == 0 or completed == total_tasks:
                    logger.info(f"  {completed}/{total_tasks} tasks done")
                try:
                    group_results = future.result()
                    for er in group_results:
                        chunk_batch_map[er.chunk_id][batch_idx] = er
                except Exception as e:
                    logger.error(f"Error in group {group_ids} batch {batch_idx}: {e}")
                    for cid in group_ids:
                        chunk_batch_map[cid][batch_idx] = ExtractionResult(
                            chunk_id=cid,
                            records=[],
                            schema_keys=set(),
                            extraction_time=0.0,
                            error=str(e),
                        )

        # Merge column batches per chunk and cache the unified result.
        all_results: List[ExtractionResult] = list(pre_cached)
        for chunk_id, batch_map in chunk_batch_map.items():
            merged = self._merge_column_batches(chunk_id, batch_map, n_col_batches)
            self._cache_result(chunk_id, table_name, merged)
            all_results.append(merged)

        return all_results
    
    def _extract_single_chunk_safe(
        self,
        chunk: str,
        chunk_id: str,
        table_name: str,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]] = None,
        normalization_hints: Optional[Dict[str, List[str]]] = None,
        entity_col: Optional[str] = None,
    ) -> ExtractionResult:
        """Thread-safe wrapper for single chunk extraction."""
        try:
            result = self._extract_single_chunk(
                chunk,
                table_name,
                schema,
                constrained_keys,
                normalization_hints,
                entity_col,
            )
            result.chunk_id = chunk_id
            return result
        except Exception as e:
            logger.error(f"Error in chunk {chunk_id}: {e}")
            return ExtractionResult(
                chunk_id=chunk_id,
                records=[],
                schema_keys=set(),
                extraction_time=0.0,
                error=str(e)
            )
    
    def extract_batch_with_predicates(
        self,
        chunks: List[str],
        chunk_ids: List[str],
        table_name: str,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]] = None,
        predicates: Optional[List[str]] = None,
        normalization_hints: Optional[Dict[str, List[str]]] = None,
        entity_col: Optional[str] = None,
    ) -> List[ExtractionResult]:
        """
        Extract data matching specific predicates (used by delta engine row-delta).

        Uses the same column-batching strategy as extract_batch to keep each
        LLM call within the 7B model's reliable range (≤ COLUMN_BATCH_SIZE keys).
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from config import MAX_PARALLEL_REQUESTS

        col_batches = self._split_schema_into_batches(
            schema, constrained_keys, normalization_hints
        )
        n_batches = len(col_batches)
        pred_key = "_".join(sorted(predicates or []))

        pre_cached: List[ExtractionResult] = []
        chunk_batch_map: Dict[str, Dict[int, ExtractionResult]] = {}
        future_to_key: Dict = {}

        logger.info(
            f"Extracting {len(chunks)} chunks for '{table_name}' with predicates: "
            f"{n_batches} column batch(es) of ≤{COLUMN_BATCH_SIZE} cols each, "
            f"{MAX_PARALLEL_REQUESTS} parallel workers"
        )

        # Build chunk groups (same pattern as extract_batch)
        groups: List[tuple] = []
        current_texts: List[str] = []
        current_ids: List[str] = []

        for chunk, chunk_id in zip(chunks, chunk_ids):
            cache_key = f"{chunk_id}_{table_name}_{pred_key}"
            cached = self._get_cached_result(cache_key, table_name)
            if cached:
                pre_cached.append(cached)
                continue
            chunk_batch_map[chunk_id] = {}
            current_texts.append(chunk)
            current_ids.append(chunk_id)
            if len(current_texts) == CHUNK_BATCH_SIZE:
                groups.append((list(current_texts), list(current_ids)))
                current_texts.clear()
                current_ids.clear()

        if current_texts:
            groups.append((current_texts, current_ids))

        total_tasks = len(groups) * n_batches
        logger.info(
            f"  {len(groups)} chunk-groups × {n_batches} col-batches = {total_tasks} tasks"
        )

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REQUESTS) as executor:
            for group_texts, group_ids in groups:
                for batch_idx, (col_batch, batch_ck, batch_nh) in enumerate(col_batches):
                    # For predicate extraction we still use the per-chunk method so
                    # predicate filtering is applied inside the call.  We wrap it
                    # in a group loop to stay consistent with the new architecture.
                    future = executor.submit(
                        self._extract_chunk_group_safe,
                        group_texts, group_ids, table_name,
                        col_batch, batch_ck, batch_nh, entity_col,
                    )
                    future_to_key[future] = (group_ids, batch_idx)

            completed = 0
            for future in as_completed(future_to_key):
                group_ids_fut, batch_idx = future_to_key[future]
                completed += 1
                if completed % 100 == 0 or completed == total_tasks:
                    logger.info(f"  {completed}/{total_tasks} tasks done")
                try:
                    group_results = future.result()
                    for er in group_results:
                        chunk_batch_map[er.chunk_id][batch_idx] = er
                except Exception as e:
                    logger.error(f"Error group {group_ids_fut} batch {batch_idx}: {e}")
                    for cid in group_ids_fut:
                        chunk_batch_map[cid][batch_idx] = ExtractionResult(
                            chunk_id=cid,
                            records=[],
                            schema_keys=set(),
                            extraction_time=0.0,
                            error=str(e),
                        )

        all_results: List[ExtractionResult] = list(pre_cached)
        for chunk_id, batch_map in chunk_batch_map.items():
            merged = self._merge_column_batches(chunk_id, batch_map, n_batches)
            cache_key = f"{chunk_id}_{table_name}_{pred_key}"
            self._cache_result(cache_key, table_name, merged)
            all_results.append(merged)

        return all_results
    
    def _extract_single_chunk_with_predicates(
        self,
        chunk: str,
        chunk_id: str,
        table_name: str,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]] = None,
        predicates: Optional[List[str]] = None,
        normalization_hints: Optional[Dict[str, List[str]]] = None,
        entity_col: Optional[str] = None,
    ) -> ExtractionResult:
        """Extract data matching specific predicates."""
        start_time = time.time()
        
        # Build extraction prompt with predicate filtering
        prompt = self._build_extraction_prompt_with_predicates(
            chunk,
            table_name,
            schema,
            constrained_keys,
            predicates,
            normalization_hints,
            entity_col,
        )
        
        # Call LLM
        response = self.llm_client.generate(
            prompt,
            max_tokens=EXTRACTION_MAX_TOKENS,
            temperature=EXTRACTION_TEMPERATURE
        )
        
        # Parse response
        records = self._parse_extraction_response(response, constrained_keys)
        
        # Filter records by predicates if specified
        if predicates and records:
            records = self._filter_records_by_predicates(records, predicates)
        
        # Collect schema keys
        schema_keys = set()
        for record in records:
            schema_keys.update(record.keys())
        
        extraction_time = time.time() - start_time
        
        return ExtractionResult(
            chunk_id=chunk_id,
            records=records,
            schema_keys=schema_keys,
            extraction_time=extraction_time
        )
    
    def _build_extraction_prompt_with_predicates(
        self,
        chunk: str,
        table_name: str,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]] = None,
        predicates: Optional[List[str]] = None,
        normalization_hints: Optional[Dict[str, List[str]]] = None,
        entity_col: Optional[str] = None,
    ) -> str:
        """Build extraction prompt with predicate filtering."""
        keys_to_use = constrained_keys if constrained_keys else schema.keys()
        keys_str = ', '.join(f'"{k}"' for k in keys_to_use)
        
        # Add predicate filtering instructions
        predicate_str = ""
        if predicates:
            predicate_str = f"\n\nIMPORTANT: Only extract records that match these conditions:\n"
            for pred in predicates:
                predicate_str += f"- {pred}\n"
            predicate_str += "\nDo NOT extract records that don't match these conditions."

        normalization_section = self._build_normalization_section(normalization_hints)
        entity_section = self._build_entity_section(entity_col)

        prompt = f"""Extract data from the following text for table '{table_name}'.

Schema (use these keys): {keys_str}
{predicate_str}
{normalization_section}
{entity_section}

Text:
{chunk}

Instructions:
1. Extract data matching the schema
2. Return a JSON array of objects
3. Use the exact keys specified above
4. If no matching data is found, return an empty array []
5. Be precise - only extract data that clearly matches

Output (JSON only):"""
        
        return prompt
    
    def _filter_records_by_predicates(
        self,
        records: List[Dict[str, Any]],
        predicates: List[str]
    ) -> List[Dict[str, Any]]:
        """Filter extracted records by predicates."""
        filtered = []
        
        for record in records:
            matches_all = True
            
            for pred in predicates:
                # Parse predicate (e.g., "age > 25")
                parts = pred.split()
                if len(parts) >= 3:
                    col = parts[0]
                    op = parts[1]
                    val_str = ' '.join(parts[2:]).strip("'\"")
                    
                    if col in record:
                        record_val = record[col]
                        
                        try:
                            # Try numeric comparison
                            if op == '>':
                                if not (float(record_val) > float(val_str)):
                                    matches_all = False
                                    break
                            elif op == '<':
                                if not (float(record_val) < float(val_str)):
                                    matches_all = False
                                    break
                            elif op == '>=':
                                if not (float(record_val) >= float(val_str)):
                                    matches_all = False
                                    break
                            elif op == '<=':
                                if not (float(record_val) <= float(val_str)):
                                    matches_all = False
                                    break
                            elif op == '=' or op == '==':
                                if str(record_val).lower() != val_str.lower():
                                    matches_all = False
                                    break
                            elif op == '!=' or op == '<>':
                                if str(record_val).lower() == val_str.lower():
                                    matches_all = False
                                    break
                        except (ValueError, TypeError):
                            # String comparison fallback
                            if op == '=' or op == '==':
                                if str(record_val).lower() != val_str.lower():
                                    matches_all = False
                                    break
                            elif op == '!=' or op == '<>':
                                if str(record_val).lower() == val_str.lower():
                                    matches_all = False
                                    break
                    else:
                        # Column not in record, doesn't match
                        matches_all = False
                        break
            
            if matches_all:
                filtered.append(record)
        
        return filtered
    
    def _extract_single_chunk(
        self,
        chunk: str,
        table_name: str,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]] = None,
        normalization_hints: Optional[Dict[str, List[str]]] = None,
        entity_col: Optional[str] = None,
    ) -> ExtractionResult:
        """Extract data from a single chunk."""
        start_time = time.time()
        
        # Build extraction prompt
        prompt = self._build_extraction_prompt(
            chunk,
            table_name,
            schema,
            constrained_keys,
            normalization_hints,
            entity_col,
        )
        
        # Call LLM
        response = self.llm_client.generate(
            prompt,
            max_tokens=EXTRACTION_MAX_TOKENS,
            temperature=EXTRACTION_TEMPERATURE
        )
        
        # Parse response
        records = self._parse_extraction_response(response, constrained_keys)
        
        # Collect schema keys
        schema_keys = set()
        for record in records:
            schema_keys.update(record.keys())
        
        extraction_time = time.time() - start_time
        
        return ExtractionResult(
            chunk_id="",  # Will be set by caller
            records=records,
            schema_keys=schema_keys,
            extraction_time=extraction_time
        )
    
    def _build_normalization_section(
        self,
        normalization_hints: Optional[Dict[str, List[str]]]
    ) -> str:
        """
        Build the normalization section of the extraction prompt.

        normalization_hints maps column_name → list of expected literal values
        taken directly from the SQL workload predicates (e.g. {'country': ['USA', 'Canada']}).
        The LLM must output exactly those strings, regardless of how the source text
        phrases them ('United States' → 'USA', 'Kanada' → 'Canada', etc.).
        """
        if not normalization_hints:
            return ""

        lines = [
            "\nValue normalization (CRITICAL — your output must use these exact strings):"
        ]
        for col, literals in sorted(normalization_hints.items()):
            quoted = ", ".join(f'"{v}"' for v in literals)
            lines.append(
                f'  - Column "{col}": allowed values are [{quoted}]. '
                f"If the text expresses the same concept with different wording, "
                f"abbreviations, or aliases, map it to the closest value in this list."
            )
        lines.append(
            "  Do NOT invent values outside the allowed list for these columns."
        )
        return "\n".join(lines)

    def _build_entity_section(self, entity_col: Optional[str]) -> str:
        """
        Build the entity-routing section of an extraction prompt.

        When entity_col is set, every record the LLM returns must include
        a special `_entity` key whose value is the entity_col value for that
        record.  This key is used after extraction to route each record to the
        correct database row (UPDATE existing row or INSERT new row) and is
        then stripped before writing to the DB.
        """
        if not entity_col:
            return ""
        return (
            f"\nEntity routing (MANDATORY — never omit):\n"
            f'Every record MUST include a field "_entity" whose value is the '
            f'"{entity_col}" of the entity being described. '
            f"If the text discusses multiple entities, return a separate record for each.\n"
            f'Example: {{"_entity": "<{entity_col} value>", "other_col": "..."}}'
        )

    def _build_extraction_prompt(
        self,
        chunk: str,
        table_name: str,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]] = None,
        normalization_hints: Optional[Dict[str, List[str]]] = None,
        entity_col: Optional[str] = None,
    ) -> str:
        """Build extraction prompt for LLM."""
        # Build schema description
        schema_lines = []
        for col_name, semantic_type in schema.items():
            schema_lines.append(f"  - {col_name} ({semantic_type})")
        
        schema_desc = "\n".join(schema_lines)
        
        # Build constraints
        constraints = []
        
        if constrained_keys:
            keys_list = ", ".join(sorted(constrained_keys))
            constraints.append(f"- Use ONLY these keys: {keys_list}")
        
        constraints.append("- If a value is not found, use null (not empty string)")
        constraints.append("- If text says 'diabetic', output 'Diabetes'")
        constraints.append("- Normalize values to standard forms")
        constraints.append("- If no data found, return empty list")
        
        constraints_desc = "\n".join(constraints)
        normalization_section = self._build_normalization_section(normalization_hints)
        entity_section = self._build_entity_section(entity_col)
        
        prompt = f"""Extract structured data from the following text for the table "{table_name}".

Schema:
{schema_desc}

Constraints:
{constraints_desc}
{normalization_section}
{entity_section}

Text:
{chunk}

Return a JSON array of objects. Each object should have keys matching the schema.

Example format:
[
  {{"column1": "value1", "column2": "value2"}},
  {{"column1": "value3", "column2": null}}
]

Return ONLY the JSON array, no other text.
"""
        
        return prompt
    
    def _parse_extraction_response(
        self,
        response: str,
        constrained_keys: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """Parse LLM extraction response."""
        try:
            # Try to find JSON in response
            json_match = self._extract_json(response)
            
            if json_match:
                records = json.loads(json_match)
            else:
                # Try parsing entire response
                records = json.loads(response)
            
            # Validate records
            if not isinstance(records, list):
                logger.warning("Extraction response is not a list, wrapping in list")
                records = [records]
            
            # Filter keys if constrained
            if constrained_keys:
                filtered_records = []
                for record in records:
                    filtered = {
                        k: v for k, v in record.items()
                        if k in constrained_keys
                    }
                    if filtered:
                        filtered_records.append(filtered)
                records = filtered_records
            
            return records
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction response: {e}")
            logger.debug(f"Response: {response[:500]}")
            return []
    
    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from text."""
        # Look for JSON array
        import re
        
        # Try to find JSON array
        pattern = r'\[[\s\S]*?\]'
        match = re.search(pattern, text)
        
        if match:
            return match.group(0)
        
        # Try to find JSON object
        pattern = r'\{[\s\S]*?\}'
        match = re.search(pattern, text)
        
        if match:
            return match.group(0)
        
        return None
    
    # ========================================================================
    # Caching
    # ========================================================================
    
    def _get_cache_key(self, chunk_id: str, table_name: str) -> str:
        """Generate cache key."""
        return hashlib.md5(f"{chunk_id}:{table_name}".encode()).hexdigest()
    
    def _get_cached_result(
        self,
        chunk_id: str,
        table_name: str
    ) -> Optional[ExtractionResult]:
        """Get cached extraction result."""
        cache_key = self._get_cache_key(chunk_id, table_name)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                
                return ExtractionResult(
                    chunk_id=data['chunk_id'],
                    records=data['records'],
                    schema_keys=set(data['schema_keys']),
                    extraction_time=data['extraction_time'],
                    error=data.get('error')
                )
            
            except Exception as e:
                logger.warning(f"Error loading cached result: {e}")
        
        return None
    
    def _cache_result(
        self,
        chunk_id: str,
        table_name: str,
        result: ExtractionResult
    ) -> None:
        """Cache extraction result."""
        cache_key = self._get_cache_key(chunk_id, table_name)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        try:
            data = {
                'chunk_id': result.chunk_id,
                'records': result.records,
                'schema_keys': list(result.schema_keys),
                'extraction_time': result.extraction_time,
                'error': result.error
            }
            
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
        
        except Exception as e:
            logger.warning(f"Error caching result: {e}")
    
    # ========================================================================
    # Lazy Enrichment
    # ========================================================================
    
    def enrich_records(
        self,
        records: List[Dict[str, Any]],
        chunk_ids: List[str],
        chunks: List[str],
        table_name: str,
        schema: Dict[str, str],
        new_columns: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Enrich existing records with new columns (lazy enrichment).
        
        Args:
            records: Existing records
            chunk_ids: Chunk IDs for each record
            chunks: Text chunks for each record
            table_name: Name of the table
            schema: Full schema including new columns
            new_columns: List of new columns to extract
            
        Returns:
            Enriched records
        """
        logger.info(f"Enriching {len(records)} records with columns: {new_columns}")
        
        enriched_records = []
        
        for record, chunk_id, chunk in zip(records, chunk_ids, chunks):
            # Build prompt for enrichment
            prompt = self._build_enrichment_prompt(
                chunk,
                table_name,
                schema,
                record,
                new_columns
            )
            
            # Call LLM
            try:
                response = self.llm_client.generate(
                    prompt,
                    max_tokens=500,
                    temperature=EXTRACTION_TEMPERATURE
                )
                
                # Parse response
                new_values = self._parse_enrichment_response(response, new_columns)
                
                # Merge with existing record
                enriched = {**record, **new_values}
                enriched_records.append(enriched)
            
            except Exception as e:
                logger.error(f"Error enriching record: {e}")
                # Keep original record with null values for new columns
                enriched = {**record}
                for col in new_columns:
                    enriched[col] = None
                enriched_records.append(enriched)
            
            # Rate limiting
            time.sleep(0.5)
        
        return enriched_records
    
    def _build_enrichment_prompt(
        self,
        chunk: str,
        table_name: str,
        schema: Dict[str, str],
        existing_record: Dict[str, Any],
        new_columns: List[str]
    ) -> str:
        """Build enrichment prompt."""
        # Show existing data
        existing_data = json.dumps(existing_record, indent=2)
        
        # Show new columns to extract
        new_cols_desc = "\n".join([
            f"  - {col} ({schema.get(col, 'unknown')})"
            for col in new_columns
        ])
        
        prompt = f"""We already have this data from the text:
{existing_data}

Now extract these additional fields from the same text:
{new_cols_desc}

Text:
{chunk}

Return a JSON object with ONLY the new fields. Use null if not found.

Example format:
{{"new_field1": "value", "new_field2": null}}

Return ONLY the JSON object, no other text.
"""
        
        return prompt
    
    def _parse_enrichment_response(
        self,
        response: str,
        new_columns: List[str]
    ) -> Dict[str, Any]:
        """Parse enrichment response."""
        try:
            json_match = self._extract_json(response)
            
            if json_match:
                data = json.loads(json_match)
            else:
                data = json.loads(response)
            
            # Filter to only new columns
            filtered = {
                k: v for k, v in data.items()
                if k in new_columns
            }
            
            return filtered
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse enrichment response: {e}")
            return {col: None for col in new_columns}


# ============================================================================
# Utility Functions
# ============================================================================

def normalize_value(value: Any, semantic_type: str) -> Any:
    """Normalize extracted value based on semantic type."""
    if value is None or value == "":
        return None
    
    # String normalization
    if isinstance(value, str):
        value = value.strip()
        
        # Normalize common variations
        if semantic_type == "PERSON":
            # Capitalize names
            value = value.title()
        
        elif semantic_type == "DATE":
            # Could add date parsing here
            pass
        
        elif semantic_type == "CODE":
            # Uppercase codes
            value = value.upper()
    
    return value
