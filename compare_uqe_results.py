#!/usr/bin/env python3
"""
Compare UQE results with ground truth.

Usage:
    python compare_uqe_results.py --run-id 20251210_185123
"""

import argparse
import pandas as pd
from pathlib import Path
import sys
import json

PROJECT_ROOT = Path(__file__).parent

# Ground truth paths
GT_PATHS = {
    "Med": {
        "disease": PROJECT_ROOT / "Data" / "Med" / "disease.csv",
    },
    "Player": {
        "player": PROJECT_ROOT / "Data" / "Player" / "player.csv",
    }
}


def load_ground_truth(dataset: str, entity: str) -> pd.DataFrame:
    """Load ground truth CSV."""
    path = GT_PATHS.get(dataset, {}).get(entity)
    if path and path.exists():
        return pd.read_csv(path)
    raise FileNotFoundError(f"Ground truth not found: {dataset}/{entity}")


def load_uqe_metadata(run_id: str, query_id: str) -> dict:
    """Load UQE query metadata."""
    metadata_path = PROJECT_ROOT / "results" / "challenging_queries" / run_id / "results" / "uqe" / "simple" / query_id / "metadata.json"
    
    if metadata_path.exists():
        with open(metadata_path) as f:
            return json.load(f)
    return {}


def load_uqe_result(run_id: str, query_id: str) -> pd.DataFrame:
    """Load UQE result CSV."""
    result_path = PROJECT_ROOT / "results" / "challenging_queries" / run_id / "results" / "uqe" / "simple" / query_id / "result.csv"
    
    if result_path.exists():
        return pd.read_csv(result_path)
    raise FileNotFoundError(f"Result CSV not found: {result_path}")


def load_query_info(run_id: str, query_id: str) -> dict:
    """Load query information."""
    query_path = PROJECT_ROOT / "results" / "challenging_queries" / run_id / "results" / "uqe" / "simple" / query_id / "query.json"
    
    if query_path.exists():
        with open(query_path) as f:
            return json.load(f)
    return {}


def extract_selected_columns(query_info: dict) -> list:
    """Extract column names from SQL SELECT clause."""
    sql = query_info.get("sql", "")
    if not sql:
        return []
    
    # Simple parsing: extract columns from SELECT ... FROM
    lines = sql.split("\n")
    select_line = None
    for line in lines:
        if line.strip().upper().startswith("SELECT"):
            select_line = line.strip()
            break
    
    if not select_line:
        return []
    
    # Remove "SELECT" keyword
    select_part = select_line[6:].strip()
    # Split by comma and clean up
    columns = [col.strip() for col in select_part.split(",")]
    return columns


def normalize_value(val):
    """Normalize a value for comparison."""
    if pd.isna(val):
        return ""
    val_str = str(val).strip().lower()
    # Remove extra whitespace
    val_str = " ".join(val_str.split())
    return val_str


