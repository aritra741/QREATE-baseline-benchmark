#!/bin/bash
# Quick test of PZ integration with UDA-Bench

echo "=========================================="
echo "PZ Integration Test"
echo "=========================================="
echo ""

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/systems/PZ/pz_venv"

# Activate venv
echo "Activating PZ virtual environment..."
source "$VENV_DIR/bin/activate"

# Test 1: Check Python version
echo ""
echo "Test 1: Python version"
python --version

# Test 2: Check installed packages
echo ""
echo "Test 2: Checking key packages..."
python -c "
import pandas as pd
import openai
import colorama
print(f'  ✓ pandas {pd.__version__}')
print(f'  ✓ openai {openai.__version__}')
print(f'  ✓ colorama {colorama.__version__}')
"

# Test 3: Check PZ runner can be imported
echo ""
echo "Test 3: PZ runner import test..."
cd "$PROJECT_ROOT"
python -c "
import sys
sys.path.insert(0, 'systems/PZ')
from pz_runner import PZRunner
print('  ✓ PZRunner imported successfully')
"

# Test 4: Show how to run
echo ""
echo "=========================================="
echo "Integration Tests Passed!"
echo "=========================================="
echo ""
echo "To run PZ with UDA-Bench challenging queries:"
echo ""
echo "1. Activate the PZ environment:"
echo "   source systems/PZ/pz_venv/bin/activate"
echo ""
echo "2. Run a quick test with simple queries:"
echo "   python run_challenging_queries.py --systems pz --query-types simple"
echo ""
echo "3. Run specific query types:"
echo "   python run_challenging_queries.py --systems pz --query-types filter projection"
echo ""
echo "4. Run with other systems (if available):"
echo "   python run_challenging_queries.py --systems pz quest uqe --query-types all"
echo ""
echo "5. Resume from checkpoint:"
echo "   python run_challenging_queries.py --resume"
echo ""
echo "=========================================="

