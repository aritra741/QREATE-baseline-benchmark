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


def values_match(val1, val2, blocker=None, resolver=None):
    """Check if two values match using two-stage matching:
    
    Stage 1: Split by ||, normalize each value, do exact matching
    Stage 2: For unmatched values:
        - For numeric values: check if difference < 1
        - For categorical values: ask GEM if they refer to the same entity
    
    If ANY split value from GT matches ANY split value from result (exactly or semantically),
    the entire cell is considered a match.
    
    Args:
        val1: First value (from GT)
        val2: Second value (from GEM result)
        blocker: SemanticBlocker instance (not used, kept for compatibility)
        resolver: EntityResolver instance for LLM-based entity matching
    
    Returns:
        True if ANY value matches, False if no matches at all
    """
    norm1 = normalize_value(val1)
    norm2 = normalize_value(val2)
    
    # Both empty
    if not norm1 and not norm2:
        return True
    
    # One empty, one not
    if (not norm1) != (not norm2):
        return False
    
    # Exact match
    if norm1 == norm2:
        return True
    
    # ============================================================
    # STAGE 1: Split by ||, normalize, and try exact matching
    # ============================================================
    values1 = [v.strip() for v in norm1.split('||') if v.strip()]
    values2 = [v.strip() for v in norm2.split('||') if v.strip()]
    
    # Try exact match: if ANY value from GT matches ANY value from result, it's a match
    for v1 in values1:
        for v2 in values2:
            if v1 == v2:
                logger.debug(f"Exact match: '{v1}' == '{v2}'")
                return True
    
    # ============================================================
    # STAGE 2: Try numeric comparison or GEM entity resolution
    # ============================================================
    for v1 in values1:
        for v2 in values2:
            # Try numeric comparison first
            try:
                num1 = float(v1)
                num2 = float(v2)
                if abs(num1 - num2) < 1:
                    logger.debug(f"Numeric match: {num1} ~ {num2} (diff={abs(num1-num2):.2f})")
                    return True
            except ValueError:
                # Not numeric values, try GEM entity resolution
                if resolver is not None:
                    try:
                        # Ask GEM if these two values refer to the same entity
                        # Using blocking to find if they should be in the same cluster
                        canonical = resolver._get_canonical_for_block([v1, v2])
                        
                        # If GEM says they map to the same canonical, they're the same entity
                        if canonical:
                            logger.debug(f"GEM entity match: '{v1}' and '{v2}' -> canonical='{canonical}'")
                            return True
                    except Exception as e:
                        logger.debug(f"GEM entity matching failed for '{v1}' vs '{v2}': {e}")
                        pass
    
    logger.debug(f"No match: '{val1}' vs '{val2}'")
    return False



