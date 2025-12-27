"""
SQUiD Integration - Quick Reference Card

PREPROCESSING
=============

Preprocess all datasets:
    python preprocess_squid_data.py --dataset all

Preprocess specific dataset:
    python preprocess_squid_data.py --dataset Med

Preprocess specific entities:
    python preprocess_squid_data.py --dataset Med --entities disease drug

With debugging:
    python preprocess_squid_data.py --dataset Med --log-level DEBUG


RUNNING QUERIES
===============

Run SQUiD on all query types:
    python run_challenging_queries.py --systems squid --query-types all

Run SQUiD on specific query types:
    python run_challenging_queries.py --systems squid --query-types simple filter projection

Run multiple systems:
    python run_challenging_queries.py --systems quest uqe squid --query-types all

Resume previous run:
    python run_challenging_queries.py --systems squid --resume


VALIDATION
==========

Validate integration:
    python validate_squid_integration.py

View validation results:
    python validate_squid_integration.py 2>&1 | grep -E "^[✓✗]"


CHECKING RESULTS
================

View preprocessing results:
    ls -la preprocess_squid/Med/disease/
    head preprocess_squid/Med/disease/preprocessed_data.json

View query results:
    ls -la results/challenging_queries/

View specific query result:
    cat results/challenging_queries/RUNID/results/squid/simple/simple_1/result.csv

View execution metadata:
    cat results/challenging_queries/RUNID/results/squid/simple/simple_1/metadata.json

Generate summary report:
    python -m evaluation.run_eval --run-id RUNID


DATASETS & ENTITIES
===================

Med:        disease, drug, institution
Player:     player, team, manager, city
Art:        art
Legal:      legal_case
Finan:      finance


QUERY TYPES
===========

simple:      Basic projection queries
filter:      Filtering on single conditions
projection:  Multi-attribute extraction
join:        Multi-attribute with filtering
aggregation: COUNT, GROUP BY, AVG operations
union:       UNION queries


DIRECTORY STRUCTURE
===================

After preprocessing:
    preprocess_squid/Med/disease/
    ├── documents/
    │   ├── doc_0000.txt
    │   └── ...
    ├── preprocessed_data.json
    ├── preprocessed_data.pkl
    └── summary.json

Query results:
    results/challenging_queries/RUNID/
    └── results/squid/
        └── simple/
            └── simple_1/
                ├── query.json
                ├── result.csv
                └── metadata.json


COMMON ISSUES & FIXES
=====================

Issue: "Preprocessed data not found"
Fix:   python preprocess_squid_data.py --dataset Med

Issue: "Module not found" warning
Fix:   This is expected for partial SQUiD implementation

Issue: Empty query results
Fix:   Check preprocessed data exists:
       ls preprocess_squid/Med/disease/preprocessed_data.json

Issue: Permission errors
Fix:   Check file permissions: chmod +x preprocess_squid_data.py


DOCUMENTATION FILES
===================

SQUID_INTEGRATION_GUIDE.md          - User guide for preprocessing & queries
SQUID_IMPLEMENTATION_SUMMARY.md     - Technical architecture & design
SQUID_COMPLETION_REPORT.md          - Implementation details & status
systems/SQUiD/squid.md              - Original SQUiD paper


KEY COMMANDS SUMMARY
====================

Setup:
    python validate_squid_integration.py
    python preprocess_squid_data.py --dataset all

Run:
    python run_challenging_queries.py --systems squid --query-types all

Verify:
    ls results/challenging_queries/*/results/squid/*/*/result.csv
    wc -l preprocess_squid/*/*/preprocessed_data.json


SYSTEM COMPARISON
=================

                Quest    UQE    SQUiD
Simple          ✓        ✓      ✓
Filter          ✓        ✓      ✓
Projection      ✓        ✓      ✓
Join            ✓        ✗      ✓
Aggregation     ✗        ✓      ✓
Union           ✗        ✗      ✓

Run all systems:
    python run_challenging_queries.py --systems all --query-types all
"""

if __name__ == "__main__":
    import sys
    print(__doc__)


