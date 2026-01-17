import json
import os
import torch
import numpy as np
from typing import List, Dict
from collections import defaultdict
from sentence_transformers import CrossEncoder

# Configuration
NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-base"

class NLIBinder:
    def __init__(self, model_name=NLI_MODEL_NAME):
        print(f"Loading NLI model for attribute validation: {model_name}...")
        self.model = CrossEncoder(model_name)
        self.labels = self.model.config.id2label
        
    def validate_attribute(self, column_name: str, value: str) -> bool:
        if not value or str(value).lower() == "null" or len(str(value)) < 2:
            return False
        # Premise: "This is a valid {column_name}."
        # Hypothesis: "{value} is a {column_name}."
        premise = f"This is a {column_name}."
        hypothesis = f"'{value}' is a {column_name}."
        
        logits = self.model.predict([premise, hypothesis])
        # Logits to probs
        probs = torch.nn.functional.softmax(torch.tensor(logits), dim=0).numpy()
        
        label_map = {v.lower(): k for k, v in self.labels.items()}
        ent_idx = label_map.get('entailment', 2)
        con_idx = label_map.get('contradiction', 0)
        
        # Entailment must be significantly higher than contradiction
        return probs[ent_idx] > 0.3 and probs[ent_idx] > probs[con_idx]

def fuse_records(records: List[Dict], pk_col: str, nli_binder: NLIBinder) -> Dict:
    """Additive Fusion: Longest non-null string wins."""
    fused = {}
    for record in records:
        for k, v in record.items():
            if v is None or str(v).lower() == "null": continue
            
            # Step 5.1: Type Checking via NLI (Only for non-PK columns)
            if k != pk_col:
                if not nli_binder.validate_attribute(k, str(v)):
                    continue
            
            # Step 5.2: Additive Fusion (Longest wins)
            if k not in fused or len(str(v)) > len(str(fused[k])):
                fused[k] = v
    return fused

def main():
    if not os.path.exists("extracted_data_v8.jsonl") or not os.path.exists("resolution_map_v8.json") or not os.path.exists("schema.json"):
        print("Required files missing.")
        return

    with open("schema.json", 'r') as f: schema = json.load(f)
    with open("resolution_map_v8.json", 'r') as f: res_map = json.load(f)
    
    nli_binder = NLIBinder()
    
    # table -> canonical_pk -> list of records
    grouped_records = defaultdict(lambda: defaultdict(list))
    
    with open("extracted_data_v8.jsonl", 'r') as f:
        for line in f:
            entry = json.loads(line)
            for table_name, records in entry["tables"].items():
                col_names = [c["name"] for c in schema[table_name]["columns"]]
                pk_col = next((p for p in ["name", "identifier", "id"] if p in col_names), col_names[0])
                
                table_res_map = res_map.get(table_name, {})
                
                for r in records:
                    pk_val = str(r.get(pk_col, ""))
                    if not pk_val: continue
                    
                    canonical_pk = table_res_map.get(pk_val, pk_val)
                    # Update the record with canonical PK
                    r[pk_col] = canonical_pk
                    grouped_records[table_name][canonical_pk].append(r)

    # Final Fusion
    final_data = defaultdict(list)
    for table_name, pks in grouped_records.items():
        print(f"Fusing records for table: {table_name}")
        col_names = [c["name"] for c in schema[table_name]["columns"]]
        pk_col = next((p for p in ["name", "identifier", "id"] if p in col_names), col_names[0])
        
        for canonical_pk, records in pks.items():
            fused_row = fuse_records(records, pk_col, nli_binder)
            if fused_row:
                final_data[table_name].append(fused_row)

    with open("final_data.json", "w") as f:
        json.dump(final_data, f, indent=2)

    print("Phase 5: Binding and Fusion complete. Saved to final_data.json")

if __name__ == "__main__":
    main()
