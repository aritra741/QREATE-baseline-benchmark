#!/usr/bin/env python
"""Test LLM extraction directly on actual documents from source_data"""

import os
os.environ["PALIMPZEST_USE_OLLAMA_ONLY"] = "true"
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"
os.environ["LITELLM_DROP_PARAMS"] = "True"

import litellm
import json

# Read a few actual documents
docs_to_test = [
    "/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare/disease_small/103.txt",
    "/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare/disease_small/106.txt",
    "/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare/disease_small/109.txt",
]

print("Testing LLM extraction on actual documents...")
print("=" * 80)

for doc_path in docs_to_test:
    if not os.path.exists(doc_path):
        print(f"SKIP: {doc_path} not found")
        continue
    
    with open(doc_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Truncate for readability
    content_preview = content[:300] + "..." if len(content) > 300 else content
    print(f"\nDocument: {os.path.basename(doc_path)}")
    print(f"Content preview: {content_preview}")
    print(f"Full length: {len(content)} chars")
    
    # Test 1: Simple extraction prompt
    messages = [
        {
            "role": "user",
            "content": f"""Extract the disease_type from this document. Return just the disease type value.

Document:
{content}

Disease type:"""
        }
    ]
    
    try:
        print("\n[Test 1] Simple extraction...")
        response = litellm.completion(
            model="openai/qwen2.5:7b-instruct",
            messages=messages,
            api_base=os.environ.get("OLLAMA_API_BASE", "http://localhost:11434/v1"),
            api_key="local",
            temperature=0.3,
            max_tokens=100,
        )
        result = response.choices[0].message.content.strip()
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 2: JSON extraction prompt
    messages_json = [
        {
            "role": "user",
            "content": f"""Extract information from this document. Return as JSON with keys: disease_type, disease_name.

Document:
{content}

Return valid JSON only:"""
        }
    ]
    
    try:
        print("\n[Test 2] JSON extraction...")
        response = litellm.completion(
            model="openai/qwen2.5:7b-instruct",
            messages=messages_json,
            api_base=os.environ.get("OLLAMA_API_BASE", "http://localhost:11434/v1"),
            api_key="local",
            temperature=0.3,
            max_tokens=200,
        )
        result = response.choices[0].message.content.strip()
        print(f"Result: {result}")
        try:
            parsed = json.loads(result)
            print(f"Parsed JSON: {parsed}")
        except:
            print("(Not valid JSON)")
    except Exception as e:
        print(f"Error: {e}")
    
    print("-" * 80)

