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
    
    def extract_batch(
        self,
        chunks: List[str],
        chunk_ids: List[str],
        table_name: str,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]] = None
    ) -> List[ExtractionResult]:
        """
        Extract data from a batch of chunks.
        
        Args:
            chunks: List of text chunks
            chunk_ids: List of chunk IDs
            table_name: Name of the table
            schema: Column schema
            constrained_keys: Optional set of required keys
            
        Returns:
            List of ExtractionResult
        """
        results = []
        
        # Process in batches
        for i in range(0, len(chunks), EXTRACTION_BATCH_SIZE):
            batch_chunks = chunks[i:i + EXTRACTION_BATCH_SIZE]
            batch_ids = chunk_ids[i:i + EXTRACTION_BATCH_SIZE]
            
            logger.info(f"Extracting batch {i // EXTRACTION_BATCH_SIZE + 1} "
                       f"({len(batch_chunks)} chunks)")
            
            for chunk, chunk_id in zip(batch_chunks, batch_ids):
                # Check cache
                cached_result = self._get_cached_result(chunk_id, table_name)
                
                if cached_result:
                    results.append(cached_result)
                    continue
                
                # Extract
                try:
                    result = self._extract_single_chunk(
                        chunk,
                        table_name,
                        schema,
                        constrained_keys
                    )
                    result.chunk_id = chunk_id
                    
                    # Cache result
                    self._cache_result(chunk_id, table_name, result)
                    
                    results.append(result)
                
                except Exception as e:
                    logger.error(f"Error extracting from chunk {chunk_id}: {e}")
                    results.append(ExtractionResult(
                        chunk_id=chunk_id,
                        records=[],
                        schema_keys=set(),
                        extraction_time=0.0,
                        error=str(e)
                    ))
                
                # Rate limiting
                time.sleep(0.5)
        
        return results
    
    def _extract_single_chunk(
        self,
        chunk: str,
        table_name: str,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]] = None
    ) -> ExtractionResult:
        """Extract data from a single chunk."""
        start_time = time.time()
        
        # Build extraction prompt
        prompt = self._build_extraction_prompt(
            chunk,
            table_name,
            schema,
            constrained_keys
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
    
    def _build_extraction_prompt(
        self,
        chunk: str,
        table_name: str,
        schema: Dict[str, str],
        constrained_keys: Optional[Set[str]] = None
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
        
        prompt = f"""Extract structured data from the following text for the table "{table_name}".

Schema:
{schema_desc}

Constraints:
{constraints_desc}

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
