# GEM Quick Start Guide

## Installation

```bash
# 1. Install dependencies
pip install -r systems/GEM/requirements.txt

# 2. Or install individually
pip install duckdb pandas openai sentence-transformers faiss-cpu
```

## Prerequisites

1. **Ollama Server Running**:
   ```bash
   # Terminal 1: Start Ollama
   ollama pull qwen2.5:7b-instruct
   ollama serve
   
   # Verify it works
   curl http://localhost:11434/v1/models
   ```

2. **Data & Schemas**:
   - Text files in `source_data/{Dataset}/{Entity}/`
   - Schema definitions in `Query/{Dataset}/{Dataset}_attributes.json`

## Quick Test

```bash
# Test with a single query
python run_challenging_queries.py --systems gem --query-ids filter_1

# Test with multiple systems for comparison
python run_challenging_queries.py --systems gem lotus quest --query-types filter projection
```

## Full Run

```bash
# Run all query types with GEM
python run_challenging_queries.py --systems gem --query-types all

# Run specific datasets
python run_challenging_queries.py --systems gem --query-types filter --query-ids filter_1 filter_2

# Resume from checkpoint
python run_challenging_queries.py --systems gem --resume
```

## Configuration

Edit `systems/GEM/config.py` to customize:

```python
# LLM Settings
OLLAMA_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "qwen2.5:7b-instruct"

# Blocking Settings
SIMILARITY_THRESHOLD = 0.85  # Lower = more lenient blocking
TOP_K_NEIGHBORS = 15         # More = more candidates checked

# Extraction Settings  
CHUNK_SIZE = 4000            # Max tokens per chunk
CHUNK_OVERLAP = 200          # Overlap for context
```

## Output

Results are saved to:
```
results/challenging_queries/{RUNID}/
├── results/gem/              # Query results by type
├── preprocessing/gem/        # Cached canonical maps
├── summary.json             # Overall statistics
└── detailed_report.json     # Per-query details
```

## Debugging

Enable verbose logging:

```python
# In config.py
LOG_LEVEL = "DEBUG"
```

Check logs:
```bash
tail -f systems/GEM/logs/gem_runner.log
tail -f results/challenging_queries/{RUNID}/run.log
```

## Performance Tips

1. **Cache Reuse**: Preprocessing results cached in `systems/GEM/.cache/`
   - Delete cache to force re-extraction: `rm -rf systems/GEM/.cache/`

2. **Parallel Runs**: Start multiple Ollama instances on different ports
   - Create separate config files with different OLLAMA_URLs

3. **Dataset Size**: Test with `--query-ids` before running all queries

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | Start Ollama: `ollama serve` |
| Empty results | Check schema file exists in Query/ |
| Slow extraction | Verify LLM is loaded: `ollama list` |
| Out of memory | Lower CHUNK_SIZE, use FAISS GPU version |
| Schema not found | Verify {Dataset}_attributes.json exists |

## Next Steps

1. ✅ Run simple queries to verify setup
2. ✅ Check results in `results/challenging_queries/`
3. ✅ Review logs for any issues
4. ✅ Compare with other systems using `--systems all`
5. ✅ Tune SIMILARITY_THRESHOLD based on results

## References

- Full documentation: `systems/GEM/README.md`
- Configuration: `systems/GEM/config.py`
- Main runner: `systems/GEM/gem_runner.py`
- Pipeline modules: `systems/GEM/*.py`

