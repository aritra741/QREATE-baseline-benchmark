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
from typing import List, Dict

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "systems"))

from GEM.config import CACHE_DIR
from GEM.blocking import SemanticBlocker
from GEM.db_engine import DBEngine
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


def resolve_and_deduplicate_records(records: List[Dict], key_field: str, blocker, llm_client) -> tuple:
    """
    Run full GEM entity resolution on extracted records.
    
    Returns: (deduplicated_records, canonical_map)
    """
    if not records:
        return [], {}
    
    # Filter out incomplete records and split pipe-delimited key fields
    valid_records = []
    key_mentions = []
    for record in records:
        key = record.get(key_field, "")
        if key and str(key).strip() and str(key).strip() != "not specified in the text":
            key_str = str(key).strip()
            
            # Split pipe-delimited values (e.g., "disease1||disease2||disease3")
            # into separate mentions for proper entity resolution
            if "||" in key_str:
                parts = [p.strip() for p in key_str.split("||") if p.strip()]
                for part in parts:
                    key_mentions.append(part)
            else:
                key_mentions.append(key_str)
            
            valid_records.append(record)
    
    logger.info(f"Filtered {len(records)} records to {len(valid_records)} with valid key field")
    logger.info(f"Split pipe-delimited values: {len(records)} records → {len(key_mentions)} mentions")
    
    if not valid_records:
        return [], {}
    
    # PHASE 1: Semantic blocking (cluster similar mentions)
    logger.info(f"Phase 1: Semantic blocking on {len(key_mentions)} {key_field} mentions...")
    blocker.reset()  # Clear any previous state
    
    for mention in key_mentions:
        blocker.add_and_link(mention)
    
    blocks_dict = blocker.get_blocks()
    blocks = list(blocks_dict.values())  # Convert dict values to list of blocks
    logger.info(f"Semantic blocking produced {len(blocks)} blocks from {len(key_mentions)} mentions")
    
    # PHASE 2: LLM resolution (disambiguate within blocks)
    logger.info(f"Phase 2: LLM resolution on {len(blocks)} blocks...")
    canonical_map = {}  # mention -> canonical name
    
    for block in blocks:
        # Resolve this block with LLM
        resolved = llm_client.resolve_block(block)
        
        # resolved is {"Canonical Name": ["variant1", "variant2"], ...}
        for canonical, variants in resolved.items():
            for variant in variants:
                canonical_map[variant] = canonical
    
    logger.info(f"Built canonical map with {len(canonical_map)} mention -> canonical mappings")
    
    # PHASE 3: Normalize records using canonical map
    logger.info(f"Phase 3: Normalizing records with canonical map...")
    normalized_records = []
    for record in valid_records:
        record_copy = record.copy()
        key_value = str(record_copy.get(key_field, "")).strip()
        
        # Use canonical map to get canonical name
        canonical_key = canonical_map.get(key_value, key_value)
        record_copy[key_field] = canonical_key
        
        normalized_records.append(record_copy)
    
    # PHASE 4: Deduplicate and merge by canonical key
    logger.info(f"Phase 4: Deduplicating {len(normalized_records)} records by canonical {key_field}...")
    grouped = {}
    for record in normalized_records:
        key = str(record.get(key_field, "")).strip().lower()
        if key not in grouped:
            grouped[key] = record.copy()
        else:
            # Merge: keep non-empty fields from current record
            for field, value in record.items():
                if value and str(value).strip() and str(value).strip() != "not specified in the text":
                    if not grouped[key].get(field) or str(grouped[key].get(field)).strip() == "not specified in the text":
                        grouped[key][field] = value
    
    # Restore original casing for canonical key
    deduplicated = []
    for key, record in grouped.items():
        # Find original casing from any input record
        for original_record in normalized_records:
            if str(original_record.get(key_field, "")).strip().lower() == key:
                record[key_field] = original_record.get(key_field)
                break
        deduplicated.append(record)
    
    logger.info(f"Deduplicated {len(normalized_records)} records to {len(deduplicated)} unique entities")
    return deduplicated, canonical_map


