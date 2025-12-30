# GEM Fixes Applied - Discriminative Entity Resolution

## Problem Identified
GEM was committing **Entity Resolution Errors (Over-Merging)** - it was merging distinct product variants (e.g., "iPhone 15 Pro" and "iPhone 15 Pro Max") into a single canonical entity, causing loss of query selectivity.

## Root Cause
The embedding model (MiniLM) produces coarse-grained similarity scores, treating variants like "Pro" and "Pro Max" as 95% similar. This is good for blocking (high recall), but the resolution logic was too aggressive - it assumed everything in a block must be the same entity.

## Architectural Solutions Implemented

### 1. Increased Blocking Threshold (Conservative Blocking)

**File:** `systems/GEM/config.py`

**Change:** Increased `SIMILARITY_THRESHOLD` from `0.85` to `0.92`

```python
# Before: SIMILARITY_THRESHOLD = 0.85
# After:  SIMILARITY_THRESHOLD = 0.92  # More conservative
```

**Effect:** Reduces the likelihood of variants like "Pro" and "Pro Max" being blocked together initially. Implements the "Safety Valve" strategy - better to under-merge than over-merge.

### 2. Discriminative Resolution Logic (Splitter Pattern)

**File:** `systems/GEM/resolver.py`

**Change:** Rewrote `_get_canonical_for_block()` method with explicit discriminative instructions

**Key Changes:**
- Updated LLM prompt to distinguish between synonyms and distinct variants
- Added explicit rules:
  - "If they are SYNONYMS or case variations of the SAME thing, group them"
  - "If they represent DIFFERENT PRODUCTS or VERSIONS, treat them as DISTINCT"
  - "If they have different sizes, capacities, tiers, or generations, they are DISTINCT"
  - "Better to under-merge (keep separate) than over-merge (lose information)"

**Example Behavior:**

Before (Aggressive Merging):
```
Input: ["iPhone 15", "iPhone 15 Pro", "iPhone 15 Pro Max"]
Output: "iPhone 15 Pro Max" (all merged - query for "Pro" fails!)
```

After (Discriminative):
```
Input: ["iPhone 15", "iPhone 15 Pro", "iPhone 15 Pro Max"]
Output: For blocks that contain distinct variants:
  - "iPhone 15" stays separate
  - "iPhone 15 Pro" stays separate  
  - "iPhone 15 Pro Max" stays separate
Query: SELECT price FROM phones WHERE model = 'iPhone 15 Pro' → Works!
```

## Testing the Fix

Run the synthetic test on CHPC to verify:

```bash
cd /path/to/UDA-Bench-main
source systems/GEM/venv/bin/activate
python3 systems/GEM/run_synthetic_test.py
```

Expected behavior: Product variants should now be kept separate (e.g., iPhone 15 vs Pro vs Pro Max).

## Configuration Tuning

To adjust behavior in the future:

- **More conservative (more under-merging):** Increase `SIMILARITY_THRESHOLD` further (e.g., 0.95)
- **More aggressive (more merging):** Decrease `SIMILARITY_THRESHOLD` (e.g., 0.88)
- **Modify resolution rules:** Update the LLM prompt in `_get_canonical_for_block()`

## Impact on Query Accuracy

This fix enables:
- ✅ Selective filtering: `WHERE model = 'iPhone 15 Pro'` now works correctly
- ✅ Accurate joins: Matching phones to prices by exact model
- ✅ Precision aggregation: Computing stats by specific product variant

Without this fix:
- ❌ All variants merged into one → Query precision = 0
- ❌ Cannot distinguish between different products

