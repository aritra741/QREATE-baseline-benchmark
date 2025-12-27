# Testing Protocol

## Pre-Test Verification

Before running the test, verify fixes are applied:

```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

echo "=== Pre-Test Verification ==="
echo ""
echo "Checking if fixes were applied..."

CHECK_1=$(grep -c "if value is None:" systems/Unify/main/PlanManager.py)
CHECK_2=$(grep -c 'f"\[{placeholder}\]"' systems/Unify/main/utils/placeholders.py)
CHECK_3=$(grep -c "WARNING: Mapping" systems/Unify/main/PlanManager.py)

echo "  Fix 1 (Type safety): $([[ $CHECK_1 -gt 0 ]] && echo "✅" || echo "❌")"
echo "  Fix 2 (Fallback): $([[ $CHECK_2 -gt 0 ]] && echo "✅" || echo "❌")"
echo "  Fix 3 (Diagnostics): $([[ $CHECK_3 -gt 0 ]] && echo "✅" || echo "❌")"

if [[ $CHECK_1 -gt 0 && $CHECK_2 -gt 0 && $CHECK_3 -gt 0 ]]; then
    echo ""
    echo "✅ All fixes verified!"
    echo ""
else
    echo ""
    echo "❌ Some fixes missing!"
    echo "Please check the code files"
    exit 1
fi
```

---

## Test Phase 1: Simple Queries

**Purpose**: Quick test of the TypeError fix
**Duration**: ~40 seconds
**Expected**: Both queries complete without crash

```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

echo "=== Running Simple Queries Test ==="
echo "Start time: $(date)"
echo ""

python run_challenging_queries.py --systems unify --query-types simple \
  --run-id test_simple_$(date +%Y%m%d_%H%M%S)

echo ""
echo "End time: $(date)"
```

---

## Test Phase 2: Results Analysis

**Purpose**: Verify no TypeError and check status
**Duration**: ~5 seconds

```bash
TESTDIR=$(ls -td results/challenging_queries/test_simple_* 2>/dev/null | head -1)

if [[ -z "$TESTDIR" ]]; then
    echo "❌ Test directory not found!"
    exit 1
fi

echo "=== Results Analysis ==="
echo "Test directory: $TESTDIR"
echo ""

# Check summary
echo "Summary:"
cat $TESTDIR/summary.json | python -m json.tool

echo ""
echo "=== Detailed Status ==="
echo -n "simple_1: "
cat $TESTDIR/results/unify/simple/simple_1/metadata.json | python -m json.tool | grep '"status"' | head -1

echo -n "simple_2: "
cat $TESTDIR/results/unify/simple/simple_2/metadata.json | python -m json.tool | grep '"status"' | head -1

echo ""
echo "=== Error Check ==="
if grep -q "TypeError.*replace()" $TESTDIR/run.log; then
    echo "❌ FAILED: TypeError found"
    echo ""
    echo "Error details:"
    grep -B 2 -A 5 "TypeError" $TESTDIR/run.log
    exit 1
else
    echo "✅ PASSED: No TypeError found"
fi
```

---

## Test Phase 3: Extended Test (Optional)

**Purpose**: Test with more query types
**Duration**: ~3 minutes
**Expected**: All queries complete

```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

echo "=== Extended Test (Simple + Filter + Projection) ==="
echo "Duration: ~3 minutes"
echo ""

python run_challenging_queries.py --systems unify \
  --query-types simple filter projection \
  --run-id test_extended_$(date +%Y%m%d_%H%M%S)

# Analysis
TESTDIR=$(ls -td results/challenging_queries/test_extended_* 2>/dev/null | head -1)
echo ""
echo "Results:"
cat $TESTDIR/summary.json | python -m json.tool
```

---

## Troubleshooting Protocol

### Scenario 1: TypeError Still Present

```bash
TESTDIR=$(ls -td results/challenging_queries/test_* 2>/dev/null | head -1)

echo "=== Troubleshooting: TypeError Found ==="
echo ""
echo "1. Verify fixes in code:"
grep "if value is None:" systems/Unify/main/PlanManager.py
grep 'f"\[{placeholder}\]"' systems/Unify/main/utils/placeholders.py
echo ""

echo "2. Full error context:"
grep -B 5 -A 10 "TypeError" $TESTDIR/run.log

echo ""
echo "3. Check if old code is cached:"
python -c "import py_compile; py_compile.compile('systems/Unify/main/PlanManager.py', doraise=True)"
echo "Code compiles successfully"

echo ""
echo "4. Try removing __pycache__:"
find . -type d -name __pycache__ -delete
echo "Cache cleared"
```

