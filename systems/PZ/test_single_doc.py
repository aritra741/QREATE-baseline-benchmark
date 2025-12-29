#!/usr/bin/env python
"""Test extraction on a single document to see the full prompt"""

import os
import sys

# Set environment variables BEFORE any imports
os.environ["PALIMPZEST_USE_OLLAMA_ONLY"] = "true"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
os.environ["LITELLM_DROP_PARAMS"] = "True"

# Unset commercial API keys
for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TOGETHER_API_KEY", "GEMINI_API_KEY", "VLLM_API_BASE"]:
    os.environ.pop(key, None)

if not os.getenv("OLLAMA_API_BASE"):
    os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"

from pathlib import Path
import tempfile
import shutil

print("[TEST] Importing palimpzest...")
import palimpzest as pz

PROJECT_ROOT = Path(__file__).parent.parent.parent
SOURCE_DATA = PROJECT_ROOT / "source_data" / "Healthcare" / "disease_small"

print(f"[TEST] Creating temp dir with only 1 document...")
# Create temp directory with just 1 document
with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir_path = Path(tmpdir)
    # Copy just one document
    src_doc = SOURCE_DATA / "103.txt"
    dst_doc = tmpdir_path / "103.txt"
    shutil.copy2(src_doc, dst_doc)
    print(f"[TEST] Copied {src_doc.name} to temp dir")
    
    print(f"\n[TEST] Creating dataset on temp dir with 1 doc...")
    dataset = pz.TextFileDataset(path=str(tmpdir_path), id="test_single")
    
    print(f"[TEST] Applying sem_map for disease_type...")
    schema = [
        {"name": "disease_type", "type": str, "desc": "The disease_type attribute extracted from the document"}
    ]
    dataset = dataset.sem_map(schema)
    
    print(f"\n[TEST] Running optimize_and_run()...")
    config = pz.QueryProcessorConfig(
        policy=pz.MinCost(),
        execution_strategy="SEQUENTIAL",
        progress=False,
    )
    
    validator = pz.Validator()
    output = dataset.optimize_and_run(config=config, validator=validator)
    
    print(f"\n[TEST] Converting to DataFrame...")
    result_df = output.to_df()
    
    print(f"\n[RESULTS]")
    print(f"Shape: {result_df.shape}")
    if 'disease_type' in result_df.columns:
        print(f"disease_type value: {result_df['disease_type'].iloc[0] if len(result_df) > 0 else 'N/A'}")
        print(f"disease_type is null: {result_df['disease_type'].isnull().any()}")
    print(f"\nFull row:\n{result_df.to_string()}")

print("\n[TEST] Complete")