def calculate_metrics(gt_df: pd.DataFrame, result_df: pd.DataFrame, id_col: str, data_cols: list) -> dict:
    """Calculate precision, recall, and F1 for each column and overall."""
    metrics = {}
    
    # Normalize ID columns
    gt_df = gt_df.copy()
    result_df = result_df.copy()
    
    # Map IDs: ground truth might use numeric index, UQE uses string IDs like "disease_0"
    # Try to match by position if ID format differs
    gt_df['_match_idx'] = range(len(gt_df))
    
    # Extract numeric part from UQE IDs (e.g., "disease_0" -> 0)
    if id_col in result_df.columns:
        result_df['_match_idx'] = result_df[id_col].str.extract(r'(\d+)$')[0].astype(int)
    else:
        result_df['_match_idx'] = range(len(result_df))
    
    # Merge on match index
    merged = pd.merge(gt_df, result_df, on='_match_idx', how='outer', suffixes=('_gt', '_result'))
    
    overall_tp = 0
    overall_fp = 0
    overall_fn = 0
    
    for col in data_cols:
        col_gt = f"{col}_gt" if f"{col}_gt" in merged.columns else col
        col_result = f"{col}_result" if f"{col}_result" in merged.columns else col
        
        if col_gt not in merged.columns or col_result not in merged.columns:
            metrics[col] = {
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "tp": 0,
                "fp": 0,
                "fn": 0
            }
            continue
        
        # Compare values
        tp = 0  # True positives: correct matches
        fp = 0  # False positives: result has value but wrong
        fn = 0  # False negatives: ground truth has value but result missing/wrong
        
        for idx, row in merged.iterrows():
            gt_val = normalize_value(row[col_gt])
            result_val = normalize_value(row[col_result])
            
            if gt_val and result_val:
                if gt_val == result_val:
                    tp += 1
                    overall_tp += 1
                else:
                    fp += 1
                    fn += 1
                    overall_fp += 1
                    overall_fn += 1
            elif gt_val and not result_val:
                fn += 1
                overall_fn += 1
            elif result_val and not gt_val:
                fp += 1
                overall_fp += 1
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        metrics[col] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tp": tp,
            "fp": fp,
            "fn": fn
        }
    
    # Overall metrics
    overall_precision = overall_tp / (overall_tp + overall_fp) if (overall_tp + overall_fp) > 0 else 0.0
    overall_recall = overall_tp / (overall_tp + overall_fn) if (overall_tp + overall_fn) > 0 else 0.0
    overall_f1 = 2 * (overall_precision * overall_recall) / (overall_precision + overall_recall) if (overall_precision + overall_recall) > 0 else 0.0
    
    metrics["overall"] = {
        "precision": overall_precision,
        "recall": overall_recall,
        "f1": overall_f1,
        "tp": overall_tp,
        "fp": overall_fp,
        "fn": overall_fn
    }
    
    return metrics


def compare_results(gt_df: pd.DataFrame, result_df: pd.DataFrame, query_info: dict, selected_cols: list, system: str = "UQE"):
    """Compare results with virtual ground truth (only selected columns)."""
    print(f"\n{'='*80}")
    print(f"Query: {query_info['id']} - {query_info['name']}")
    print(f"{'='*80}\n")
    
    if result_df is None or len(result_df) == 0:
        print(f"\n⚠️  WARNING: {system} returned EMPTY results!")
        print("   This means no documents were successfully extracted.")
        return
    
    # Create virtual ground truth with only selected columns
    gt_virtual = gt_df[selected_cols].copy() if all(col in gt_df.columns for col in selected_cols) else pd.DataFrame()
    
    # Rename result columns to remove "description." prefix
    result_df_renamed = result_df.copy()
    renamed_cols = {}
    for col in result_df_renamed.columns:
        if col.startswith("description."):
            renamed_cols[col] = col.replace("description.", "")
        elif col == "id":
            continue  # Keep id column as is
    result_df_renamed.rename(columns=renamed_cols, inplace=True)
    
    # Remove id column from selected columns for comparison (we'll use it for matching)
    data_cols = [col for col in selected_cols if col != "id"]
    
    print(f"Virtual Ground Truth: {len(gt_virtual)} rows, {len(selected_cols)} columns")
    print(f"  Selected columns: {selected_cols}")
    print(f"{system} Result: {len(result_df_renamed)} rows, {len(result_df_renamed.columns)} columns")
    
    if len(gt_virtual) == 0:
        print(f"\n❌ Cannot create virtual ground truth - missing columns in GT")
        print(f"   Required: {selected_cols}")
        print(f"   Available: {list(gt_df.columns)}")
        return
    
    # Calculate metrics
    id_col = "id" if "id" in result_df_renamed.columns else selected_cols[0]
    metrics = calculate_metrics(gt_virtual, result_df_renamed, id_col, data_cols)
    
    # Print metrics
    print(f"\n{'='*80}")
    print(f"EVALUATION METRICS")
    print(f"{'='*80}\n")
    
    print(f"{'Column':<25} {'Precision':<12} {'Recall':<12} {'F1':<12} {'TP':<6} {'FP':<6} {'FN':<6}")
    print(f"{'-'*80}")
    
    for col in data_cols:
        if col in metrics:
            m = metrics[col]
            print(f"{col:<25} {m['precision']:<12.4f} {m['recall']:<12.4f} {m['f1']:<12.4f} {m['tp']:<6} {m['fp']:<6} {m['fn']:<6}")
    
    print(f"{'-'*80}")
    if "overall" in metrics:
        m = metrics["overall"]
        print(f"{'OVERALL':<25} {m['precision']:<12.4f} {m['recall']:<12.4f} {m['f1']:<12.4f} {m['tp']:<6} {m['fp']:<6} {m['fn']:<6}")
    
    # Show sample comparison
    print(f"\n{'='*80}")
    print(f"SAMPLE COMPARISON (first 5 rows)")
    print(f"{'='*80}\n")
    
    print(f"Virtual Ground Truth:")
    print(gt_virtual.head(5).to_string())
    
    print(f"\n{system} Result:")
    result_display = result_df_renamed[['id'] + data_cols].head(5) if 'id' in result_df_renamed.columns else result_df_renamed[data_cols].head(5)
    print(result_display.to_string())


