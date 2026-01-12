#!/usr/bin/env python3
"""Debug: Check extracted record structure."""

from docetl_query_executor import DocETLHealthcareQueryExecutor
from docetl_healthcare_evaluation import HealthcareEvaluationSystem

evaluator = HealthcareEvaluationSystem(
    data_dir="source_data/Healthcare",
    attributes_file="Query/Med/Med_attributes.json",
    queries_file="Query/Med/Join/join_queries.sql",
    ground_truth_dir="ground_truth/Healthcare"
)

executor = DocETLHealthcareQueryExecutor()

disease_docs = evaluator.documents.get("disease", [])[:2]
drug_docs = evaluator.documents.get("drug", [])[:2]

print("="*60)
print("DISEASE EXTRACTED STRUCTURE")
print("="*60)
for doc in disease_docs:
    ext = executor.extract_disease_attributes(doc.get('content', ''))
    print(f"\nKeys: {list(ext.keys())}")
    print(f"disease_name value: '{ext.get('disease_name', 'KEY NOT FOUND')}'")
    print(f"First 3 items:")
    for k, v in list(ext.items())[:3]:
        print(f"  {k}: {v[:50] if len(str(v)) > 50 else v}")

print("\n" + "="*60)
print("DRUG EXTRACTED STRUCTURE")
print("="*60)
for doc in drug_docs:
    ext = executor.extract_drug_attributes(doc.get('content', ''))
    print(f"\nKeys: {list(ext.keys())}")
    print(f"disease_name value: '{ext.get('disease_name', 'KEY NOT FOUND')}'")
    print(f"First 3 items:")
    for k, v in list(ext.items())[:3]:
        print(f"  {k}: {v[:50] if len(str(v)) > 50 else v}")

print("\n" + "="*60)
print("NOW PERFORMING JOIN")
print("="*60)

disease_extracted = [executor.extract_disease_attributes(doc.get('content', '')) for doc in disease_docs]
drug_extracted = [executor.extract_drug_attributes(doc.get('content', '')) for doc in drug_docs]

print(f"\nDisease records: {len(disease_extracted)}")
print(f"Drug records: {len(drug_extracted)}")
print(f"Join key: 'disease_name'")

# Check join key values
print("\nDisease disease_name values:")
for i, rec in enumerate(disease_extracted):
    print(f"  {i}: '{rec.get('disease_name', 'NOT FOUND')}'")

print("\nDrug disease_name values:")
for i, rec in enumerate(drug_extracted):
    print(f"  {i}: '{rec.get('disease_name', 'NOT FOUND')}'")

# Perform join
result = executor._perform_join(
    disease_extracted,
    drug_extracted,
    "disease_name",
    ["disease.disease_name", "drug.disease_name"]
)

print(f"\nJoin result: {len(result)} tuples")
for i, t in enumerate(result):
    print(f"  {i}: {t}")
