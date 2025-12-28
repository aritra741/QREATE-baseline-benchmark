#!/usr/bin/env python
"""Debug script to see what's actually being sent to LLM"""

import sys
sys.path.insert(0, '/Users/aritramazumder/Documents/UDA-Bench-main')
sys.path.insert(0, '/Users/aritramazumder/Documents/UDA-Bench-main/systems/PZ/PZ_original/palimpzest/src')

import os
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"

import palimpzest as pz
import logging

# Enable debug logging for LiteLLM to see actual prompts
import litellm
litellm._turn_on_debug()

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Load test documents
test_path = '/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare/disease_test'

print(f"Loading documents from: {test_path}\n")

# Create dataset and apply extraction
dataset = pz.TextFileDataset(path=test_path, id="disease_test")

# Apply sem_map to extract disease_type
schema = [
    {
        "name": "disease_type",
        "type": str,
        "desc": "The disease type mentioned in the document"
    }
]

print("Applying sem_map to extract disease_type...")
dataset = dataset.sem_map(schema)

# Create config
config = pz.QueryProcessorConfig(
    policy=pz.MaxQuality(),
    execution_strategy="SEQUENTIAL",
    progress=False,
)

print("\nRunning optimize_and_run...\n")

# Run the query
try:
    validator = pz.Validator()
    output = dataset.optimize_and_run(config=config, validator=validator)
    result_df = output.to_df()
    print("\n=== RESULTS ===")
    print(result_df)
    print(f"\nNull values in disease_type: {result_df['disease_type'].isna().sum()}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

