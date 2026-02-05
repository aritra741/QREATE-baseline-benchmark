"""
Extraction Engine: LLM-based data extraction with view synthesis.
"""
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger
from tqdm import tqdm

from models import (
    ExtractionTask, ExtractionResult, TableSchema, Predicate
)
from config import QAIRSConfig
from llm_client import OllamaClient


class Extractor:
    """
    The Extraction Engine uses Qwen 2.5 to extract structured data
    from text chunks according to a schema and predicate.
    
    Supports parallel extraction for improved throughput.
    """
    
    def __init__(self, config: QAIRSConfig, llm_client: OllamaClient, max_workers: int = 4):
        self.config = config
        self.llm = llm_client
        self.max_workers = max_workers
    
    def extract(
        self,
        task: ExtractionTask,
        chunks: Dict[str, str],
        parallel: bool = True
    ) -> List[ExtractionResult]:
        """
        Execute an extraction task.
        
        Args:
            task: ExtractionTask specifying what to extract
            chunks: Dictionary mapping chunk_id -> chunk_text
            parallel: If True, process chunks in parallel
        
        Returns:
            List of ExtractionResult objects
        """
        logger.info(f"Starting extraction task {task.task_id}")
        logger.info(f"Processing {len(task.candidate_chunks)} chunks")
        
        if parallel and self.max_workers > 1:
            results = self._extract_parallel(task, chunks)
        else:
            results = self._extract_sequential(task, chunks)
        
        # Statistics
        total_rows = sum(len(r.data) for r in results if r.data)
        logger.info(f"Extraction complete: {total_rows} rows from {len(results)} chunks")
        
        return results
    
    def _extract_sequential(
        self,
        task: ExtractionTask,
        chunks: Dict[str, str]
    ) -> List[ExtractionResult]:
        """Sequential extraction (original implementation)."""
        results = []
        
        for chunk_id in tqdm(task.candidate_chunks, desc="Extracting"):
            if chunk_id not in chunks:
                logger.warning(f"Chunk {chunk_id} not found in corpus")
                continue
            
            chunk_text = chunks[chunk_id]
            result = self._extract_from_chunk(
                chunk_id=chunk_id,
                chunk_text=chunk_text,
                schema=task.table_schema,
                predicate=task.predicate,
                dictionary_map=task.dictionary_map
            )
            results.append(result)
        
        return results
    
    def _extract_parallel(
        self,
        task: ExtractionTask,
        chunks: Dict[str, str]
    ) -> List[ExtractionResult]:
        """Parallel extraction using ThreadPoolExecutor."""
        results = []
        
        # Create extraction jobs
        jobs = []
        for chunk_id in task.candidate_chunks:
            if chunk_id not in chunks:
                logger.warning(f"Chunk {chunk_id} not found in corpus")
                continue
            jobs.append((chunk_id, chunks[chunk_id]))
        
        # Process in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all jobs
            future_to_chunk = {
                executor.submit(
                    self._extract_from_chunk,
                    chunk_id=chunk_id,
                    chunk_text=chunk_text,
                    schema=task.table_schema,
                    predicate=task.predicate,
                    dictionary_map=task.dictionary_map
                ): chunk_id
                for chunk_id, chunk_text in jobs
            }
            
            # Collect results as they complete
            for future in tqdm(as_completed(future_to_chunk), total=len(jobs), desc="Extracting (parallel)"):
                chunk_id = future_to_chunk[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Extraction failed for chunk {chunk_id}: {e}")
                    results.append(ExtractionResult(
                        chunk_id=chunk_id,
                        data=[],
                        error=str(e)
                    ))
        
        return results
    
    def _extract_from_chunk(
        self,
        chunk_id: str,
        chunk_text: str,
        schema: TableSchema,
        predicate: Optional[Predicate],
        dictionary_map: Dict[str, str]
    ) -> ExtractionResult:
        """
        Extract data from a single chunk.
        """
        # Build prompt
        prompt = self._build_extraction_prompt(
            chunk_text=chunk_text,
            schema=schema,
            predicate=predicate,
            dictionary_map=dictionary_map
        )
        
        # Call LLM
        try:
            response = self.llm.generate_json(
                prompt=prompt,
                system_prompt=self.config.extraction.system_prompt,
                max_retries=self.config.extraction.max_retries
            )
            
            # Parse response
            data = response.get('data', [])
            has_more = response.get('has_more', False)
            
            # Validate schema if enabled
            if self.config.extraction.validate_schema:
                data = self._validate_rows(data, schema)
            
            return ExtractionResult(
                chunk_id=chunk_id,
                data=data,
                has_more=has_more
            )
        
        except Exception as e:
            logger.error(f"Extraction failed for chunk {chunk_id}: {e}")
            return ExtractionResult(
                chunk_id=chunk_id,
                data=[],
                error=str(e)
            )
    
    def _build_extraction_prompt(
        self,
        chunk_text: str,
        schema: TableSchema,
        predicate: Optional[Predicate],
        dictionary_map: Dict[str, str]
    ) -> str:
        """
        Build the extraction prompt for the LLM.
        """
        prompt_parts = []
        
        # Schema description
        prompt_parts.append("TASK: Extract structured data from the following text.")
        prompt_parts.append("")
        prompt_parts.append("SCHEMA:")
        prompt_parts.append(schema.to_prompt_string())
        prompt_parts.append("")
        
        # Dictionary mapping
        if dictionary_map:
            prompt_parts.append("DICTIONARY MAPPING:")
            prompt_parts.append("Use these canonical terms when extracting:")
            for synonym, canonical in dictionary_map.items():
                prompt_parts.append(f"  - If text mentions '{synonym}', output '{canonical}'")
            prompt_parts.append("")
        
        # Predicate filter
        if predicate:
            prompt_parts.append("FILTER:")
            prompt_parts.append(f"Only extract rows where: {predicate.to_sql_where()}")
            prompt_parts.append("IMPORTANT: Ignore any data that does not match this filter.")
            prompt_parts.append("")
        
        # Output format
        prompt_parts.append("OUTPUT FORMAT:")
        prompt_parts.append("Return a JSON object with this structure:")
        prompt_parts.append("{")
        prompt_parts.append('  "data": [')
        prompt_parts.append('    {')
        for col in schema.columns.keys():
            prompt_parts.append(f'      "{col}": <value>,')
        prompt_parts.append('    },')
        prompt_parts.append('    ...')
        prompt_parts.append('  ],')
        prompt_parts.append('  "has_more": false  // Set to true if text contains more data you cannot extract')
        prompt_parts.append("}")
        prompt_parts.append("")
        
        # Constraints
        prompt_parts.append("CONSTRAINTS:")
        prompt_parts.append("1. Extract ALL rows that match the schema and filter")
        prompt_parts.append("2. Use exact column names from schema")
        prompt_parts.append("3. Apply dictionary mappings consistently")
        prompt_parts.append("4. Set 'has_more' to true only if you see valid data you cannot extract")
        prompt_parts.append("5. Return empty 'data' array if no matching rows found")
        prompt_parts.append("6. CRITICAL: All field values MUST be strings or numbers, NEVER arrays/lists")
        prompt_parts.append("7. If multiple values exist (e.g., multiple teams), choose the MOST RECENT or PRIMARY one")
        prompt_parts.append("")
        
        # Input text
        prompt_parts.append("INPUT TEXT:")
        prompt_parts.append("---")
        prompt_parts.append(chunk_text)
        prompt_parts.append("---")
        prompt_parts.append("")
        prompt_parts.append("JSON OUTPUT:")
        
        return "\n".join(prompt_parts)
    
    def _validate_rows(
        self,
        rows: List[Dict[str, Any]],
        schema: TableSchema
    ) -> List[Dict[str, Any]]:
        """
        Validate extracted rows against schema.
        """
        valid_rows = []
        
        for row in rows:
            # Check all required columns present
            if not all(col in row for col in schema.columns.keys()):
                logger.warning(f"Row missing columns: {row}")
                continue
            
            # Check enum constraints
            valid = True
            for col, allowed_values in schema.enums.items():
                if col in row and row[col] not in allowed_values:
                    logger.warning(f"Invalid enum value for {col}: {row[col]}")
                    valid = False
                    break
            
            if valid:
                valid_rows.append(row)
        
        return valid_rows
    
    def extract_denormalized_view(
        self,
        chunk_text: str,
        primary_schema: TableSchema,
        related_schemas: List[TableSchema],
        predicate: Optional[Predicate] = None
    ) -> ExtractionResult:
        """
        Extract a denormalized view (joined data) to ensure referential integrity.
        
        This is useful for queries that join multiple tables.
        """
        # Build combined schema
        combined_columns = {}
        for schema in [primary_schema] + related_schemas:
            for col, dtype in schema.columns.items():
                combined_columns[f"{schema.table_name}.{col}"] = dtype
        
        combined_schema = TableSchema(
            table_name=f"{primary_schema.table_name}_view",
            columns=combined_columns
        )
        
        # Extract as normal
        return self._extract_from_chunk(
            chunk_id="view",
            chunk_text=chunk_text,
            schema=combined_schema,
            predicate=predicate,
            dictionary_map={}
        )
