#!/bin/bash
# Quick Unify test on CHPC

cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

# Install missing dependencies
echo "Installing missing dependencies..."
pip install -q sentence-transformers 2>/dev/null || echo "Note: sentence-transformers install may take time"

# Run the test
echo ""
echo "Starting Unify test..."
python3 run_challenging_queries.py --systems unify --query-types simple --log-level INFO
