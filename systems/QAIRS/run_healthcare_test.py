#!/usr/bin/env python3
"""
Run QAIRS pipeline with healthcare data and join queries.
"""
import sys
import os
from pathlib import Path
from loguru import logger

# Add QAIRS to path
sys.path.insert(0, str(Path(__file__).parent))

from config import QAIRSConfig
from models import TableSchema, create_tables
from sieve import Sieve
from registry import Registry
from llm_client import OllamaClient
from extractor import Extractor
from planner import WorkloadPlanner, SQLParser
from query_engine import QueryEngine


def load_healthcare_corpus():
    """Load first 2 files from each healthcare subfolder."""
    base_path = Path("/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare")
    
    chunks = {}
    
    # Disease files
    disease_files = ["103.txt", "106.txt"]
    for fname in disease_files:
        fpath = base_path / "disease_small" / fname
        if fpath.exists():
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            chunks[f"disease_{fname}"] = text
            logger.info(f"Loaded {fname}: {len(text)} chars")
    
    # Drug files
    drug_files = ["1110.txt", "117088.txt"]
    for fname in drug_files:
        fpath = base_path / "drug_small" / fname
        if fpath.exists():
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            chunks[f"drug_{fname}"] = text
            logger.info(f"Loaded {fname}: {len(text)} chars")
    
    # Institute files
    institute_files = ["100027.txt", "103032.txt"]
    for fname in institute_files:
        fpath = base_path / "institutes_small" / fname
        if fpath.exists():
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            chunks[f"institute_{fname}"] = text
            logger.info(f"Loaded {fname}: {len(text)} chars")
    
    logger.info(f"Total chunks loaded: {len(chunks)}")
    return chunks


def load_join_queries():
    """Load join queries from SQL file."""
    query_path = Path("/Users/aritramazumder/Documents/UDA-Bench-main/Query/Med/Join/join_queries.sql")
    
    with open(query_path, 'r') as f:
        content = f.read()
    
    # Split by lines and extract queries
    queries = []
    current_query = []
    
    for line in content.split('\n'):
        line = line.strip()
        
        # Skip comment-only lines
        if line.startswith('--') or not line:
            continue
        
        # Remove inline comments
        if '--' in line:
            line = line[:line.index('--')].strip()
        
        if line:
            current_query.append(line)
            
            # If line ends with semicolon, we have a complete query
            if line.endswith(';'):
                query = ' '.join(current_query).rstrip(';')
                if query.upper().startswith('SELECT'):
                    queries.append(query)
                current_query = []
    
    logger.info(f"Loaded {len(queries)} queries")
    return queries


def create_healthcare_schemas():
    """Create schemas for drug, disease, and institution tables."""
    schemas = {}
    
    # Drug schema
    schemas['drug'] = TableSchema(
        table_name="drug",
        columns={
            "disease_name": "string",
            "brand_name": "string",
            "generic_name": "string",
            "manufacturer": "string",
            "mechanism_of_action": "string",
            "storage_conditions": "string",
            "single_dose": "string",
            "recommended_usage": "string",
            "prescription_status": "string",
            "pharmaceutical_form": "string",
            "unsuitable_population": "string",
            "administration_route": "string",
            "indication": "string",
            "activation_conditions": "string",
        }
    )
    
    # Disease schema
    schemas['disease'] = TableSchema(
        table_name="disease",
        columns={
            "disease_name": "string",
            "diagnostic_methods": "string",
            "diagnosis_challenges": "string",
            "pathogenesis": "string",
            "treatments": "string",
            "epidemiology": "string",
            "preventive_measures": "string",
            "complications": "string",
            "etiology": "string",
            "sequelae": "string",
            "treatment_challenges": "string",
            "risk_factors": "string",
            "disease_type": "string",
            "prognosis": "string",
            "common_symptoms": "string",
            "quality_of_life_impact": "string",
        }
    )
    
    # Institution schema
    schemas['institution'] = TableSchema(
        table_name="institution",
        columns={
            "research_diseases": "string",
            "establishment_year": "string",
            "parent_organization": "string",
            "number_of_staff": "string",
            "key_technologies": "string",
            "institution_city": "string",
            "international_collaboration": "string",
            "key_achievements": "string",
            "institution_country": "string",
            "technology_application": "string",
            "institution_name": "string",
            "institution_type": "string",
        }
    )
    
    return schemas


