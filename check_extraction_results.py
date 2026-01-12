#!/usr/bin/env python3
"""Check what's actually being extracted from the documents"""

from docetl_healthcare_evaluation import HealthcareEvaluationSystem
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

eval_sys = HealthcareEvaluationSystem()

# Get first disease and drug doc
disease_docs = eval_sys.documents.get("disease", [])
drug_docs = eval_sys.documents.get("drug", [])

print("=" * 60)
print("DISEASE DOC 0")
print("=" * 60)
print(disease_docs[0][:300] + "...")

print("\n" + "=" * 60)
print("DISEASE DOC 1")
print("=" * 60)
print(disease_docs[1][:300] + "...")

print("\n" + "=" * 60)
print("DRUG DOC 0")
print("=" * 60)
print(drug_docs[0][:300] + "...")

# Now let's check the extracted records from the join
from docetl_query_executor import DocETLHealthcareQueryExecutor

with open("Query/Med/Join/join_queries.sql") as f:
    query_1 = f.readlines()[0]

executor = DocETLHealthcareQueryExecutor(
    attributes_file="Query/Med/Med_attributes.json",
    model="ollama/qwen2.5:7b-instruct"
)

print("\n" + "=" * 60)
print("EXECUTING QUERY")
print("=" * 60)

results = executor.execute_join_query(query_1, disease_docs, drug_docs, [])

tuples = results.get("tuples", [])
print(f"Total tuples: {len(tuples)}")

if tuples:
    print(f"\nFirst 5 tuples:")
    for i, t in enumerate(tuples[:5]):
        disease_name_val = t.get("disease.disease_name", "")
        drug_disease_val = t.get("disease.disease_name")  # from disease table
        generic_name_val = t.get("drug.generic_name", "")
        
        print(f"\n  Tuple {i+1}:")
        print(f"    disease.disease_name: {disease_name_val[:30] if disease_name_val else 'EMPTY'}")
        print(f"    drug.generic_name: {generic_name_val[:30] if generic_name_val else 'EMPTY'}")
        
    # Stats
    count_with_disease = sum(1 for t in tuples if t.get("disease.disease_name", "").lower() not in ("", "not found"))
    count_with_drug = sum(1 for t in tuples if t.get("drug.generic_name", "").lower() not in ("", "not found"))
    
    print(f"\n\nStats:")
    print(f"  Tuples with disease.disease_name: {count_with_disease}/{len(tuples)}")
    print(f"  Tuples with drug.generic_name: {count_with_drug}/{len(tuples)}")
