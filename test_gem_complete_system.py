#!/usr/bin/env python3
"""
Complete GEM System Test - Full Pipeline with Semantic Shim

Tests the entire system:
1. Extract entities from Healthcare dataset
2. Resolve with GEM (HNSW-Union-Find + LLM)
3. Store in multi-table database
4. Execute JOINs with semantic shim rewriting
5. Report metrics
"""

import json
import logging
import sys
from pathlib import Path

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
    """Load schema from Med_attributes.json."""
    schema_file = PROJECT_ROOT / "Query" / "Med" / "Med_attributes.json"
    
    if not schema_file.exists():
        logger.error(f"Schema file not found: {schema_file}")
        return None
    
    with open(schema_file, 'r') as f:
        schema_dict = json.load(f)
    
    return schema_dict


def load_and_extract_data(data_dir: Path, extractor: EntityExtractor, use_cache: bool = True, max_files: int = None) -> dict:
    """Extract entities from Healthcare dataset with caching."""
    cache_file = Path(CACHE_DIR) / "extracted_entities.json"
    
    # Try to load from cache
    if use_cache and cache_file.exists():
        logger.info(f"Loading extracted entities from cache: {cache_file}")
        with open(cache_file, 'r') as f:
            return json.load(f)
    
    data = {"drug": [], "disease": [], "institution": []}
    
    entity_dirs = {
        "drug": data_dir / "drug_small",
        "disease": data_dir / "disease_small",
        "institutes_small": data_dir / "institutes_small"
    }
    
    print("=" * 100)
    print("PHASE 1: ENTITY EXTRACTION FROM HEALTHCARE DATASET")
    print("=" * 100)
    print()
    
    for entity_type, entity_dir in entity_dirs.items():
        if not entity_dir.exists():
            logger.warning(f"Directory not found: {entity_dir}")
            continue
        
        entity_key = "institution" if entity_type == "institutes_small" else entity_type
        
        logger.info(f"Extracting {entity_key} entities from {entity_dir}...")
        extracted = extractor.extract_from_directory(entity_dir, entity_key, max_files=max_files)
        
        data[entity_key].extend(extracted)
        print(f"Extracted {len(extracted)} {entity_key} records")
    
    # Cache results
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, 'w') as f:
        json.dump(data, f, indent=2)
    logger.info(f"Cached extraction results to {cache_file}")
    
    print()
    return data


def create_tables_and_db(schema_dict: dict) -> DBEngine:
    """Create database and tables."""
    loader = SchemaLoader()
    db_engine = DBEngine()
    
    print("=" * 100)
    print("PHASE 2: DATABASE INITIALIZATION")
    print("=" * 100)
    print()
    
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
    print()
    return db_engine


def preprocess_and_insert(data: dict, db_engine: DBEngine, 
                          blocker: SemanticBlocker, resolver: EntityResolver):
    """Preprocess with GEM and insert into database."""
    
    print("=" * 100)
    print("PHASE 3: GEM PREPROCESSING & INSERTION")
    print("=" * 100)
    print()
    
    for entity_type in ["drug", "disease", "institution"]:
        records = data.get(entity_type, [])
        if not records:
            logger.warning(f"No {entity_type} records to process")
            continue
        
        # Filter empty records
        filtered_records = []
        for record in records:
            non_empty = sum(1 for v in record.values() if v and str(v).strip())
            if non_empty > 0:
                filtered_records.append(record)
        
        logger.info(f"Processing {len(filtered_records)}/{len(records)} {entity_type} records")
        
        if not filtered_records:
            continue
        
        # Extract key field
        key_fields = {
            "drug": "generic_name",
            "disease": "disease_name",
            "institution": "institution_name"
        }
        
        key_field = key_fields.get(entity_type)
        
        # Get unique mentions
        mentions = set()
        for record in filtered_records:
            mention = record.get(key_field, "")
            if mention and str(mention).strip():
                mentions.add(str(mention).strip())
        
        mentions = list(mentions)
        logger.info(f"Found {len(mentions)} unique mentions for {entity_type}")
        
        if not mentions:
            continue
        
        # Resolve with GEM
        dummy_records = [{"name": m} for m in mentions]
        deduplicator = InlineDeduplicator(blocker, resolver, db_engine, None, logger=logger)
        final_records, canonical_map = deduplicator.ingest_batch(dummy_records, ["name"])
        
        logger.info(f"Canonical map: {len(canonical_map)} mention->canonical mappings")
        
        # Normalize and insert
        normalized_records = []
        for record in filtered_records:
            norm_record = record.copy()
            mention = record.get(key_field, "")
            if mention:
                canonical = canonical_map.get(str(mention).strip(), str(mention).strip())
                norm_record[key_field] = canonical
            normalized_records.append(norm_record)
        
        db_engine.set_schema(None)
        db_engine.insert_records(entity_type, normalized_records)
        logger.info(f"Inserted {len(normalized_records)} {entity_type} records")
    
    print()


