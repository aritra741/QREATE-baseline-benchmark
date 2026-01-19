import json
import numpy as np
from extract_data import VectorRelevancyFilter, verify_relevancy, extract_multi_tables, get_llm_client, process_chunk

def test_vector_relevancy():
    with open("schema.json", 'r') as f:
        schema = json.load(f)
    
    with open("chunks.json", 'r') as f:
        chunks = json.load(f)
    
    print("Initializing Vector Relevancy Filter...")
    relevancy_filter = VectorRelevancyFilter(schema)
    client = get_llm_client()
    
    print("\n--- DYNAMIC SHARDING & EXTRACTION TEST (First 5 Chunks) ---")
    for i in range(5):
        chunk = chunks[i]
        text = chunk['text']
        print(f"\nChunk {i+1} Text Snippet: {text[:100]}...")
        
        # Test the full process_chunk logic
        result = process_chunk(chunk, schema, relevancy_filter)
        
        print(f"Extracted Tables: {list(result['tables'].keys())}")
        if result['tables']:
            print(f"EXTRACTED DATA: {json.dumps(result['tables'], indent=2)}")
        else:
            print("No data extracted.")
            
        print("-" * 30)

if __name__ == "__main__":
    test_vector_relevancy()