def main():
    parser = argparse.ArgumentParser(description="Compare UQE results with ground truth")
    parser.add_argument("--run-id", required=True, help="Run ID (e.g., 20251210_185123)")
    
    args = parser.parse_args()
    
    # Simple queries from run_challenging_queries.py
    queries = [
        {
            "id": "simple_1",
            "name": "Simple projection query on disease",
            "dataset": "Med",
            "entity": "disease",
        },
        {
            "id": "simple_2",
            "name": "Simple projection query on player",
            "dataset": "Player",
            "entity": "player",
        }
    ]
    
    print(f"\n{'='*80}")
    print(f"UQE Result Comparison")
    print(f"Run ID: {args.run_id}")
    print(f"{'='*80}")
    
    # Load overall report
    detailed_path = PROJECT_ROOT / "results" / "challenging_queries" / args.run_id / "detailed_report.json"
    if detailed_path.exists():
        with open(detailed_path) as f:
            report = json.load(f)
        
        if "systems" in report and "uqe" in report["systems"]:
            uqe_summary = report["systems"]["uqe"]
            print(f"\nUQE Summary:")
            print(f"  Total: {uqe_summary['total']}")
            print(f"  Completed: {uqe_summary['completed']}")
            print(f"  Failed: {uqe_summary['failed']}")
    
    for query in queries:
        try:
            # Load metadata
            metadata = load_uqe_metadata(args.run_id, query["id"])
            status = metadata.get("status", "unknown")
            error_msg = metadata.get("error", "")
            elapsed_time = metadata.get("elapsed_time", 0)
            
            print(f"\n{'-'*80}")
            print(f"Query: {query['id']}")
            print(f"  Status: {status}")
            if error_msg:
                print(f"  Error: {error_msg}")
            if elapsed_time:
                print(f"  Time: {elapsed_time:.2f}s")
            print(f"{'-'*80}")
            
            if status == "failed":
                print(f"⚠️  Query failed - no results to compare")
                continue
            
            if status != "completed":
                print(f"⚠️  Query did not complete - no results to compare")
                continue
            
            # Load query info to extract selected columns
            query_info = load_query_info(args.run_id, query["id"])
            selected_cols = extract_selected_columns(query_info)
            
            if not selected_cols:
                print(f"⚠️  Could not extract selected columns from query")
                continue
            
            # Try to load data and compare
            gt_df = load_ground_truth(query["dataset"], query["entity"])
            
            # Load result CSV
            try:
                result_df = load_uqe_result(args.run_id, query["id"])
                
                compare_results(gt_df, result_df, query, selected_cols, system="UQE")
            except FileNotFoundError as e:
                print(f"⚠️  {e}")
                
        except FileNotFoundError as e:
            print(f"\n⚠️  {query['id']}: {e}")
        except Exception as e:
            print(f"\n❌ {query['id']}: Error: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()
