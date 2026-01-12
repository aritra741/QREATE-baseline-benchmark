#!/usr/bin/env python3
"""Evaluate DocETL on all Healthcare queries."""

import time
import logging
from docetl_healthcare_evaluation import HealthcareEvaluationSystem

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

print("="*70)
print("DocETL Healthcare Evaluation - All Queries")
print("="*70)

# Initialize
evaluator = HealthcareEvaluationSystem(
    data_dir="source_data/Healthcare",
    attributes_file="Query/Med/Med_attributes.json",
    queries_file="Query/Med/Join/join_queries.sql",
    ground_truth_dir="ground_truth/Healthcare"
)

# Load queries
with open(evaluator.queries_file) as f:
    queries_text = f.read()
queries = [q.strip() for q in queries_text.split(';') if q.strip()]

print(f"\nLoaded {len(queries)} queries\n")

# Run evaluation on all queries
results = []
total_start = time.time()

for query_id, query_sql in enumerate(queries, 1):
    # TEMPORARY: Only test query 11
    if query_id != 11:
        continue
    
    print(f"Query {query_id}/{len(queries)}...", end=" ", flush=True)
    start = time.time()
    
    try:
        results_dict, cost, latency = evaluator.execute_query(query_id, query_sql)
        elapsed = time.time() - start
        
        result = {
            "query_id": query_id,
            "tuples": len(results_dict.get("tuples", [])),
            "precision": results_dict.get("precision", 0.0),
            "recall": results_dict.get("recall", 0.0),
            "f1": results_dict.get("f1", 0.0),
            "cost_k_tokens": cost,
            "latency_sec": latency,
            "elapsed": elapsed
        }
        results.append(result)
        
        print(f"✓ {result['tuples']} tuples, F1={result['f1']:.3f}")
        
    except Exception as e:
        print(f"✗ Error: {str(e)[:60]}")
        results.append({
            "query_id": query_id,
            "error": str(e)
        })

total_time = time.time() - total_start

# Print summary
print("\n" + "="*70)
print("SUMMARY")
print("="*70 + "\n")

print(f"{'Query':<8} {'Tuples':<10} {'Precision':<12} {'Recall':<12} {'F1':<10} {'Cost':<10} {'Latency':<10}")
print("-" * 70)

total_tuples = 0
total_f1 = 0
valid_queries = 0

for r in results:
    if "error" not in r:
        valid_queries += 1
        total_tuples += r["tuples"]
        total_f1 += r["f1"]
        print(f"{r['query_id']:<8} {r['tuples']:<10} {r['precision']:<12.3f} {r['recall']:<12.3f} {r['f1']:<10.3f} {r['cost_k_tokens']:<10.4f} {r['latency_sec']:<10.2f}")
    else:
        print(f"{r['query_id']:<8} ERROR: {r['error']}")

print("-" * 70)
if valid_queries > 0:
    print(f"{'AVERAGE':<8} {total_tuples/valid_queries:<10.1f} {'':<12} {'':<12} {total_f1/valid_queries:<10.3f}")
    print(f"\nTotal queries: {valid_queries}/{len(queries)}")
    print(f"Total execution time: {total_time:.1f}s")
    print(f"Average F1-score: {total_f1/valid_queries:.3f}")
    print(f"Total tuples extracted: {total_tuples}")

print("\n" + "="*70)
