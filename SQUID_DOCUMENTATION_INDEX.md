# SQUiD Integration - Complete Documentation Index

This document provides an index of all files related to the SQUiD system integration into UDA-Bench.

## Overview

**What**: Integration of SQUiD (Synthesizing Relational Databases from Unstructured Text) into the UDA-Bench challenging query runner.

**Why**: To enable testing and evaluation of SQUiD's ability to synthesize relational databases from natural language text documents.

**How**: Through a preprocessing pipeline that converts CSV ground truth to text, and a SQUiDRunner that executes queries.

## Core Implementation Files

### 1. **preprocess_squid_data.py** (411 lines)
   - **Purpose**: Main preprocessing pipeline
   - **Location**: `/Users/aritramazumder/Documents/UDA-Bench-main/`
   - **Key Functions**:
     - `csv_row_to_document()` - Convert CSV rows to NL documents
     - `preprocess_dataset()` - Process a dataset/entity
     - `main()` - CLI interface
   - **Usage**:
     ```bash
     python preprocess_squid_data.py --dataset all
     python preprocess_squid_data.py --dataset Med --entities disease
     ```
   - **Output**: `preprocess_squid/<dataset>/<entity>/{documents/, preprocessed_data.json, ...}`

### 2. **run_challenging_queries.py** (Modified, +257 lines)
   - **Purpose**: Main query execution framework
   - **Location**: `/Users/aritramazumder/Documents/UDA-Bench-main/`
   - **Changes**:
     - Added `import re` for SQL parsing
     - Added `SQUiDRunner` class (lines 1478-1734)
     - Updated `AVAILABLE_SYSTEMS` to include `"squid"`
     - Updated `_get_runner()` method
   - **Usage**:
     ```bash
     python run_challenging_queries.py --systems squid --query-types all
     ```

### 3. **SQUiDRunner Class** (257 lines, in run_challenging_queries.py)
   - **Purpose**: System runner for SQUiD queries
   - **Methods**:
     - `_ensure_init()` - Initialize SQUiD modules
     - `_load_preprocessed_data()` - Load text documents
     - `_sql_query_to_text()` - Convert SQL to natural language
     - `preprocess()` - Preprocess dataset/entity
     - `run_query()` - Execute a query
   - **Design**: Extends `SystemRunner` base class
   - **Integration**: Works with all other systems (Quest, UQE, Unify)

## Validation Tools

### 4. **validate_squid_integration.py** (195 lines)
   - **Purpose**: Verify SQUiD integration is properly set up
   - **Location**: `/Users/aritramazumder/Documents/UDA-Bench-main/`
   - **Checks**:
     - Preprocessing script exists and has required functions
     - SQUiDRunner is properly integrated
     - SQUiD system files are present
     - Ground truth data files exist
     - Integration guide is present
   - **Usage**:
     ```bash
     python validate_squid_integration.py
     ```
   - **Output**: Pass/Fail for each component

## Documentation Files

### User Guides

#### 5. **SQUID_QUICK_REFERENCE.py**
   - **Purpose**: Quick command reference
   - **Contents**:
     - Common commands for preprocessing & querying
     - Directory structure overview
     - Common issues & fixes
     - System comparison table
   - **Usage**:
     ```bash
     python SQUID_QUICK_REFERENCE.py
     # or
     cat SQUID_QUICK_REFERENCE.py | grep -A5 "PREPROCESSING"
     ```

#### 6. **SQUID_INTEGRATION_GUIDE.md**
   - **Purpose**: User guide for SQUiD integration
   - **Contents**:
     - Quick start instructions
     - Command-line options
     - Expected output structure
     - Query execution flow
     - Dataset & query type info
     - Troubleshooting guide
     - Technical notes
   - **Audience**: End users

### Technical Documentation

#### 7. **SQUID_IMPLEMENTATION_SUMMARY.md**
   - **Purpose**: Comprehensive technical documentation
   - **Contents**:
     - Overview of SQUiD system
     - File listing and modifications
     - Architecture & design patterns
     - Data formats and schemas
     - Current implementation status
     - Performance characteristics
     - Integration details
     - Development notes
   - **Audience**: Developers, architects

#### 8. **SQUID_COMPLETION_REPORT.md**
   - **Purpose**: Implementation completion report
   - **Contents**:
     - Summary of what was done
     - Detailed feature descriptions
     - Three-tier system architecture
     - Design patterns used
     - Dataset and query support table
     - Implementation status (completed vs planned)
     - Testing recommendations
     - File summary
     - Next steps for full implementation
   - **Audience**: Project managers, stakeholders

## Existing Files (Reference)

