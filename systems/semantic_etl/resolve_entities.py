import json
import os
import numpy as np
import faiss
from typing import List, Dict, Set, Tuple
from collections import defaultdict
from sentence_transformers import CrossEncoder
from langchain_huggingface import HuggingFaceEmbeddings

# Configuration
SIMILARITY_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
TOP_K_NEIGHBORS = 30
SIMILARITY_THRESHOLD = 0.8

def get_embeddings():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)

class EntityResolver:
    def __init__(self):
        print(f"Loading Similarity model: {SIMILARITY_MODEL_NAME}...")
        self.model = CrossEncoder(SIMILARITY_MODEL_NAME)
        self.embeddings = get_embeddings()
        
    def resolve_table_entities(self, unique_entities: List[str]) -> Dict[str, str]:
        if not unique_entities: return {}
        if len(unique_entities) == 1: return {unique_entities[0]: unique_entities[0]}
            
        # 1. HNSW Indexing
        dim = 1024
        index = faiss.IndexHNSWFlat(dim, 32)
        embs = np.array(self.embeddings.embed_documents(unique_entities), dtype='float32')
        faiss.normalize_L2(embs)
        index.add(embs)
        
        # 2. Retrieve & Rank
        D, I = index.search(embs, min(TOP_K_NEIGHBORS, len(unique_entities)))
        pairs = []
        pair_indices = []
        for i in range(len(unique_entities)):
            for j_idx in range(1, len(I[i])):
                neighbor_idx = I[i][j_idx]
                if neighbor_idx == -1: continue
                if i < neighbor_idx:
                    pairs.append([unique_entities[i], unique_entities[neighbor_idx]])
                    pair_indices.append((i, neighbor_idx))
        
        if not pairs: return {e: e for e in unique_entities}
            
        print(f"  Scoring {len(pairs)} pairs...")
        scores = self.model.predict(pairs)
        scores = 1 / (1 + np.exp(-scores)) # Sigmoid
        
        # 3. Subsumption Merge (Short -> Long)
        parent = {e: e for e in unique_entities}
        for idx, score in enumerate(scores):
            if score > SIMILARITY_THRESHOLD:
                e1, e2 = pairs[idx]
                # Specific Wins: Longest entity is the parent
                if len(e1) <= len(e2): self._union(parent, e1, e2)
                else: self._union(parent, e2, e1)
                    
        return {e: self._find(parent, e) for e in unique_entities}

    def _find(self, parent, i):
        if parent[i] == i: return i
        parent[i] = self._find(parent, parent[i])
        return parent[i]

    def _union(self, parent, child, p):
        root_child = self._find(parent, child)
        root_p = self._find(parent, p)
        if root_child != root_p: parent[root_child] = root_p

def main():
    if not os.path.exists("extracted_data_v8.jsonl") or not os.path.exists("schema.json"):
        print("Required files missing.")
        return

    with open("schema.json", 'r') as f: schema = json.load(f)
    
    # table -> list of unique PKs
    table_pks = defaultdict(set)
    with open("extracted_data_v8.jsonl", 'r') as f:
        for line in f:
            entry = json.loads(line)
            for table_name, records in entry["tables"].items():
                col_names = [c["name"] for c in schema[table_name]["columns"]]
                pk_col = next((p for p in ["name", "identifier", "id"] if p in col_names), col_names[0])
                for r in records:
                    if r.get(pk_col): table_pks[table_name].add(str(r[pk_col]))

    resolver = EntityResolver()
    global_resolution_map = {} # table -> {old -> new}

    for table_name, pks in table_pks.items():
        print(f"Resolving entities for table: {table_name}")
        mapping = resolver.resolve_table_entities(list(pks))
        global_resolution_map[table_name] = mapping

    with open("resolution_map_v8.json", "w") as f:
        json.dump(global_resolution_map, f, indent=2)

    print("Phase 4 resolution complete.")

if __name__ == "__main__":
    main()
