# GEM System Update: Inline Deduplication & SQLite Integration

## Overview

This document describes the comprehensive upgrade to the GEM ingestion pipeline, implementing:

1. **Inline Deduplication** - "Search-before-Add" strategy using HNSW index
2. **SQLite Storage** - Robust relational storage with proper type handling
3. **Type Cleaning** - Automatic extraction and normalization of numeric values
4. **Discriminative LLM Resolution** - Prevents over-merging of distinct variants

---

## Module 1: SQLite Storage Engine (`db_engine.py`)

### Purpose
Manages database schema creation, record insertion, and query execution with semantic rewriting.

### Key Enhancements

#### 1.1 Schema Enforcement
- Maps JSON schema types to SQLite types:
  - `int`, `integer` → `INTEGER`
  - `float`, `double`, `decimal` → `REAL`
  - `bool`, `boolean` → `INTEGER` (0/1)
  - String types → `TEXT`

#### 1.2 Type Cleaning (`_clean_numeric_value`)
Automatically cleans numeric values by:
- Removing currency symbols ($, €, £, etc.)
- Removing thousand separators (,)
- Removing whitespace
- Keeping only digits, decimal points, and minus signs

**Example:**
```
Input:  "$1,234.56"
Output: 1234.56 (float)

Input:  "€999"
Output: 999 (float)
```

#### 1.3 Semantic Shim (`execute_query`)
- **Before execution**: Parse SQL for string constants
- **Consult CanonicalMap**: If a queried string is an alias, rewrite to canonical form
- **Example**: Query for 'Ibuprofen' → rewritten to 'Advil' if that's the canonical name

**Implementation:**
```python
rewritten_sql = self._rewrite_sql_with_canonical_map(sql)
df = pd.read_sql_query(rewritten_sql, self.conn)
```

#### 1.4 Insert Records with Type Conversion
The `insert_records` method now:
1. Filters columns to match schema
2. Applies type-specific cleaning for numeric columns
3. Converts lists to pipe-delimited strings for multi-valued fields
4. Handles boolean conversion

---

## Module 2: Ingestion with Inline Deduplication (`ingest.py`)

### Purpose
Implements the "One-Pass" ingestion algorithm with FAISS-based HNSW indexing.

### Algorithm: "Search-before-Add"

For each new mention `M_new`:

1. **Identity Check (K=1 Search)**
   - Query FAISS index for single nearest neighbor
   - Get similarity score (normalized from L2 distance)

2. **Deduplication Logic**

   **Case A: Similarity > 0.98 (Exact Duplicate)**
   - Skip HNSW insertion
   - Map `M_new` to same Component_ID as neighbor
   - **Action:** No insert

   **Case B: Similarity > 0.85 (Potential Synonym)**
   - Insert into HNSW
   - Link `M_new` and neighbor in Union-Find structure
   - **Action:** Insert + mark as candidate for LLM review

   **Case C: Similarity ≤ 0.85 (New Entity)**
   - Insert into HNSW
   - Start new Component_ID in Union-Find
   - **Action:** Insert

### Class: `InlineDeduplicator`

```python
class InlineDeduplicator:
    def ingest_batch(records, key_attributes):
        """Ingest records with inline deduplication"""
        # For each record:
        #   - Encode using blocker
        #   - Search index for nearest neighbor
        #   - Apply deduplication logic
        #   - Update FAISS index
        # Return: (deduplicated_records, component_map)
    
    def finalize():
        """Apply LLM resolution to candidate blocks"""
        # Resolve blocks using LLM
        # Update canonical names in records
        # Return final records
```

### Key Methods

- `_build_index()` - Create/rebuild FAISS index from embeddings
- `_search_nearest_neighbor(embedding)` - Find NN in O(1) time
- `ingest_record(record, key_attributes)` - Process single record
- `ingest_batch(records, key_attributes)` - Batch process and return deduplicated records
- `finalize()` - Apply LLM resolution and return final records

---

## Module 3: Discriminative LLM Resolution (`resolver.py`)

### Purpose
Audit candidate blocks to prevent over-merging of distinct variants.

### Algorithm: Splitter Pattern

For each candidate block, the LLM is asked:

**Prompt:**
```
Group these mentions into entities. Keep SYNONYMS together 
but KEEP DISTINCT VARIANTS SEPARATE.

Rules:
1. SAME ENTITY: Synonyms, case variations, abbreviations
   - Example: "iPhone 15" vs "iphone 15" → GROUP
2. DIFFERENT ENTITIES: Different products, versions, tiers
   - Example: "iPhone 15 Pro" vs "iPhone 15 Pro Max" → SEPARATE
3. Better to under-merge than over-merge

Return JSON:
{
  "Canonical Name 1": ["variant1", "variant2"],
  "Canonical Name 2": ["variant3", "variant4"]
}
```

### Implementation

Enhanced `_get_canonical_for_block()` now:
1. Sends discriminative prompt to Ollama
2. Parses JSON response to get entity groups
3. Returns primary canonical name
4. Updates CanonicalMap with all variant → canonical mappings

---

## Module 4: Type Cleaning & Normalization

### Type Cleaning Pipeline

