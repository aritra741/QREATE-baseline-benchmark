# Unify System Integration with UDA-Bench

This guide explains how to set up and run the **Unify** system as part of the UDA-Bench benchmarking suite.

## Overview

Unify is an unstructured data analytics system that:
- Decomposes natural language queries into sub-queries
- Matches queries with predefined semantic operators
- Generates and optimizes execution plans
- Executes plans efficiently using LLMs for semantic analysis

The integration uses **Ollama** with **Qwen2.5:7b-instruct** for local LLM inference, matching the setup of other systems in UDA-Bench (UQE, Palimpzest, etc.).

## Prerequisites

### 1. Install Required Dependencies

```bash
# Install Unify dependencies
pip install openai torch sentence-transformers hnswlib

# Or use the requirements file in Unify directory
cd systems/Unify
pip install -r requirements.txt
```

### 2. Set Up Ollama with Qwen2.5

First, ensure you have Ollama installed:

```bash
# Install Ollama from https://ollama.ai
# Then pull the Qwen2.5 model

ollama pull qwen2.5:7b-instruct

# Start the Ollama server (runs on http://localhost:11434/v1)
ollama serve
```

Verify Ollama is running:
```bash
curl http://localhost:11434/api/tags
```

### 3. Download Unify Models

Unify requires pre-trained models for:
- **Tokenizer**: For token counting and processing
- **Embedding Model**: For semantic similarity and indexing

Create the directory structure:
```bash
mkdir -p systems/Unify/main/models/{tokenizer,embedding}
```

Download models (these should match your setup):
- Tokenizer: `heilerich/llama-tokenizer-fast` (or similar)
- Embedding: `all-MiniLM-L6-v2` or similar (from Hugging Face)

Example using Hugging Face CLI:
```bash
cd systems/Unify/main/models

# Download tokenizer
huggingface-cli download heilerich/llama-tokenizer-fast --local-dir tokenizer

# Download embedding model
huggingface-cli download sentence-transformers/all-MiniLM-L6-v2 --local-dir embedding
```

### 4. Verify Data Files

Ensure all benchmark datasets are present in the `Data/` directory:
```bash
ls -la Data/
# Should contain: Med/, Player/, Art/, Legal/, Finan/
```

## Running Unify Queries

### Quick Start

Run Unify on specific query types:

```bash
# Run Unify on simple queries
python run_challenging_queries.py --systems unify --query-types simple

# Run on filter queries
python run_challenging_queries.py --systems unify --query-types filter

# Run on all query types
python run_challenging_queries.py --systems unify --query-types all
```

### Full Example

```bash
# Run all systems including Unify
python run_challenging_queries.py --systems quest uqe unify --query-types simple filter projection

# Resume from checkpoint
python run_challenging_queries.py --resume --run-id 20251210_120000

# Use DEBUG logging for troubleshooting
python run_challenging_queries.py --systems unify --query-types simple --log-level DEBUG
```

## Unify Integration Details

### System Configuration

The UnifyRunner class in `run_challenging_queries.py` configures:

- **Model**: `qwen2.5:7b-instruct` via Ollama
- **Base URL**: `http://localhost:11434/v1`
- **API Key**: `ollama` (dummy key for local inference)

### Query Processing Pipeline

1. **Preprocessing**: Loads and chunks documents, builds semantic index
2. **Semantic Parsing**: Uses LLM to parse query into structured form
3. **Plan Generation**: Recursively decomposes query into operators
4. **Physical Planning**: Optimizes operator execution order
5. **Execution**: Runs operators and collects results

### Supported Query Types

Unify should support all query types defined in the benchmark:
- **Simple**: Basic projections
- **Filter**: Selection with predicates
- **Projection**: Multi-attribute extraction
- **Join**: Cross-document operations
- **Aggregation**: Grouping and aggregation
- **Union**: Set operations

However, some complex operations may have limitations depending on Unify's current implementation.

## Output Structure

Results are saved to `results/challenging_queries/{RUN_ID}/`:

