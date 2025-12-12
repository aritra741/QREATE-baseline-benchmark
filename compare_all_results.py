#!/usr/bin/env python3
"""
Compare UQE results with ground truth for ALL query types.

Usage:
    python compare_all_results.py --run-id 20251211_000936
"""

import argparse
import pandas as pd
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).parent
GT_DIR = PROJECT_ROOT / "ground_truth" / "challenging_queries"


def normalize_value(val):
    """Normalize a value for comparison."""
    if pd.isna(val):
        return ""
    val_str = str(val).strip().lower()
    val_str = " ".join(val_str.split())
    return val_str


def values_match(val1, val2):
    """Check if two values match, handling multi-valued fields with || separator."""
    norm1 = normalize_value(val1)
    norm2 = normalize_value(val2)
    
    if not norm1 or not norm2:
        return norm1 == norm2
    
    # Exact match
    if norm1 == norm2:
        return True
    
    # Handle multi-valued fields (separated by ||)
    # Check if either value contains the other as a complete token
    values1 = set(v.strip() for v in norm1.split('||'))
    values2 = set(v.strip() for v in norm2.split('||'))
    
    # Match if there's any overlap in values
    return bool(values1 & values2)


def calculate_metrics(gt_df: pd.DataFrame, result_df: pd.DataFrame) -> dict:
    """Calculate precision, recall, and F1."""
    
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
    
    # Normalize data for comparison
    gt_normalized = gt_df.copy()
    result_normalized = result_df.copy()
    
    # Create matching index based on row position
    gt_normalized['_idx'] = range(len(gt_normalized))
    result_normalized['_idx'] = range(len(result_normalized))
    
    # Calculate TP, FP, FN per cell
    tp = 0
    fp = 0
    fn = 0
    
    max_rows = max(len(gt_normalized), len(result_normalized))
    
    for col_lower in common_cols_lower:
        gt_col = gt_cols_lower[col_lower]
        result_col = result_cols_lower[col_lower]
        
        for idx in range(max_rows):
            # Get GT value
            if idx < len(gt_normalized):
                gt_val = gt_normalized.iloc[idx][gt_col]
                gt_val_norm = normalize_value(gt_val)
            else:
                gt_val = ""
                gt_val_norm = ""
            
            # Get result value
            if idx < len(result_normalized):
                result_val = result_normalized.iloc[idx][result_col]
                result_val_norm = normalize_value(result_val)
            else:
                result_val = ""
                result_val_norm = ""
            
            if gt_val_norm and result_val_norm:
                if values_match(gt_val, result_val):
                    tp += 1
                else:
                    fp += 1
                    fn += 1
            elif gt_val_norm and not result_val_norm:
                fn += 1
            elif result_val_norm and not gt_val_norm:
                fp += 1
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def main():
    parser = argparse.ArgumentParser(description="Compare UQE results with ground truth for ALL queries")
    parser.add_argument("--run-id", required=True, help="Run ID (e.g., 20251211_000936)")
    args = parser.parse_args()
    
    run_id = args.run_id
    results_dir = PROJECT_ROOT / "results" / "challenging_queries" / run_id
    
    # Load detailed report
    report_path = results_dir / "detailed_report.json"
    if not report_path.exists():
        print(f"Error: Report not found at {report_path}")
        return
    
    with open(report_path) as f:
        report = json.load(f)
    
    print("=" * 100)
    print("UQE BENCHMARK RESULTS - ALL QUERY TYPES")
    print(f"Run ID: {run_id}")
    print("=" * 100)
    print()
    
    # Summary
    uqe = report["systems"]["uqe"]
    print(f"Total Queries: {uqe['total']}")
    print(f"Completed: {uqe['completed']}")
    print(f"Failed: {uqe['failed']}")
    print(f"Unsupported: {uqe.get('unsupported', 0)}")
    print()
    
    # Detailed comparison
    print("-" * 100)
    print(f"{'Query ID':<15} {'Type':<12} {'Status':<12} {'GT Rows':>8} {'Result':>8} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    print("-" * 100)
    
    all_metrics = []
    
    for query_id, query_data in sorted(report["systems"]["uqe"]["queries"].items()):
        qtype = query_data["query_type"]
        status = query_data["status"]
        
        gt_rows = "N/A"
        result_rows = "N/A"
        precision = "N/A"
        recall = "N/A"
        f1 = "N/A"
        
        # Load ground truth
        gt_file = GT_DIR / f"{query_id}_ground_truth.csv"
        
        if status == "completed":
            # Load result
            result_path = results_dir / "results" / "uqe" / qtype / query_id / "result.csv"
            
            if result_path.exists():
                result_df = pd.read_csv(result_path)
                result_rows = len(result_df)
                
                if gt_file.exists():
                    gt_df = pd.read_csv(gt_file)
                    gt_rows = len(gt_df)
                    
                    # Calculate metrics
                    metrics = calculate_metrics(gt_df, result_df)
                    precision = f"{metrics['precision']:.4f}"
                    recall = f"{metrics['recall']:.4f}"
                    f1 = f"{metrics['f1']:.4f}"
                    
                    all_metrics.append({
                        "query_id": query_id,
                        "type": qtype,
                        "precision": metrics["precision"],
                        "recall": metrics["recall"],
                        "f1": metrics["f1"]
                    })
                else:
                    gt_rows = "No GT"
        
        print(f"{query_id:<15} {qtype:<12} {status:<12} {str(gt_rows):>8} {str(result_rows):>8} {precision:>10} {recall:>10} {f1:>10}")
    
    # Calculate averages
    print("-" * 100)
    
    avg_p = None
    avg_r = None
    avg_f1 = None
    
    if all_metrics:
        avg_p = sum(m["precision"] for m in all_metrics) / len(all_metrics)
        avg_r = sum(m["recall"] for m in all_metrics) / len(all_metrics)
        avg_f1 = sum(m["f1"] for m in all_metrics) / len(all_metrics)
        
        print(f"{'AVERAGE':<15} {'(n=' + str(len(all_metrics)) + ')':<12} {'':<12} {'':<8} {'':<8} {avg_p:>10.4f} {avg_r:>10.4f} {avg_f1:>10.4f}")
    
    print("=" * 100)
    print()

    # Summary by query type
    print("SUMMARY BY QUERY TYPE:")
    print("-" * 100)
    
    by_type = report.get("by_query_type", {})
    for qtype in ["simple", "filter", "projection", "join", "aggregation", "union"]:
        if qtype not in by_type:
            continue
        stats = by_type[qtype]
        total = stats["total"]
        completed = stats["completed"]
        failed = stats["failed"]
        rate = (completed / total * 100) if total > 0 else 0
        
        # Calculate average metrics for this type
        type_metrics = [m for m in all_metrics if m["type"] == qtype]
        if type_metrics:
            type_p = sum(m["precision"] for m in type_metrics) / len(type_metrics)
            type_r = sum(m["recall"] for m in type_metrics) / len(type_metrics)
            type_f1 = sum(m["f1"] for m in type_metrics) / len(type_metrics)
            metrics_str = f"P={type_p:.2f} R={type_r:.2f} F1={type_f1:.2f}"
        else:
            metrics_str = "N/A"
        
        print(f"  {qtype:<12}: {completed}/{total} completed ({rate:.0f}%) | {metrics_str}")
    
    print("=" * 100)
    
    # Save metrics to JSON and CSV files
    metrics_output_dir = results_dir / "metrics"
    metrics_output_dir.mkdir(exist_ok=True)
    
    # Save as JSON
    metrics_json = {
        "run_id": run_id,
        "summary": {
            "total_queries": uqe['total'],
            "completed": uqe['completed'],
            "failed": uqe['failed'],
            "unsupported": uqe.get('unsupported', 0),
            "average_precision": avg_p if all_metrics else None,
            "average_recall": avg_r if all_metrics else None,
            "average_f1": avg_f1 if all_metrics else None
        },
        "queries": all_metrics,
        "by_type": {}
    }
    
    # Add metrics by type
    for qtype in ["simple", "filter", "projection", "join", "aggregation", "union"]:
        type_metrics = [m for m in all_metrics if m["type"] == qtype]
        if type_metrics:
            metrics_json["by_type"][qtype] = {
                "count": len(type_metrics),
                "average_precision": sum(m["precision"] for m in type_metrics) / len(type_metrics),
                "average_recall": sum(m["recall"] for m in type_metrics) / len(type_metrics),
                "average_f1": sum(m["f1"] for m in type_metrics) / len(type_metrics)
            }
    
    json_path = metrics_output_dir / "evaluation_metrics.json"
    with open(json_path, 'w') as f:
        json.dump(metrics_json, f, indent=2)
    print(f"\nMetrics saved to: {json_path}")
    
    # Save as CSV
    if all_metrics:
        metrics_df = pd.DataFrame(all_metrics)
        csv_path = metrics_output_dir / "evaluation_metrics.csv"
        metrics_df.to_csv(csv_path, index=False)
        print(f"Metrics saved to: {csv_path}")


if __name__ == "__main__":
    main()

