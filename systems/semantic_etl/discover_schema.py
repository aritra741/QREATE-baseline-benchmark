import json
import os
import numpy as np
import random
from typing import List, Dict
from ollama import Client
from sklearn.cluster import AgglomerativeClustering
from langchain_huggingface import HuggingFaceEmbeddings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
MODEL_NAME = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"
SAMPLE_SIZE = 1000  # Sample 2000 chunks for schema discovery
MAX_WORKERS = 20    # Number of parallel threads for LLM calls

def get_llm_client():
    return Client(host=OLLAMA_HOST)

def get_embeddings():
    return HuggingFaceEmbeddings(model_name="BAAI/bge-m3")

def process_chunk_observation(chunk: Dict, prompt_template: str) -> List[Dict]:
    """Worker function for parallel observation collection."""
    client = get_llm_client()
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
            # Check for a dictionary wrapping the list (common LLM behavior)
            for key, value in obs.items():
                if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                    observations_to_add = value
                    break
            else:
                # If no list found, it might be a single object
                if "type" in obs:
                    observations_to_add = [obs]
        
        results = []
        for o in observations_to_add:
            if isinstance(o, dict) and "type" in o:
                # Merge attributes and relationships for clustering
                combined_attrs = {}
                if "attributes" in o:
                    if isinstance(o["attributes"], list):
                        for attr in o["attributes"]:
                            combined_attrs[attr] = "example"
                    elif isinstance(o["attributes"], dict):
                        combined_attrs.update(o["attributes"])
                
                if "relationships" in o and isinstance(o["relationships"], list):
                    for rel in o["relationships"]:
                        combined_attrs[rel] = "relationship"
                
                o["attributes"] = combined_attrs
                o["chunk_id"] = chunk["id"]
                results.append(o)
        return results
    except Exception as e:
        return []

def get_observations(chunks: List[Dict]) -> List[Dict]:
    # Sampling for schema discovery
    if len(chunks) > SAMPLE_SIZE:
        print(f"Sampling {SAMPLE_SIZE} chunks out of {len(chunks)} for schema discovery...")
        sampled_chunks = random.sample(chunks, SAMPLE_SIZE)
    else:
        sampled_chunks = chunks

    raw_observations = []
    
    prompt_template = """Analyze the text. Identify distinct Entity Types.
Instruction: Focus on the Primary Subjects of the text (the core domain objects) rather than document metadata (like authors, dates, or blog titles).

For each Entity Type, separate its properties into two lists:

1. Attributes: Intrinsic data that belongs inside this object (e.g., properties, metrics, status).
2. Relationships: References or connections to other independent entities (e.g., 'Entity A interacts with Entity B', 'X is a part of Y').

Output JSON:
[{"type": "EntityName", "attributes": ["list", "of", "strings"], "relationships": ["list", "of", "strings"]}]

TEXT:
{chunk_text}"""

    print(f"Processing {len(sampled_chunks)} chunks with {MAX_WORKERS} threads...")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_chunk_observation, chunk, prompt_template): chunk for chunk in sampled_chunks}
        
        completed = 0
        for future in as_completed(futures):
            results = future.result()
            raw_observations.extend(results)
            completed += 1
            if completed % 100 == 0:
                print(f"  Progress: {completed}/{len(sampled_chunks)} chunks processed.")
            
    return raw_observations

def cluster_observations(raw_observations: List[Dict], embeddings_model):
    if not raw_observations:
        return []

    fingerprints = []
    valid_observations = []
    for obs in raw_observations:
        if "type" not in obs:
            continue
        attrs = sorted(obs.get("attributes", {}).keys())
        fp = f"{obs['type']}: {', '.join(attrs)}"
        fingerprints.append(fp)
        valid_observations.append(obs)
    
    if not fingerprints:
        return []
        
    vectors = embeddings_model.embed_documents(fingerprints)
    vectors = np.array(vectors)
    
    if len(vectors) == 1:
        cluster_ids = np.array([0])
    else:
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
    if not draft_schema:
        return {}

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
            if new_name is None: new_name = old_name
            if new_name not in merged_schema:
                merged_schema[new_name] = {"columns": [], "samples": []}
            
            # Case-insensitive column merging
            existing_cols_lower = {c["name"].lower(): c["name"] for c in merged_schema[new_name]["columns"]}
            for col in info["columns"]:
                if col["name"].lower() not in existing_cols_lower:
                    merged_schema[new_name]["columns"].append(col)
                    existing_cols_lower[col["name"].lower()] = col["name"]
            
            for obs in raw_obs:
                if obs["type"] == old_name:
                    merged_schema[new_name]["samples"].append(obs["attributes"])
        
        draft_schema = merged_schema
    except Exception as e:
        print(f"Warning: Table merge audit failed: {e}")

    sanitized_schema = {}
    for table_name, table_info in draft_schema.items():
        col_names = [c["name"] for c in table_info["columns"]]
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
            seen_cols_lower = set()
            for col in table_info["columns"]:
                new_col_name = mapping.get(col["name"], col["name"])
                if new_col_name is None: new_col_name = col["name"]
                if not isinstance(new_col_name, str): new_col_name = str(new_col_name)
                
                # Case-insensitive check
                if new_col_name and new_col_name.lower() not in seen_cols_lower:
                    new_columns.append({
                        "name": new_col_name,
                        "is_foreign_key": False,
                        "references_table": None
                    })
                    seen_cols_lower.add(new_col_name.lower())
            
            sanitized_schema[table_name] = {"columns": new_columns}
        except Exception as e:
            sanitized_schema[table_name] = {"columns": table_info["columns"]}

    return sanitized_schema

