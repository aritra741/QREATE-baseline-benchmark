#!/usr/bin/env python3
"""
Debug script to examine extraction process step by step.
"""
import sys
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent))

from config import QAIRSConfig
from models import TableSchema, ExtractionTask
from llm_client import OllamaClient
from extractor import Extractor

# Configure logger for debug output
logger.remove()
logger.add(sys.stderr, level="DEBUG")

def main():
    # Load config
    config = QAIRSConfig.from_yaml(Path(__file__).parent / "config.yaml")
    
    # Create schema (from queries)
    schema = TableSchema(
        table_name="player",
        columns={
            'name': 'string',
            'team': 'string',
            'age': 'string',
            'position': 'string'
        }
    )
    
    logger.info(f"Schema: {schema.columns}")
    
    # Sample chunk
    chunk_text = """
    John Smith is a basketball player for the Los Angeles Lakers.
    He is 28 years old and plays as a Guard. He was drafted in 2016
    and has won 2 championships.
    """
    
    # Create extraction task
    task = ExtractionTask(
        task_id="debug_task",
        table_schema=schema,
        predicate=None,
        candidate_chunks=["chunk_1"],
        dictionary_map={}
    )
    
    # Initialize extractor
    llm_client = OllamaClient(config)
    extractor = Extractor(config, llm_client, max_workers=1)
    
    # Build prompt
    prompt = extractor._build_extraction_prompt(
        chunk_text=chunk_text,
        schema=schema,
        predicate=None,
        dictionary_map={}
    )
    
    logger.info("=" * 80)
    logger.info("PROMPT SENT TO LLM:")
    logger.info("=" * 80)
    print(prompt)
    logger.info("=" * 80)
    
    # Call LLM
    logger.info("\nCalling LLM...")
    response = llm_client.generate_json(
        prompt=prompt,
        system_prompt=config.extraction.system_prompt,
        max_retries=3
    )
    
    logger.info("=" * 80)
    logger.info("RAW LLM RESPONSE:")
    logger.info("=" * 80)
    import json
    print(json.dumps(response, indent=2))
    logger.info("=" * 80)
    
    # Parse data
    data = response.get('data', [])
    logger.info(f"\nExtracted {len(data)} rows:")
    for i, row in enumerate(data, 1):
        logger.info(f"Row {i}: {row}")
        logger.info(f"  Types: {[(k, type(v).__name__) for k, v in row.items()]}")

if __name__ == "__main__":
    main()
