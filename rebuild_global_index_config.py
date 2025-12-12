#!/usr/bin/env python3
"""
Rebuild the global index config file to include all available table indices.
This fixes the issue where the config only includes 'finance' table.
"""

import json
import os
from pathlib import Path

# Configuration
SCRATCH_USER = os.environ.get('USER', 'u1592362')
INDEX_ROOT = f"/scratch/general/vast/{SCRATCH_USER}/UDA-Bench-main/index"
HNSW_DIR = os.path.join(INDEX_ROOT, "hnsw")
CONFIG_DIR = os.path.join(INDEX_ROOT, "global_index")
CONFIG_FILE = os.path.join(CONFIG_DIR, "global_index.json")

print(f"INDEX_ROOT: {INDEX_ROOT}")
print(f"HNSW_DIR: {HNSW_DIR}")
print(f"CONFIG_FILE: {CONFIG_FILE}")
print()

# Find all table directories in hnsw/
if not os.path.exists(HNSW_DIR):
    print(f"ERROR: HNSW directory not found: {HNSW_DIR}")
    exit(1)

table_dirs = [d for d in os.listdir(HNSW_DIR) 
              if os.path.isdir(os.path.join(HNSW_DIR, d))]
table_dirs.sort()

print(f"Found {len(table_dirs)} table directories:")
for table in table_dirs:
    print(f"  - {table}")
print()

# Create table_to_type mapping
table_to_type = {}
for table in table_dirs:
    # All are TextDoc type (based on the indices that were built)
    table_to_type[table] = "TextDoc"

# Make sure config directory exists
os.makedirs(CONFIG_DIR, exist_ok=True)

# Write the config file
print(f"Writing {len(table_to_type)} tables to config file...")
with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
    json.dump(table_to_type, f, ensure_ascii=False, indent=2)

print(f"✓ Config file written to: {CONFIG_FILE}")
print()

# Verify by reading it back
with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    verify = json.load(f)

print("Verification - Config now contains:")
for table in sorted(verify.keys()):
    print(f"  {table}: {verify[table]}")
print()
print(f"✓ Successfully rebuilt global index config with {len(verify)} tables!")


