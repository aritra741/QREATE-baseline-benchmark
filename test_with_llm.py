#!/usr/bin/env python3
"""Test DocETL Healthcare with actual LLM inference."""

import time
import logging
from docetl_healthcare_evaluation import HealthcareEvaluationSystem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("="*60)
print("DocETL Healthcare Evaluation Test")
print("="*60)

# Initialize evaluation system
print("\n1. Initializing evaluation system...")
evaluator = HealthcareEvaluationSystem(
    data_dir="source_data/Healthcare",
    attributes_file="Query/Med/Med_attributes.json",
    queries_file="Query/Med/Join/join_queries.sql",
    ground_truth_dir="ground_truth/Healthcare"
)

# Load first query
with open(evaluator.queries_file) as f:
    queries_text = f.read()
queries = [q.strip() for q in queries_text.split(';') if q.strip()]
test_query = queries[0]

print(f"✓ Loaded {len(queries)} queries")
print(f"\nTest query:\n{test_query[:200]}...\n")

# Run a full evaluation on one query
print("\n2. Running evaluation on Query 1...")
print("   (This will call the LLM for extraction - takes time)")
print("-" * 60)

start_time = time.time()

try:
    results_dict, cost, latency = evaluator.execute_query(query_id=1, query_sql=test_query)
    elapsed = time.time() - start_time
    
    print("-" * 60)
    print(f"\n✓ Query executed in {elapsed:.2f} seconds")
    print(f"\nResults:")
    print(f"  Tuples extracted: {len(results_dict.get('tuples', []))}")
    print(f"  Cost (k-tokens/doc/query): {cost:.4f}")
    print(f"  Latency (sec/doc/query): {latency:.4f}")
    
    if results_dict.get('tuples'):
        print(f"\n  Sample extracted tuples:")
        for i, t in enumerate(results_dict['tuples'][:3]):
            print(f"    {i+1}. {t}")
    else:
        print(f"\n  ⚠ No tuples extracted from join")
        print(f"  Query type: {results_dict.get('query_type')}")
        print(f"  Tokens used: {results_dict.get('token_count', 0)}")
        print(f"  Docs processed: {results_dict.get('num_documents_processed', 0)}")
    
except Exception as e:
    elapsed = time.time() - start_time
    print(f"\n✗ Error after {elapsed:.2f}s: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