def main():
    logger.info("=" * 70)
    logger.info("QAIRS Healthcare Test Pipeline")
    logger.info("=" * 70)
    
    # Configuration - use SQLite instead of PostgreSQL
    config = QAIRSConfig()
    config.ollama.model = "qwen2.5:0.5b"
    config.ollama.host = "http://localhost:11434"
    
    # Override database config for SQLite
    config.database.host = ""
    config.database.port = 0
    config.database.database = "qairs_test.db"
    config.database.user = ""
    config.database.password = ""
    
    config.extraction.enable_parallel = False  # Disable for small test
    config.extraction.max_workers = 1
    
    logger.info(f"Using LLM: {config.ollama.model}")
    
    # Step 1: Load corpus
    logger.info("\n[1/7] Loading corpus...")
    chunks = load_healthcare_corpus()
    
    if not chunks:
        logger.error("No chunks loaded!")
        return
    
    # Step 2: Load queries
    logger.info("\n[2/7] Loading queries...")
    sql_queries = load_join_queries()
    
    # Step 3: Create schemas
    logger.info("\n[3/7] Creating schemas...")
    schemas = create_healthcare_schemas()
    
    # Step 4: Initialize Sieve
    logger.info("\n[4/7] Building Sieve index...")
    sieve = Sieve(config)
    
    # Extract dictionary terms from schemas
    dict_terms = set()
    for schema in schemas.values():
        for col in schema.columns.keys():
            # Add column names as potential terms
            dict_terms.add(col.replace('_', ' '))
    
    logger.info(f"Dictionary terms: {len(dict_terms)}")
    sieve.build_dictionary(list(dict_terms)[:20], llm_client=None)  # Limit for speed
    sieve.build_index(chunks)
    
    # Step 5: Initialize LLM client
    logger.info("\n[5/7] Connecting to Ollama...")
    try:
        llm_client = OllamaClient(config)
        logger.info("✓ Connected to Ollama")
    except Exception as e:
        logger.error(f"Failed to connect to Ollama: {e}")
        logger.error("Make sure Ollama is running: ollama serve")
        logger.error(f"And model is pulled: ollama pull {config.ollama.model}")
        return
    
    # Step 6: Create database tables
    logger.info("\n[6/7] Creating database tables...")
    # Use SQLite for testing
    from sqlalchemy import create_engine, text
    
    # Use file-based SQLite so Registry can share the same database
    db_path = Path(__file__).parent / "qairs_test.db"
    if db_path.exists():
        db_path.unlink()  # Remove old test database
    
    conn_str = f"sqlite:///{db_path}"
    engine = create_engine(conn_str)
    
    for schema in schemas.values():
        cols = ", ".join([f"{col} TEXT" for col in schema.columns.keys()])
        create_sql = f"CREATE TABLE IF NOT EXISTS {schema.table_name} ({cols})"
        with engine.connect() as conn:
            conn.execute(text(create_sql))
            conn.commit()
        logger.info(f"✓ Created table: {schema.table_name}")
    
    # Create registry tables using the same connection string
    create_tables(conn_str)
    
    # Step 7: Test extraction with first query
    logger.info("\n[7/7] Testing extraction...")
    
    # Use first simple query
    test_query = sql_queries[0] if sql_queries else "SELECT * FROM drug"
    logger.info(f"Test query: {test_query[:100]}...")
    
    # Initialize components
    registry = Registry(config)
    extractor = Extractor(config, llm_client, max_workers=1)
    planner = WorkloadPlanner(config, sieve)
    
    # Parse query
    parser = SQLParser()
    pred = parser.parse_query(test_query, "Q1")
    
    if pred:
        logger.info(f"✓ Parsed query: table={pred.table}, conditions={len(pred.conditions)}")
        
        # Try extraction on one chunk
        from models import ExtractionTask, Predicate
        
        task = ExtractionTask(
            task_id="test_task",
            table_schema=schemas.get(pred.table, schemas['drug']),
            predicate=Predicate(table_name=pred.table, conditions=[pred.to_sql_where()]) if pred.conditions else None,
            candidate_chunks=list(chunks.keys())[:2],  # Just first 2 chunks
            dictionary_map=sieve.dictionary_map
        )
        
        logger.info(f"Extracting from {len(task.candidate_chunks)} chunks...")
        results = extractor.extract(task, chunks, parallel=False)
        
        total_rows = sum(len(r.data) for r in results if r.data)
        logger.info(f"✓ Extracted {total_rows} rows from {len(results)} chunks")
        
        # Show sample results
        for i, result in enumerate(results[:2]):
            if result.data:
                logger.info(f"  Chunk {i+1}: {len(result.data)} rows")
                if result.data:
                    logger.info(f"    Sample: {list(result.data[0].keys())[:5]}")
            elif result.error:
                logger.error(f"  Chunk {i+1}: Error - {result.error}")
    
    logger.info("\n" + "=" * 70)
    logger.info("✓ Pipeline test completed successfully!")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
