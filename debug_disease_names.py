#!/usr/bin/env python3
"""Debug: Show what disease_name values are extracted."""

from docetl_query_executor import DocETLHealthcareQueryExecutor
from docetl_healthcare_evaluation import HealthcareEvaluationSystem

evaluator = HealthcareEvaluationSystem(
    data_dir="source_data/Healthcare",
    attributes_file="Query/Med/Med_attributes.json",
    queries_file="Query/Med/Join/join_queries.sql",
    ground_truth_dir="ground_truth/Healthcare"
)

executor = DocETLHealthcareQueryExecutor()

# Get first 3 disease and drug docs
disease_docs = evaluator.documents.get("disease", [])[:3]
drug_docs = evaluator.documents.get("drug", [])[:3]

print("="*60)
print("DISEASE DISEASE_NAME VALUES:")
print("="*60)
for i, doc in enumerate(disease_docs):
    ext = executor.extract_disease_attributes(doc.get('content', ''))
    disease_name = ext.get("disease_name", "Not found")
    print(f"  Doc {i+1}: '{disease_name}'")

print("\n" + "="*60)
print("DRUG DISEASE_NAME VALUES:")
print("="*60)
for i, doc in enumerate(drug_docs):
    ext = executor.extract_drug_attributes(doc.get('content', ''))
    disease_name = ext.get("disease_name", "Not found")
    print(f"  Doc {i+1}: '{disease_name}'")

print("\n" + "="*60)
print("GROUND TRUTH VALUES:")
print("="*60)
gt_disease = evaluator.ground_truth.get("disease", {})
gt_drug = evaluator.ground_truth.get("drug", {})

print(f"\nDiseases in GT: {len(gt_disease)}")
for i, (id, row) in enumerate(list(gt_disease.items())[:5]):
    print(f"  {row.get('disease_name', 'N/A')}")

print(f"\nDrugs in GT: {len(gt_drug)}")
for i, (id, row) in enumerate(list(gt_drug.items())[:5]):
    print(f"  Generic: {row.get('generic_name', 'N/A')}")
    print(f"    Treats: {row.get('disease_name', 'N/A')}")

print("\n" + "="*60)
