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
        distance_threshold=0.2, # Relaxed from 0.1 to 0.2 for more aggressive merging (V2)
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
    # table -> pk_val -> record
    final_data_map = defaultdict(lambda: defaultdict(dict)) 

    for data in records:
        for table_name, table_rows in data.items():
            if table_name not in schema: continue
            
            # Identify PK for this table
            col_names = [c["name"] for c in schema[table_name]["columns"]]
            potential_pks = ["name", "identifier", "model", "id", "title"]
            pk_col = next((p for p in potential_pks if p in col_names), col_names[0] if col_names else None)
            
            for row in table_rows:
                new_row = {k: (resolution_map.get(v, v) if isinstance(v, str) else v) for k, v in row.items()}
                
                if not pk_col: continue
                pk_val = new_row.get(pk_col)
                if pk_val is None or str(pk_val).lower() == "null":
                    pk_val = next((v for v in new_row.values() if v and isinstance(v, str) and str(v).lower() != "null"), None)
                
                if pk_val is None or str(pk_val).lower() == "null": continue
                
                existing_record = final_data_map[table_name][pk_val]
                for k, v in new_row.items():
                    if k not in existing_record or existing_record[k] is None or str(existing_record[k]).lower() == "null":
                        existing_record[k] = v
                    elif v is not None and str(v).lower() != "null" and v != existing_record[k]:
                        if len(str(v)) > len(str(existing_record[k])):
                            existing_record[k] = v

    # Step 4.4: Phase 4.4 - Polymorphic Entity Filter (Dense Winner Strategy)
    # If an entity exists in multiple tables, keep it where it is most "dense" (most non-null attributes)
    entity_to_tables = defaultdict(list)
    for table_name, pk_map in final_data_map.items():
        for pk_val in pk_map.keys():
            entity_to_tables[pk_val].append(table_name)
    
    for entity_name, tables in entity_to_tables.items():
        if len(tables) > 1:
            # Calculate density for each table
            densities = []
            for t in tables:
                record = final_data_map[t][entity_name]
                non_null_count = sum(1 for v in record.values() if v is not None and str(v).lower() != "null")
                densities.append((non_null_count, t))
            
            # Sort by density (descending)
            densities.sort(key=lambda x: x[0], reverse=True)
            winner_table = densities[0][1]
            
            # Remove from other tables
            for _, t in densities[1:]:
                print(f"Hierarchy Filter: Removing {entity_name} from {t} (Winner: {winner_table})")
                del final_data_map[t][entity_name]

    # Convert to regular dict for JSON
    output_data = {table_name: list(pk_map.values()) for table_name, pk_map in final_data_map.items()}
        
    with open("final_data.json", "w") as f:
        json.dump(output_data, f, indent=2)
    
    print("Entity resolution and fusion complete. Saved to final_data.json")

if __name__ == "__main__":
    main()
