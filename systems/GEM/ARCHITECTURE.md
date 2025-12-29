# GEM Architecture Document

## Overview

The Global Entity Manager (GEM) is a complete unstructured data analysis system that transforms raw text documents into queryable structured data. It combines LLM-powered extraction, semantic blocking, and entity resolution to achieve high-quality data normalization.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GEM System Architecture                       │
└─────────────────────────────────────────────────────────────────┘

Raw Text Files (source_data/)
    │
    ├─→ Schema Loader (Module 1)
    │   • Reads JSON attribute definitions
    │   • Builds LLM-friendly prompts
    │   • Identifies key attributes
    │
    ├─→ Extractor (Module 3)
    │   • Chunks long documents
    │   • Calls Ollama with prompts
    │   • Validates & caches JSON
    │   ↓
    │   Extracted Records (∼100k mentions)
    │
    ├─→ Semantic Blocker (Module 4)
    │   • Embeds entity values
    │   • Builds FAISS index
    │   • Clusters via Union-Find
    │   ↓
    │   Blocks (∼10k clusters)
    │
    ├─→ Entity Resolver (Module 5)
    │   • Calls LLM for each block
    │   • Builds canonical map
    │   • Normalizes all records
    │   ↓
    │   Canonical Map + Normalized Records
    │
    ├─→ DB Engine (Module 6)
    │   • Creates DuckDB schema
    │   • Loads normalized data
    │   • Builds semantic query rewriter
    │   ↓
    │   Queryable Database
    │
    └─→ Query Executor
        • Intercepts SQL strings
        • Rewrites with canonical map
        • Executes on normalized data
        ↓
        Results as DataFrame
```

## Module Details

### Module 1: Configuration & Setup (`config.py`)

**Purpose**: Centralized configuration management

**Responsibilities**:
- Define Ollama connection parameters
- Set embedding model and blocking thresholds
- Manage file paths (cache, database, logs)
- Configure chunking and batching parameters

**Key Classes/Functions**:
- `OLLAMA_URL`, `OLLAMA_MODEL`: LLM configuration
- `EMBEDDING_MODEL`, `SIMILARITY_THRESHOLD`: Blocking configuration
- `CACHE_DIR`, `DB_PATH`: File system paths

**Configuration Points**:
```python
OLLAMA_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "qwen2.5:7b-instruct"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SIMILARITY_THRESHOLD = 0.85
TOP_K_NEIGHBORS = 15
CHUNK_SIZE = 4000
```

### Module 2: Schema Induction (`schema_loader.py`)

**Purpose**: Parse attribute definitions into usable schemas

**Data Structures**:
```
Attribute
├── name (str): field name
├── type (str): "string", "integer", "float", etc.
├── description (str): human-readable description
└── Methods:
    ├── to_dict() → Dict
    ├── to_prompt_str() → str  (for LLM prompt)

Schema
├── entity_name (str): e.g., "disease"
├── attributes: List[Attribute]
└── Methods:
    ├── to_prompt_str() → str  (full schema as prompt)
    ├── get_key_attributes() → List[str]  (for blocking)
    ├── get_numeric_attributes() → List[str]  (for agg)

SchemaLoader
├── schemas: Dict[str, Schema]  (cache)
└── Methods:
    ├── load_from_file(filepath) → Schema
    ├── load_multiple(directory) → Dict[str, Schema]
    ├── _parse_schema(data) → Schema
```

**Input Format** (`Query/Med/Med_attributes.json`):
```json
{
  "entity_name": "disease",
  "attributes": {
    "disease_name": {
      "type": "string",
      "description": "The medical name of the disease"
    },
    "disease_type": {
      "type": "string",
      "description": "Category (infectious, genetic, etc.)"
    }
  }
}
```

**Output** (LLM System Prompt):
```
Entity: disease
Extract the following fields:
- disease_name (string): The medical name of the disease
- disease_type (string): Category (infectious, genetic, etc.)
```

### Module 3: Extraction (`extractor.py`)

**Purpose**: Extract structured data from text using LLM

**Data Structures**:
```
Extractor
├── schema: Schema
├── client: OpenAI (Ollama client)
├── chunker: TextChunker
├── cache_dir: Path
└── Methods:
    ├── extract_from_file(filepath) → List[Dict]
    ├── extract_from_directory(directory) → Tuple[List[Dict], Dict]
    ├── _extract_from_text(text) → List[Dict]
    ├── _get_cache_path(filepath) → Path
    ├── _read_cache(filepath) → Optional[List[Dict]]
    ├── _write_cache(filepath, records) → None

