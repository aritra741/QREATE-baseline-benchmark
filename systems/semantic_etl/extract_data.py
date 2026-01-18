import json
import os
import torch
import sys
from typing import List, Dict
from ollama import Client
from sentence_transformers import CrossEncoder
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from collections import defaultdict

# Configuration
MODEL_NAME = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"
NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-base"
MAX_WORKERS = 50    # Significant increase for Blackwell 6000

def get_llm_client():
    return Client(host=OLLAMA_HOST)

def get_relevant_tables(chunk: Dict, schema_names: List[str], client: Client) -> List[str]:
    """Pre-flight check: Ask LLM which tables are actually mentioned in this text."""
    if not schema_names: return []
    
    prompt = f"""Review the text and identify which of these database tables are likely to have data present.
TABLES: {json.dumps(schema_names)}
TEXT: "{chunk['text']}"

Output strictly a JSON list of table names found. If none, output []."""
    
    try:
        response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json')
        content = json.loads(response['message']['content'])
        if isinstance(content, list):
            return [t for t in content if t in schema_names]
        elif isinstance(content, dict):
            for v in content.values():
                if isinstance(v, list):
                    return [t for t in v if t in schema_names]
        return []
    except:
        return []

def extract_multi_tables(chunk: Dict, tables: List[str], schema: Dict, client: Client) -> Dict[str, List[Dict]]:
    """Phase 3.1: One-Shot Extraction for multiple tables at once."""
    if not tables: return {}
    
    table_configs = {t: {
        "definition": schema[t].get("definition", ""),
        "columns": [c["name"] for c in schema[t]["columns"]],
        "pk_col": schema[t].get("_meta", {}).get("primary_key", [c["name"] for c in schema[t]["columns"]][0])
    } for t in tables}

    prompt = f"""Task: Extract data for multiple tables from the provided Target Text.
TARGET TABLES: {json.dumps(table_configs)}

CONTEXT (Information from previous text):
"{chunk.get('previous_context', '')}"

TARGET TEXT (Extract from this):
"{chunk['text']}"

INSTRUCTIONS:
1. READ CONTEXT: Note entities mentioned in context for pronoun resolution.
2. RESOLVE PRONOUNS: If Target Text uses 'It', 'They', 'He', 'She', or 'The company', resolve them to the specific entity name from Context.
3. EXTRACT: Extract data strictly for the specified columns of each table.
4. NO LEAKAGE: Primary Keys MUST be concise names/IDs (max 5 words). No full sentences in PK columns.
5. FORMAT: Output strictly a JSON object where keys are Table Names and values are lists of extracted records.

JSON FORMAT:
{{
  "TableName": [{"pk_column": "Resolved Name", "attr": "value"}]
}}"""

    try:
        response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json', options={"temperature": 0.3})
        content = json.loads(response['message']['content'])
        
        # Validation and Sanitization
        final_extracted = {}
        for table_name, records in content.items():
            if table_name not in tables: continue
            if not isinstance(records, list): continue
            
            sanitized_records = []
            pk_col = table_configs[table_name]["pk_col"]
            cols = table_configs[table_name]["columns"]
            
            for rec in records:
                if not isinstance(rec, dict): continue
                # Basic column alignment and PK check
                new_rec = {}
                for k, v in rec.items():
                    matched = False
                    for target_col in cols:
                        if k.lower() == target_col.lower():
                            new_rec[target_col] = v
                            matched = True
                            break
                    if not matched: new_rec[k] = v
                
                # Check for PK presence or fallback
                if pk_col not in new_rec:
                    for k, v in list(new_rec.items()):
                        if k not in cols and isinstance(v, str) and len(v.split()) < 10:
                            new_rec[pk_col] = v
                            break
                
                pk_val = new_rec.get(pk_col)
                if pk_val and not isinstance(pk_val, (list, dict)) and len(str(pk_val).split()) <= 10:
                    sanitized_records.append(new_rec)
            
            if sanitized_records:
                final_extracted[table_name] = sanitized_records
        
        return final_extracted
    except:
        return {}

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

def process_chunk(chunk: Dict, schema: Dict) -> Dict:
    """Worker function for parallel extraction - RAW Extraction only."""
    client = get_llm_client()
    chunk_data = {"chunk_id": chunk["id"], "tables": {}}
    
    # 1. Pre-flight check
    relevant_tables = get_relevant_tables(chunk, list(schema.keys()), client)
    if not relevant_tables: return chunk_data

    # 2. One-Shot Extraction for all relevant tables
    chunk_data["tables"] = extract_multi_tables(chunk, relevant_tables, schema, client)
    return chunk_data

