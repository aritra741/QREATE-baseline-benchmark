#!/bin/bash
# Test script to run on CHPC and capture all output including debug messages

cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

# Activate venv
source pz_venv/bin/activate

echo "[SHELL] Running test with output capture..."
echo "[SHELL] =============================================="

# Run test with unbuffered output, capture to temp file and stdout
python -u systems/PZ/test_debug_extraction_simple.py 2>&1 | tee /tmp/pz_test_output.txt

echo ""
echo "[SHELL] =============================================="
echo "[SHELL] Test complete. Looking for GENERATOR DEBUG messages..."
echo ""

grep -n "GENERATOR DEBUG" /tmp/pz_test_output.txt || echo "[SHELL] No GENERATOR DEBUG messages found!"

echo ""
echo "[SHELL] Full output saved to /tmp/pz_test_output.txt"
echo "[SHELL] Tail of output:"
echo "[SHELL] =============================================="
tail -50 /tmp/pz_test_output.txt

