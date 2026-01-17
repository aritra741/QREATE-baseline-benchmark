import os
import json
import faiss
import numpy as np
import ollama
from typing import List, Dict, Any, Optional
from langchain_huggingface import HuggingFaceEmbeddings

class QREATEResolver:
    def __init__(self, embedding_model_name: str = "intfloat/e5-large-v2"):
        self.embeddings = HuggingFaceEmbeddings(model_name=embedding_model_name)
        self.exact_match_cache = {} # normalized_name -> node_id
        self.variant_split_cache = set() 
        self.node_metadata = {} # node_id -> {"canonical_name": str, "embedding": np.ndarray}
        self.alias_map = {} # all_names -> canonical_name
        self.next_node_id = 0
        self.dimension = 1024 
        self.index = faiss.IndexHNSWFlat(self.dimension, 32)
        self.id_to_node_id = {} 

    def _get_embedding(self, text: str) -> np.ndarray:
        return np.array(self.embeddings.embed_query(text)).astype('float32')

    def resolve(self, subject: str) -> str:
        s_norm = subject.lower().strip().replace('_', ' ').replace('-', ' ')
        
        if s_norm in self.exact_match_cache:
            return self.exact_match_cache[s_norm]
        
        if self.index.ntotal > 0:
            s_embed = self._get_embedding(s_norm).reshape(1, -1)
            k = min(5, self.index.ntotal)
            distances, indices = self.index.search(s_embed, k)
            
            candidates = []
            for idx in indices[0]:
                if idx != -1:
                    node_id = self.id_to_node_id[idx]
                    candidates.append({"id": node_id, "name": self.node_metadata[node_id]["canonical_name"]})
            
            if candidates:
                filtered_candidates = [c for c in candidates if (s_norm, c["name"].lower().replace('_', ' ')) not in self.variant_split_cache]
                
                if filtered_candidates:
                    decision = self._llm_judge(subject, filtered_candidates)
                    print(f"Resolver LLM output: {decision}")
                    if isinstance(decision, dict) and decision.get("decision") == "MATCH" and decision.get("target_id") in self.node_metadata:
                        node_id = decision["target_id"]
                        self.exact_match_cache[s_norm] = node_id
                        self.alias_map[subject] = self.node_metadata[node_id]["canonical_name"]
                        return node_id
                    elif isinstance(decision, dict) and decision.get("decision") == "VARIANT" and decision.get("target_id") in self.node_metadata:
                        self.variant_split_cache.add((s_norm, self.node_metadata[decision["target_id"]]["canonical_name"].lower().replace('_', ' ')))
        
        # NEW Node
        node_id = f"node_{self.next_node_id}"
        self.next_node_id += 1
        self.exact_match_cache[s_norm] = node_id
        s_embed = self._get_embedding(subject)
        self.node_metadata[node_id] = {"canonical_name": subject, "embedding": s_embed}
        self.alias_map[subject] = subject
        
        faiss_id = self.index.ntotal
        self.index.add(s_embed.reshape(1, -1))
        self.id_to_node_id[faiss_id] = node_id
        return node_id

    def _llm_judge(self, subject: str, candidates: List[Dict[str, str]]) -> Dict[str, Any]:
        candidate_str = "\n".join([f"- {c['id']}: {c['name']}" for c in candidates])
        prompt = f"""Task: Analyze the relationship between the new entity '{subject}' and the existing candidates.

Candidates:
{candidate_str}

Decision Categories:
1. MATCH: The new entity is logically identical to a candidate.
   - Includes: Exact synonyms, common abbreviations, different naming formats (case, punctuation), or brand names representing the same underlying substance/concept.
   - Example: 'Global Corp' matches 'Global Corporation', 'Vitamin C' matches 'Ascorbic Acid'.
2. VARIANT: The new entity is a related but distinct specialization, model, or version.
   - Includes: Sub-models, specialized editions, or iterations that share a lineage but are not interchangeable.
   - Example: 'Standard Edition' vs 'Premium Edition', '2023 Model' vs '2024 Model'.
3. NEW: The new entity is conceptually unrelated to the candidates.

Output Format (JSON ONLY):
{{"decision": "MATCH|VARIANT|NEW", "target_id": "ID or null"}}"""

        try:
            response = ollama.generate(
                model="qwen2.5:7b-instruct",
                prompt=prompt,
                format="json"
            )
            raw_output = response['response']
            import re
            json_match = re.search(r'\{\s*"decision":.*\}', raw_output, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return json.loads(raw_output)
        except:
            return {"decision": "NEW", "target_id": None}

    def normalize_data(self, tables_dfs: Dict[str, Any]):
        for table_name, df in tables_dfs.items():
            for col in df.columns:
                df[col] = df[col].apply(lambda x: self.alias_map.get(str(x), x) if isinstance(x, str) else x)