def compute_semantic_overlap(cols1: List[str], cols2: List[str], embeddings_model) -> float:
    # Filter out None values and ensure they are strings
    cols1 = [str(c) for c in cols1 if c is not None]
    cols2 = [str(c) for c in cols2 if c is not None]
    
    if not cols1 or not cols2: return 0.0
    vecs1 = embeddings_model.embed_documents(cols1)
    vecs2 = embeddings_model.embed_documents(cols2)
    matches = 0
    for v1 in vecs1:
        for v2 in vecs2:
            similarity = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
            if similarity > 0.85:
                matches += 1
                break
    return matches / len(set(cols1 + cols2))

def crunch_schema(schema: Dict, embeddings_model) -> Dict:
    table_names = list(schema.keys())
    merged_tables = set()
    final_schema = {}
    for i in range(len(table_names)):
        t1 = table_names[i]
        if t1 in merged_tables: continue
        for j in range(i + 1, len(table_names)):
            t2 = table_names[j]
            if t2 in merged_tables: continue
            cols1 = [c["name"] for c in schema[t1]["columns"]]
            cols2 = [c["name"] for c in schema[t2]["columns"]]
            overlap = compute_semantic_overlap(cols1, cols2, embeddings_model)
            if overlap > 0.5:
                merged_tables.add(t2)
                existing_cols_lower = {c["name"].lower() for c in schema[t1]["columns"]}
                for col in schema[t2]["columns"]:
                    if col["name"].lower() not in existing_cols_lower:
                        schema[t1]["columns"].append(col)
                        existing_cols_lower.add(col["name"].lower())
    for name, info in schema.items():
        if name not in merged_tables:
            final_schema[name] = info
    return final_schema

def topology_weaver(schema: Dict, client: Client) -> Dict:
    """Phase 2.6: The Topology Weaver - Identifies Foreign Key relationships."""
    print("Phase 2.6: The Topology Weaver (Relational Mapping)...")
    all_table_names = list(schema.keys())
    updated_schema = {}
    
    for table_name, table_info in schema.items():
        weaver_prompt = f"""Role: Database Architect.
Context: The database contains these tables: {json.dumps(all_table_names)}.
Table Definition: {table_info.get('definition', '')}
Task: We are defining the schema for '{table_name}'.

Instruction:
Analyze the relationships inherent to a '{table_name}'.
Does a '{table_name}' logically require a reference (Foreign Key) to any of the other tables in the list?
Criteria: Only add a link if '{table_name}' is subordinate to, owned by, or structurally interacts with the other table.

Output JSON:
A list of new columns to add to '{table_name}'.
[
  {{"column_name": "target_table_name_ref", "target_table": "TargetTableName", "description": "short explanation"}}
]
If none, output empty list []."""

        try:
            response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': weaver_prompt}], format='json')
            content = json.loads(response['message']['content'])
            
            # Flexible parsing
            new_links = []
            if isinstance(content, list):
                new_links = content
            elif isinstance(content, dict):
                for v in content.values():
                    if isinstance(v, list):
                        new_links = v
                        break
            
            for link in new_links:
                if isinstance(link, list) and len(link) > 0: link = link[0] # Handle nested lists
                if not isinstance(link, dict): continue
                
                col_name = link.get("column_name")
                target_table = link.get("target_table")
                if col_name and target_table and target_table in all_table_names:
                    print(f"  Added Link: {table_name}.{col_name} -> {target_table}")
                    table_info["columns"].append({
                        "name": col_name,
                        "is_foreign_key": True,
                        "references_table": target_table,
                        "description": link.get("description", "")
                    })
        except Exception as e:
            print(f"  Warning: Topology Weaver failed for {table_name}: {e}")
            
        updated_schema[table_name] = table_info
    return updated_schema