### Scenario 2: Queries Return 0 Rows

```bash
TESTDIR=$(ls -td results/challenging_queries/test_* 2>/dev/null | head -1)

echo "=== Troubleshooting: Zero Rows Returned ==="
echo ""
echo "This is a DIFFERENT issue from the TypeError"
echo ""

echo "1. Check mapping in logs:"
grep "See mapping\|WARNING" $TESTDIR/run.log | tail -10

echo ""
echo "2. Check if plan was generated:"
grep -i "plan\|matched" $TESTDIR/run.log | head -10

echo ""
echo "3. Check metadata for error details:"
cat $TESTDIR/results/unify/simple/simple_1/metadata.json | python -m json.tool | head -20

echo ""
echo "Note: Zero rows with 'completed' status is a plan generation issue,"
echo "not the TypeError we fixed. Investigate separately."
```

### Scenario 3: Preprocessing Missing

```bash
TESTDIR=$(ls -td results/challenging_queries/test_* 2>/dev/null | head -1)

echo "=== Troubleshooting: Preprocessing Missing ==="

if grep -q "requires_preprocessing" $TESTDIR/results/unify/simple/*/metadata.json; then
    echo "Preprocessing data not available for Med/disease"
    echo ""
    echo "To set up preprocessing, run:"
    echo "  python systems/Unify/scripts/preprocess_unify_data.py --entities Med disease"
    echo ""
    echo "But the important thing: No TypeError means the fix worked!"
fi
```

---

## Pass/Fail Criteria

### PASS ✅
- [x] No "TypeError: replace() argument 2" in logs
- [x] Simple queries don't crash
- [x] Status shows "completed" or "requires_preprocessing"
- [x] summary.json shows: failed = 0

### FAIL ❌
- [ ] "TypeError: replace()" appears in logs
- [ ] One or both queries marked as "failed"
- [ ] summary.json shows: failed > 0
- [ ] Crash before completion

### PARTIAL ✅ (Still Good)
- [x] No TypeError
- [x] Queries completed
- [x] But returning 0 rows
- → This is a different issue (plan generation), not the TypeError fix

---

## Documentation

For each test result, save:
1. Test timestamp
2. Summary JSON
3. Metadata for each query
4. Last 50 lines of log (if errors)

```bash
TESTDIR=$(ls -td results/challenging_queries/test_* | head -1)
REPORT_DIR="test_reports"
mkdir -p "$REPORT_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cat $TESTDIR/summary.json > "$REPORT_DIR/summary_$TIMESTAMP.json"
tail -50 $TESTDIR/run.log > "$REPORT_DIR/log_tail_$TIMESTAMP.txt"

echo "Report saved to $REPORT_DIR/"
```

---

## Final Verification

```bash
echo "=== Final Verification ==="
echo ""
echo "1. Code changes applied?"
grep "if value is None:" systems/Unify/main/PlanManager.py && echo "✅ Fix 1" || echo "❌ Fix 1"
grep 'f"\[{placeholder}\]"' systems/Unify/main/utils/placeholders.py && echo "✅ Fix 2" || echo "❌ Fix 2"
grep "WARNING: Mapping" systems/Unify/main/PlanManager.py && echo "✅ Fix 3" || echo "❌ Fix 3"

echo ""
echo "2. Test results available?"
TESTDIR=$(ls -td results/challenging_queries/test_* 2>/dev/null | head -1)
[[ -n "$TESTDIR" ]] && echo "✅ Results found: $TESTDIR" || echo "❌ No results"

echo ""
echo "3. No TypeError?"
[[ -n "$TESTDIR" ]] && ! grep -q "TypeError" $TESTDIR/run.log && echo "✅ No TypeError" || echo "❌ TypeError found"

echo ""
echo "=== Testing Complete ==="
```

---

## Summary Report Template

```
TEST REPORT
===========
Date: [DATE]
Time: [TIME]
Duration: [SECONDS]

FIXES VERIFICATION:
  Fix 1 (Type Safety): ✅
  Fix 2 (Fallback): ✅  
  Fix 3 (Diagnostics): ✅

TEST RESULTS:
  Total queries: 2
  Completed: 2
  Failed: 0
  Skipped: 0

CRASH TEST:
  TypeErrors found: 0
  Status: ✅ PASSED

NEXT STEPS:
  [ ] Document any issues
  [ ] Run extended test if needed
  [ ] Archive test results
```


