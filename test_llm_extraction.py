#!/usr/bin/env python3
"""
Test script to verify LLM extraction on actual player documents
"""
import json
import os
import sys
from pathlib import Path

# Setup path
proj_root = Path(__file__).parent
os.chdir(proj_root)
sys.path.insert(0, str(proj_root / 'systems'))

# Read a few actual player documents from the indexed content
player_docs_path = proj_root / 'index' / 'hnsw' / 'player' / 'doc_content.json'

if not player_docs_path.exists():
    print(f"ERROR: Player doc_content.json not found at {player_docs_path}")
    print("Make sure you have indexed the player documents")
    exit(1)

with open(player_docs_path, 'r') as f:
    doc_content = json.load(f)

print(f"Total player documents: {len(doc_content)}")
print("\n" + "="*80)

# Test on first 5 documents
test_docs = list(doc_content.items())[:5]

for doc_id, text in test_docs:
    print(f"\n{'='*80}")
    print(f"Document ID: {doc_id}")
    print(f"Text length: {len(text)} chars")
    print(f"\nFull text:\n{text}\n")
    print(f"{'='*80}")
    
    # Now test LLM extraction on this
    from quest.core.llm.llm_query import TextLLMQuerier
    
    # Create a simple schema with just team
    schema = "team: the current NBA team the player belongs to, or the last NBA team the player joined if not currently active."
    
    querier = TextLLMQuerier(prompt=schema)
    
    print(f"\nExtracting 'team' from this document using LLM...")
    print(f"Schema: {schema}\n")
    
    # Create textDict in the expected format
    textDict = {
        doc_id: {
            'team': [(text, 0)]  # (text, chunk_id)
        }
    }
    
    try:
        # Use extract_attribute_from_textDict which takes textDict directly
        result_df = querier.extract_attribute_from_textDict(textDict, attributeList=['team'])
        print(f"\nLLM Extraction Result:")
        print(result_df)
        
        if len(result_df) > 0:
            extracted_team = result_df['team'].iloc[0]
            print(f"\nExtracted team: {extracted_team}")
        else:
            print("\nNo extraction result")
    except Exception as e:
        print(f"Error during extraction: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*80}")
print("Test complete!")