```
results/challenging_queries/{RUN_ID}/
├── preprocessing/
│   └── unify/
│       └── {DATASET}/{ENTITY}/metadata.json
├── results/
│   └── unify/
│       ├── simple/
│       ├── filter/
│       ├── projection/
│       └── ...
├── run.log
├── checkpoint.json
├── summary.json
└── detailed_report.json
```

Each query result includes:
- `result.csv`: Query results as DataFrame
- `metadata.json`: Execution stats (timing, status, etc.)
- `query.json`: Original query definition

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'unify'"

**Solution**: Ensure you're in the correct directory and Unify path is added to sys.path:
```bash
cd systems/Unify/main
# Or set PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/systems/Unify/main"
```

### Issue: "Connection refused" for Ollama

**Solution**: Start Ollama server:
```bash
ollama serve
# In another terminal:
ollama pull qwen2.5:7b-instruct
```

### Issue: "Model not found" for tokenizer/embedding

**Solution**: Verify model directories exist:
```bash
ls systems/Unify/main/models/tokenizer/
ls systems/Unify/main/models/embedding/
```

### Issue: Memory/CUDA errors

**Solution**: Reduce batch size or use CPU:
```bash
# Check GPU availability
python -c "import torch; print(torch.cuda.is_available())"

# Set to use CPU (slower but more stable)
export CUDA_VISIBLE_DEVICES=""
```

### Issue: Query execution timeout

**Solution**: Increase timeout or optimize data size:
- Ensure data files aren't too large (check token counts)
- Check Ollama is running smoothly: `curl http://localhost:11434/api/tags`
- Review logs for specific errors: `results/challenging_queries/{RUN_ID}/run.log`

## Configuration Reference

### Environment Variables

```bash
# Model Configuration (automatically set in code)
UNIFY_MODEL="qwen2.5:7b-instruct"
UNIFY_BASE_URL="http://localhost:11434/v1"

# Optional: Override default paths
UNIFY_TOKENIZER_PATH="/path/to/tokenizer"
UNIFY_EMBEDDING_PATH="/path/to/embedding"
```

### Unify Code Configuration

In `run_challenging_queries.py`, UnifyRunner uses:
```python
self.ollama_model = "qwen2.5:7b-instruct"
self.ollama_base_url = "http://localhost:11434/v1"
self.ollama_api_key = "ollama"
```

To modify these, edit the UnifyRunner `_ensure_init()` method.

## Performance Expectations

### Typical Performance on UDA-Bench

- **Query types**: All types should be supported (simple, filter, projection, join, aggregation, union)
- **Accuracy**: Varies by dataset complexity; expect 0.4-0.8 F1 on complex datasets
- **Cost**: Typically 2-5K tokens per document per query (depends on strategy)
- **Latency**: 5-30 seconds per query depending on document size and complexity

### Optimization Tips

1. **Chunking Strategy**: Adjust chunk size in `ChunkExtractor`
2. **Embedding Model**: Use higher-quality embeddings for better retrieval
3. **LLM Selection**: Qwen2.5:7b is fast; consider larger models for accuracy
4. **Parallel Execution**: Unify supports concurrent operator execution

## Comparing with Other Systems

Unify differs from other systems in UDA-Bench:

| Aspect | Unify | QUEST | UQE | Palimpzest |
|--------|-------|-------|-----|------------|
| Query Interface | Natural language → logical plan | SQL-like | SQL-like | Python API |
| Plan Generation | Iterative operator matching | Direct parsing | Direct parsing | Direct parsing |
| Optimization | Semantic cost model | Filter reordering | Sampling-based | Model selection |
| LLM Integration | Full pipeline | For extraction | For filtering | Multi-agent |

## Citation

If you use Unify in your research, please cite:

```bibtex
@inproceedings{wang2025unify,
  title={Unify: An unstructured data analytics system},
  author={Wang, Jiayi and Feng, Jianhua},
  booktitle={2025 IEEE 41st International Conference on Data Engineering (ICDE)},
  year={2025},
}
```

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the Unify paper: `systems/Unify/unify.pdf.md`
3. Check Unify README: `systems/Unify/README.md`
4. Examine logs: `results/challenging_queries/{RUN_ID}/run.log`


