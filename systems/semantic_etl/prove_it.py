import json
from ollama import Client
import sys

MODEL_NAME = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"

def get_relevant_tables(chunk_text, schema_names, client):
    prompt = f"""Review the text and identify which of these database tables are likely to have data present.
TABLES: {json.dumps(schema_names)}
TEXT: "{chunk_text}"

Output strictly a JSON list of table names found. If none, output []."""
    
    response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json')
    return response['message']['content']

def prove_bottleneck():
    client = Client(host=OLLAMA_HOST)
    
    with open("schema.json", 'r') as f:
        schema = json.load(f)
    schema_names = list(schema.keys())
    
    with open("chunks.json", 'r') as f:
        chunks = json.load(f)
    
    print(f"--- DIAGNOSTIC PROOF ---")
    print(f"Total Tables in Schema: {len(schema_names)}")
    print(f"Testing first 5 chunks...\n")
    
    for i in range(5):
        text = chunks[i]['text']
        print(f"Chunk {i+1} Text Snippet: {text[:100]}...")
        
        # Run relevancy check
        raw_output = get_relevant_tables(text, schema_names, client)
        print(f"LLM RELEVANCY OUTPUT: {raw_output}")
        print("-" * 30)

if __name__ == "__main__":
    prove_bottleneck()
