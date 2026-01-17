import json
import os
from typing import List, Dict
from ollama import Client

# Configuration
MODEL_NAME = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"

def get_llm_client():
    return Client(host=OLLAMA_HOST)

def extract_from_chunk(chunk_text: str, schema_json: str, client: Client) -> Dict:
    prompt_template = """You are a strict database ETL agent.

TARGET SCHEMA:
{schema_json}

TEXT:
{chunk_text}

INSTRUCTIONS:
1. Extract data ONLY for the Tables and Columns defined in the TARGET SCHEMA. Do not invent new columns.
2. Foreign Key Rule: If a column is marked as a Foreign Key (e.g., 'manufacturer' linking to 'Company'), you MUST extract the specific Name/ID of that entity from the text.
3. Null Rule: If an attribute is not explicitly mentioned in the text, set the value to null.
4. Data Quality Rule: Values must be CONCISE (names, numbers, dates, short identifiers). 
5. NEVER extract full sentences or descriptive paragraphs as values. If the text only contains a long description without a clear attribute value, use null.
6. Output strictly a JSON object containing a list of records for each table found.

JSON FORMAT:
{
  "TableName1": [
    {"column1": "value", "column2": "value"}
  ],
  "TableName2": []
}"""

    retries = 1
    for attempt in range(retries + 1):
        try:
            # Use replace instead of format to avoid KeyError from braces in text/schema
            prompt = prompt_template.replace("{chunk_text}", chunk_text).replace("{schema_json}", schema_json)
            
            response = client.chat(model=MODEL_NAME, messages=[
                {'role': 'user', 'content': prompt}
            ], format='json')
            
            data = json.loads(response['message']['content'])
            return data
        except Exception as e:
            if attempt == retries:
                print(f"Failed to extract data after {retries} retries: {type(e).__name__}: {e}")
                return {}
            print(f"Extraction failed, retrying... Error: {type(e).__name__}: {e}")
    
    return {}

def main():
    if not os.path.exists("schema.json") or not os.path.exists("chunks.json"):
        print("Required files missing (schema.json or chunks.json)")
        return

    with open("schema.json", 'r') as f:
        schema = json.load(f)
    schema_str = json.dumps(schema, indent=2)

    with open("chunks.json", 'r') as f:
        chunks = json.load(f)

    client = get_llm_client()
    
    with open("extracted_raw.jsonl", "w") as out_f:
        for i, chunk in enumerate(chunks):
            print(f"Extracting from chunk {i+1}/{len(chunks)}...")
            extracted_data = extract_from_chunk(chunk["text"], schema_str, client)
            
            if extracted_data:
                # Add metadata
                record = {
                    "chunk_id": chunk["id"],
                    "source_file": chunk["source_file"],
                    "data": extracted_data
                }
                out_f.write(json.dumps(record) + "\n")

    print("Extraction complete. Results saved to extracted_raw.jsonl")

if __name__ == "__main__":
    main()
