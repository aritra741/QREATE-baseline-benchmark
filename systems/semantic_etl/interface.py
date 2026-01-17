import json
import sqlite3
import os
import numpy as np
from typing import List, Dict
from ollama import Client
from langchain_huggingface import HuggingFaceEmbeddings

# Configuration
MODEL_NAME = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"
DB_PATH = "uda.db"

def get_llm_client():
    return Client(host=OLLAMA_HOST)

def get_embeddings():
    return HuggingFaceEmbeddings(model_name="BAAI/bge-m3")

def build_database():
    if not os.path.exists("schema.json") or not os.path.exists("final_data.json"):
        print("Required files missing (schema.json or final_data.json)")
        return

    # V3 HARD RESET: Delete existing database to remove ghost tables from previous runs
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Clean slate: removed existing {DB_PATH}")

    with open("schema.json", 'r') as f:
        schema = json.load(f)
    
    with open("final_data.json", 'r') as f:
        final_data = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Step 5.1: Create tables and insert data
    for table_name, table_info in schema.items():
        columns = table_info["columns"]
        col_defs = []
        for col in columns:
            col_name = f'"{col["name"]}"'
            # Simple type detection: check first row of final_data if available
            col_type = "TEXT"
            if table_name in final_data and final_data[table_name]:
                sample_val = final_data[table_name][0].get(col["name"])
                if isinstance(sample_val, int):
                    col_type = "INTEGER"
                elif isinstance(sample_val, float):
                    col_type = "REAL"
            
            col_defs.append(f"{col_name} {col_type}")
        
        create_sql = f"CREATE TABLE IF NOT EXISTS \"{table_name}\" ({', '.join(col_defs)});"
        cursor.execute(f"DROP TABLE IF EXISTS \"{table_name}\"")
        cursor.execute(create_sql)
        
        # Insert data
        if table_name in final_data:
            for row in final_data[table_name]:
                col_names = [f'"{c["name"]}"' for c in columns]
                placeholders = ["?" for _ in columns]
                insert_sql = f"INSERT INTO \"{table_name}\" ({', '.join(col_names)}) VALUES ({', '.join(placeholders)})"
                
                # Ensure all columns exist in the row dict, even if null
                values = [row.get(c["name"]) for c in columns]
                cursor.execute(insert_sql, values)
    
    conn.commit()
    conn.close()
    print(f"Database {DB_PATH} built successfully.")

def answer_query(user_question: str):
    if not os.path.exists("schema.json"):
        print("schema.json missing")
        return

    with open("schema.json", 'r') as f:
        schema = json.load(f)
    
    embeddings_model = get_embeddings()
    q_vec = embeddings_model.embed_query(user_question)
    
    # Vector Mapping: Identify relevant tables
    relevant_tables = []
    for table_name in schema.keys():
        t_vec = embeddings_model.embed_query(table_name)
        similarity = np.dot(q_vec, t_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(t_vec))
        if similarity > 0.3: # Low threshold to be safe
            relevant_tables.append(table_name)
    
    # If no tables found via similarity, include all
    if not relevant_tables:
        relevant_tables = list(schema.keys())
        
    filtered_schema = {t: schema[t] for t in relevant_tables}
    schema_str = json.dumps(filtered_schema, indent=2)

    client = get_llm_client()
    prompt = f"""You are a SQL expert. Write a SQLite query to answer the user's question.

DATABASE SCHEMA:
{schema_str}

USER QUESTION:
{user_question}

INSTRUCTIONS:
1. Use only the tables provided.
2. Output strictly the SQL query text. No markdown formatting.
3. Ensure you handle JOINs using the foreign key columns defined in the schema."""

    try:
        response = client.chat(model=MODEL_NAME, messages=[
            {'role': 'user', 'content': prompt}
        ])
        sql_query = response['message']['content'].strip()
        # Remove markdown code blocks if any
        if "```sql" in sql_query:
            sql_query = sql_query.split("```sql")[1].split("```")[0].strip()
        elif "```" in sql_query:
            sql_query = sql_query.split("```")[1].split("```")[0].strip()
            
        print(f"Generated SQL: {sql_query}")
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row # Enable name-based access
        cursor = conn.cursor()
        cursor.execute(sql_query)
        
        # V3 Better Printing: Show Headers
        rows = cursor.fetchall()
        if rows:
            headers = rows[0].keys()
            print("\n" + " | ".join(headers))
            print("-" * (len(" | ".join(headers)) + 2))
            for row in rows:
                print(" | ".join(str(v) if v is not None else "NULL" for v in row))
        else:
            print("\nNo results found.")
        conn.close()
    except Exception as e:
        print(f"Error answering query: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python interface.py build         # To build the DB")
        print("  python interface.py query <text>  # To answer a question")
    elif sys.argv[1] == "build":
        build_database()
    elif sys.argv[1] == "query":
        answer_query(" ".join(sys.argv[2:]))
