import re
import pandas as pd
import duckdb
from typing import List, Dict, Any, Set
from dateutil import parser as date_parser
from sklearn.cluster import AgglomerativeClustering
from langchain_huggingface import HuggingFaceEmbeddings
import numpy as np

class QREATEMaterializer:
    def __init__(self, embedding_model_name: str = "intfloat/e5-large-v2"):
        self.embeddings = HuggingFaceEmbeddings(model_name=embedding_model_name)
        self.db = duckdb.connect(':memory:')

    def materialize(self, triples: List[Dict[str, Any]], resolver_metadata: Dict[str, Any]) -> duckdb.DuckDBPyConnection:
        # 1. Identify "Type-Defining" predicates dynamically
        unique_preds = list(set([str(t.get('pred', '')).lower().strip() for t in triples if t.get('pred')]))
        type_preds = self._identify_type_predicates(unique_preds)
        print(f"Dynamically identified type predicates: {type_preds}")

        entity_types = {} # node_id -> set(types)
        entity_attributes = {} # node_id -> {attr_key: [values]}
        
        print(f"Materializing {len(triples)} triples...")
        for t in triples:
            sub_id = t.get('sub_id')
            if not sub_id: continue
            
            pred = str(t.get('pred', '')).lower().strip()
            obj = str(t.get('obj', ''))
            
            if not pred or not obj: continue
            
            if pred in type_preds:
                if sub_id not in entity_types: entity_types[sub_id] = set()
                entity_types[sub_id].add(obj.lower().strip())
            else:
                if sub_id not in entity_attributes: entity_attributes[sub_id] = {}
                if pred not in entity_attributes[sub_id]: entity_attributes[sub_id][pred] = []
                entity_attributes[sub_id][pred].append(obj)

        print(f"Nodes with types: {len(entity_types)}")
        # Table Discovery: Max-Inclusion Similarity
        tables = self._discover_tables(entity_types)
        print(f"Tables discovered: {list(tables.keys())}")
        
        # 2. Column Consolidation and 3. Value Typing
        for table_name, node_ids in tables.items():
            df = self._build_table_df(table_name, node_ids, entity_attributes, resolver_metadata)
            if not df.empty:
                self.db.register(table_name, df)
                self.db.execute(f"CREATE TABLE {table_name} AS SELECT * FROM {table_name}")
        
        return self.db

    def _identify_type_predicates(self, predicates: List[str]) -> Set[str]:
        import ollama
        import json
        
        prompt = f"""Given these predicates extracted from text, identify which ones are used to define the "TYPE" or "CLASS" of an entity (e.g., 'is_a', 'type', 'category').
Predicates: {predicates}

Return ONLY a JSON list of the type-defining predicates.
Example: ["is_a", "type"]"""

        try:
            response = ollama.generate(
                model="qwen2.5:7b-instruct",
                prompt=prompt,
                format="json"
            )
            result = json.loads(response['response'])
            return set([p.lower().strip() for p in result]) if isinstance(result, list) else {"is_a"}
        except:
            # Fallback to a broader set if LLM fails, but still avoiding strict hardcoding in the primary path
            return {"is_a", "type", "category", "kind_of"}

    def _discover_tables(self, entity_types: Dict[str, Set[str]]) -> Dict[str, List[str]]:
        # Simplified Max-Inclusion: Group by most common type
        type_to_nodes = {}
        for node_id, types in entity_types.items():
            for t in types:
                if t not in type_to_nodes: type_to_nodes[t] = []
                type_to_nodes[t].append(node_id)
        
        # Merge types based on inclusion (simplified)
        sorted_types = sorted(type_to_nodes.keys(), key=lambda k: len(type_to_nodes[k]), reverse=True)
        final_tables = {}
        processed_nodes = set()
        
        for t in sorted_types:
            nodes = [n for n in type_to_nodes[t] if n not in processed_nodes]
            if nodes:
                table_name = re.sub(r'[^A-Z0-9_]', '', t.upper().replace(' ', '_'))
                final_tables[table_name] = nodes
                processed_nodes.update(nodes)
        
        return final_tables

    def _build_table_df(self, table_name: str, node_ids: List[str], entity_attributes: Dict[str, Dict[str, List[Any]]], resolver_metadata: Dict[str, Any]) -> pd.DataFrame:
        all_keys = set()
        for nid in node_ids:
            if nid in entity_attributes:
                all_keys.update(entity_attributes[nid].keys())
        
        if not all_keys:
            # Just ID and Canonical Name
            data = []
            for nid in node_ids:
                data.append({"id": nid, "name": resolver_metadata[nid]["canonical_name"]})
            return pd.DataFrame(data)

        # Column Consolidation: Agglomerative Clustering
        key_list = list(all_keys)
        if len(key_list) < 2:
            # No clustering needed for 0 or 1 keys
            col_mapping = {k: k.replace(' ', '_').lower() for k in key_list}
        else:
            key_embeddings = self.embeddings.embed_documents(key_list)
            
            # Calculate co-occurrence to avoid merging keys that appear together
            co_occurrence = {k1: {k2: False for k2 in key_list} for k1 in key_list}
            for nid in node_ids:
                if nid in entity_attributes:
                    attrs = list(entity_attributes[nid].keys())
                    for i in range(len(attrs)):
                        for j in range(i + 1, len(attrs)):
                            co_occurrence[attrs[i]][attrs[j]] = True
                            co_occurrence[attrs[j]][attrs[i]] = True

            # Custom clustering with anti-collision
            clusters = AgglomerativeClustering(n_clusters=None, distance_threshold=0.4, metric='cosine', linkage='average').fit(key_embeddings)
            
            col_mapping = {} # original_key -> consolidated_col
            cluster_to_keys = {}
            for i, label in enumerate(clusters.labels_):
                if label not in cluster_to_keys: cluster_to_keys[label] = []
                cluster_to_keys[label].append(key_list[i])
            
            for label, keys in cluster_to_keys.items():
                # Handle anti-collision: if keys co-occur, they must stay separate
                current_keys = []
                for k in keys:
                    can_add = True
                    for existing_k in current_keys:
                        if co_occurrence[k][existing_k]:
                            can_add = False
                            break
                    if can_add:
                        for k_to_map in keys: # Map all keys in this cluster to the first one (simplified)
                            col_mapping[k_to_map] = keys[0].replace(' ', '_').lower()
                        break
        
        # Build Data
        rows = []
        for nid in node_ids:
            row = {"id": nid, "name": resolver_metadata[nid]["canonical_name"]}
            if nid in entity_attributes:
                for k, vals in entity_attributes[nid].items():
                    col = col_mapping.get(k, k.replace(' ', '_').lower())
                    val = vals[0] # Take first value
                    row[col] = self._type_value(val)
            rows.append(row)
            
        return pd.DataFrame(rows)

    def _type_value(self, val: Any) -> Any:
        if isinstance(val, (int, float)): return val
        s_val = str(val).strip()
        # Numeric check
        if re.match(r'^-?\d+(\.\d+)?$', s_val):
            return float(s_val)
        # Date check
        try:
            return date_parser.parse(s_val)
        except:
            pass
        return s_val
