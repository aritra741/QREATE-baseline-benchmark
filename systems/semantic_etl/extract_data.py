import json
import os
import torch
import sys
from typing import List, Dict
from ollama import Client
from sentence_transformers import CrossEncoder
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Configuration
MODEL_NAME = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"
NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-base"
MAX_WORKERS = 10    # Number of parallel threads for extraction

def get_llm_client():
    return Client(host=OLLAMA_HOST)

class NLIGuardrail:
    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(NLIGuardrail, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, model_name=NLI_MODEL_NAME):
        if self._initialized: return
        print(f"Loading NLI model: {model_name}...")
        self.model = CrossEncoder(model_name)
        self.labels = self.model.config.id2label
        self._initialized = True
        
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
        for i, c in enumerate(candidates):
            p_ent = probs[i][ent_idx]
            p_con = probs[i][con_idx]
            
            if p_ent > 0.5:
                valid.append(c)
            elif p_con > 0.5:
                pass # Discarded
            else:
                valid.append(c) # Neutral fallback
        return valid

    def validate_attribute(self, column_name: str, value: str) -> bool:
        if not value or str(value).lower() == "null": return False
        # Premise: "The {column_name} is a data value."
        # Hypothesis: "{value} is a valid {column_name}."
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
    pk_col = schema_info.get("_meta", {}).get("primary_key")
    
    if not pk_col:
        # Strict requirement: if no PK was designated, extraction is impossible
        print(f"[ERROR] No Primary Key designated for table {table_name}. Skipping.")
        return []

    prompt = f"""Task: Extract data for Table: **{table_name}**.
**Definition:** {definition}
**Target Columns:** {json.dumps(cols)}
**Primary Key Column:** '{pk_col}'

**Context (Information from previous text):**
"{chunk.get('previous_context', '')}"

**Target Text (Extract from this):**
"{chunk['text']}"

**Instructions:**
1. ANALYZE CONTEXT: Note entities, titles, or subjects mentioned in the context.
2. ANALYZE TARGET TEXT: Identify instances of '{table_name}'.
3. RESOLVE PRONOUNS: If the Target Text uses 'It', 'They', 'He', 'She', or 'The company', you MUST resolve them to the specific entity name found in the Context or the text itself.
4. ATOMIC EXTRACTION: Extract one object per distinct entity.
5. NO NARRATIVE LEAKAGE: The '{pk_col}' MUST be a concise name or identifier (max 5 words). Do not put full sentences or JSON blocks in the '{pk_col}'.
6. DATA ALIGNMENT: Map extracted values strictly to the Target Columns. Use 'null' for missing values.
7. REASONING: (Internal) Resolve all anaphora before generating JSON.

**Output Format:** Strictly a JSON list of objects.
Example: [{{ "{pk_col}": "Resolved Name", ... }}]"""

    try:
        # Use a slightly higher temperature for Recall to avoid "Safe-Null" behavior
        response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json', options={"temperature": 0.3})
        raw_content = response['message']['content']
        # Keeping the debug log as per previous user request, but it might be noisy for 100k chunks
        # print(f"\n[DEBUG] LLM RAW OUTPUT (Table: {table_name}):\n{raw_content}", flush=True)
        content = json.loads(raw_content)
        
        # Robust Parsing
        extracted = []
        if isinstance(content, list):
            extracted = content
        elif isinstance(content, dict):
            found_list = False
            for key, value in content.items():
                if isinstance(value, list) and len(value) > 0:
                    if key.lower() in [table_name.lower(), "entities", "records", "data", "rows", table_name.lower() + "s"]:
                        extracted = value
                        found_list = True
                        break
            if not found_list:
                if any(k in cols for k in content.keys()):
                    extracted = [content]
                elif content:
                    extracted = [content]
        
        # Clean and align keys
        aligned_records = []
        for rec in extracted:
            if not isinstance(rec, dict): continue
            new_rec = {}
            for k, v in rec.items():
                # Case-insensitive column matching
                matched = False
                for target_col in cols:
                    if k.lower() == target_col.lower():
                        new_rec[target_col] = v
                        matched = True
                        break
                if not matched:
                    # Capture unmapped keys in case they are the PK
                    new_rec[k] = v
            
            # Ensure the designated PK column is present
            if pk_col not in new_rec:
                # If the LLM returned a flat dict with a different key for PK, try to find it
                # but ONLY if there's a strong candidate that isn't already a column
                for k, v in list(new_rec.items()):
                    if k not in cols and isinstance(v, str) and len(v.split()) < 10:
                        new_rec[pk_col] = v
                        break
            
            # FINAL PK SANITIZATION: Kill JSON-in-Value or Narrative leakage
            pk_val = new_rec.get(pk_col)
            if pk_val:
                # If PK is a list or dict, it's a hallucination/extraction error
                if isinstance(pk_val, (list, dict)):
                    continue
                # If PK is too long, it's narrative leakage
                if len(str(pk_val).split()) > 10:
                    continue
                
                aligned_records.append(new_rec)
            
        return aligned_records
    except Exception as e:
        # print(f"[DEBUG] LLM EXTRACTION ERROR (Table: {table_name}): {e}", flush=True)
        return []

def process_chunk(chunk: Dict, schema: Dict, nli_guard: NLIGuardrail) -> Dict:
    """Worker function for parallel extraction."""
    client = get_llm_client()
    chunk_data = {"chunk_id": chunk["id"], "tables": {}}
    
    for table_name, table_info in schema.items():
        records = extract_records(chunk, table_name, table_info, client)
        if not records: continue
        
        pk_col = table_info.get("_meta", {}).get("primary_key")
        if not pk_col:
            pk_col = [c["name"] for c in table_info["columns"]][0]
        
        pk_candidates = [str(r.get(pk_col, "")) for r in records if r.get(pk_col)]
        if not pk_candidates: continue
        
        valid_pks = nli_guard.validate_entities(table_name, table_info["definition"], pk_candidates)
        valid_pks_set = set(valid_pks)
        
        valid_records = [r for r in records if str(r.get(pk_col)) in valid_pks_set]
        if valid_records:
            chunk_data["tables"][table_name] = valid_records
            
    return chunk_data

def main():
    if not os.path.exists("schema.json") or not os.path.exists("chunks.json"):
        print("Files missing.")
        return

    with open("schema.json", 'r') as f: schema = json.load(f)
    with open("chunks.json", 'r') as f: chunks = json.load(f)
    
    nli_guard = NLIGuardrail()
    file_lock = Lock()
    
    output_file = "extracted_data_v8.jsonl"
    # Clear output file if it exists
    with open(output_file, "w") as f: pass

    print(f"Starting extraction on {len(chunks)} chunks with {MAX_WORKERS} threads...")
    
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_chunk, chunk, schema, nli_guard): chunk for chunk in chunks}
        
        for future in as_completed(futures):
            try:
                chunk_result = future.result()
                if chunk_result["tables"]:
                    with file_lock:
                        with open(output_file, "a") as f:
                            f.write(json.dumps(chunk_result) + "\n")
            except Exception as e:
                print(f"Error processing chunk: {e}")
            
            completed += 1
            if completed % 100 == 0:
                print(f"  Progress: {completed}/{len(chunks)} chunks extracted.", flush=True)

    print(f"Extraction complete. Results saved to {output_file}")

if __name__ == "__main__":
    main()
