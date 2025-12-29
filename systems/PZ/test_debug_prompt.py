#!/usr/bin/env python
"""Debug: Log exactly what prompt is being sent to Ollama"""

import os
os.environ["PALIMPZEST_USE_OLLAMA_ONLY"] = "true"
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"
os.environ["LITELLM_DROP_PARAMS"] = "True"

from pathlib import Path
import palimpzest as pz
import logging

# Enable DEBUG logging to see prompts
logging.basicConfig(level=logging.DEBUG)

PROJECT_ROOT = Path(__file__).parent.parent.parent
SOURCE_DATA = PROJECT_ROOT / "source_data" / "Healthcare" / "disease_small"

print("=" * 80)
print("CREATING DATASET AND SCHEMA")
print("=" * 80)

dataset = pz.TextFileDataset(path=str(SOURCE_DATA), id="disease_test")
print(f"Dataset created. First file: {list(SOURCE_DATA.glob('*.txt'))[0]}")

# Read actual file content to see what's in it
first_file = list(SOURCE_DATA.glob('*.txt'))[0]
with open(first_file) as f:
    content = f.read()[:500]
    print(f"\nActual file content (first 500 chars):\n{content}\n")

schema = [{"name": "disease_type", "type": str, "desc": "The disease_type attribute"}]
dataset = dataset.sem_map(schema)

config = pz.QueryProcessorConfig(
    policy=pz.MinCost(),
    execution_strategy="SEQUENTIAL",
    progress=False,
)

print("=" * 80)
print("RUNNING OPTIMIZE_AND_RUN - CHECK DEBUG LOGS FOR PROMPTS")
print("=" * 80)

validator = pz.Validator()
output = dataset.optimize_and_run(config=config, validator=validator)

result_df = output.to_df()
print(f"\nResults: {result_df[['filename', 'disease_type']].head(5).to_string()}")

