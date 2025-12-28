#!/usr/bin/env python
"""Test sem_map extraction WITHOUT aggregation"""

import sys
sys.path.insert(0, '/Users/aritramazumder/Documents/UDA-Bench-main')
sys.path.insert(0, '/Users/aritramazumder/Documents/UDA-Bench-main/systems/PZ/PZ_original/palimpzest/src')

import os
os.environ["LITELLM_DROP_PARAMS"] = "True"
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"
os.environ["OPENAI_API_KEY"] = "sk-dummy-for-ollama"

import palimpzest as pz

# Load test documents
test_path = '/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare/disease_test'

print(f"Testing sem_map extraction (no aggregation)...")

dataset = pz.TextFileDataset(path=test_path, id="disease_test")

# Apply sem_map ONLY - no groupby
schema = [
    {
        "name": "disease_type",
        "type": str,
        "desc": "The disease type mentioned in the document"
    }
]

dataset = dataset.sem_map(schema)

config = pz.QueryProcessorConfig(
    policy=pz.MaxQuality(),
    execution_strategy="SEQUENTIAL",
    progress=False,
)

try:
    validator = pz.Validator()
    output = dataset.optimize_and_run(config=config, validator=validator)
    result_df = output.to_df()
    print("\n=== EXTRACTION ONLY (NO AGGREGATION) ===")
    print(result_df)
    print(f"\nNull count in disease_type: {result_df['disease_type'].isna().sum()}/{len(result_df)}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

