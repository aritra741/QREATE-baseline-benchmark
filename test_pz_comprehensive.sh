#!/bin/bash
# Comprehensive test suite for PZ integration

echo "=========================================="
echo "PZ Integration Test Suite"
echo "=========================================="
echo ""

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/systems/PZ/pz_venv"

# Activate venv
echo "Activating PZ virtual environment..."
source "$VENV_DIR/bin/activate"

cd "$PROJECT_ROOT"

echo ""
echo "Test 1: Simple queries"
echo "======================================"
python run_challenging_queries.py --systems pz --query-types simple --log-level INFO 2>&1 | grep -E "Query|Result|SUMMARY|Completed|Failed"

echo ""
echo "Test 2: Filter queries"
echo "======================================"
python run_challenging_queries.py --systems pz --query-types filter --log-level INFO 2>&1 | grep -E "Query|Result|SUMMARY|Completed|Failed"

echo ""
echo "Test 3: Projection queries"
echo "======================================"
python run_challenging_queries.py --systems pz --query-types projection --log-level INFO 2>&1 | grep -E "Query|Result|SUMMARY|Completed|Failed"

echo ""
echo "Test 4: Aggregation queries"
echo "======================================"
python run_challenging_queries.py --systems pz --query-types aggregation --log-level INFO 2>&1 | grep -E "Query|Result|SUMMARY|Completed|Failed"

echo ""
echo "Test 5: Union queries"
echo "======================================"
python run_challenging_queries.py --systems pz --query-types union --log-level INFO 2>&1 | grep -E "Query|Result|SUMMARY|Completed|Failed"

echo ""
echo "=========================================="
echo "All tests complete!"
echo "=========================================="
echo ""
echo "Results are saved in: $PROJECT_ROOT/results/challenging_queries/"
echo ""

