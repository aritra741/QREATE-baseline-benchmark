#!/usr/bin/env python3
"""
Simple test of GEM on synthetic product dataset
Just does extraction, not full blocking/resolution
"""
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT))

from systems.GEM.schema_loader import load_schema
from systems.GEM.extractor import Extractor

print("\n" + "=" * 70)
print("GEM SYNTHETIC TEST - EXTRACTION ONLY")
print("=" * 70)

# Load schema
schema = load_schema(PROJECT_ROOT / "Query" / "Synthetic" / "Synthetic_attributes.json")

print(f"\n[1] SCHEMA")
print(f"  Entity: {schema.entity_name}")
print(f"  Attributes: {', '.join([a.name for a in schema.attributes])}")

# Extract from synthetic documents
extractor = Extractor(schema)

doc_dir = PROJECT_ROOT / "test_data" / "synthetic"
documents = sorted(doc_dir.glob("*.txt"))

print(f"\n[2] EXTRACTION FROM {len(documents)} DOCUMENTS")

all_records = []
for i, doc_path in enumerate(documents, 1):
    records = extractor.extract_from_file(doc_path, use_cache=False)
    all_records.extend(records)
    
    if records:
        print(f"  ✓ {doc_path.name}: {len(records)} record(s)")
        for rec in records:
            product = rec.get("product_name", "?")
            brand = rec.get("brand", "?")
            price = rec.get("price", "?")
            print(f"      - {brand} {product} (${price})")
    else:
        print(f"  - {doc_path.name}: no records extracted")

print(f"\n[3] EXTRACTION SUMMARY")
print(f"  Total records extracted: {len(all_records)}")

# Show what we got
if all_records:
    print(f"\n  Unique product mentions:")
    by_product = {}
    for rec in all_records:
        key = f"{rec.get('brand', 'Unknown')} {rec.get('product_name', 'Unknown')}"
        by_product[key] = by_product.get(key, 0) + 1
    
    for product in sorted(by_product.keys()):
        count = by_product[product]
        print(f"    - {product}: {count} mention(s)")

print("\n" + "=" * 70)
print("OBSERVATION: Entity resolution will now cluster these variations:")
print("  - 'iPhone 15' vs 'Apple iPhone 15' vs 'iPhone 15 (by Apple)'")
print("  - 'Apple' vs 'Apple Inc' vs 'AAPL'")
print("  - 'Galaxy S24' vs 'Samsung Galaxy S24'")
print("  - 'black' vs 'midnight black' vs 'phantom black'")
print("=" * 70 + "\n")

