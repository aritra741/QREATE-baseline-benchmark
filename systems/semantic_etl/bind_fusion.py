import json
import os
import torch
import numpy as np
from typing import List, Dict
from collections import defaultdict
from sentence_transformers import CrossEncoder
from gliner import GLiNER

# Configuration
NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-base"
GLINER_MODEL_NAME = "urchade/gliner_base"

class ValidationGuard:
    def __init__(self, schema: Dict):
        print(f"Loading NLI model: {NLI_MODEL_NAME}...")
        self.nli = CrossEncoder(NLI_MODEL_NAME)
        self.nli_labels = self.nli.config.id2label
        self.schema = schema
        
        print(f"Loading GLiNER model: {GLINER_MODEL_NAME}...")
        self.gliner = GLiNER.from_pretrained(GLINER_MODEL_NAME)
        
    def validate_attribute(self, table_name: str, column_name: str, value: str) -> bool:
        if not value or str(value).lower() == "null":
            return False
        
        val_str = str(value)
        print(f"\n    --- FUSION DEBUG: Column '{column_name}' ---")
        print(f"      Value: '{val_str}'")

        # Check if this is a Foreign Key column
        is_fk = False
        target_table = None
        for col in self.schema.get(table_name, {}).get("columns", []):
            if col["name"] == column_name and col.get("is_foreign_key"):
                is_fk = True
                target_table = col.get("references_table")
                break

        if is_fk and target_table:
            # CHANGE 4: The "Foreign Key" NLI Check
            target_def = self.schema.get(target_table, {}).get("definition", f"a {target_table} entity")
            premise = f"A {target_table} is defined as: {target_def}."
            hypothesis = f"'{val_str}' is a {target_table}."
            
            logits = self.nli.predict([premise, hypothesis])
            probs = torch.nn.functional.softmax(torch.tensor(logits), dim=0).numpy()
            
            label_map = {v.lower(): k for k, v in self.nli_labels.items()}
            ent_idx = label_map.get('entailment', 2)
            con_idx = label_map.get('contradiction', 0)
            
            p_ent = probs[ent_idx]
            p_con = probs[con_idx]
            print(f"      FK NLI Check (Target: {target_table}) -> E: {p_ent:.4f}, C: {p_con:.4f}")
            
            if p_ent > 0.5:
                print("      Result: ACCEPTED (FK Entailment)")
                return True
            elif p_con > 0.5:
                print("      Result: DISCARDED (FK Contradiction)")
                return False
            else:
                print("      Result: DISCARDED (FK Neutral/Weak)")
                return False
        
        # Default Attribute Validation (Standard)
        # 1. NLI Type Check First
        premise = f"This is a {column_name} of a {table_name}."
        hypothesis = f"'{val_str}' is a valid {column_name}."
        
        logits = self.nli.predict([premise, hypothesis])
        probs = torch.nn.functional.softmax(torch.tensor(logits), dim=0).numpy()
        
        label_map = {v.lower(): k for k, v in self.nli_labels.items()}
        ent_idx = label_map.get('entailment', 2)
        con_idx = label_map.get('contradiction', 0)
        
        p_ent = probs[ent_idx]
        p_con = probs[con_idx]
        print(f"      NLI Scores -> E: {p_ent:.4f}, C: {p_con:.4f}")
        
        if p_con > 0.6:
            print("      Result: DISCARDED (NLI Contradiction)")
            return False

        # 2. GLiNER Filter
        labels = [table_name, column_name]
        entities = self.gliner.predict_entities(val_str, labels, threshold=0.3)
        gliner_found = [e['label'] for e in entities]
        print(f"      GLiNER Labels Found: {gliner_found}")
        
        if not gliner_found and p_ent < 0.4: # Require either GLiNER or strong NLI
            print("      Result: DISCARDED (No GLiNER match & Low NLI)")
            return False

        # 3. Length Cap (Anti-Hallucination)
        if len(val_str) > 50:
            print(f"      Result: DISCARDED (Length {len(val_str)} > 50)")
            return False
            
        print("      Result: ACCEPTED")
        return True

def fuse_records(records: List[Dict], pk_col: str, table_name: str, guard: ValidationGuard) -> Dict:
    """Validated String Wins: Quality check first, then length."""
    fused = {}
    for record in records:
        for k, v in record.items():
            if v is None or str(v).lower() == "null": continue
            
            # Skip validation for PK as it's already validated in Phase 3
            if k != pk_col:
                if not guard.validate_attribute(table_name, k, v):
                    continue
            
            # Additive Fusion: Longest surviving string wins
            if k not in fused or len(str(v)) > len(str(fused[k])):
                fused[k] = v
    return fused

def main():
    if not os.path.exists("extracted_data_v8.jsonl") or not os.path.exists("resolution_map_v8.json") or not os.path.exists("schema.json"):
        print("Required files missing.")
        return

    with open("schema.json", 'r') as f: schema = json.load(f)
    with open("resolution_map_v8.json", 'r') as f: res_map = json.load(f)
    
    guard = ValidationGuard(schema)
    
    # table -> canonical_pk -> list of records
    grouped_records = defaultdict(lambda: defaultdict(list))
    
    with open("extracted_data_v8.jsonl", 'r') as f:
        for line in f:
            entry = json.loads(line)
            for table_name, records in entry["tables"].items():
                table_info = schema.get(table_name, {})
                pk_col = table_info.get("_meta", {}).get("primary_key")
                if not pk_col:
                    col_names = [c["name"] for c in table_info["columns"]]
                    pk_col = col_names[0]
                
                table_res_map = res_map.get(table_name, {})
                
                for r in records:
                    pk_val = str(r.get(pk_col, ""))
                    if not pk_val: continue
                    
                    canonical_pk = table_res_map.get(pk_val, pk_val)
                    r[pk_col] = canonical_pk
                    grouped_records[table_name][canonical_pk].append(r)

    # Final Fusion
    final_data = defaultdict(list)
    for table_name, pks in grouped_records.items():
        print(f"Fusing records for table: {table_name}")
        table_info = schema.get(table_name, {})
        pk_col = table_info.get("_meta", {}).get("primary_key")
        if not pk_col:
            col_names = [c["name"] for c in table_info["columns"]]
            pk_col = col_names[0]
        
        for canonical_pk, records in pks.items():
            fused_row = fuse_records(records, pk_col, table_name, guard)
            if fused_row:
                final_data[table_name].append(fused_row)

    with open("final_data.json", "w") as f:
        json.dump(final_data, f, indent=2)

    print("Phase 5: Validated Binding and Fusion complete. Saved to final_data.json")

if __name__ == "__main__":
    main()
