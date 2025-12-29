#!/usr/bin/env python
"""Test Palimpzest sem_map extraction directly"""

import os
os.environ["PALIMPZEST_USE_OLLAMA_ONLY"] = "true"
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"
os.environ["LITELLM_DROP_PARAMS"] = "True"

from pathlib import Path
import palimpzest as pz

PROJECT_ROOT = Path(__file__).parent.parent.parent
SOURCE_DATA = PROJECT_ROOT / "source_data" / "Healthcare" / "disease_small"

print("Testing Palimpzest sem_map extraction...")
print(f"Source: {SOURCE_DATA}")
print("=" * 80)

# Create dataset
dataset = pz.TextFileDataset(path=str(SOURCE_DATA), id="disease_test")

# Apply sem_map with just disease_type
schema = [{"name": "disease_type", "type": str, "desc": "The disease_type attribute extracted from the document"}]
dataset = dataset.sem_map(schema)

# Configure and run
config = pz.QueryProcessorConfig(
    policy=pz.MinCost(),
    execution_strategy="SEQUENTIAL",
    progress=False,
)

print("Running sem_map via optimize_and_run()...")
validator = pz.Validator()
output = dataset.optimize_and_run(config=config, validator=validator)

result_df = output.to_df()

print(f"\nResult shape: {result_df.shape}")
print(f"Columns: {list(result_df.columns)}")
print(f"Null counts: {result_df.isnull().sum().to_dict()}")

if len(result_df) > 0:
    print(f"\nFirst 10 results:")
    print(result_df[['filename', 'disease_type']].head(10).to_string())
    
    non_null = result_df[result_df['disease_type'].notna()]
    print(f"\nNon-null disease_type values: {len(non_null)}/{len(result_df)}")
    if len(non_null) > 0:
        print(f"Unique values: {non_null['disease_type'].unique()[:10]}")

