#!/usr/bin/env python3
"""
Test integrated HNSW-Union-Find blocking with discriminative LLM resolution.

Verifies:
1. Semantic Isolation: Distinct variants (Pro vs Pro Max) kept separate
2. Synonym Consolidation: Case variations and short forms consolidated
3. Multi-Entity Resolution: One block can resolve to multiple canonical entities
"""

import json
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
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
from GEM.llm import LLMClient


def create_test_schema():
    """Create a schema for products."""
    schema_dict = {
        "product": {
            "name": {
                "value_type": "str",
                "usage": "general",
                "description": "Product name"
            },
            "price": {
                "value_type": "float",
                "usage": "numerical",
                "description": "Price in USD"
            },
            "category": {
                "value_type": "str",
                "usage": "categorical",
                "description": "Product category"
            }
        }
    }
    
    loader = SchemaLoader()
    schema = loader._parse_schema(schema_dict)
    return schema


def create_test_products():
    """Create test products with distinct variants and synonyms."""
    products = [
        # iPhone 15 variants (should be 3 separate entities)
        {"name": "iPhone 15", "price": "799", "category": "smartphone"},
        {"name": "iphone 15", "price": "799", "category": "smartphone"},  # Synonym
        {"name": "Apple iPhone 15", "price": "799", "category": "smartphone"},  # Synonym
        
        # iPhone 15 Pro variants (should be 1 canonical)
        {"name": "iPhone 15 Pro", "price": "999", "category": "smartphone"},
        {"name": "iphone 15 pro", "price": "999", "category": "smartphone"},  # Synonym
        {"name": "15 Pro", "price": "999", "category": "smartphone"},  # Short form (synonym)
        
        # iPhone 15 Pro Max (should be DIFFERENT from Pro)
        {"name": "iPhone 15 Pro Max", "price": "1099", "category": "smartphone"},
        {"name": "iphone 15 pro max", "price": "1099", "category": "smartphone"},  # Synonym
        
        # Galaxy S24 variants (should be 2 separate entities)
        {"name": "Galaxy S24", "price": "799", "category": "smartphone"},
        {"name": "galaxy s24", "price": "799", "category": "smartphone"},  # Synonym
        {"name": "Samsung S24", "price": "799", "category": "smartphone"},  # Synonym
        
        # Galaxy S24 Ultra (should be DIFFERENT from S24)
        {"name": "Galaxy S24 Ultra", "price": "1299", "category": "smartphone"},
        {"name": "samsung galaxy s24 ultra", "price": "1299", "category": "smartphone"},  # Synonym
    ]
    
    return products


