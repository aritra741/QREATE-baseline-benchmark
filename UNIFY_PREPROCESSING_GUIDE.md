# Unify Offline Preprocessing Guide

This guide explains how to run offline preprocessing for Unify and then run the challenging queries test.

## Overview

According to the Unify paper, data preprocessing should happen **offline** (before query time), not during query execution:

1. **Offline Preprocessing** (once per dataset):
   - Load text documents
   - Chunk into segments
   - Generate embeddings
   - Build HNSW indexes
   - Save indexes to disk

2. **Online Query Time** (reuse preprocessed indexes):
   - Load pre-built indexes
   - Parse query
   - Generate execution plan
   - Execute plan

## Step 1: Preprocess Data

Run the preprocessing script to build and save indexes:

### Preprocess All Datasets

```bash
# From UDA-Bench-main directory:
python systems/Unify/scripts/preprocess_unify_data.py --datasets all

# Or from systems/Unify directory:
python scripts/preprocess_unify_data.py --datasets all
```

### Preprocess Specific Datasets

```bash
# Preprocess only Med and Player datasets
python systems/Unify/scripts/preprocess_unify_data.py --datasets Med Player

# Preprocess only Finance
python systems/Unify/scripts/preprocess_unify_data.py --datasets Finan
```

### Preprocess Specific Entities

```bash
# Preprocess only Med/disease and Player/player
python systems/Unify/scripts/preprocess_unify_data.py --entities Med disease Player player

# Preprocess just Med/drug
python systems/Unify/scripts/preprocess_unify_data.py --entities Med drug
```

### Custom Output Directory

```bash
# Save indexes to a custom location
python systems/Unify/scripts/preprocess_unify_data.py --datasets all --output-dir /path/to/custom/indexes
```

## Output

The script saves preprocessed data in the following structure:

```
preprocess_unify/indexes/
├── Med/
│   ├── disease/
│   │   ├── preprocessed_data.pkl      # All chunks, embeddings, index
│   │   └── metadata.json              # Metadata about preprocessing
│   ├── drug/
│   │   ├── preprocessed_data.pkl
│   │   └── metadata.json
│   └── institution/
│       ├── preprocessed_data.pkl
│       └── metadata.json
├── Player/
│   ├── player/
│   │   ├── preprocessed_data.pkl
│   │   └── metadata.json
│   ├── city/
│   │   ├── preprocessed_data.pkl
│   │   └── metadata.json
│   └── team/
│       ├── preprocessed_data.pkl
│       └── metadata.json
├── Art/
├── Legal/
├── Finan/
└── preprocessing_summary.json
```

## Step 2: Run Challenging Queries

After preprocessing, run the challenging queries using the preprocessed indexes:

### Run Unify on All Query Types

```bash
python run_challenging_queries.py --systems unify --query-types all
```

### Run Unify on Specific Query Types

```bash
# Test filter and projection queries
python run_challenging_queries.py --systems unify --query-types filter projection

# Test only aggregation
python run_challenging_queries.py --systems unify --query-types aggregation
```

### Run All Systems for Comparison

```bash
# Test all systems (quest, uqe, lotus, unify)
python run_challenging_queries.py --systems all --query-types all
```

## Key Points

✅ **Offline Preprocessing** (`systems/Unify/scripts/preprocess_unify_data.py`):
- Happens once per dataset/entity
- Saves indexes to disk for reuse
- Follows the Unify paper's architecture

✅ **Online Query Execution** (`run_challenging_queries.py`):
- Loads preprocessed indexes from disk
- No need to rebuild indexes for each query
- Much faster query execution

⚠️ **Prerequisites**:
- Unify models must be in: `systems/Unify/main/models/`
  - `models/tokenizer`
  - `models/embedding`
- Ollama server with `qwen2.5:7b-instruct` or compatible model must be running
  - Start with: `ollama pull qwen2.5:7b-instruct && ollama serve`

## Troubleshooting

### "Preprocessed index not found"

```
[UNIFY] Preprocessing {dataset}/{entity}: requires_preprocessing
[UNIFY] Hint: Run: python preprocess_unify_data.py --entities {dataset} {entity}
```

**Solution**: Run preprocessing for that dataset/entity:
```bash
python systems/Unify/scripts/preprocess_unify_data.py --entities Med disease
```

### "Embedding model not found"

```
Failed to initialize embedding model: ...
```

**Solution**: Ensure embedding model is downloaded to:
```
systems/Unify/main/models/embedding
```

### "HNSW index build failed"

Check logs for memory issues or corrupted embeddings. Try preprocessing with smaller dataset first.

## Performance Notes

- **Preprocessing time**: ~5-30 seconds per entity (depending on dataset size)
- **Query execution**: ~10-30 seconds per query (using preprocessed indexes)
- **Disk space**: ~100MB-1GB per entity (depending on document size and chunk count)

## Results

Results are saved in: `results/challenging_queries/{run_id}/`

```
results/challenging_queries/20241209_120000/
├── results/
│   ├── unify/
│   │   ├── filter/
│   │   │   ├── filter_1/
│   │   │   │   ├── query.json
│   │   │   │   ├── result.csv
│   │   │   │   └── metadata.json
│   │   │   └── ...
│   │   └── ...
│   ├── quest/
│   └── ...
├── summary.json
├── detailed_report.json
└── run.log
```

## Full Example Workflow

```bash
# 1. Preprocess Med and Player datasets (once)
python systems/Unify/scripts/preprocess_unify_data.py --datasets Med Player

# 2. Run filter queries
python run_challenging_queries.py --systems unify --query-types filter

# 3. Run projection queries
python run_challenging_queries.py --systems unify --query-types projection

# 4. Run all query types
python run_challenging_queries.py --systems unify --query-types all

# 5. Compare with other systems
python run_challenging_queries.py --systems all --query-types all
```

