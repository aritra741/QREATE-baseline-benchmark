#!/bin/bash
# GEM Preprocessing Script - Processes all datasets in source_data/

set -e

# Navigate to project root (go up 2 levels from systems/GEM/)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

# Activate venv
# source systems/GEM/venv/bin/activate

echo "================================"
echo "GEM Preprocessing Pipeline"
echo "================================"
echo ""

# Create preprocessing script
python3 << 'PYTHON_SCRIPT'
import sys
import os
from pathlib import Path
from datetime import datetime

# Add to path
PROJECT_ROOT = Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "GEM"))

from systems.GEM.gem_runner import GEMRunner
from systems.GEM.config import CACHE_DIR

print("=" * 70)
print("GEM PREPROCESSING PIPELINE")
print("=" * 70)
print(f"Timestamp: {datetime.now().isoformat()}")
print(f"Cache dir: {CACHE_DIR}")
print("")

# Datasets and entities to preprocess
datasets = [
    ("Med", "disease"),
    ("Med", "drug"),
    ("Med", "institution"),
    ("Player", "player"),
    ("Player", "team"),
    ("Player", "manager"),
    ("Player", "city"),
    ("Art", "art"),
    ("Legal", "legal_case"),
    ("Finan", "finance"),
]

print(f"Starting preprocessing for {len(datasets)} dataset(s)...\n")

runner = GEMRunner()
results = {}

for i, (dataset, entity) in enumerate(datasets, 1):
    print(f"[{i}/{len(datasets)}] Preprocessing {dataset}/{entity}...")
    try:
        meta = runner.preprocess(dataset, entity)
        status = meta.get("status")
        records = meta.get("records_count", 0)
        canonicals = meta.get("canonical_count", 0)
        
        if status == "completed":
            print(f"  ✓ Status: {status}")
            print(f"  ✓ Records: {records}")
            print(f"  ✓ Canonicals: {canonicals}")
        else:
            print(f"  ✗ Status: {status}")
            if "error" in meta:
                print(f"  ✗ Error: {meta['error']}")
        
        results[f"{dataset}/{entity}"] = status
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        results[f"{dataset}/{entity}"] = "error"
    print("")

print("=" * 70)
print("PREPROCESSING SUMMARY")
print("=" * 70)
completed = sum(1 for v in results.values() if v == "completed")
print(f"Completed: {completed}/{len(results)}")
for key, status in sorted(results.items()):
    symbol = "✓" if status == "completed" else "✗"
    print(f"  {symbol} {key}: {status}")
print("")

PYTHON_SCRIPT

echo "================================"
echo "Preprocessing Complete!"
echo "================================"

