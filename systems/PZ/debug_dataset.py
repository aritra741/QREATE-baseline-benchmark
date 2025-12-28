#!/usr/bin/env python
"""Debug script to check if TextFileDataset properly loads documents"""

import sys
sys.path.insert(0, '/Users/aritramazumder/Documents/UDA-Bench-main')
sys.path.insert(0, '/Users/aritramazumder/Documents/UDA-Bench-main/systems/PZ/PZ_original/palimpzest/src')

import os
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"

import palimpzest as pz

# Load test documents
test_path = '/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare/disease_test'

print(f"Loading documents from: {test_path}")
print(f"Files in directory: {os.listdir(test_path)}")

# Create dataset
dataset = pz.TextFileDataset(path=test_path, id="disease_test")

# Check if documents are accessible
print(f"\nDataset object: {dataset}")
print(f"Dataset type: {type(dataset)}")

# Try to access documents programmatically
try:
    # Iterate through documents
    doc_count = 0
    for doc in dataset:
        doc_count += 1
        print(f"\n--- Document {doc_count} ---")
        print(f"Type: {type(doc)}")
        print(f"Content preview: {str(doc)[:200]}...")
        if doc_count >= 2:
            break
    print(f"\nTotal documents accessible: {doc_count}")
except Exception as e:
    print(f"Error accessing documents: {e}")
    import traceback
    traceback.print_exc()

