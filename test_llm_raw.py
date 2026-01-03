#!/usr/bin/env python3
"""
Raw LLM test - no QUEST involved, just see what the LLM does
"""
import json
import os
from pathlib import Path
from litellm import completion

# Setup path
proj_root = Path(__file__).parent
os.chdir(proj_root)

# Read a few actual player documents
player_docs_path = proj_root / 'index' / 'hnsw' / 'player' / 'doc_content.json'

if not player_docs_path.exists():
    print(f"ERROR: Player doc_content.json not found")
    exit(1)

with open(player_docs_path, 'r') as f:
    doc_content = json.load(f)

print(f"Total player documents: {len(doc_content)}")

# Test on first 3 documents
test_docs = list(doc_content.items())[:3]

for doc_id, text in test_docs:
    print(f"\n{'='*80}")
    print(f"Testing Document ID: {doc_id}")
    print(f"Text length: {len(text)} chars")
    print(f"{'='*80}")
    
    # Create a simple prompt
    prompt = f"""Extract the NBA team from this document.

Document:
{text}

What NBA team is mentioned? Return just the team name, or NONE if not found."""
    
    print(f"\nSending to LLM...")
    try:
        response = completion(
            model="ollama/qwen2.5:7b-instruct",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            api_base="http://localhost:11434",
            temperature=0.3,
            max_tokens=50
        )
        
        result = response.choices[0].message.content.strip()
        print(f"\nLLM Response: {result}")
        
    except Exception as e:
        print(f"Error: {e}")

print(f"\n{'='*80}")
print("Test complete!")

