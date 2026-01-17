import os
import pickle
import pandas as pd
from typing import List, Dict, Any, Tuple
from .chunking import QREATEChunker
from .extraction.miner import QREATEMiner
from .kg.kg_state import QREATEKGState
from .resolution.resolver import QREATEResolver
from .topology.topology_materializer import QREATETopologyMaterializer
from .storage.query_shim import QREATESQLShim

from .topology.ontology import QREATEOntologyManager

class QREATE:
    def __init__(self, cache_dir: str = ".cache/qreate_state.pkl"):
        self.cache_dir = cache_dir
        self.chunker = QREATEChunker()
        self.miner = QREATEMiner()
        self.resolver = QREATEResolver()
        self.kg = QREATEKGState()
        self.materializer = QREATETopologyMaterializer()
        self.ontology_manager = QREATEOntologyManager()
        self.processed_docs = 0
        self.db = None
        self.shim = None

    def save_state(self):
        os.makedirs(os.path.dirname(self.cache_dir), exist_ok=True)
        state = {
            "processed_docs": self.processed_docs,
            "kg_graph": self.kg.graph,
            "resolver_exact_match_cache": self.resolver.exact_match_cache,
            "resolver_variant_split_cache": self.resolver.variant_split_cache,
            "resolver_node_metadata": self.resolver.node_metadata,
            "resolver_alias_map": self.resolver.alias_map,
            "resolver_next_node_id": self.resolver.next_node_id,
        }
        with open(self.cache_dir, 'wb') as f:
            pickle.dump(state, f)
        print(f"State saved to {self.cache_dir}")

    def load_state(self):
        if os.path.exists(self.cache_dir):
            with open(self.cache_dir, 'rb') as f:
                state = pickle.load(f)
            self.processed_docs = state["processed_docs"]
            self.kg.graph = state["kg_graph"]
            self.resolver.exact_match_cache = state["resolver_exact_match_cache"]
            self.resolver.variant_split_cache = state["resolver_variant_split_cache"]
            self.resolver.node_metadata = state["resolver_node_metadata"]
            self.resolver.alias_map = state["resolver_alias_map"]
            self.resolver.next_node_id = state["resolver_next_node_id"]
            # Rebuild Faiss
            for node_id, meta in self.resolver.node_metadata.items():
                embed = meta["embedding"].reshape(1, -1)
                faiss_id = self.resolver.index.ntotal
                self.resolver.index.add(embed)
                self.resolver.id_to_node_id[faiss_id] = node_id
            print(f"State loaded from {self.cache_dir}")

    def ingest_documents(self, doc_dir: str):
        files = [f for f in os.listdir(doc_dir) if os.path.isfile(os.path.join(doc_dir, f))]
        
        for i, filename in enumerate(files):
            if i < self.processed_docs:
                continue
            
            file_path = os.path.join(doc_dir, filename)
            print(f"Processing {filename} ({i+1}/{len(files)})")
            
            chunks = self.chunker.chunk_document(file_path, filename)
            focus_state = []
            
            for chunk in chunks:
                chunk_triples, focus_state = self.miner.extract_triples(chunk['text'], focus_state)
                
                for t in chunk_triples:
                    if not t.get('sub'): continue
                    sub_id = self.resolver.resolve(t['sub'])
                    obj_id = None
                    if t.get('object_type') == 'ENTITY' and t.get('obj'):
                        obj_id = self.resolver.resolve(t['obj'])
                    
                    self.kg.add_triple(t, sub_id, obj_id)
            
            self.processed_docs += 1
            if self.processed_docs % 5 == 0:
                self.save_state()
        self.save_state()

    def materialize(self):
        # NEW SEQUENCE:
        # 2. OntologyManager.clean_types (Leiden Filter)
        print("Cleaning Ontology (Leiden Filter)...")
        self.ontology_manager.clean_types(self.kg.graph)

        # 3. Materializer.rescue_orphans (Signature Fitting)
        print("Rescuing Orphans (Signature Fitting)...")
        self.materializer.rescue_orphans(self.kg.graph)

        print("Materializing Knowledge Graph (DuckDB Load)...")
        self.db = self.materializer.materialize(self.kg.graph, self.resolver.node_metadata, self.resolver.alias_map)
        self.shim = QREATESQLShim(self.db, self.resolver)
        print("Materialization complete.")

    def run_query(self, query: Dict) -> Tuple[pd.DataFrame, Dict]:
        sql = query.get("sql", "")
        dataset_path = query.get("dataset_path", "")
        
        import time
        from datetime import datetime
        
        start_time = time.time()
        metadata = {
            "system": "QREATE",
            "query_id": query.get("id"),
            "start_time": datetime.now().isoformat()
        }
        
        if not self.shim:
            if dataset_path and self.processed_docs == 0:
                self.ingest_documents(dataset_path)
            self.materialize()
        
        df = self.shim.execute_query(sql)
        
        metadata["total_time"] = time.time() - start_time
        metadata["end_time"] = datetime.now().isoformat()
        metadata["status"] = "completed" if not df.empty else "empty_or_failed"
        
        return df, metadata

qreate_instance = None

def run_query(query: Dict) -> Tuple[pd.DataFrame, Dict]:
    global qreate_instance
    if qreate_instance is None:
        qreate_instance = QREATE()
        qreate_instance.load_state()
    return qreate_instance.run_query(query)
