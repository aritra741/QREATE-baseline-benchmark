#!/usr/bin/env python
"""Test if LLM can extract disease_type from noisy documents"""

import os
import sys
from pathlib import Path

os.environ["PALIMPZEST_USE_OLLAMA_ONLY"] = "true"
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"
os.environ["LITELLM_DROP_PARAMS"] = "True"

import litellm

PROJECT_ROOT = Path(__file__).parent.parent.parent
SOURCE_DATA = PROJECT_ROOT / "source_data" / "Healthcare" / "disease_small"

doc_files = sorted(list(SOURCE_DATA.glob("*.txt")))[:10]

if not doc_files:
    print(f"ERROR: No documents found in {SOURCE_DATA}")
    sys.exit(1)

print("Testing disease_type extraction (same prompt Palimpzest uses)...")
print("=" * 80)

extracted_values = []

for doc_path in doc_files:
    with open(doc_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Use the EXACT prompt format Palimpzest would use via sem_map
    messages = [
        {
            "role": "user",
            "content": f"""Extract from the document:
- The disease_type attribute extracted from the document

Document:
{content}

Respond with only the value for disease_type, nothing else:"""
        }
    ]
    
    try:
        response = litellm.completion(
            model="openai/qwen2.5:7b-instruct",
            messages=messages,
            api_base=os.environ.get("OLLAMA_API_BASE"),
            api_key="local",
            temperature=0.1,
            max_tokens=50,
        )
        result = response.choices[0].message.content.strip()
        extracted_values.append((doc_path.name, result))
        print(f"{doc_path.name:20} -> {result}")
    except Exception as e:
        print(f"{doc_path.name:20} -> ERROR: {e}")
        extracted_values.append((doc_path.name, f"ERROR: {e}"))

print("\n" + "=" * 80)
print("Summary:")
print(f"Total docs tested: {len(extracted_values)}")
non_empty = [v for k, v in extracted_values if v and "ERROR" not in v and v.lower() != "none" and v.lower() != "not applicable" and v.lower() != "not found"]
print(f"Non-empty extractions: {len(non_empty)}")
print(f"Unique values found: {set(v for k, v in extracted_values if v and 'ERROR' not in v)}")


