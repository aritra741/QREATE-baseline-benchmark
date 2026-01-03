#!/usr/bin/env python3
"""
Test GEM with JOIN queries from Med dataset.

This script:
1. Loads the join queries from Query/Med/Join/join_queries.sql
2. Generates ground truth by executing queries against CSV files
3. Executes queries through GEM
4. Compares results with ground truth
"""

import pandas as pd
import sqlite3
from pathlib import Path
import sys
import re
import logging

PROJECT_ROOT = Path(__file__).parent

# Add GEM to path
sys.path.insert(0, str(PROJECT_ROOT / "systems"))

from GEM.gem_runner import GEMRunner
from GEM.blocking import SemanticBlocker
from GEM.resolver import EntityResolver

# Setup logging
logger = logging.getLogger(__name__)

# Initialize GEM's entity matcher components
try:
    blocker = SemanticBlocker(logger=logger)
    resolver = EntityResolver(logger=logger)
    HAS_ENTITY_MANAGER = True
except Exception as e:
    HAS_ENTITY_MANAGER = False
    logger.warning(f"Failed to initialize GEM entity manager: {e}")


def load_join_queries(sql_file: Path) -> list:
    """Load JOIN queries from SQL file."""
    with open(sql_file) as f:
        content = f.read()
    
    queries = []
    lines = content.strip().split('\n')
    current_comment = ""
    current_sql = []
    query_num = 0
    
    for line in lines:
        line = line.rstrip()
        
        # Check if this is a query header comment
        if line.startswith('-- Query'):
            # Save previous query if exists
            if current_sql:
                query_num += 1
                sql = ' '.join(current_sql).strip()
                if sql.endswith(';'):
                    sql = sql[:-1].strip()
                
                queries.append({
                    "id": f"join_{query_num}",
                    "comment": current_comment,
                    "sql": sql
                })
            
            # Start new query
            current_comment = line[2:].strip()  # Remove '-- '
            current_sql = []
        elif line and not line.startswith('--'):
            # Add SQL line
            current_sql.append(line)
    
    # Save last query
    if current_sql:
        query_num += 1
        sql = ' '.join(current_sql).strip()
        if sql.endswith(';'):
            sql = sql[:-1].strip()
        
        queries.append({
            "id": f"join_{query_num}",
            "comment": current_comment,
            "sql": sql
        })
    
    return queries


def load_csv_data(data_dir: Path) -> dict:
    """Load CSV data files."""
    data = {}
    for csv_file in data_dir.glob("*.csv"):
        table_name = csv_file.stem
        data[table_name] = pd.read_csv(csv_file)
        print(f"Loaded {table_name}: {len(data[table_name])} rows, {len(data[table_name].columns)} columns")
    
    return data


def generate_ground_truth(queries: list, data: dict) -> dict:
    """Generate ground truth by executing queries against CSV data."""
    results = {}
    
    # Create in-memory SQLite database
    conn = sqlite3.connect(":memory:")
    
    # Register all tables
    for table_name, df in data.items():
        df.to_sql(table_name, conn, if_exists='replace', index=False)
    
    print(f"\nGenerating ground truth for {len(queries)} queries...")
    
    for i, query in enumerate(queries):
        query_sql = query["sql"]
        try:
            gt_df = pd.read_sql_query(query_sql, conn)
            results[i] = {
                "sql": query_sql,
                "comment": query["comment"],
                "ground_truth": gt_df,
                "gt_rows": len(gt_df),
                "status": "success"
            }
            print(f"  [{i+1}] {query['comment']}: {len(gt_df)} rows")
        except Exception as e:
            # Log error but don't fail
            error_msg = str(e)
            print(f"  [{i+1}] {query['comment']}: ERROR - {error_msg}")
            results[i] = {
                "sql": query_sql,
                "comment": query["comment"],
                "error": error_msg,
                "status": "error"
            }
            print(f"  [{i+1}] {query['comment']}: ERROR - {e}")
    
    conn.close()
    return results


def normalize_value(val):
    """Normalize a value for comparison."""
    if pd.isna(val):
        return ""
    val_str = str(val).strip().lower()
    val_str = " ".join(val_str.split())
    return val_str


