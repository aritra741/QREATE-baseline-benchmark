import sqlglot
import pandas as pd
import duckdb
import re
import numpy as np
from typing import List, Dict, Any
from langchain_huggingface import HuggingFaceEmbeddings

class QREATESQLShim:
    def __init__(self, db: duckdb.DuckDBPyConnection, resolver, embedding_model_name: str = "intfloat/e5-large-v2"):
        self.db = db
        self.resolver = resolver
        self.embeddings = HuggingFaceEmbeddings(model_name=embedding_model_name)

    def fuzzy_table_mapping(self, sql_query: str) -> str:
        try:
            expression = sqlglot.parse_one(sql_query)
        except:
            return sql_query

        tables_in_query = [table.name.upper() for table in expression.find_all(sqlglot.exp.Table)]
        materialized_tables = [row[0] for row in self.db.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()]
        
        if not materialized_tables:
            return sql_query

        mat_table_embeddings = self.embeddings.embed_documents(materialized_tables)
        new_sql = sql_query
        
        for q_table in tables_in_query:
            q_embed = self.embeddings.embed_query(q_table)
            sims = np.dot(mat_table_embeddings, q_embed) / (np.linalg.norm(mat_table_embeddings, axis=1) * np.linalg.norm(q_embed))
            best_idx = np.argmax(sims)
            matched_table = materialized_tables[best_idx]
            new_sql = re.sub(rf'\b{q_table}\b', matched_table, new_sql, flags=re.IGNORECASE)
            
        return new_sql

    def literal_grounding(self, sql_query: str) -> str:
        try:
            expression = sqlglot.parse_one(sql_query)
        except:
            return sql_query

        new_sql = sql_query
        for literal in expression.find_all(sqlglot.exp.Literal):
            if literal.is_string:
                val = literal.this
                # Check Alias Map
                if val in self.resolver.alias_map:
                    canonical = self.resolver.alias_map[val]
                    # Regex Rule: replace only quoted strings
                    new_sql = re.sub(rf"'{re.escape(val)}'", f"'{canonical}'", new_sql, flags=re.IGNORECASE)
        
        return new_sql

    def execute_query(self, sql_query: str) -> pd.DataFrame:
        processed_sql = self.fuzzy_table_mapping(sql_query)
        processed_sql = self.literal_grounding(processed_sql)
        
        try:
            return self.db.execute(processed_sql).df()
        except Exception as e:
            print(f"Query execution failed: {e}")
            return pd.DataFrame()
