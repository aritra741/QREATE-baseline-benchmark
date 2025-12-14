# Quick Test Commands for CHPC

## Run Fixed Version

```bash
# Test the simple queries again
python run_challenging_queries.py --systems unify --query-types simple \
  --run-id test_fix_$(date +%Y%m%d_%H%M%S)
```

## Check Results

```bash
# Find latest run
LATEST=$(ls -td results/challenging_queries/test_fix_* | head -1)
cd $LATEST

# Quick summary
echo "=== Summary ===" && cat summary.json | python -m json.tool

# Detailed status
echo "=== simple_1 ===" && cat results/unify/simple/simple_1/metadata.json | python -m json.tool
echo "=== simple_2 ===" && cat results/unify/simple/simple_2/metadata.json | python -m json.tool

# Check for errors in log
echo "=== Errors in log ===" && grep -i "error\|failed\|traceback" run.log | head -20
```

## Expected Improvements

### Before Fix:
- **simple_2**: FAILED with `TypeError: replace() argument 2 must be str, not None`
- Error occurs during plan execution at placeholder variable replacement

### After Fix:
- **simple_2**: Should complete without crash (may return 0 rows, but that's different issue)
- Diagnostic logs will show which placeholders had None values
- System should be more robust to template-to-question mismatches

## Verify Changes

To verify the fixes were applied:

```bash
# Check PlanManager.py has the fixed replace_variables function
grep -A 10 "def replace_variables" systems/Unify/main/PlanManager.py | head -15

# Check placeholders.py has the improved mapping function  
grep -A 5 'mapping\[placeholder\] = f"\[' systems/Unify/main/utils/placeholders.py

# Check for diagnostic logging
grep "WARNING: Mapping contains None" systems/Unify/main/PlanManager.py
```

## If Tests Still Fail

1. **Check mapping output in logs**:
   ```bash
   tail -500 $LATEST/run.log | grep -B 2 -A 2 "mapping"
   ```

2. **Compare template vs original**:
   ```bash
   tail -500 $LATEST/run.log | grep "Numbered\|Original\|Formatted"
   ```

3. **See full traceback if crash**:
   ```bash
   tail -1000 $LATEST/run.log | tail -50
   ```

## What The Fixes Do

### Fix #1: Type Safety in replace_variables()
- **Before**: `mapping[var]` could be None → crash
- **After**: Converts None to "" and all values to str() → no crash

### Fix #2: Better Placeholder Matching
- **Before**: Template parts not in original → None in mapping
- **After**: Uses "" or placeholder name as fallback → graceful degradation

### Fix #3: Diagnostic Logging
- **Before**: Silent failure - hard to debug
- **After**: Logs which placeholders failed to map → easier debugging

