#!/bin/bash
# Reprocess Finance and Player datasets with improved JSON handling
# Run this on CHPC after the fixes

# Navigate to project root (go up 2 levels from systems/GEM/)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

# Activate venv
source systems/GEM/venv/bin/activate

echo "================================"
echo "GEM Reprocessing Pipeline"
echo "================================"
echo ""

# Create reprocessing script
python3 << 'PYTHON_SCRIPT'
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT))

from systems.GEM.gem_runner import GEMRunner

print("=" * 70)
print("GEM REPROCESSING - FINANCE & PLAYER")
print("=" * 70)
print(f"Timestamp: {datetime.now().isoformat()}")
print("")

# Datasets to reprocess
datasets = [
    ("Finan", "finance"),
    ("Player", "manager"),
    ("Player", "player"),
    ("Player", "team"),
    ("Player", "city"),
]

print(f"Reprocessing {len(datasets)} dataset(s) with improved JSON handling...\n")

runner = GEMRunner()
results = {}

for i, (dataset, entity) in enumerate(datasets, 1):
    print(f"[{i}/{len(datasets)}] Reprocessing {dataset}/{entity}...")
    try:
        meta = runner.preprocess(dataset, entity)
        status = meta.get("status")
        records = meta.get("records_count", 0)
        canonicals = meta.get("canonical_count", 0)
        
        if status in ["completed", "completed_empty"]:
            print(f"  ✓ Status: {status}")
            print(f"  ✓ Records: {records}")
            print(f"  ✓ Canonicals: {canonicals}")
        else:
            print(f"  ✗ Status: {status}")
            if "error" in meta:
                print(f"  Error: {meta['error']}")
        
        results[f"{dataset}/{entity}"] = status
    except Exception as e:
        print(f"  ✗ Exception: {str(e)[:100]}")
        results[f"{dataset}/{entity}"] = "error"
    print("")

print("=" * 70)
print("REPROCESSING SUMMARY")
print("=" * 70)
completed = sum(1 for v in results.values() if v in ["completed", "completed_empty"])
print(f"Successful: {completed}/{len(results)}")
for key, status in sorted(results.items()):
    symbol = "✓" if status in ["completed", "completed_empty"] else "✗"
    print(f"  {symbol} {key}: {status}")
print("")

PYTHON_SCRIPT

echo "================================"
echo "Reprocessing Complete!"
echo "================================"

