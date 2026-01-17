import numpy as np
import networkx as nx
import igraph as ig
import leidenalg as la
from sklearn.neighbors import NearestNeighbors
from typing import Dict, List, Any, Optional
import ollama
import json
import re
from langchain_huggingface import HuggingFaceEmbeddings

BANNED_TYPES = {"entity", "object", "thing", "noun", "item", "unknown", "null", "miscellaneous"}

class QREATEOntologyManager:
    def __init__(self, embedding_model_name: str = "intfloat/e5-large-v2"):
        self.embeddings = HuggingFaceEmbeddings(model_name=embedding_model_name)
        self.model = "qwen2.5:7b-instruct"

    def clean_types(self, graph: nx.MultiDiGraph):
        """
        Executes the Leiden Filter to group synonyms and filter non-categorical labels.
        """
        # 1. Extract unique vocabulary
        unique_types = []
        for _, data in graph.nodes(data=True):
            t = data.get('entity_type')
            if t:
                unique_types.append(t)
        
        unique_types = sorted(list(set(unique_types)))
        if not unique_types:
            return

        # 2. Generate embeddings and build KNN graph (k=min(10, len-1))
        type_embeddings = self.embeddings.embed_documents(unique_types)
        n_samples = len(unique_types)
        k = min(10, n_samples - 1)
        
        if k < 1:
            # Not enough types to cluster, just rewrite to canonical strings
            canonical_map = {t: t.strip().capitalize() for t in unique_types}
            self._rewrite_graph(graph, canonical_map)
            return

        knn = NearestNeighbors(n_neighbors=k, metric='cosine')
        knn.fit(type_embeddings)
        distances, indices = knn.kneighbors(type_embeddings)

        # 3. Build igraph and execute Leiden
        edges = []
        weights = []
        for i in range(n_samples):
            for j_idx, neighbor_idx in enumerate(indices[i]):
                if i != neighbor_idx:
                    edges.append((i, neighbor_idx))
                    # Weight is 1 - distance (cosine distance)
                    weights.append(max(0.01, 1.0 - distances[i][j_idx]))

        g = ig.Graph(n=n_samples, edges=edges, directed=False)
        g.es['weight'] = weights
        
        partition = la.find_partition(g, la.ModularityVertexPartition, weights=g.es['weight'])
        
        # 4. Canonical Table Mapping
        clusters = {}
        for idx, cluster_id in enumerate(partition.membership):
            if cluster_id not in clusters:
                clusters[cluster_id] = []
            clusters[cluster_id].append(unique_types[idx])

        type_to_canonical = {}
        for cluster_id, members in clusters.items():
            # Get frequencies from graph to find most frequent string
            freqs = {}
            for m in members:
                freqs[m] = sum(1 for _, data in graph.nodes(data=True) if data.get('entity_type') == m)
            
            rep = max(members, key=lambda m: freqs[m])
            
            # Execute LLM verification
            canonical = self._llm_verify_type(rep, members)
            
            # Banned Types Filter: Dissolve if canonical name is banned
            if canonical and canonical.lower() in BANNED_TYPES:
                canonical = None
                
            for m in members:
                type_to_canonical[m] = canonical

        # 5. Graph Rewrite
        self._rewrite_graph(graph, type_to_canonical)

    def _llm_verify_type(self, rep: str, members: List[str]) -> Optional[str]:
        prompt = f"""You are an Ontology Expert. Analyze this cluster of entity types and nominate a single, high-level, formal Table Name (noun).
If the strings are non-categorical (adjectives like 'Genius', 'Fast', or statuses like 'Active'), return NULL.

Representative: {rep}
All Cluster Members: {members}

Rules:
1. Return ONLY the Table Name or the word NULL.
2. Table Name must be a generic noun (e.g., 'Company', 'Medication', 'Smartphone').
3. No descriptions or phrases. 1-2 words max.

Response:"""
        try:
            response = ollama.generate(model=self.model, prompt=prompt)
            output = response['response'].strip().upper().replace('"', '').replace("'", "")
            if "NULL" in output:
                return None
            return output
        except:
            return rep.strip().upper()

    def _rewrite_graph(self, graph: nx.MultiDiGraph, type_map: Dict[str, Optional[str]]):
        for node_id, data in graph.nodes(data=True):
            old_type = data.get('entity_type')
            if old_type in type_map:
                data['entity_type'] = type_map[old_type]
            elif old_type:
                # Fallback for anything missed
                data['entity_type'] = old_type.strip().upper()
