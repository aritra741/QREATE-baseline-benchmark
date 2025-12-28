#!/usr/bin/env python
"""Quick test of Ollama extraction with fixed configuration"""

import sys
sys.path.insert(0, '/Users/aritramazumder/Documents/UDA-Bench-main')
sys.path.insert(0, '/Users/aritramazumder/Documents/UDA-Bench-main/systems/PZ/PZ_original/palimpzest/src')

import os
# Clear ALL other LLM API keys to ensure ONLY Ollama is available
for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TOGETHER_API_KEY", "GEMINI_API_KEY"]:
    os.environ.pop(key, None)

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"
os.environ["LITELLM_DROP_PARAMS"] = "True"

import palimpzest as pz

test_path = '/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare/disease_test'

print("Testing extraction with FIXED config...")
dataset = pz.TextFileDataset(path=test_path, id="disease_test")

schema = [{"name": "disease_type", "type": str, "desc": "The disease type mentioned in the document"}]
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
    print("\n=== RESULTS ===")
    print(result_df[['disease_type']].to_string())
    print(f"\nNon-null disease_type values: {result_df['disease_type'].notna().sum()}/{len(result_df)}")
    print(f"Values: {result_df['disease_type'].unique()}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

