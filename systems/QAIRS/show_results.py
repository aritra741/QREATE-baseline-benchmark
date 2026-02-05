#!/usr/bin/env python3
"""
Show detailed extraction results from QAIRS pipeline.
"""
import sys
import json
from pathlib import Path
from loguru import logger

# Add QAIRS to path
sys.path.insert(0, str(Path(__file__).parent))

from config import QAIRSConfig
from models import TableSchema, ExtractionTask, Predicate
from sieve import Sieve
from llm_client import OllamaClient
from extractor import Extractor


def main():
    logger.info("=" * 80)
    logger.info("QAIRS Extraction Results")
    logger.info("=" * 80)
    
    # Configuration
    config = QAIRSConfig()
    config.ollama.model = "qwen2.5:7b-instruct"  # Use larger model
    config.extraction.enable_parallel = False
    config.extraction.max_workers = 1
    
    # Load all healthcare chunks
    logger.info("\nLoading all healthcare chunks...")
    base_path = Path("/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare")
    chunks = {}
    
    # Disease
    for fname in ["103.txt", "106.txt"]:
        fpath = base_path / "disease_small" / fname
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            chunks[f"disease_{fname}"] = f.read()
    
    # Drug
    for fname in ["1110.txt", "117088.txt"]:
        fpath = base_path / "drug_small" / fname
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            chunks[f"drug_{fname}"] = f.read()
    
    # Institution
    for fname in ["100027.txt", "103032.txt"]:
        fpath = base_path / "institutes_small" / fname
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            chunks[f"institute_{fname}"] = f.read()
    
    logger.info(f"Loaded {len(chunks)} chunks")
    
    # Initialize components
    logger.info("\nInitializing components...")
    sieve = Sieve(config)
    sieve.build_dictionary(["disease", "drug", "treatment", "manufacturer"], llm_client=None)
    sieve.build_index(chunks)
    
    llm_client = OllamaClient(config)
    extractor = Extractor(config, llm_client, max_workers=1)
    
    # Define test queries
    test_cases = [
        {
            "name": "Extract Disease Information",
            "schema": TableSchema(
                table_name="disease",
                columns={
                    "disease_name": "string",
                    "symptoms": "string",
                    "treatment": "string",
                    "diagnosis": "string",
                }
            ),
            "chunks": [k for k in chunks.keys() if "disease" in k],
        },
        {
            "name": "Extract Drug Information",
            "schema": TableSchema(
                table_name="drug",
                columns={
                    "drug_name": "string",
                    "manufacturer": "string",
                    "dosage": "string",
                    "side_effects": "string",
                }
            ),
            "chunks": [k for k in chunks.keys() if "drug" in k],
        },
        {
            "name": "Extract Institution Information",
            "schema": TableSchema(
                table_name="institution",
                columns={
                    "institution_name": "string",
                    "location": "string",
                    "research_focus": "string",
                    "staff_count": "string",
                }
            ),
            "chunks": [k for k in chunks.keys() if "institute" in k],
        },
    ]
    
    # Run extractions
    for i, test_case in enumerate(test_cases, 1):
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Test {i}: {test_case['name']}")
        logger.info(f"{'=' * 80}")
        logger.info(f"Chunks: {test_case['chunks']}")
        
        task = ExtractionTask(
            task_id=f"test_{i}",
            table_schema=test_case['schema'],
            predicate=None,
            candidate_chunks=test_case['chunks'],
            dictionary_map=sieve.dictionary_map
        )
        
        logger.info(f"Extracting from {len(task.candidate_chunks)} chunks...")
        
        results = extractor.extract(task, chunks, parallel=False)
        
        # Display results
        total_rows = 0
        for chunk_idx, result in enumerate(results):
            chunk_name = result.chunk_id
            chunk_size = len(chunks.get(chunk_name, ""))
            
            logger.info(f"\n  Chunk: {chunk_name} ({chunk_size:,} chars)")
            
            if result.error:
                logger.error(f"    Error: {result.error}")
            elif result.data:
                logger.info(f"    ✓ Extracted {len(result.data)} rows")
                total_rows += len(result.data)
                
                # Show each row
                for row_idx, row in enumerate(result.data, 1):
                    logger.info(f"\n    Row {row_idx}:")
                    for key, value in row.items():
                        # Truncate long values
                        val_str = str(value)[:100]
                        if len(str(value)) > 100:
                            val_str += "..."
                        logger.info(f"      {key}: {val_str}")
            else:
                logger.info(f"    No data extracted")
        
        logger.info(f"\n  Total rows extracted: {total_rows}")
    
    logger.info(f"\n{'=' * 80}")
    logger.info("✓ All extraction tests completed")
    logger.info(f"{'=' * 80}")


if __name__ == "__main__":
    main()
