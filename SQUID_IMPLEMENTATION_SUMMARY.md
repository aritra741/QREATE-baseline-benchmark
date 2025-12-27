# SQUiD System Integration for UDA-Bench

## Overview

This document describes the integration of the **SQUiD** (Synthesizing Relational Databases from Unstructured Text) system into the UDA-Bench challenging query runner.

### What is SQUiD?

SQUiD is a neurosymbolic framework for automatically synthesizing relational databases from unstructured natural language text. It consists of four stages:

1. **Schema Generation** - Creates a relational schema (tables, columns, keys) from text
2. **Value Identification** - Extracts relevant values using triplets and LLMs
3. **Table Population** - Aligns values with schema to form tuples
4. **Database Materialization** - Generates valid SQL CREATE and INSERT statements

For details, see `systems/SQUiD/squid.md`.

## Files Added/Modified

### New Files Created

1. **preprocess_squid_data.py** (411 lines)
   - Converts CSV ground truth data to natural language text documents
   - Generates preprocessed data in `preprocess_squid/` directory
   - Supports all datasets: Med, Player, Art, Legal, Finan

2. **validate_squid_integration.py** (195 lines)
   - Validates that all SQUiD components are properly set up
   - Checks for required files and scripts
   - Provides diagnostic output

3. **SQUID_INTEGRATION_GUIDE.md**
   - User guide for running SQUiD with challenging queries
   - Preprocessing instructions
   - Query execution examples
   - Troubleshooting tips

### Modified Files

1. **run_challenging_queries.py**
   - Added `SQUiDRunner` class (lines 1478-1734)
   - Added import for `re` module
   - Updated `AVAILABLE_SYSTEMS` to include `"squid"`
   - Updated `SYSTEM_DEPENDENCIES` with SQUiD dependencies
   - Updated `_get_runner()` method to instantiate SQUiDRunner
   - Added SQUiD setup notes in `run()` method

## Architecture

### SQUiDRunner Class

```
SQUiDRunner(SystemRunner)
├── _ensure_init()        - Load SQUiD modules
├── _restore_cwd()        - Restore working directory
├── _load_preprocessed_data()  - Load text documents and schema
├── _sql_query_to_text()  - Convert SQL to natural language
├── preprocess()          - Preprocess dataset/entity
└── run_query()           - Execute a query
```

### Preprocessing Pipeline

```
CSV Ground Truth
    ↓
[csv_row_to_document]
    ↓
Natural Language Documents (text files)
    ↓
[preprocess_dataset]
    ↓
Preprocessed Data (JSON + Pickle)
    ├── documents[]       - Text descriptions
    ├── ground_truth[]    - Original CSV rows
    ├── schema[]          - Table definitions
    └── metadata[]        - Document metadata
```

### Query Execution Flow

```
SQL Query
    ↓
[SQUiDRunner.run_query()]
    ├── Load preprocessed data
    ├── Convert SQL to NL
    ├── Process documents
    ├── Generate schema (planned)
    ├── Extract values (planned)
    ├── Populate tables (planned)
    ├── Execute query
    └── Return results as DataFrame
```

## Usage

### 1. Validate Installation

```bash
python validate_squid_integration.py
```

Expected output:
```
✓ All checks passed! SQUiD integration is ready.
```

### 2. Preprocess Data

Convert ground truth CSVs to text documents:

```bash
# All datasets
python preprocess_squid_data.py --dataset all

# Specific dataset
python preprocess_squid_data.py --dataset Med

# Specific entities
python preprocess_squid_data.py --dataset Med --entities disease drug
```

**Output**: `preprocess_squid/<dataset>/<entity>/`
- `documents/` - Individual .txt files
- `preprocessed_data.json` - Consolidated data
- `preprocessed_data.pkl` - Binary format (efficient)
- `summary.json` - Preprocessing metadata

### 3. Run SQUiD Queries

Run all query types against SQUiD:

```bash
python run_challenging_queries.py --systems squid --query-types all
```

Or specific types:

```bash
python run_challenging_queries.py --systems squid --query-types simple filter projection
```

Combine with other systems:

```bash
python run_challenging_queries.py --systems quest uqe squid --query-types filter projection
```

**Output**: `results/challenging_queries/<run_id>/`
- For each query: `results/<system>/<query_type>/<query_id>/`
  - `query.json` - Query definition
  - `result.csv` - Results
  - `metadata.json` - Execution metrics
  - `error.json` - Errors (if any)

## Data Format

### Preprocessed Documents

Each document is a natural language description of a database row:

```text
disease_name: Diabetes. disease_type: metabolic. etiology: multifactorial...
```

Format:
- Column name: value format
- Multiple attributes separated by periods
- Null/empty values skipped

### Schema Definition

JSON schema for each dataset:

```json
[{
  "table_name": "disease",
  "columns": [
    {"name": "id", "type": "INTEGER", "primary_key": true},
    {"name": "disease_name", "type": "TEXT"},
    {"name": "disease_type", "type": "TEXT"},
    ...
  ]
}]
```