def load_and_extract_data(data_dir: Path, extractor: EntityExtractor, blocker, llm_client, use_cache: bool = True, max_files: int = None) -> dict:
    """Extract entities from Healthcare dataset with full GEM resolution and caching."""
    cache_file = Path(CACHE_DIR) / "extracted_entities.json"
    
    # Try to load from cache
    if use_cache and cache_file.exists():
        logger.info(f"Loading extracted entities from cache: {cache_file}")
        with open(cache_file, 'r') as f:
            return json.load(f)
    
    data = {"drug": [], "disease": [], "institution": []}
    
    # Define all source directories (may contain mixed entity types)
    source_dirs = [
        data_dir / "drug_small",
        data_dir / "disease_small",
        data_dir / "institutes_small"
    ]
    
    key_fields = {
        "drug": "generic_name",
        "disease": "disease_name",
        "institution": "institution_name"
    }
    
    print("=" * 100)
    print("PHASE 1: ENTITY EXTRACTION & RESOLUTION FROM HEALTHCARE DATASET")
    print("=" * 100)
    print()
    
    # Extract ALL entity types from ALL source directories
    # (real-world data is not organized by entity type)
    all_extracted = {"drug": [], "disease": [], "institution": []}
    
    for source_dir in source_dirs:
        if not source_dir.exists():
            logger.warning(f"Directory not found: {source_dir}")
            continue
        
        logger.info(f"Processing files from {source_dir.name}...")
        
        # Get all text files
        text_files = sorted(source_dir.glob("*.txt"))
        if max_files:
            text_files = text_files[:max_files]
        
        logger.info(f"Found {len(text_files)} text files")
        
        for file_path in text_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                
                # Extract ALL entity types from this single file
                for entity_type in ["drug", "disease", "institution"]:
                    extracted = extractor.extract_from_text(text, entity_type)
                    if extracted:
                        all_extracted[entity_type].extend(extracted)
                        logger.debug(f"  {file_path.name}: extracted {len(extracted)} {entity_type} entities")
            
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                continue
    
    print()
    print("=" * 100)
    print("PHASE 2: GEM ENTITY RESOLUTION")
    print("=" * 100)
    print()
    
    # Now run GEM resolution on each entity type
    for entity_type in ["drug", "disease", "institution"]:
        records = all_extracted.get(entity_type, [])
        if not records:
            logger.warning(f"No {entity_type} records extracted")
            continue
        
        key_field = key_fields.get(entity_type)
        
        logger.info(f"Resolving {len(records)} raw {entity_type} records...")
        
        # Run full GEM resolution
        deduplicated, canonical_map = resolve_and_deduplicate_records(
            records, key_field, blocker, llm_client
        )
        
        data[entity_type].extend(deduplicated)
        print(f"✓ {len(deduplicated)} resolved {entity_type} records (from {len(records)} raw, canonical map: {len(canonical_map)} mappings)")
    
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


def preprocess_and_insert(data: dict, db_engine: DBEngine):
    """Insert preprocessed and resolved data into database."""
    
    print("=" * 100)
    print("PHASE 3: INSERTION INTO DATABASE")
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
        
        # Data is already resolved at extraction time, just insert
        db_engine.set_schema(None)
        db_engine.insert_records(entity_type, filtered_records)
        logger.info(f"Inserted {len(filtered_records)} {entity_type} records")
    
    print()


def load_queries(query_file: Path):
    """Load SQL queries from file."""
    if not query_file.exists():
        logger.error(f"Query file not found: {query_file}")
        return []
    
    with open(query_file, 'r') as f:
        content = f.read()
    
    # Parse queries - each query is preceded by a comment line starting with --
    queries = []
    lines = content.split('\n')
    current_comment = ""
    current_query = ""
    
    for line in lines:
        line_stripped = line.strip()
        
        if not line_stripped:
            continue
        
        if line_stripped.startswith('--'):
            # This is a comment line
            if current_query:
                # Save previous query
                queries.append({
                    'comment': current_comment,
                    'query': current_query.strip()
                })
            current_comment = line_stripped
            current_query = ""
        elif line_stripped.startswith('SELECT'):
            # Start of a SELECT query
            current_query = line_stripped
            if current_query.endswith(';'):
                # Query is complete on one line
                current_query = current_query[:-1]  # Remove trailing semicolon
                queries.append({
                    'comment': current_comment,
                    'query': current_query.strip()
                })
                current_query = ""
                current_comment = ""
        else:
            # Continuation of query
            if current_query:
                current_query += " " + line_stripped
                if current_query.endswith(';'):
                    # Query is complete
                    current_query = current_query[:-1]  # Remove trailing semicolon
                    queries.append({
                        'comment': current_comment,
                        'query': current_query.strip()
                    })
                    current_query = ""
                    current_comment = ""
    
    # Don't forget last query if exists
    if current_query:
        if current_query.endswith(';'):
            current_query = current_query[:-1]
        queries.append({
            'comment': current_comment,
            'query': current_query.strip()
        })
    
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
    
    llm_client = LLMClient()
    logger.info("✓ LLMClient initialized")
    
    extractor = EntityExtractor(schema=schema_dict)
    logger.info("✓ EntityExtractor initialized with schema guidance")
    
    print()
    
    # Extract (with caching and full GEM resolution)
    data = load_and_extract_data(data_dir, extractor, blocker, llm_client, use_cache=not args.no_cache, max_files=args.max_files)
    
    # Create DB
    db_engine = create_tables_and_db(schema_dict)
    
    # Preprocess and insert
    preprocess_and_insert(data, db_engine)
    
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
