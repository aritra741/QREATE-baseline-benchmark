#!/usr/bin/env python3
"""Debug extraction to see what's being extracted."""

import json
from docetl_query_executor import DocETLHealthcareQueryExecutor
from docetl_healthcare_evaluation import HealthcareEvaluationSystem

print("="*60)
print("Debug: Check extraction quality")
print("="*60)

# Load data
evaluator = HealthcareEvaluationSystem(
    data_dir="source_data/Healthcare",
    attributes_file="Query/Med/Med_attributes.json",
    queries_file="Query/Med/Join/join_queries.sql",
    ground_truth_dir="ground_truth/Healthcare"
)

executor = DocETLHealthcareQueryExecutor()

# Test extraction on first few documents
print("\n1. Testing disease extraction...")
disease_docs = evaluator.documents.get("disease", [])[:3]

for i, doc in enumerate(disease_docs):
    print(f"\nDisease doc {i+1}:")
    print(f"  Content: {doc.get('content', '')[:150]}...")
    extracted = executor.extract_disease_attributes(doc.get('content', ''))
    print(f"  Extracted:")
    for key, val in extracted.items():
        if val != "Not found":
            print(f"    {key}: {val}")

print("\n" + "="*60)
print("2. Testing drug extraction...")
drug_docs = evaluator.documents.get("drug", [])[:3]

for i, doc in enumerate(drug_docs):
    print(f"\nDrug doc {i+1}:")
    print(f"  Content: {doc.get('content', '')[:150]}...")
    extracted = executor.extract_drug_attributes(doc.get('content', ''))
    print(f"  Extracted:")
    for key, val in extracted.items():
        if val != "Not found":
            print(f"    {key}: {val}")

print("\n" + "="*60)
