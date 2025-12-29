#!/usr/bin/env python3
"""
Create accurate ground truth for join_1 query using actual database CSV files.

Query: SELECT d.disease_name, d.disease_type, d.treatments, dr.generic_name, dr.brand_name, dr.side_effects
       FROM disease d
       JOIN drug dr ON d.disease_name = dr.disease_name
       WHERE d.disease_name IN ('Type 2 Diabetes Mellitus', 'Tuberculosis', 'Fibromyalgia', 'Asthma', 'Depression')
"""

import csv
import os

def main():
    base_dir = "/Users/aritramazumder/Documents/UDA-Bench-main/Query/Med"
    disease_file = os.path.join(base_dir, "disease.csv")
    drug_file = os.path.join(base_dir, "drug.csv")
    
    target_diseases = {
        'Type 2 Diabetes Mellitus',
        'Tuberculosis', 
        'Fibromyalgia',
        'Asthma',
        'Depression'
    }
    
    # Load disease data
    disease_data = {}
    with open(disease_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            disease_name = row.get('disease_name', '').strip()
            if disease_name in target_diseases:
                disease_data[disease_name] = row
                print(f"✓ Found disease: {disease_name}")
    
    print(f"\nLoaded {len(disease_data)} target diseases")
    
    # Load drug data, filter by target diseases
    drugs_by_disease = {d: [] for d in target_diseases}
    with open(drug_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            disease_field = row.get('disease_name', '').strip()
            if not disease_field:
                continue
            # Disease field can have multiple diseases separated by ||
            diseases_in_row = [d.strip() for d in disease_field.split('||')]
            for disease in diseases_in_row:
                if disease in target_diseases:
                    drugs_by_disease[disease].append(row)
    
    print(f"\nDrugs found per disease:")
    for disease, drugs in drugs_by_disease.items():
        print(f"  {disease}: {len(drugs)} drugs")
    
    # Generate ground truth
    output_file = "/Users/aritramazumder/Documents/UDA-Bench-main/ground_truth/challenging_queries/join_1_ground_truth.csv"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Write header matching the query SELECT clause
        writer.writerow(['disease_name', 'disease_type', 'treatments', 'generic_name', 'brand_name', 'side_effects'])
        
        # Write data for each disease
        total_rows = 0
        for disease_name in sorted(target_diseases):
            if disease_name not in disease_data:
                print(f"WARNING: Disease '{disease_name}' not found in disease.csv")
                continue
            
            disease_row = disease_data[disease_name]
            disease_type = disease_row.get('disease_type', '')
            treatments = disease_row.get('treatments', '')
            
            drugs = drugs_by_disease.get(disease_name, [])
            
            if not drugs:
                print(f"  WARNING: No drugs found for '{disease_name}'")
                # Still include the disease with empty drug fields
                writer.writerow([disease_name, disease_type, treatments, '', '', ''])
                total_rows += 1
            else:
                for drug_row in drugs:
                    generic_name = drug_row.get('generic_name', '')
                    brand_name = drug_row.get('brand_name', '')
                    side_effects = drug_row.get('side_effects', '')
                    
                    writer.writerow([
                        disease_name,
                        disease_type,
                        treatments,
                        generic_name,
                        brand_name,
                        side_effects
                    ])
                    total_rows += 1
    
    print(f"\n✓ Ground truth written to {output_file}")
    print(f"  Total rows: {total_rows}")
    
    # Display the generated ground truth
    print(f"\nGenerated ground truth (first 15 rows):")
    with open(output_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i < 15:  # Print first 15 rows
                print(f"  {row}")

if __name__ == "__main__":
    main()

