# UQE Setup Complete ✅

## Preprocessing Completed Successfully

All UDA datasets have been preprocessed for UQE:

```
✓ Med/disease: 100 items, embeddings (100, 384)
✓ Med/drug: 100 items, embeddings (100, 384)
✓ Med/institutes: 100 items, embeddings (100, 384)
✓ Player/nba: 141 items, embeddings (141, 384)
✓ Player/team: 30 items, embeddings (30, 384)
✓ Player/manager: 16 items, embeddings (16, 384)
✓ Player/city: 29 items, embeddings (29, 384)
✓ Art/Wikiart: 1003 items, embeddings (1003, 384)
✓ Legal/LCR: 570 items, embeddings (570, 384)
✓ Finan/Finance: 100 items, embeddings (100, 384)
```

## Preprocessing Details

1. **Data Conversion**: CSV files converted to JSON format with unified "id" and "description" fields
2. **Embedding Generation**: Text embeddings generated using `sentence-transformers` (all-MiniLM-L6-v2)
3. **Storage**: Data and embeddings stored in `systems/UQE/data/{entity_name}/`

Location: `/Users/aritramazumder/Documents/UDA-Bench-main/systems/UQE/data/`

## How to Run UQE

### Using the run_challenging_queries.py script:

```bash
# Activate venv
source /Users/aritramazumder/Documents/UDA-Bench-main/.venv/bin/activate

# Run simple queries (projection-only)
python3 run_challenging_queries.py --systems uqe --query-types simple

# Run all UQE-supported queries
python3 run_challenging_queries.py --systems uqe --query-types simple projection

# Resume from checkpoint
python3 run_challenging_queries.py --resume --run-id <RUN_ID>

# Results saved to:
# results/challenging_queries/<RUN_ID>/
```

### Direct UQE queries:

```bash
cd /Users/aritramazumder/Documents/UDA-Bench-main/systems/UQE
python3 main_disease.py
python3 main_player.py
python3 main_fin.py
```

## Important: UQE Data Model

UQE operates on **unstructured data** with virtual attributes, unlike QUEST which uses structured relational data.

### UQE Data Model:
- **Concrete columns**: "id", "description" (text documents)
- **Virtual columns**: Attributes extracted from description via LLM (disease_name, pathogenesis, etc.)

### For Queries:
- `SELECT` operations extract attributes from unstructured text
- `WHERE` conditions apply semantic filters on virtual columns
- `GROUP BY` performs semantic clustering
- Queries use Ollama with `qwen3:8b` model (configured in `systems/UQE/config_uqe.py`)

## Required Dependencies Installed

```
pandas, numpy, sentence-transformers, torch, torchvision, transformers, 
pillow, tqdm, openai, litellm, faiss-cpu
```

All installed in `.venv` environment.

## Configuration Files

- **LLM Config**: `systems/UQE/config_uqe.py`
  - Model: `qwen3:8b` (via Ollama)
  - Base URL: `http://localhost:11434/v1`
  - API Key: "ollama"

- **Schema Definitions**: `systems/UQE/schema/*.py`
  - Defines virtual attributes for each dataset entity

## Preprocessing Script

Created: `systems/UQE/preprocess_uda.py`

To re-run preprocessing:
```bash
source .venv/bin/activate
cd systems/UQE
python3 preprocess_uda.py
```

## Next Steps

1. To run filter/aggregation/join queries with UQE, queries need to be adapted to use semantic conditions (natural language) rather than direct attribute comparisons
2. Ollama server must be running for LLM-based extraction and filtering
3. Consider running only simple queries initially for testing

## Summary

UQE preprocessing is complete and ready for querying. The system extracts semantic attributes from unstructured documents using LLMs and performs efficient sampling-based aggregation queries.


