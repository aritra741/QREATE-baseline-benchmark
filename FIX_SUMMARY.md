# UQE Optimization Test Fix - Quick Reference

## Issue
```
KeyError: 2896 in test_stratified_sampling
File: systems/UQE/active_learning.py, line 234
```

## What Was Changed
**File**: `systems/UQE/active_learning.py`
**Method**: `StratifiedSampler.get_importance_weights()`

### The Fix
Added graceful handling for rows not assigned to any cluster:

```python
# Before: Direct dict lookup (fails on missing keys)
cluster_id = row_to_cluster[row_idx_int]

# After: Check before access
if row_idx_int not in row_to_cluster:
    weights[i] = 1.0  # Uniform weight for unmapped rows
else:
    cluster_id = row_to_cluster[row_idx_int]
    # ... compute weight ...
```

## Why This Works
1. **Type Safety**: Converts `np.int64` to Python `int` consistently
2. **Robustness**: Handles imperfect clustering that doesn't cover all rows
3. **Correctness**: Unmapped rows get neutral weight (1.0), which is appropriate for stratified sampling with incomplete cluster coverage

## How to Test
```bash
cd /Users/aritramazumder/Documents/UDA-Bench-main
source systems/UQE/uqe_venv/bin/activate
python systems/UQE/test_optimizations.py
```

## Expected Output
All 5 tests should pass:
- ✓ stratified_sampling
- ✓ active_learning  
- ✓ query_optimizer
- ✓ cost_estimation
- ✓ integration

## Files Modified
1. `systems/UQE/active_learning.py` - Fixed `get_importance_weights()` method

## No Breaking Changes
- Backward compatible with existing code
- Gracefully handles edge cases
- Maintains mathematical correctness of stratified sampling
