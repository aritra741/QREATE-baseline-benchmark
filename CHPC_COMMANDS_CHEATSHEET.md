# CHPC Command Cheat Sheet

## Copy & Paste Ready Commands

### 1️⃣ Verify Fixes Are Applied

```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

echo "Verifying fixes..."
echo -n "Fix 1 (Type safety): "
grep -q "if value is None:" systems/Unify/main/PlanManager.py && echo "✅" || echo "❌"

echo -n "Fix 2 (Fallback): "
grep -q 'f"\[{placeholder}\]"' systems/Unify/main/utils/placeholders.py && echo "✅" || echo "❌"

echo -n "Fix 3 (Diagnostics): "
grep -q "WARNING: Mapping contains None" systems/Unify/main/PlanManager.py && echo "✅" || echo "❌"
```

### 2️⃣ Run Simple Queries Test

```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

python run_challenging_queries.py --systems unify --query-types simple \
  --run-id test_unify_$(date +%Y%m%d_%H%M%S)
```

### 3️⃣ Check Results Immediately After Test

```bash
TESTDIR=$(ls -td results/challenging_queries/test_unify_* 2>/dev/null | head -1)

echo "Test directory: $TESTDIR"
echo ""
echo "Summary:"
cat $TESTDIR/summary.json | python -m json.tool
echo ""
echo "Error check:"
if grep -q "TypeError.*replace()" $TESTDIR/run.log; then
    echo "❌ FAILED: TypeError found"
    grep -B 2 -A 2 "TypeError" $TESTDIR/run.log | head -10
else
    echo "✅ PASSED: No TypeError"
fi
```

### 4️⃣ Detailed Results

```bash
TESTDIR=$(ls -td results/challenging_queries/test_unify_* 2>/dev/null | head -1)

echo "=== Query Statuses ==="
echo -n "simple_1: "
cat $TESTDIR/results/unify/simple/simple_1/metadata.json | python -m json.tool | grep '"status"' | head -1

echo -n "simple_2: "
cat $TESTDIR/results/unify/simple/simple_2/metadata.json | python -m json.tool | grep '"status"' | head -1

echo ""
echo "=== Errors (if any) ==="
grep "ERROR\|FAILED\|TypeError" $TESTDIR/run.log || echo "None"

echo ""
echo "=== Row Counts ==="
echo -n "simple_1 rows: "
cat $TESTDIR/results/unify/simple/simple_1/metadata.json | python -m json.tool | grep result_count

echo -n "simple_2 rows: "
cat $TESTDIR/results/unify/simple/simple_2/metadata.json | python -m json.tool | grep result_count
```

### 5️⃣ View Full Log (Last 200 Lines)

```bash
TESTDIR=$(ls -td results/challenging_queries/test_unify_* 2>/dev/null | head -1)
tail -200 $TESTDIR/run.log
```

### 6️⃣ Search Log for Specific Info

```bash
TESTDIR=$(ls -td results/challenging_queries/test_unify_* 2>/dev/null | head -1)

echo "=== Mapping Info ==="
grep "See mapping\|WARNING.*None" $TESTDIR/run.log

echo ""
echo "=== Timing Info ==="
grep "total_time\|parse_time" $TESTDIR/run.log | head -5
```

### 7️⃣ Run Extended Test (After Simple Test Passes)

```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

python run_challenging_queries.py --systems unify \
  --query-types simple filter projection \
  --run-id test_extended_$(date +%Y%m%d_%H%M%S)
```

### 8️⃣ Full Test (All Query Types)

```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

python run_challenging_queries.py --systems unify \
  --query-types all \
  --run-id test_all_$(date +%Y%m%d_%H%M%S)
```

---

## Quick One-Liners

### Check if fixes applied + show results:
```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main && \
grep "if value is None:" systems/Unify/main/PlanManager.py && \
grep 'f"\[{placeholder}\]"' systems/Unify/main/utils/placeholders.py && \
grep "WARNING: Mapping" systems/Unify/main/PlanManager.py && \
echo "✅ All fixes in place"
```

### Run test + show summary:
```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main && \
python run_challenging_queries.py --systems unify --query-types simple --run-id test_$(date +%s) && \
TESTDIR=$(ls -td results/challenging_queries/test_* | head -1) && \
cat $TESTDIR/summary.json | python -m json.tool
```

### Run + test in one go:
```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main && \
python run_challenging_queries.py --systems unify --query-types simple --run-id test_$(date +%s) && \
TESTDIR=$(ls -td results/challenging_queries/test_* | head -1) && \
if grep -q "TypeError" $TESTDIR/run.log; then echo "❌ FAILED"; else echo "✅ PASSED"; fi && \
cat $TESTDIR/summary.json | python -m json.tool
```

---

## Troubleshooting Commands

### If you get a crash:
```bash
TESTDIR=$(ls -td results/challenging_queries/test_* 2>/dev/null | head -1)

echo "Full error:"
grep -A 20 "TypeError\|Traceback" $TESTDIR/run.log | head -30

echo ""
echo "Check if fixes are applied:"
grep "if value is None:" systems/Unify/main/PlanManager.py
```

### If results are empty but no crash:
```bash
TESTDIR=$(ls -td results/challenging_queries/test_* 2>/dev/null | head -1)

echo "Metadata:"
cat $TESTDIR/results/unify/simple/simple_1/metadata.json

echo ""
echo "Is there a result CSV?"
ls -la $TESTDIR/results/unify/simple/simple_1/result.csv 2>&1
```

### If you want to see what's in the results directory:
```bash
TESTDIR=$(ls -td results/challenging_queries/test_* 2>/dev/null | head -1)

echo "Files created:"
find $TESTDIR -type f | sort

echo ""
echo "Directory structure:"
tree $TESTDIR -L 3
```

---

## Environment Check

```bash
# Check Python version
python --version

# Check if Unify system exists
ls -la systems/Unify/main/

# Check if data files exist
ls -la Data/Med/disease.csv
ls -la Data/Player/player.csv

# Check if source data exists (for Unify)
ls -la source_data/Healthcare/

# Check if preprocessing data exists
ls -la preprocess_unify/indexes/
```

---

## Performance Expectations

```
Simple queries (2): ~40-50 seconds
Filter queries (3): ~60 seconds each = 180 total
Projection queries (3): ~60 seconds each = 180 total
All queries (18): ~15-20 minutes

Per query: ~60 seconds
- LLM initialization: ~10s
- Plan generation: ~20s
- Execution: ~30s
```

---

## File Locations for Reference

```
Project Root: /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main

Code files:
  systems/Unify/main/PlanManager.py
  systems/Unify/main/utils/placeholders.py

Data directories:
  Data/Med/, Data/Player/, etc.
  source_data/Healthcare/, source_data/Player/, etc.

Test results:
  results/challenging_queries/test_*/
```

---

## Success Check Summary

```
✅ Minimal Requirements:
  ✓ No TypeError in logs
  ✓ Both queries completed (status != "failed")
  ✓ Summary shows completed >= 1

✅ Ideal Results:
  ✓ No TypeError in logs
  ✓ Both queries completed
  ✓ Both return result rows
  ✓ Summary shows: total=2, completed=2, failed=0

❌ If This Happens:
  ✗ "TypeError: replace() argument 2" → Fix not applied
  ✗ Both failed → Different issue
  ✗ 0 rows returned → Plan generation issue (separate)
```


