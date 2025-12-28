#!/usr/bin/env python
"""Minimal test with 1 document to debug performance"""

import os
# Set env vars FIRST before any imports
os.environ["PALIMPZEST_USE_OLLAMA_ONLY"] = "true"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"
os.environ["LITELLM_DROP_PARAMS"] = "True"

# Unset ALL commercial API keys to ensure they're not used
for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TOGETHER_API_KEY", "GEMINI_API_KEY", "VLLM_API_BASE"]:
    os.environ.pop(key, None)

import sys
sys.path.insert(0, '/Users/aritramazumder/Documents/UDA-Bench-main')

import palimpzest as pz
import time
import logging

# Enable debug logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a tiny test directory with 1 document
import tempfile
import shutil

test_dir = tempfile.mkdtemp()
with open(f"{test_dir}/test1.txt", "w") as f:
    f.write("This document is about metabolic syndrome.")

try:
    logger.info(f"Test directory: {test_dir}")
    
    start = time.time()
    logger.info("Creating dataset...")
    dataset = pz.TextFileDataset(path=test_dir, id="minimal_test")
    
    logger.info("Adding sem_map...")
    schema = [{"name": "disease_type", "type": str, "desc": "The disease type"}]
    dataset = dataset.sem_map(schema)
    
    logger.info("Creating config with MinCost policy...")
    config = pz.QueryProcessorConfig(
        policy=pz.MinCost(),  # Use MinCost instead of MaxQuality for speed
        execution_strategy="SEQUENTIAL",
        progress=False,
    )
    
    logger.info("Starting optimize_and_run...")
    validator = pz.Validator()
    output = dataset.optimize_and_run(config=config, validator=validator)
    
    elapsed = time.time() - start
    result_df = output.to_df()
    
    logger.info(f"\n{'='*50}")
    logger.info(f"COMPLETED in {elapsed:.2f} seconds")
    logger.info(f"Result: {result_df['disease_type'].values}")
    logger.info(f"{'='*50}")
    
except Exception as e:
    elapsed = time.time() - start
    logger.error(f"Error after {elapsed:.2f} seconds: {e}")
    import traceback
    traceback.print_exc()
finally:
    shutil.rmtree(test_dir, ignore_errors=True)