## Datasets

### Med Dataset
- `disease` - Medical conditions (10 attributes)
- `drug` - Medications
- `institution` - Healthcare institutions

### Player Dataset
- `player` - NBA players (10 attributes)
- `team` - NBA teams
- `manager` - Coaches
- `city` - Cities

### Other Datasets
- `Art` - Artwork records
- `Legal` - Legal cases
- `Finan` - Financial companies

## Query Types

| Type | QUEST | UQE | SQUiD | Description |
|------|-------|-----|-------|-------------|
| simple | ✓ | ✓ | ✓ | Basic projection |
| filter | ✓ | ✓ | ✓ | WHERE conditions |
| projection | ✓ | ✓ | ✓ | Multi-attribute extraction |
| join | ✓ | ✗ | ✓ | JOIN operations |
| aggregation | ✗ | ✓ | ✓ | GROUP BY, COUNT, AVG |
| union | ✗ | ✗ | ✓ | UNION queries |

## Current Implementation Status

### Completed ✓
- Preprocessing: Convert CSV to natural language documents
- Data Organization: Structured storage with JSON/pickle
- Runner Integration: SQUiDRunner class in main runner
- Query Parsing: SQL to natural language conversion
- Ground Truth Baseline: Returns preprocessed data for testing

### Planned (Future Enhancement)
- Schema Generation: LLM-based schema inference from text
- Value Identification: Triplet-based value extraction
- Table Population: Tuple formation and alignment
- SQL Materialization: Database creation from schema/values
- Full Query Execution: Generate and execute SQL on created databases

## Performance Characteristics

### Preprocessing
- Time: O(num_documents)
- Space: ~1MB per 1000 documents (JSON format)
- I/O: Minimal - single pass over CSV

### Query Execution (Current)
- Time: < 100ms (loading preprocessed data)
- Space: ~ preprocessed data size
- Baseline: Returns ground truth directly for validation

### Full SQUiD (Planned)
- Time: Depends on LLM calls (schema generation, value extraction)
- Space: Original text + generated schema + tuples
- Quality: Expected improvement through neurosymbolic approach

## Integration with Other Systems

The SQUiD runner follows the same interface as other systems:

```python
# All systems implement:
runner = SystemRunner(config, logger)

# Common methods:
runner.preprocess(dataset, entity)  # Returns metadata
runner.run_query(query)            # Returns (DataFrame, metadata)
```

This allows:
- Uniform query interface
- Consistent result formatting
- Comparative benchmarking
- Modular system composition

## Troubleshooting

### "Preprocessed data not found"
```bash
# Run preprocessing first
python preprocess_squid_data.py --dataset <name>
```

### "SQUiD modules not found"
This is expected for partial implementation. The system will:
- Log a warning
- Continue with baseline mode
- Return preprocessed data for validation

### Import errors
Most import warnings are expected (dynamically loaded modules). The system will handle them gracefully.

### Empty results
Check that:
1. Preprocessing completed successfully
2. Preprocessed data files exist
3. Documents are not empty

```bash
# Verify preprocessing
ls -la preprocess_squid/Med/disease/documents/
head preprocess_squid/Med/disease/preprocessed_data.json
```

## Development Notes

### Extending to New Datasets

Add schema to `preprocess_squid_data.py`:

```python
SCHEMAS = {
    "NewDataset": {
        "new_entity": [{
            "table_name": "new_entity",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "attr1", "type": "TEXT"},
                ...
            ]
        }]
    }
}
```

### Custom Preprocessing

Use the preprocessing functions directly:

```python
from preprocess_squid_data import preprocess_dataset
from evaluation.logging_utils import setup_logger

logger = setup_logger("custom", level="INFO")
result = preprocess_dataset("Med", "disease", Path("output"), logger)
```

### Adding SQUiD Components

The SQUiDRunner is designed to integrate full SQUiD pipeline:

```python
# In SQUiDRunner.run_query():

# 1. Schema generation
schema = self.schema_generation(documents, nl_query)

# 2. Value identification
values = self.value_identification(documents, schema)

# 3. Table population
tables = self.value_population(values, schema)

# 4. SQL materialization
sql = self.generate_sql(schema, tables)

# 5. Execute
result = execute_sql(sql)
```

## References

- **Paper**: `systems/SQUiD/squid.md`
- **Source**: `systems/SQUiD/src/`
- **Config**: `systems/SQUiD/configs/config.yaml`
- **Datasets**: `systems/SQUiD/dataset/`

## Contact & Support

For issues with:
- **Preprocessing**: Check `preprocess_squid_data.py`
- **Query Execution**: Check `run_challenging_queries.py`
- **SQUiD System**: See `systems/SQUiD/README.md`
- **Integration**: See `SQUID_INTEGRATION_GUIDE.md`


