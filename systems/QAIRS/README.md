# QAIRS: Query-Aware Incremental Relational Synthesis

**Model:** Qwen 2.5 (7B-Instruct) via Ollama  
**Key Principle:** Workload-Driven Optimization (MQO) & Schema-Guided Sieve

## Overview

QAIRS is a workload-driven text-to-database extraction system that uses:
- **The Sieve**: A lightweight preprocessing index for fast chunk filtering
- **Metadata Registry**: Tracks which predicates have been materialized
- **Multi-Query Optimization (MQO)**: Batches overlapping queries to minimize LLM calls
- **View Synthesis**: Extracts denormalized views to guarantee referential integrity

## Architecture

### Phase 1: Preprocessing (Build)
1. **Dictionary Expansion**: One-time LLM call to generate synonyms
2. **Sieve Construction**: Build fast lookup index using FlashText, Regex, and NER

### Phase 2: Workload Planning (Lattice)
1. **SQL Parsing**: Parse queries using `sqlglot` into AST
2. **DNF Normalization**: Convert predicates to Disjunctive Normal Form
3. **Subsumption Analysis**: Build DAG using `networkx` to identify query relationships
4. **Sibling Merging**: Merge categorical predicates on same column (key optimization)
5. **Plan Generation**: Create minimal covering plan with merged tasks

### Phase 3: Runtime Execution (Engine)
1. **Router**: Check metadata registry for subsumption
2. **Pruning**: Use sieve to filter candidate chunks
3. **View Synthesis**: Extract data via Qwen 2.5
4. **State Update**: Update registry and database

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize the system
python init_system.py --corpus-path /path/to/corpus \
  --dictionary Denied Paid Approved --expand-dict

# Analyze a workload (offline planning)
python analyze_workload.py --workload example_workload.sql \
  --output execution_plan.json

# Run a query
python run_query.py --sql "SELECT * FROM Claims WHERE status='Denied'" \
  --corpus-path /path/to/corpus

# Test the planner
python test_planner.py
```

## Components

- `sieve.py`: Preprocessing index construction (FlashText + Regex)
- `registry.py`: Metadata registry management (PostgreSQL)
- `planner.py`: Advanced MQO planner (sqlglot + networkx)
- `extractor.py`: LLM-based extraction engine (Qwen 2.5)
- `query_engine.py`: Main query execution interface
- `llm_client.py`: Ollama client with JSON mode
- `config.py`: System configuration
- `models.py`: Data models and schemas

## Utilities

- `init_system.py`: System initialization script
- `run_query.py`: Query execution script
- `analyze_workload.py`: Offline workload analysis
- `test_system.py`: System tests
- `test_planner.py`: Planner-specific tests

## Configuration

Edit `config.yaml` to configure:
- Ollama endpoint and model
- PostgreSQL connection
- Sieve parameters
- Extraction prompts
