# Exact Code Locations - For Reference

## File 1: systems/Unify/main/PlanManager.py

### Change Location 1: replace_variables() function
- **Lines**: 414-428
- **What changed**: Handles None values in mapping by converting to empty string
- **Why**: Prevents TypeError when .replace() gets None as argument
- **To verify**:
  ```bash
  sed -n '414,428p' systems/Unify/main/PlanManager.py
  ```

### Change Location 2: execute_with_plan() diagnostic logging
- **Lines**: 350-365 (approximately)
- **What changed**: Added warning logs for None values in mapping
- **Why**: Helps debug when placeholders don't match original question
- **To verify**:
  ```bash
  sed -n '350,370p' systems/Unify/main/PlanManager.py | grep "WARNING"
  ```

---

## File 2: systems/Unify/main/utils/placeholders.py

### Change Location: map_placeholders_to_original() function
- **Lines**: 33-63
- **What changed**: Returns fallback `f"[{placeholder}]"` instead of None
- **Why**: Prevents None from appearing in mapping dictionary
- **To verify**:
  ```bash
  sed -n '33,63p' systems/Unify/main/utils/placeholders.py
  ```

---

## How to View the Changes

### View all three changes at once:
```bash
echo "=== Fix 1: PlanManager replace_variables ===" && \
sed -n '414,428p' systems/Unify/main/PlanManager.py && \
echo "" && \
echo "=== Fix 2: PlanManager diagnostic logging ===" && \
sed -n '350,365p' systems/Unify/main/PlanManager.py && \
echo "" && \
echo "=== Fix 3: placeholders map function ===" && \
sed -n '33,63p' systems/Unify/main/utils/placeholders.py
```

### View only the key lines that changed:
```bash
# The critical type check
grep -n "if value is None:" systems/Unify/main/PlanManager.py

# The fallback mapping
grep -n 'mapping\[placeholder\] = f"\[' systems/Unify/main/utils/placeholders.py

# The diagnostic warning
grep -n "WARNING: Mapping contains None" systems/Unify/main/PlanManager.py
```

---

## Verify Fixes Are Applied

```bash
#!/bin/bash

echo "Checking if all fixes are in place..."
echo ""

# Check 1: Replace Variables Fix
if grep -q "if value is None:" systems/Unify/main/PlanManager.py; then
    echo "✅ Fix 1: None handling in replace_variables() - FOUND"
else
    echo "❌ Fix 1: None handling - NOT FOUND"
fi

# Check 2: Diagnostic Logging
if grep -q "WARNING: Mapping contains None" systems/Unify/main/PlanManager.py; then
    echo "✅ Fix 2: Diagnostic logging - FOUND"
else
    echo "❌ Fix 2: Diagnostic logging - NOT FOUND"
fi

# Check 3: Fallback Mapping
if grep -q 'mapping\[placeholder\] = f"\[{placeholder}\]"' systems/Unify/main/utils/placeholders.py; then
    echo "✅ Fix 3: Fallback placeholder mapping - FOUND"
else
    echo "❌ Fix 3: Fallback mapping - NOT FOUND"
fi

echo ""
echo "If all three show ✅, fixes are properly applied."
```

---

## Diff Summary (What Changed)

### PlanManager.py Line 421 Changed:
```diff
- input_string = input_string.replace(f'[{var}]', mapping[var])
+ value = mapping[var]
+ if value is None:
+     value = ""
+ else:
+     value = str(value)
+ input_string = input_string.replace(f'[{var}]', value)
```

### placeholders.py Line 62 Changed:
```diff
- mapping[placeholder] = None
+ mapping[placeholder] = f"[{placeholder}]"
```

### PlanManager.py Lines 350-361 Added:
```diff
+ # Check if mapping has any None values and log a warning
+ none_mappings = {k: v for k, v in mapping.items() if v is None}
+ if none_mappings:
+     print(f"WARNING: Mapping contains None values: {none_mappings}")
+     print(f"WARNING: These placeholders could not be matched to the original question")
+     print(f"WARNING: Proceeding with 'None' as replacement string")
```

---

## Line-by-Line Breakdown

### PlanManager.py - The Critical Fix

**Before (line 421 - CRASHES)**:
```
421 |   input_string = input_string.replace(f'[{var}]', mapping[var])
     └─ If mapping[var] is None → TypeError
```

**After (lines 421-425 - SAFE)**:
```
421 | value = mapping[var]
422 | if value is None:
423 |     value = ""
424 | else:
425 |     value = str(value)
426 | input_string = input_string.replace(f'[{var}]', value)
     └─ value is always a string → No TypeError
```

### placeholders.py - The Root Cause Fix

**Before (line 62 - CREATES NONE)**:
```
62 | mapping[placeholder] = None
   └─ Adds None to mapping when placeholder not found
```

**After (line 59 - CREATES STRING)**:
```
59 | mapping[placeholder] = f"[{placeholder}]"
   └─ Adds fallback string instead of None
```

This prevents None from ever entering the mapping in the first place.

---

## To Revert the Changes (If Needed)

```bash
# These commands would UNDO the fixes - only use if you need to
# (Generally you DON'T want to do this)

# Revert PlanManager.py to original version:
# git checkout systems/Unify/main/PlanManager.py

# Revert placeholders.py to original version:
# git checkout systems/Unify/main/utils/placeholders.py
```

---

## Files Created for Documentation

1. **UNIFY_FIX_COMPLETE.md** - Complete testing guide
2. **UNIFY_CODE_CHANGES_DETAILED.md** - Before/after comparison
3. **UNIFY_TEST_QUICK_REF.md** - Quick reference
4. **UNIFY_CHPC_TEST_COMMANDS.md** - Copy-paste commands
5. **UNIFY_FIX_SUMMARY.md** - Overview
6. **EXACT_CODE_LOCATIONS.md** - This file

