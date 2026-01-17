import re
import pandas as pd
import duckdb
import numpy as np
from typing import List, Dict, Any
from sklearn.cluster import AgglomerativeClustering
from langchain_huggingface import HuggingFaceEmbeddings
import networkx as nx

class QREATETopologyMaterializer:
    def __init__(self, embedding_model_name: str = "intfloat/e5-large-v2"):
        self.embeddings = HuggingFaceEmbeddings(model_name=embedding_model_name)
        self.db = duckdb.connect(':memory:')

    def unify_tables(self, graph: nx.MultiDiGraph, node_metadata: Dict[str, Any]) -> Dict[str, List[str]]:
        # Use entity_type directly from graph nodes (set by KG State based on role=TYPE triples)
        node_to_type = {}
        type_to_nodes = {}
        
        for node_id, data in graph.nodes(data=True):
            entity_type = data.get('entity_type')
            if entity_type:
                type_str = str(entity_type).lower().strip()
            else:
                type_str = "entity"
            
            node_to_type[node_id] = type_str
            if type_str not in type_to_nodes:
                type_to_nodes[type_str] = set()
            type_to_nodes[type_str].add(node_id)
        
        unique_types = list(type_to_nodes.keys())
        if not unique_types or (len(unique_types) == 1 and unique_types[0] == "entity"):
            return {"ENTITY": list(graph.nodes())}

        # Cluster semantically similar types together
        type_embeddings = self.embeddings.embed_documents(unique_types)
        
        # Collect attribute keys per type for Jaccard similarity
        type_to_keys = {}
        for t in unique_types:
            keys = set()
            for nid in type_to_nodes.get(t, set()):
                keys.update(graph.nodes[nid].get('attributes', {}).keys())
                keys.update([d.get('predicate') for _, _, d in graph.out_edges(nid, data=True)])
            type_to_keys[t] = keys

        def composite_distance(i, j):
            emb_sim = np.dot(type_embeddings[i], type_embeddings[j]) / (np.linalg.norm(type_embeddings[i]) * np.linalg.norm(type_embeddings[j]) + 1e-9)
            
            keys_i = type_to_keys[unique_types[i]]
            keys_j = type_to_keys[unique_types[j]]
            if not keys_i and not keys_j: jaccard = 1.0
            elif not keys_i or not keys_j: jaccard = 0.0
            else: jaccard = len(keys_i & keys_j) / len(keys_i | keys_j)
            
            sim = 0.5 * emb_sim + 0.5 * jaccard
            return max(0.0, 1.0 - sim)

        n = len(unique_types)
        if n < 2:
            # Only one type, no clustering needed
            tables = {}
            for node_id, ntype in node_to_type.items():
                table_name = re.sub(r'[^A-Z0-9_]', '', ntype.upper().replace(' ', '_'))
                if not table_name or table_name in ['SELECT', 'FROM', 'WHERE', 'JOIN', 'TABLE', 'TRUE', 'FALSE', 'GROUP', 'BY', 'ORDER']:
                    table_name = f"TBL_{table_name}" if table_name else "ENTITY"
                if table_name not in tables: tables[table_name] = []
                tables[table_name].append(node_id)
                graph.nodes[node_id]['canonical_type'] = table_name
            return tables

        dist_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d = composite_distance(i, j)
                dist_matrix[i, j] = dist_matrix[j, i] = d

        clustering = AgglomerativeClustering(n_clusters=None, distance_threshold=0.4, metric='precomputed', linkage='average').fit(dist_matrix)
        
        # Map each type to its cluster's canonical name (most frequent type in cluster)
        cluster_to_types = {}
        for i, label in enumerate(clustering.labels_):
            if label not in cluster_to_types:
                cluster_to_types[label] = []
            cluster_to_types[label].append(unique_types[i])
        
        type_to_canonical = {}
        for label, types in cluster_to_types.items():
            type_counts = {t: len(type_to_nodes.get(t, set())) for t in types}
            canonical = max(types, key=lambda t: type_counts[t])
            for t in types:
                type_to_canonical[t] = canonical

        # Build tables
        tables = {}
        for node_id, ntype in node_to_type.items():
            canonical_type = type_to_canonical.get(ntype, ntype)
            table_name = re.sub(r'[^A-Z0-9_]', '', canonical_type.upper().replace(' ', '_'))
            if not table_name or table_name in ['SELECT', 'FROM', 'WHERE', 'JOIN', 'TABLE', 'TRUE', 'FALSE', 'GROUP', 'BY', 'ORDER']:
                table_name = f"TBL_{table_name}" if table_name else "ENTITY"
            
            if table_name not in tables: tables[table_name] = []
            tables[table_name].append(node_id)
            graph.nodes[node_id]['canonical_type'] = table_name

        return tables

    def stabilize_columns(self, table_name: str, node_ids: List[str], graph: nx.MultiDiGraph) -> Dict[str, str]:
        all_keys = set()
        for nid in node_ids:
            all_keys.update(graph.nodes[nid].get('attributes', {}).keys())
        
        if not all_keys: return {}
        
        key_list = list(all_keys)
        if len(key_list) < 2:
            return {k: k.replace(' ', '_').lower() for k in key_list}

        key_embeddings = self.embeddings.embed_documents(key_list)
        
        co_occurrence_count = {k: {k2: 0 for k2 in key_list} for k in key_list}
        for nid in node_ids:
            attrs = list(graph.nodes[nid].get('attributes', {}).keys())
            for i in range(len(attrs)):
                for j in range(i + 1, len(attrs)):
                    if attrs[i] in co_occurrence_count and attrs[j] in co_occurrence_count[attrs[i]]:
                        co_occurrence_count[attrs[i]][attrs[j]] += 1
                        co_occurrence_count[attrs[j]][attrs[i]] += 1

        threshold = 0.05 * len(node_ids)
        
        def custom_dist(i, j):
            norm_i = np.linalg.norm(key_embeddings[i])
            norm_j = np.linalg.norm(key_embeddings[j])
            if norm_i == 0 or norm_j == 0: return 1.0
            
            emb_sim = np.dot(key_embeddings[i], key_embeddings[j]) / (norm_i * norm_j)
            dist = max(0.0, 1.0 - emb_sim)
            
            if co_occurrence_count[key_list[i]][key_list[j]] > threshold:
                return 2.0 
            return dist

        n = len(key_list)
        dist_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d = custom_dist(i, j)
                dist_matrix[i, j] = dist_matrix[j, i] = d

        clusters = AgglomerativeClustering(n_clusters=None, distance_threshold=0.2, metric='precomputed', linkage='average').fit(dist_matrix)
        
        col_mapping = {}
        cluster_to_keys = {}
        for i, label in enumerate(clusters.labels_):
            if label not in cluster_to_keys: cluster_to_keys[label] = []
            cluster_to_keys[label].append(key_list[i])
        
        for label, keys in cluster_to_keys.items():
            canonical_col = sorted(keys, key=len)[0].replace(' ', '_').lower()
            if canonical_col in ['id', 'name', 'type', 'table', 'select', 'where', 'from']:
                canonical_col = f"attr_{canonical_col}"
            for k in keys:
                col_mapping[k] = canonical_col
        
        return col_mapping

    def discover_foreign_keys(self, tables_dfs: Dict[str, pd.DataFrame], graph: nx.MultiDiGraph, node_metadata: Dict[str, Any], alias_map: Dict[str, str]) -> List[Dict[str, str]]:
        fks = []
        all_canonical_names = set(alias_map.values())
        
        name_to_table = {}
        for nid, data in graph.nodes(data=True):
            name = node_metadata[nid]["canonical_name"]
            etype = data.get('entity_type')
            if name and etype:
                final_t = re.sub(r'[^A-Z0-9_]', '', etype.upper().replace(' ', '_'))
                name_to_table[name] = final_t

        for table_name, df in tables_dfs.items():
            for col in df.columns:
                if col in ['id', 'name']: continue
                values = df[col].dropna().unique()
                if len(values) == 0: continue
                
                overlapping_values = [str(v) for v in values if str(v) in all_canonical_names]
                overlap_ratio = len(overlapping_values) / len(values)
                
                if overlap_ratio > 0.8:
                    target_tables = [name_to_table.get(v) for v in overlapping_values if v in name_to_table]
                    if target_tables:
                        target_table = max(set(target_tables), key=target_tables.count)
                        fks.append({
                            "from_table": table_name, 
                            "from_col": col, 
                            "to_table": target_table
                        })
        return fks

    def rescue_orphans(self, graph: nx.MultiDiGraph):
        """
        Structural Schema Fitting: Re-assign orphans to tables based on attribute fingerprinting.
        """
        # 1. Attribute Fingerprinting
        table_signatures = {} # table_name -> set of keys
        
        # Get all nodes grouped by entity_type
        tables = {}
        for node_id, data in graph.nodes(data=True):
            etype = data.get('entity_type')
            if etype:
                if etype not in tables: tables[etype] = []
                tables[etype].append(node_id)
        
        for etype, node_ids in tables.items():
            key_counts = {}
            for nid in node_ids:
                keys = set(graph.nodes[nid].get('attributes', {}).keys())
                for k in keys:
                    key_counts[k] = key_counts.get(k, 0) + 1
            
            # Signature: keys appearing in > 20% of its member nodes
            threshold = 0.2 * len(node_ids)
            table_signatures[etype] = {k for k, count in key_counts.items() if count > threshold}

        # 2. Orphan Re-assignment
        remaining_orphans = []
        for node_id, data in graph.nodes(data=True):
            etype = data.get('entity_type')
            if not etype or etype == "ENTITY":
                orphan_keys = set(data.get('attributes', {}).keys())
                if not orphan_keys: continue
                
                best_table = None
                max_sim = 0
                
                for table_name, signature in table_signatures.items():
                    if not signature: continue
                    intersection = orphan_keys & signature
                    union = orphan_keys | signature
                    sim = len(intersection) / len(union)
                    
                    if sim > max_sim:
                        max_sim = sim
                        best_table = table_name
                
                # If Similarity > 0.4, re-assign
                if max_sim > 0.4:
                    data['entity_type'] = best_table
                else:
                    remaining_orphans.append(node_id)
        
        # 3. Emergency Table Splitting (Geometric Fallback)
        if remaining_orphans:
            self._emergency_table_splitting(graph, remaining_orphans)

    def _emergency_table_splitting(self, graph: nx.MultiDiGraph, orphan_ids: List[str]):
        """
        Implement Geometric Splitting for nodes whose types were banned or missing.
        """
        if len(orphan_ids) < 2:
            return

        # 1. Fingerprint Generation
        fingerprints = []
        for nid in orphan_ids:
            keys = sorted(list(graph.nodes[nid].get('attributes', {}).keys()))
            fingerprints.append("|".join(keys))
        
        # Vectorize these strings using the embedding model
        fingerprint_embeddings = self.embeddings.embed_documents(fingerprints)
        
        # 2. Geometric Splitting
        clustering = AgglomerativeClustering(n_clusters=None, distance_threshold=0.5, metric='cosine', linkage='average').fit(fingerprint_embeddings)
        
        # 3. Pseudo-Naming
        clusters = {}
        for idx, label in enumerate(clustering.labels_):
            if label not in clusters: clusters[label] = []
            clusters[label].append(orphan_ids[idx])
            
        import ollama
        for label, member_ids in clusters.items():
            # Extract top 3 unique keys in the cluster
            cluster_keys = {}
            for nid in member_ids:
                keys = set(graph.nodes[nid].get('attributes', {}).keys())
                for k in keys: cluster_keys[k] = cluster_keys.get(k, 0) + 1
            
            top_keys = sorted(cluster_keys.items(), key=lambda x: x[1], reverse=True)[:3]
            keys_str = ", ".join([k[0] for k in top_keys])
            
            # LLM Call for naming
            prompt = f"I have a table with these columns: {keys_str}. What is a standard relational name for this table? Return ONLY the name."
            try:
                response = ollama.generate(model="qwen2.5:7b-instruct", prompt=prompt)
                table_name = response['response'].strip().upper().split('\n')[0].replace('.', '')
                if len(table_name) > 30: table_name = table_name[:30] # Limit length
            except:
                table_name = f"UNIDENTIFIED_{label}"
            
            for nid in member_ids:
                graph.nodes[nid]['entity_type'] = table_name

    def materialize(self, graph: nx.MultiDiGraph, node_metadata: Dict[str, Any], alias_map: Dict[str, str]):
        # No more unify_tables() call here, we use entity_type directly after cleanup/rescue
        tables_dfs = {}
        
        # Group nodes by cleaned/rescued entity_type
        discovered_tables = {}
        for node_id, data in graph.nodes(data=True):
            etype = data.get('entity_type') or "ENTITY"
            if etype not in discovered_tables: discovered_tables[etype] = []
            discovered_tables[etype].append(node_id)

        for table_name, node_ids in discovered_tables.items():
            col_mapping = self.stabilize_columns(table_name, node_ids, graph)
            
            # Determine column types for sanitization
            # (In a real system, we'd do a pass over values, here we'll use a simple heuristic)
            numeric_cols = set()
            for nid in node_ids:
                attrs = graph.nodes[nid].get('attributes', {})
                for k, v in attrs.items():
                    col = col_mapping.get(k)
                    if col and self._is_numeric_like(v):
                        numeric_cols.add(col)

            rows = []
            for nid in node_ids:
                row = {"id": nid, "name": node_metadata[nid]["canonical_name"]}
                attrs = graph.nodes[nid].get('attributes', {})
                for k, v in attrs.items():
                    col = col_mapping.get(k, k.replace(' ', '_').lower())
                    # Numerical Value Extraction Sanitization
                    if col in numeric_cols:
                        v = self._sanitize_numeric(v)
                    row[col] = v
                rows.append(row)
            
            df = pd.DataFrame(rows)
            for col in df.columns:
                df[col] = df[col].apply(lambda x: alias_map.get(str(x), x) if isinstance(x, str) else x)
            
            final_table_name = re.sub(r'[^A-Z0-9_]', '', table_name.upper().replace(' ', '_'))
            if final_table_name in ['SELECT', 'FROM', 'WHERE', 'JOIN', 'TABLE', 'TRUE', 'FALSE', 'GROUP', 'BY', 'ORDER']:
                final_table_name = f"TBL_{final_table_name}"

            tables_dfs[final_table_name] = df
            self.db.register(final_table_name, df)
            self.db.execute(f"CREATE TABLE {final_table_name} AS SELECT * FROM {final_table_name}")

        self.fks = self.discover_foreign_keys(tables_dfs, graph, node_metadata, alias_map)
        return self.db

    def _is_numeric_like(self, val: Any) -> bool:
        if isinstance(val, (int, float)): return True
        s = str(val).strip()
        return bool(re.search(r'\d', s))

    def _sanitize_numeric(self, val: Any) -> Any:
        if isinstance(val, (int, float)): return val
        s = str(val).strip()
        # Handle cases where multiple numbers exist by taking only the first match
        match = re.search(r'[-+]?\d*\.?\d+', s)
        if match:
            try:
                num_str = match.group(0)
                if '.' in num_str: return float(num_str)
                return int(num_str)
            except:
                return None
        return None
