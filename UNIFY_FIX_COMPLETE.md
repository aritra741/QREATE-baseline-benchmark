# Unify System Fixes - Complete Guide

## Summary

Fixed **TypeError** in Unify system when executing queries with placeholder mismatches:
```
TypeError: replace() argument 2 must be str, not None
```

This occurred when the plan template couldn't match all placeholders to the original SQL query.

## Files Modified

1. **systems/Unify/main/PlanManager.py**
   - Fixed `replace_variables()` function to handle None values
   - Added diagnostic logging for mapping issues

2. **systems/Unify/main/utils/placeholders.py**
   - Improved `map_placeholders_to_original()` to never return None
   - Better error handling for template mismatches

## Test on CHPC

### Step 1: Verify Changes

```bash
cd /path/to/UDA-Bench-main

# Verify fix 1 is in place
grep "if value is None:" systems/Unify/main/PlanManager.py

# Verify fix 2 is in place  
grep 'f"\[{placeholder}\]"' systems/Unify/main/utils/placeholders.py

# Verify fix 3 is in place
grep "WARNING: Mapping contains None" systems/Unify/main/PlanManager.py
```

### Step 2: Run Test

```bash
# Run simple queries (these are quick and hit the issue)
python run_challenging_queries.py --systems unify --query-types simple \
  --run-id test_unify_fix_$(date +%Y%m%d_%H%M%S)
```

### Step 3: Check Results

```bash
# Find the latest run
LATEST=$(ls -td results/challenging_queries/test_unify_fix_* 2>/dev/null | head -1)

if [ -z "$LATEST" ]; then
    echo "No test results found!"
    exit 1
fi

echo "Results directory: $LATEST"
cd $LATEST

# Summary
echo ""
echo "===== SUMMARY ====="
cat summary.json | python -m json.tool
echo ""

# Check each query
echo "===== simple_1 Status ====="
cat results/unify/simple/simple_1/metadata.json | python -m json.tool | grep status

echo "===== simple_2 Status ====="
cat results/unify/simple/simple_2/metadata.json | python -m json.tool | grep status

# Check for errors
if grep -q "TypeError\|replace() argument" run.log; then
    echo ""
    echo "❌ FAILED: TypeError still present"
    echo "Error context:"
    grep -B 5 -A 5 "TypeError" run.log
else
    echo ""
    echo "✅ PASSED: No TypeError found"
fi

# Show any warnings
echo ""
echo "===== Diagnostic Warnings ====="
grep "WARNING:" run.log | head -10
```

## Expected Results

### Success Criteria:

✅ **simple_2 doesn't crash** with TypeError
✅ **Both queries complete** (status = "completed" or "requires_preprocessing")
✅ **Diagnostic logs show** which placeholders were problematic
✅ **No TypeErrors** in run.log

### What You Should See:

```json
{
  "total": 2,
  "completed": 2,
  "failed": 0,
  "skipped": 0
}
```

Or at minimum:
```json
{
  "total": 2,
  "completed": 1,
  "failed": 0,
  "skipped": 0
}
```

(The difference is whether preprocessing data is available)

### Diagnostic Output in Logs:

```
See mapping used in BQ for the original question
{'Entity1': 'player', 'Entity2': 'team', 'Attribute1': 'team', 'Attribute2': '[Attribute2]'}
WARNING: Mapping contains None values: {} (or list of problematic keys)
WARNING: These placeholders could not be matched to the original question
WARNING: Proceeding with 'None' as replacement string
```

## If Tests Fail

### Issue: Still Getting TypeError

```bash
# Get full error
grep -A 20 "TypeError" $LATEST/run.log

# Check if changes were applied
grep "if value is None:" systems/Unify/main/PlanManager.py
grep 'mapping\[placeholder\] = f"\[' systems/Unify/main/utils/placeholders.py
```

### Issue: Queries Still Return 0 Rows

This is a **different issue** - plan generation/execution logic
- Not related to the TypeError we fixed
- Would need to debug the basic question matching and plan validity
- Check the log for "No valid reduction found" messages

### Issue: Dependencies Missing

```bash
# Check what's actually available
pip list | grep -i "sentence\|unify\|torch"

# May need to install
pip install sentence-transformers torch hnswlib
```

## Run More Comprehensive Tests

Once basic tests pass:

```bash
# Test all simple, filter, projection queries (no joins)
python run_challenging_queries.py --systems unify \
  --query-types simple filter projection \
  --run-id test_unify_comprehensive_$(date +%Y%m%d_%H%M%S)

# Check results
cd results/challenging_queries/test_unify_comprehensive_*
cat summary.json | python -m json.tool
```

## Performance Note

Each query takes ~15-20 seconds due to:
- LLM model initialization
- Plan generation with LLM calls
- Embedding model operations
- Actual query execution

For 2 simple queries: ~30-40 seconds total

## Files to Review for Reference

- `UNIFY_FIX_SUMMARY.md` - High-level overview
- `UNIFY_CODE_CHANGES_DETAILED.md` - Before/after code comparison
- `UNIFY_TEST_QUICK_REF.md` - Quick reference commands
- `run_challenging_queries.py` - Main test runner (lines 1289-1410 for Unify runner)

