# QUEST Empty Extraction Bug - Root Cause & Fix

## Problem
All QUEST queries returned empty DataFrames (0 rows) despite indices containing 100-1000 documents:

```
[QUEST] Index 'finance' has 100 documents
[QUEST] First 5 document IDs in 'finance': ['1', '2', '3', '4', '5']
...
[DEBUG build_text_list] Processing 0 documents  ← CRITICAL ISSUE
```

## Root Cause

### The Bug Chain

1. **In `run_challenging_queries.py` line 525:**
   ```python
   table_to_type = {entity: "TextDoc"} if entity else {}
   gb_indexer = load_all_indexer(table_to_type=table_to_type)
   ```

2. **This passes a FILTERED `table_to_type`** with only the current query's entity (e.g., `{"finance": "TextDoc"}`)

3. **In `GlobalIndexer.load_indexer()` line 168:**
   ```python
   if table_to_type is None:
       # Load ALL tables from config
       self.table_to_type = json.load(f)
   else:
       # OVERWRITE with ONLY the passed table_to_type!
       self.table_to_type = table_to_type
   ```

4. **Result:** Only ONE table gets loaded, so when the first query retrieves data, it works. But subsequent queries for other tables get `docs_meta = {}` (empty dict).

5. **In `TextDocIndexer.get_docs_id()`:**
   ```python
   return list(self.docs_meta.keys())  # Returns [] for unloaded tables!
   ```

6. **In `RetrieveText.process()` line 42:**
   ```python
   for doc_id in self.retrieveList:  # EMPTY LIST - loop never executes!
       # ... retrieval code ...
   ```

7. **Final Result:** Empty DataFrame with 0 rows returned.

## Verification

Files **DO** exist in the scratch directory:
```
/scratch/general/vast/u1592362/UDA-Bench-main/index/hnsw/finance/docs_meta.json (5.0K)
/scratch/general/vast/u1592362/UDA-Bench-main/index/hnsw/disease/docs_meta.json (5.1K)
/scratch/general/vast/u1592362/UDA-Bench-main/index/hnsw/art/docs_meta.json (48K)
```

The indices were **successfully built and saved**, but the retrieval code couldn't access them.

## Solution

### Fix 1: Primary Fix (run_challenging_queries.py)

Change line 528 from:
```python
gb_indexer = load_all_indexer(table_to_type=table_to_type)
```

To:
```python
# CRITICAL FIX: Pass table_to_type=None to load ALL pre-built indexes from config
# Do NOT pass a filtered table_to_type, as it will override the full config
gb_indexer = load_all_indexer(table_to_type=None)
```

This ensures all tables are loaded from the global index config file.

### Fix 2: Enhanced Debugging

Added diagnostic logging to catch this issue early:

**In `single_indexer.py` - `get_docs_id()` method:**
```python
def get_docs_id(self) -> list[int]:
    doc_ids = list(self.docs_meta.keys())
    if not doc_ids:
        print(f"[WARNING] get_docs_id returned EMPTY for table '{self.table_name}'!")
        print(f"[WARNING] docs_meta keys: {list(self.docs_meta.keys())}")
        print(f"[WARNING] docs_meta_path: {self.docs_meta_path}")
    return doc_ids
```

**In `single_indexer.py` - `load_indexer()` method:**
```python
def load_indexer(self) -> None:
    if self.use_hnsw:
        print(f"[DEBUG load_indexer] Loading HNSW index for table: {self.table_name}")
        if not os.path.exists(self.docs_meta_path):
            print(f"[ERROR] docs_meta.json NOT FOUND at: {self.docs_meta_path}")
            raise FileNotFoundError(...)
        # ... load file ...
        print(f"[DEBUG load_indexer] Loaded docs_meta with {len(self.docs_meta)} documents")
```

**In `retrieve_text.py` - `process()` method:**
```python
def process(self):
    # ...
    print(f"[DEBUG RetrieveText] retrieveList size: {len(self.retrieveList)}")
    if not self.retrieveList:
        print("[ERROR] retrieveList is EMPTY! No documents to retrieve from!")
        return
```

**In `physical.py` - `build_retrieve()` method:**
```python
def build_retrieve(self, root : LogicalRetrieve):
    # ...
    doc_list = node.indexer.get_docs_id()
    print(f"[DEBUG PhysicalPlanner] Retrieved {len(doc_list)} documents from indexer")
    if not doc_list:
        print(f"[ERROR PhysicalPlanner] Empty document list for table '{root.table}'!")
    node.set_retrieveList(doc_list)
```

## Files Changed

1. ✅ `/Users/aritramazumder/Documents/UDA-Bench-main/run_challenging_queries.py` - PRIMARY FIX
2. ✅ `/Users/aritramazumder/Documents/UDA-Bench-main/systems/quest/db/indexer/single_indexer.py` - Debug logging
3. ✅ `/Users/aritramazumder/Documents/UDA-Bench-main/systems/quest/sql/nn/retrieve_text.py` - Debug logging
4. ✅ `/Users/aritramazumder/Documents/UDA-Bench-main/systems/quest/sql/planner/physical.py` - Debug logging
5. ✅ `/Users/aritramazumder/Documents/UDA-Bench-main/systems/quest/sql/nn/extract_text.py` - Debug logging

## Testing

After applying these fixes, re-run the test:

```bash
python run_challenging_queries.py --systems quest --query-types projection 2>&1 | tee debug_detailed.log
```

Expected output:
- `[DEBUG PhysicalPlanner] Retrieved 100 documents from indexer` (or similar count)
- `[DEBUG RetrieveText] retrieveList size: 100` (or similar)
- `fianl_table` with rows (not empty!)

## Summary

| Issue | Cause | Fix |
|-------|-------|-----|
| Empty retrieval list | Filtered table_to_type overrides config | Pass `None` to load all tables |
| No docs_meta loaded | Only current table was loaded | Load ALL tables from global config |
| Silent failure | No warning logs when list is empty | Added debug logging at 4 key points |

The core issue was a logic error in how `GlobalIndexer.load_indexer()` handles the `table_to_type` parameter. By passing `None`, the method loads the complete configuration of all available indices instead of just the current query's table.


