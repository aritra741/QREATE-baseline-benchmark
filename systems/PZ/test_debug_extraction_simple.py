#!/usr/bin/env python
"""Simple test to debug sem_map extraction with clear output"""

import os
import sys

# Set environment variables BEFORE any imports
os.environ["PALIMPZEST_USE_OLLAMA_ONLY"] = "true"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
os.environ["LITELLM_DROP_PARAMS"] = "True"

# Unset commercial API keys to force Ollama only
for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TOGETHER_API_KEY", "GEMINI_API_KEY", "VLLM_API_BASE"]:
    os.environ.pop(key, None)

# Set Ollama API base 
if not os.getenv("OLLAMA_API_BASE"):
    os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"

print("[TEST] Environment setup complete")
print(f"[TEST] OLLAMA_API_BASE={os.environ.get('OLLAMA_API_BASE')}")
print(f"[TEST] PALIMPZEST_USE_OLLAMA_ONLY={os.environ.get('PALIMPZEST_USE_OLLAMA_ONLY')}")

from pathlib import Path

print("\n[TEST] Importing palimpzest...")
try:
    import palimpzest as pz
    print("[TEST] ✓ Palimpzest imported")
except Exception as e:
    print(f"[ERROR] Failed to import palimpzest: {e}")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).parent.parent.parent
SOURCE_DATA = PROJECT_ROOT / "source_data" / "Healthcare" / "disease_small"

print(f"\n[TEST] Source data path: {SOURCE_DATA}")
print(f"[TEST] Exists: {SOURCE_DATA.exists()}")

if not SOURCE_DATA.exists():
    print(f"[ERROR] Path does not exist: {SOURCE_DATA}")
    sys.exit(1)

# Count docs  
docs = list(SOURCE_DATA.glob("*.txt"))
print(f"[TEST] Found {len(docs)} documents")
if docs:
    print(f"[TEST] First 3: {[d.name for d in docs[:3]]}")

print("\n" + "="*80)
print("[TEST] Creating dataset...")
print("="*80)

try:
    dataset = pz.TextFileDataset(path=str(SOURCE_DATA), id="test")
    print("[TEST] ✓ Dataset created")
except Exception as e:
    print(f"[ERROR] Failed to create dataset: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*80)
print("[TEST] Applying sem_map for disease_type...")
print("="*80)

try:
    schema = [
        {"name": "disease_type", "type": str, "desc": "The disease_type attribute extracted from the document"}
    ]
    dataset = dataset.sem_map(schema)
    print("[TEST] ✓ sem_map applied")
except Exception as e:
    print(f"[ERROR] Failed to apply sem_map: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*80)
print("[TEST] Running optimize_and_run()...")
print("="*80)

try:
    config = pz.QueryProcessorConfig(
        policy=pz.MinCost(),
        execution_strategy="SEQUENTIAL",
        progress=False,
    )
    
    validator = pz.Validator()
    output = dataset.optimize_and_run(config=config, validator=validator)
    print("[TEST] ✓ optimize_and_run() completed")
except Exception as e:
    print(f"[ERROR] Failed during optimize_and_run: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*80)
print("[TEST] Converting to DataFrame...")
print("="*80)

try:
    result_df = output.to_df()
    print(f"[TEST] ✓ DataFrame created: shape={result_df.shape}")
except Exception as e:
    print(f"[ERROR] Failed to convert to DataFrame: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*80)
print("[RESULTS]")
print("="*80)
print(f"Shape: {result_df.shape}")
print(f"Columns: {list(result_df.columns)}")

if 'disease_type' in result_df.columns:
    null_count = result_df['disease_type'].isnull().sum()
    non_null_count = len(result_df) - null_count
    print(f"\ndisease_type values:")
    print(f"  Non-null: {non_null_count}/{len(result_df)}")
    print(f"  Null: {null_count}/{len(result_df)}")
    
    if non_null_count > 0:
        print(f"\nFirst 10 non-null values:")
        non_null_df = result_df[result_df['disease_type'].notna()]
        for idx, (_, row) in enumerate(non_null_df.head(10).iterrows()):
            print(f"  {idx+1}. {row.get('filename', 'N/A')}: {row.get('disease_type', 'N/A')}")
    else:
        print(f"\nAll values are NULL!")
        print(f"Sample rows (first 5):")
        for idx, (_, row) in enumerate(result_df.head(5).iterrows()):
            print(f"  {idx+1}. {row.get('filename', 'N/A')}: {row.get('disease_type', 'N/A')}")
else:
    print(f"ERROR: disease_type not in columns!")
    print(f"Available columns: {list(result_df.columns)}")

print("\n[TEST] ✓ Complete")

