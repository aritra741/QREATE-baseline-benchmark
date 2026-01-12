#!/usr/bin/env python3
"""Check what the actual document content looks like."""

from docetl_healthcare_evaluation import HealthcareEvaluationSystem

evaluator = HealthcareEvaluationSystem(
    data_dir="source_data/Healthcare",
    attributes_file="Query/Med/Med_attributes.json",
    queries_file="Query/Med/Join/join_queries.sql",
    ground_truth_dir="ground_truth/Healthcare"
)

disease_docs = evaluator.documents.get("disease", [])[:3]
drug_docs = evaluator.documents.get("drug", [])[:3]

print("="*60)
print("DISEASE DOCUMENTS")
print("="*60)
for i, doc in enumerate(disease_docs):
    print(f"\nDisease {i+1} (ID: {doc.get('id')}):")
    content = doc.get('content', '')
    print(content[:300])
    print("...")

print("\n" + "="*60)
print("DRUG DOCUMENTS")
print("="*60)
for i, doc in enumerate(drug_docs):
    print(f"\nDrug {i+1} (ID: {doc.get('id')}):")
    content = doc.get('content', '')
    print(content[:300])
    print("...")