### SQUiD Source Code
- **systems/SQUiD/squid.md** - Original SQUiD paper and documentation
- **systems/SQUiD/src/** - SQUiD implementation modules:
  - `database_generation.py` - SQL generation
  - `schema_generation.py` - Schema inference
  - `value_identification.py` - Value extraction
  - `value_population.py` - Table population
  - `model.py` - LLM integration
  - `utils.py` - Utility functions

### Ground Truth Data
- **Data/Med/** - Medical datasets (disease, drug, institution CSV files)
- **Data/Player/** - NBA player datasets (player, team, manager, city)
- **Data/Art/** - Artwork dataset (Art.csv)
- **Data/Legal/** - Legal cases dataset (Legal.csv)
- **Data/Finan/** - Financial dataset (Finan.csv)

## File Organization After Setup

```
/Users/aritramazumder/Documents/UDA-Bench-main/
├── preprocess_squid_data.py                    # Main preprocessing script
├── run_challenging_queries.py                  # Query runner (modified)
├── validate_squid_integration.py               # Validation script
├── SQUID_QUICK_REFERENCE.py                    # Quick reference
├── SQUID_INTEGRATION_GUIDE.md                  # User guide
├── SQUID_IMPLEMENTATION_SUMMARY.md             # Technical docs
├── SQUID_COMPLETION_REPORT.md                  # Completion report
│
├── preprocess_squid/                           # Preprocessing output
│   ├── Med/
│   │   ├── disease/
│   │   ├── drug/
│   │   └── institution/
│   ├── Player/
│   ├── Art/
│   ├── Legal/
│   └── Finan/
│
└── results/
    └── challenging_queries/
        └── <run_id>/
            └── results/
                └── squid/
                    ├── simple/
                    ├── filter/
                    ├── projection/
                    ├── join/
                    ├── aggregation/
                    └── union/
```

## Quick Links

### To Get Started
1. Read: **SQUID_QUICK_REFERENCE.py** (2 min)
2. Validate: `python validate_squid_integration.py` (1 min)
3. Preprocess: `python preprocess_squid_data.py --dataset all` (5-10 min)
4. Run: `python run_challenging_queries.py --systems squid` (2-10 min)

### For Detailed Information
- User Guide: **SQUID_INTEGRATION_GUIDE.md**
- Technical Details: **SQUID_IMPLEMENTATION_SUMMARY.md**
- Implementation Status: **SQUID_COMPLETION_REPORT.md**

### For Developers
- SQUiD Source: **systems/SQUiD/src/**
- SQUiD Paper: **systems/SQUiD/squid.md**
- Integration Code: **run_challenging_queries.py** (SQUiDRunner class)

## Key Concepts

### Preprocessing
Converts CSV ground truth data to natural language documents that SQUiD can process:
```
CSV Row → Natural Language → Preprocessed Data
```

### Query Execution
Processes natural language queries against text documents:
```
SQL Query → NL Conversion → Document Processing → Results
```

### Integration
SQUiD is integrated as a system runner, similar to Quest, UQE, and Unify:
```
run_challenging_queries.py
├── QuestRunner
├── UQERunner
├── UnifyRunner
├── SQUiDRunner (NEW)
└── LotusRunner
```

## Commands by Use Case

### Use Case 1: Test Preprocessing
```bash
python preprocess_squid_data.py --dataset Med --log-level DEBUG
ls preprocess_squid/Med/disease/documents/ | head
cat preprocess_squid/Med/disease/preprocessed_data.json | python -m json.tool | head -20
```

### Use Case 2: Run Simple Query
```bash
python run_challenging_queries.py --systems squid --query-types simple
cat results/challenging_queries/*/results/squid/simple/*/result.csv
```

### Use Case 3: Compare Systems
```bash
python run_challenging_queries.py --systems quest uqe squid --query-types projection
# Compare results across systems
```

### Use Case 4: Full Benchmarking
```bash
python run_challenging_queries.py --systems all --query-types all --log-level INFO
# Generate comprehensive benchmarking report
```

## Support Resources

### For "How do I...?" questions
- See: **SQUID_INTEGRATION_GUIDE.md** (Troubleshooting section)

### For "What should I change to...?" questions
- See: **SQUID_IMPLEMENTATION_SUMMARY.md** (Development Notes section)

### For "What's the status of...?" questions
- See: **SQUID_COMPLETION_REPORT.md** (Implementation Status section)

### For quick command syntax
- See: **SQUID_QUICK_REFERENCE.py** (Common commands section)

## Integration Layers

### Layer 1: Data Layer
- CSV files → Natural language conversion
- Preprocessed data storage (JSON/pickle)
- Ground truth preservation

### Layer 2: Execution Layer
- SQL query parsing
- SQL to natural language conversion
- Query execution framework
- Result formatting

### Layer 3: Extension Layer
- SQUiD schema generation (planned)
- Value identification (planned)
- Table population (planned)
- SQL materialization (planned)

## Performance Targets

### Preprocessing
- Time: < 1 minute for all datasets
- Space: ~ 50-100MB for preprocessed data
- I/O: Single pass over CSV files

### Query Execution (Baseline)
- Time: < 100ms per query
- Space: < preprocessed data size
- Results: Ground truth baseline for validation

### Full SQUiD (Planned)
- Time: 2-10s per query (depends on LLM calls)
- Space: Original text + generated schema
- Quality: Improved accuracy through neurosymbolic approach

## Status & Timeline

- ✓ **Complete**: Preprocessing pipeline
- ✓ **Complete**: SQUiDRunner integration
- ✓ **Complete**: Documentation
- → **Planned**: Full SQUiD implementation
- → **Planned**: Performance optimization
- → **Planned**: Extended evaluation

## Contact

For issues, questions, or contributions related to SQUiD integration:
1. Check documentation files in this index
2. Run validate_squid_integration.py for diagnostics
3. Review SQUID_COMPLETION_REPORT.md for known limitations

---

**Last Updated**: December 2024
**Integration Version**: 1.0
**SQUiD Status**: Baseline implementation with planned extensions

