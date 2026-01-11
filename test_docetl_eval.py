#!/usr/bin/env python3
"""Quick test for DocETL Healthcare evaluation system."""

from docetl_healthcare_evaluation import HealthcareEvaluationSystem
from docetl_query_executor import DocETLHealthcareQueryExecutor

# Test 1: Initialize evaluation system
print("Test 1: Initialize evaluation system...")
try:
    evaluator = HealthcareEvaluationSystem(
        data_dir="source_data/Healthcare",
        attributes_file="Query/Med/Med_attributes.json",
        queries_file="Query/Med/Join/join_queries.sql",
        ground_truth_dir="ground_truth/Healthcare"
    )
    print(f"✓ Loaded {len(evaluator.documents)} document categories")
    for category, docs in evaluator.documents.items():
        print(f"  - {category}: {len(docs)} documents")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 2: Load queries
print("\nTest 2: Load queries...")
try:
    with open(evaluator.queries_file) as f:
        queries_text = f.read()
    queries = [q.strip() for q in queries_text.split(';') if q.strip()]
    print(f"✓ Loaded {len(queries)} queries")
    print(f"  First query: {queries[0][:80]}...")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 3: Initialize query executor
print("\nTest 3: Initialize query executor...")
try:
    executor = DocETLHealthcareQueryExecutor()
    print("✓ Query executor initialized")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 4: Parse a query
print("\nTest 4: Parse SQL query...")
try:
    test_query = queries[0]
    parsed = executor._parse_sql_query(test_query)
    print(f"✓ Query parsed successfully")
    print(f"  Type: {parsed.get('query_type')}")
    print(f"  Join key: {parsed.get('join_key')}")
    print(f"  Tables: {parsed.get('from_tables')}")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 5: Test accuracy evaluation (dummy data)
print("\nTest 5: Test accuracy evaluation...")
try:
    # Create dummy ground truth
    evaluator.ground_truth[1] = [
        {"disease_name": "test_disease", "attr1": "value1"},
    ]
    
    extracted = [
        {"disease_name": "test_disease", "attr1": "value1"},
    ]
    
    p, r, f1 = evaluator.evaluate_accuracy(1, extracted)
    print(f"✓ Accuracy evaluation works")
    print(f"  Precision: {p:.2f}, Recall: {r:.2f}, F1: {f1:.2f}")
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "="*60)
print("All tests completed!")
