import sqlglot
import pandas as pd
import duckdb
from typing import List, Dict, Any
from langchain_huggingface import HuggingFaceEmbeddings
import numpy as np

class QREATESQLShim:
    def __init__(self, db: duckdb.DuckDBPyConnection, resolver, embedding_model_name: str = "intfloat/e5-large-v2"):
        self.db = db
        self.resolver = resolver
        self.embeddings = HuggingFaceEmbeddings(model_name=embedding_model_name)

    def execute_query(self, sql_query: str) -> pd.DataFrame:
        # 1. Parsing with sqlglot
        try:
            expression = sqlglot.parse_one(sql_query)
        except:
            return pd.DataFrame()

        # 2. Table Mapping
        # Find table names in query
        tables_in_query = [table.name.upper() for table in expression.find_all(sqlglot.exp.Table)]
        materialized_tables = [row[0] for row in self.db.execute("SELECT table_name FROM information_schema.tables").fetchall()]
        
        table_map = {}
        if materialized_tables:
            mat_table_embeddings = self.embeddings.embed_documents(materialized_tables)
            for query_table in tables_in_query:
                q_embed = self.embeddings.embed_query(query_table)
                # Cosine similarity
                sims = np.dot(mat_table_embeddings, q_embed) / (np.linalg.norm(mat_table_embeddings, axis=1) * np.linalg.norm(q_embed))
                best_idx = np.argmax(sims)
                table_map[query_table] = materialized_tables[best_idx]

        # 3. Literal Grounding
        # Find literals in WHERE clause
        new_sql = sql_query
        for literal in expression.find_all(sqlglot.exp.Literal):
            if literal.is_string:
                val = literal.this
                # Look up in exact_match_cache
                s_norm = val.lower().strip()
                if s_norm in self.resolver.exact_match_cache:
                    node_id = self.resolver.exact_match_cache[s_norm]
                    canonical_name = self.resolver.node_metadata[node_id]["canonical_name"]
                    new_sql = new_sql.replace(f"'{val}'", f"'{canonical_name}'")

        # Replace table names
        for q_table, m_table in table_map.items():
            # Use regex to replace table names safely (case insensitive)
            import re
            new_sql = re.sub(rf'\b{q_table}\b', m_table, new_sql, flags=re.IGNORECASE)

        # 4. Execution
        try:
            return self.db.execute(new_sql).df()
        except Exception as e:
            print(f"Query execution failed: {e}")
            return pd.DataFrame()