def load_queries(query_file: Path):
    """Load SQL queries from file."""
    if not query_file.exists():
        logger.error(f"Query file not found: {query_file}")
        return []
    
    with open(query_file, 'r') as f:
        content = f.read()
    
    # Parse queries (each query is a comment + SELECT statement)
    queries = []
    current_query = ""
    current_comment = ""
    
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        if line.startswith('--'):
            current_comment = line
            continue
        
        if line.startswith('SELECT'):
            current_query = line + " "
        elif current_query:
            current_query += line + " "
            if line.endswith(';'):
                queries.append({
                    'comment': current_comment,
                    'query': current_query.strip()
                })
                current_query = ""
                current_comment = ""
    
    logger.info(f"Loaded {len(queries)} queries from {query_file}")
    return queries


def execute_join_queries(db_engine: DBEngine, query_file: Path):
    """Execute join queries from SQL file."""
    
    print("=" * 100)
    print("PHASE 4: EXECUTE JOIN QUERIES WITH SEMANTIC SHIM")
    print("=" * 100)
    print()
    
    queries = load_queries(query_file)
    
    if not queries:
        logger.warning("No queries loaded")
        return {}
    
    results = {}
    successful = 0
    failed = 0
    
    for i, q in enumerate(queries, 1):
        try:
            logger.info(f"Query {i}: {q['comment']}")
            result_df = db_engine.execute_query(q['query'])
            
            if result_df is not None:
                row_count = len(result_df)
                results[i] = {
                    "success": True,
                    "rows": row_count,
                    "query": q['comment']
                }
                logger.info(f"  ✓ {row_count} rows")
                successful += 1
            else:
                results[i] = {"success": False, "error": "No results", "query": q['comment']}
                failed += 1
        
        except Exception as e:
            results[i] = {"success": False, "error": str(e), "query": q['comment']}
            logger.error(f"  ✗ Query {i} failed: {e}")
            failed += 1
    
    print()
    print(f"Executed {len(queries)} queries: {successful} successful, {failed} failed")
    print()
    
    return results


def main():
    """Main test flow."""
    import argparse
    
    parser = argparse.ArgumentParser(description="GEM Complete System Test")
    parser.add_argument("--no-cache", action="store_true", help="Disable extraction caching")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache before running")
    parser.add_argument("--max-files", type=int, default=None, help="Maximum files to process per entity type (None = all)")
    args = parser.parse_args()
    
    print("\n")
    print("=" * 100)
    print("GEM COMPLETE SYSTEM TEST - Full Pipeline with Semantic Shim")
    print("=" * 100)
    print()
    
    # Setup
    data_dir = PROJECT_ROOT / "source_data" / "Healthcare"
    query_file = PROJECT_ROOT / "Query" / "Med" / "Join" / "join_queries.sql"
    
    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        sys.exit(1)
    
    if not query_file.exists():
        logger.error(f"Query file not found: {query_file}")
        sys.exit(1)
    
    # Clear cache if requested
    cache_dir = Path(CACHE_DIR)
    if args.clear_cache and cache_dir.exists():
        import shutil
        logger.info(f"Clearing cache: {cache_dir}")
        shutil.rmtree(cache_dir)
    
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Load schema
    schema_dict = get_medical_schema()
    if not schema_dict:
        sys.exit(1)
    
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
    
    print()
    
    # Extract (with caching)
    data = load_and_extract_data(data_dir, extractor, use_cache=not args.no_cache, max_files=args.max_files)
    
    # Create DB
    db_engine = create_tables_and_db(schema_dict)
    
    # Preprocess and insert
    preprocess_and_insert(data, db_engine, blocker, resolver)
    
    # Execute queries
    results = execute_join_queries(db_engine, query_file)
    
    # Summary
    print("=" * 100)
    print("TEST SUMMARY")
    print("=" * 100)
    print()
    
    successful = sum(1 for r in results.values() if r.get("success"))
    total = len(results)
    
    print(f"Queries executed: {total}")
    print(f"Successful: {successful}")
    print(f"Failed: {total - successful}")
    if total > 0:
        print(f"Success rate: {successful/total*100:.1f}%")
    print()
    
    for query_id, result in sorted(results.items()):
        if result.get("success"):
            print(f"  ✓ Query {query_id}: {result.get('rows', 0)} rows - {result.get('query', '')}")
        else:
            print(f"  ✗ Query {query_id}: {result.get('error', 'Unknown error')}")
    
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
