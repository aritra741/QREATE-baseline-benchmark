import json
import os
import numpy as np
from typing import List, Dict, Set
from collections import defaultdict
from ollama import Client
from sklearn.cluster import AgglomerativeClustering
from langchain_huggingface import HuggingFaceEmbeddings

# Configuration
MODEL_NAME = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"

def get_llm_client():
    return Client(host=OLLAMA_HOST)

def get_embeddings():
    return HuggingFaceEmbeddings(model_name="BAAI/bge-m3")

class UnionFind:
    def __init__(self, elements):
        self.parent = {el: el for el in elements}
    def find(self, i):
        if self.parent[i] == i: return i
        self.parent[i] = self.find(self.parent[i])
        return self.parent[i]
    def union(self, i, j):
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j: self.parent[root_i] = root_j
    def get_groups(self):
        groups = defaultdict(set)
        for el in self.parent: groups[self.find(el)].add(el)
        return groups

def map_triple_to_schema(triple: Dict, schema: Dict, client: Client) -> Dict:
    """Uses LLM to map an OpenIE triple (Subject, Relation, Object) to the relational schema."""
    schema_summary = {t: [c["name"] for c in info["columns"]] for t, info in schema.items()}
    
    prompt = f"""Map this OpenIE Triple to the Database Schema.
TRIPLE: ({triple['subject']}, {triple['relation']}, {triple['object']})
SCHEMA: {json.dumps(schema_summary)}

TASK:
1. Identify which Table and Column the 'object' data point belongs to.
2. The 'subject' is the entity name.
3. If no mapping is clear, output "null".
4. Output strictly a JSON object: {{"table": "TableName", "column": "ColumnName"}}.

JSON FORMAT:
{{"table": "Table", "column": "Column"}}"""

    try:
        response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json')
        mapping = json.loads(response['message']['content'])
        return mapping
    except:
        return None

def main():
    if not os.path.exists("schema.json") or not os.path.exists("raw_triples.jsonl"):
        print("Required files missing (schema.json or raw_triples.jsonl)")
        return

    with open("schema.json", 'r') as f: schema = json.load(f)
    client = get_llm_client()
    
    # Step 1: Collect Candidate Subjects
    candidate_subjects = set()
    raw_triples = []
    with open("raw_triples.jsonl", 'r') as f:
        for line in f:
            t = json.loads(line)
            candidate_subjects.add(t["subject"])
            raw_triples.append(t)

    if not candidate_subjects:
        print("No subjects found in triples.")
        return

    # Step 2: Entity Resolution (Union-Find)
    uf = UnionFind(candidate_subjects)
    subject_list = sorted(list(candidate_subjects))
    embeddings_model = get_embeddings()
    print(f"Resolving {len(subject_list)} subjects...")
    vectors = embeddings_model.embed_documents(subject_list)
    clustering = AgglomerativeClustering(n_clusters=None, distance_threshold=0.2, metric='cosine', linkage='average')
    labels = clustering.fit_predict(np.array(vectors))
    
    cluster_to_entities = defaultdict(list)
    for i, l in enumerate(labels): cluster_to_entities[l].append(subject_list[i])
    for entities in cluster_to_entities.values():
        for i in range(len(entities) - 1): uf.union(entities[i], entities[i+1])
    
    resolution_map = {member: max(members, key=len) for members in uf.get_groups().values() for member in members}

    # Step 3: Bind triples to schema
    final_data_map = defaultdict(lambda: defaultdict(dict))
    print(f"Binding {len(raw_triples)} triples to schema...")
    
    for t in raw_triples:
        mapping = map_triple_to_schema(t, schema, client)
        if mapping and mapping.get("table") in schema:
            table = mapping["table"]
            col = mapping["column"]
            val = t["object"]
            
            # Use canonical subject
            subject = resolution_map.get(t["subject"], t["subject"])
            
            # Identify PK for this table
            col_names = [c["name"] for c in schema[table]["columns"]]
            pk_col = next((p for p in ["name", "identifier", "id", "model"] if p in col_names), col_names[0])
            
            record = final_data_map[table][subject]
            record[pk_col] = subject
            if col in col_names:
                # Additive logic: prefer longer values
                if col not in record or not record[col] or len(str(val)) > len(str(record[col])):
                    record[col] = val

    # Step 4: Finalize and Save
    output_data = {t: list(rows.values()) for t, rows in final_data_map.items()}
    with open("final_data.json", "w") as f:
        json.dump(output_data, f, indent=2)
    print("OpenIE binding and fusion complete. Saved to final_data.json")

if __name__ == "__main__":
    main()
