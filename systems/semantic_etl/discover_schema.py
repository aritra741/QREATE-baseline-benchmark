import json
import os
import numpy as np
from typing import List, Dict
from ollama import Client
from sklearn.cluster import AgglomerativeClustering
from langchain_huggingface import HuggingFaceEmbeddings
from collections import Counter

# Configuration
MODEL_NAME = "qwen2.5:7b-instruct" # Adjusted to match user request (they said Qwen2.5-7b-instruct)
OLLAMA_HOST = "http://localhost:11434"

def get_llm_client():
    return Client(host=OLLAMA_HOST)

def get_embeddings():
    return HuggingFaceEmbeddings(model_name="BAAI/bge-m3")

def get_observations(chunks: List[Dict]) -> List[Dict]:
    client = get_llm_client()
    raw_observations = []
    
    prompt_template = """Analyze the provided text to discover its underlying relational structure. Identify real-world Entity Types and their Attributes.

TEXT:
{chunk_text}

INSTRUCTIONS:
1. Identify Entity Types (things that store data) and their Attributes.
2. For each Attribute, provide an EXAMPLE VALUE found in the text.
3. Attributes must be GENERIC categories.
4. Output strictly a JSON list of objects.

JSON FORMAT:
[
  {{
    "type": "EntityTypeName",
    "attributes": {{
      "attribute_name": "example_value",
      "attribute_name_2": "example_value"
    }}
  }}
]"""

    for chunk in chunks:
        text = chunk["text"]
        try:
            prompt = prompt_template.replace("{chunk_text}", text)
            response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': prompt}], format='json')
            content = response['message']['content']
            obs = json.loads(content)
            
            observations_to_add = []
            if isinstance(obs, list):
                observations_to_add = obs
            elif isinstance(obs, dict):
                if "type" in obs and "attributes" in obs:
                    observations_to_add = [obs]
                else:
                    for key, value in obs.items():
                        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict) and "type" in value[0]:
                            observations_to_add = value
                            break
            
            for o in observations_to_add:
                if isinstance(o, dict) and "type" in o and "attributes" in o:
                    o["chunk_id"] = chunk["id"]
                    raw_observations.append(o)
        except Exception as e:
            pass
            
    return raw_observations

def cluster_observations(raw_observations: List[Dict], embeddings_model):
    if not raw_observations:
        return []

    fingerprints = []
    valid_observations = []
    for obs in raw_observations:
        if "type" not in obs:
            continue
        attrs = sorted(obs.get("attributes", []))
        fp = f"{obs['type']}: {', '.join(attrs)}"
        fingerprints.append(fp)
        valid_observations.append(obs)
    
    if not fingerprints:
        return []
        
    vectors = embeddings_model.embed_documents(fingerprints)
    vectors = np.array(vectors)
    
    # Agglomerative Clustering
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=0.2,
        metric='cosine',
        linkage='average'
    )
    cluster_ids = clustering.fit_predict(vectors)
    
    for i, obs in enumerate(valid_observations):
        obs["cluster_id"] = int(cluster_ids[i])
        
    return valid_observations

def audit_schema(draft_schema: Dict, raw_obs: List[Dict], client: Client) -> Dict:
    """Uses LLM to merge synonymous tables and sanitize column names using data context."""
    if not draft_schema:
        return {}

    # Step 1: Merge Synonymous Tables
    table_names = list(draft_schema.keys())
    merge_prompt = f"""You are a database normalization expert. Review these raw discovered table names:
{json.dumps(table_names)}

Identify tables that refer to identical or near-identical concepts and map them to a single CANONICAL name.
Output strictly a JSON object mapping EVERY old table name to its new CANONICAL name.
Example Format: {{"RawA": "Canonical1", "RawB": "Canonical1"}}"""

    try:
        response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': merge_prompt}], format='json')
        mapping = json.loads(response['message']['content'])
        
        merged_schema = {}
        for old_name, info in draft_schema.items():
            new_name = mapping.get(old_name, old_name)
            if new_name not in merged_schema:
                merged_schema[new_name] = {"columns": [], "samples": []}
            
            existing_cols = {c["name"] for c in merged_schema[new_name]["columns"]}
            for col in info["columns"]:
                if col["name"] not in existing_cols:
                    merged_schema[new_name]["columns"].append(col)
                    existing_cols.add(col["name"])
            
            # Aggregate sample values for the next step
            for obs in raw_obs:
                if obs["type"] == old_name:
                    merged_schema[new_name]["samples"].append(obs["attributes"])
        
        draft_schema = merged_schema
    except Exception as e:
        print(f"Warning: Table merge audit failed: {e}")

    # Step 2: Sanitize Column Names using Data Context
    sanitized_schema = {}
    for table_name, table_info in draft_schema.items():
        col_names = [c["name"] for c in table_info["columns"]]
        # Show top 5 sample extractions to help model distinguish values from columns
        samples = table_info.get("samples", [])[:5]
        
        sanitize_prompt = f"""Review the columns for table '{table_name}':
Columns: {json.dumps(col_names)}
Sample Data: {json.dumps(samples)}

Identify columns that act as specific data values rather than generic categories. Rename them.
Output strictly a JSON object mapping OLD_NAME to NEW_NAME."""

        try:
            response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': sanitize_prompt}], format='json')
            mapping = json.loads(response['message']['content'])
            
            new_columns = []
            seen_cols = set()
            for col in table_info["columns"]:
                new_col_name = mapping.get(col["name"], col["name"])
                if new_col_name not in seen_cols:
                    new_columns.append({
                        "name": new_col_name,
                        "is_foreign_key": col["is_foreign_key"],
                        "references_table": col["references_table"]
                    })
                    seen_cols.add(new_col_name)
            
            sanitized_schema[table_name] = {"columns": new_columns}
        except Exception as e:
            sanitized_schema[table_name] = {"columns": table_info["columns"]}

    return sanitized_schema

