# QUEST Filter_2 Bug Fix - Complete Summary

## What Was Wrong

The QUEST system was returning 110 rows with only the `position` column populated, while other SELECT columns (name, team, nationality, draft_year) were empty.

### Root Cause
In the **LogicalPlanner** (and its variants), the FilterText node was being created with **ONLY WHERE clause columns**, not including SELECT columns:

```python
# BEFORE (BUG)
columns = []
for attr in where_attrs:  # ← ONLY WHERE ATTRIBUTES!
    if table == attr.parse_table():
        columns.append(attr)
filternn = LogicalFilter(columns = columns, ...)
```

This meant:
1. FilterText only extracted text for the filter column (position)
2. ExtractText had no text to extract other columns from
3. Result: empty columns for name, team, nationality, draft_year

---

## What Was Fixed

Modified all 3 logical planners to pass **ALL columns** (WHERE + SELECT) to FilterText:

```python
# AFTER (FIXED)
filter_columns = []
for attr in where_attrs:
    if table == attr.parse_table():
        filter_columns.append(attr)

# Also include SELECT columns!
for attr in proj_attrs:
    if table == attr.parse_table():
        if attr not in filter_columns:
            filter_columns.append(attr)

filternn = LogicalFilter(columns = filter_columns, ...)
```

### Files Modified
1. `systems/quest/sql/planner/logical.py` (lines 214-244)
2. `systems/quest/sql/planner/joinlogical.py` (lines 223-244)
3. `systems/quest/sql/planner/semlogical.py` (lines 229-255)

---

## Architecture Now Follows QUEST Paper

According to QUEST paper Section 3.1.2 (line 140):
> "For conjunctions, $A_s$ will have to be extracted only if all filters return True. Therefore, in this scenario, QUEST should always extract the attributes in $A_w$ first, followed by $A_s$."

Our fix ensures:
1. ✅ FilterText extracts WHERE attributes (A_w) - position
2. ✅ Evaluates filter condition - position = 'Frontcourt'
3. ✅ Passes filtered doc_ids AND text for SELECT attributes (A_s)
4. ✅ ExtractText extracts all needed attributes from filtered documents

---

## Data Flow

### Query
```sql
SELECT name, team, position, nationality, draft_year
WHERE position = 'Frontcourt'
```

### New Data Flow (FIXED)
```
Retrieve
  ├─ Gets ALL documents + text for [name, team, position, nationality, draft_year]
  └─ Output: text for all columns
       ↓
FilterText
  ├─ Receives: text for ALL columns (not just position)
  ├─ Extracts: position value from each document
  ├─ Evaluates: position = 'Frontcourt'?
  ├─ Filters: keep 113 matching documents
  └─ Output: TablePack(113 rows) + DocListPack(113 doc_ids) + TextListPacks for all columns
       ↓
ExtractText
  ├─ Receives: filtered 113 doc_ids + text for all columns
  ├─ Extracts: name, team, position, nationality, draft_year
  └─ Output: Fully populated table (113 rows × 5 columns)
       ↓
ProjectionText
  └─ Output: Final result (all columns populated)
```

---

## Testing on CHPC

### Setup
```bash
cd /uufs/chpc.utah.edu/common/home/u1592362/Downloads/UDA-Bench-main/UDA-Bench-main
source quest_venv_chpc/bin/activate
pip install -r requirements_quest_chpc.txt
python -m spacy download en_core_web_sm
```

### Run
```bash
python3 run_challenging_queries.py --systems quest --query-ids filter_2
```

### Check Results
```bash
TESTDIR=$(ls -td results/challenging_queries/* | head -1)
head -3 $TESTDIR/results/quest/filter/filter_2/result.csv
```

---

## Files Created/Modified

### New Files
- `requirements_quest_chpc.txt` - CHPC-compatible requirements (minimal versions)
- `QUEST_CHPC_SETUP.md` - Complete setup guide for CHPC
- `QUEST_CHPC_QUICK_START.md` - Quick reference commands

### Modified Code
- `systems/quest/sql/planner/logical.py`
- `systems/quest/sql/planner/joinlogical.py`
- `systems/quest/sql/planner/semlogical.py`

### Also Previously Fixed
- `systems/quest/sql/nn/filter_text.py` - Condition evaluation
- `systems/quest/sql/nn/extract_text.py` - DocListPack handling
- `systems/quest/core/llm/llm_query.py` - Prompt format

---

## Expected Results

### Before Fix
```
name,team,position,nationality,draft_year
,,Frontcourt,,,
,,Frontcourt,,,
...
```
❌ Only position populated (113 rows)

### After Fix
```
name,team,position,nationality,draft_year
LeBron James,Lakers,Frontcourt,USA,2003
Kevin Durant,Suns,Frontcourt,USA,2007
...
```
✅ All columns populated (113 rows)

---

## References

- QUEST Paper: `systems/quest/quest.pdf.md` (Section 3.1.2)
- UDA-Bench Paper: `uda-new.md` (Section 2.2 - Filter operator strategy)
- Setup Guide: `QUEST_CHPC_SETUP.md`
- Quick Start: `QUEST_CHPC_QUICK_START.md`

---

## Status

✅ **Fix Complete and Ready to Test on CHPC**

All necessary code changes have been applied. The system now correctly follows QUEST's architecture as documented in their research paper.

