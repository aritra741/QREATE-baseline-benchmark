#!/usr/bin/env python3
"""
Compare QUEST results with ground truth.

Usage:
    python compare_quest_results.py --run-id 20251210_095536
"""

import argparse
import pandas as pd
from pathlib import Path
import sys

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


def load_quest_result(run_id: str, query_id: str) -> pd.DataFrame:
    """Load QUEST result CSV."""
    result_path = PROJECT_ROOT / "results" / "challenging_queries" / run_id / "results" / "quest" / "simple" / query_id / "result.csv"
    if result_path.exists():
        return pd.read_csv(result_path)
    raise FileNotFoundError(f"Result not found: {result_path}")


def compare_results(gt_df: pd.DataFrame, result_df: pd.DataFrame, query_info: dict):
    """Compare QUEST results with ground truth."""
    print(f"\n{'='*80}")
    print(f"Query: {query_info['id']} - {query_info['name']}")
    print(f"{'='*80}\n")
    
    print(f"Ground Truth: {len(gt_df)} rows, {len(gt_df.columns)} columns")
    print(f"QUEST Result: {len(result_df)} rows, {len(result_df.columns)} columns")
    
    if len(result_df) == 0:
        print("\n⚠️  WARNING: QUEST returned EMPTY results!")
        print("   This means no documents were successfully extracted.")
        return
    
    # Check column overlap
    gt_cols = set(gt_df.columns)
    result_cols = set(result_df.columns)
    common_cols = gt_cols & result_cols
    
    print(f"\nColumns:")
    print(f"  - In ground truth: {sorted(gt_cols)[:5]}... ({len(gt_cols)} total)")
    print(f"  - In QUEST result: {sorted(result_cols)[:5]}... ({len(result_cols)} total)")
    print(f"  - Common: {len(common_cols)} columns")
    
    if not common_cols:
        print("\n❌ No common columns! Cannot compare.")
        return
    
    # Show sample of results
    print(f"\nQUEST Result Sample (first 5 rows):")
    print(result_df.head(5).to_string())
    
    print(f"\nGround Truth Sample (first 5 rows):")
    print(gt_df[list(common_cols)][:5].to_string())


def main():
    parser = argparse.ArgumentParser(description="Compare QUEST results with ground truth")
    parser.add_argument("--run-id", required=True, help="Run ID (e.g., 20251210_095536)")
    
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
    
    for query in queries:
        try:
            # Load data
            gt_df = load_ground_truth(query["dataset"], query["entity"])
            result_df = load_quest_result(args.run_id, query["id"])
            
            # Compare
            compare_results(gt_df, result_df, query)
            
        except FileNotFoundError as e:
            print(f"\n⚠️  {query['id']}: {e}")
        except Exception as e:
            print(f"\n❌ {query['id']}: Error: {e}")
    
    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()


