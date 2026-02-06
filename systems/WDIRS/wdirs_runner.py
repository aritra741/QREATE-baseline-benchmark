"""
WDIRS Runner - Main orchestration module.
Integrates all components and provides the main interface.
"""

import json
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
import sys

from data_layer import DataLayer, RecursiveCharacterSplitter, TextChunk
from lattice_planner import LatticePlanner, load_workload_from_directory
from sieve_synthesizer import SieveSynthesizer
from extractor import ConstrainedExtractor, OllamaClient
from entity_resolver import EntityResolver, extract_mentions_from_records, apply_canonical_map
from delta_engine import DeltaEngine, DeltaType

from config import (
    SOURCE_DATA_DIR,
    QUERY_DIR,
    get_dataset_path,
    get_schema_path,
    get_workload_path,
    CACHE_DIR,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_FILE
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class PreprocessingResult:
    """Result of preprocessing phase."""
    success: bool
    tables_processed: List[str]
    total_chunks: int
    total_records: int
    preprocessing_time: float
    error: Optional[str] = None

@dataclass
class QueryResult:
    """Result of query execution."""
    success: bool
    results: List[Dict[str, Any]]
    delta_type: str
    rows_extracted: int
    rows_enriched: int
    execution_time: float
    error: Optional[str] = None


# ============================================================================
# WDIRS Runner
# ============================================================================

class WDIRSRunner:
    """
    Main orchestrator for WDIRS system.
    Coordinates all phases of the pipeline.
    """
    
    def __init__(
        self,
        dataset: str,
        postgres_uri: Optional[str] = None
    ):
        """
        Initialize WDIRS runner.
        
        Args:
            dataset: Name of the dataset
            postgres_uri: Optional PostgreSQL connection URI
        """
        self.dataset = dataset
        
        logger.info(f"Initializing WDIRS for dataset: {dataset}")
        
        # Initialize components
        self.data_layer = DataLayer(postgres_uri) if postgres_uri else DataLayer()
        self.llm_client = OllamaClient()
        self.lattice_planner = LatticePlanner(self.llm_client)
        self.sieve_synthesizer = SieveSynthesizer(self.llm_client)
        self.extractor = ConstrainedExtractor(self.llm_client)
        self.entity_resolver = EntityResolver(self.llm_client)
        self.delta_engine = DeltaEngine(
            self.data_layer,
            self.lattice_planner,
            self.extractor,
            self.entity_resolver
        )
        
        # Text splitter
        self.text_splitter = RecursiveCharacterSplitter()
        
        # Cache
        self.cache_dir = CACHE_DIR / dataset
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("WDIRS initialization complete")
    
    # ========================================================================
    # Phase 1: Offline Relational Synthesis (Preprocessing)
    # ========================================================================
    
    def preprocess(
        self,
        workload_queries: Optional[List[str]] = None
    ) -> PreprocessingResult:
        """
        Run complete preprocessing pipeline.
        
        Args:
            workload_queries: Optional list of SQL queries. If not provided, loads from Query directory.
            
        Returns:
            PreprocessingResult
        """
        logger.info("=" * 80)
        logger.info("PHASE 1: OFFLINE RELATIONAL SYNTHESIS")
        logger.info("=" * 80)
        
        start_time = time.time()
        
        try:
            # Step 1: Load and parse workload
            logger.info("\n[Step 1/6] Loading workload...")
            if workload_queries is None:
                workload_path = str(QUERY_DIR / self.dataset)
                from lattice_planner import load_workload_from_directory
                workload_queries = load_workload_from_directory(workload_path)
            
            lattice = self.lattice_planner.parse_workload(workload_queries)
            
            logger.info(f"Workload parsed: {len(lattice.tables)} tables")
            
            # Step 2: Ingest text data
            logger.info("\n[Step 2/6] Ingesting text data...")
            total_chunks = self._ingest_text_data()
            logger.info(f"Ingested {total_chunks} chunks")
            
            # Step 3: Synthesize sieves
            logger.info("\n[Step 3/6] Synthesizing programmatic sieves...")
            self._synthesize_sieves(lattice)
            
            # Step 4: Global extraction
            logger.info("\n[Step 4/6] Performing constrained global extraction...")
            total_records = self._global_extraction(lattice)
            logger.info(f"Extracted {total_records} records")
            
            # Step 5: Entity resolution
            logger.info("\n[Step 5/6] Performing proactive entity resolution...")
            self._proactive_entity_resolution(lattice)
            
            # Step 6: Save preprocessing results
            logger.info("\n[Step 6/6] Saving preprocessing results...")
            self._save_preprocessing_results(lattice)
            
            preprocessing_time = time.time() - start_time
            
            result = PreprocessingResult(
                success=True,
                tables_processed=list(lattice.tables.keys()),
                total_chunks=total_chunks,
                total_records=total_records,
                preprocessing_time=preprocessing_time
            )
            
            logger.info("=" * 80)
            logger.info("PREPROCESSING COMPLETE")
            logger.info(f"Time: {preprocessing_time:.2f}s")
            logger.info(f"Tables: {len(lattice.tables)}")
            logger.info(f"Chunks: {total_chunks}")
            logger.info(f"Records: {total_records}")
            logger.info("=" * 80)
            
            return result
        
        except Exception as e:
            logger.error(f"Preprocessing failed: {e}", exc_info=True)
            preprocessing_time = time.time() - start_time
            
            return PreprocessingResult(
                success=False,
                tables_processed=[],
                total_chunks=0,
                total_records=0,
                preprocessing_time=preprocessing_time,
                error=str(e)
            )
    
    def _ingest_text_data(self) -> int:
        """Ingest text data and create chunks."""
        dataset_path = get_dataset_path(self.dataset)
        
        if not dataset_path.exists():
            logger.warning(f"Dataset path not found: {dataset_path}")
            return 0
        
        total_chunks = 0
        
        # Process all text files
        for text_file in dataset_path.glob("**/*.txt"):
            try:
                with open(text_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Create chunks
                doc_id = str(text_file.relative_to(dataset_path))
                chunks = self.text_splitter.create_chunks(
                    content,
                    doc_id,
                    metadata={"source_file": str(text_file)}
                )
                
                # Insert into database
                self.data_layer.insert_chunks(chunks)
                total_chunks += len(chunks)
                
                logger.debug(f"Ingested {len(chunks)} chunks from {doc_id}")
            
            except Exception as e:
                logger.error(f"Error ingesting {text_file}: {e}")
        
        return total_chunks
    
    def _synthesize_sieves(self, lattice) -> None:
        """Synthesize sieves for all tables."""
        for table_name, table_info in lattice.tables.items():
            try:
                # Get sample chunks
                sample_chunks_objs = self.data_layer.get_all_chunks(
                    limit=10
                )
                sample_chunks = [c.content for c in sample_chunks_objs]
                
                # Get schema
                schema = self.lattice_planner.get_table_schema(table_name)
                
                # Synthesize sieve
                sieve_result = self.sieve_synthesizer.synthesize_sieve(
                    table_name,
                    schema,
                    sample_chunks
                )
                
                logger.info(f"Synthesized sieve for {table_name} "
                           f"(accuracy: {sieve_result.accuracy:.2%})")
                
                # Apply sieve to all chunks
                all_chunks = self.data_layer.get_all_chunks()
                chunk_texts = [c.content for c in all_chunks]
                
                relevant_indices = self.sieve_synthesizer.apply_sieve(
                    table_name,
                    chunk_texts
                )
                
                # Store candidate indices
                relevant_chunk_ids = [all_chunks[i].chunk_id for i in relevant_indices]
                self.data_layer.insert_candidates(table_name, relevant_chunk_ids)
                
                logger.info(f"Indexed {len(relevant_chunk_ids)} candidate chunks for {table_name}")
            
            except Exception as e:
                logger.error(f"Error synthesizing sieve for {table_name}: {e}")
    
    def _global_extraction(self, lattice) -> int:
        """Perform constrained global extraction."""
        total_records = 0
        
        for table_name, table_info in lattice.tables.items():
            try:
                # Get schema
                schema = self.lattice_planner.get_table_schema(table_name)
                
                # Get candidate chunks
                candidate_chunk_ids = self.data_layer.get_candidates(table_name)
                
                if not candidate_chunk_ids:
                    logger.warning(f"No candidate chunks for {table_name}")
                    continue
                
                candidate_chunks = self.data_layer.get_chunks_by_ids(candidate_chunk_ids)
                
                # Schema stabilization
                sample_chunks = [c.content for c in candidate_chunks[:50]]
                stabilized_schema = self.extractor.stabilize_schema(
                    table_name,
                    schema,
                    sample_chunks
                )
                
                logger.info(f"Stabilized schema for {table_name}: "
                           f"{len(stabilized_schema.frozen_keys)} keys")
                
                # Extract from all candidate chunks
                chunk_texts = [c.content for c in candidate_chunks]
                chunk_ids = [c.chunk_id for c in candidate_chunks]
                
                results = self.extractor.extract_batch(
                    chunk_texts,
                    chunk_ids,
                    table_name,
                    schema,
                    stabilized_schema.frozen_keys
                )
                
                # Count records
                table_records = sum(len(r.records) for r in results)
                total_records += table_records
                
                logger.info(f"Extracted {table_records} records for {table_name}")
                
                # Update metadata
                for col_name in schema.keys():
                    self.data_layer.update_metadata(
                        table_name,
                        col_name,
                        [],
                        "PARTIAL",
                        table_records
                    )
            
            except Exception as e:
                logger.error(f"Error extracting for {table_name}: {e}")
        
        return total_records
    
    def _proactive_entity_resolution(self, lattice) -> None:
        """Perform proactive entity resolution."""
        for table_name, table_info in lattice.tables.items():
            try:
                # Get extracted records (would load from cache/DB)
                # For now, skip actual resolution
                logger.info(f"Entity resolution for {table_name} (skipped in demo)")
            
            except Exception as e:
                logger.error(f"Error in entity resolution for {table_name}: {e}")
    
    def _save_preprocessing_results(self, lattice) -> None:
        """Save preprocessing results to cache."""
        results_file = self.cache_dir / "preprocessing_results.json"
        
        extraction_plan = self.lattice_planner.get_extraction_plan()
        
        with open(results_file, 'w') as f:
            json.dump(extraction_plan, f, indent=2)
        
        logger.info(f"Saved preprocessing results to {results_file}")
    
    # ========================================================================
    # Phase 2: Runtime Execution
    # ========================================================================
    
    def execute_query(self, query: str) -> QueryResult:
        """
        Execute query with delta engine.
        
        Args:
            query: SQL query string
            
        Returns:
            QueryResult
        """
        logger.info("=" * 80)
        logger.info("PHASE 2: RUNTIME QUERY EXECUTION")
        logger.info("=" * 80)
        logger.info(f"Query: {query}")
        
        start_time = time.time()
        
        try:
            # Analyze query
            plan = self.delta_engine.analyze_query(query)
            
            logger.info(f"Delta plan: {plan.delta_type.value}")
            logger.info(f"Missing columns: {plan.missing_columns}")
            logger.info(f"Missing predicates: {plan.missing_predicates}")
            
            # Execute delta
            delta_result = self.delta_engine.execute_delta(plan, query)
            
            if not delta_result.success:
                raise Exception(f"Delta execution failed: {delta_result.error}")
            
            # Execute SQL query (would use actual SQL engine)
            results = []
            
            execution_time = time.time() - start_time
            
            result = QueryResult(
                success=True,
                results=results,
                delta_type=plan.delta_type.value,
                rows_extracted=delta_result.rows_extracted,
                rows_enriched=delta_result.rows_enriched,
                execution_time=execution_time
            )
            
            logger.info("=" * 80)
            logger.info("QUERY EXECUTION COMPLETE")
            logger.info(f"Time: {execution_time:.2f}s")
            logger.info(f"Delta type: {plan.delta_type.value}")
            logger.info(f"Rows extracted: {delta_result.rows_extracted}")
            logger.info(f"Rows enriched: {delta_result.rows_enriched}")
            logger.info("=" * 80)
            
            return result
        
        except Exception as e:
            logger.error(f"Query execution failed: {e}", exc_info=True)
            execution_time = time.time() - start_time
            
            return QueryResult(
                success=False,
                results=[],
                delta_type="error",
                rows_extracted=0,
                rows_enriched=0,
                execution_time=execution_time,
                error=str(e)
            )
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get system statistics."""
        stats = {
            "dataset": self.dataset,
            "total_chunks": self.data_layer.count_chunks(),
            "tables": [],
            "metadata_entries": len(self.data_layer.get_metadata())
        }
        
        # Get table statistics
        metadata_entries = self.data_layer.get_metadata()
        tables_set = set(entry.table_name for entry in metadata_entries)
        
        for table_name in tables_set:
            table_metadata = self.data_layer.get_metadata(table_name=table_name)
            
            stats["tables"].append({
                "name": table_name,
                "columns": len(table_metadata),
                "status": "materialized" if table_metadata else "pending"
            })
        
        return stats
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        import shutil
        
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Cache cleared")
    
    def close(self) -> None:
        """Close all connections."""
        self.data_layer.close()
        logger.info("WDIRS runner closed")


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """Main CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="WDIRS - Workload-Driven Incremental Relational Synthesis")
    parser.add_argument("dataset", help="Dataset name")
    parser.add_argument("--preprocess", action="store_true", help="Run preprocessing")
    parser.add_argument("--query", help="Execute SQL query")
    parser.add_argument("--workload", help="Path to workload directory")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache")
    
    args = parser.parse_args()
    
    # Initialize runner
    runner = WDIRSRunner(args.dataset)
    
    try:
        if args.clear_cache:
            runner.clear_cache()
            print("Cache cleared")
        
        if args.preprocess:
            result = runner.preprocess(args.workload)
            
            if result.success:
                print(f"\nPreprocessing complete!")
                print(f"Tables: {len(result.tables_processed)}")
                print(f"Chunks: {result.total_chunks}")
                print(f"Records: {result.total_records}")
                print(f"Time: {result.preprocessing_time:.2f}s")
            else:
                print(f"\nPreprocessing failed: {result.error}")
                sys.exit(1)
        
        if args.query:
            result = runner.execute_query(args.query)
            
            if result.success:
                print(f"\nQuery executed successfully!")
                print(f"Delta type: {result.delta_type}")
                print(f"Rows extracted: {result.rows_extracted}")
                print(f"Rows enriched: {result.rows_enriched}")
                print(f"Time: {result.execution_time:.2f}s")
                print(f"\nResults: {len(result.results)} rows")
            else:
                print(f"\nQuery failed: {result.error}")
                sys.exit(1)
        
        if args.stats:
            stats = runner.get_statistics()
            print(f"\nSystem Statistics:")
            print(f"Dataset: {stats['dataset']}")
            print(f"Total chunks: {stats['total_chunks']}")
            print(f"Metadata entries: {stats['metadata_entries']}")
            print(f"\nTables:")
            for table in stats['tables']:
                print(f"  - {table['name']}: {table['columns']} columns ({table['status']})")
    
    finally:
        runner.close()


if __name__ == "__main__":
    main()
