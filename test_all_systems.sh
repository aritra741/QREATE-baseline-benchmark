#!/bin/bash
# Full test suite for all systems

# Test 1: Quick UQE test
echo "=== Test 1: UQE (should work) ==="
python3 run_challenging_queries.py --systems uqe --query-types simple --log-level INFO

# Test 2: New Unify with NL conversion
echo ""
echo "=== Test 2: Unify with NL conversion ==="
python3 run_challenging_queries.py --systems unify --query-types simple --log-level DEBUG

# Test 3: Compare results
echo ""
echo "=== Results Comparison ==="
python3 << 'EOF'
import json
from pathlib import Path

results_dir = Path("results/challenging_queries")
latest = sorted(results_dir.glob("*"))[-1] if results_dir.exists() else None

if latest:
    print(f"\nLatest run: {latest.name}")
    
    for system in ["uqe", "unify"]:
        system_dir = latest / "results" / system / "simple"
        if system_dir.exists():
            print(f"\n{system.upper()} Results:")
            for query_dir in sorted(system_dir.iterdir()):
                if query_dir.is_dir():
                    meta_file = query_dir / "metadata.json"
                    result_file = query_dir / "result.csv"
                    if meta_file.exists():
                        meta = json.load(open(meta_file))
                        rows = 0
                        if result_file.exists():
                            with open(result_file) as f:
                                rows = len(f.readlines()) - 1
                        print(f"  {query_dir.name}: status={meta.get('status')}, rows={rows}, time={meta.get('total_time', 0):.2f}s")
EOF

