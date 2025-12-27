# Copy-Paste Commands for CHPC Testing

## Quick Test (Copy & Paste All)

```bash
#!/bin/bash

# Navigate to project
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

echo "=========================================="
echo "Step 1: Verify fixes were applied"
echo "=========================================="

echo ""
echo "Checking PlanManager.py..."
if grep -q "if value is None:" systems/Unify/main/PlanManager.py; then
    echo "✓ Fix 1 found: None value handling"
else
    echo "✗ Fix 1 NOT found"
fi

echo ""
echo "Checking placeholders.py..."
if grep -q 'f"\[{placeholder}\]"' systems/Unify/main/utils/placeholders.py; then
    echo "✓ Fix 2 found: Fallback placeholder mapping"
else
    echo "✗ Fix 2 NOT found"
fi

echo ""
echo "=========================================="
echo "Step 2: Run test queries"
echo "=========================================="
echo ""

# Run with simple queries
python run_challenging_queries.py --systems unify --query-types simple \
  --run-id test_fix_$(date +%Y%m%d_%H%M%S)

# Wait for completion
echo ""
echo "Test run complete!"
```

## Check Results (Copy & Paste All)

```bash
#!/bin/bash

cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

# Find latest test run
LATEST=$(ls -td results/challenging_queries/test_fix_* 2>/dev/null | head -1)

if [ -z "$LATEST" ]; then
    echo "No test results found!"
    exit 1
fi

echo "Results: $LATEST"
echo ""

cd $LATEST

# Show summary
echo "===== SUMMARY ====="
cat summary.json | python -m json.tool
echo ""

# Show query statuses
echo "===== QUERY STATUSES ====="
echo -n "simple_1: "
cat results/unify/simple/simple_1/metadata.json | python -m json.tool | grep '"status"' | head -1

echo -n "simple_2: "
cat results/unify/simple/simple_2/metadata.json | python -m json.tool | grep '"status"' | head -1

echo ""

# Check for crashes
echo "===== ERROR CHECK ====="
if grep -q "TypeError.*replace().*argument 2" run.log; then
    echo "❌ FAILED: TypeError still present!"
    echo ""
    grep -B 3 -A 3 "TypeError" run.log
else
    echo "✅ PASSED: No TypeError found"
fi

echo ""
echo "===== MAPPINGS ====="
grep "See mapping\|WARNING: Mapping" run.log | tail -5
```

## Step-by-Step Individual Commands

```bash
# 1. Navigate to project
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

# 2. Verify Fix 1
grep -n "if value is None:" systems/Unify/main/PlanManager.py
# Should show: systems/Unify/main/PlanManager.py:423:            if value is None:

# 3. Verify Fix 2  
grep -n 'f"\[{placeholder}\]"' systems/Unify/main/utils/placeholders.py
# Should show: systems/Unify/main/utils/placeholders.py:59:            mapping[placeholder] = f"[{placeholder}]"

# 4. Run test
python run_challenging_queries.py --systems unify --query-types simple \
  --run-id test_unify_$(date +%Y%m%d_%H%M%S)

# 5. Check results after test completes
TESTDIR=$(ls -td results/challenging_queries/test_unify_* | head -1)
echo "Test directory: $TESTDIR"

# 6. View summary
cat $TESTDIR/summary.json

# 7. Check for errors
grep "TypeError" $TESTDIR/run.log && echo "FAILED" || echo "PASSED"

# 8. View detailed statuses
cat $TESTDIR/results/unify/simple/simple_1/metadata.json
cat $TESTDIR/results/unify/simple/simple_2/metadata.json
```

## If You Get an Error, Troubleshoot With:

```bash
# Get test directory
TESTDIR=$(ls -td results/challenging_queries/test_unify_* | head -1)

# Show last 100 lines of log
echo "===== Last 100 lines of log ====="
tail -100 $TESTDIR/run.log

# Show error context
echo ""
echo "===== Error context (if any) ====="
grep -B 10 -A 10 "Error\|Failed\|Traceback" $TESTDIR/run.log | tail -50

# Show metadata for both queries
echo ""
echo "===== Query Metadata ====="
echo "simple_1:"
cat $TESTDIR/results/unify/simple/simple_1/metadata.json | python -m json.tool | head -20

echo ""
echo "simple_2:"
cat $TESTDIR/results/unify/simple/simple_2/metadata.json | python -m json.tool | head -20
```

## Expected Output for Success

```
===== SUMMARY =====
{
  "total": 2,
  "completed": 2,  ← both completed
  "failed": 0,     ← no failures
  "skipped": 0,
  ...
}

===== QUERY STATUSES =====
simple_1: "status": "completed"
simple_2: "status": "completed"

===== ERROR CHECK =====
✅ PASSED: No TypeError found
```

## One More Test: Run More Queries

```bash
# After basic test passes, try more query types
python run_challenging_queries.py --systems unify \
  --query-types simple filter projection \
  --run-id test_unify_extended_$(date +%Y%m%d_%H%M%S)

# This will take longer (~3-5 min for 9 queries total)
# Then check results the same way
```


