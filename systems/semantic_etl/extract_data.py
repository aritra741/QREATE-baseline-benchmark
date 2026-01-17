import json
import os
from typing import List, Dict
from ollama import Client

# Configuration
MODEL_NAME = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"

def get_llm_client():
    return Client(host=OLLAMA_HOST)

def get_relevant_tables(chunk_text: str, schema: Dict, client: Client) -> List[str]:
    """Phase 3 Optimization: Pre-Flight check to identify relevant tables for a chunk."""
    table_names = list(schema.keys())
    prompt = f"""Identify which of these database tables are relevant to the provided text.
    
TABLES: {json.dumps(table_names)}

TEXT: {chunk_text}

Output strictly a JSON list of relevant table names. If none are relevant, output []."""
    
    try:
        response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json')
        relevant = json.loads(response['message']['content'])
        return [t for t in relevant if t in table_names]
    except:
        return table_names

def extract_from_chunk(chunk_text: str, schema_json: str, client: Client) -> List[Dict]:
    """Phase 3 (OpenIE Pass): Extract atomic facts as triples."""
    prompt = f"""You are an Open Information Extraction (OpenIE) agent.
    
TARGET SCHEMA (for context):
{schema_json}

TEXT:
{chunk_text}

TASK:
Extract every atomic fact about the entities in the text that relate to the TARGET SCHEMA.
Format each fact as a 'Triple': (Subject, Attribute, Value).

RULES:
1. SUBJECT: The specific name/ID of the entity (e.g., 'Apple Inc.', 'iPhone 15', 'Ibuprofen').
2. ATTRIBUTE: Must be a column name from the TARGET SCHEMA.
3. VALUE: A concise data point (number, date, or short string).
4. NEVER extract full sentences as values.
5. Output strictly a JSON list of objects.

JSON FORMAT:
[
  {{"subject": "Entity Name", "table": "TableName", "attribute": "col_name", "value": "data_point"}}
]"""

    try:
        response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json')
        facts = json.loads(response['message']['content'])
        return facts if isinstance(facts, list) else []
    except:
        return []

def main():
    if not os.path.exists("schema.json") or not os.path.exists("chunks.json"):
        print("Required files missing.")
        return

    with open("schema.json", 'r') as f: schema = json.load(f)
    with open("chunks.json", 'r') as f: chunks = json.load(f)
    client = get_llm_client()
    
    with open("extracted_facts.jsonl", "w") as out_f:
        for i, chunk in enumerate(chunks):
            print(f"Mining facts from chunk {i+1}/{len(chunks)}...")
            facts = extract_from_chunk(chunk["text"], json.dumps(schema), client)
            
            # V5 Quality Filter
            for fact in facts:
                # Discard narrative leakage (long values or PKs)
                if len(str(fact.get("subject", ""))) > 60 or len(str(fact.get("value", ""))) > 100:
                    continue
                # Ensure the table and attribute actually exist in our schema
                if fact.get("table") in schema:
                    out_f.write(json.dumps(fact) + "\n")

    print("Fact mining complete. Atomic facts saved to extracted_facts.jsonl")

    print("Extraction complete. Results saved to extracted_raw.jsonl")

if __name__ == "__main__":
    main()
