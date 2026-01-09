#!/usr/bin/env python3
"""
Test GEM on Medical Dataset - Healthcare Join Queries

Workflow:
1. Load text files from source_data/Healthcare
2. Parse entities (drug, disease, institution)
3. Preprocess with GEM (entity resolution + canonicalization)
4. Load join queries from Query/Med/Join/join_queries.sql
5. Execute queries on canonicalized data
6. Report metrics
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "systems"))

from GEM.config import CACHE_DIR
from GEM.blocking import SemanticBlocker
from GEM.resolver import EntityResolver
from GEM.db_engine import DBEngine
from GEM.ingest import InlineDeduplicator
from GEM.schema_loader import SchemaLoader
from GEM.llm import LLMClient
from GEM.extractor import EntityExtractor


def get_medical_schema():
    """Get schema from Med_attributes.json."""
    schema_file = PROJECT_ROOT / "Query" / "Med" / "Med_attributes.json"
    
    if not schema_file.exists():
        logger.error(f"Schema file not found: {schema_file}")
        return None
    
    with open(schema_file, 'r') as f:
        schema_dict = json.load(f)
    
    loader = SchemaLoader()
    schema = loader._parse_schema(schema_dict)
    return schema


def load_healthcare_data(data_dir: Path, extractor: EntityExtractor) -> Dict[str, List[Dict[str, Any]]]:
    """Load healthcare text files and extract entities using LLM pipeline."""
    data = {"drug": [], "disease": [], "institution": []}
    
    # Define which files belong to which entity type
    entity_dirs = {
        "drug": data_dir / "drug_small",
        "disease": data_dir / "disease_small",
        "institutes_small": data_dir / "institutes_small"
    }
    
    print("=" * 100)
    print("LOADING AND EXTRACTING HEALTHCARE DATA")
    print("=" * 100)
    print()
    
    for entity_type, entity_dir in entity_dirs.items():
        if not entity_dir.exists():
            logger.warning(f"Directory not found: {entity_dir}")
            continue
        
        # Map institution to disease in data structure
        entity_key = "institution" if entity_type == "institutes_small" else entity_type
        
        # Use LLM extractor to process directory
        logger.info(f"Extracting {entity_key} entities from {entity_dir}...")
        extracted = extractor.extract_from_directory(entity_dir, entity_key, max_files=5)
        
        data[entity_key].extend(extracted)
        print(f"Extracted {len(extracted)} {entity_key} records")
    
    print()
    return data


def create_tables(db_engine: DBEngine, schema_dict: Dict):
    """Create database tables for each entity type."""
    loader = SchemaLoader()
    
    for table_name in ["drug", "disease", "institution"]:
        if table_name not in schema_dict:
            logger.warning(f"Schema missing for table: {table_name}")
            continue
        
        table_schema_dict = {table_name: schema_dict[table_name]}
        table_schema = loader._parse_schema(table_schema_dict)
        db_engine.set_schema(table_schema)
        db_engine.create_table(table_name, table_schema)
        logger.info(f"Created table: {table_name}")
    
    db_engine.schema = None


def preprocess_with_gem(data: Dict[str, List[Dict]], db_engine: DBEngine, 
                        blocker: SemanticBlocker, resolver: EntityResolver) -> Dict[str, Dict]:
    """
    Preprocess data with GEM.
    
    For each entity type, extract key field (name), resolve synonyms,
    then insert into database.
    """
    print("=" * 100)
    print("PREPROCESSING WITH GEM")
    print("=" * 100)
    print()
    
    canonical_maps = {}
    
    for entity_type in ["drug", "disease", "institution"]:
        records = data.get(entity_type, [])
        if not records:
            logger.warning(f"No {entity_type} records to process")
            continue
        
        logger.info(f"\nProcessing {len(records)} {entity_type} records...")
        
        # Determine key field based on entity type
        key_fields = {
            "drug": ["generic_name", "brand_name"],
            "disease": ["disease_name"],
            "institution": ["institution_name"]
        }
        
        key_field = key_fields.get(entity_type, ["name"])[0]
        
        # Extract mentions for entity resolution
        mentions = []
        for record in records:
            mention = record.get(key_field, "")
            if mention:
                mentions.append(mention)
        
        logger.info(f"Extracted {len(mentions)} mentions for {entity_type}")
        
        if not mentions:
            logger.warning(f"No mentions extracted for {entity_type}")
            continue
        
        # Resolve synonyms using HNSW-Union-Find + LLM
        dummy_records = [{"name": mention} for mention in mentions]
        deduplicator = InlineDeduplicator(blocker, resolver, db_engine, None, logger=logger)
        final_records, canonical_map = deduplicator.ingest_batch(dummy_records, ["name"])
        canonical_maps[entity_type] = canonical_map
        
        logger.info(f"Built canonical map with {len(canonical_map)} mappings for {entity_type}")
        
        # Normalize records to use canonical names
        normalized_records = []
        for record in records:
            norm_record = record.copy()
            mention = record.get(key_field, "")
            canonical = canonical_map.get(mention, mention)
            norm_record[key_field] = canonical
            normalized_records.append(norm_record)
        
        # Insert into database
        db_engine.set_schema(None)  # Clear schema temporarily
        db_engine.insert_records(entity_type, normalized_records)
        logger.info(f"Inserted {len(normalized_records)} {entity_type} records into database")
    
    return canonical_maps


def load_queries(query_file: Path) -> List[str]:
    """Load SQL queries from file."""
    if not query_file.exists():
        logger.error(f"Query file not found: {query_file}")
        return []
    
    with open(query_file, 'r') as f:
        content = f.read()
    
    # Parse queries (each query is a comment + SELECT statement)
    queries = []
    current_query = ""
    
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('--'):
            if line.startswith('--'):
                if current_query:
                    queries.append(current_query.strip())
                current_query = ""
            continue
        
        if line.startswith('SELECT'):
            current_query = line + " "
        elif current_query:
            current_query += line + " "
    
    if current_query:
        queries.append(current_query.strip())
    
    logger.info(f"Loaded {len(queries)} queries")
    return queries


def execute_queries(db_engine: DBEngine, queries: List[str]) -> Dict[int, Any]:
    """Execute queries and collect results."""
    print("=" * 100)
    print("EXECUTING QUERIES")
    print("=" * 100)
    print()
    
    results = {}
    
    for i, query in enumerate(queries, 1):
        try:
            logger.info(f"Query {i}: {query[:80]}...")
            result_df = db_engine.execute_query(query)
            
            if result_df is not None:
                results[i] = {
                    "success": True,
                    "row_count": len(result_df),
                    "columns": result_df.columns.tolist(),
                    "sample": result_df.head(2).to_dict('records') if len(result_df) > 0 else []
                }
                logger.info(f"  ✓ Query {i}: {len(result_df)} rows")
            else:
                results[i] = {"success": False, "error": "Query returned None"}
                logger.warning(f"  ✗ Query {i}: No results")
        
        except Exception as e:
            results[i] = {"success": False, "error": str(e)}
            logger.error(f"  ✗ Query {i}: {e}")
    
    return results


def main():
    """Main test workflow."""
    print("\n")
    print("=" * 100)
    print("TEST: GEM on Medical Dataset with Join Queries")
    print("=" * 100)
    print()
    
    # Setup paths
    data_dir = PROJECT_ROOT / "source_data" / "Healthcare"
    query_file = PROJECT_ROOT / "Query" / "Med" / "Join" / "join_queries.sql"
    
    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        sys.exit(1)
    
    # Clear cache
    cache_dir = Path(CACHE_DIR)
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize components
    print("=" * 100)
    print("INITIALIZATION")
    print("=" * 100)
    print()
    
    blocker = SemanticBlocker(blocking_threshold=0.85)
    logger.info("✓ SemanticBlocker initialized")
    
    resolver = EntityResolver()
    logger.info("✓ EntityResolver initialized")
    
    llm_client = LLMClient()
    logger.info("✓ LLMClient initialized")
    
    extractor = EntityExtractor()
    logger.info("✓ EntityExtractor initialized")
    
    # Load data with LLM extraction
    data = load_healthcare_data(data_dir, extractor)
    print()
    
    db_engine = DBEngine()
    logger.info("✓ DBEngine initialized")
    
    schema_dict = get_medical_schema()
    if schema_dict is None:
        logger.error("Failed to load schema")
        sys.exit(1)
    
    # Extract just the schema dictionaries (not the Schema object)
    with open(PROJECT_ROOT / "Query" / "Med" / "Med_attributes.json", 'r') as f:
        schema_dict = json.load(f)
    
    create_tables(db_engine, schema_dict)
    print()
    
    # Preprocess with GEM
    canonical_maps = preprocess_with_gem(data, db_engine, blocker, resolver)
    print()
    
    # Load and execute queries
    queries = load_queries(query_file)
    results = execute_queries(db_engine, queries)
    print()
    
    # Report metrics
    print("=" * 100)
    print("RESULTS SUMMARY")
    print("=" * 100)
    print()
    
    successful = sum(1 for r in results.values() if r.get("success"))
    total = len(results)
    
    print(f"Total queries: {total}")
    print(f"Successful: {successful}")
    print(f"Failed: {total - successful}")
    print(f"Success rate: {successful/total*100:.1f}%" if total > 0 else "N/A")
    print()
    
    # Show sample results
    if results:
        print("Sample Query Results:")
        for query_id in list(results.keys())[:3]:
            result = results[query_id]
            if result.get("success"):
                print(f"\n  Query {query_id}: {result['row_count']} rows")
                if result.get('sample'):
                    print(f"    Sample: {result['sample'][0]}")
            else:
                print(f"\n  Query {query_id}: FAILED - {result.get('error')}")
    print()
    
    # Cleanup
    db_engine.close()
    logger.info("✓ Test completed")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