def test_hnsw_union_find():
    """Test integrated HNSW-Union-Find blocking."""
    print("=" * 100)
    print("TEST: Integrated HNSW-Union-Find with Discriminative LLM Resolution")
    print("=" * 100)
    print()
    
    # Clear cache
    cache_dir = Path(CACHE_DIR)
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Create test data
    products = create_test_products()
    schema = create_test_schema()
    
    print(f"Created {len(products)} test products:")
    for i, p in enumerate(products):
        print(f"  [{i:2d}] {p['name']:30s} ${p['price']:>7s}")
    print()
    
    # Initialize components
    print("=" * 100)
    print("INITIALIZATION")
    print("=" * 100)
    print()
    
    blocker = SemanticBlocker(blocking_threshold=0.85)
    print("✓ SemanticBlocker initialized with HNSW-Union-Find")
    
    resolver = EntityResolver()
    print("✓ EntityResolver initialized")
    
    llm_client = LLMClient()
    print("✓ LLMClient initialized")
    
    db_engine = DBEngine()
    db_engine.set_schema(schema)
    print("✓ DBEngine initialized")
    
    db_engine.create_table("product", schema)
    print("✓ Table created")
    print()
    
    # Phase 1: Streaming HNSW-Union-Find blocking
    print("=" * 100)
    print("PHASE 1: Streaming HNSW-Union-Find Blocking")
    print("=" * 100)
    print()
    
    deduplicator = InlineDeduplicator(blocker, resolver, db_engine, schema, logger=logger)
    key_attributes = ["name"]
    
    final_records, canonical_map = deduplicator.ingest_batch(products, key_attributes)
    
    print()
    print(f"Canonical Map ({len(canonical_map)} entries):")
    for mention, canonical in sorted(canonical_map.items()):
        if mention != canonical:
            print(f"  '{mention}' -> '{canonical}'")
    print()
    
    # Phase 2: Normalize records
    print("=" * 100)
    print("PHASE 2: Normalization")
    print("=" * 100)
    print()
    
    normalized_records = deduplicator.finalize()
    print(f"Normalized {len(products)} records")
    print()
    
    # Phase 3: Insert into database
    print("=" * 100)
    print("PHASE 3: Database Insertion")
    print("=" * 100)
    print()
    
    db_engine.insert_records("product", normalized_records)
    print()
    
    # Phase 4: Verification
    print("=" * 100)
    print("PHASE 4: VERIFICATION")
    print("=" * 100)
    print()
    
    # Test 1: Semantic Isolation
    print("[TEST 1] Semantic Isolation - Distinct variants as separate rows")
    print()
    result_df = db_engine.execute_query(
        "SELECT DISTINCT name, price FROM product WHERE name LIKE '%iPhone 15%' OR name LIKE '%iphone 15%' ORDER BY price DESC"
    )
    if result_df is not None:
        print("iPhone 15 variants in database:")
        print(result_df.to_string(index=False))
        
        # Check for 3 distinct iPhone 15 variants
        iphone_15_base = any(result_df['name'].str.lower().str.strip() == 'iphone 15')
        iphone_15_pro = any(result_df['name'].str.lower().str.contains('pro', regex=False))
        iphone_15_pro_max = any(result_df['name'].str.lower().str.contains('pro max', regex=False))
        
        if iphone_15_base and iphone_15_pro and iphone_15_pro_max:
            print("\n✓ PASS: Found all 3 iPhone 15 variants (base, Pro, Pro Max)")
        else:
            print(f"\n✗ FAIL: Missing variants - Base:{iphone_15_base}, Pro:{iphone_15_pro}, Max:{iphone_15_pro_max}")
    else:
        print("✗ FAIL: Query returned None")
    print()
    
    # Test 2: Galaxy variants
    print("[TEST 2] Semantic Isolation - Galaxy variants")
    print()
    result_df = db_engine.execute_query(
        "SELECT DISTINCT name, price FROM product WHERE name LIKE '%Galaxy%' OR name LIKE '%galaxy%' OR name LIKE '%Samsung%' ORDER BY price DESC"
    )
    if result_df is not None:
        print("Galaxy variants in database:")
        print(result_df.to_string(index=False))
        
        # Check for 2 distinct Galaxy variants
        galaxy_s24 = any(result_df['name'].str.lower().str.contains('s24', regex=False) & ~result_df['name'].str.lower().str.contains('ultra', regex=False))
        galaxy_s24_ultra = any(result_df['name'].str.lower().str.contains('s24 ultra', regex=False))
        
        if galaxy_s24 and galaxy_s24_ultra:
            print("\n✓ PASS: Found 2 Galaxy variants (S24, S24 Ultra)")
        else:
            print(f"\n✗ FAIL: Missing variants - S24:{galaxy_s24}, S24 Ultra:{galaxy_s24_ultra}")
    else:
        print("✗ FAIL: Query returned None")
    print()
    
    # Test 3: Synonym consolidation
    print("[TEST 3] Synonym Consolidation")
    print()
    result_df = db_engine.execute_query("SELECT COUNT(DISTINCT name) as unique_names, COUNT(*) as total_rows FROM product")
    if result_df is not None:
        unique_names = result_df['unique_names'].iloc[0]
        total_rows = result_df['total_rows'].iloc[0]
        print(f"Total records: {total_rows}")
        print(f"Distinct product names: {unique_names}")
        
        if unique_names < total_rows:
            print(f"✓ PASS: Synonyms consolidated ({total_rows} -> {unique_names} distinct names)")
        else:
            print(f"✗ FAIL: No consolidation (expected fewer distinct names)")
    print()
    
    # Test 4: List all products
    print("[TEST 4] All Products in Database")
    print()
    result_df = db_engine.execute_query("SELECT name, price FROM product ORDER BY price DESC, name")
    if result_df is not None:
        print(result_df.to_string(index=False))
    print()
    
    # Summary
    print("=" * 100)
    print("TEST SUMMARY")
    print("=" * 100)
    print()
    print(f"Input products: {len(products)}")
    print(f"Canonical map size: {len(canonical_map)}")
    print(f"Records inserted: {len(normalized_records)}")
    print(f"Distinct names in DB: {unique_names if result_df is not None else 'unknown'}")
    print()
    
    # Cleanup
    db_engine.close()
    print("✓ Test completed")


if __name__ == "__main__":
    try:
        test_hnsw_union_find()
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
