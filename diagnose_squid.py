#!/usr/bin/env python3
"""
Diagnose SQUiD pipeline execution flow and expected file structure.
"""

import os
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
SQUID_PATH = PROJECT_ROOT / "systems" / "SQUiD"

print("=" * 100)
print("SQUiD Pipeline Execution Diagnosis")
print("=" * 100)
print()

# What the pipeline should do:
print("EXPECTED PIPELINE FLOW:")
print("-" * 100)
print("1. Schema Generation (qwen)")
print("   Input:  preprocess_squid/Med/{disease,drug,institution}/documents/")
print("   Output: results/schema_generation/{...}/schemas.json")
print()
print("2. Value Identification (Symbolic + LLM)")
print("   Input:  schemas from step 1 + documents")
print("   Output: results/value_identification/{...}/identified_values.json")
print()
print("3. Value Population (TS, TST, TST-L methods)")
print("   Input:  identified values from step 2")
print("   Output: results/value_population/{method}/{...}/populated_values.json")
print()
print("4. Database Generation (for TS, TST, TST-L)")
print("   Input:  populated values")
print("   Output: results/database_generation/{method}/{datapath}/text_cot_qwen.json")
print()
print("5. Ensemble (combines TS, TST, TST-L)")
print("   Input:  results/database_generation/{TS,TST,TST-L}/{datapath}/text_cot_qwen.json")
print("   Output: results/database_generation/ensemble/TS_TST_TST-L/{datapath}/text_cot_qwen.json")
print()
print("-" * 100)
print()

# What we actually have
print("CURRENT STATE:")
print("-" * 100)

preprocess_dir = PROJECT_ROOT / "preprocess_squid"
if preprocess_dir.exists():
    print(f"✓ LLM Documents generated: {preprocess_dir}/")
    for dataset_dir in sorted(preprocess_dir.iterdir()):
        if dataset_dir.is_dir():
            for entity_dir in sorted(dataset_dir.iterdir()):
                if entity_dir.is_dir():
                    docs_dir = entity_dir / "documents"
                    if docs_dir.exists():
                        doc_count = len(list(docs_dir.glob("*.txt")))
                        print(f"    {dataset_dir.name}/{entity_dir.name}: {doc_count} documents")
else:
    print(f"✗ LLM Documents NOT found")

print()

results_dir = SQUID_PATH / "results"
if results_dir.exists():
    print(f"✓ Results directory exists: {results_dir}/")
    for method_dir in sorted(results_dir.iterdir()):
        if method_dir.is_dir():
            file_count = len(list(method_dir.rglob("*.json")))
            print(f"    {method_dir.name}: {file_count} JSON files")
else:
    print(f"✗ Results directory NOT found (will be created by pipeline)")

print()
print("-" * 100)
print()

# Key issue analysis
print("KEY ISSUES:")
print("-" * 100)

# Check config.yaml
config_file = SQUID_PATH / "configs" / "config.yaml"
if config_file.exists():
    print(f"✓ config.yaml exists and is accessible")
else:
    print(f"✗ config.yaml NOT accessible (add to .gitignore exceptions)")

# Check mysql
try:
    import mysql.connector
    print(f"✓ mysql-connector-python is installed")
except ImportError:
    print(f"✗ mysql-connector-python NOT installed (needed by SQUiD models)")
    print(f"  Install with: pip install mysql-connector-python")

# Check datapath mapping
print()
print("DATAPATH MAPPING ISSUE:")
print("  The ensemble script looks for specific datapaths:")
print("    - BIRD/bird_dataset")
print("    - SyntheticText/merged_dataset2")
print()
print("  But we have documents in: preprocess_squid/Med/disease, etc.")
print()
print("  SQUiD's pipeline scripts use config.yaml to determine datapaths.")
print("  Check config.yaml for 'datapath' entries - they must match what pipeline produces.")

print()
print("-" * 100)
print()

print("WHAT YOU NEED TO DO:")
print("-" * 100)
print("1. Ensure mysql-connector-python is installed:")
print("   pip install mysql-connector-python")
print()
print("2. Run the full pipeline and monitor for actual errors:")
print("   python preprocess_squid_data.py --dataset Med --log-level DEBUG")
print()
print("3. Check the generated results/ directory structure to see what actually gets created")
print()
print("4. If ensemble fails, examine:")
print("   - Do results/database_generation/{TS,TST,TST-L}/... files exist?")
print("   - Are the datapath names in config.yaml matching what's created?")
print()
print("=" * 100)


