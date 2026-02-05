#!/usr/bin/env python3
"""
Initialize QAIRS system: Build sieve and setup database.
"""
import argparse
from pathlib import Path
from typing import Dict
from loguru import logger

from config import QAIRSConfig
from models import create_tables
from sieve import Sieve
from registry import Registry
from llm_client import OllamaClient


def load_corpus(corpus_path: str, chunk_size: int = 1000, chunk_overlap: int = 100) -> Dict[str, str]:
    """
    Load corpus and split into chunks.
    
    Args:
        corpus_path: Path to corpus directory or file
        chunk_size: Size of each chunk in characters
        chunk_overlap: Overlap between chunks
    
    Returns:
        Dictionary mapping chunk_id -> chunk_text
    """
    logger.info(f"Loading corpus from: {corpus_path}")
    
    corpus_path = Path(corpus_path)
    chunks = {}
    
    if corpus_path.is_file():
        # Single file
        with open(corpus_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        
        # Split into chunks
        for i in range(0, len(text), chunk_size - chunk_overlap):
            chunk_id = f"chunk_{i}"
            chunk_text = text[i:i + chunk_size]
            chunks[chunk_id] = chunk_text
    
    elif corpus_path.is_dir():
        # Directory of files
        for file_path in corpus_path.rglob("*.txt"):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            
            # Split into chunks
            for i in range(0, len(text), chunk_size - chunk_overlap):
                chunk_id = f"{file_path.stem}_{i}"
                chunk_text = text[i:i + chunk_size]
                chunks[chunk_id] = chunk_text
    
    else:
        raise ValueError(f"Invalid corpus path: {corpus_path}")
    
    logger.info(f"Loaded {len(chunks)} chunks")
    return chunks


def main():
    parser = argparse.ArgumentParser(description="Initialize QAIRS system")
    parser.add_argument("--corpus-path", required=True, help="Path to corpus")
    parser.add_argument("--config", default=None, help="Path to config YAML")
    parser.add_argument("--dictionary", nargs="+", help="Dictionary terms")
    parser.add_argument("--expand-dict", action="store_true", help="Expand dictionary with LLM")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Chunk size")
    parser.add_argument("--chunk-overlap", type=int, default=100, help="Chunk overlap")
    
    args = parser.parse_args()
    
    # Load config
    if args.config:
        config = QAIRSConfig.from_yaml(args.config)
    else:
        config = QAIRSConfig()
        config.corpus_path = args.corpus_path
    
    logger.info("Initializing QAIRS system")
    
    # Step 1: Create database tables
    logger.info("Creating database tables")
    create_tables(config.database.connection_string)
    
    # Step 2: Initialize LLM client
    logger.info("Connecting to Ollama")
    llm_client = OllamaClient(config)
    
    # Step 3: Build Sieve
    logger.info("Building Sieve index")
    sieve = Sieve(config)
    
    # Build dictionary
    if args.dictionary:
        logger.info(f"Building dictionary with {len(args.dictionary)} terms")
        sieve.build_dictionary(
            terms=args.dictionary,
            llm_client=llm_client if args.expand_dict else None
        )
    
    # Load corpus and build index
    chunks = load_corpus(args.corpus_path, args.chunk_size, args.chunk_overlap)
    sieve.build_index(chunks)
    
    # Save sieve
    sieve.save()
    
    # Step 4: Print statistics
    logger.info("System initialized successfully")
    logger.info("Sieve statistics:")
    stats = sieve.get_statistics()
    for key, value in stats.items():
        logger.info(f"  {key}: {value}")
    
    # Step 5: Initialize registry
    registry = Registry(config)
    logger.info("Registry statistics:")
    reg_stats = registry.get_statistics()
    for key, value in reg_stats.items():
        logger.info(f"  {key}: {value}")
    
    logger.info("✓ QAIRS system ready")


if __name__ == "__main__":
    main()
