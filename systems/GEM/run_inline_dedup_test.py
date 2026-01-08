#!/usr/bin/env python3
"""
Test synthetic data with inline deduplication and type cleaning.

Verifies:
1. Distinct variants (e.g., "Pro" vs "Pro Max") are kept separate
2. Numeric comparisons work without VARCHAR errors
3. Inline deduplication reduces duplicate records
4. LLM discriminative resolution prevents over-merging
"""

import json
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "systems"))

from GEM.config import CACHE_DIR
from GEM.blocking import SemanticBlocker
from GEM.resolver import EntityResolver
from GEM.db_engine import DBEngine
from GEM.ingest import InlineDeduplicator
from GEM.schema_loader import SchemaLoader


def create_synthetic_data():
    """Create synthetic product data with distinct variants."""
    products = [
        {"product_name": "iPhone 15 Pro", "price": "$999", "storage": "128GB"},
        {"product_name": "iPhone 15 Pro", "price": "$999", "storage": "128GB"},  # Exact duplicate
        {"product_name": "iphone 15 pro", "price": "999", "storage": "128GB"},  # Synonym (case/format variation)
        {"product_name": "iPhone 15 Pro Max", "price": "$1099", "storage": "128GB"},  # Different variant (should NOT merge)
        {"product_name": "iPhone 15 Pro Max", "price": "$1099", "storage": "256GB"},  # Different capacity (should NOT merge)
        {"product_name": "iPhone 15", "price": "$799", "storage": "128GB"},  # Different product
    ]
    return products


def create_test_schema():
    """Create a schema for products."""
    schema_dict = {
        "product": {
            "product_name": {
                "value_type": "str",
                "usage": "general",
                "description": "Name of the product (e.g., iPhone 15 Pro)"
            },
            "price": {
                "value_type": "float",
                "usage": "numerical",
                "description": "Price in USD"
            },
            "storage": {
                "value_type": "str",
                "usage": "categorical",
                "description": "Storage capacity (e.g., 128GB, 256GB)"
            }
        }
    }
    
    loader = SchemaLoader()
    schema = loader._parse_schema(schema_dict)
    return schema


def test_inline_deduplication():
    """Test the inline deduplication pipeline."""
    print("=" * 100)
    print("TEST: Inline Deduplication with Type Cleaning")
    print("=" * 100)
    print()
    
    # Clear cache
    cache_dir = Path(CACHE_DIR)
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Create test data
    products = create_synthetic_data()
    schema = create_test_schema()
    
    print(f"Created {len(products)} synthetic products:")
    for i, p in enumerate(products):
        print(f"  [{i}] {p['product_name']:25s} ${p['price']:>7s} {p['storage']:>6s}")
    print()
    
    # Initialize components
    print("Initializing components...")
    blocker = SemanticBlocker()
    blocker.load_embedding_model()
    print("✓ SemanticBlocker initialized")
    
    resolver = EntityResolver()
    print("✓ EntityResolver initialized")
    
    db_engine = DBEngine()
    db_engine.set_schema(schema)
    print("✓ DBEngine initialized")
    
    db_engine.create_table("product", schema)
    print("✓ Table created")
    print()
    
    # Inline deduplication
    print("=" * 100)
    print("INGESTION: Inline Deduplication")
    print("=" * 100)
    print()
    
    deduplicator = InlineDeduplicator(blocker, resolver, db_engine, schema, logger=logger)
    key_attributes = ["product_name"]
    
    deduplicated_records, component_map = deduplicator.ingest_batch(products, key_attributes)
    
    print()
    print("=" * 100)
    print(f"RESULTS: {len(products)} -> {len(deduplicated_records)} records after deduplication")
    print("=" * 100)
    print()
    
    # Finalize with LLM resolution
    print("Finalizing with LLM resolution...")
    final_records = deduplicator.finalize()
    print(f"After LLM resolution: {len(final_records)} records")
    print()
    
    # Insert into database
    print("Inserting records into SQLite...")
    db_engine.insert_records("product", final_records)
    print()
    
    # Query database
    print("=" * 100)
    print("DATABASE VERIFICATION")
    print("=" * 100)
    print()
    
    # Test 1: Verify distinct variants are separate
    print("[TEST 1] Verify distinct variants are separate:")
    result_df = db_engine.execute_query("SELECT product_name, price, COUNT(*) as count FROM product GROUP BY product_name, price")
    if result_df is not None:
        print(result_df.to_string(index=False))
        
        # Check that Pro and Pro Max are different
        pro_count = len(result_df[result_df['product_name'].str.contains('Pro', case=False, regex=False)])
        pro_max_count = len(result_df[result_df['product_name'].str.contains('Pro Max', case=False, regex=False)])
        
        if pro_count > 0 and pro_max_count > 0:
            print("✓ PASS: Found both 'Pro' and 'Pro Max' as separate records")
        else:
            print("✗ FAIL: Pro and Pro Max not properly separated")
    else:
        print("✗ FAIL: Could not execute query")
    print()
    
    # Test 2: Verify numeric comparison works
    print("[TEST 2] Verify numeric comparison works (WHERE price > 1000):")
    try:
        result_df = db_engine.execute_query("SELECT product_name, price FROM product WHERE price > 1000")
        if result_df is not None:
            print(result_df.to_string(index=False))
            print("✓ PASS: Numeric comparison works without type errors")
        else:
            print("✗ FAIL: Query returned None")
    except Exception as e:
        print(f"✗ FAIL: {e}")
    print()
    
    # Test 3: Verify deduplication of exact duplicates
    print("[TEST 3] Verify deduplication of exact duplicates:")
    result_df = db_engine.execute_query("SELECT COUNT(*) as total FROM product")
    if result_df is not None:
        total = result_df['total'].iloc[0]
        print(f"Total records in database: {total}")
        print(f"Original records: {len(products)}")
        if total < len(products):
            print(f"✓ PASS: Deduplication reduced records from {len(products)} to {total}")
        else:
            print(f"✗ FAIL: Expected fewer records after deduplication")
    print()
    
    # Summary
    print("=" * 100)
    print("TEST SUMMARY")
    print("=" * 100)
    print()
    print(f"Input: {len(products)} records")
    print(f"After inline dedup: {len(deduplicated_records)} records")
    print(f"After LLM resolution: {len(final_records)} records")
    print(f"In database: {result_df['total'].iloc[0] if result_df is not None else 'unknown'} records")
    print()
    
    # Cleanup
    db_engine.close()
    print("✓ Test completed")


if __name__ == "__main__":
    try:
        test_inline_deduplication()
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
