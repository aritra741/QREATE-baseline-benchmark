#!/usr/bin/env python3
"""
Evaluate DocETL on filter queries from UDA-Bench Healthcare dataset.
Filter queries only extract and filter single tables - no joins needed.
"""

import logging
from pathlib import Path
from docetl_healthcare_evaluation import HealthcareEvaluationSystem

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

def load_filter_queries():
    """Load filter queries from SQL files."""
    queries = {}
    
    for dataset_type in ["disease", "drug", "institution"]:
        sql_file = Path(f"Query/Med/Filter/filter_queries_{dataset_type}.sql")
        if not sql_file.exists():
            continue
        
        with open(sql_file) as f:
            lines = f.readlines()
        
        i = 0
        query_id = 1
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            # Parse query comment
            if line.startswith("--"):
                i += 1
                # Next line should be the SQL
                if i < len(lines):
                    sql = lines[i].strip()
                    queries[query_id] = (sql, dataset_type)
                    query_id += 1
                i += 1
            else:
                i += 1
    
    return queries

def main():
    logger.info("="*70)
    logger.info("EVALUATING DOCETL ON FILTER QUERIES")
    logger.info("="*70)
    
    # Load queries
    queries = load_filter_queries()
    logger.info(f"\nLoaded {len(queries)} filter queries\n")
    
    # Initialize evaluation system
    eval_sys = HealthcareEvaluationSystem()
    
    # Track results
    results_summary = []
    total_f1 = 0
    successful_queries = 0
    
    for query_id, (query_sql, dataset_type) in sorted(queries.items()):
        try:
            logger.info(f"Query {query_id}/{len(queries)} ({dataset_type})...")
            logger.info(f"  SQL: {query_sql[:80]}...")
            
            results, cost, latency = eval_sys.execute_query(query_id, query_sql)
            
            f1 = results.get("f1", 0.0)
            precision = results.get("precision", 0.0)
            recall = results.get("recall", 0.0)
            
            logger.info(f"  ✓ P={precision:.3f}, R={recall:.3f}, F1={f1:.3f}")
            logger.info(f"    Cost: {cost:.4f}k tokens, Latency: {latency:.2f}s\n")
            
            results_summary.append({
                "query_id": query_id,
                "dataset": dataset_type,
                "tuples": results.get("tuples", 0),
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "cost": cost,
                "latency": latency
            })
            
            total_f1 += f1
            successful_queries += 1
            
        except Exception as e:
            logger.error(f"  ✗ Error: {e}\n")
            results_summary.append({
                "query_id": query_id,
                "dataset": dataset_type,
                "error": str(e)
            })
    
    # Print summary
    logger.info("\n" + "="*70)
    logger.info("SUMMARY")
    logger.info("="*70)
    
    print("\nQuery  Dataset      Tuples     Precision    Recall       F1         Cost       Latency")
    print("-" * 90)
    
    for result in results_summary:
        if "error" in result:
            print(f"{result['query_id']:3d}    {result['dataset']:12s}  ERROR: {result['error'][:40]}")
        else:
            dataset = result['dataset'][:12]
            tuples_val = result.get('tuples', 0)
            if isinstance(tuples_val, list):
                tuples_val = len(tuples_val)
            p = result['precision']
            r = result['recall']
            f1 = result['f1']
            cost = result['cost']
            lat = result['latency']
            
            print(f"{result['query_id']:3d}    {dataset:12s}  {tuples_val:8d}  {p:8.3f}      {r:8.3f}      {f1:8.3f}   {cost:10.4f}  {lat:10.2f}")
    
    print("-" * 90)
    
    if successful_queries > 0:
        avg_f1 = total_f1 / successful_queries
        print(f"\nSuccessful queries: {successful_queries}/{len(queries)}")
        print(f"Average F1-score: {avg_f1:.3f}")
    else:
        print(f"\nNo successful queries")

if __name__ == "__main__":
    main()
