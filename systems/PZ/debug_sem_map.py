#!/usr/bin/env python
"""Debug sem_map by directly checking what Palimpzest extracts"""

import os
import sys

# Set environment variables BEFORE any imports
os.environ["PALIMPZEST_USE_OLLAMA_ONLY"] = "true"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
os.environ["LITELLM_DROP_PARAMS"] = "True"

# Unset commercial API keys
for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TOGETHER_API_KEY", "GEMINI_API_KEY", "VLLM_API_BASE"]:
    os.environ.pop(key, None)

# Set Ollama API base 
if not os.getenv("OLLAMA_API_BASE"):
    os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"

from pathlib import Path
import logging

# Enable debug logging for litellm to see what's happening
os.environ["LITELLM_DEBUG"] = "True"

# Now import palimpzest
try:
    import palimpzest as pz
    print("[DEBUG] Successfully imported palimpzest")
except Exception as e:
    print(f"[ERROR] Failed to import palimpzest: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Set up logging to see generator output
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("palimpzest")
logger.setLevel(logging.DEBUG)

PROJECT_ROOT = Path(__file__).parent.parent.parent
SOURCE_DATA = PROJECT_ROOT / "source_data" / "Healthcare" / "disease_small"

print(f"\n[INFO] Testing sem_map on: {SOURCE_DATA}")
print(f"[INFO] Checking if path exists: {SOURCE_DATA.exists()}")

if not SOURCE_DATA.exists():
    print(f"[ERROR] Path does not exist: {SOURCE_DATA}")
    sys.exit(1)

# Count documents
doc_count = len(list(SOURCE_DATA.glob("*.txt")))
print(f"[INFO] Found {doc_count} documents")

try:
    print("\n[INFO] Creating TextFileDataset...")
    dataset = pz.TextFileDataset(path=str(SOURCE_DATA), id="disease_test")
    print(f"[INFO] Dataset created: {dataset}")
    
    print("\n[INFO] Applying sem_map for disease_type extraction...")
    schema = [{"name": "disease_type", "type": str, "desc": "The disease_type attribute extracted from the document"}]
    dataset = dataset.sem_map(schema)
    print(f"[INFO] sem_map applied")
    
    print("\n[INFO] Creating config...")
    config = pz.QueryProcessorConfig(
        policy=pz.MinCost(),
        execution_strategy="SEQUENTIAL",
        progress=False,
    )
    print(f"[INFO] Config created: {config}")
    
    print("\n[INFO] Running optimize_and_run()...")
    validator = pz.Validator()
    output = dataset.optimize_and_run(config=config, validator=validator)
    print(f"[INFO] optimize_and_run() completed")
    
    print("\n[INFO] Converting to DataFrame...")
    result_df = output.to_df()
    print(f"[INFO] DataFrame shape: {result_df.shape}")
    print(f"[INFO] Columns: {list(result_df.columns)}")
    
    print(f"\n[RESULTS]")
    print(f"  Shape: {result_df.shape}")
    print(f"  Null counts:\n{result_df.isnull().sum()}")
    
    if len(result_df) > 0:
        print(f"\n  First 5 rows:")
        if 'disease_type' in result_df.columns:
            for idx, row in result_df.head(5).iterrows():
                print(f"    {row.get('filename', 'N/A')}: {row.get('disease_type', 'NULL')}")
        
        non_null = result_df[result_df['disease_type'].notna()] if 'disease_type' in result_df.columns else result_df.iloc[0:0]
        print(f"\n  Non-null disease_type: {len(non_null)}/{len(result_df)}")
        if len(non_null) > 0:
            print(f"  Unique values: {non_null['disease_type'].unique()[:5]}")

except Exception as e:
    print(f"[ERROR] Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n[SUCCESS] Test completed")

