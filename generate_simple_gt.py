#!/usr/bin/env python3
"""
Generate ground truth CSV files for simple queries by executing SQL on the data CSVs.
"""

import pandas as pd
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent

# Data paths
DATA_PATHS = {
    "Med": {
        "disease": PROJECT_ROOT / "Data" / "Med" / "disease.csv",
    },
    "Player": {
        "player": PROJECT_ROOT / "Data" / "Player" / "player.csv",
    }
}

# Simple queries from run_challenging_queries.py
SIMPLE_QUERIES = {
    "simple_1": {
        "dataset": "Med",
        "entity": "disease",
        "sql": "SELECT disease_name, disease_type FROM disease",
        "columns": ["disease_name", "disease_type"]
    },
    "simple_2": {
        "dataset": "Player",
        "entity": "player",
        "sql": "SELECT name, team, position FROM player",
        "columns": ["name", "team", "position"]
    }
}

def generate_ground_truth(query_id: str):
    """Generate ground truth CSV for a simple query."""
    if query_id not in SIMPLE_QUERIES:
        print(f"Error: Unknown query {query_id}")
        return False
    
    query = SIMPLE_QUERIES[query_id]
    dataset = query["dataset"]
    entity = query["entity"]
    columns = query["columns"]
    
    # Load data
    data_path = DATA_PATHS[dataset][entity]
    if not data_path.exists():
        print(f"Error: Data file not found: {data_path}")
        return False
    
    df = pd.read_csv(data_path)
    
    # Select columns (equivalent to SQL SELECT)
    if not all(col in df.columns for col in columns):
        print(f"Error: Columns not found. Available: {df.columns.tolist()}")
        return False
    
    result_df = df[columns].copy()
    
    # Save ground truth
    gt_dir = PROJECT_ROOT / "ground_truth" / "challenging_queries"
    gt_dir.mkdir(parents=True, exist_ok=True)
    
    gt_file = gt_dir / f"{query_id}_ground_truth.csv"
    result_df.to_csv(gt_file, index=False)
    
    print(f"Generated ground truth: {gt_file}")
    print(f"  Rows: {len(result_df)}, Columns: {columns}")
    
    return True

def main():
    if len(sys.argv) > 1:
        # Generate for specific query
        query_id = sys.argv[1]
        generate_ground_truth(query_id)
    else:
        # Generate for all simple queries
        print("Generating ground truth for all simple queries...")
        for query_id in SIMPLE_QUERIES:
            generate_ground_truth(query_id)
        print("\nDone!")

if __name__ == "__main__":
    main()

