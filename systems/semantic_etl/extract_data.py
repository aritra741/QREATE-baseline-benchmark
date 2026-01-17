import json
import os
import torch
from typing import List, Dict
from ollama import Client
from sentence_transformers import CrossEncoder

# Configuration
MODEL_NAME = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"
NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-base"

def get_llm_client():
    return Client(host=OLLAMA_HOST)

class NLIGuardrail:
    def __init__(self, model_name=NLI_MODEL_NAME):
        print(f"Loading NLI model: {model_name}...")
        self.model = CrossEncoder(model_name)
        self.labels = self.model.config.id2label
        
    def validate_entities(self, table_name: str, definition: str, candidates: List[str]) -> List[str]:
        if not candidates: return []
        pairs = [[f"This is a {table_name}: {definition}.", f"{c} is a {table_name}."] for c in candidates]
        logits = self.model.predict(pairs)
        label_map = {v.lower(): k for k, v in self.labels.items()}
        ent_idx = label_map.get('entailment', 2)
        con_idx = label_map.get('contradiction', 0)
        neu_idx = label_map.get('neutral', 1)
        probs = torch.nn.functional.softmax(torch.tensor(logits), dim=1).numpy()
        
        valid = []
        print(f"\n--- NLI DEBUG: Table '{table_name}' ---")
        for i, c in enumerate(candidates):
            p_ent = probs[i][ent_idx]
            p_con = probs[i][con_idx]
            p_neu = probs[i][neu_idx]
            
            status = "REJECTED"
            if p_ent > 0.5:
                valid.append(c)
                status = "ACCEPTED (Entailment)"
            elif p_con > 0.5:
                status = "DISCARDED (Contradiction)"
            else:
                valid.append(c) # Neutral fallback
                status = "ACCEPTED (Neutral Fallback)"
            
            print(f"  Candidate: '{c}'")
            print(f"    Scores -> E: {p_ent:.4f}, N: {p_neu:.4f}, C: {p_con:.4f}")
            print(f"    Result: {status}")
        return valid

    def validate_attribute(self, column_name: str, value: str) -> bool:
        if not value or str(value).lower() == "null": return False
        # Premise: "The {column_name} is a data value."
        # Hypothesis: "{value} is a valid {column_name}."
        # This is a bit tricky. Let's use the user's example logic.
        # "An active ingredient is a chemical substance." -> Hypothesis: "'Same compound' is a chemical substance."
        # We need a generic premise for attributes.
        premise = f"This is a valid {column_name}."
        hypothesis = f"'{value}' is a {column_name}."
        
        logits = self.model.predict([premise, hypothesis])
        probs = torch.nn.functional.softmax(torch.tensor(logits), dim=0).numpy()
        label_map = {v.lower(): k for k, v in self.labels.items()}
        ent_idx = label_map.get('entailment', 2)
        return probs[ent_idx] > 0.3 # Lower threshold for attributes

def extract_records(chunk: Dict, table_name: str, schema_info: Dict, client: Client) -> List[Dict]:
    """Phase 3.1: LLM Extraction (Recall) - Extracts full records with Context-Aware Resolution."""
    cols = [c["name"] for c in schema_info["columns"]]
    definition = schema_info.get("definition", "")
    pk_col = schema_info.get("_meta", {}).get("primary_key", cols[0])
    
    prompt = f"""You are a database extraction agent.
Table: **{table_name}**
Definition: {definition}
Target Columns: {json.dumps(cols)}

CONTEXT (from previous text): 
"{chunk.get('previous_context', '')}"

TARGET TEXT: 
"{chunk['text']}"

TASK:
1. Identify all entities in the Target Text that fit the definition of a '{table_name}'.
2. RESOLVE PRONOUNS: If the text says 'It', 'The device', 'The subject', etc., use the CONTEXT to find the actual name.
3. For each entity, extract all available attributes.
4. If no clear name exists for an attribute set, use the most descriptive subject found.

Output strictly a JSON list of objects. If none found, output [].

JSON FORMAT:
[
  {{"{pk_col}": "Resolved Name", "attribute": "value"}}
]"""

    try:
        # Use a slightly higher temperature for Recall to avoid "Safe-Null" behavior
        response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json', options={"temperature": 0.3})
        raw_content = response['message']['content']
        print(f"\n[DEBUG] LLM RAW OUTPUT (Table: {table_name}):\n{raw_content}", flush=True)
        content = json.loads(raw_content)
        return content if isinstance(content, list) else []
    except Exception as e:
        print(f"[DEBUG] LLM EXTRACTION ERROR (Table: {table_name}): {e}", flush=True)
        return []

def main():
    if not os.path.exists("schema.json") or not os.path.exists("chunks.json"):
        print("Files missing.")
        return

    with open("schema.json", 'r') as f: schema = json.load(f)
    with open("chunks.json", 'r') as f: chunks = json.load(f)
    client = get_llm_client()
    nli_guard = NLIGuardrail()
    
    extracted_data = []

    for i, chunk in enumerate(chunks):
        print(f"Processing chunk {i+1}/{len(chunks)}...")
        chunk_data = {"chunk_id": chunk["id"], "tables": {}}
        
        for table_name, table_info in schema.items():
            # Step 3.1: Recall (Extract full records)
            records = extract_records(chunk, table_name, table_info, client)
            if not records: continue
            
            # Step 3.2: Precision (Validate PK)
            pk_col = table_info.get("_meta", {}).get("primary_key")
            if not pk_col:
                col_names = [c["name"] for c in table_info["columns"]]
                pk_col = col_names[0]
            
            pk_candidates = [str(r.get(pk_col, "")) for r in records if r.get(pk_col)]
            if not pk_candidates: continue
            
            valid_pks = nli_guard.validate_entities(table_name, table_info["definition"], pk_candidates)
            valid_pks_set = set(valid_pks)
            
            valid_records = [r for r in records if str(r.get(pk_col)) in valid_pks_set]
            if valid_records:
                chunk_data["tables"][table_name] = valid_records
                
        if chunk_data["tables"]:
            extracted_data.append(chunk_data)

    with open("extracted_data_v8.jsonl", "w") as f:
        for entry in extracted_data:
            f.write(json.dumps(entry) + "\n")

    print(f"Extraction complete. Results saved to extracted_data_v8.jsonl")

if __name__ == "__main__":
    main()