**Numeric Columns:**
```
Input:  "$1,234.56"  (INTEGER or FLOAT field)
Clean:  Remove [^\d.\-]
Result: 1234.56
```

**String Columns:**
```
Input:  ["ibuprofen", "advil"]  (LIST type)
Join:   "||"
Result: "ibuprofen||advil"
```

**Boolean Columns:**
```
Input:  "True", "1", "yes"
Result: True
```

### Schema-Driven Conversion

The schema defines expected types, and insertion respects them:

```python
schema = {
    "attributes": [
        {"name": "price", "type": "float"},
        {"name": "quantity", "type": "int"},
        {"name": "tags", "type": "multi_str"},
    ]
}
```

During insertion:
- `price` column: Clean with `_clean_numeric_value(value, "float")`
- `quantity` column: Clean with `_clean_numeric_value(value, "int")`
- `tags` column: Join list items with "||"

---

## Module 5: Execution & Verification

### Test: Inline Deduplication

Run the synthetic test:
```bash
python systems/GEM/run_inline_dedup_test.py
```

**Test Cases:**

1. **Exact Duplicates** - Same product, same price → Should be deduplicated
2. **Synonym Variations** - "iphone 15 pro" vs "iPhone 15 Pro" → Should be deduplicated
3. **Distinct Variants** - "iPhone 15 Pro" vs "iPhone 15 Pro Max" → Should be SEPARATE
4. **Numeric Queries** - `WHERE price > 1000` → Should work without type errors

**Expected Output:**

```
Created 6 synthetic products:
  [0] iPhone 15 Pro                $   999 128GB
  [1] iPhone 15 Pro                $   999 128GB
  [2] iphone 15 pro                $   999 128GB
  [3] iPhone 15 Pro Max            $ 1099 128GB
  [4] iPhone 15 Pro Max            $ 1099 256GB
  [5] iPhone 15                    $   799 128GB

Results: 6 -> 4 records after deduplication
(Removed 2 exact duplicates)

Database Verification:
✓ TEST 1: Pro and Pro Max are separate records
✓ TEST 2: Numeric comparison works (WHERE price > 1000)
✓ TEST 3: Exact duplicates were removed
```

### Running Tests

```bash
# Clear cache
rm -rf systems/GEM/.cache

# Run inline deduplication test
python systems/GEM/run_inline_dedup_test.py

# Run existing GEM tests
python systems/GEM/test_gem.py

# Run with challenging queries
python run_challenging_queries.py --systems gem --query-id join_1
```

---

## Key Design Decisions

### 1. Why K=1 Search (not K=5)?
- **O(1) similarity lookup** instead of O(K)
- **Clear decision logic**: Exact or not, synonym or not
- **Single nearest neighbor is sufficient** for blocking decisions

### 2. Why Discriminative LLM?
- **Prevents over-merging**: "iPhone 15 Pro" ≠ "iPhone 15 Pro Max"
- **Understands context**: Different capacities, tiers, versions
- **Better than unsupervised**: LLM has domain knowledge

### 3. Why Type Cleaning in Insertion?
- **Database correctness**: SQLite enforces types
- **Prevents binder errors**: "VARCHAR vs INTEGER" bugs eliminated
- **Handles real-world data**: "$1,234.56" is common in extractions

### 4. Why Union-Find for Candidate Blocks?
- **Efficient clustering**: O(α(n)) amortized
- **Natural grouping**: Transitive relations handled automatically
- **LLM input**: Gives clear groups to resolve

---

## Configuration

Key thresholds in `config.py`:

```python
# Deduplication thresholds
EXACT_THRESHOLD = 0.98      # Exact duplicate
SYNONYM_THRESHOLD = 0.85    # Potential synonym

# Embedding
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SIMILARITY_THRESHOLD = 0.85

# LLM
OLLAMA_MODEL = "qwen2.5:7b-instruct"
RESOLUTION_TIMEOUT = 30
RESOLUTION_MAX_RETRIES = 3
```

---

## Future Enhancements

1. **Batched FAISS Operations** - Process multiple records in parallel
2. **Adaptive Thresholds** - Learn thresholds from training data
3. **Incremental Updates** - Add new records without full reprocessing
4. **Schema Evolution** - Handle new fields dynamically
5. **Caching** - Cache embeddings and LLM resolutions

---

## Troubleshooting

### Issue: "ValueError: unknown type int"
**Solution:** Ensure schema has correct type mapping. Check `_get_sql_type()` in db_engine.py

### Issue: "WHERE price > 1000 → type error"
**Solution:** Type cleaning not applied. Check `_clean_numeric_value()` was called

### Issue: "Over-merged duplicates"
**Solution:** Lower `EXACT_THRESHOLD` or `SYNONYM_THRESHOLD`. Check LLM discriminative prompt

### Issue: "Index build failed"
**Solution:** Check FAISS installation. Verify embeddings have consistent dimensions

---

## References

- **FAISS**: Efficient similarity search library
- **HNSW**: Hierarchical Navigable Small World graph
- **Union-Find**: Disjoint set data structure
- **Sentence Transformers**: Embedding models
- **SQLite**: Lightweight relational database

