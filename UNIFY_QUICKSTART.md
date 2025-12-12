# Unify Quick Start

## 1. Prerequisites (One-time Setup)

```bash
# Install dependencies
pip install openai torch sentence-transformers hnswlib

# Start Ollama server (in one terminal)
ollama pull qwen2.5:7b-instruct
ollama serve

# Download models to systems/Unify/main/models/
mkdir -p systems/Unify/main/models/{tokenizer,embedding}
# Download and place tokenizer and embedding models
```

## 2. Run Unify Queries

```bash
# Simple queries
python run_challenging_queries.py --systems unify --query-types simple

# Filter queries
python run_challenging_queries.py --systems unify --query-types filter

# All query types
python run_challenging_queries.py --systems unify --query-types all

# With debug logging
python run_challenging_queries.py --systems unify --query-types simple --log-level DEBUG

# Compare with other systems
python run_challenging_queries.py --systems quest unify uqe --query-types filter projection
```

## 3. Check Results

```bash
# View latest run
ls -ltr results/challenging_queries/ | tail -5

# Check logs
tail -f results/challenging_queries/LATEST_RUN_ID/run.log

# View summary
cat results/challenging_queries/LATEST_RUN_ID/summary.json | python -m json.tool

# View detailed report
cat results/challenging_queries/LATEST_RUN_ID/detailed_report.json | python -m json.tool
```

## 4. Verify Everything Works

```bash
# Check Ollama connectivity
curl http://localhost:11434/api/tags

# Verify models are loaded
python -c "
from systems.Unify.main.embed import EmbedModel
from systems.Unify.main.chunk import ChunkExtractor
print('✓ Unify modules loaded successfully')
"

# Run single query test
python run_challenging_queries.py --systems unify --query-types simple --log-level DEBUG
```

## Configuration

**Location**: `run_challenging_queries.py` line ~1040 (UnifyRunner._ensure_init)

```python
self.ollama_model = "qwen2.5:7b-instruct"      # Change LLM model
self.ollama_base_url = "http://localhost:11434/v1"  # Change server URL
self.ollama_api_key = "ollama"                 # API key for Ollama
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Connection refused | Start Ollama: `ollama serve` |
| Model not found | Place models in `systems/Unify/main/models/` |
| Import error | Run from project root: `cd /path/to/UDA-Bench-main` |
| Memory error | Reduce batch size or use CPU |
| Slow queries | Check Ollama with: `curl http://localhost:11434/api/tags` |

## Output Location

```
results/challenging_queries/
└── YYYYMMDD_HHMMSS/
    ├── preprocessing/
    │   └── unify/...
    ├── results/
    │   └── unify/
    │       ├── simple/simple_1/result.csv
    │       ├── filter/filter_1/result.csv
    │       └── ...
    ├── run.log
    └── summary.json
```

## Integration Summary

✓ Unify Runner created with Ollama/Qwen2.5 support
✓ Data preprocessing for all datasets (Med, Player, Art, Legal, Finance)  
✓ Query execution pipeline (parse → plan → execute)
✓ Results saved in standard UDA-Bench format
✓ Integrated with run_challenging_queries.py framework


