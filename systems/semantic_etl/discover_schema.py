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
    
    prompt_template = """Analyze the provided text to discover its underlying relational structure. Identify real-world Entity Types and the generic Attribute Names that define their properties.

TEXT:
{chunk_text}

INSTRUCTIONS:
1. Focus on "Noun-Property" relationships. What entities are being described, and what specific categories of information are provided about them?
2. Attributes must be GENERIC CATEGORY NAMES (e.g., "identifier", "cost", "status", "category").
3. NEVER use specific values from the text as attribute names.
4. Output strictly a JSON list of objects.
5. If no entities are found, output an empty list [].

DOMAIN-AGNOSTIC EXAMPLES:
- For "The flight BA202 to London is delayed, costing $400", return: {"type": "Transport", "attributes": ["id", "destination", "status", "price"]}
- For "Employee 101 in Sales earned a bonus of 5000", return: {"type": "Staff", "attributes": ["id", "department", "compensation"]}
- For "The 5-star Hotel Ritz has 200 rooms", return: {"type": "Accommodation", "attributes": ["rating", "name", "capacity"]}

JSON FORMAT:
[
  {
    "type": "EntityTypeName",
    "attributes": ["attribute_name_1", "attribute_name_2"]
  }
]"""

    for chunk in chunks:
        text = chunk["text"]
        try:
            # Avoid .format() issues with braces in the input text
            prompt = prompt_template.replace("{chunk_text}", text)
            
            response = client.chat(model=MODEL_NAME, messages=[
                {'role': 'user', 'content': prompt}
            ], format='json')
            
            content = response['message']['content']
            obs = json.loads(content)
            
            # Robust parsing of the LLM response
            observations_to_add = []
            if isinstance(obs, list):
                observations_to_add = obs
            elif isinstance(obs, dict):
                # Check if it's a single observation or a wrapper
                if "type" in obs and "attributes" in obs:
                    observations_to_add = [obs]
                else:
                    # Look for any list in the dict that might contain observations
                    for key, value in obs.items():
                        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict) and "type" in value[0]:
                            observations_to_add = value
                            break
            
            for o in observations_to_add:
                if isinstance(o, dict) and "type" in o and "attributes" in o:
                    # Ensure attributes is a list
                    if isinstance(o["attributes"], str):
                        o["attributes"] = [o["attributes"]]
                    
                    o["chunk_id"] = chunk["id"]
                    raw_observations.append(o)
        except Exception as e:
            # More descriptive error logging
            print(f"Error processing chunk {chunk['id']}: {type(e).__name__}: {e}")
            
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

def audit_schema(draft_schema: Dict, client: Client) -> Dict:
    """Uses LLM to merge synonymous tables and sanitize column names."""
    if not draft_schema:
        return {}

    # Step 1: Merge Synonymous Tables
    table_names = list(draft_schema.keys())
    merge_prompt = f"""Here is a list of discovered database table names:
{json.dumps(table_names)}

Identify groups of tables that are synonymous or should be merged into a single canonical table. 
Focus on common-sense relationships (e.g., 'Drugs' and 'Medication' should be 'Medication').

Output strictly a JSON list of lists, where each sub-list contains table names to merge.
If no tables should be merged, output [].

Example: [["MedicalCondition", "HealthCondition"], ["Drugs", "Medication"]]"""

    try:
        response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': merge_prompt}], format='json')
        merges = json.loads(response['message']['content'])
        
        # Apply merges
        canonical_map = {} # old_name -> new_name
        for group in merges:
            if not group: continue
            # Use the most frequent or first name as canonical
            canonical_name = group[0]
            for table in group:
                canonical_map[table] = canonical_name
        
        merged_schema = {}
        for table, info in draft_schema.items():
            new_name = canonical_map.get(table, table)
            if new_name not in merged_schema:
                merged_schema[new_name] = {"columns": []}
            
            # Combine columns, avoid duplicates
            existing_cols = {c["name"] for c in merged_schema[new_name]["columns"]}
            for col in info["columns"]:
                if col["name"] not in existing_cols:
                    merged_schema[new_name]["columns"].append(col)
                    existing_cols.add(col["name"])
        
        draft_schema = merged_schema
    except Exception as e:
        print(f"Warning: Table merge audit failed: {e}")

    # Step 2: Sanitize Column Names (Values as Columns)
    sanitized_schema = {}
    for table_name, table_info in draft_schema.items():
        col_names = [c["name"] for c in table_info["columns"]]
        sanitize_prompt = f"""Review the columns for the table '{table_name}':
{json.dumps(col_names)}

Identify any 'Column Names' that act closer to specific data values or entity instances (e.g., 'iPhone 15', 'Aspirin') rather than categories (e.g., 'model_name', 'drug_type').
Rename them to their appropriate generic category name.

Output strictly a JSON object mapping OLD_NAME to NEW_NAME. If no change is needed, map it to itself.
Example: {{"iPhone 15": "model_name", "Q3": "quarter", "price": "price"}}"""

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
            print(f"Warning: Column sanitization failed for table {table_name}: {e}")
            sanitized_schema[table_name] = table_info

    return sanitized_schema

def discover_schema(chunks_file: str):
    with open(chunks_file, 'r') as f:
        chunks = json.load(f)
    
    client = get_llm_client()
    
    print("Collecting observations from chunks...")
    raw_observations = get_observations(chunks)
    
    print("Clustering observations...")
    embeddings_model = get_embeddings()
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
    
    print("Auditing and Sanitizing Schema (V2 Corrective Loop)...")
    final_schema = audit_schema(draft_schema, client)
    
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