TextChunker
├── chunk_size: int
├── overlap: int
└── Methods:
    ├── chunk_text(text) → List[str]
    ├── estimate_tokens(text) → int
```

**Pipeline**:

1. **Read File**: Load text from disk
2. **Chunk**: Split into overlapping chunks if > 4k tokens
3. **LLM Call**: For each chunk:
   - System prompt: schema + extraction instructions
   - User prompt: chunk text
   - Extract: JSON validation
4. **Cache**: Save results by file hash
5. **Return**: List of extracted records

**Caching Strategy**:
- Hash filename to get unique cache key
- Store extracted JSON in `.cache/extractions/{entity}/{hash}.json`
- Avoid re-extraction on restart
- Delete cache to force fresh extraction

**Error Handling**:
- Invalid JSON → warn + skip record
- LLM timeout → retry with exponential backoff
- Null values → omit from record (not hallucinate)

### Module 4: Blocking (`blocking.py`)

**Purpose**: Cluster similar entity mentions using embeddings

**Data Structures**:
```
UnionFind
├── parent: List[int]
├── rank: List[int]
└── Methods:
    ├── find(x) → int  (with path compression)
    ├── union(x, y) → bool  (with union by rank)
    ├── get_clusters() → Dict[int, List[int]]

SemanticBlocker
├── model: SentenceTransformer
├── index: faiss.Index
└── Methods:
    ├── encode_texts(texts) → np.ndarray
    ├── build_index(embeddings) → faiss.Index
    ├── find_similar_items(embeddings, k, threshold) → List[List[int]]
    ├── block_entities(records, key_attributes) → List[Set[int]]
```

**Algorithm**:

1. **Extract Key Values**: Get entity mention strings from records
   - Concatenate key attributes (e.g., disease_name)
   - Example: ["Advil", "advil", "Advil Liqui-Gels", "Ibuprofen"]

2. **Vectorize**: Encode strings to embeddings
   - Model: `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
   - Output: (n, 384) array

3. **Index**: Build FAISS index
   - Type: IndexFlatIP (inner product for cosine similarity)
   - Normalize vectors for cosine distance
   - O(log n) search complexity

4. **Search**: Find neighbors for each vector
   - Top k=15 nearest neighbors
   - Filter by similarity > 0.85
   - Record indices returned

5. **Cluster**: Merge similar items with Union-Find
   - If neighbors[i] contains j, union(i, j)
   - Path compression for efficiency
   - Result: clusters of similar mentions

**Example**:
```
Mentions: ["Diabetes", "Type 2 Diabetes", "T2DM", "Insulin Resistance"]
Embeddings: [[0.12, ...], [0.14, ...], [0.85, ...], [0.72, ...]]
Similarities: 
  - Diabetes ↔ Type 2 Diabetes: 0.92 (>0.85 → merge)
  - Diabetes ↔ T2DM: 0.45 (<0.85 → separate)
  - Diabetes ↔ Insulin Resistance: 0.60 (<0.85 → separate)

Result Blocks:
- Block 1: {0, 1} (Diabetes, Type 2 Diabetes)
- Block 2: {2} (T2DM)
- Block 3: {3} (Insulin Resistance)
```

### Module 5: Global Resolution (`resolver.py`)

**Purpose**: Find canonical names for each entity block

**Data Structures**:
```
EntityResolver
├── client: OpenAI (Ollama)
├── canonical_map: Dict[str, str]
└── Methods:
    ├── resolve_blocks(records, blocks, key_attrs) → Dict[str, str]
    ├── _get_canonical_for_block(mentions) → str
    ├── get_canonical(mention) → str
    ├── normalize_record(record, key_attrs) → Dict
    ├── normalize_records(records, key_attrs) → List[Dict]
    ├── save_canonical_map(filepath) → None
    ├── load_canonical_map(filepath) → None
```

**Canonical Map Format**:
```json
{
  "diabetes": "Type 2 Diabetes Mellitus",
  "type 2 diabetes": "Type 2 Diabetes Mellitus",
  "diabetes type ii": "Type 2 Diabetes Mellitus",
  "t2dm": "Type 2 Diabetes Mellitus",
  "advil": "Advil",
  "advil pm": "Advil"
}
```

**Resolution Process**:

1. **For Each Block**:
   - Extract all unique mention strings
   - If 1 item: use as canonical
   - If >1 item: call LLM

