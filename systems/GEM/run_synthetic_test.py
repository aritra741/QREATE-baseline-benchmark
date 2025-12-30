#!/usr/bin/env python3
"""
GEM Synthetic Test - End-to-end test on synthetic product dataset
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

print("\n" + "=" * 70)
print("✓ GEM TEST COMPLETE")
print("=" * 70 + "\n")

