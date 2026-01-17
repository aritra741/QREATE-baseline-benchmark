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
        self.exact_match_cache = {} # canonical_name -> node_id
        self.variant_split_cache = set() # (S, C) tuples
        self.node_metadata = {} # node_id -> {"canonical_name": str, "embedding": np.ndarray}
        self.next_node_id = 0
        
        # Faiss HNSW index
        self.dimension = 1024 # e5-large-v2 dimension
        self.index = faiss.IndexHNSWFlat(self.dimension, 32)
        self.id_to_node_id = {} # faiss_id -> node_id

    def _get_embedding(self, text: str) -> np.ndarray:
        return np.array(self.embeddings.embed_query(text)).astype('float32')

    def resolve(self, subject: str) -> str:
        # Tier 1: Memoization (Normalize: lowercase, trim, replace underscores/dashes with spaces)
        s_norm = subject.lower().strip().replace('_', ' ').replace('-', ' ')
        
        if s_norm in self.exact_match_cache:
            return self.exact_match_cache[s_norm]
        
        # Tier 2: Semantic Search (Top-5)
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
                # Tier 3: Negative Cache (variant_split_cache)
                filtered_candidates = [c for c in candidates if (s_norm, c["name"].lower().replace('_', ' ').replace('-', ' ')) not in self.variant_split_cache]
                
                if filtered_candidates:
                    # Tier 4: LLM Judge
                    decision = self._llm_judge(subject, filtered_candidates)
                    if decision["decision"] == "MATCH" and decision.get("target_id") in self.node_metadata:
                        self.exact_match_cache[s_norm] = decision["target_id"]
                        return decision["target_id"]
                    elif decision["decision"] == "VARIANT" and decision.get("target_id") in self.node_metadata:
                        # Record in negative cache
                        self.variant_split_cache.add((s_norm, self.node_metadata[decision["target_id"]]["canonical_name"].lower().replace('_', ' ').replace('-', ' ')))
                        # Fall through to create NEW
        
        # NEW Node Creation
        node_id = f"node_{self.next_node_id}"
        self.next_node_id += 1
        self.exact_match_cache[s_norm] = node_id
        s_embed = self._get_embedding(subject)
        self.node_metadata[node_id] = {"canonical_name": subject, "embedding": s_embed}
        
        # Add to Faiss
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
1. MATCH: The new entity is semantically identical to a candidate.
   - Includes: Exact synonyms, different naming conventions for the same object (e.g., chemical name vs brand name), formatting variations, or shorthand.
   - Logic: If an attribute is true for '{subject}', it MUST be true for the candidate.

2. VARIANT: The new entity is a related but distinct specialization or version.
   - Includes: Incremental versions, specific models within a product line, or items with distinguishing modifiers that imply a separate identity despite sharing a root name.
   - Logic: They belong to the same lineage but are not interchangeable in a database record.

3. NEW: The new entity has no clear semantic or lineage-based relationship with the candidates.

Decision Criteria:
- Use linguistic cues: modifiers, version numbers, or specific subtype indicators often signify a VARIANT.
- Use domain knowledge: if two names refer to the same physical substance or entity, they are a MATCH.

Output Format (JSON ONLY):
{{"decision": "MATCH|VARIANT|NEW", "target_id": "ID or null"}}"""

        try:
            response = ollama.generate(
                model="qwen2.5:7b-instruct",
                prompt=prompt,
                format="json"
            )
            return json.loads(response['response'])
        except:
            return {"decision": "NEW", "target_id": None}