2. **LLM Prompt**:
   ```
   Here is a list of entity mentions that likely refer to the same thing:
   ['Type 2 Diabetes Mellitus', 'Diabetes Type II', 'T2DM']
   
   Identify the most standard, concise, and widely-recognized canonical name.
   Return ONLY the name.
   ```

3. **Build Map**:
   - For each mention m in block:
     - canonical_map[m.lower()] = canonical
     - canonical_map[m] = canonical

4. **Normalize Records**:
   - For each record:
     - For each key attribute:
       - Replace value with canonical form

**Global Map Sharing**:
- Single canonical_map for entire dataset
- If "Disease Name" in disease table maps to "Advil" → map to "Advil"
- If "Drug Name" in drug table also contains "Advil" → same canonical
- Ensures consistency across JOIN queries

### Module 6: Storage & Query (`db_engine.py`)

**Purpose**: Store normalized data and execute queries with semantic rewriting

**Data Structures**:
```
DBEngine
├── conn: duckdb.Connection
├── db_path: Path
├── resolver: EntityResolver
├── schema: Schema
└── Methods:
    ├── create_table(table_name, schema) → None
    ├── insert_records(table_name, records) → None
    ├── execute_query(sql) → pd.DataFrame
    ├── _rewrite_sql_with_canonical_map(sql) → str
    ├── drop_table(table_name) → None
    ├── table_exists(table_name) → bool
    ├── get_table_info(table_name) → Dict
    ├── close() → None
```

**Table Creation**:
```python
# Schema → SQL types
disease_name (string) → VARCHAR
disease_type (string) → VARCHAR
disease_count (integer) → INTEGER
avg_cases (float) → DOUBLE
```

**Semantic Query Rewriting**:

```python
# User query
sql = "SELECT * FROM disease WHERE disease_name = 'Diabetes Type II'"

# Canonical map
canonical_map = {
    "diabetes type ii": "Type 2 Diabetes Mellitus",
    ...
}

# Rewrite process:
1. Find string literals: 'Diabetes Type II'
2. Lookup in canonical_map: 'Diabetes Type II'.lower() → canonical
3. Replace: 'Type 2 Diabetes Mellitus'

# Rewritten query
sql = "SELECT * FROM disease WHERE disease_name = 'Type 2 Diabetes Mellitus'"

# Execute on normalized data
```

**NULL Handling**:
- If JSON extraction omits key → record doesn't have key → NULL in CSV
- pandas → DuckDB preserves NULL values
- SQL NULL != missing (proper semantics)

### Module 7: Integration (`gem_runner.py`)

**Purpose**: Orchestrate full pipeline, implement SystemRunner interface

**Key Methods**:
```
GEMRunner
├── preprocess(dataset, entity) → Dict
│   └─ Runs extraction → blocking → resolution
│   └─ Caches results
│
└── run_query(query) → Tuple[pd.DataFrame, Dict]
    └─ Uses cached preprocessing
    └─ Creates DB + executes SQL
    └─ Returns results + metadata
```

**Preprocessing Pipeline**:
```
1. Load schema from Query/{Dataset}/{Dataset}_attributes.json
2. Get data path from source_data/{Dataset}/{Entity}/
3. Extract records using LLM
4. Block entities using embeddings
5. Resolve blocks to canonical names
6. Normalize all records
7. Cache canonical_map + normalized_records
```

**Query Execution Pipeline**:
```
1. Check preprocessing cache (skip if exists)
2. Create in-memory DuckDB
3. Create table from schema
4. Insert normalized records
5. Rewrite SQL with canonical map
6. Execute query
7. Return DataFrame + metadata
```

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                     GEM Data Flow                             │
└──────────────────────────────────────────────────────────────┘

