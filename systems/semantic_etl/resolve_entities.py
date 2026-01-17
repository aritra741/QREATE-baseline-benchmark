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
        
    def resolve_table_entities(self, unique_entities: List[str], rich_texts: List[str]) -> Dict[str, str]:
        if not unique_entities: return {}
        if len(unique_entities) == 1: return {unique_entities[0]: unique_entities[0]}
            
        # 1. HNSW Indexing using Rich Texts
        dim = 1024
        index = faiss.IndexHNSWFlat(dim, 32)
        embs = np.array(self.embeddings.embed_documents(rich_texts), dtype='float32')
        faiss.normalize_L2(embs)
        index.add(embs)
        
        # 2. Retrieve & Rank (Using the same rich texts)
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
        print("\n--- ER DEBUG: Similarity Scoring ---")
        for idx, score in enumerate(scores):
            e1, e2 = pairs[idx]
            status = "NO MERGE"
            if score > SIMILARITY_THRESHOLD:
                status = "MERGED"
                # Specific Wins: Longest entity is the parent
                if len(e1) <= len(e2): self._union(parent, e1, e2)
                else: self._union(parent, e2, e1)
            
            if score > 0.5: # Only log interesting candidates
                print(f"  Pair: '{e1}' <-> '{e2}'")
                print(f"    Similarity: {score:.4f} -> {status}")
                    
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
    
    resolver = EntityResolver()
    global_resolution_map = {} # table -> {old -> new}

    # table -> list of all extracted records
    table_to_full_records = defaultdict(list)
    with open("extracted_data_v8.jsonl", 'r') as f:
        for line in f:
            entry = json.loads(line)
            for table_name, records in entry["tables"].items():
                table_to_full_records[table_name].extend(records)

    for table_name, records in table_to_full_records.items():
        print(f"Resolving entities for table: {table_name}")
        
        table_info = schema.get(table_name, {})
        pk_col = table_info.get("_meta", {}).get("primary_key")
        if not pk_col:
            pk_col = [c["name"] for c in table_info.get("columns", [])][0] if table_info.get("columns") else "name"
            
        definition = table_info.get("definition", "an entity")
        
        # 1. Construct Rich Vectors for each unique PK mention in this table
        pk_to_rich_text = defaultdict(list)
        for r in records:
            pk_val = r.get(pk_col)
            if pk_val is None or str(pk_val).lower() == "null": continue
            
            # Sanitization: If PK is somehow a stringified list or dict, skip it
            # This shouldn't happen with the new extract_data.py but good for robustness
            val_str = str(pk_val).strip()
            if val_str.startswith('[') or val_str.startswith('{'):
                print(f"  [DEBUG] Skipping resolution for complex PK: {val_str[:50]}...")
                continue
            
            # Construct summary of attributes (Rich Vector)
            # Filter out nulls, empty strings, and the PK itself
            attrs_list = []
            for k, v in r.items():
                if k != pk_col and v and str(v).lower() != "null":
                    # If attribute value is a list/dict, stringify it concisely
                    if isinstance(v, (list, dict)):
                        v_str = json.dumps(v)
                    else:
                        v_str = str(v)
                    attrs_list.append(f"{k}: {v_str}")
            
            rich_sentence = f"{val_str} is a {definition}."
            if attrs_list:
                rich_sentence += f" It has {', '.join(attrs_list)}."
            
            pk_to_rich_text[val_str].append(rich_sentence)
            
        # For each unique PK mention, take its most descriptive (longest) rich sentence
        unique_mentions = []
        rich_texts = []
        for pk_val, sentences in pk_to_rich_text.items():
            unique_mentions.append(pk_val)
            rich_texts.append(max(sentences, key=len))
            
        if not unique_mentions: continue
        
        # 2. Resolve using Rich Vectors
        print(f"  Indexing {len(unique_mentions)} rich entities...")
        mapping = resolver.resolve_table_entities(unique_mentions, rich_texts)
        global_resolution_map[table_name] = mapping

    with open("resolution_map_v8.json", "w") as f:
        json.dump(global_resolution_map, f, indent=2)

    print("Phase 4 resolution complete.")

if __name__ == "__main__":
    main()
