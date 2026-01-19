import json
import os
from ollama import Client

MODEL_NAME = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"

def get_llm_client():
    return Client(host=OLLAMA_HOST)

def refine_schema_links():
    if not os.path.exists("schema.json"):
        print("schema.json not found.")
        return

    with open("schema.json", 'r') as f:
        schema = json.load(f)

    client = get_llm_client()
    table_names = list(schema.keys())
    
    print(f"Refining linkages for {len(table_names)} tables...")

    for table_name, table_info in schema.items():
        cols = [c["name"] for c in table_info["columns"]]
        definition = table_info.get("definition", "")
        
        # Create a mapping of table names to their definitions for context
        other_tables_with_defs = {name: info.get("definition", "") for name, info in schema.items() if name != table_name}

        prompt = f"""Role: Database Architect.
Task: Identify Foreign Key (FK) relationships between tables based on their columns and definitions.

CURRENT TABLE: **{table_name}**
DEFINITION: {definition}
COLUMNS: {json.dumps(cols)}

OTHER TABLES (Potential Targets):
{json.dumps(other_tables_with_defs, indent=2)}

INSTRUCTIONS:
1. Examine the COLUMNS of the CURRENT TABLE.
2. Determine if any column stores an identifier (name, ID, type) that belongs to one of the OTHER TABLES.
3. Be specific: Only link if the column semantically 'points' to the other entity.
   - Example: 'medication_type' in table 'Treatment' points to table 'Drug'.
   - Example: 'condition_treated' points to 'MedicalCondition'.
4. Output strictly a JSON list of objects: [{{"column": "col_name", "references": "table_name"}}]
5. If no clear relationships exist, output []."""

        try:
            response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json')
            raw_content = response['message']['content']
            links_raw = json.loads(raw_content)
            
            # Robust Parsing for various output styles
            final_links = []
            if isinstance(links_raw, list):
                final_links = links_raw
            elif isinstance(links_raw, dict):
                # Case 1: {"column": "X", "references": "Y"}
                if "column" in links_raw and "references" in links_raw:
                    final_links = [links_raw]
                else:
                    # Case 2: {"links": [...]} or similar
                    for key in ["foreign_keys", "links", "relationships", "relevant_tables"]:
                        if key in links_raw and isinstance(links_raw[key], list):
                            final_links = links_raw[key]
                            break
            
            if final_links:
                print(f"  Analysing {table_name}: Found {len(final_links)} potential links.")
                for link in final_links:
                    if not isinstance(link, dict): continue
                    col_name = link.get("column")
                    ref_table = link.get("references")
                    
                    if col_name in cols and ref_table in schema:
                        # Update the column in schema
                        for col in table_info["columns"]:
                            if col["name"] == col_name:
                                col["is_foreign_key"] = True
                                col["references_table"] = ref_table
                                print(f"    [LINKED] {table_name}.{col_name} -> {ref_table}")
        except Exception as e:
            print(f"  Error refining {table_name}: {e}")

    with open("schema.json", "w") as f:
        json.dump(schema, f, indent=2)
    print("Schema linkages refined and saved.")

if __name__ == "__main__":
    refine_schema_links()
