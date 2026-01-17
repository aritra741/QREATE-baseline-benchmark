import json
import os
import numpy as np
import faiss
from typing import List, Dict, Set, Tuple
from collections import defaultdict
from ollama import Client
from langchain_huggingface import HuggingFaceEmbeddings

# Configuration
MODEL_NAME = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"
SIMILARITY_THRESHOLD = 0.85 

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

def resolve_block_with_llm(mentions: List[str], client: Client) -> Dict[str, str]:
    """
    Discriminative LLM Resolution (Splitter Pattern).
    Strictly domain-agnostic rules for entity identity.
    """
    if len(mentions) <= 1:
        return {m: m for m in mentions}

    prompt = f"""Analyze these semantically similar mentions and group them into Canonical Entities.
MENTIONS: {json.dumps(mentions)}

RULES FOR GROUPING:
1. SYNONYMS: Map abbreviations, case variations, and aliases to the same canonical name.
2. DISTINCT VARIANTS: If mentions refer to different versions, models, sub-types, or distinct physical iterations of a base concept, they MUST remain separate.
3. CATEGORY VS INSTANCE: A generic category and a specific member of that category are DIFFERENT unless the member is a direct synonym for the category in this context.

Output strictly a JSON map: {{ "Original Mention": "Canonical Name" }} for every mention in the list.
"""
    try:
        response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json')
        return json.loads(response['message']['content'])
    except:
        return {m: mentions[0] for m in mentions}

def map_triple_to_schema(triple: Dict, schema: Dict, client: Client) -> Dict:
    schema_summary = {t: [c["name"] for c in info["columns"]] for t, info in schema.items()}
    prompt = f"""Map this atomic fact to the Relational Schema.
FACT: ({triple['subject']}, {triple['relation']}, {triple['object']})
SCHEMA: {json.dumps(schema_summary)}

Output strictly JSON: {{"table": "TableName", "column": "ColumnName"}}. If no mapping is valid, output null.
"""
    try:
        response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json')
        return json.loads(response['message']['content'])
    except:
        return None

def main():
    if not os.path.exists("schema.json") or not os.path.exists("raw_triples.jsonl"):
        print("Required files missing.")
        return

    with open("schema.json", 'r') as f: schema = json.load(f)
    client = get_llm_client()
    embeddings_model = get_embeddings()
    
    raw_triples = []
    unique_subjects = []
    subject_to_idx = {}
    
    with open("raw_triples.jsonl", 'r') as f:
        for line in f:
            t = json.loads(line)
            raw_triples.append(t)
            subj = t["subject"]
            if subj not in subject_to_idx:
                subject_to_idx[subj] = len(unique_subjects)
                unique_subjects.append(subj)

    if not unique_subjects: return

    # HNSW-Union-Find Blocking (ANN O(log N) Search)
    print(f"Indexing {len(unique_subjects)} entities using HNSW...")
    uf = UnionFind(unique_subjects)
    dim = 1024 
    # IndexHNSWFlat: Graph-based ANN. 'Flat' means full vector storage, not O(N) search.
    index = faiss.IndexHNSWFlat(dim, 32) 
    
    for i, subj in enumerate(unique_subjects):
        emb = np.array(embeddings_model.embed_query(subj), dtype='float32').reshape(1, -1)
        faiss.normalize_L2(emb)
        
        if i > 0:
            # Graph-based search for nearest neighbors
            D, I = index.search(emb, 1)
            if D[0][0] >= SIMILARITY_THRESHOLD:
                neighbor_idx = I[0][0]
                uf.union(subj, unique_subjects[neighbor_idx])
        
        index.add(emb)

    # Resolution & Mapping
    blocks = uf.get_groups()
    final_resolution_map = {}
    print(f"Resolving {len(blocks)} clusters via Splitter Pattern...")
    for members in blocks.values():
        mapping = resolve_block_with_llm(list(members), client)
        final_resolution_map.update(mapping)

    final_data_map = defaultdict(lambda: defaultdict(dict))
    for t in raw_triples:
        mapping = map_triple_to_schema(t, schema, client)
        if mapping and mapping.get("table") in schema:
            table, col, val = mapping["table"], mapping["column"], t["object"]
            subject = final_resolution_map.get(t["subject"], t["subject"])
            col_names = [c["name"] for c in schema[table]["columns"]]
            pk_col = next((p for p in ["name", "identifier", "id"] if p in col_names), col_names[0])
            
            record = final_data_map[table][subject]
            record[pk_col] = subject
            if col in col_names and (col not in record or len(str(val)) > len(str(record[col]))):
                record[col] = val

    output_data = {t: list(rows.values()) for t, rows in final_data_map.items()}
    with open("final_data.json", "w") as f:
        json.dump(output_data, f, indent=2)
    print("V7.1 HNSW-Union-Find resolution complete.")

if __name__ == "__main__":
    main()
