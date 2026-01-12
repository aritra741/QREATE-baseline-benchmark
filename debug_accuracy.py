#!/usr/bin/env python3
"""Debug the accuracy matching logic."""

from docetl_healthcare_evaluation import HealthcareEvaluationSystem
from docetl_query_executor import DocETLHealthcareQueryExecutor

evaluator = HealthcareEvaluationSystem(
    data_dir="source_data/Healthcare",
    attributes_file="Query/Med/Med_attributes.json",
    queries_file="Query/Med/Join/join_queries.sql",
    ground_truth_dir="ground_truth/Healthcare"
)

executor = DocETLHealthcareQueryExecutor()

# Get some docs
disease_docs = evaluator.documents.get("disease", [])[:5]
drug_docs = evaluator.documents.get("drug", [])[:5]

# Extract
disease_extracted = []
for doc in disease_docs:
    ext = executor.extract_disease_attributes(doc.get('content', ''))
    disease_extracted.append(ext)

drug_extracted = []
for doc in drug_docs:
    ext = executor.extract_drug_attributes(doc.get('content', ''))
    drug_extracted.append(ext)

# Perform join
join_results = executor._perform_join(
    disease_extracted,
    drug_extracted,
    "disease_name",
    ["disease.disease_name", "drug.disease_name"]
)

print(f"Join produced {len(join_results)} tuples\n")

# Show sample tuples
print("Sample joined tuples:")
for i, t in enumerate(join_results[:10]):
    print(f"  {i+1}. {t}")

# Now check accuracy matching
print("\n" + "="*60)
print("CHECKING GROUND TRUTH MATCHING")
print("="*60)

gt_disease = evaluator.ground_truth.get("disease", {})
gt_drug = evaluator.ground_truth.get("drug", {})

# Build GT pairs
gt_disease_names = set()
gt_disease_drug_pairs = set()

for dis_id, dis_row in gt_disease.items():
    disease_name = dis_row.get("disease_name", "")
    if disease_name:
        norm_disease = evaluator._normalize_value(disease_name)
        gt_disease_names.add(norm_disease)
        print(f"\nDisease: '{disease_name}' -> normalized: '{norm_disease}'")
        
        drugs_str = dis_row.get("drugs", "")
        if drugs_str:
            for drug_name in drugs_str.split("||"):
                drug_name = drug_name.strip()
                if drug_name:
                    norm_drug = evaluator._normalize_value(drug_name)
                    gt_disease_drug_pairs.add((norm_disease, norm_drug))
                    print(f"  Treats: '{drug_name}' -> normalized: '{norm_drug}'")

print(f"\n\nTotal GT disease-drug pairs: {len(gt_disease_drug_pairs)}")

# Check extracted pairs
print("\n" + "="*60)
print("EXTRACTED PAIRS")
print("="*60)

extracted_pairs = set()
for t in join_results:
    disease_name = t.get("disease.disease_name", "")
    drug_name = t.get("drug.disease_name", "")
    
    if disease_name and drug_name:
        norm_disease = evaluator._normalize_value(disease_name)
        norm_drug = evaluator._normalize_value(drug_name)
        extracted_pairs.add((norm_disease, norm_drug))

print(f"Extracted {len(extracted_pairs)} unique pairs")
for i, p in enumerate(list(extracted_pairs)[:5]):
    print(f"  {i+1}. ({p[0][:30]}..., {p[1][:30]}...)")

# Try matching
print("\n" + "="*60)
print("MATCHING")
print("="*60)

matches = 0
for extracted_pair in extracted_pairs:
    for gt_pair in gt_disease_drug_pairs:
        if (evaluator._values_match(extracted_pair[0], gt_pair[0]) and 
            evaluator._values_match(extracted_pair[1], gt_pair[1])):
            matches += 1
            print(f"✓ MATCH: ({extracted_pair[0]}, {extracted_pair[1]}) <-> ({gt_pair[0]}, {gt_pair[1]})")
            break

print(f"\nTotal matches: {matches}/{len(extracted_pairs)}")
