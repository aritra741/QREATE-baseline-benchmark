#!/usr/bin/env python3
"""
Execute a query using QAIRS system.
"""
import argparse
import json
from pathlib import Path
from loguru import logger

from config import QAIRSConfig
from sieve import Sieve
from registry import Registry
from llm_client import OllamaClient
from extractor import Extractor
from query_engine import QueryEngine
from init_system import load_corpus


def main():
    parser = argparse.ArgumentParser(description="Execute query with QAIRS")
    parser.add_argument("--sql", required=True, help="SQL query to execute")
    parser.add_argument("--config", default=None, help="Path to config YAML")
    parser.add_argument("--corpus-path", help="Path to corpus (if extraction needed)")
    parser.add_argument("--output", help="Output file for results (JSON)")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logger.add(lambda msg: print(msg), level="DEBUG")
    
    # Load config
    if args.config:
        config = QAIRSConfig.from_yaml(args.config)
    else:
        config = QAIRSConfig()
    
    logger.info("Loading QAIRS system")
    
    # Load components
    sieve = Sieve.load(config.sieve.sieve_path, config)
    registry = Registry(config)
    llm_client = OllamaClient(config)
    extractor = Extractor(config, llm_client, max_workers=config.extraction.max_workers)
    
    # Create query engine
    engine = QueryEngine(config, registry, sieve, extractor)
    
    # Load corpus if needed
    chunks = None
    if args.corpus_path:
        chunks = load_corpus(args.corpus_path, config.chunk_size, config.chunk_overlap)
    
    # Execute query
    logger.info(f"Executing: {args.sql}")
    results = engine.execute(args.sql, chunks=chunks)
    
    # Output results
    logger.info(f"Query returned {len(results)} rows")
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results written to {args.output}")
    else:
        # Print to console
        print("\nResults:")
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
