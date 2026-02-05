#!/usr/bin/env python3
"""
Simple QAIRS test without database - just test extraction.
"""
import sys
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
    logger.info("=" * 70)
    logger.info("QAIRS Simple Extraction Test")
    logger.info("=" * 70)
    
    # Configuration
    config = QAIRSConfig()
    config.ollama.model = "qwen2.5:0.5b"
    config.extraction.enable_parallel = False
    config.extraction.max_workers = 1
    
    logger.info(f"Using LLM: {config.ollama.model}")
    
    # Load one healthcare file
    logger.info("\nLoading corpus...")
    disease_file = Path("/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare/disease_small/103.txt")
    with open(disease_file, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    
    chunks = {"disease_103": text[:2000]}  # Just first 2000 chars for speed
    logger.info(f"Loaded 1 chunk: {len(chunks['disease_103'])} chars")
    
    # Initialize Sieve (minimal)
    logger.info("\nBuilding Sieve...")
    sieve = Sieve(config)
    sieve.build_dictionary(["disease", "treatment", "diagnosis"], llm_client=None)
    sieve.build_index(chunks)
    
    # Connect to Ollama
    logger.info("\nConnecting to Ollama...")
    try:
        llm_client = OllamaClient(config)
        logger.info("✓ Connected")
    except Exception as e:
        logger.error(f"Failed: {e}")
        return
    
    # Create schema
    logger.info("\nCreating schema...")
    schema = TableSchema(
        table_name="disease",
        columns={
            "disease_name": "string",
            "symptoms": "string",
            "treatment": "string",
        }
    )
    
    # Create extraction task
    logger.info("\nCreating extraction task...")
    task = ExtractionTask(
        task_id="test",
        table_schema=schema,
        predicate=None,  # Extract all
        candidate_chunks=list(chunks.keys()),
        dictionary_map=sieve.dictionary_map
    )
    
    # Extract
    logger.info("\nExtracting data...")
    extractor = Extractor(config, llm_client, max_workers=1)
    
    try:
        results = extractor.extract(task, chunks, parallel=False)
        
        logger.info(f"\n✓ Extraction complete!")
        logger.info(f"  Processed: {len(results)} chunks")
        
        for i, result in enumerate(results):
            if result.data:
                logger.info(f"  Chunk {i+1}: {len(result.data)} rows extracted")
                if result.data:
                    logger.info(f"    Sample row keys: {list(result.data[0].keys())}")
                    logger.info(f"    Sample data: {result.data[0]}")
            elif result.error:
                logger.error(f"  Chunk {i+1}: Error - {result.error}")
            else:
                logger.info(f"  Chunk {i+1}: No data extracted")
        
        total_rows = sum(len(r.data) for r in results if r.data)
        logger.info(f"\nTotal rows extracted: {total_rows}")
        
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    logger.info("\n" + "=" * 70)
    logger.info("✓ Test completed!")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
