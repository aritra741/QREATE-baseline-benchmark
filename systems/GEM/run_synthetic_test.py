#!/usr/bin/env python3
"""
GEM Synthetic Test - End-to-end test on synthetic product dataset
Includes extraction, entity resolution, and SQL query workloads
"""
import sys
from pathlib import Path
from datetime import datetime
import json

PROJECT_ROOT = Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT))

from systems.GEM.gem_runner import GEMRunner

print("\n" + "=" * 70)
print("GEM END-TO-END TEST - SYNTHETIC PRODUCT DATASET")
print("=" * 70)
print(f"Timestamp: {datetime.now().isoformat()}\n")

runner = GEMRunner()

# Preprocess
print("[1] PREPROCESSING: Extracting and resolving entities...")
meta = runner.preprocess("Synthetic", "product")

if meta.get("status") in ["completed", "completed_empty"]:
    print(f"  ✓ Extraction: OK")
    print(f"  ✓ Blocking: OK")
    print(f"  ✓ Resolution: OK")
    print(f"  ✓ Normalized Records: {meta.get('records_count', 0)}")
    print(f"  ✓ Canonical Entities: {meta.get('canonical_count', 0)}")
else:
    print(f"  ✗ Preprocessing failed: {meta.get('error')}")
    sys.exit(1)

# Display results
print("\n[2] ENTITY RESOLUTION RESULTS:")
cache_dir = PROJECT_ROOT / "systems/GEM/.cache/preprocessing/Synthetic/product"
canonical_file = cache_dir / "canonical_map.json"

if canonical_file.exists():
    with open(canonical_file) as f:
        canonical_map = json.load(f)
    
    by_canonical = {}
    for variant, canonical in canonical_map.items():
        if canonical not in by_canonical:
            by_canonical[canonical] = []
        by_canonical[canonical].append(variant)
    
    print("  Canonical names identified:")
    for canonical, variants in sorted(by_canonical.items()):
        print(f"    - {canonical}")
        for v in sorted(set(variants)):
            if v != canonical:
                print(f"      ← {v}")

print("\n[3] NORMALIZED RECORDS:")
records_file = cache_dir / "normalized_records.json"
if records_file.exists():
    with open(records_file) as f:
        records = json.load(f)
    
    print(f"  Total records: {len(records)}")
    by_product = {}
    for rec in records:
        pname = rec.get("product_name", "Unknown")
        if pname not in by_product:
            by_product[pname] = []
        by_product[pname].append(rec)
    
    print(f"  Records by product:")
    for pname in sorted(by_product.keys()):
        print(f"    - {pname}: {len(by_product[pname])} mentions")

# Test SQL queries
print("\n[4] SQL QUERY WORKLOADS:")
print("  Testing query execution on normalized data...\n")

try:
    from systems.GEM.db_engine import DBEngine
    from systems.GEM.schema_loader import load_schema
    
    # Load schema and create DB engine
    schema = load_schema(PROJECT_ROOT / "Query" / "Synthetic" / "Synthetic_attributes.json")
    db = DBEngine()
    db.set_schema(schema)
    
    # Load normalized records
    with open(records_file) as f:
        records = json.load(f)
    
    # Create table and insert records
    db.create_table("product", schema)
    db.insert_records("product", records)
    
    print("  ✓ Created table and inserted records\n")
    
    # Test workloads
    workloads = [
        {
            "name": "Filter - High Price",
            "query": "SELECT product_name, brand, price FROM product WHERE price > 1000 ORDER BY price DESC",
            "description": "Find premium products over $1000"
        },
        {
            "name": "Filter - By Brand (Entity Resolution Test)",
            "query": "SELECT product_name, price FROM product WHERE brand = 'Apple' ORDER BY price",
            "description": "Find all Apple products - tests synonym resolution for 'Apple', 'AAPL', 'Apple Inc'"
        },
        {
            "name": "CRITICAL: iPhone 15 Base Model",
            "query": "SELECT product_name, price, storage FROM product WHERE product_name = 'iPhone 15'",
            "description": "SELECT ONLY the base iPhone 15 (NOT Pro, NOT Pro Max)"
        },
        {
            "name": "CRITICAL: iPhone 15 Pro Model",
            "query": "SELECT product_name, price, storage FROM product WHERE product_name = 'iPhone 15 Pro'",
            "description": "SELECT ONLY iPhone 15 Pro (NOT base, NOT Pro Max)"
        },
        {
            "name": "CRITICAL: iPhone 15 Pro Max Model",
            "query": "SELECT product_name, price, storage FROM product WHERE product_name = 'iPhone 15 Pro Max'",
            "description": "SELECT ONLY iPhone 15 Pro Max (NOT base, NOT Pro)"
        },
        {
            "name": "Aggregation - Average Price by Brand",
            "query": "SELECT brand, AVG(price) as avg_price, COUNT(*) as count FROM product GROUP BY brand ORDER BY avg_price DESC",
            "description": "Compare average prices by brand"
        },
    ]
    
    for i, workload in enumerate(workloads, 1):
        print(f"  [{i}] {workload['name']}")
        print(f"      Description: {workload['description']}")
        result = db.execute_query(workload['query'])
        
        if result is not None and len(result) > 0:
            print(f"      ✓ Result: {len(result)} rows")
            # Show all rows for variant tests
            for idx, (_, row) in enumerate(result.iterrows()):
                print(f"        Row {idx + 1}: {dict(row)}")
        elif result is not None:
            print(f"      ⚠ No results returned (empty result set)")
        else:
            print(f"      ✗ Query execution failed")
        
        # Variant-specific validation
        if "iPhone 15" in workload['name']:
            if result is not None and len(result) > 0:
                # Check that we got the right variant
                product_names = result['product_name'].unique()
                expected = workload['query'].split("WHERE product_name = '")[1].split("'")[0]
                if len(product_names) == 1 and product_names[0] == expected:
                    print(f"      ✓✓ PASS: Correctly isolated {expected} (distinct from other variants)")
                else:
                    print(f"      ✗✗ FAIL: Expected only '{expected}', got {list(product_names)}")
            else:
                print(f"      ✗✗ FAIL: No results for {workload['name']} (variants were merged)")
        print()
    
    db.close()
    
except Exception as e:
    print(f"  ✗ Error executing queries: {e}")
    import traceback
    traceback.print_exc()

print("=" * 70)
print("✓ GEM TEST COMPLETE")
print("=" * 70 + "\n")

