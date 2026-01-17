import json
import numpy as np
import os
from typing import List, Dict, Set
from sklearn.cluster import AgglomerativeClustering
from langchain_huggingface import HuggingFaceEmbeddings
from collections import defaultdict

def get_embeddings():
    return HuggingFaceEmbeddings(model_name="BAAI/bge-m3")

def main():
    if not os.path.exists("schema.json") or not os.path.exists("extracted_raw.jsonl"):
        print("Required files missing (schema.json or extracted_raw.jsonl)")
        return

    with open("schema.json", 'r') as f:
        schema = json.load(f)

    # Identify columns to resolve: PKs and FKs
    resolve_cols = defaultdict(set) # table -> set of column names
    for table_name, table_info in schema.items():
        # Heuristic: PK is "name" if it exists, otherwise the first column
        col_names = [c["name"] for c in table_info["columns"]]
        pk = "name" if "name" in col_names else (col_names[0] if col_names else None)
        if pk:
            resolve_cols[table_name].add(pk)
        
        for col in table_info["columns"]:
            if col["is_foreign_key"]:
                resolve_cols[table_name].add(col["name"])

    # Step 4.1: Collect Candidates
    candidate_entities = set()
    records = []
    with open("extracted_raw.jsonl", 'r') as f:
        for line in f:
            chunk_record = json.loads(line)
            data = chunk_record["data"]
            records.append(data)
            for table_name, table_rows in data.items():
                if table_name in resolve_cols:
                    cols_to_check = resolve_cols[table_name]
                    for row in table_rows:
                        for col in cols_to_check:
                            val = row.get(col)
                            if val and isinstance(val, str):
                                candidate_entities.add(val)

    if not candidate_entities:
        print("No entities found to resolve.")
        # Create an empty final_data.json anyway
        with open("final_data.json", "w") as f:
            json.dump({}, f)
        return

    # Step 4.2: Resolution Clustering
    entity_list = sorted(list(candidate_entities))
    embeddings_model = get_embeddings()
    vectors = embeddings_model.embed_documents(entity_list)
    
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=0.1,
        metric='cosine',
        linkage='average'
    )
    labels = clustering.fit_predict(np.array(vectors))
    
    # Map raw_string -> canonical_id (longest string in cluster)
    cluster_to_entities = defaultdict(list)
    for i, label in enumerate(labels):
        cluster_to_entities[label].append(entity_list[i])
    
    resolution_map = {}
    for label, entities in cluster_to_entities.items():
        canonical_id = max(entities, key=len)
        for ent in entities:
            resolution_map[ent] = canonical_id

    # Step 4.3: Rewrite and Fuse
    final_data = defaultdict(lambda: defaultdict(dict)) # table -> pk_val -> record

    for data in records:
        for table_name, table_rows in data.items():
            if table_name not in schema: continue
            
            # Identify PK for this table
            col_names = [c["name"] for c in schema[table_name]["columns"]]
            pk_col = "name" if "name" in col_names else (col_names[0] if col_names else None)
            
            for row in table_rows:
                # Rewrite values in all columns (if they are in the resolution map)
                new_row = {}
                for col_name, val in row.items():
                    if isinstance(val, str) and val in resolution_map:
                        new_row[col_name] = resolution_map[val]
                    else:
                        new_row[col_name] = val
                
                if not pk_col: continue
                
                pk_val = new_row.get(pk_col)
                if pk_val is None: continue
                
                # Fuse records
                existing_record = final_data[table_name][pk_val]
                for k, v in new_row.items():
                    if v is not None:
                        # Merge Logic: If Record A has null and Record B has value, keep value
                        if k not in existing_record or existing_record[k] is None:
                            existing_record[k] = v
    
    # Convert to regular dict for JSON
    output_data = {}
    for table_name, pk_map in final_data.items():
        output_data[table_name] = list(pk_map.values())
        
    with open("final_data.json", "w") as f:
        json.dump(output_data, f, indent=2)
    
    print("Entity resolution and fusion complete. Saved to final_data.json")

if __name__ == "__main__":
    main()