def compute_semantic_overlap(cols1: List[str], cols2: List[str], embeddings_model) -> float:
    if not cols1 or not cols2:
        return 0.0
    
    vecs1 = embeddings_model.embed_documents(cols1)
    vecs2 = embeddings_model.embed_documents(cols2)
    
    matches = 0
    for v1 in vecs1:
        for v2 in vecs2:
            similarity = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
            if similarity > 0.85: # Semantic match threshold
                matches += 1
                break
    
    # Jaccard-like semantic similarity
    return matches / len(set(cols1 + cols2))

def crunch_schema(schema: Dict, embeddings_model) -> Dict:
    """Phase 2.6: The Cruncher - Force merge tables with high semantic column overlap."""
    table_names = list(schema.keys())
    merged_tables = set()
    final_schema = {}
    
    # Mapping to track where each table ended up
    remap = {name: name for name in table_names}
    
    for i in range(len(table_names)):
        t1 = table_names[i]
        if t1 in merged_tables: continue
        
        for j in range(i + 1, len(table_names)):
            t2 = table_names[j]
            if t2 in merged_tables: continue
            
            cols1 = [c["name"] for c in schema[t1]["columns"]]
            cols2 = [c["name"] for c in schema[t2]["columns"]]
            
            overlap = compute_semantic_overlap(cols1, cols2, embeddings_model)
            if overlap > 0.5: # Overlap threshold
                print(f"Cruncher: Force-merging {t2} into {t1} (Overlap: {overlap:.2f})")
                merged_tables.add(t2)
                remap[t2] = t1
                
                # Merge columns
                existing_cols = {c["name"] for c in schema[t1]["columns"]}
                for col in schema[t2]["columns"]:
                    if col["name"] not in existing_cols:
                        schema[t1]["columns"].append(col)
                        existing_cols.add(col["name"])
    
    for name, info in schema.items():
        if name not in merged_tables:
            final_schema[name] = info
            
    return final_schema

def discover_schema(chunks_file: str):
    with open(chunks_file, 'r') as f:
        chunks = json.load(f)
    
    client = get_llm_client()
    embeddings_model = get_embeddings()
    
    print("Collecting observations from chunks...")
    raw_observations = get_observations(chunks)
    
    print("Clustering observations...")
    raw_observations = cluster_observations(raw_observations, embeddings_model)
    
    # Step 2.3: Noise Filtering & Naming
    cluster_counts = Counter(obs["cluster_id"] for obs in raw_observations)
    total_chunks = len(chunks)
    
    surviving_clusters = {}
    for cluster_id, count in cluster_counts.items():
        if count >= max(3, 0.01 * total_chunks):
            # Find canonical name
            types_in_cluster = [obs["type"] for obs in raw_observations if obs["cluster_id"] == cluster_id]
            canonical_name = Counter(types_in_cluster).most_common(1)[0][0]
            surviving_clusters[cluster_id] = canonical_name
    
    # Step 2.4: Attribute Normalization
    draft_schema = {}
    for cluster_id, table_name in surviving_clusters.items():
        all_attrs = []
        for obs in raw_observations:
            if obs["cluster_id"] == cluster_id:
                all_attrs.extend(obs.get("attributes", []))
        
        if not all_attrs:
            continue
            
        attr_vectors = embeddings_model.embed_documents(all_attrs)
        attr_clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=0.2,
            metric='cosine',
            linkage='average'
        )
        attr_labels = attr_clustering.fit_predict(np.array(attr_vectors))
        
        canonical_columns = []
        for attr_label in set(attr_labels):
            attrs_in_group = [all_attrs[i] for i, label in enumerate(attr_labels) if label == attr_label]
            canonical_col = Counter(attrs_in_group).most_common(1)[0][0]
            canonical_columns.append(canonical_col)
            
        draft_schema[table_name] = {
            "columns": [{"name": col, "is_foreign_key": False, "references_table": None} for col in canonical_columns]
        }
    
    print("Auditing and Sanitizing Schema (V4 Data-Aware Loop)...")
    audited_schema = audit_schema(draft_schema, raw_observations, client)
    
    print("Crunching Schema (V3 Force-Normalization)...")
    final_schema = crunch_schema(audited_schema, embeddings_model)
    
    # Step 2.5: Linkage Detection
    table_names = list(final_schema.keys())
    for table_name, table_info in final_schema.items():
        for col in table_info["columns"]:
            col_vec = embeddings_model.embed_query(col["name"])
            for other_table in table_names:
                table_vec = embeddings_model.embed_query(other_table)
                similarity = np.dot(col_vec, table_vec) / (np.linalg.norm(col_vec) * np.linalg.norm(table_vec))
                
                if similarity > 0.85:
                    col["is_foreign_key"] = True
                    col["references_table"] = other_table
                    break
                    
    with open("schema.json", "w") as f:
        json.dump(final_schema, f, indent=2)
    
    print(f"Schema discovered and saved to schema.json. Tables: {', '.join(table_names)}")

if __name__ == "__main__":
    discover_schema("chunks.json")