def batch_nli_validation(extracted_raw_file: str, schema: Dict, output_file: str):
    """Post-processing: Validate unique (Table, Entity) pairs row-by-row to save memory."""
    print("\nStarting Batch NLI Validation (Precision Pass)...")
    nli_guard = NLIGuardrail()
    
    # 1. Collect unique entities per table (This is small enough for RAM)
    table_entities = defaultdict(set)
    if not os.path.exists(extracted_raw_file): return

    print("  Scanning raw extraction for unique entities...")
    with open(extracted_raw_file, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line)
                for table_name, records in entry["tables"].items():
                    pk_info = schema.get(table_name, {}).get("_meta", {})
                    pk_col = pk_info.get("primary_key")
                    if not pk_col:
                        pk_col = [c["name"] for c in schema[table_name]["columns"]][0]
                    
                    for r in records:
                        val = r.get(pk_col)
                        if val: table_entities[table_name].add(str(val))
            except: continue

    # 2. Validate unique entities in batches (GPU optimized)
    valid_map = defaultdict(set)
    for table_name, entities in table_entities.items():
        if not entities: continue
        entity_list = list(entities)
        print(f"  Validating {len(entity_list)} unique entities for table: {table_name}")
        
        definition = schema[table_name].get("definition", "")
        batch_size = 128
        for i in range(0, len(entity_list), batch_size):
            batch = entity_list[i : i + batch_size]
            valid_batch = nli_guard.validate_entities(table_name, definition, batch)
            valid_map[table_name].update(valid_batch)

    # 3. Stream from disk to output file (Memory Safe)
    print(f"  Filtering and saving validated data to {output_file}...")
    with open(extracted_raw_file, 'r') as f_in, open(output_file, "w") as f_out:
        for line in f_in:
            try:
                entry = json.loads(line)
                filtered_tables = {}
                for table_name, records in entry["tables"].items():
                    pk_info = schema.get(table_name, {}).get("_meta", {})
                    pk_col = pk_info.get("primary_key")
                    if not pk_col:
                        pk_col = [c["name"] for c in schema[table_name]["columns"]][0]
                    
                    valid_records = [r for r in records if str(r.get(pk_col)) in valid_map[table_name]]
                    if valid_records:
                        filtered_tables[table_name] = valid_records
                
                if filtered_tables:
                    entry["tables"] = filtered_tables
                    f_out.write(json.dumps(entry) + "\n")
            except: continue

def main():
    if not os.path.exists("schema.json") or not os.path.exists("chunks.json"):
        print("Files missing.")
        return

    with open("schema.json", 'r') as f: schema = json.load(f)
    # Load chunks as a generator if possible, but for now we just process them in a safe loop
    with open("chunks.json", 'r') as f: chunks = json.load(f)
    
    file_lock = Lock()
    raw_output_file = "extracted_raw_v8.jsonl"
    final_output_file = "extracted_data_v8.jsonl"
    
    # Ensure raw file is fresh
    with open(raw_output_file, "w") as f: pass

    print(f"Starting RAW extraction on {len(chunks)} chunks with {MAX_WORKERS} threads (Memory Safe)...")
    
    completed = 0
    # Use a sliding window of futures to avoid OOM
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit tasks in manageable chunks
        chunk_size = 1000
        for i in range(0, len(chunks), chunk_size):
            batch = chunks[i : i + chunk_size]
            futures = {executor.submit(process_chunk, chunk, schema): chunk for chunk in batch}
            
            for future in as_completed(futures):
                try:
                    chunk_result = future.result()
                    if chunk_result and chunk_result.get("tables"):
                        with file_lock:
                            with open(raw_output_file, "a") as f:
                                f.write(json.dumps(chunk_result) + "\n")
                except: pass
                
                completed += 1
                if completed % 100 == 0:
                    print(f"  Progress: {completed}/{len(chunks)} chunks extracted.", flush=True)

    # Decoupled Precision Pass (Memory Safe)
    batch_nli_validation(raw_output_file, schema, final_output_file)
    print(f"\nExtraction complete. Final results saved to {final_output_file}")

if __name__ == "__main__":
    main()
