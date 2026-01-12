#!/usr/bin/env python3
"""Debug: Show actual extracted values to diagnose SELECT issue."""

from docetl_query_executor import DocETLHealthcareQueryExecutor
from docetl_healthcare_evaluation import HealthcareEvaluationSystem

print("="*60)
print("Debug: Check extracted data structure")
print("="*60)

evaluator = HealthcareEvaluationSystem(
    data_dir="source_data/Healthcare",
    attributes_file="Query/Med/Med_attributes.json",
    queries_file="Query/Med/Join/join_queries.sql",
    ground_truth_dir="ground_truth/Healthcare"
)

executor = DocETLHealthcareQueryExecutor()

# Get first disease and drug doc
disease_docs = evaluator.documents.get("disease", [])[:1]
drug_docs = evaluator.documents.get("drug", [])[:1]

print("\n1. Disease extraction:")
disease_ext = executor.extract_disease_attributes(disease_docs[0].get('content', ''))
print(f"Keys in extracted disease: {list(disease_ext.keys())}")
print(f"Sample values:")
for k, v in list(disease_ext.items())[:5]:
    print(f"  {k}: {v[:50] if len(str(v)) > 50 else v}")

print("\n2. Drug extraction:")
drug_ext = executor.extract_drug_attributes(drug_docs[0].get('content', ''))
print(f"Keys in extracted drug: {list(drug_ext.keys())}")
print(f"Sample values:")
for k, v in list(drug_ext.items())[:5]:
    print(f"  {k}: {v[:50] if len(str(v)) > 50 else v}")

print("\n3. Performing join with these two records:")
result = executor._perform_join(
    [disease_ext],
    [drug_ext],
    "disease_name",
    ["disease.diagnostic_methods", "drug.manufacturer", "drug.brand_name", "disease.disease_name"]
)

print(f"Join result: {result}")

print("\n" + "="*60)