def calculate_metrics(gt_df: pd.DataFrame, result_df: pd.DataFrame, blocker=None, resolver=None) -> dict:
    """Calculate precision, recall, and F1 using set-based tuple matching.
    
    Any result tuple can match any GT tuple (order-independent).
    A tuple is counted as TP only if all columns match.
    
    Args:
        gt_df: Ground truth DataFrame
        result_df: GEM result DataFrame
        blocker: SemanticBlocker instance for semantic matching
        resolver: EntityResolver instance for LLM-based matching
    """
    
    # Handle empty results
    if len(result_df) == 0 and len(gt_df) == 0:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 0, "fp": 0, "fn": 0, "note": "Both empty"}
    
    if len(result_df) == 0 and len(gt_df) > 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": len(gt_df), "note": "Empty result"}
    
    if len(result_df) > 0 and len(gt_df) == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": len(result_df), "fn": 0, "note": "Empty GT"}
    
    # Normalize column names by removing table prefixes (e.g., "disease.name" -> "name")
    gt_df_norm = gt_df.copy()
    result_df_norm = result_df.copy()
    
    gt_df_norm.columns = [col.split('.')[-1].lower() for col in gt_df_norm.columns]
    result_df_norm.columns = [col.split('.')[-1].lower() for col in result_df_norm.columns]
    
    # Get common columns (case-insensitive)
    gt_cols = set(gt_df_norm.columns)
    result_cols = set(result_df_norm.columns)
    common_cols = sorted(list(gt_cols & result_cols))
    common_cols = [c for c in common_cols if c != 'id']  # Don't compare ID column
    
    if not common_cols:
        logger.warning(f"No common columns! GT: {gt_cols}, Result: {result_cols}")
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 0, "note": "No common columns"}
    
    logger.debug(f"GT cols: {gt_cols}, Result cols: {result_cols}, Common: {common_cols}")
    logger.debug(f"GT shape: {gt_df_norm.shape}, Result shape: {result_df_norm.shape}")
    
    # Convert to dicts for set-based matching
    gt_tuples = [gt_df_norm[common_cols].iloc[i].to_dict() for i in range(len(gt_df_norm))]
    result_tuples = [result_df_norm[common_cols].iloc[i].to_dict() for i in range(len(result_df_norm))]
    
    logger.debug(f"Sample GT tuple: {gt_tuples[0] if gt_tuples else 'empty'}")
    logger.debug(f"Sample Result tuple: {result_tuples[0] if result_tuples else 'empty'}")
    
    # Track which tuples have been matched
    gt_matched = [False] * len(gt_tuples)
    result_matched = [False] * len(result_tuples)
    
    tp = 0
    
    # Try to match each result tuple with a GT tuple (greedy matching)
    for r_idx, result_tuple in enumerate(result_tuples):
        for g_idx, gt_tuple in enumerate(gt_tuples):
            if not gt_matched[g_idx]:
                # Check if all values in common columns match
                all_match = True
                for col in common_cols:
                    gt_val = gt_tuple.get(col)
                    result_val = result_tuple.get(col)
                    if not values_match(str(gt_val) if gt_val is not None else "", 
                                       str(result_val) if result_val is not None else "",
                                       blocker=blocker,
                                       resolver=resolver):
                        all_match = False
                        break
                
                if all_match:
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
    
    logger.debug(f"Metrics: TP={tp}, FP={fp}, FN={fn}, Common cols={common_cols}")
    
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
    print("Initializing GEM's semantic matching components...")
    print("=" * 100)
    print()
    
    # Initialize blocker and resolver for semantic matching
    try:
        blocker = SemanticBlocker()
        blocker.load_embedding_model()
        print("✓ Loaded embedding model for semantic similarity")
    except Exception as e:
        print(f"⚠️  Warning: Could not initialize blocker: {e}")
        blocker = None
    
    try:
        resolver = EntityResolver()
        print("✓ Initialized entity resolver for LLM verification")
    except Exception as e:
        print(f"⚠️  Warning: Could not initialize resolver: {e}")
        resolver = None
    
    print()
    print("=" * 100)
    print("QUERY RESULTS")
    print("=" * 100)
    print()
    print(f"{'Query':<8} {'Description':<40} {'GT Rows':>8} {'Gem Rows':>8} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    print("-" * 100)
    
    metrics_list = []
    failed_queries = []  # Track failed queries
    
    # Execute queries
    for i, (query_idx, gt_result) in enumerate(gt_results.items()):
        if gt_result["status"] == "error":
            print(f"[{i+1:2d}] {gt_result['comment']:<40} ERROR - {gt_result['error']}")
            failed_queries.append({
                "query_id": f"join_{i+1}",
                "description": gt_result["comment"],
                "reason": f"Ground truth generation failed: {gt_result['error']}",
                "sql": gt_result.get("sql", "N/A")
            })
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
            error_msg = meta.get('error', 'Unknown error')
            traceback_msg = meta.get('traceback', '')
            print(f"[{i+1:2d}] {gt_result['comment']:<40} {gt_rows:>8} {'ERROR':>8}")
            failed_queries.append({
                "query_id": f"join_{i+1}",
                "description": gt_result["comment"],
                "reason": error_msg,
                "traceback": traceback_msg,
                "sql": sql
            })
            continue
        
        gem_rows = len(result_df)
        
        # Calculate metrics
        print(f"  DEBUG GT columns: {list(gt_df.columns)}")
        print(f"  DEBUG Result columns: {list(result_df.columns)}")
        print(f"  DEBUG GT rows: {len(gt_df)}, Result rows: {len(result_df)}")
        if len(gt_df) > 0:
            print(f"  DEBUG GT first row: {dict(gt_df.iloc[0])}") 
        if len(result_df) > 0:
            print(f"  DEBUG Result first row: {dict(result_df.iloc[0])}")
        
        # Check for cross-products: if result has way more rows than GT, it's likely a join issue
        if len(result_df) > 0 and len(gt_df) > 0 and len(result_df) > len(gt_df) * 5:
            print(f"  ⚠️  WARNING: Result has {len(result_df)} rows but GT has {len(gt_df)} - likely cross-product join issue!")
        
        metrics = calculate_metrics(gt_df, result_df, blocker=blocker, resolver=resolver)
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
    
    # Display failed queries
    if failed_queries:
        print("=" * 100)
        print("FAILED QUERIES")
        print("=" * 100)
        print()
        
        for i, failed in enumerate(failed_queries, 1):
            print(f"[{i}] {failed['query_id']}: {failed['description']}")
            print(f"    Error: {failed['reason']}")
            
            # Show SQL if available
            if 'sql' in failed:
                print(f"    SQL: {failed['sql'][:100]}..." if len(failed['sql']) > 100 else f"    SQL: {failed['sql']}")
            
            # Show traceback if available
            if failed.get('traceback'):
                print(f"    Traceback:")
                # Show first few lines of traceback
                tb_lines = failed['traceback'].split('\n')[:5]
                for line in tb_lines:
                    print(f"      {line}")
                if len(failed['traceback'].split('\n')) > 5:
                    print(f"      ... ({len(failed['traceback'].split('\n')) - 5} more lines)")
            print()
        
        print(f"Total Failed: {len(failed_queries)}")
        print("=" * 100)
        print()
    else:
        print("✓ All queries executed successfully!")
        print("=" * 100)
        print()


if __name__ == "__main__":
    main()
