#!/bin/bash
# Simple command to run on CHPC to test with debug output

cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main
source pz_venv/bin/activate

echo "[DEBUG] Running test with both stdout and stderr capture..."
python -u systems/PZ/test_debug_extraction_simple.py 2>&1 | head -200

