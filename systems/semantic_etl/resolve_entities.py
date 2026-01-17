import json
import numpy as np
import os
from typing import List, Dict, Set
from sklearn.cluster import AgglomerativeClustering
from langchain_huggingface import HuggingFaceEmbeddings
from collections import defaultdict

def get_embeddings():
    return HuggingFaceEmbeddings(model_name="BAAI/bge-m3")

class UnionFind:
    def __init__(self, elements):
        self.parent = {e: e for e in elements}
        self.rank = {e: 0 for e in elements}
    
    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    
    def union(self, x, y):
        root_x = self.find(x)
        root_y = self.find(y)
        if root_x != root_y:
            if self.rank[root_x] < self.rank[root_y]:
                self.parent[root_x] = root_y
            elif self.rank[root_x] > self.rank[root_y]:
                self.parent[root_y] = root_x
            else:
                self.parent[root_y] = root_x
                self.rank[root_x] += 1
            return True
        return False

    def get_groups(self):
        groups = defaultdict(list)
        for element in self.parent:
            root = self.find(element)
            groups[root].append(element)
        return groups

def main():
    if not os.path.exists("schema.json") or not os.path.exists("extracted_raw.jsonl"):
        print("Required files missing (schema.json or extracted_raw.jsonl)")
        return

    with open("schema.json", 'r') as f:
        schema = json.load(f)

    # Identify columns to check for links: PKs, FKs, and common identifier names
    link_cols = defaultdict(set)
    for table_name, table_info in schema.items():
        col_names = [c["name"] for c in table_info["columns"]]
        potential_pks = ["name", "identifier", "model", "id", "title", "drug_name", "active_ingredient", "brand_names"]
        for col in col_names:
            if col in potential_pks:
                link_cols[table_name].add(col)
        
        for col in table_info["columns"]:
            if col["is_foreign_key"]:
                link_cols[table_name].add(col["name"])

    # Step 4.1: Bind Facts to Schema (V5 Binder)
    # table -> subject -> attributes_dict
    bound_data = defaultdict(lambda: defaultdict(dict))
    candidate_entities = set()
    
    if os.path.exists("extracted_facts.jsonl"):
        with open("extracted_facts.jsonl", 'r') as f:
            for line in f:
                fact = json.loads(line)
                table = fact["table"]
                subject = fact["subject"]
                attr = fact["attribute"]
                val = fact["value"]
                
                candidate_entities.add(subject)
                # Group all attributes for this subject in this table
                if val and str(val).lower() != "null":
                    bound_data[table][subject][attr] = val

    if not candidate_entities:
        print("No entities found to resolve.")
        with open("final_data.json", "w") as f:
            json.dump({}, f)
        return

    # Step 4.2: Resolution using Union-Find (V5 Semantic Resolver)
    uf = UnionFind(candidate_entities)
    
    # 4.2.1: Semantic Similarity Links
    entity_list = sorted(list(candidate_entities))
    embeddings_model = get_embeddings()
    print(f"Resolving {len(entity_list)} distinct subjects via Union-Find...")
    vectors = embeddings_model.embed_documents(entity_list)
    
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=0.2, 
        metric='cosine',
        linkage='average'
    )
    labels = clustering.fit_predict(np.array(vectors))
    
    cluster_to_entities = defaultdict(list)
    for i, label in enumerate(labels):
        cluster_to_entities[label].append(entity_list[i])
    
    for entities in cluster_to_entities.values():
        for i in range(len(entities) - 1):
            uf.union(entities[i], entities[i+1])
            
    # Map raw_string -> canonical_id
    groups = uf.get_groups()
    resolution_map = {member: max(members, key=len) for members in groups.values() for member in members}

    # Step 4.3: Additive Fusion (Combine triples into final rows)
    final_data_map = defaultdict(lambda: defaultdict(dict))
    
    for table, subjects in bound_data.items():
        for subject, attributes in subjects.items():
            canonical_id = resolution_map.get(subject, subject)
            
            # Identify PK column for this table
            col_names = [c["name"] for c in schema.get(table, {}).get("columns", [])]
            pk_col = next((p for p in ["name", "identifier", "model", "id"] if p in col_names), col_names[0] if col_names else "name")
            
            record = final_data_map[table][canonical_id]
            record[pk_col] = canonical_id
            
            for k, v in attributes.items():
                if k not in record or record[k] is None or str(record[k]).lower() == "null":
                    record[k] = v
                elif len(str(v)) > len(str(record[k])): # Keep longer data point
                    record[k] = v

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

    # Convert to regular dict for JSON and clean up values
    output_data = {}
    for table_name, pk_map in final_data_map.items():
        table_rows = []
        for row in pk_map.values():
            clean_row = {}
            for k, v in row.items():
                # Flatten lists/dicts into clean comma-separated strings
                if isinstance(v, list):
                    clean_row[k] = ", ".join(str(item) for item in v if item)
                elif isinstance(v, dict):
                    clean_row[k] = ", ".join(f"{dk}: {dv}" for dk, dv in v.items())
                else:
                    clean_row[k] = v
            table_rows.append(clean_row)
        output_data[table_name] = table_rows
        
    with open("final_data.json", "w") as f:
        json.dump(output_data, f, indent=2)
    
    print("Entity resolution and fusion complete. Saved to final_data.json")

if __name__ == "__main__":
    main()
