"""
GEM (Global Entity Manager) - Unstructured Data Analysis System

A complete implementation of an LLM-powered data extraction and resolution system
that transforms raw text documents into queryable structured data.

Architecture Overview
=====================

GEM implements a 7-module pipeline:

1. Configuration & Setup (config.py)
   - Defines constants and file paths
   - Manages Ollama connection settings
   - Controls embedding and blocking parameters

2. Schema Induction (schema_loader.py)
   - Reads attribute definitions from JSON files
   - Converts schemas to LLM-friendly prompts
   - Identifies key attributes for blocking

3. Extraction (extractor.py)
   - Calls Ollama with LLM prompts
   - Handles long documents via chunking
   - Validates JSON output
   - Caches results to avoid re-extraction

4. Blocking (blocking.py)
   - Uses SentenceTransformers for embeddings
   - Builds FAISS indexes for similarity search
   - Clusters similar mentions using Union-Find
   - Ensures scalable processing of 100k+ mentions

5. Resolution (resolver.py)
   - Calls LLM to find canonical names
   - Builds global canonical map
   - Normalizes all records to canonical forms
   - Ensures consistency across dataset

6. Storage & Query (db_engine.py)
   - Creates DuckDB tables from schema
   - Implements semantic query rewriting
   - Converts user variations to canonical forms
   - Executes SQL on normalized data

7. Integration (gem_runner.py)
   - Implements SystemRunner interface
   - Orchestrates full pipeline
   - Manages preprocessing cache
   - Handles query execution

Data Flow
=========

Raw Text Files
    ↓
Extraction (LLM) → extracted_records.json + cache
    ↓
Blocking (Embeddings) → blocks (clustered mentions)
    ↓
Resolution (LLM) → canonical_map.json
    ↓
Normalization → normalized_records.json
    ↓
Storage (DuckDB) → tables with normalized data
    ↓
Query Execution (with semantic rewriting) → results

Example: Disease Entity Resolution
===================================

1. Raw documents mention diseases:
   - "Type 2 Diabetes Mellitus"
   - "Diabetes Type II"
   - "T2DM"
   - "Diabetes Mellitus Type 2"

2. Extraction:
   Extractor learns schema from Med_attributes.json:
   - disease_name (string): The name of the disease
   - disease_type (string): Type of disease
   - treatments (text): Available treatments
   
   Extracts records from each document with LLM

3. Blocking:
   SemanticBlocker encodes disease names:
   - "Type 2 Diabetes Mellitus" → [0.12, 0.45, ...]
   - "Diabetes Type II" → [0.13, 0.46, ...]
   - "T2DM" → [0.85, 0.32, ...]  (different cluster)
   
   Similarity threshold = 0.85 → {Type 2 Diabetes, Diabetes Type II} in one block

4. Resolution:
   EntityResolver calls LLM:
   Prompt: "Which is the canonical name for: ['Type 2 Diabetes Mellitus', 'Diabetes Type II']"
   LLM Output: "Type 2 Diabetes Mellitus"
   
   canonical_map = {
       "type 2 diabetes mellitus": "Type 2 Diabetes Mellitus",
       "diabetes type ii": "Type 2 Diabetes Mellitus",
       ...
   }

5. Query Execution:
   User query: SELECT * FROM disease WHERE disease_name = 'Diabetes Type II'
   
   Semantic rewriting:
   - Lookup 'Diabetes Type II' in canonical_map
   - Find canonical form: 'Type 2 Diabetes Mellitus'
   - Rewrite query: SELECT * FROM disease WHERE disease_name = 'Type 2 Diabetes Mellitus'
   
   Execute on normalized data → correct results

Critical Features
=================

1. NULL Handling:
   - If LLM extraction returns null or omits key, DuckDB receives SQL NULL
   - Never hallucinate values
   - Empty results treated as missing, not 0

2. Multi-Table Joins:
   - Single canonical map shared across all entities in dataset
   - Ensures "Disease Name" resolved same way in disease and drug tables
   - Consistent normalization across all joins

3. Rate Limiting:
   - Ollama calls sequential with 500ms delays
   - Extraction batches processed one-at-a-time
   - Prevents timeout or overload

4. Caching:
   - Extraction results cached by file hash
   - Preprocessing results cached by dataset/entity
   - Speeds up re-runs and development

5. Semantic Blocking:
   - Cosine similarity on 384-dim embeddings
   - FAISS index for O(log n) search
   - Union-Find for efficient clustering
   - Top-15 neighbors with 0.85 threshold

Setup Instructions
===================

### 1. Create Virtual Environment

```bash
# Create venv in systems/GEM/
python3 -m venv systems/GEM/venv

# Activate (macOS/Linux)
source systems/GEM/venv/bin/activate

# Or use the convenience script
bash systems/GEM/activate.sh
```

### 2. Install Dependencies

```bash
# Using the requirements file
pip install -r systems/GEM/requirements.txt

# Or manually
pip install duckdb pandas openai sentence-transformers faiss-cpu
```

### 3. Start Ollama Server

Open a new terminal:
```bash
# Install and pull the model
ollama pull qwen2.5:7b-instruct

# Start the server (runs on http://localhost:11434)
ollama serve
```

### 4. Preprocess Data

```bash
# Make sure venv is activated, then run preprocessing
cd systems/GEM
bash preprocess_all.sh

# Or manually preprocess specific datasets
python3 << 'EOF'
from gem_runner import GEMRunner

runner = GEMRunner()
meta = runner.preprocess("Med", "disease")
print(f"Status: {meta['status']}")
print(f"Records: {meta.get('records_count', 0)}")
EOF
```

### 5. Verify Data & Schemas

Verify these exist before running queries:
- `source_data/{Dataset}/{Entity}/*.txt` (text documents)
- `Query/{Dataset}/{Dataset}_attributes.json` (schemas)

### 6. Run GEM Queries

```bash
# Run all challenging queries with GEM
python run_challenging_queries.py --systems gem --query-types all

# Run specific queries
python run_challenging_queries.py --systems gem --query-ids filter_1 projection_2

# Compare with other systems
python run_challenging_queries.py --systems gem lotus quest --query-types filter
```

Configuration
=============

Edit systems/GEM/config.py to adjust:

- OLLAMA_URL: Ollama endpoint (default: http://localhost:11434/v1)
- OLLAMA_MODEL: Model to use (default: qwen2.5:7b-instruct)
- EMBEDDING_MODEL: Sentence transformer (default: all-MiniLM-L6-v2)
- SIMILARITY_THRESHOLD: Blocking similarity cutoff (default: 0.85)
- TOP_K_NEIGHBORS: Blocking neighbor count (default: 15)
- CHUNK_SIZE: Max tokens per extraction chunk (default: 4000)

### Preprocessing Cache Management

The preprocessing pipeline caches results to avoid re-running expensive operations:

```bash
# Clear extraction cache (forces fresh LLM extraction)
rm -rf systems/GEM/.cache/extractions/

# Clear all preprocessing results (blocks, resolutions, normalization)
rm -rf systems/GEM/.cache/preprocessing/

# Clear entire cache
rm -rf systems/GEM/.cache/
```

Cached data locations:
- `systems/GEM/.cache/extractions/{entity}/` - Raw LLM extracted JSON by file hash
- `systems/GEM/.cache/preprocessing/{dataset}/{entity}/` - Final normalized records and canonical maps
- Results are also saved to `results/challenging_queries/{run_id}/preprocessing/gem/`

Output Structure
================

results/challenging_queries/GEM_RUNID/
├── run.log                          # Main log file
├── results/
│   └── gem/
│       ├── simple/
│       │   └── simple_1/
│       │       ├── query.json       # Original query
│       │       ├── result.csv       # Query results
│       │       └── metadata.json    # Extraction & execution stats
│       ├── filter/
│       ├── projection/
│       ├── join/
│       ├── aggregation/
│       └── union/
├── preprocessing/
│   └── gem/
│       └── {Dataset}/
│           └── {Entity}/
│               ├── canonical_map.json        # Entity resolutions
│               ├── normalized_records.json   # Normalized data
│               └── metadata.json             # Preprocessing stats
├── checkpoint.json
├── summary.json
└── detailed_report.json

Supported Query Types
======================

GEM supports all query types through normalized SQL:

✓ Simple (projections)
✓ Filter (equality/range)
✓ Projection (multi-attribute selection)
✓ Join (single-entity joins currently, multi-entity pending)
✓ Aggregation (GROUP BY with COUNT/AVG)
✓ Union (UNION ALL combinations)

Limitations & Future Work
==========================

Current:
- Join resolution works for single entity type
- Multi-entity joins require shared key attribute

Future:
- Cross-entity blocking for join optimization
- Incremental canonical map updates
- Confidence scores for resolutions
- Advanced semantic matching for numerical fields

Troubleshooting
===============

Issue: Connection refused to Ollama
→ Verify: ollama serve is running
→ Check: http://localhost:11434/v1/models

Issue: Empty extraction results
→ Check extraction cache for errors
→ Verify: source_data files contain valid text
→ Check: LLM output in logs for parsing issues

Issue: Schema not found
→ Verify: Query/{Dataset}/{Dataset}_attributes.json exists
→ Check: File has valid JSON format with entity_name and attributes

Issue: Blocking produces too many blocks
→ Lower SIMILARITY_THRESHOLD in config.py
→ Increase TOP_K_NEIGHBORS to catch more similar items

Testing
=======

Run diagnostic queries:
```bash
# Simple filter
python run_challenging_queries.py --systems gem --query-ids filter_1

# Multiple query types
python run_challenging_queries.py --systems gem --query-types filter projection

# Full test
python run_challenging_queries.py --systems gem --query-types all
```

Performance Metrics
===================

Typical performance for disease dataset (100 documents):

- Extraction: ~2-3 seconds per document (LLM calls)
- Blocking: ~0.5 seconds (embeddings + FAISS)
- Resolution: ~1 second per block (LLM calls)
- Query execution: <100ms (DuckDB)

Total preprocessing: ~5-10 minutes for typical dataset
Query response: <1 second (cached preprocessing)

References
==========

- FAISS: https://github.com/facebookresearch/faiss
- DuckDB: https://duckdb.org/
- SentenceTransformers: https://www.sbert.net/
- Ollama: https://ollama.ai/

Author: GEM Development Team
Version: 0.1.0
License: Same as UDA-Bench
"""

