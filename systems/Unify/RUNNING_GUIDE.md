# How to Run the Unify Pipeline

This guide explains how to run the Unify system for unstructured data analytics.

## Overview

The Unify pipeline follows the architecture shown in the paper:
1. **Offline Preprocessing**: Build indexes for data and operators
2. **Online Planning**: Convert NL queries to logical plans, then optimize to physical plans
3. **Plan Execution**: Execute the plan and return results

## Prerequisites

### 1. Environment Setup

```bash
# Ensure Python 3.10+ is installed
python3 --version  # Should be 3.10 or later

# Create and activate a virtual environment (standard library venv)
python3 -m venv ~/.venvs/unify
source ~/.venvs/unify/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Download Models

You need three types of models:

#### A. LLM Model (via Ollama)
- Install Ollama from the official download page: https://ollama.com/download  
- Pull the Qwen 3 8B chat model from the Ollama library entry: https://ollama.com/library/qwen3

```bash
# After installing Ollama
ollama pull qwen3:8b
```

#### B. Tokenizer Model
- Clone the tokenizer bundled with the official Qwen3-8B release on Hugging Face: https://huggingface.co/Qwen/Qwen3-8B

```bash
git clone https://huggingface.co/Qwen/Qwen3-8B ~/models/Qwen3-8B
```

#### C. Embedding Model (Sentence Transformer)
- Download the all-MiniLM-L6-v2 sentence-transformer from Hugging Face: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2

```bash
git clone https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 ~/models/all-MiniLM-L6-v2
```

### 3. Prepare Dataset

Download datasets from the [Google Drive link](https://drive.google.com/drive/folders/1K69FGBb77piIsjKdYPO9xbvPhXg9yDyd?usp=drive_link) mentioned in the README, or prepare your own unstructured text documents.

## Running the Pipeline

### Method 1: Direct Execution (Recommended for Testing)

Run the pipeline directly using `unify.py`:

```bash
cd main

python unify.py \
  --llm_model_path qwen3:8b \
  --tokenizer_path /path/to/tokenizer \
  --sentence_model_path /path/to/sentence_model \
  --doc_path /path/to/docs \
  --query "Your natural language query here" \
  --api_base http://localhost:11434/v1
```

**Parameters:**
- `--llm_model_path`: Ollama model name (e.g., `qwen3:8b`, `llama3.1:8b`)
- `--tokenizer_path`: Path to the tokenizer directory
- `--sentence_model_path`: Path to the sentence transformer model directory
- `--doc_path`: Path to your document dataset directory
- `--query`: Your natural language query
- `--api_base`: Ollama API base URL (default: `http://localhost:11434/v1`)
- `--api_key`: Optional API key (default: "EMPTY" for Ollama)

**Example Query:**
```bash
python unify.py \
  --llm_model_path qwen3:8b \
  --tokenizer_path ~/models/Qwen3-8B \
  --sentence_model_path ~/models/all-MiniLM-L6-v2 \
  --doc_path ~/data/wikipedia_docs \
  --query "Compare the number of documents for boxing and swimming among those with more than 10,000 views; return the sport with fewer documents"
```

### Method 2: Using the Shell Script

Edit `main/run.sh` with your paths, then run:

```bash
cd main
bash run.sh
```

### Method 3: Flask API Server (For Web Interface)

Start the Flask API server:

```bash
cd main
python API.py
```

The server will run on `http://0.0.0.0:8000`.

**API Endpoint:**
```bash
POST http://localhost:8000/process_query
Content-Type: application/json

{
  "query": "Your natural language query",
  "dataset_path": "/path/to/docs",
  "model_path": "qwen3:8b",
  "tokenizer_path": "/path/to/tokenizer",
  "sentence_model_path": "/path/to/sentence_model",
  "openai_api_key": "EMPTY",
  "openai_api_base": "http://localhost:11434/v1"
}
```

## Pipeline Execution Flow

When you run a query, Unify executes the following steps:

### 1. **Semantic Parsing**
- Parses the natural language query
- Extracts entities, conditions, and semantic elements
- Transforms query into logical representation with placeholders

### 2. **Logical Plan Generation** (Iterative)
   - **Operator Matching**: Uses embedding similarity to find relevant operators
   - **Operator Re-ranking**: LLM evaluates operator applicability
   - **Query Reduction**: Applies selected operator to reduce the query
   - Repeats until query is fully decomposed

### 3. **Physical Plan Optimization**
   - Selects physical implementations for each operator
   - Optimizes execution order using cost model
   - Estimates cardinality using semantic methods

### 4. **Plan Execution**
   - Executes operators in topological order (parallel when possible)
   - Processes intermediate results
   - Dynamically adjusts plan if needed
   - Returns final answer

## Output

The system will output:
- **Transformed Question**: Query with placeholders
- **Parsed Results**: Extracted semantic elements
- **Final Plan**: DAG of operators to execute
- **Execution Details**: Intermediate results for each operator
- **Final Result**: The answer to your query

## Troubleshooting

### Ollama Not Running
```bash
# Start Ollama service
ollama serve

# In another terminal, verify model is available
ollama list
```

### Model Path Issues
- Ensure tokenizer path points to a directory containing `tokenizer.json` or `tokenizer_config.json`
- Ensure sentence model path points to a valid sentence-transformers model directory

### Memory Issues
- For large models, ensure sufficient GPU memory
- Consider using smaller models (e.g., 8B instead of 70B)
- Adjust `CUDA_VISIBLE_DEVICES` in `unify.py` if needed

### Dataset Format
- Documents should be in text files
- The system will automatically chunk and index them
- Supported formats: `.txt`, `.pdf` (via PyMuPDF)

## Example Workflow

```bash
# 1. Start Ollama (if not running)
ollama serve

# 2. Pull a model
ollama pull qwen3:8b

# 3. Run a query
cd main
python unify.py \
  --llm_model_path qwen3:8b \
  --tokenizer_path ~/models/Qwen2.5-7B-Instruct \
  --sentence_model_path ~/models/all-MiniLM-L6-v2 \
  --doc_path ~/data/my_documents \
  --query "Count the number of documents about machine learning"
```

## Architecture Alignment

The execution follows the architecture diagram:
- **Offline Preprocessing**: Happens automatically when you first load documents (chunking, embedding, indexing)
- **Online Planning**: Semantic parsing → Operator matching → Re-ranking → Query reduction (iterative)
- **Plan Execution**: Topological execution with parallel operators and dynamic replanning

For more details, refer to the paper and the README.md file.