def llm_values_match(val1: str, val2: str) -> bool:
    """Check if two values belong to the same entity.
    
    For now, uses exact normalized matching only.
    TODO: Add semantic matching with GEM's entity manager later.
    """
    if not val1 or not val2:
        return False
    
    # Normalize both values
    norm_val1 = normalize_value(val1)
    norm_val2 = normalize_value(val2)
    
    # Exact match after normalization
    if norm_val1 == norm_val2:
        return True
    
    return False


def values_match(val1, val2):
    """Check if two values match using GEM's entity manager.
    
    Matching strategy:
    1. Normalize both values
    2. Check exact match
    3. Use GEM's blocking + resolution (semantic similarity + LLM confirmation)
    """
    norm1 = normalize_value(val1)
    norm2 = normalize_value(val2)
    
    if not norm1 or not norm2:
        return norm1 == norm2
    
    # Exact match (after normalization)
    if norm1 == norm2:
        return True
    
    # Handle multi-valued fields (separated by ||)
    values1 = [v.strip() for v in norm1.split('||') if v.strip()]
    values2 = [v.strip() for v in norm2.split('||') if v.strip()]
    
    # For multi-valued fields, check if there's ANY overlap
    for v1 in values1:
        for v2 in values2:
            # Exact match
            if v1 == v2:
                return True
            
            # Use GEM's entity manager (blocking + resolution)
            if llm_values_match(v1, v2):
                return True
    
    return False


def tuple_matches(gt_row: dict, result_row: dict, common_cols_lower: set, gt_cols_lower: dict, result_cols_lower: dict) -> bool:
    """Check if a result tuple matches a GT tuple (all columns must match)."""
    for col_lower in common_cols_lower:
        gt_col = gt_cols_lower[col_lower]
        result_col = result_cols_lower[col_lower]
        
        gt_val = gt_row[gt_col]
        result_val = result_row[result_col]
        
        gt_val_norm = normalize_value(gt_val)
        result_val_norm = normalize_value(result_val)
        
        # Both empty = match, both have values = check if they match, one empty one not = no match
        if not gt_val_norm and not result_val_norm:
            continue
        elif gt_val_norm and result_val_norm:
            if not values_match(gt_val, result_val):
                return False
        else:
            return False
    
    return True


