#!/usr/bin/env python3
"""
Generate ground truth for join_1 query.

Query: SELECT d.disease_name, d.disease_type, d.treatments, dr.generic_name, dr.brand_name, dr.side_effects
       FROM disease d
       JOIN drug dr ON d.disease_name = dr.disease_name
       WHERE d.disease_name IN ('Type 2 Diabetes Mellitus', 'Tuberculosis', 'Fibromyalgia', 'Asthma', 'Depression')
"""

import json
import os
import re
from typing import Dict, List, Set

# Target diseases from WHERE clause
TARGET_DISEASES = {
    'Type 2 Diabetes Mellitus',
    'Tuberculosis', 
    'Fibromyalgia',
    'Asthma',
    'Depression'
}

def normalize_disease_name(name: str) -> str:
    """Normalize disease name for matching."""
    return name.lower().strip()

def extract_disease_info_from_text(text: str) -> Dict:
    """Extract disease information from unstructured text."""
    info = {
        'disease_name': None,
        'disease_type': None,
        'treatments': [],
        'diagnostic_methods': [],
        'common_symptoms': []
    }
    
    # Try to find disease name (look for section headers or first mention)
    lines = text.split('\n')
    
    for line in lines:
        # Look for disease type indicators
        if 'infectious' in line.lower():
            info['disease_type'] = 'infectious'
            break
        elif 'chronic' in line.lower():
            info['disease_type'] = 'chronic'
            break
        elif 'autoimmune' in line.lower():
            info['disease_type'] = 'autoimmune'
            break
        elif 'genetic' in line.lower():
            info['disease_type'] = 'genetic'
            break
        elif 'neurological' in line.lower():
            info['disease_type'] = 'neurological'
            break
    
    # Extract treatment keywords
    treatment_keywords = ['medication', 'therapy', 'treatment', 'drug', 'antibiotic', 'vaccine']
    for keyword in treatment_keywords:
        if keyword in text.lower():
            # Find sentence with treatment keyword
            for line in lines:
                if keyword in line.lower():
                    info['treatments'].append(line.strip())
                    break
    
    # Extract diagnostic keywords
    diagnostic_keywords = ['diagnostic', 'test', 'examination', 'scan', 'screening']
    for keyword in diagnostic_keywords:
        if keyword in text.lower():
            for line in lines:
                if keyword in line.lower():
                    info['diagnostic_methods'].append(line.strip())
                    break
    
    # Extract symptom keywords
    symptom_keywords = ['symptom', 'pain', 'fever', 'cough', 'weakness', 'fatigue']
    for keyword in symptom_keywords:
        if keyword in text.lower():
            for line in lines:
                if keyword in line.lower():
                    info['common_symptoms'].append(line.strip())
                    break
    
    return info

def find_disease_documents(diseases_dir: str, target_diseases: Set[str]) -> Dict[str, str]:
    """
    Find disease documents matching target diseases.
    Returns dict mapping disease_name -> file_path
    """
    found_diseases = {}
    
    if not os.path.exists(diseases_dir):
        print(f"Disease directory not found: {diseases_dir}")
        return found_diseases
    
    # Scan all disease files
    for filename in os.listdir(diseases_dir):
        if not filename.endswith('.txt'):
            continue
        
        filepath = os.path.join(diseases_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().lower()
                
                # Check for each target disease
                for disease in target_diseases:
                    disease_lower = disease.lower()
                    if disease_lower in content:
                        found_diseases[disease] = filepath
                        print(f"Found {disease} in {filename}")
        except Exception as e:
            print(f"Error reading {filename}: {e}")
    
    return found_diseases

def find_drug_documents(drugs_dir: str, disease_names: Set[str]) -> Dict[str, List[str]]:
    """
    Find drug documents that mention the target diseases.
    Returns dict mapping disease_name -> list of drug file paths
    """
    drugs_by_disease = {disease: [] for disease in disease_names}
    
    if not os.path.exists(drugs_dir):
        print(f"Drug directory not found: {drugs_dir}")
        return drugs_by_disease
    
    # Scan all drug files
    for filename in os.listdir(drugs_dir):
        if not filename.endswith('.txt'):
            continue
        
        filepath = os.path.join(drugs_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().lower()
                
                # Check for each disease mention
                for disease in disease_names:
                    disease_lower = disease.lower()
                    if disease_lower in content:
                        drugs_by_disease[disease].append(filepath)
        except Exception as e:
            print(f"Error reading {filename}: {e}")
    
    return drugs_by_disease

def main():
    # Set up paths
    base_dir = "/Users/aritramazumder/Documents/UDA-Bench-main/source_data/Healthcare"
    disease_dir = os.path.join(base_dir, "disease_small")
    drug_dir = os.path.join(base_dir, "drug_small")
    
    # Find disease and drug documents
    print("Searching for disease documents...")
    disease_docs = find_disease_documents(disease_dir, TARGET_DISEASES)
    
    print("\nSearching for drug documents...")
    drug_docs = find_drug_documents(drug_dir, TARGET_DISEASES)
    
    # Generate ground truth
    ground_truth = []
    
    for disease in sorted(TARGET_DISEASES):
        if disease not in disease_docs:
            print(f"Warning: No document found for disease '{disease}'")
            continue
        
        drug_files = drug_docs.get(disease, [])
        if not drug_files:
            print(f"Warning: No drugs found for disease '{disease}'")
            # Still add disease entry without drugs
            row = {
                'disease_name': disease,
                'disease_type': '',
                'treatments': '',
                'generic_name': '',
                'brand_name': '',
                'side_effects': ''
            }
            ground_truth.append(row)
            continue
        
        # Extract info from disease document
        disease_file = disease_docs[disease]
        with open(disease_file, 'r', encoding='utf-8', errors='ignore') as f:
            disease_text = f.read()
        disease_info = extract_disease_info_from_text(disease_text)
        
        # For each drug document, create a join result row
        for drug_file in drug_files[:5]:  # Limit to 5 drugs per disease
            with open(drug_file, 'r', encoding='utf-8', errors='ignore') as f:
                drug_text = f.read()
            
            # Extract drug info (simplified - just look for names and properties)
            # This is a simplified extraction - in reality you'd parse the full drug document
            row = {
                'disease_name': disease,
                'disease_type': disease_info.get('disease_type', ''),
                'treatments': ' || '.join(disease_info.get('treatments', []))[:50],  # Truncate for CSV
                'generic_name': os.path.basename(drug_file),  # Placeholder
                'brand_name': '',  # Would need to extract from drug_text
                'side_effects': ''  # Would need to extract from drug_text
            }
            ground_truth.append(row)
    
    # Save to CSV
    output_file = "/Users/aritramazumder/Documents/UDA-Bench-main/ground_truth/challenging_queries/join_1_ground_truth.csv"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    import csv
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        if ground_truth:
            writer = csv.DictWriter(f, fieldnames=ground_truth[0].keys())
            writer.writeheader()
            writer.writerows(ground_truth)
            print(f"\nGround truth saved to {output_file}")
            print(f"Total rows: {len(ground_truth)}")
        else:
            print("No ground truth data to save!")

if __name__ == '__main__':
    main()

