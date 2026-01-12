#!/usr/bin/env python3
"""Debug: Check what tuples are actually being extracted"""

from docetl_query_executor import DocETLHealthcareQueryExecutor
from pathlib import Path
import json

# Load SQL query
with open("Query/Med/Join/join_queries.sql") as f:
    queries = f.readlines()
    query_1 = queries[0]

print(f"Query 1: {query_1[:100]}...")

# Execute
executor = DocETLHealthcareQueryExecutor()
results = executor.execute_join_query(query_1)

tuples = results.get("tuples", [])
print(f"\nTotal tuples extracted: {len(tuples)}")

if tuples:
    print(f"\nFirst 3 tuples:")
    for i, t in enumerate(tuples[:3]):
        print(f"\n  Tuple {i+1}:")
        for k, v in t.items():
            val_str = str(v)[:60] if v else v
            print(f"    {k}: {val_str}")
    
    # Count tuples with actual values (not "Not found")
    has_disease_name = sum(1 for t in tuples if t.get("disease.disease_name", "").lower() != "not found")
    has_generic_name = sum(1 for t in tuples if t.get("drug.generic_name", "").lower() != "not found")
    
    print(f"\n\nStats:")
    print(f"  Tuples with non-null disease.disease_name: {has_disease_name}/{len(tuples)}")
    print(f"  Tuples with non-null drug.generic_name: {has_generic_name}/{len(tuples)}")
