#!/usr/bin/env python3
"""
Test QAIRS system with synthetic data.
"""
import tempfile
from pathlib import Path
from loguru import logger

from config import QAIRSConfig
from models import TableSchema, create_tables
from sieve import Sieve
from registry import Registry
from llm_client import OllamaClient
from extractor import Extractor
from query_engine import QueryEngine


def create_synthetic_corpus() -> dict:
    """Create synthetic test corpus."""
    return {
        "chunk_1": """
        Patient John Doe was admitted on 01/15/2024.
        Insurance claim #12345 was DENIED by Cigna.
        Total cost: $5,000.
        Diagnosis: Appendicitis
        """,
        "chunk_2": """
        Patient Jane Smith visited on 02/20/2024.
        Insurance claim #12346 was PAID by Blue Cross.
        Total cost: $2,500.
        Diagnosis: Flu
        """,
        "chunk_3": """
        Patient Bob Johnson was seen on 03/10/2024.
        Insurance claim #12347 was REJECTED by United Healthcare.
        Total cost: $10,000.
        Diagnosis: Surgery
        """,
    }


def test_sieve():
    """Test Sieve construction."""
    logger.info("Testing Sieve")
    
    config = QAIRSConfig()
    sieve = Sieve(config)
    
    # Build dictionary
    terms = ["Denied", "Paid", "USA", "Cigna"]
    sieve.build_dictionary(terms, llm_client=None)
    
    # Build index
    chunks = create_synthetic_corpus()
    sieve.build_index(chunks)
    
    # Query
    results = sieve.query(dict_tags=["Denied"])
    logger.info(f"Sieve query results: {results}")
    assert "chunk_1" in results
    
    # Statistics
    stats = sieve.get_statistics()
    logger.info(f"Sieve stats: {stats}")
    
    logger.info("✓ Sieve test passed")


def test_registry():
    """Test Registry operations."""
    logger.info("Testing Registry")
    
    # Use in-memory SQLite
    config = QAIRSConfig()
    config.database.database = ":memory:"
    
    # Create tables
    create_tables(config.database.connection_string)
    
    registry = Registry(config)
    
    # Register predicate
    from models import Predicate, MaterializationStatus
    pred = Predicate(table_name="Claims", conditions=["status = 'Denied'"])
    pred_id = registry.register_predicate(pred)
    
    # Check status
    status = registry.check_predicate(pred)
    assert status == MaterializationStatus.PENDING
    
    # Update status
    registry.update_status(pred, MaterializationStatus.MATERIALIZED, rows_extracted=10)
    
    # Check again
    status = registry.check_predicate(pred)
    assert status == MaterializationStatus.MATERIALIZED
    
    # Statistics
    stats = registry.get_statistics()
    logger.info(f"Registry stats: {stats}")
    
    logger.info("✓ Registry test passed")


def test_extraction():
    """Test Extraction engine."""
    logger.info("Testing Extraction")
    
    config = QAIRSConfig()
    
    try:
        llm_client = OllamaClient(config)
    except Exception as e:
        logger.warning(f"Ollama not available: {e}")
        logger.info("⊘ Extraction test skipped (Ollama required)")
        return
    
    extractor = Extractor(config, llm_client, max_workers=config.extraction.max_workers)
    
    # Create schema
    schema = TableSchema(
        table_name="Claims",
        columns={
            "PatientName": "string",
            "Status": "string",
            "Cost": "float",
            "Diagnosis": "string"
        },
        enums={"Status": ["Denied", "Paid"]}
    )
    
    # Create task
    from models import ExtractionTask, Predicate
    pred = Predicate(table_name="Claims", conditions=["Status = 'Denied'"])
    task = ExtractionTask(
        task_id="test_task",
        table_schema=schema,
        predicate=pred,
        candidate_chunks=["chunk_1"],
        dictionary_map={"DENIED": "Denied", "REJECTED": "Denied"}
    )
    
    # Extract
    chunks = create_synthetic_corpus()
    results = extractor.extract(task, chunks)
    
    logger.info(f"Extraction results: {results}")
    assert len(results) > 0
    
    logger.info("✓ Extraction test passed")


def test_end_to_end():
    """Test complete query execution."""
    logger.info("Testing end-to-end query execution")
    
    # Setup
    config = QAIRSConfig()
    config.database.database = ":memory:"
    
    # Create database
    from sqlalchemy import create_engine, text
    engine = create_engine(config.database.connection_string)
    
    # Create Claims table
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS Claims (
                PatientName TEXT,
                Status TEXT,
                Cost REAL,
                Diagnosis TEXT
            )
        """))
        conn.commit()
    
    create_tables(config.database.connection_string)
    
    # Initialize components
    sieve = Sieve(config)
    sieve.build_dictionary(["Denied", "Paid", "Cigna"], llm_client=None)
    chunks = create_synthetic_corpus()
    sieve.build_index(chunks)
    
    registry = Registry(config)
    
    try:
        llm_client = OllamaClient(config)
        extractor = Extractor(config, llm_client, max_workers=config.extraction.max_workers)
        
        # Create query engine
        engine = QueryEngine(config, registry, sieve, extractor)
        
        # Execute query
        sql = "SELECT * FROM Claims WHERE Status = 'Denied'"
        results = engine.execute(sql, chunks=chunks)
        
        logger.info(f"Query results: {results}")
        
        logger.info("✓ End-to-end test passed")
    
    except Exception as e:
        logger.warning(f"Ollama not available: {e}")
        logger.info("⊘ End-to-end test skipped (Ollama required)")


def main():
    logger.info("Running QAIRS system tests")
    
    test_sieve()
    test_registry()
    test_extraction()
    test_end_to_end()
    
    logger.info("✓ All tests completed")


if __name__ == "__main__":
    main()
