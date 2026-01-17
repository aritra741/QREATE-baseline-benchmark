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

def extract_from_chunk(chunk_text: str, schema_json: str, client: Client) -> Dict:
    prompt_template = """You are a strict database ETL agent.

TARGET SCHEMA:
{schema_json}

TEXT:
{chunk_text}

INSTRUCTIONS:
1. Extract data ONLY for the Tables and Columns defined in the TARGET SCHEMA. Do not invent new columns.
2. MUTUAL EXCLUSION RULE: If an entity fits into multiple tables, extract it into the SINGLE MOST SPECIFIC table ONLY. Do not duplicate data across multiple tables.
3. Foreign Key Rule: If a column is marked as a Foreign Key (e.g., 'manufacturer' linking to 'Company'), you MUST extract the specific Name/ID of that entity from the text.
4. Null Rule: If an attribute is not explicitly mentioned in the text, set the value to null.
5. Data Quality Rule: Values must be CONCISE (names, numbers, dates, short identifiers). 
6. CRITICAL PK RULE: Primary Key columns (names, IDs) MUST be under 10 words. If the text provides a sentence description but no clear name/ID, output null.
7. NEVER extract full sentences or descriptive paragraphs as values. If a value is longer than 50 characters, it is likely narrative and should be discarded (set to null).
8. Output strictly a JSON object containing a list of records for each table found.

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
            prompt = prompt_template.replace("{chunk_text}", chunk_text).replace("{schema_json}", schema_json)
            response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json')
            data = json.loads(response['message']['content'])
            return data
        except Exception as e:
            if attempt == retries:
                return {}
    return {}

def main():
    if not os.path.exists("schema.json") or not os.path.exists("chunks.json"):
        print("Required files missing (schema.json or chunks.json)")
        return

    with open("schema.json", 'r') as f:
        schema = json.load(f)

    with open("chunks.json", 'r') as f:
        chunks = json.load(f)

    client = get_llm_client()
    
    with open("extracted_raw.jsonl", "w") as out_f:
        for i, chunk in enumerate(chunks):
            print(f"Processing chunk {i+1}/{len(chunks)}...")
            
            # Step 3 Optimization: Schema Sharding
            relevant_table_names = get_relevant_tables(chunk["text"], schema, client)
            
            # Fallback: if pre-flight is empty but text is long, use all tables
            if not relevant_table_names and len(chunk["text"]) > 100:
                relevant_table_names = list(schema.keys())
            
            if not relevant_table_names:
                continue
            
            sharded_schema = {t: schema[t] for t in relevant_table_names}
            extracted_data = extract_from_chunk(chunk["text"], json.dumps(sharded_schema), client)
            
            if extracted_data:
                valid_extracted_data = {}
                for table_name, rows in extracted_data.items():
                    if table_name not in schema: continue
                    
                    # Phase 3.2: Hard Filter for PK Quality
                    col_names = [c["name"] for c in schema[table_name]["columns"]]
                    pk_col = "name" if "name" in col_names else (col_names[0] if col_names else None)
                    
                    valid_rows = []
                    for row in rows:
                        pk_val = row.get(pk_col)
                        if pk_val:
                            # Discard if PK is too long or has newlines
                            if len(str(pk_val)) > 80 or "\n" in str(pk_val):
                                continue
                        valid_rows.append(row)
                    
                    if valid_rows:
                        valid_extracted_data[table_name] = valid_rows
                
                if valid_extracted_data:
                    record = {
                        "chunk_id": chunk["id"],
                        "source_file": chunk["source_file"],
                        "data": valid_extracted_data
                    }
                    out_f.write(json.dumps(record) + "\n")

    print("Extraction complete. Results saved to extracted_raw.jsonl")

if __name__ == "__main__":
    main()
