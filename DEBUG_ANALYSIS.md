# QUEST Empty Extraction - Root Cause Analysis

## Problem Summary
All three projection queries return empty DataFrames (0 rows), despite the index having 100-1000 documents available.

### Key Observations from Logs
```
[QUEST] Index 'finance' has 100 documents
[QUEST] First 5 document IDs in 'finance': ['1', '2', '3', '4', '5']
...
[DEBUG RetrieveText] Processing retrieve for columns: [...]
...
[DEBUG build_text_list] Processing 0 documents  ← CRITICAL ISSUE
```

## Root Cause

The issue is in the **initialization and retrieval chain**:

### 1. TextDocIndexer Initialization Issue (single_indexer.py:119)

When a `TextDocIndexer` is created but `docs_meta` is **NOT loaded**, it defaults to an empty dict:
```python
class TextDocIndexer(SingleIndexer):
    def __init__(...):
        super().__init__(table_name, type, **kwargs)
        self.docs_meta = {}  # ← Initialized but EMPTY!
        # ... other initialization ...
```

When `get_docs_id()` is called later (physical.py:32):
```python
def get_docs_id(self) -> list[int]:
    return list(self.docs_meta.keys())  # ← Returns [] because docs_meta is empty!
```

### 2. Incomplete load_indexer() Flow

The `load_indexer()` method in `TextDocIndexer` (single_indexer.py:319-342) expects:
- `docs_meta.json` file to exist
- Must be called BEFORE any retrieval

But if called in wrong order or if `docs_meta` isn't properly loaded before retrieval, we get empty lists.

### 3. Physical Planner Issue (physical.py:32)

```python
def build_retrieve(self, root : LogicalRetrieve):
    # ...
    node.set_retrieveList(node.indexer.get_docs_id())  # ← Gets EMPTY list!
```

The retrieve node gets an empty `retrieveList` because `docs_meta` was never populated.

### 4. Silent Failure in Retrieve

In `retrieve_text.py:42`, the loop over empty `retrieveList`:
```python
for doc_id in self.retrieveList:  # ← Empty list, loop never executes
    # ... retrieval code never runs ...
```

Result: Empty output → empty DataFrame in final extraction.

## Why This Happened

1. **Index was built** but then the `docs_meta` wasn't properly propagated to the `TextDocIndexer` instance
2. **load_indexer() wasn't called** before retrieval operations, or it failed silently
3. **No explicit debugging** for empty retrieval lists in the physical execution

## Evidence

From the logs:
- The index EXISTS: "Successfully loaded index: finance"
- Documents ARE in index: "Index 'finance' has 100 documents"  
- But retrieval returns 0 docs for extraction
- `build_text_list` processes 0 documents

This pattern indicates `retrieveList` is empty when `RetrieveText.process()` is called.

## Solution

The fix needs to ensure:
1. `docs_meta` is properly initialized from the index when `TextDocIndexer` is created
2. `get_docs_id()` returns the correct document list from the index
3. Add explicit logging to catch empty retrieval lists early