def calculate_metrics(gt_df: pd.DataFrame, result_df: pd.DataFrame) -> dict:
    """Calculate precision, recall, and F1 using set-based tuple matching.
    
    Any result tuple can match any GT tuple (order-independent).
    A tuple is counted as TP only if all columns match.
    """
    
    # Handle empty results
    if len(result_df) == 0 and len(gt_df) == 0:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 0, "fp": 0, "fn": 0, "note": "Both empty"}
    
    if len(result_df) == 0 and len(gt_df) > 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": len(gt_df), "note": "Empty result"}
    
    if len(result_df) > 0 and len(gt_df) == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": len(result_df), "fn": 0, "note": "Empty GT"}
    
    # Get common columns (case-insensitive matching)
    gt_cols_lower = {c.lower(): c for c in gt_df.columns}
    result_cols_lower = {c.lower(): c for c in result_df.columns}
    
    common_cols_lower = set(gt_cols_lower.keys()) & set(result_cols_lower.keys())
    common_cols_lower.discard('id')  # Don't compare ID column
    
    if not common_cols_lower:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 0, "note": "No common columns"}
    
    # Convert to dicts for set-based matching
    gt_tuples = [gt_df.iloc[i].to_dict() for i in range(len(gt_df))]
    result_tuples = [result_df.iloc[i].to_dict() for i in range(len(result_df))]
    
    # Track which tuples have been matched
    gt_matched = [False] * len(gt_tuples)
    result_matched = [False] * len(result_tuples)
    
    tp = 0
    
    # Try to match each result tuple with a GT tuple (greedy matching)
    for r_idx, result_tuple in enumerate(result_tuples):
        for g_idx, gt_tuple in enumerate(gt_tuples):
            if not gt_matched[g_idx] and tuple_matches(gt_tuple, result_tuple, common_cols_lower, gt_cols_lower, result_cols_lower):
                # Found a match
                gt_matched[g_idx] = True
                result_matched[r_idx] = True
                tp += 1
                break
    
    # Count unmatched tuples
    fn = sum(1 for matched in gt_matched if not matched)  # Unmatched GT tuples
    fp = sum(1 for matched in result_matched if not matched)  # Unmatched result tuples
    
    precision = tp / len(result_tuples) if len(result_tuples) > 0 else 0.0
    recall = tp / len(gt_tuples) if len(gt_tuples) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def main():
    print("=" * 100)
    print("GEM JOIN QUERY EVALUATION")
    print("=" * 100)
    print()
    
    # Paths
    queries_file = PROJECT_ROOT / "Query" / "Med" / "Join" / "join_queries.sql"
    data_dir = PROJECT_ROOT / "Data" / "Med"
    
    # Load queries
    print(f"Loading queries from {queries_file}")
    queries = load_join_queries(queries_file)
    print(f"Loaded {len(queries)} queries")
    print()
    
    # Load CSV data
    print(f"Loading CSV data from {data_dir}")
    data = load_csv_data(data_dir)
    print()
    
    # Generate ground truth
    gt_results = generate_ground_truth(queries, data)
    print()
    
    # Initialize GEM runner
    print("Initializing GEM runner...")
    gem_runner = GEMRunner()
    
    # Preprocess Med dataset
    print("Preprocessing Med dataset...")
    preprocess_meta = gem_runner.preprocess("Med", "disease")
    if preprocess_meta["status"] not in ["completed", "completed_empty"]:
        print(f"ERROR: Preprocessing failed: {preprocess_meta}")
        return
    
    preprocess_meta = gem_runner.preprocess("Med", "drug")
    if preprocess_meta["status"] not in ["completed", "completed_empty"]:
        print(f"ERROR: Preprocessing failed: {preprocess_meta}")
        return
    
    preprocess_meta = gem_runner.preprocess("Med", "institution")
    if preprocess_meta["status"] not in ["completed", "completed_empty"]:
        print(f"ERROR: Preprocessing failed: {preprocess_meta}")
        return
    
    print()
    print("=" * 100)
    print("QUERY RESULTS")
    print("=" * 100)
    print()
    print(f"{'Query':<8} {'Description':<40} {'GT Rows':>8} {'Gem Rows':>8} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    print("-" * 100)
    
    metrics_list = []
    
    # Execute queries
    for i, (query_idx, gt_result) in enumerate(gt_results.items()):
        if gt_result["status"] == "error":
            print(f"[{i+1:2d}] {gt_result['comment']:<40} ERROR - {gt_result['error']}")
            continue
        
        sql = gt_result["sql"]
        gt_df = gt_result["ground_truth"]
        gt_rows = gt_result["gt_rows"]
        
        # Execute through GEM
        query_dict = {
            "id": f"join_{i+1}",
            "dataset": "Med",
            "entity": "disease,drug,institution",
            "sql": sql
        }
        
        result_df, meta = gem_runner.run_query(query_dict)
        
        if result_df is None or meta["status"] != "completed":
            print(f"[{i+1:2d}] {gt_result['comment']:<40} {gt_rows:>8} {'ERROR':>8}")
            continue
        
        gem_rows = len(result_df)
        
        # Calculate metrics
        metrics = calculate_metrics(gt_df, result_df)
        precision = metrics["precision"]
        recall = metrics["recall"]
        f1 = metrics["f1"]
        
        metrics_list.append({
            "query_id": f"join_{i+1}",
            "description": gt_result["comment"],
            "gt_rows": gt_rows,
            "gem_rows": gem_rows,
            "precision": precision,
            "recall": recall,
            "f1": f1
        })
        
        print(f"[{i+1:2d}] {gt_result['comment']:<40} {gt_rows:>8} {gem_rows:>8} {precision:>10.4f} {recall:>10.4f} {f1:>10.4f}")
    
    # Summary
    print("-" * 100)
    
    if metrics_list:
        avg_p = sum(m["precision"] for m in metrics_list) / len(metrics_list)
        avg_r = sum(m["recall"] for m in metrics_list) / len(metrics_list)
        avg_f1 = sum(m["f1"] for m in metrics_list) / len(metrics_list)
        
        print(f"{'AVERAGE':<50} {avg_p:>10.4f} {avg_r:>10.4f} {avg_f1:>10.4f}")
    
    print("=" * 100)
    print()


if __name__ == "__main__":
    main()