def generate_definitions(schema: Dict, client: Client) -> Dict:
    """Phase 2.5: Generate physical definitions and identify Primary Key."""
    print("Phase 2.5: Generating schema definitions...")
    updated_schema = {}
    for table_name, table_info in schema.items():
        cols = [c["name"] for c in table_info["columns"]]
        
        # 1. Generate SIMPLE Definition
        def_prompt = f"""Role: Data Architect.
Task: Write a physical definition for the database table: **{table_name}**.
Context: It contains columns: {json.dumps(cols)}.
Constraint: Your definition MUST BE A SINGLE CONCISE SENTENCE (under 15 words).
Example: 'A Device is a physical hardware unit or piece of equipment.'
Output JSON: {{"definition": "string"}}"""
        
        try:
            response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': def_prompt}], format='json')
            content = json.loads(response['message']['content'])
            table_info["definition"] = content.get("definition", f"Data table for {table_name}")
        except:
            table_info["definition"] = f"Data table for {table_name}"

        # 2. Identify Primary Key (No Heuristics)
        pk_prompt = f"""Identify which of these attributes represents the unique Identifier or Name of the entity in the table '{table_name}'. 
Attributes: {json.dumps(cols)}
Constraint: Return strictly the column name that acts as the primary subject.
Output JSON: {{"primary_key": "column_name"}}"""

        try:
            response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': pk_prompt}], format='json')
            content = json.loads(response['message']['content'])
            pk = content.get("primary_key")
            if pk in cols:
                table_info["_meta"] = {"primary_key": pk}
            else:
                # Fallback to first column if LLM fails or picks invalid PK
                table_info["_meta"] = {"primary_key": cols[0] if cols else None}
        except:
            table_info["_meta"] = {"primary_key": cols[0] if cols else None}
            
        updated_schema[table_name] = table_info
    return updated_schema

def discover_schema(chunks_file: str):
    if not os.path.exists(chunks_file):
        print("chunks.json missing")
        return

    with open(chunks_file, 'r') as f:
        chunks = json.load(f)
    
    client = get_llm_client()
    embeddings_model = get_embeddings()
    
    print("Collecting observations from chunks...")
    raw_observations = get_observations(chunks)
    
    print("Clustering observations...")
    valid_observations = cluster_observations(raw_observations, embeddings_model)
    
    cluster_counts = Counter(obs["cluster_id"] for obs in valid_observations)
    surviving_clusters = {}
    for cluster_id, count in cluster_counts.items():
        if count >= 3:
            types_in_cluster = [obs["type"] for obs in valid_observations if obs["cluster_id"] == cluster_id]
            canonical_name = Counter(types_in_cluster).most_common(1)[0][0]
            surviving_clusters[cluster_id] = canonical_name
    
    draft_schema = {}
    for cluster_id, table_name in surviving_clusters.items():
        all_attrs = []
        for obs in valid_observations:
            if obs["cluster_id"] == cluster_id:
                all_attrs.extend(obs["attributes"].keys())
        
        if not all_attrs: continue
        
        attr_vectors = embeddings_model.embed_documents(all_attrs)
        if len(attr_vectors) == 1:
            attr_labels = np.array([0])
        else:
            attr_clustering = AgglomerativeClustering(n_clusters=None, distance_threshold=0.2, metric='cosine', linkage='average')
            attr_labels = attr_clustering.fit_predict(np.array(attr_vectors))
        
        canonical_columns = []
        for attr_label in set(attr_labels):
            attrs_in_group = [all_attrs[i] for i, label in enumerate(attr_labels) if label == attr_label]
            canonical_col = Counter(attrs_in_group).most_common(1)[0][0]
            canonical_columns.append(canonical_col)
            
        draft_schema[table_name] = {
            "columns": [{"name": col, "is_foreign_key": False, "references_table": None} for col in canonical_columns]
        }
    
    print("Auditing and Sanitizing Schema...")
    audited_schema = audit_schema(draft_schema, valid_observations, client)
    
    print("Crunching Schema...")
    final_schema = crunch_schema(audited_schema, embeddings_model)
    
    # Phase 2.4: Table Renaming Audit
    print("Phase 2.4: Table Renaming Audit...")
    renamed_schema = {}
    for old_name, info in final_schema.items():
        cols = [c["name"] for c in info["columns"]]
        rename_prompt = f"""Role: Data Architect.
Review the table name '{old_name}' and its columns: {json.dumps(cols)}.
Task: Determine if the name can be more descriptive of its Role within its specific domain.
Constraint: Avoid overly generic names (like 'Entity' or 'Object') if the columns suggest a specific functional role.
Output JSON: {{"canonical_name": "string"}}"""
        try:
            response = client.chat(model=MODEL_NAME, messages=[{'role': 'user', 'content': rename_prompt}], format='json')
            new_name = json.loads(response['message']['content']).get("canonical_name", old_name)
            renamed_schema[new_name] = info
        except:
            renamed_schema[old_name] = info
    final_schema = renamed_schema

    # Phase 2.5: Definitions
    final_schema = generate_definitions(final_schema, client)

    # Phase 2.6: Topology Weaver (Needs definitions to work well)
    final_schema = topology_weaver(final_schema, client)
    
    # Final cleanup: Remove any None keys that might have slipped through
    final_schema = {k: v for k, v in final_schema.items() if k is not None}
    
    with open("schema.json", "w") as f:
        json.dump(final_schema, f, indent=2)
    
    print(f"Schema discovered with definitions and links. Tables: {', '.join(str(k) for k in final_schema.keys())}")

if __name__ == "__main__":
    discover_schema("chunks.json")
