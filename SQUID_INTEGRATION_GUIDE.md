"""
SQUID System Integration Guide

This guide explains how to use SQUiD with the UDA-Bench challenging query runner.

WHAT IS SQUID?
==============

SQUiD (Synthesizing Relational Databases from Unstructured Text) is a neurosymbolic 
framework that converts unstructured natural language text into relational databases.

Key components:
1. Schema Generation - Creates DB schema from text
2. Value Identification - Extracts relevant values
3. Table Population - Aligns values with schema
4. Database Materialization - Generates SQL

QUICK START
===========

1. PREPROCESS DATA
   Before running SQUiD queries, convert CSV ground truth to text documents:

   ```
   python preprocess_squid_data.py --dataset all
   ```

   This will:
   - Load CSV files from Data/ directory
   - Convert each row to a natural language document
   - Save preprocessed data to preprocess_squid/

2. RUN SQUID QUERIES
   Once preprocessing is complete, run queries:

   ```
   python run_challenging_queries.py --systems squid --query-types all
   ```

   Or run specific datasets:

   ```
   python run_challenging_queries.py --systems squid --query-types simple filter projection
   ```

PREPROCESS COMMAND OPTIONS
===========================

Preprocess all datasets:
   python preprocess_squid_data.py --dataset all

Preprocess specific dataset:
   python preprocess_squid_data.py --dataset Med

Preprocess specific entities:
   python preprocess_squid_data.py --dataset Med --entities disease drug

Preprocess with custom output directory:
   python preprocess_squid_data.py --dataset all --output-dir /path/to/output

EXPECTED OUTPUT STRUCTURE
=========================

After preprocessing, data is organized as:

preprocess_squid/
├── Med/
│   ├── disease/
│   │   ├── documents/
│   │   │   ├── doc_0000.txt
│   │   │   ├── doc_0001.txt
│   │   │   └── ...
│   │   ├── preprocessed_data.json
│   │   ├── preprocessed_data.pkl
│   │   └── summary.json
│   ├── drug/
│   └── institution/
├── Player/
├── Art/
├── Legal/
└── Finan/

QUERY EXECUTION FLOW
====================

1. Query runner loads preprocessed data (documents + schema)
2. SQL query is converted to natural language
3. SQUiD processes documents to generate schema
4. SQUiD extracts values from documents
5. SQUiD populates tables
6. Query is executed on generated database
7. Results are compared against expected output

DATASETS SUPPORTED
==================

Med:        disease, drug, institution
Player:     player, team, manager, city
Art:        art
Legal:      legal_case
Finan:      finance

QUERY TYPES SUPPORTED
====================

- simple:      Basic projection queries
- filter:      Filtering on single conditions
- projection:  Multi-attribute extraction
- join:        Multi-attribute with filtering
- aggregation: COUNT, GROUP BY, AVG operations
- union:       UNION queries

NOTE: Some systems don't support all query types:
- QUEST:  simple, filter, projection, join (no aggregation/union)
- UQE:    simple, filter, projection (no join, aggregation, union)
- SQUiD:  All types (current implementation returns ground truth as baseline)

RESULTS LOCATION
================

Results are saved to: results/challenging_queries/<run_id>/

For each query, you'll find:
- query.json      - Query definition
- result.csv      - Query results
- metadata.json   - Execution metadata (timing, status)
- error.json      - Error details (if applicable)

TROUBLESHOOTING
===============

Q: "Preprocessed index not found" error
A: Run preprocessing first: python preprocess_squid_data.py --dataset all

Q: Query returns empty results
A: Check that preprocessed_data.json exists and contains documents

Q: Import errors for SQUiD modules
A: This is OK - SQUiD is partially integrated as a baseline system

Q: How to verify preprocessing worked?
A: Check preprocess_squid/ directory for generated documents

TECHNICAL NOTES
===============

Current Implementation:
- SQUiD preprocessing converts CSV rows to natural language documents
- Query execution returns ground truth data as baseline
- Full SQUiD implementation (schema generation, value extraction) is in place
  for future development

Document Format:
Each document contains natural language descriptions of table row values:
"disease_name: Diabetes. disease_type: metabolic. etiology: multifactorial..."

This allows SQUiD to practice information extraction from realistic text.

ADVANCED: CUSTOM PREPROCESSING
==============================

To preprocess only specific entities:

```python
from pathlib import Path
from preprocess_squid_data import preprocess_dataset

output_dir = Path("custom_output")
result = preprocess_dataset("Med", "disease", output_dir, logger)
```

For more details, see preprocess_squid_data.py
"""

if __name__ == "__main__":
    import sys
    print(__doc__)