source_data/Med/disease/*.txt (100 files, ∼2k per file)
    │ (Extractor.extract_from_directory)
    ↓
[
  {"disease_name": "Diabetes Mellitus Type 2", "disease_type": "metabolic"},
  {"disease_name": "Type 2 Diabetes", "disease_type": "metabolic"},
  {"disease_name": "T2DM", "disease_type": "metabolic"},
  ...  (∼1000 records total)
]
    │ (SemanticBlocker.block_entities)
    ↓
[
  {0, 1, 2},        # Similar diabetes mentions
  {3, 4},           # Hypertension variants
  {5},              # Asthma (unique)
  ...               # ∼100 blocks
]
    │ (EntityResolver.resolve_blocks)
    ↓
{
  "diabetes mellitus type 2": "Type 2 Diabetes Mellitus",
  "type 2 diabetes": "Type 2 Diabetes Mellitus",
  "t2dm": "Type 2 Diabetes Mellitus",
  "hypertension": "Hypertension",
  "high blood pressure": "Hypertension",
  "asthma": "Asthma",
  ...  (∼200 mappings)
}
    │ (EntityResolver.normalize_records)
    ↓
[
  {"disease_name": "Type 2 Diabetes Mellitus", "disease_type": "metabolic"},
  {"disease_name": "Type 2 Diabetes Mellitus", "disease_type": "metabolic"},
  {"disease_name": "Type 2 Diabetes Mellitus", "disease_type": "metabolic"},
  ...  (∼1000 normalized records)
]
    │ (DBEngine + GEMRunner)
    ↓
DuckDB Database (in-memory or on-disk)
  ├── Table: disease
  │   ├── disease_name VARCHAR
  │   ├── disease_type VARCHAR
  │   └── 1000 rows (normalized)
    │ (DBEngine.execute_query)
    ↓
SQL Query: "SELECT * FROM disease WHERE disease_name = 'Diabetes Type II'"
  ├─ Rewrite: 'Diabetes Type II' → 'Type 2 Diabetes Mellitus'
  ├─ Execute: "SELECT * FROM disease WHERE disease_name = 'Type 2 Diabetes Mellitus'"
  └─ Return: 3 rows (all T2DM variants resolved to same canonical)
    │
    ↓
DataFrame (result as CSV or JSON)
```

## Configuration Parameters

### Extraction
- `CHUNK_SIZE`: 4000 tokens (max per LLM call)
- `CHUNK_OVERLAP`: 200 tokens (for context)
- `EXTRACTION_TIMEOUT`: 60 seconds
- `EXTRACTION_MAX_RETRIES`: 3

### Blocking
- `SIMILARITY_THRESHOLD`: 0.85 (0-1 cosine similarity)
- `TOP_K_NEIGHBORS`: 15 (neighbors to check)
- `EMBEDDING_DIM`: 384 (MiniLM dimension)

### Resolution
- `RESOLUTION_TIMEOUT`: 30 seconds per block
- `RESOLUTION_MAX_RETRIES`: 2

### LLM
- `OLLAMA_URL`: http://localhost:11434/v1
- `OLLAMA_MODEL`: qwen2.5:7b-instruct
- `EMBEDDING_MODEL`: sentence-transformers/all-MiniLM-L6-v2

## Performance Characteristics

### Time Complexity
- Extraction: O(n) where n = number of documents
- Embedding: O(n) with batch encoding
- FAISS: O(log n) per query with IP index
- Blocking: O(n log n) with Union-Find
- Resolution: O(b) where b = number of blocks
- Query: O(1) after indexing

### Space Complexity
- Embeddings: O(n × 384) bytes
- FAISS index: O(n × 384) bytes
- Canonical map: O(u) where u = unique mentions
- Database: O(r × a) where r = records, a = attributes

### Example Performance
For typical Med dataset (100 documents, 1000 mentions):
- Extraction: 2-3 seconds per document
- Embedding: 0.5 seconds
- Blocking: 1-2 seconds
- Resolution: 30-60 seconds (30 LLM calls)
- Query: <100ms

## Error Handling

1. **Extraction Errors**:
   - JSON parse error → warn + skip
   - Timeout → retry with backoff
   - Invalid UTF-8 → ignore + continue

2. **Blocking Errors**:
   - FAISS error → fallback to singleton blocks
   - Embedding error → return empty blocks

3. **Resolution Errors**:
   - LLM error → use first mention as canonical
   - Empty response → fallback to first mention

4. **Query Errors**:
   - SQL syntax → log + return None
   - Table not found → error + return None
   - Type mismatch → DuckDB handles automatically

## Extensibility

### Adding New Extraction Methods
- Subclass `Extractor`
- Override `_extract_from_text()`
- E.g., for structured formats (CSV → records)

### Adding New Blocking Strategies
- Implement `block_entities()` interface
- Alternative similarity methods (Jaccard, BM25)
- Alternative clustering (DBSCAN, hierarchical)

### Adding New Resolution Methods
- Implement `resolve_blocks()` interface
- Different LLM prompting strategies
- Confidence scoring for resolutions

## Testing

Run test suite:
```bash
pytest systems/GEM/test_gem.py -v
```

Covered:
- Schema loading and parsing
- Union-Find clustering
- Database operations
- Entity resolution
- Full pipeline integration

